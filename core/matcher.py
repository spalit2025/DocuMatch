"""
Matcher Engine for DocuMatch Architect.

Compares extracted invoice data against contract terms
and generates validation reports.
"""

import logging
import re
from datetime import datetime
from typing import List, Optional, Tuple

import requests


def normalize_vendor_name(name: str) -> str:
    """
    Normalize vendor name for matching.

    Handles common variations:
    - Trailing punctuation (Inc. vs Inc)
    - Extra whitespace
    - Case differences
    """
    if not name:
        return ""
    # Strip whitespace and trailing punctuation
    normalized = name.strip().rstrip('.,;:')
    # Normalize internal whitespace
    normalized = ' '.join(normalized.split())
    return normalized

from .models import (
    InvoiceSchema,
    MatchResult,
    RetrievedClause,
    ValidationIssue,
    PurchaseOrderSchema,
    MatchDetail,
    ThreeWayMatchResult,
)
from .vector_store import VectorStore
from .po_store import POStore

# Configure logging
logger = logging.getLogger(__name__)


# LLM prompt for rate comparison
RATE_COMPARISON_PROMPT = """You are a contract compliance validator. Compare the invoice line items against the contract rate card.

CONTRACT CLAUSES:
{contract_clauses}

INVOICE LINE ITEMS:
{invoice_items}

TASK: Identify any rate violations where invoice rates exceed contract rates.

Output a JSON array of violations. Each violation should have:
- "description": what item/service has a rate issue
- "invoice_rate": the rate charged on the invoice
- "contract_rate": the rate specified in the contract
- "difference": how much higher the invoice rate is

If no violations found, output an empty array: []

JSON OUTPUT:"""


