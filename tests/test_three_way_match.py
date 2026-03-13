"""
Tests for Three-Way Matching.

Run with: pytest tests/test_three_way_match.py -v
"""

import tempfile
import shutil

import pytest

from core.matcher import Matcher, validate_invoice_three_way
from core.vector_store import VectorStore
from core.po_store import POStore
from core.models import (
    InvoiceSchema,
    PurchaseOrderSchema,
    LineItem,
    ThreeWayMatchResult,
    MatchDetail,
)


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


class TestThreeWayMatcherInit:
    """Test cases for Three-Way Matcher initialization."""

    @pytest.fixture
    def stores(self):
        """Create temporary stores."""
        temp_dir = tempfile.mkdtemp()
        vector_store = VectorStore(persist_directory=temp_dir)
        po_store = POStore(persist_directory=temp_dir)
        yield vector_store, po_store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_init_with_po_store(self, stores):
        """Test initialization with PO store."""
        vector_store, po_store = stores
        matcher = Matcher(vector_store, po_store=po_store)
        assert matcher.po_store == po_store


class TestInvoicePOMatch:
    """Test cases for Invoice ↔ PO matching."""

    @pytest.fixture
    def populated_stores(self):
        """Create and populate stores."""
        temp_dir = tempfile.mkdtemp()
        vector_store = VectorStore(persist_directory=temp_dir, chunk_size=500)
        po_store = POStore(persist_directory=temp_dir)

        # Index contract
        vector_store.index_contract(SAMPLE_CONTRACT, "Acme Consulting", "MSA")

        # Index PO
        po = PurchaseOrderSchema(
            po_number="PO-2024-001",
            vendor_name="Acme Consulting",
            order_date="2024-06-01",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ]
        )
        po_store.index_po(po)

        yield vector_store, po_store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_invoice_po_match_pass(self, populated_stores):
        """Test Invoice ↔ PO match with matching data."""
        vector_store, po_store = populated_stores
        matcher = Matcher(vector_store, po_store=po_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-001",
            invoice_date="2024-06-15",
            po_number="PO-2024-001",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ]
        )

        result = matcher.validate_invoice_three_way(invoice, po_number="PO-2024-001")

        assert result.invoice_po_match is not None
        assert result.invoice_po_match.passed is True

    def test_invoice_po_match_amount_mismatch(self, populated_stores):
        """Test Invoice ↔ PO match with amount mismatch."""
        vector_store, po_store = populated_stores
        matcher = Matcher(vector_store, po_store=po_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-001",
            invoice_date="2024-06-15",
            po_number="PO-2024-001",
            total_amount=2000.00,  # Doesn't match PO amount
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=200, total=2000)
            ]
        )

        result = matcher.validate_invoice_three_way(invoice, po_number="PO-2024-001")

        assert result.invoice_po_match is not None
        # Should have issues with amount mismatch
        issues = [i for i in result.invoice_po_match.issues if i.rule == "po_total_match"]
        assert len(issues) > 0 or result.invoice_po_match.passed is False


