"""
Document Service for DocuMatch Architect.

Orchestrates document ingestion pipelines:
  - Contract: PDF → parse → chunk → index to ChromaDB
  - PO:       PDF → parse → LLM extract → index to ChromaDB
  - Invoice:  PDF → parse → LLM extract → return schema

Processing Pipeline:
    ┌────────┐     ┌─────────┐     ┌──────────┐     ┌────────┐
    │  PDF   │────▶│  Parse  │────▶│ Extract  │────▶│ Store  │
    │ (file) │     │ (Docling)│     │ (Ollama) │     │(Chroma)│
    └────────┘     └─────────┘     └──────────┘     └────────┘
                        │               │                │
                   ParseResult    Schema (Invoice   contract_id
                                   or PO)           or indexed PO

    Contract: Parse → Store (no extraction needed)
    PO:       Parse → Extract → Store
    Invoice:  Parse → Extract (no storage — matched, not stored)
"""

import logging
from pathlib import Path
from typing import Optional

from ..extraction import ExtractionEngine
from ..models import InvoiceSchema, ParseResult, PurchaseOrderSchema
from ..parser_engine import ParserEngine
from ..po_store import POStore
from ..vector_store import VectorStore

logger = logging.getLogger(__name__)


class DocumentProcessingError(Exception):
    """Raised when document processing fails at the orchestration level."""
    pass


class DocumentService:
    """
    Orchestrates all document ingestion workflows.

    Accepts core module instances via constructor injection for testability.

    Usage:
        service = DocumentService(parser, vector_store, po_store, extraction_engine)
        contract_id, result = service.ingest_contract("path.pdf", "Acme", "MSA")
        po, result = service.ingest_po("po.pdf", "Acme")
        invoice, result = service.process_invoice("invoice.pdf")
    """

    def __init__(
        self,
        parser: ParserEngine,
        vector_store: VectorStore,
        po_store: POStore,
        extraction_engine: ExtractionEngine,
    ):
        self.parser = parser
        self.vector_store = vector_store
        self.po_store = po_store
        self.extraction_engine = extraction_engine

    def ingest_contract(
        self,
        file_path: str,
        vendor_name: str,
        contract_type: str = "MSA",
        metadata: Optional[dict] = None,
    ) -> tuple[str, ParseResult]:
        """
        Ingest a contract PDF: parse and index to ChromaDB.

        Args:
            file_path: Path to the contract PDF
            vendor_name: Vendor name for organizing clauses
            contract_type: Contract type (MSA, SOW, NDA, Other)
            metadata: Additional metadata to store with the contract

        Returns:
            Tuple of (contract_id, ParseResult)

        Raises:
            DocumentProcessingError: If parsing fails
            StoreError: If ChromaDB indexing fails
        """
        logger.info(f"Ingesting contract for vendor '{vendor_name}' from {file_path}")

        # Parse PDF to markdown
        result = self._parse_document(file_path)

        # Index to ChromaDB
        contract_id = self.vector_store.index_contract(
            text=result.markdown,
            vendor_name=vendor_name,
            contract_type=contract_type,
            metadata=metadata or {},
        )

        logger.info(f"Contract indexed: id={contract_id}, vendor={vendor_name}")
        return contract_id, result

    def ingest_po(
        self,
        file_path: str,
        vendor_name: str,
    ) -> tuple[PurchaseOrderSchema, ParseResult]:
        """
        Ingest a PO PDF: parse, extract structured data, and index.

        Args:
            file_path: Path to the PO PDF
            vendor_name: Vendor name (overrides LLM extraction)

        Returns:
            Tuple of (PurchaseOrderSchema, ParseResult)

        Raises:
            DocumentProcessingError: If parsing fails
            ExtractionError: If LLM extraction fails
            StoreError: If ChromaDB indexing fails
        """
        logger.info(f"Ingesting PO for vendor '{vendor_name}' from {file_path}")

        # Parse PDF to markdown
        result = self._parse_document(file_path)

        # Extract structured PO data via LLM
        po = self.extraction_engine.extract_po_data(result.markdown)
        po.vendor_name = vendor_name

        # Index to ChromaDB
        self.po_store.index_po(po)

        logger.info(f"PO indexed: number={po.po_number}, vendor={vendor_name}")
        return po, result

    def process_invoice(
        self,
        file_path: str,
    ) -> tuple[InvoiceSchema, ParseResult]:
        """
        Process an invoice PDF: parse and extract structured data.

        Note: Invoices are not stored -- they are extracted and then
        validated against contracts/POs via MatchService.

        Args:
            file_path: Path to the invoice PDF

        Returns:
            Tuple of (InvoiceSchema, ParseResult)

        Raises:
            DocumentProcessingError: If parsing fails
            ExtractionError: If LLM extraction fails
        """
        logger.info(f"Processing invoice from {file_path}")

        # Parse PDF to markdown
        result = self._parse_document(file_path)

        # Extract structured invoice data via LLM
        invoice = self.extraction_engine.extract_invoice_data(result.markdown)

        logger.info(
            f"Invoice processed: number={invoice.invoice_number}, "
            f"vendor={invoice.vendor_name}, total=${invoice.total_amount:.2f}"
        )
        return invoice, result

    def _parse_document(self, file_path: str) -> ParseResult:
        """
        Parse a PDF document to markdown.

        Raises:
            DocumentProcessingError: If file doesn't exist or parsing fails
        """
        path = Path(file_path)
        if not path.exists():
            raise DocumentProcessingError(f"File not found: {file_path}")

        result = self.parser.parse_to_markdown(file_path)

        if not result.success:
            raise DocumentProcessingError(
                f"Failed to parse {path.name}: {result.error_message}"
            )

        return result
