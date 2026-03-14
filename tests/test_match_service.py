"""
Tests for MatchService.

Tests delegation to Matcher, auto PO matching, and report generation.
Core matching logic is tested separately in test_matcher.py and
test_three_way_match.py.
"""

import pytest
from unittest.mock import MagicMock

from core.services.match_service import MatchService, POMatchResult
from core.models import (
    InvoiceSchema,
    LineItem,
    MatchResult,
    PurchaseOrderSchema,
    ThreeWayMatchResult,
    MatchDetail,
    ValidationIssue,
)


# ==================== FIXTURES ====================


@pytest.fixture
def sample_invoice():
    return InvoiceSchema(
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        invoice_date="2024-01-15",
        total_amount=5000.00,
        po_number="PO-001",
        line_items=[
            LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
        ],
    )


@pytest.fixture
def sample_invoice_no_po():
    return InvoiceSchema(
        vendor_name="Acme Corp",
        invoice_number="INV-002",
        invoice_date="2024-01-15",
        total_amount=5000.00,
        po_number=None,
        line_items=[
            LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
        ],
    )


@pytest.fixture
def sample_po():
    return PurchaseOrderSchema(
        po_number="PO-001",
        vendor_name="Acme Corp",
        order_date="2024-01-10",
        total_amount=5000.00,
        line_items=[
            LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
        ],
    )


@pytest.fixture
def mock_match_result():
    return MatchResult(
        status="PASS",
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        issues=[],
        matched_clauses=[],
        confidence_score=0.95,
    )


@pytest.fixture
def mock_three_way_result():
    return ThreeWayMatchResult(
        status="PASS",
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        po_number="PO-001",
        invoice_po_match=MatchDetail(
            match_type="invoice_po", passed=True, score=0.95, issues=[]
        ),
        invoice_contract_match=MatchDetail(
            match_type="invoice_contract", passed=True, score=0.90, issues=[]
        ),
        po_contract_match=MatchDetail(
            match_type="po_contract", passed=True, score=0.85, issues=[]
        ),
        matches_passed=3,
        total_matches=3,
        overall_score=0.90,
        all_issues=[],
        matched_clauses=[],
    )


@pytest.fixture
def mock_matcher(mock_match_result, mock_three_way_result):
    matcher = MagicMock()
    matcher.validate_invoice.return_value = mock_match_result
    matcher.validate_invoice_three_way.return_value = mock_three_way_result
    matcher.generate_report.return_value = "Two-way report text"
    matcher.generate_three_way_report.return_value = "Three-way report text"
    return matcher


@pytest.fixture
def mock_po_store():
    return MagicMock()


@pytest.fixture
def service(mock_matcher, mock_po_store):
    return MatchService(mock_matcher, po_store=mock_po_store)


@pytest.fixture
def service_no_po_store(mock_matcher):
    return MatchService(mock_matcher)


# ==================== TWO-WAY VALIDATION ====================


class TestValidate:
    """Tests for MatchService.validate()."""

    def test_delegates_to_matcher(self, service, mock_matcher, sample_invoice):
        result = service.validate(sample_invoice)

        assert result.status == "PASS"
        mock_matcher.validate_invoice.assert_called_once_with(
            sample_invoice, None
        )

    def test_with_vendor_override(self, service, mock_matcher, sample_invoice):
        service.validate(sample_invoice, vendor_name="Override Vendor")

        mock_matcher.validate_invoice.assert_called_once_with(
            sample_invoice, "Override Vendor"
        )

    def test_returns_matcher_result(self, service, sample_invoice, mock_match_result):
        result = service.validate(sample_invoice)
        assert result is mock_match_result


# ==================== THREE-WAY VALIDATION ====================


class TestValidateThreeWay:
    """Tests for MatchService.validate_three_way()."""

    def test_delegates_to_matcher(self, service, mock_matcher, sample_invoice):
        result = service.validate_three_way(sample_invoice, po_number="PO-001")

        assert result.status == "PASS"
        assert result.matches_passed == 3
        mock_matcher.validate_invoice_three_way.assert_called_once_with(
            sample_invoice, "PO-001"
        )

    def test_explicit_po_skips_auto_match(self, service, mock_po_store, sample_invoice):
        """When po_number is explicitly provided, auto-match is skipped."""
        service.validate_three_way(sample_invoice, po_number="PO-EXPLICIT")

        mock_po_store.get_po_by_number.assert_not_called()
        mock_po_store.get_pos_by_vendor.assert_not_called()

    def test_auto_match_exact(self, service, mock_matcher, mock_po_store, sample_invoice_no_po):
        """Auto-match finds PO via invoice.po_number."""
        # invoice_no_po has no po_number, but let's give it one
        sample_invoice_no_po.po_number = "PO-AUTO"
        mock_po_store.get_po_by_number.return_value = PurchaseOrderSchema(
            po_number="PO-AUTO", vendor_name="Acme Corp",
            order_date="2024-01-10", total_amount=5000.00,
        )

        service.validate_three_way(sample_invoice_no_po)

        # Should pass auto-matched PO number to matcher
        mock_matcher.validate_invoice_three_way.assert_called_once_with(
            sample_invoice_no_po, "PO-AUTO"
        )

    def test_auto_match_fuzzy(self, service, mock_matcher, mock_po_store, sample_invoice_no_po):
        """Auto-match finds PO via vendor + amount fuzzy match."""
        mock_po_store.get_po_by_number.return_value = None
        mock_po_store.get_pos_by_vendor.return_value = [
            PurchaseOrderSchema(
                po_number="PO-FUZZY", vendor_name="Acme Corp",
                order_date="2024-01-10", total_amount=5000.00,
            )
        ]

        service.validate_three_way(sample_invoice_no_po)

        mock_matcher.validate_invoice_three_way.assert_called_once_with(
            sample_invoice_no_po, "PO-FUZZY"
        )

    def test_auto_match_no_result_falls_back(self, service, mock_matcher, mock_po_store, sample_invoice_no_po):
        """When auto-match finds nothing, falls back to two-way."""
        mock_po_store.get_po_by_number.return_value = None
        mock_po_store.get_pos_by_vendor.return_value = []

        service.validate_three_way(sample_invoice_no_po)

        # Called with None po_number (two-way)
        mock_matcher.validate_invoice_three_way.assert_called_once_with(
            sample_invoice_no_po, None
        )

    def test_returns_matcher_result(self, service, sample_invoice, mock_three_way_result):
        result = service.validate_three_way(sample_invoice, po_number="PO-001")
        assert result is mock_three_way_result


