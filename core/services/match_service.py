"""
Match Service for DocuMatch Architect.

Orchestrates invoice validation workflows:
  - Two-way matching:   Invoice ↔ Contract
  - Three-way matching: Invoice ↔ PO ↔ Contract

Batch processing will be added in Phase 2.4.
"""

import logging
from typing import Optional

from ..matcher import Matcher
from ..models import (
    InvoiceSchema,
    MatchResult,
    ThreeWayMatchResult,
)

logger = logging.getLogger(__name__)


class MatchService:
    """
    Orchestrates invoice validation and matching.

    Accepts a Matcher instance via constructor injection for testability.

    Usage:
        service = MatchService(matcher)
        result = service.validate(invoice)
        result = service.validate_three_way(invoice, po_number="PO-001")
        report = service.generate_report(result)
    """

    def __init__(self, matcher: Matcher):
        self.matcher = matcher

    def validate(
        self,
        invoice: InvoiceSchema,
        vendor_name: Optional[str] = None,
    ) -> MatchResult:
        """
        Two-way validation: Invoice ↔ Contract.

        Args:
            invoice: Extracted invoice data
            vendor_name: Override vendor (uses invoice vendor if not provided)

        Returns:
            MatchResult with validation status and issues
        """
        vendor = vendor_name or invoice.vendor_name
        logger.info(
            f"Validating invoice {invoice.invoice_number} "
            f"against contract for '{vendor}'"
        )

        result = self.matcher.validate_invoice(invoice, vendor_name)

        logger.info(
            f"Validation complete: invoice={invoice.invoice_number}, "
            f"status={result.status}, issues={len(result.issues)}"
        )
        return result

    def validate_three_way(
        self,
        invoice: InvoiceSchema,
        po_number: Optional[str] = None,
    ) -> ThreeWayMatchResult:
        """
        Three-way validation: Invoice ↔ PO ↔ Contract.

        Args:
            invoice: Extracted invoice data
            po_number: PO number to match (uses invoice.po_number if not provided)

        Returns:
            ThreeWayMatchResult with validation status and match details
        """
        po_num = po_number or invoice.po_number
        logger.info(
            f"Three-way validation: invoice={invoice.invoice_number}, "
            f"po={po_num or 'none'}, vendor={invoice.vendor_name}"
        )

        result = self.matcher.validate_invoice_three_way(invoice, po_number)

        logger.info(
            f"Three-way validation complete: invoice={invoice.invoice_number}, "
            f"status={result.status}, "
            f"matches={result.matches_passed}/{result.total_matches}"
        )
        return result

    def generate_report(self, result: MatchResult) -> str:
        """Generate a human-readable validation report."""
        return self.matcher.generate_report(result)

    def generate_three_way_report(self, result: ThreeWayMatchResult) -> str:
        """Generate a human-readable three-way validation report."""
        return self.matcher.generate_three_way_report(result)