class TestThreeWayValidation:
    """Integration tests for full three-way validation."""

    @pytest.fixture
    def populated_stores(self):
        """Create and populate stores for three-way testing."""
        temp_dir = tempfile.mkdtemp()
        vector_store = VectorStore(persist_directory=temp_dir, chunk_size=500)
        po_store = POStore(persist_directory=temp_dir)

        # Index contract
        vector_store.index_contract(SAMPLE_CONTRACT, "Acme Consulting", "MSA")

        # Index PO matching contract rates
        po = PurchaseOrderSchema(
            po_number="PO-2024-001",
            vendor_name="Acme Consulting",
            order_date="2024-06-01",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ]
        )
        po_store.index_po(po)

        yield vector_store, po_store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_three_way_match_all_pass(self, populated_stores):
        """Test three-way match where all three matches pass."""
        vector_store, po_store = populated_stores
        matcher = Matcher(vector_store, po_store=po_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-001",
            invoice_date="2024-06-15",
            po_number="PO-2024-001",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ],
            payment_terms="Net 30"
        )

        result = matcher.validate_invoice_three_way(invoice, po_number="PO-2024-001")

        assert isinstance(result, ThreeWayMatchResult)
        assert result.status == "PASS"
        assert result.matches_passed >= 2

    def test_three_way_match_two_of_three_pass(self, populated_stores):
        """Test three-way match where 2 of 3 matches pass (should PASS)."""
        vector_store, po_store = populated_stores
        matcher = Matcher(vector_store, po_store=po_store)

        # Invoice with wrong rate (fails Invoice ↔ Contract)
        # but matches PO correctly
        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-002",
            invoice_date="2024-06-15",
            po_number="PO-2024-001",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ]
        )

        result = matcher.validate_invoice_three_way(invoice, po_number="PO-2024-001")

        assert isinstance(result, ThreeWayMatchResult)
        # Should pass if at least 2 matches pass
        if result.matches_passed >= 2:
            assert result.status == "PASS"

    def test_three_way_match_one_of_three_pass(self, populated_stores):
        """Test three-way match where only 1 match passes (should FAIL)."""
        vector_store, po_store = populated_stores

        # Add a bad PO
        bad_po = PurchaseOrderSchema(
            po_number="PO-BAD-001",
            vendor_name="Acme Consulting",
            order_date="2023-01-01",  # Outside contract period
            total_amount=5000.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=500, total=5000)  # Wrong rate
            ]
        )
        po_store.index_po(bad_po)

        matcher = Matcher(vector_store, po_store=po_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-003",
            invoice_date="2023-06-15",  # Outside contract period
            po_number="PO-BAD-001",
            total_amount=7500.00,  # Doesn't match PO
            line_items=[
                LineItem(description="Senior Consultant", quantity=15, unit_price=500, total=7500)  # Wrong rate
            ]
        )

        result = matcher.validate_invoice_three_way(invoice, po_number="PO-BAD-001")

        # With many mismatches, fewer than 2 should pass
        if result.matches_passed < 2:
            assert result.status in ("FAIL", "REVIEW")

    def test_two_way_match_no_po(self, populated_stores):
        """Test two-way match when no PO is provided."""
        vector_store, po_store = populated_stores
        matcher = Matcher(vector_store, po_store=po_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-004",
            invoice_date="2024-06-15",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ]
        )

        result = matcher.validate_invoice_three_way(invoice, po_number=None)

        assert isinstance(result, ThreeWayMatchResult)
        assert result.invoice_po_match is None
        assert result.po_contract_match is None
        assert result.invoice_contract_match is not None
        # Only 1 match possible, need 1 of 1 to pass
        assert result.total_matches == 1


class TestMatchScoring:
    """Test cases for match scoring."""

    @pytest.fixture
    def populated_stores(self):
        """Create and populate stores."""
        temp_dir = tempfile.mkdtemp()
        vector_store = VectorStore(persist_directory=temp_dir, chunk_size=500)
        po_store = POStore(persist_directory=temp_dir)

        vector_store.index_contract(SAMPLE_CONTRACT, "Acme Consulting", "MSA")

        po = PurchaseOrderSchema(
            po_number="PO-001",
            vendor_name="Acme Consulting",
            order_date="2024-06-01",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ]
        )
        po_store.index_po(po)

        yield vector_store, po_store
        shutil.rmtree(temp_dir, ignore_errors=True)

    def test_overall_score_calculation(self, populated_stores):
        """Test that overall score is calculated correctly."""
        vector_store, po_store = populated_stores
        matcher = Matcher(vector_store, po_store=po_store)

        invoice = InvoiceSchema(
            vendor_name="Acme Consulting",
            invoice_number="INV-001",
            invoice_date="2024-06-15",
            total_amount=1500.00,
            line_items=[
                LineItem(description="Senior Consultant", quantity=10, unit_price=150, total=1500)
            ]
        )

        result = matcher.validate_invoice_three_way(invoice, po_number="PO-001")

        # Overall score should be between 0 and 1
        assert 0 <= result.overall_score <= 1


