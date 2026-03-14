"""
API route handlers for DocuMatch Architect.

Endpoints:
    POST /api/contracts/ingest  - Upload and index a contract PDF
    POST /api/pos/ingest        - Upload, extract, and index a PO PDF
    POST /api/invoices/process  - Upload, extract, validate an invoice PDF
    GET  /api/results           - Query stored validation results
    GET  /api/stats             - Aggregate processing statistics
    GET  /api/health            - System health check
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from fastapi.responses import Response

from config import settings
from core.database import Database
from core.export import export_results_excel
from core.extraction import ExtractionEngine
from core.services import BatchService, DocumentService, MatchService
from core.services.batch_service import BatchFile

from .dependencies import (
    get_batch_service,
    get_database,
    get_document_service,
    get_match_service,
)
from .schemas import (
    BatchErrorDetail,
    BatchStatusResponse,
    BatchSubmitRequest,
    BatchSubmitResponse,
    ComponentHealth,
    ContractIngestResponse,
    HealthResponse,
    InvoiceProcessResponse,
    LineItemResponse,
    MatchDetailResponse,
    ParseInfo,
    POIngestResponse,
    ResultResponse,
    StatsResponse,
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
    model: Optional[str] = Form(None, description="LLM model override (e.g., llama3.2)"),
    service: DocumentService = Depends(get_document_service),
):
    # Save uploaded file
    save_path = settings.purchase_orders_path / file.filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(file.file.read())

    # Swap extraction engine if model override specified
    original_engine = None
    if model and model != settings.default_model:
        original_engine = service.extraction_engine
        service.extraction_engine = ExtractionEngine(
            model=model, ollama_host=settings.ollama_host,
        )

    try:
        po, result = service.ingest_po(
            file_path=str(save_path),
            vendor_name=vendor_name,
        )
    finally:
        if original_engine:
            service.extraction_engine = original_engine

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
    model: Optional[str] = Form(None, description="LLM model override (e.g., llama3.2)"),
    doc_service: DocumentService = Depends(get_document_service),
    match_service: MatchService = Depends(get_match_service),
):
    # Save uploaded file
    save_path = settings.invoices_path / file.filename
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(file.file.read())

    # Swap extraction engine if model override specified
    original_engine = None
    if model and model != settings.default_model:
        original_engine = doc_service.extraction_engine
        doc_service.extraction_engine = ExtractionEngine(
            model=model, ollama_host=settings.ollama_host,
        )

    try:
        invoice, parse_result = doc_service.process_invoice(str(save_path))
    finally:
        if original_engine:
            doc_service.extraction_engine = original_engine

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


# ==================== BATCH PROCESSING ====================


@router.post(
    "/batch/process",
    response_model=BatchSubmitResponse,
    summary="Submit a batch of invoices for processing",
    description=(
        "Submit multiple invoice files for concurrent processing. "
        "Returns immediately with a batch ID for status polling via "
        "GET /api/batch/{batch_id}/status. Max 100 files per batch."
    ),
)
def submit_batch(
    request: BatchSubmitRequest,
    batch_service: BatchService = Depends(get_batch_service),
):
    files = [
        BatchFile(file_path=f.file_path, po_number=f.po_number)
        for f in request.files
    ]

    batch_id = batch_service.submit_batch(files)

    return BatchSubmitResponse(
        batch_id=batch_id,
        total_files=len(files),
        status="PARSING",
    )


@router.get(
    "/batch/{batch_id}/status",
    response_model=BatchStatusResponse,
    summary="Check batch processing status",
    description="Poll this endpoint to track progress of a submitted batch.",
)
def get_batch_status(
    batch_id: int,
    batch_service: BatchService = Depends(get_batch_service),
):
    status = batch_service.get_batch_status(batch_id)
    if status is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    return BatchStatusResponse(
        job_id=status.job_id,
        status=status.status,
        total_files=status.total_files,
        completed=status.completed,
        failed=status.failed,
        pending=status.pending,
        processing=status.processing,
        eta_seconds=status.eta_seconds,
        errors=[
            BatchErrorDetail(file=e["file"], error=e["error"])
            for e in status.errors
        ],
    )


@router.post(
    "/batch/{batch_id}/cancel",
    summary="Cancel a running batch",
    description="Signal cancellation for a running batch. Already-processing files will complete.",
)
def cancel_batch(
    batch_id: int,
    batch_service: BatchService = Depends(get_batch_service),
):
    cancelled = batch_service.cancel_batch(batch_id)
    if cancelled:
        return {"message": f"Batch {batch_id} cancellation requested"}

    from fastapi import HTTPException
    raise HTTPException(
        status_code=404,
        detail=f"Batch {batch_id} not found or already finished",
    )


# ==================== RESULTS ====================


@router.get(
    "/results",
    response_model=list[ResultResponse],
    summary="Query validation results",
    description="Retrieve stored validation results with optional filters by vendor, status, or job.",
)
def get_results(
    vendor_name: Optional[str] = Query(None, description="Filter by vendor name"),
    status: Optional[str] = Query(None, description="Filter by status: PASS, FAIL, or REVIEW"),
    job_id: Optional[int] = Query(None, description="Filter by job ID"),
    limit: int = Query(50, ge=1, le=500, description="Max results to return"),
    db: Database = Depends(get_database),
):
    results = db.get_results(
        vendor_name=vendor_name,
        status=status,
        job_id=job_id,
        limit=limit,
    )

    return [
        ResultResponse(
            id=r.id,
            job_id=r.job_id,
            invoice_file=r.invoice_file,
            vendor_name=r.vendor_name,
            invoice_number=r.invoice_number,
            status=r.status,
            confidence=r.confidence,
            matches_passed=r.matches_passed,
            total_matches=r.total_matches,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in results
    ]


@router.get(
    "/stats",
    response_model=StatsResponse,
    summary="Processing statistics",
    description="Get aggregate statistics: total jobs, pass/fail rates, pending counts.",
)
def get_stats(
    db: Database = Depends(get_database),
):
    return StatsResponse(**db.get_stats())


# ==================== EXPORT ====================


@router.get(
    "/export/excel",
    summary="Export results as Excel",
    description="Download validation results as an Excel file with summary and details sheets.",
)
def export_excel(
    vendor_name: Optional[str] = Query(None, description="Filter by vendor"),
    status: Optional[str] = Query(None, description="Filter by status"),
    db: Database = Depends(get_database),
):
    excel_bytes = export_results_excel(
        database=db, vendor_name=vendor_name, status=status,
    )

    filename = f"documatch_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
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
