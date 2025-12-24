"""
Tests for the Matcher Engine.

Run with: pytest tests/test_matcher.py -v
"""

import tempfile
import shutil
from datetime import datetime

import pytest

from core.matcher import Matcher, validate_invoice
from core.vector_store import VectorStore
from core.models import InvoiceSchema, LineItem, MatchResult, ValidationIssue


# Sample contract text for testing
SAMPLE_CONTRACT = """
# Master Service Agreement - Acme Consulting

## Effective Date
This agreement is effective from January 1, 2024 and terminates on December 31, 2024.

## Rate Card

The following rates apply to all services:

- Senior Consultant: $150 per hour
- Junior Consultant: $85 per hour
- Project Manager: $125/hr
- Technical Lead: $175/hour

## Payment Terms

All invoices are due within Net 30 days of receipt.
Late payments will incur a 1.5% monthly interest charge.

## Services

Consulting services for software development and technical advisory.
"""


class TestMatcherInit:
    """Test cases for Matcher initialization."""

    @pytest.fixture
    def temp_store(self):
        """Create a temporary vector store."""
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir)
        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init_default(self, temp_store):
        """Test default initialization."""
        matcher = Matcher(temp_store)
        assert matcher.vector_store == temp_store
        assert matcher.model == "phi3.5"


class TestRateExtraction:
    """Test cases for rate extraction from clauses."""

    @pytest.fixture
    def matcher(self):
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir)
        matcher = Matcher(store)
        yield matcher
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_extract_rates_standard_format(self, matcher):
        """Test extracting rates in standard format."""
        from core.models import RetrievedClause

        clauses = [
            RetrievedClause(
                text="Senior Consultant: $150 per hour\nJunior Developer: $85/hr",
                vendor_name="Test",
                similarity_score=0.9,
                chunk_id="1",
                metadata={}
            )
        ]

        rates = matcher._extract_rates_from_clauses(clauses)

        assert "Senior Consultant" in rates
        assert rates["Senior Consultant"] == 150
        assert "Junior Developer" in rates
        assert rates["Junior Developer"] == 85

    def test_extract_rates_dash_format(self, matcher):
        """Test extracting rates with dash separator."""
        from core.models import RetrievedClause

        clauses = [
            RetrievedClause(
                text="Project Manager - $125/hour",
                vendor_name="Test",
                similarity_score=0.9,
                chunk_id="1",
                metadata={}
            )
        ]

        rates = matcher._extract_rates_from_clauses(clauses)

        assert "Project Manager" in rates
        assert rates["Project Manager"] == 125


class TestPaymentTermsExtraction:
    """Test cases for payment terms extraction."""

    @pytest.fixture
    def matcher(self):
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir)
        matcher = Matcher(store)
        yield matcher
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_extract_net_terms(self, matcher):
        """Test extracting Net XX payment terms."""
        from core.models import RetrievedClause

        clauses = [
            RetrievedClause(
                text="Payment is due Net 30 days from invoice date.",
                vendor_name="Test",
                similarity_score=0.9,
                chunk_id="1",
                metadata={}
            )
        ]

        terms = matcher._extract_payment_terms(clauses)
        assert terms == "Net 30"

    def test_extract_within_days(self, matcher):
        """Test extracting 'within X days' format."""
        from core.models import RetrievedClause

        clauses = [
            RetrievedClause(
                text="Payment must be made within 15 days.",
                vendor_name="Test",
                similarity_score=0.9,
                chunk_id="1",
                metadata={}
            )
        ]

        terms = matcher._extract_payment_terms(clauses)
        assert terms == "Net 15"


class TestLineItemValidation:
    """Test cases for line item validation."""

    @pytest.fixture
    def matcher(self):
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir)
        matcher = Matcher(store)
        yield matcher
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_valid_line_items(self, matcher):
        """Test validation of correctly calculated line items."""
        invoice = InvoiceSchema(
            vendor_name="Test",
            invoice_number="001",
            invoice_date="2024-01-15",
            total_amount=500.00,
            line_items=[
                LineItem(description="Service A", quantity=5, unit_price=100, total=500)
            ]
        )

        issues = matcher._validate_line_item_totals(invoice)
        assert len(issues) == 0

    def test_incorrect_line_item_math(self, matcher):
        """Test detection of incorrect line item calculation."""
        invoice = InvoiceSchema(
            vendor_name="Test",
            invoice_number="001",
            invoice_date="2024-01-15",
            total_amount=600.00,
            line_items=[
                LineItem(description="Service A", quantity=5, unit_price=100, total=600)  # Should be 500
            ]
        )

        issues = matcher._validate_line_item_totals(invoice)
        assert len(issues) >= 1
        assert any(i.rule == "line_item_math" for i in issues)

    def test_total_sum_mismatch(self, matcher):
        """Test detection of total sum mismatch."""
        invoice = InvoiceSchema(
            vendor_name="Test",
            invoice_number="001",
            invoice_date="2024-01-15",
            total_amount=1000.00,  # Doesn't match line items
            line_items=[
                LineItem(description="Service A", quantity=5, unit_price=100, total=500)
            ]
        )

        issues = matcher._validate_line_item_totals(invoice)
        assert any(i.rule == "total_sum" for i in issues)


