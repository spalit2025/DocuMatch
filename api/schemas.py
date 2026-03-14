"""
API request/response schemas for DocuMatch Architect.

These are API-specific Pydantic models, separate from internal core models.
This allows the API contract to evolve independently from internal data structures.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ==================== SHARED ====================


class ParseInfo(BaseModel):
    """Parse result summary returned in API responses."""

    page_count: int
    tables_found: int
    parse_method: str


class LineItemResponse(BaseModel):
    """Line item as returned by the API."""

    description: str
    quantity: float
    unit_price: float
    total: float


class ValidationIssueResponse(BaseModel):
    """A single validation issue."""

    rule: str
    severity: str
    message: str


# ==================== CONTRACT ====================


class ContractIngestResponse(BaseModel):
    """Response after successfully ingesting a contract."""

    contract_id: str
    vendor_name: str
    contract_type: str
    parse_info: ParseInfo


# ==================== PURCHASE ORDER ====================


class POIngestResponse(BaseModel):
    """Response after successfully ingesting a PO."""

    po_number: str
    vendor_name: str
    order_date: str
    total_amount: float
    currency: str
    line_items: list[LineItemResponse]
    parse_info: ParseInfo


# ==================== INVOICE ====================


class MatchDetailResponse(BaseModel):
    """Result of one match comparison (e.g., Invoice vs PO)."""

    match_type: str
    passed: bool
    score: float
    issues: list[ValidationIssueResponse]


class ValidationSummary(BaseModel):
    """Summary of validation results."""

    status: str = Field(description="PASS, FAIL, or REVIEW")
    matches_passed: int
    total_matches: int
    overall_score: float
    invoice_po_match: Optional[MatchDetailResponse] = None
    invoice_contract_match: Optional[MatchDetailResponse] = None
    po_contract_match: Optional[MatchDetailResponse] = None
    issues: list[ValidationIssueResponse]


class InvoiceProcessResponse(BaseModel):
    """Response after processing and validating an invoice."""

    invoice_number: str
    vendor_name: str
    invoice_date: str
    total_amount: float
    currency: str
    line_items: list[LineItemResponse]
    po_number: Optional[str] = None
    payment_terms: Optional[str] = None
    validation: ValidationSummary


# ==================== HEALTH ====================


class ComponentHealth(BaseModel):
    """Health status of a single system component."""

    status: str = Field(description="ok or error")
    detail: Optional[str] = None


class HealthResponse(BaseModel):
    """System health check response."""

    status: str = Field(description="healthy, degraded, or unhealthy")
    components: dict[str, ComponentHealth]


# ==================== RESULTS ====================


class ResultResponse(BaseModel):
    """A stored validation result."""

    id: int
    job_id: int
    invoice_file: Optional[str] = None
    vendor_name: Optional[str] = None
    invoice_number: Optional[str] = None
    status: Optional[str] = None
    confidence: Optional[float] = None
    matches_passed: Optional[int] = None
    total_matches: Optional[int] = None
    created_at: str


class StatsResponse(BaseModel):
    """Aggregate statistics for the dashboard."""

    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    pending_jobs: int
    total_results: int
    pass_count: int
    fail_count: int
    review_count: int
    pass_rate: float


# ==================== ERRORS ====================


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: str
    detail: str
