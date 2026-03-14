"""
FastAPI application for DocuMatch Architect.

Run with:
    uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload

OpenAPI docs available at:
    http://localhost:8000/docs  (Swagger UI)
    http://localhost:8000/redoc (ReDoc)
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from core.exceptions import StoreError
from core.extraction import ExtractionError
from core.services import DocumentProcessingError

from .routes import router
from .schemas import ErrorResponse

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="DocuMatch Architect API",
    description=(
        "Privacy-first, 100% offline document processing API. "
        "Validates invoices against contracts and purchase orders "
        "using local LLMs and semantic search. "
        "Supports three-way matching: Invoice <-> PO <-> Contract."
    ),
    version="2.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware (allow all origins for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router)


# ==================== EXCEPTION HANDLERS ====================


@app.exception_handler(DocumentProcessingError)
async def document_processing_error_handler(
    request: Request, exc: DocumentProcessingError
):
    """Handle document parsing/processing failures."""
    logger.warning(f"Document processing error: {exc}")
    return JSONResponse(
        status_code=422,
        content=ErrorResponse(
            error="document_processing_error",
            detail=str(exc),
        ).model_dump(),
    )


@app.exception_handler(ExtractionError)
async def extraction_error_handler(request: Request, exc: ExtractionError):
    """Handle LLM extraction failures (Ollama down, bad response, etc.)."""
    logger.error(f"Extraction error: {exc}")
    return JSONResponse(
        status_code=502,
        content=ErrorResponse(
            error="extraction_error",
            detail=str(exc),
        ).model_dump(),
    )


@app.exception_handler(StoreError)
async def store_error_handler(request: Request, exc: StoreError):
    """Handle ChromaDB infrastructure failures."""
    logger.error(f"Store error: {exc}")
    return JSONResponse(
        status_code=503,
        content=ErrorResponse(
            error="store_error",
            detail=str(exc),
        ).model_dump(),
    )