class TestDateParsing:
    """Test cases for date parsing."""

    @pytest.fixture
    def matcher(self):
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir)
        matcher = Matcher(store)
        yield matcher
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_parse_iso_date(self, matcher):
        """Test parsing ISO format date."""
        date = matcher._parse_date("2024-01-15")
        assert date is not None
        assert date.year == 2024
        assert date.month == 1
        assert date.day == 15

    def test_parse_us_date(self, matcher):
        """Test parsing US format date."""
        date = matcher._parse_date("01/15/2024")
        assert date is not None
        assert date.month == 1
        assert date.day == 15

    def test_parse_invalid_date(self, matcher):
        """Test parsing invalid date returns None."""
        date = matcher._parse_date("not a date")
        assert date is None


class TestFullValidation:
    """Integration tests for full validation flow."""

    @pytest.fixture
    def populated_store(self):
        """Create and populate a vector store."""
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir, chunk_size=500)
        store.index_contract(SAMPLE_CONTRACT, "Acme Consulting", "MSA")
        yield store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_validate_passing_invoice(self, populated_store):
        """Test validation of a compliant invoice."""
        matcher = Matcher(populated_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-001",
            invoice_date="2024-06-15",
            total_amount=1500.00,
            line_items=[
                LineItem(
                    description="Senior Consultant",
                    quantity=10,
                    unit_price=150,
                    total=1500
                )
            ],
            payment_terms="Net 30"
        )

        result = matcher.validate_invoice(invoice)

        assert isinstance(result, MatchResult)
        assert result.vendor_name == "Acme Consulting"
        # Should pass or review (no critical issues)
        assert result.status in ("PASS", "REVIEW")

    def test_validate_rate_violation(self, populated_store):
        """Test detection of rate violation."""
        matcher = Matcher(populated_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-002",
            invoice_date="2024-06-15",
            total_amount=2000.00,
            line_items=[
                LineItem(
                    description="Senior Consultant",
                    quantity=10,
                    unit_price=200,  # Exceeds contract rate of $150
                    total=2000
                )
            ]
        )

        result = matcher.validate_invoice(invoice)

        # Should have rate compliance issue
        rate_issues = [i for i in result.issues if i.rule == "rate_compliance"]
        assert len(rate_issues) > 0 or result.status == "FAIL"

    def test_validate_no_contract(self, populated_store):
        """Test validation when no contract exists for vendor."""
        matcher = Matcher(populated_store)

        invoice = InvoiceSchema(
            vendor_name="Unknown Vendor",
            invoice_number="INV-003",
            invoice_date="2024-06-15",
            total_amount=500.00,
            line_items=[]
        )

        result = matcher.validate_invoice(invoice)

        assert result.status == "FAIL"
        assert any(i.rule == "contract_exists" for i in result.issues)

    def test_matched_clauses_returned(self, populated_store):
        """Test that matched clauses are returned in result."""
        matcher = Matcher(populated_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-004",
            invoice_date="2024-06-15",
            total_amount=500.00,
            line_items=[]
        )

        result = matcher.validate_invoice(invoice)

        assert len(result.matched_clauses) > 0


class TestReportGeneration:
    """Test cases for report generation."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample MatchResult for testing."""
        return MatchResult(
            status="FAIL",
            vendor_name="Test Vendor",
            invoice_number="INV-001",
            issues=[
                ValidationIssue(
                    rule="rate_compliance",
                    severity="critical",
                    message="Rate exceeds contract",
                    invoice_value=200,
                    contract_value=150
                ),
                ValidationIssue(
                    rule="total_sum",
                    severity="warning",
                    message="Totals don't match",
                    invoice_value=1000,
                    contract_value=900
                )
            ],
            matched_clauses=[],
            confidence_score=0.5
        )

    def test_generate_report(self, sample_result):
        """Test report generation."""
        temp_dir = tempfile.mkdtemp()
        try:
            store = VectorStore(persist_directory=temp_dir)
            matcher = Matcher(store)

            report = matcher.generate_report(sample_result)

            assert "INVOICE VALIDATION REPORT" in report
            assert "FAIL" in report
            assert "Test Vendor" in report
            assert "INV-001" in report
            assert "rate_compliance" in report
            assert "Critical: 1" in report

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestConvenienceFunction:
    """Test the convenience function."""

    def test_validate_invoice_function(self):
        """Test validate_invoice convenience function."""
        temp_dir = tempfile.mkdtemp()
        try:
            store = VectorStore(persist_directory=temp_dir)
            store.index_contract(SAMPLE_CONTRACT, "TestVendor", "MSA")

            invoice = InvoiceSchema(
                vendor_name="TestVendor",
                invoice_number="001",
                invoice_date="2024-06-15",
                total_amount=100,
                line_items=[]
            )

            result = validate_invoice(invoice, store)

            assert isinstance(result, MatchResult)
            assert result.vendor_name == "TestVendor"

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestFuzzyMatching:
    """Test fuzzy matching logic."""

    @pytest.fixture
    def matcher(self):
        temp_dir = tempfile.mkdtemp()
        store = VectorStore(persist_directory=temp_dir)
        matcher = Matcher(store)
        yield matcher
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_fuzzy_match_exact(self, matcher):
        """Test fuzzy match with exact match."""
        assert matcher._fuzzy_match("senior consultant", "senior consultant") is True

    def test_fuzzy_match_partial(self, matcher):
        """Test fuzzy match with partial match."""
        assert matcher._fuzzy_match("senior consultant services", "senior consultant") is True

    def test_fuzzy_match_no_match(self, matcher):
        """Test fuzzy match with no match."""
        assert matcher._fuzzy_match("junior developer", "senior consultant") is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
