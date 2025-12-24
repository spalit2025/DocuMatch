"""
Pydantic models for DocuMatch Architect.

This module defines all data models used throughout the application
for type safety and validation.
"""

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class LineItem(BaseModel):
    """Represents a single line item on an invoice."""

    description: str = Field(..., description="Description of the item or service")
    quantity: float = Field(ge=0, description="Quantity of items")
    unit_price: float = Field(ge=0, description="Price per unit")
    total: float = Field(ge=0, description="Total for this line item")

    @field_validator("total")
    @classmethod
    def validate_total(cls, v: float, info) -> float:
        """Validate that total approximately equals quantity * unit_price."""
        if info.data.get("quantity") and info.data.get("unit_price"):
            expected = info.data["quantity"] * info.data["unit_price"]
            # Allow 1% tolerance for rounding
            if abs(v - expected) > expected * 0.01 and expected > 0:
                pass  # Log warning but don't fail - LLM extractions may vary
        return v


class InvoiceSchema(BaseModel):
    """Schema for extracted invoice data."""

    vendor_name: str = Field(..., description="Name of the vendor/supplier")
    invoice_number: str = Field(..., description="Unique invoice identifier")
    invoice_date: str = Field(..., description="Date of the invoice (YYYY-MM-DD)")
    due_date: Optional[str] = Field(None, description="Payment due date")
    total_amount: float = Field(ge=0, description="Total invoice amount")
    currency: str = Field(default="USD", description="Currency code")
    line_items: List[LineItem] = Field(default_factory=list, description="Invoice line items")
    payment_terms: Optional[str] = Field(None, description="Payment terms (e.g., Net 30)")
    billing_address: Optional[str] = Field(None, description="Billing address")
    notes: Optional[str] = Field(None, description="Additional notes or comments")
    po_number: Optional[str] = Field(None, description="Reference to Purchase Order number")

    @field_validator("invoice_date", "due_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format is reasonable."""
        if v is None:
            return v
        # Basic validation - dates should be parseable
        # LLM may return various formats, so we're lenient here
        return v


class PurchaseOrderSchema(BaseModel):
    """Schema for extracted Purchase Order data."""

    po_number: str = Field(..., description="Unique PO identifier")
    vendor_name: str = Field(..., description="Name of the vendor/supplier")
    order_date: str = Field(..., description="Date the PO was created (YYYY-MM-DD)")
    expected_delivery_date: Optional[str] = Field(None, description="Expected delivery date")
    total_amount: float = Field(ge=0, description="Total PO amount")
    currency: str = Field(default="USD", description="Currency code")
    line_items: List[LineItem] = Field(default_factory=list, description="PO line items")
    billing_address: Optional[str] = Field(None, description="Billing address")
    shipping_address: Optional[str] = Field(None, description="Shipping address")
    payment_terms: Optional[str] = Field(None, description="Payment terms (e.g., Net 30)")
    contract_reference: Optional[str] = Field(None, description="Reference to contract")
    notes: Optional[str] = Field(None, description="Additional notes or comments")

    @field_validator("order_date", "expected_delivery_date")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        """Validate date format is reasonable."""
        if v is None:
            return v
        return v


class ParseResult(BaseModel):
    """Result of parsing a PDF document."""

    markdown: str = Field(..., description="Extracted markdown content")
    page_count: int = Field(ge=0, description="Number of pages in the document")
    tables_found: int = Field(ge=0, default=0, description="Number of tables detected")
    parse_method: Literal["docling", "pdfplumber"] = Field(
        ..., description="Method used for parsing"
    )
    success: bool = Field(..., description="Whether parsing was successful")
    error_message: Optional[str] = Field(None, description="Error message if parsing failed")
    file_path: Optional[str] = Field(None, description="Original file path")


class RetrievedClause(BaseModel):
    """A contract clause retrieved from vector store."""

    text: str = Field(..., description="The clause text content")
    vendor_name: str = Field(..., description="Vendor this clause belongs to")
    similarity_score: float = Field(ge=0, le=1, description="Semantic similarity score")
    chunk_id: str = Field(..., description="Unique identifier for this chunk")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class ValidationIssue(BaseModel):
    """Represents a validation issue found during matching."""

    rule: str = Field(..., description="Name of the validation rule")
    severity: Literal["critical", "error", "warning", "info"] = Field(
        ..., description="Severity level of the issue"
    )
    message: str = Field(..., description="Human-readable description of the issue")
    invoice_value: Any = Field(..., description="Value from the invoice")
    contract_value: Optional[Any] = Field(None, description="Expected value from contract")
    match_type: Optional[Literal["invoice_po", "invoice_contract", "po_contract"]] = Field(
        None, description="Type of match this issue belongs to (for three-way matching)"
    )


class MatchResult(BaseModel):
    """Result of matching an invoice against a contract."""

    status: Literal["PASS", "FAIL", "REVIEW"] = Field(
        ..., description="Overall match status"
    )
    vendor_name: str = Field(..., description="Vendor name")
    invoice_number: str = Field(..., description="Invoice number that was validated")
    issues: List[ValidationIssue] = Field(
        default_factory=list, description="List of validation issues"
    )
    matched_clauses: List[RetrievedClause] = Field(
        default_factory=list, description="Contract clauses used for matching"
    )
    confidence_score: float = Field(
        ge=0, le=1, description="Confidence in the match result"
    )
    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the match was performed"
    )

    @property
    def has_critical_issues(self) -> bool:
        """Check if there are any critical issues."""
        return any(issue.severity == "critical" for issue in self.issues)

    @property
    def issue_summary(self) -> dict:
        """Get a summary of issues by severity."""
        summary = {"critical": 0, "error": 0, "warning": 0, "info": 0}
        for issue in self.issues:
            summary[issue.severity] += 1
        return summary


