"""
API route handlers for DocuMatch Architect.

Endpoints:
    POST /api/contracts/ingest  - Upload and index a contract PDF
    POST /api/pos/ingest        - Upload, extract, and index a PO PDF
    POST /api/invoices/process  - Upload, extract, validate an invoice PDF
    GET  /api/health            - System health check
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from config import settings
from core.services import DocumentService, MatchService

from .dependencies import get_document_service, get_extraction_engine, get_match_service
from .schemas import (
    ComponentHealth,
    ContractIngestResponse,
    HealthResponse,
    InvoiceProcessResponse,
    LineItemResponse,
    MatchDetailResponse,
    ParseInfo,
    POIngestResponse,
    ValidationIssueResponse,
    ValidationSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")


# ==================== CONTRACTS ====================


@router.post(
    "/contracts/ingest",
    response_model=ContractIngestResponse,
    summary="Ingest a contract PDF",
    description="Upload a contract PDF, parse it to markdown, and index it in ChromaDB for semantic search.",
)
def ingest_contract(
    file: UploadFile = File(..., description="Contract PDF file"),
    vendor_name: str = Form(..., description="Vendor name"),
    contract_type: str = Form("MSA", description="Contract type: MSA, SOW, NDA, or Other"),
    service: DocumentService = Depends(get_document_service),
):
    # Save uploaded file
    save_path = settings.contracts_path / file.filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(file.file.read())

    # Process via service
    contract_id, result = service.ingest_contract(
        file_path=str(save_path),
        vendor_name=vendor_name,
        contract_type=contract_type,
        metadata={"filename": file.filename},
    )

    return ContractIngestResponse(
        contract_id=contract_id,
        vendor_name=vendor_name,
        contract_type=contract_type,
        parse_info=ParseInfo(
            page_count=result.page_count,
            tables_found=result.tables_found,
            parse_method=result.parse_method,
        ),
    )


# ==================== PURCHASE ORDERS ====================


@router.post(
    "/pos/ingest",
    response_model=POIngestResponse,
    summary="Ingest a Purchase Order PDF",
    description="Upload a PO PDF, extract structured data via LLM, and index it in ChromaDB.",
)
def ingest_po(
    file: UploadFile = File(..., description="Purchase Order PDF file"),
    vendor_name: str = Form(..., description="Vendor name"),
    service: DocumentService = Depends(get_document_service),
):
    # Save uploaded file
    save_path = settings.purchase_orders_path / file.filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(file.file.read())

    # Process via service
    po, result = service.ingest_po(
        file_path=str(save_path),
        vendor_name=vendor_name,
    )

    return POIngestResponse(
        po_number=po.po_number,
        vendor_name=po.vendor_name,
        order_date=po.order_date,
        total_amount=po.total_amount,
        currency=po.currency,
        line_items=[
            LineItemResponse(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total=item.total,
            )
            for item in po.line_items
        ],
        parse_info=ParseInfo(
            page_count=result.page_count,
            tables_found=result.tables_found,
            parse_method=result.parse_method,
        ),
    )


# ==================== INVOICES ====================


@router.post(
    "/invoices/process",
    response_model=InvoiceProcessResponse,
    summary="Process and validate an invoice",
    description=(
        "Upload an invoice PDF, extract structured data via LLM, "
        "and validate against indexed contracts and POs. "
        "Performs three-way matching if po_number is provided."
    ),
)
def process_invoice(
    file: UploadFile = File(..., description="Invoice PDF file"),
    po_number: Optional[str] = Form(None, description="PO number for three-way matching"),
    doc_service: DocumentService = Depends(get_document_service),
    match_service: MatchService = Depends(get_match_service),
):
    # Save uploaded file
    save_path = settings.invoices_path / file.filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(file.file.read())

    # Extract invoice data
    invoice, parse_result = doc_service.process_invoice(str(save_path))

    # Validate (three-way if PO provided, two-way otherwise)
    result = match_service.validate_three_way(invoice, po_number=po_number)

    # Build match detail responses
    def _match_detail(match) -> Optional[MatchDetailResponse]:
        if match is None:
            return None
        return MatchDetailResponse(
            match_type=match.match_type,
            passed=match.passed,
            score=match.score,
            issues=[
                ValidationIssueResponse(
                    rule=i.rule, severity=i.severity, message=i.message
                )
                for i in match.issues
            ],
        )

    return InvoiceProcessResponse(
        invoice_number=invoice.invoice_number,
        vendor_name=invoice.vendor_name,
        invoice_date=invoice.invoice_date,
        total_amount=invoice.total_amount,
        currency=invoice.currency,
        line_items=[
            LineItemResponse(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                total=item.total,
            )
            for item in invoice.line_items
        ],
        po_number=po_number or invoice.po_number,
        payment_terms=invoice.payment_terms,
        validation=ValidationSummary(
            status=result.status,
            matches_passed=result.matches_passed,
            total_matches=result.total_matches,
            overall_score=result.overall_score,
            invoice_po_match=_match_detail(result.invoice_po_match),
            invoice_contract_match=_match_detail(result.invoice_contract_match),
            po_contract_match=_match_detail(result.po_contract_match),
            issues=[
                ValidationIssueResponse(
                    rule=i.rule, severity=i.severity, message=i.message
                )
                for i in result.all_issues
            ],
        ),
    )


# ==================== HEALTH ====================


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="System health check",
    description="Check the status of all system components: parser, LLM (Ollama), and vector store (ChromaDB).",
)
def health_check(
    doc_service: DocumentService = Depends(get_document_service),
):
    components = {}

    # Parser (always available)
    parser = doc_service.parser
    parser_name = "Docling" if parser._docling_available else "pdfplumber"
    components["parser"] = ComponentHealth(status="ok", detail=parser_name)

    # Ollama LLM
    engine = doc_service.extraction_engine
    ollama_ok, ollama_msg = engine.check_connection()
    components["ollama"] = ComponentHealth(
        status="ok" if ollama_ok else "error",
        detail=ollama_msg,
    )

    # ChromaDB (try to get stats)
    try:
        doc_service.vector_store.get_stats()
        components["chromadb"] = ComponentHealth(status="ok", detail="Connected")
    except Exception as e:
        components["chromadb"] = ComponentHealth(status="error", detail=str(e))

    # Overall status
    statuses = [c.status for c in components.values()]
    if all(s == "ok" for s in statuses):
        overall = "healthy"
    elif any(s == "error" for s in statuses):
        # Degraded if parser works but other things don't
        if components["parser"].status == "ok":
            overall = "degraded"
        else:
            overall = "unhealthy"
    else:
        overall = "degraded"

    return HealthResponse(status=overall, components=components)
