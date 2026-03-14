"""
Match Service for DocuMatch Architect.

Orchestrates invoice validation workflows:
  - Two-way matching:   Invoice ↔ Contract
  - Three-way matching: Invoice ↔ PO ↔ Contract
  - Auto PO matching:   Resolves PO from invoice data before validation

Auto PO Resolution:
    ┌──────────────────┐
    │ invoice.po_number │
    │ provided?         │
    └───────┬──────────┘
        YES │         NO
            ▼          ▼
    ┌──────────┐  ┌──────────────────────┐
    │ Exact     │  │ Fuzzy match:          │
    │ lookup    │  │ vendor + total_amount │
    │ by number │  │ via get_pos_by_vendor │
    └────┬─────┘  └───────┬──────────────┘
         │                │
         ▼                ▼
    ┌──────────┐  ┌──────────────────────┐
    │ Found?   │  │ Exactly 1 match       │
    │ Use it   │  │ within 5% tolerance?  │
    └──────────┘  │ Use it. Otherwise     │
                  │ skip (two-way only).  │
                  └──────────────────────┘
"""

import logging
from dataclasses import dataclass
from typing import Optional

from ..matcher import Matcher
from ..models import (
    InvoiceSchema,
    MatchResult,
    PurchaseOrderSchema,
    ThreeWayMatchResult,
)
from ..po_store import POStore

logger = logging.getLogger(__name__)

# Tolerance for fuzzy amount matching (5%)
AMOUNT_MATCH_TOLERANCE = 0.05


@dataclass
class POMatchResult:
    """Result of auto PO matching."""

    po_number: Optional[str] = None
    match_method: Optional[str] = None  # "exact", "fuzzy", None
    confidence: float = 0.0
    candidates: int = 0


class MatchService:
    """
    Orchestrates invoice validation and matching.

    Supports auto PO resolution: when no po_number is explicitly provided,
    attempts to find the matching PO automatically from the invoice data.

    Usage:
        service = MatchService(matcher, po_store)
        result = service.validate_three_way(invoice)  # auto-resolves PO
        result = service.validate_three_way(invoice, po_number="PO-001")  # explicit
    """

    def __init__(self, matcher: Matcher, po_store: Optional[POStore] = None):
        self.matcher = matcher
        self.po_store = po_store

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

        If po_number is not provided, attempts auto PO matching:
        1. Exact lookup by invoice.po_number
        2. Fuzzy match by vendor_name + total_amount

        Args:
            invoice: Extracted invoice data
            po_number: PO number to match (auto-resolved if not provided)

        Returns:
            ThreeWayMatchResult with validation status and match details
        """
        # Auto-resolve PO if not explicitly provided
        if not po_number:
            po_match = self.auto_match_po(invoice)
            po_number = po_match.po_number
            if po_number:
                logger.info(
                    f"Auto-matched PO: {po_number} "
                    f"(method={po_match.match_method}, "
                    f"confidence={po_match.confidence:.0%})"
                )

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

    def auto_match_po(self, invoice: InvoiceSchema) -> POMatchResult:
        """
        Attempt to automatically find the matching PO for an invoice.

        Strategy:
        1. If invoice has po_number, do exact lookup
        2. If no po_number, fuzzy match on vendor + total_amount
        3. Fuzzy match only returns a result if exactly 1 PO matches

        Args:
            invoice: Extracted invoice data

        Returns:
            POMatchResult with matched po_number (or None)
        """
        if not self.po_store:
            return POMatchResult()

        # Strategy 1: Exact lookup by PO number from invoice
        if invoice.po_number:
            po = self.po_store.get_po_by_number(invoice.po_number)
            if po:
                return POMatchResult(
                    po_number=po.po_number,
                    match_method="exact",
                    confidence=1.0,
                    candidates=1,
                )
            logger.warning(
                f"Invoice references PO '{invoice.po_number}' but not found in store"
            )

        # Strategy 2: Fuzzy match on vendor_name + total_amount
        vendor_pos = self.po_store.get_pos_by_vendor(invoice.vendor_name)
        if not vendor_pos:
            return POMatchResult(candidates=0)

        # Filter by amount tolerance
        matches = []
        for po in vendor_pos:
            if invoice.total_amount == 0 and po.total_amount == 0:
                matches.append(po)
            elif invoice.total_amount > 0:
                diff = abs(invoice.total_amount - po.total_amount) / invoice.total_amount
                if diff <= AMOUNT_MATCH_TOLERANCE:
                    matches.append(po)

        if len(matches) == 1:
            po = matches[0]
            # Calculate confidence based on amount closeness
            if invoice.total_amount > 0:
                diff = abs(invoice.total_amount - po.total_amount) / invoice.total_amount
                confidence = 1.0 - (diff / AMOUNT_MATCH_TOLERANCE)
            else:
                confidence = 0.5
            return POMatchResult(
                po_number=po.po_number,
                match_method="fuzzy",
                confidence=max(0.5, confidence),
                candidates=len(vendor_pos),
            )

        # 0 or 2+ matches -- don't guess
        return POMatchResult(candidates=len(vendor_pos))

    def generate_report(self, result: MatchResult) -> str:
        """Generate a human-readable validation report."""
        return self.matcher.generate_report(result)

    def generate_three_way_report(self, result: ThreeWayMatchResult) -> str:
        """Generate a human-readable three-way validation report."""
        return self.matcher.generate_three_way_report(result)