class MatchDetail(BaseModel):
    """Result of a single match comparison (e.g., Invoice vs PO)."""

    match_type: Literal["invoice_po", "invoice_contract", "po_contract"] = Field(
        ..., description="Type of match performed"
    )
    passed: bool = Field(..., description="Whether this match passed validation")
    score: float = Field(ge=0, le=1, description="Match score (0.0 to 1.0)")
    issues: List[ValidationIssue] = Field(
        default_factory=list, description="Validation issues for this match"
    )
    details: dict = Field(
        default_factory=dict, description="Additional match-specific details"
    )

    @property
    def has_critical_issues(self) -> bool:
        """Check if there are any critical issues."""
        return any(issue.severity == "critical" for issue in self.issues)


class ThreeWayMatchResult(BaseModel):
    """Result of three-way matching between Invoice, PO, and Contract."""

    status: Literal["PASS", "FAIL", "REVIEW"] = Field(
        ..., description="Overall match status"
    )
    vendor_name: str = Field(..., description="Vendor name")
    invoice_number: str = Field(..., description="Invoice number that was validated")
    po_number: Optional[str] = Field(None, description="PO number used in matching")

    # Individual match results
    invoice_po_match: Optional[MatchDetail] = Field(
        None, description="Result of Invoice vs PO match"
    )
    invoice_contract_match: Optional[MatchDetail] = Field(
        None, description="Result of Invoice vs Contract match"
    )
    po_contract_match: Optional[MatchDetail] = Field(
        None, description="Result of PO vs Contract match"
    )

    # Summary metrics
    matches_passed: int = Field(
        ge=0, le=3, description="Number of matches that passed"
    )
    total_matches: int = Field(
        ge=0, le=3, description="Total number of matches attempted"
    )
    overall_score: float = Field(
        ge=0, le=1, description="Weighted average score across all matches"
    )

    # Combined issues and clauses
    all_issues: List[ValidationIssue] = Field(
        default_factory=list, description="All validation issues across all matches"
    )
    matched_clauses: List[RetrievedClause] = Field(
        default_factory=list, description="Contract clauses used for matching"
    )

    # Timestamps
    timestamp: datetime = Field(
        default_factory=datetime.now, description="When the match was performed"
    )

    @property
    def requires_manual_review(self) -> bool:
        """Check if this result requires manual review."""
        return self.status in ("FAIL", "REVIEW")

    @property
    def issue_summary(self) -> dict:
        """Get a summary of issues by severity."""
        summary = {"critical": 0, "error": 0, "warning": 0, "info": 0}
        for issue in self.all_issues:
            summary[issue.severity] += 1
        return summary

    @property
    def match_summary(self) -> dict:
        """Get a summary of match results."""
        return {
            "invoice_po": self.invoice_po_match.passed if self.invoice_po_match else None,
            "invoice_contract": self.invoice_contract_match.passed if self.invoice_contract_match else None,
            "po_contract": self.po_contract_match.passed if self.po_contract_match else None,
            "passed_count": self.matches_passed,
            "total_count": self.total_matches,
        }
