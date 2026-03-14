"""
Tests for MatchService.

Tests that MatchService correctly delegates to Matcher
and propagates results. Core matching logic is tested
separately in test_matcher.py and test_three_way_match.py.
"""

import pytest
from unittest.mock import MagicMock

from core.services.match_service import MatchService
from core.models import (
    InvoiceSchema,
    LineItem,
    MatchResult,
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
def service(mock_matcher):
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

    def test_without_po_number(self, service, mock_matcher, sample_invoice):
        service.validate_three_way(sample_invoice)

        mock_matcher.validate_invoice_three_way.assert_called_once_with(
            sample_invoice, None
        )

    def test_returns_matcher_result(self, service, sample_invoice, mock_three_way_result):
        result = service.validate_three_way(sample_invoice)
        assert result is mock_three_way_result


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