class Matcher:
    """
    Invoice-Contract matching engine.

    Validates invoices against indexed contract terms using
    both rule-based checks and LLM-powered analysis.

    Usage:
        matcher = Matcher(vector_store)
        result = matcher.validate_invoice(invoice, "VendorA")
        print(result.status)  # "PASS" or "FAIL"
    """

    def __init__(
        self,
        vector_store: VectorStore,
        po_store: Optional[POStore] = None,
        ollama_host: str = "http://localhost:11434",
        model: str = "phi3.5",
        match_tolerance: float = 0.01,  # 1% tolerance for amount matching
    ):
        """
        Initialize the matcher.

        Args:
            vector_store: VectorStore instance for clause retrieval
            po_store: POStore instance for PO retrieval (optional, for three-way matching)
            ollama_host: Ollama API endpoint
            model: LLM model for comparison
            match_tolerance: Tolerance for amount matching (default 1%)
        """
        self.vector_store = vector_store
        self.po_store = po_store
        self.ollama_host = ollama_host.rstrip("/")
        self.model = model
        self.match_tolerance = match_tolerance

    def validate_invoice(
        self,
        invoice: InvoiceSchema,
        vendor_name: Optional[str] = None,
    ) -> MatchResult:
        """
        Validate an invoice against contract terms.

        Args:
            invoice: The extracted invoice data
            vendor_name: Vendor to match against (uses invoice vendor if not provided)

        Returns:
            MatchResult with validation status and issues
        """
        vendor = vendor_name or invoice.vendor_name
        issues: List[ValidationIssue] = []
        matched_clauses: List[RetrievedClause] = []

        # Step 1: Retrieve relevant contract clauses
        rate_clauses = self.vector_store.retrieve_clauses(
            vendor_name=vendor,
            query="hourly rate price cost rate card pricing",
            top_k=5
        )
        term_clauses = self.vector_store.retrieve_clauses(
            vendor_name=vendor,
            query="payment terms due date net days",
            top_k=3
        )
        date_clauses = self.vector_store.retrieve_clauses(
            vendor_name=vendor,
            query="contract period effective date termination expiration",
            top_k=3
        )

        matched_clauses.extend(rate_clauses)
        matched_clauses.extend(term_clauses)
        matched_clauses.extend(date_clauses)

        # Remove duplicates by chunk_id
        seen_ids = set()
        unique_clauses = []
        for clause in matched_clauses:
            if clause.chunk_id not in seen_ids:
                seen_ids.add(clause.chunk_id)
                unique_clauses.append(clause)
        matched_clauses = unique_clauses

        # Check if we have any contract data
        if not matched_clauses:
            issues.append(ValidationIssue(
                rule="contract_exists",
                severity="critical",
                message=f"No contract found for vendor '{vendor}'",
                invoice_value=vendor,
                contract_value=None
            ))
            return self._build_result(invoice, issues, matched_clauses)

        # Step 2: Run validation checks
        issues.extend(self._validate_line_item_totals(invoice))
        issues.extend(self._validate_rates(invoice, rate_clauses))
        issues.extend(self._validate_payment_terms(invoice, term_clauses))
        issues.extend(self._validate_dates(invoice, date_clauses))

        return self._build_result(invoice, issues, matched_clauses)

    def _validate_line_item_totals(self, invoice: InvoiceSchema) -> List[ValidationIssue]:
        """Validate that line item totals match quantity * unit_price."""
        issues = []

        for i, item in enumerate(invoice.line_items):
            expected = item.quantity * item.unit_price
            if abs(item.total - expected) > 0.01:  # Allow 1 cent tolerance
                issues.append(ValidationIssue(
                    rule="line_item_math",
                    severity="error",
                    message=f"Line item '{item.description}': total ${item.total:.2f} doesn't match qty({item.quantity}) x price(${item.unit_price:.2f}) = ${expected:.2f}",
                    invoice_value=item.total,
                    contract_value=expected
                ))

        # Validate sum of line items vs total
        if invoice.line_items:
            line_sum = sum(item.total for item in invoice.line_items)
            if abs(line_sum - invoice.total_amount) > 0.01:
                issues.append(ValidationIssue(
                    rule="total_sum",
                    severity="warning",
                    message=f"Line items sum (${line_sum:.2f}) differs from invoice total (${invoice.total_amount:.2f})",
                    invoice_value=invoice.total_amount,
                    contract_value=line_sum
                ))

        return issues

    def _validate_rates(
        self,
        invoice: InvoiceSchema,
        clauses: List[RetrievedClause]
    ) -> List[ValidationIssue]:
        """Validate invoice rates against contract rate card."""
        issues = []

        if not clauses or not invoice.line_items:
            return issues

        # Extract rates from contract clauses
        contract_rates = self._extract_rates_from_clauses(clauses)

        if not contract_rates:
            issues.append(ValidationIssue(
                rule="rate_card_found",
                severity="info",
                message="Could not find specific rates in contract clauses",
                invoice_value=None,
                contract_value=None
            ))
            return issues

        # Compare each line item against contract rates
        for item in invoice.line_items:
            item_lower = item.description.lower()

            for role, contract_rate in contract_rates.items():
                role_lower = role.lower()

                # Check if this line item matches a contract role
                if self._fuzzy_match(item_lower, role_lower):
                    if item.unit_price > contract_rate * 1.01:  # 1% tolerance
                        issues.append(ValidationIssue(
                            rule="rate_compliance",
                            severity="critical",
                            message=f"Rate for '{item.description}' (${item.unit_price:.2f}/hr) exceeds contract rate for '{role}' (${contract_rate:.2f}/hr)",
                            invoice_value=item.unit_price,
                            contract_value=contract_rate
                        ))
                    break

        return issues

    def _validate_payment_terms(
        self,
        invoice: InvoiceSchema,
        clauses: List[RetrievedClause]
    ) -> List[ValidationIssue]:
        """Validate payment terms alignment."""
        issues = []

        if not invoice.payment_terms or not clauses:
            return issues

        # Extract payment terms from contract
        contract_terms = self._extract_payment_terms(clauses)

        if contract_terms and invoice.payment_terms:
            invoice_days = self._extract_net_days(invoice.payment_terms)
            contract_days = self._extract_net_days(contract_terms)

            if invoice_days and contract_days:
                if invoice_days < contract_days:
                    issues.append(ValidationIssue(
                        rule="payment_terms",
                        severity="warning",
                        message=f"Invoice payment terms ({invoice.payment_terms}) are shorter than contract terms ({contract_terms})",
                        invoice_value=invoice.payment_terms,
                        contract_value=contract_terms
                    ))

        return issues

    def _validate_dates(
        self,
        invoice: InvoiceSchema,
        clauses: List[RetrievedClause]
    ) -> List[ValidationIssue]:
        """Validate invoice date falls within contract period."""
        issues = []

        # Try to parse invoice date
        invoice_date = self._parse_date(invoice.invoice_date)
        if not invoice_date:
            issues.append(ValidationIssue(
                rule="date_format",
                severity="warning",
                message=f"Could not parse invoice date: {invoice.invoice_date}",
                invoice_value=invoice.invoice_date,
                contract_value=None
            ))
            return issues

        # Extract contract dates from clauses
        contract_dates = self._extract_contract_dates(clauses)

        if contract_dates:
            start_date, end_date = contract_dates

            if start_date and invoice_date < start_date:
                issues.append(ValidationIssue(
                    rule="contract_period",
                    severity="critical",
                    message=f"Invoice date ({invoice.invoice_date}) is before contract start ({start_date.strftime('%Y-%m-%d')})",
                    invoice_value=invoice.invoice_date,
                    contract_value=start_date.strftime('%Y-%m-%d')
                ))

            if end_date and invoice_date > end_date:
                issues.append(ValidationIssue(
                    rule="contract_period",
                    severity="critical",
                    message=f"Invoice date ({invoice.invoice_date}) is after contract end ({end_date.strftime('%Y-%m-%d')})",
                    invoice_value=invoice.invoice_date,
                    contract_value=end_date.strftime('%Y-%m-%d')
                ))

        return issues

    def _extract_rates_from_clauses(self, clauses: List[RetrievedClause]) -> dict:
        """Extract rate information from contract clauses."""
        rates = {}

        for clause in clauses:
            text = clause.text

            # Pattern: "Role: $XXX/hour" or "Role - $XXX per hour"
            patterns = [
                r'([A-Za-z\s]+):\s*\$?([\d,]+(?:\.\d{2})?)\s*(?:per\s+hour|/\s*h(?:ou)?r|/hr)',
                r'([A-Za-z\s]+)\s*[-–]\s*\$?([\d,]+(?:\.\d{2})?)\s*(?:per\s+hour|/\s*h(?:ou)?r|/hr)',
                r'([A-Za-z\s]+)\s+\$?([\d,]+(?:\.\d{2})?)\s*(?:per\s+hour|/\s*h(?:ou)?r|/hr)',
            ]

            for pattern in patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for role, rate in matches:
                    role = role.strip()
                    rate = float(rate.replace(',', ''))
                    if role and rate > 0:
                        rates[role] = rate

        return rates

    def _extract_payment_terms(self, clauses: List[RetrievedClause]) -> Optional[str]:
        """Extract payment terms from contract clauses."""
        for clause in clauses:
            text = clause.text.lower()

            # Look for "Net XX" pattern
            match = re.search(r'net\s*(\d+)', text)
            if match:
                return f"Net {match.group(1)}"

            # Look for "within XX days"
            match = re.search(r'within\s*(\d+)\s*days', text)
            if match:
                return f"Net {match.group(1)}"

        return None

    def _extract_net_days(self, terms: str) -> Optional[int]:
        """Extract number of days from payment terms."""
        match = re.search(r'(\d+)', terms)
        if match:
            return int(match.group(1))
        return None

    def _extract_contract_dates(
        self,
        clauses: List[RetrievedClause]
    ) -> Optional[Tuple[Optional[datetime], Optional[datetime]]]:
        """Extract contract start and end dates from clauses."""
        start_date = None
        end_date = None

        for clause in clauses:
            text = clause.text

            # Look for date patterns
            date_patterns = [
                r'effective\s+(?:date|from)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'start(?:s|ing)?[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'commenc(?:es|ing)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            ]

            end_patterns = [
                r'terminat(?:es|ion)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'expir(?:es|ation)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
                r'end(?:s|ing)?[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            ]

            for pattern in date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match and not start_date:
                    start_date = self._parse_date(match.group(1))

            for pattern in end_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match and not end_date:
                    end_date = self._parse_date(match.group(1))

        if start_date or end_date:
            return (start_date, end_date)
        return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse a date string into datetime object."""
        if not date_str:
            return None

        formats = [
            '%Y-%m-%d',
            '%m/%d/%Y',
            '%m-%d-%Y',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%m/%d/%y',
            '%d/%m/%y',
            '%B %d, %Y',
            '%b %d, %Y',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def _fuzzy_match(self, text1: str, text2: str) -> bool:
        """
        Check if two strings represent the same role/item.

        Uses strict matching to avoid false positives like
        "Data Scientist" matching "Data Analyst".
        """
        # Normalize strings
        text1 = text1.lower().strip()
        text2 = text2.lower().strip()

        # Exact match
        if text1 == text2:
            return True

        # One contains the other (for partial matches like "Senior Consultant" vs "Senior Consultant Services")
        if text1 in text2 or text2 in text1:
            return True

        # Word-based matching with strict criteria
        words1 = set(text1.split())
        words2 = set(text2.split())

        # Remove common stopwords and modifiers
        stopwords = {'the', 'a', 'an', 'and', 'or', 'for', 'of', 'to', '-', 'services', 'service', 'senior', 'junior', 'lead'}
        core_words1 = words1 - stopwords
        core_words2 = words2 - stopwords

        if not core_words1 or not core_words2:
            # If no core words remain, fall back to original words
            core_words1 = words1
            core_words2 = words2

        # Strict matching: ALL core words must match for short phrases
        # This prevents "Data Scientist" from matching "Data Analyst"
        if len(core_words1) <= 2 and len(core_words2) <= 2:
            # For short phrases, require exact core word match
            return core_words1 == core_words2

        # For longer phrases, require significant overlap (at least 2/3)
        common = core_words1 & core_words2
        smaller_set = min(len(core_words1), len(core_words2))
        return len(common) >= max(2, smaller_set * 0.67)

    def _build_result(
        self,
        invoice: InvoiceSchema,
        issues: List[ValidationIssue],
        clauses: List[RetrievedClause]
    ) -> MatchResult:
        """Build the final MatchResult."""
        # Determine status based on issues
        has_critical = any(i.severity == "critical" for i in issues)
        has_error = any(i.severity == "error" for i in issues)

        if has_critical:
            status = "FAIL"
        elif has_error:
            status = "FAIL"
        elif issues:
            status = "REVIEW"
        else:
            status = "PASS"

        # Calculate confidence score
        if not clauses:
            confidence = 0.0
        else:
            # Average similarity of matched clauses
            avg_similarity = sum(c.similarity_score for c in clauses) / len(clauses)
            # Reduce confidence based on issues
            issue_penalty = len([i for i in issues if i.severity in ("critical", "error")]) * 0.1
            confidence = max(0, min(1, avg_similarity - issue_penalty))

        return MatchResult(
            status=status,
            vendor_name=invoice.vendor_name,
            invoice_number=invoice.invoice_number,
            issues=issues,
            matched_clauses=clauses,
            confidence_score=confidence,
        )

    def generate_report(self, result: MatchResult) -> str:
        """Generate a human-readable validation report."""
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append("INVOICE VALIDATION REPORT")
        lines.append("=" * 60)
        lines.append("")

        # Summary
        status_emoji = {"PASS": "✅", "FAIL": "❌", "REVIEW": "⚠️"}.get(result.status, "❓")
        lines.append(f"Status: {status_emoji} {result.status}")
        lines.append(f"Vendor: {result.vendor_name}")
        lines.append(f"Invoice: {result.invoice_number}")
        lines.append(f"Confidence: {result.confidence_score:.0%}")
        lines.append(f"Timestamp: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Issue Summary
        summary = result.issue_summary
        lines.append("-" * 40)
        lines.append("ISSUE SUMMARY")
        lines.append("-" * 40)
        lines.append(f"  Critical: {summary['critical']}")
        lines.append(f"  Errors:   {summary['error']}")
        lines.append(f"  Warnings: {summary['warning']}")
        lines.append(f"  Info:     {summary['info']}")
        lines.append("")

        # Detailed Issues
        if result.issues:
            lines.append("-" * 40)
            lines.append("DETAILED ISSUES")
            lines.append("-" * 40)

            for issue in result.issues:
                severity_icon = {
                    "critical": "🔴",
                    "error": "🟠",
                    "warning": "🟡",
                    "info": "🔵"
                }.get(issue.severity, "⚪")

                lines.append(f"\n{severity_icon} [{issue.severity.upper()}] {issue.rule}")
                lines.append(f"   {issue.message}")
                if issue.contract_value is not None:
                    lines.append(f"   Invoice: {issue.invoice_value} | Contract: {issue.contract_value}")

        # Matched Clauses
        if result.matched_clauses:
            lines.append("")
            lines.append("-" * 40)
            lines.append("MATCHED CONTRACT CLAUSES")
            lines.append("-" * 40)

            for i, clause in enumerate(result.matched_clauses[:5]):  # Show top 5
                lines.append(f"\n[{i+1}] Score: {clause.similarity_score:.2f}")
                preview = clause.text[:200] + "..." if len(clause.text) > 200 else clause.text
                lines.append(f"    {preview}")

        lines.append("")
        lines.append("=" * 60)
        lines.append("END OF REPORT")
        lines.append("=" * 60)

        return "\n".join(lines)

    # ==================== THREE-WAY MATCHING ====================

    def validate_invoice_three_way(
        self,
        invoice: InvoiceSchema,
        po_number: Optional[str] = None,
    ) -> ThreeWayMatchResult:
        """
        Perform three-way validation: Invoice ↔ PO ↔ Contract.

        Args:
            invoice: The extracted invoice data
            po_number: PO number to match (uses invoice.po_number if not provided)

        Returns:
            ThreeWayMatchResult with validation status and match details

        Logic:
            - If ≥2 matches pass → PASS
            - If <2 matches pass → FAIL → Manual Review
        """
        # Use po_number from invoice if not provided
        po_number = po_number or invoice.po_number
        vendor = invoice.vendor_name

        # Retrieve contract clauses
        all_clauses = self._get_all_contract_clauses(vendor)

        # Get PO if available
        po = None
        if self.po_store and po_number:
            po = self.po_store.get_po_by_number(po_number)
            if not po:
                logger.warning(f"PO {po_number} not found in store")

        # Perform matches
        match1 = self._match_invoice_po(invoice, po) if po else None
        match2 = self._match_invoice_contract(invoice, all_clauses)
        match3 = self._match_po_contract(po, all_clauses) if po else None

        # Count passed matches
        matches = [m for m in [match1, match2, match3] if m is not None]
        passed_count = sum(1 for m in matches if m.passed)
        total_count = len(matches)

        # Determine status: ≥2 passes = PASS, <2 = FAIL
        if total_count == 0:
            status = "FAIL"
        elif passed_count >= 2:
            status = "PASS"
        elif passed_count >= 1 and total_count <= 2:
            # With only 2 matches available (no PO), 1 pass means 50%
            status = "REVIEW"
        else:
            status = "FAIL"

        # Aggregate all issues
        all_issues = []
        if match1:
            all_issues.extend(match1.issues)
        if match2:
            all_issues.extend(match2.issues)
        if match3:
            all_issues.extend(match3.issues)

        # Calculate overall score
        if matches:
            overall_score = sum(m.score for m in matches) / len(matches)
        else:
            overall_score = 0.0

        return ThreeWayMatchResult(
            status=status,
            vendor_name=vendor,
            invoice_number=invoice.invoice_number,
            po_number=po_number,
            invoice_po_match=match1,
            invoice_contract_match=match2,
            po_contract_match=match3,
            matches_passed=passed_count,
            total_matches=total_count,
            overall_score=overall_score,
            all_issues=all_issues,
            matched_clauses=all_clauses,
        )

    def _get_all_contract_clauses(self, vendor: str) -> List[RetrievedClause]:
        """Retrieve all relevant contract clauses for a vendor."""
        rate_clauses = self.vector_store.retrieve_clauses(
            vendor_name=vendor,
            query="hourly rate price cost rate card pricing",
            top_k=5
        )
        term_clauses = self.vector_store.retrieve_clauses(
            vendor_name=vendor,
            query="payment terms due date net days",
            top_k=3
        )
        date_clauses = self.vector_store.retrieve_clauses(
            vendor_name=vendor,
            query="contract period effective date termination expiration",
            top_k=3
        )

        # Combine and deduplicate
        all_clauses = rate_clauses + term_clauses + date_clauses
        seen_ids = set()
        unique_clauses = []
        for clause in all_clauses:
            if clause.chunk_id not in seen_ids:
                seen_ids.add(clause.chunk_id)
                unique_clauses.append(clause)

        return unique_clauses

    def _match_invoice_po(
        self,
        invoice: InvoiceSchema,
        po: PurchaseOrderSchema,
    ) -> MatchDetail:
        """
        Match 1: Validate Invoice against PO.

        Checks:
        - PO number reference matches
        - Line item quantities match
        - Line item unit prices match
        - Total amounts match
        """
        issues = []
        score = 1.0

        # Check PO number
        if invoice.po_number and invoice.po_number != po.po_number:
            issues.append(ValidationIssue(
                rule="po_reference",
                severity="critical",
                message=f"Invoice references PO '{invoice.po_number}' but matching against PO '{po.po_number}'",
                invoice_value=invoice.po_number,
                contract_value=po.po_number,
                match_type="invoice_po"
            ))
            score -= 0.3

        # Check total amounts
        total_diff = abs(invoice.total_amount - po.total_amount)
        tolerance = max(invoice.total_amount, po.total_amount) * self.match_tolerance
        if total_diff > tolerance:
            issues.append(ValidationIssue(
                rule="total_match",
                severity="error",
                message=f"Invoice total (${invoice.total_amount:.2f}) differs from PO total (${po.total_amount:.2f})",
                invoice_value=invoice.total_amount,
                contract_value=po.total_amount,
                match_type="invoice_po"
            ))
            score -= 0.2

        # Check line items
        line_issues = self._compare_line_items(invoice.line_items, po.line_items, "invoice_po")
        issues.extend(line_issues)
        score -= len(line_issues) * 0.1

        # Determine if match passed
        # Invoice↔PO match requires NO critical issues AND NO error issues with significant mismatches
        has_critical = any(i.severity == "critical" for i in issues)
        has_total_mismatch = any(i.rule == "total_match" for i in issues)
        has_qty_or_price_errors = any(i.rule in ("line_qty_match", "line_price_match") for i in issues)

        # Stricter: fail if there's a total mismatch or both qty and price errors
        significant_errors = has_total_mismatch and has_qty_or_price_errors
        passed = not has_critical and not significant_errors and score >= 0.6

        return MatchDetail(
            match_type="invoice_po",
            passed=passed,
            score=max(0, min(1, score)),
            issues=issues,
            details={
                "invoice_total": invoice.total_amount,
                "po_total": po.total_amount,
                "line_items_compared": len(invoice.line_items),
            }
        )

    def _match_invoice_contract(
        self,
        invoice: InvoiceSchema,
        clauses: List[RetrievedClause],
    ) -> MatchDetail:
        """
        Match 2: Validate Invoice against Contract.

        Checks:
        - Rates within contract limits
        - Invoice date within contract period
        - Payment terms align
        - Contract exists for vendor
        """
        issues = []
        score = 1.0

        # Check if contract exists
        if not clauses:
            issues.append(ValidationIssue(
                rule="contract_exists",
                severity="critical",
                message=f"No contract found for vendor '{invoice.vendor_name}'",
                invoice_value=invoice.vendor_name,
                contract_value=None,
                match_type="invoice_contract"
            ))
            return MatchDetail(
                match_type="invoice_contract",
                passed=False,
                score=0.0,
                issues=issues,
                details={"contract_found": False}
            )

        # Rate validation
        rate_clauses = [c for c in clauses if any(
            word in c.text.lower() for word in ['rate', 'price', 'cost', 'hourly']
        )]
        rate_issues = self._validate_rates(invoice, rate_clauses)
        for issue in rate_issues:
            issue.match_type = "invoice_contract"
        issues.extend(rate_issues)
        score -= len([i for i in rate_issues if i.severity == "critical"]) * 0.3

        # Date validation
        date_clauses = [c for c in clauses if any(
            word in c.text.lower() for word in ['effective', 'termination', 'period', 'expir']
        )]
        date_issues = self._validate_dates(invoice, date_clauses)
        for issue in date_issues:
            issue.match_type = "invoice_contract"
        issues.extend(date_issues)
        score -= len([i for i in date_issues if i.severity == "critical"]) * 0.3

        # Payment terms validation
        term_clauses = [c for c in clauses if any(
            word in c.text.lower() for word in ['payment', 'net', 'days', 'due']
        )]
        term_issues = self._validate_payment_terms(invoice, term_clauses)
        for issue in term_issues:
            issue.match_type = "invoice_contract"
        issues.extend(term_issues)
        score -= len(term_issues) * 0.1

        # Determine if match passed
        has_critical = any(i.severity == "critical" for i in issues)
        passed = not has_critical and score >= 0.5

        return MatchDetail(
            match_type="invoice_contract",
            passed=passed,
            score=max(0, min(1, score)),
            issues=issues,
            details={
                "contract_found": True,
                "clauses_matched": len(clauses),
            }
        )

    def _match_po_contract(
        self,
        po: PurchaseOrderSchema,
        clauses: List[RetrievedClause],
    ) -> MatchDetail:
        """
        Match 3: Validate PO against Contract.

        Checks:
        - PO rates within contract limits
        - PO date within contract period
        - PO amounts within contract limits
        """
        issues = []
        score = 1.0

        # Check if contract exists
        if not clauses:
            issues.append(ValidationIssue(
                rule="contract_exists",
                severity="critical",
                message=f"No contract found for vendor '{po.vendor_name}'",
                invoice_value=po.vendor_name,
                contract_value=None,
                match_type="po_contract"
            ))
            return MatchDetail(
                match_type="po_contract",
                passed=False,
                score=0.0,
                issues=issues,
                details={"contract_found": False}
            )

        # Rate validation (using PO line items)
        rate_clauses = [c for c in clauses if any(
            word in c.text.lower() for word in ['rate', 'price', 'cost', 'hourly']
        )]
        contract_rates = self._extract_rates_from_clauses(rate_clauses)

        if contract_rates and po.line_items:
            for item in po.line_items:
                item_lower = item.description.lower()
                for role, contract_rate in contract_rates.items():
                    role_lower = role.lower()
                    if self._fuzzy_match(item_lower, role_lower):
                        if item.unit_price > contract_rate * (1 + self.match_tolerance):
                            issues.append(ValidationIssue(
                                rule="po_rate_compliance",
                                severity="critical",
                                message=f"PO rate for '{item.description}' (${item.unit_price:.2f}) exceeds contract rate for '{role}' (${contract_rate:.2f})",
                                invoice_value=item.unit_price,
                                contract_value=contract_rate,
                                match_type="po_contract"
                            ))
                            score -= 0.3
                        break

        # PO date validation
        po_date = self._parse_date(po.order_date)
        date_clauses = [c for c in clauses if any(
            word in c.text.lower() for word in ['effective', 'termination', 'period', 'expir']
        )]
        contract_dates = self._extract_contract_dates(date_clauses)

        if po_date and contract_dates:
            start_date, end_date = contract_dates
            if start_date and po_date < start_date:
                issues.append(ValidationIssue(
                    rule="po_date_validity",
                    severity="critical",
                    message=f"PO date ({po.order_date}) is before contract start ({start_date.strftime('%Y-%m-%d')})",
                    invoice_value=po.order_date,
                    contract_value=start_date.strftime('%Y-%m-%d'),
                    match_type="po_contract"
                ))
                score -= 0.3

            if end_date and po_date > end_date:
                issues.append(ValidationIssue(
                    rule="po_date_validity",
                    severity="critical",
                    message=f"PO date ({po.order_date}) is after contract end ({end_date.strftime('%Y-%m-%d')})",
                    invoice_value=po.order_date,
                    contract_value=end_date.strftime('%Y-%m-%d'),
                    match_type="po_contract"
                ))
                score -= 0.3

        # Determine if match passed
        has_critical = any(i.severity == "critical" for i in issues)
        passed = not has_critical and score >= 0.5

        return MatchDetail(
            match_type="po_contract",
            passed=passed,
            score=max(0, min(1, score)),
            issues=issues,
            details={
                "contract_found": True,
                "clauses_matched": len(clauses),
                "po_total": po.total_amount,
            }
        )

    def _compare_line_items(
        self,
        invoice_items: List,
        po_items: List,
        match_type: str,
    ) -> List[ValidationIssue]:
        """Compare line items between invoice and PO."""
        issues = []

        if not invoice_items or not po_items:
            return issues

        # Build lookup of PO items by description
        po_lookup = {}
        for item in po_items:
            key = item.description.lower().strip()
            po_lookup[key] = item

        # Check each invoice item
        for inv_item in invoice_items:
            inv_key = inv_item.description.lower().strip()

            # Try to find matching PO item
            matched = False
            for po_key, po_item in po_lookup.items():
                if self._fuzzy_match(inv_key, po_key):
                    matched = True

                    # Check quantity
                    if abs(inv_item.quantity - po_item.quantity) > 0.01:
                        issues.append(ValidationIssue(
                            rule="line_qty_match",
                            severity="error",
                            message=f"Quantity mismatch for '{inv_item.description}': Invoice={inv_item.quantity}, PO={po_item.quantity}",
                            invoice_value=inv_item.quantity,
                            contract_value=po_item.quantity,
                            match_type=match_type
                        ))

                    # Check unit price
                    price_diff = abs(inv_item.unit_price - po_item.unit_price)
                    tolerance = max(inv_item.unit_price, po_item.unit_price) * self.match_tolerance
                    if price_diff > tolerance:
                        issues.append(ValidationIssue(
                            rule="line_price_match",
                            severity="error",
                            message=f"Price mismatch for '{inv_item.description}': Invoice=${inv_item.unit_price:.2f}, PO=${po_item.unit_price:.2f}",
                            invoice_value=inv_item.unit_price,
                            contract_value=po_item.unit_price,
                            match_type=match_type
                        ))
                    break

            if not matched and len(po_items) > 0:
                issues.append(ValidationIssue(
                    rule="line_item_not_found",
                    severity="warning",
                    message=f"Invoice item '{inv_item.description}' not found in PO",
                    invoice_value=inv_item.description,
                    contract_value=None,
                    match_type=match_type
                ))

        return issues

    def generate_three_way_report(self, result: ThreeWayMatchResult) -> str:
        """Generate a human-readable three-way validation report."""
        lines = []

        # Header
        lines.append("=" * 70)
        lines.append("THREE-WAY INVOICE VALIDATION REPORT")
        lines.append("=" * 70)
        lines.append("")

        # Summary
        status_emoji = {"PASS": "✅", "FAIL": "❌", "REVIEW": "⚠️"}.get(result.status, "❓")
        lines.append(f"Status: {status_emoji} {result.status}")
        lines.append(f"Vendor: {result.vendor_name}")
        lines.append(f"Invoice: {result.invoice_number}")
        lines.append(f"PO: {result.po_number or 'N/A'}")
        lines.append(f"Overall Score: {result.overall_score:.0%}")
        lines.append(f"Matches Passed: {result.matches_passed}/{result.total_matches}")
        lines.append(f"Timestamp: {result.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Three-Way Match Summary
        lines.append("-" * 50)
        lines.append("THREE-WAY MATCH SUMMARY")
        lines.append("-" * 50)

        def match_status(m):
            if m is None:
                return "⚪ N/A"
            return f"{'✅' if m.passed else '❌'} {'PASS' if m.passed else 'FAIL'} ({m.score:.0%})"

        lines.append(f"  Match 1 (Invoice ↔ PO):       {match_status(result.invoice_po_match)}")
        lines.append(f"  Match 2 (Invoice ↔ Contract): {match_status(result.invoice_contract_match)}")
        lines.append(f"  Match 3 (PO ↔ Contract):      {match_status(result.po_contract_match)}")
        lines.append("")

        # Result explanation
        if result.status == "PASS":
            lines.append(f"  ✅ RESULT: {result.matches_passed} of {result.total_matches} matches passed → APPROVED")
        else:
            lines.append(f"  ❌ RESULT: Only {result.matches_passed} of {result.total_matches} matches passed → MANUAL REVIEW REQUIRED")
        lines.append("")

        # Issue Summary
        summary = result.issue_summary
        lines.append("-" * 50)
        lines.append("ISSUE SUMMARY")
        lines.append("-" * 50)
        lines.append(f"  Critical: {summary['critical']}")
        lines.append(f"  Errors:   {summary['error']}")
        lines.append(f"  Warnings: {summary['warning']}")
        lines.append(f"  Info:     {summary['info']}")
        lines.append("")

        # Detailed Issues by Match
        if result.all_issues:
            lines.append("-" * 50)
            lines.append("DETAILED ISSUES BY MATCH")
            lines.append("-" * 50)

            # Group issues by match type
            match_types = {
                "invoice_po": "Match 1 (Invoice ↔ PO)",
                "invoice_contract": "Match 2 (Invoice ↔ Contract)",
                "po_contract": "Match 3 (PO ↔ Contract)",
            }

            for mt, mt_label in match_types.items():
                mt_issues = [i for i in result.all_issues if i.match_type == mt]
                if mt_issues:
                    lines.append(f"\n{mt_label}:")
                    for issue in mt_issues:
                        severity_icon = {
                            "critical": "🔴",
                            "error": "🟠",
                            "warning": "🟡",
                            "info": "🔵"
                        }.get(issue.severity, "⚪")
                        lines.append(f"  {severity_icon} [{issue.severity.upper()}] {issue.rule}")
                        lines.append(f"     {issue.message}")

        lines.append("")
        lines.append("=" * 70)
        lines.append("END OF REPORT")
        lines.append("=" * 70)

        return "\n".join(lines)


# Convenience functions
def validate_invoice(
    invoice: InvoiceSchema,
    vector_store: VectorStore,
    vendor_name: Optional[str] = None,
) -> MatchResult:
    """
    Validate an invoice against contract terms.

    Args:
        invoice: The extracted invoice data
        vector_store: VectorStore with indexed contracts
        vendor_name: Vendor to match (uses invoice vendor if not provided)

    Returns:
        MatchResult with validation status
    """
    matcher = Matcher(vector_store)
    return matcher.validate_invoice(invoice, vendor_name)


def validate_invoice_three_way(
    invoice: InvoiceSchema,
    vector_store: VectorStore,
    po_store: Optional[POStore] = None,
    po_number: Optional[str] = None,
) -> ThreeWayMatchResult:
    """
    Perform three-way validation: Invoice ↔ PO ↔ Contract.

    Args:
        invoice: The extracted invoice data
        vector_store: VectorStore with indexed contracts
        po_store: POStore with indexed POs (optional)
        po_number: PO number to match (uses invoice.po_number if not provided)

    Returns:
        ThreeWayMatchResult with validation status
    """
    matcher = Matcher(vector_store, po_store=po_store)
    return matcher.validate_invoice_three_way(invoice, po_number)