# ==================== AUTO PO MATCHING ====================


class TestAutoMatchPO:
    """Tests for MatchService.auto_match_po()."""

    def test_no_po_store(self, service_no_po_store, sample_invoice):
        result = service_no_po_store.auto_match_po(sample_invoice)
        assert result.po_number is None
        assert result.match_method is None

    def test_exact_match(self, service, mock_po_store, sample_invoice):
        """Exact match by invoice.po_number."""
        mock_po_store.get_po_by_number.return_value = PurchaseOrderSchema(
            po_number="PO-001", vendor_name="Acme Corp",
            order_date="2024-01-10", total_amount=5000.00,
        )

        result = service.auto_match_po(sample_invoice)
        assert result.po_number == "PO-001"
        assert result.match_method == "exact"
        assert result.confidence == 1.0

    def test_exact_match_not_found_falls_to_fuzzy(self, service, mock_po_store, sample_invoice):
        """PO number on invoice doesn't exist, falls through to fuzzy."""
        mock_po_store.get_po_by_number.return_value = None
        mock_po_store.get_pos_by_vendor.return_value = [
            PurchaseOrderSchema(
                po_number="PO-FUZZY", vendor_name="Acme Corp",
                order_date="2024-01-10", total_amount=5000.00,
            )
        ]

        result = service.auto_match_po(sample_invoice)
        assert result.po_number == "PO-FUZZY"
        assert result.match_method == "fuzzy"

    def test_fuzzy_match_single_candidate(self, service, mock_po_store, sample_invoice_no_po):
        """Single vendor PO with matching amount -> fuzzy match."""
        mock_po_store.get_pos_by_vendor.return_value = [
            PurchaseOrderSchema(
                po_number="PO-MATCH", vendor_name="Acme Corp",
                order_date="2024-01-10", total_amount=5050.00,  # Within 5% tolerance
            )
        ]

        result = service.auto_match_po(sample_invoice_no_po)
        assert result.po_number == "PO-MATCH"
        assert result.match_method == "fuzzy"
        assert result.confidence >= 0.5

    def test_fuzzy_match_amount_too_different(self, service, mock_po_store, sample_invoice_no_po):
        """PO amount differs by more than 5% -> no match."""
        mock_po_store.get_pos_by_vendor.return_value = [
            PurchaseOrderSchema(
                po_number="PO-FAR", vendor_name="Acme Corp",
                order_date="2024-01-10", total_amount=7000.00,  # 40% diff
            )
        ]

        result = service.auto_match_po(sample_invoice_no_po)
        assert result.po_number is None
        assert result.candidates == 1

    def test_fuzzy_match_multiple_candidates(self, service, mock_po_store, sample_invoice_no_po):
        """Multiple POs match the amount -> don't guess, return None."""
        mock_po_store.get_pos_by_vendor.return_value = [
            PurchaseOrderSchema(
                po_number="PO-A", vendor_name="Acme Corp",
                order_date="2024-01-10", total_amount=5000.00,
            ),
            PurchaseOrderSchema(
                po_number="PO-B", vendor_name="Acme Corp",
                order_date="2024-02-10", total_amount=5000.00,
            ),
        ]

        result = service.auto_match_po(sample_invoice_no_po)
        assert result.po_number is None
        assert result.candidates == 2

    def test_fuzzy_match_no_vendor_pos(self, service, mock_po_store, sample_invoice_no_po):
        """No POs for vendor -> no match."""
        mock_po_store.get_pos_by_vendor.return_value = []

        result = service.auto_match_po(sample_invoice_no_po)
        assert result.po_number is None
        assert result.candidates == 0

    def test_fuzzy_match_zero_amount(self, service, mock_po_store):
        """Both invoice and PO have zero amount -> match."""
        invoice = InvoiceSchema(
            vendor_name="Acme Corp", invoice_number="INV-ZERO",
            invoice_date="2024-01-15", total_amount=0.0,
        )
        mock_po_store.get_pos_by_vendor.return_value = [
            PurchaseOrderSchema(
                po_number="PO-ZERO", vendor_name="Acme Corp",
                order_date="2024-01-10", total_amount=0.0,
            )
        ]

        result = service.auto_match_po(invoice)
        assert result.po_number == "PO-ZERO"
        assert result.confidence == 0.5


# ==================== REPORT GENERATION ====================


class TestReportGeneration:
    """Tests for report generation delegation."""

    def test_generate_report(self, service, mock_matcher, mock_match_result):
        report = service.generate_report(mock_match_result)

        assert report == "Two-way report text"
        mock_matcher.generate_report.assert_called_once_with(mock_match_result)

    def test_generate_three_way_report(self, service, mock_matcher, mock_three_way_result):
        report = service.generate_three_way_report(mock_three_way_result)

        assert report == "Three-way report text"
        mock_matcher.generate_three_way_report.assert_called_once_with(mock_three_way_result)