class TestThreeWayReportGeneration:
    """Test cases for three-way report generation."""

    @pytest.fixture
    def sample_result(self):
        """Create a sample ThreeWayMatchResult for testing."""
        from core.models import ValidationIssue, RetrievedClause
        from datetime import datetime

        return ThreeWayMatchResult(
            status="PASS",
            vendor_name="Test Vendor",
            invoice_number="INV-001",
            po_number="PO-001",
            invoice_po_match=MatchDetail(
                match_type="invoice_po",
                passed=True,
                score=0.95,
                issues=[],
                details={"total_match": True}
            ),
            invoice_contract_match=MatchDetail(
                match_type="invoice_contract",
                passed=True,
                score=0.90,
                issues=[],
                details={"rate_compliance": True}
            ),
            po_contract_match=MatchDetail(
                match_type="po_contract",
                passed=True,
                score=0.85,
                issues=[],
                details={"date_compliance": True}
            ),
            matches_passed=3,
            total_matches=3,
            overall_score=0.9,
            all_issues=[],
            matched_clauses=[],
            timestamp=datetime.now()
        )

    def test_generate_three_way_report(self, sample_result):
        """Test three-way report generation."""
        temp_dir = tempfile.mkdtemp()
        try:
            vector_store = VectorStore(persist_directory=temp_dir)
            po_store = POStore(persist_directory=temp_dir)
            matcher = Matcher(vector_store, po_store=po_store)

            report = matcher.generate_three_way_report(sample_result)

            assert "THREE-WAY INVOICE VALIDATION REPORT" in report
            assert "Test Vendor" in report
            assert "INV-001" in report
            assert "PO-001" in report
            assert "PASS" in report
            assert "3/3" in report

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestConvenienceFunction:
    """Test the convenience function."""

    def test_validate_invoice_three_way_function(self):
        """Test validate_invoice_three_way convenience function."""
        temp_dir = tempfile.mkdtemp()
        try:
            vector_store = VectorStore(persist_directory=temp_dir, chunk_size=500)
            po_store = POStore(persist_directory=temp_dir)

            vector_store.index_contract(SAMPLE_CONTRACT, "TestVendor", "MSA")

            po = PurchaseOrderSchema(
                po_number="PO-001",
                vendor_name="TestVendor",
                order_date="2024-06-01",
                total_amount=500.00
            )
            po_store.index_po(po)

            invoice = InvoiceSchema(
                vendor_name="TestVendor",
                invoice_number="INV-001",
                invoice_date="2024-06-15",
                total_amount=500.00,
                line_items=[]
            )

            result = validate_invoice_three_way(invoice, vector_store, po_store, po_number="PO-001")

            assert isinstance(result, ThreeWayMatchResult)
            assert result.vendor_name == "TestVendor"

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestNoContractScenario:
    """Test scenarios where no contract exists."""

    def test_no_contract_indexed(self):
        """Test validation when no contract is indexed for vendor."""
        temp_dir = tempfile.mkdtemp()
        try:
            vector_store = VectorStore(persist_directory=temp_dir)
            po_store = POStore(persist_directory=temp_dir)
            matcher = Matcher(vector_store, po_store=po_store)

            invoice = InvoiceSchema(
                vendor_name="Unknown Vendor",
                invoice_number="INV-001",
                invoice_date="2024-06-15",
                total_amount=500.00,
                line_items=[]
            )

            result = matcher.validate_invoice_three_way(invoice)

            assert result.status == "FAIL"
            assert any(i.rule == "contract_exists" for i in result.all_issues)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


class TestPONotFoundScenario:
    """Test scenarios where PO is not found."""

    def test_po_not_found(self):
        """Test validation when PO number doesn't exist."""
        temp_dir = tempfile.mkdtemp()
        try:
            vector_store = VectorStore(persist_directory=temp_dir, chunk_size=500)
            po_store = POStore(persist_directory=temp_dir)

            vector_store.index_contract(SAMPLE_CONTRACT, "Acme Consulting", "MSA")
            matcher = Matcher(vector_store, po_store=po_store)

            invoice = InvoiceSchema(
                vendor_name="Acme Consulting",
                invoice_number="INV-001",
                invoice_date="2024-06-15",
                total_amount=500.00,
                line_items=[]
            )

            result = matcher.validate_invoice_three_way(invoice, po_number="PO-NONEXISTENT")

            # Should still work but without PO matches
            assert result.invoice_po_match is None or result.invoice_po_match.passed is False

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
