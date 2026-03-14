"""
DocuMatch Architect - Core Business Logic Package

This package contains the core modules:
- parser_engine: PDF to Markdown conversion
- vector_store: ChromaDB operations for contract storage
- po_store: ChromaDB operations for Purchase Order storage
- extraction: LLM-based data extraction (Invoice and PO)
- matcher: Invoice-Contract-PO three-way validation logic
- models: Pydantic data models
- services: Orchestration layer (DocumentService, MatchService)
"""

from .models import (
    LineItem,
    InvoiceSchema,
    PurchaseOrderSchema,
    ParseResult,
    RetrievedClause,
    ValidationIssue,
    MatchResult,
    MatchDetail,
    ThreeWayMatchResult,
)
from .parser_engine import ParserEngine, parse_pdf
from .vector_store import VectorStore, create_vector_store
from .po_store import POStore, create_po_store
from .exceptions import StoreError
from .extraction import ExtractionEngine, ExtractionError, extract_invoice, extract_po
from .matcher import Matcher, validate_invoice, validate_invoice_three_way
from .report_generator import generate_report, generate_three_way_report
from .services import DocumentService, DocumentProcessingError, MatchService

__all__ = [
    # Models
    "LineItem",
    "InvoiceSchema",
    "PurchaseOrderSchema",
    "ParseResult",
    "RetrievedClause",
    "ValidationIssue",
    "MatchResult",
    "MatchDetail",
    "ThreeWayMatchResult",
    # Parser
    "ParserEngine",
    "parse_pdf",
    # Vector Store
    "VectorStore",
    "create_vector_store",
    # PO Store
    "POStore",
    "create_po_store",
    # Exceptions
    "StoreError",
    # Extraction
    "ExtractionEngine",
    "ExtractionError",
    "extract_invoice",
    "extract_po",
    # Matcher
    "Matcher",
    "validate_invoice",
    "validate_invoice_three_way",
    # Services
    "DocumentService",
    "DocumentProcessingError",
    "MatchService",
]
