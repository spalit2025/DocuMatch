"""
Tests for DocumentService.

Tests orchestration logic: parse → extract → store pipelines.
All core modules are mocked -- we test call order and error propagation,
not the underlying parsing/extraction/storage logic.
"""

import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.services.document_service import DocumentService, DocumentProcessingError
from core.models import ParseResult, InvoiceSchema, PurchaseOrderSchema, LineItem
from core.extraction import ExtractionError
from core.exceptions import StoreError


# ==================== FIXTURES ====================


@pytest.fixture
def mock_parser():
    parser = MagicMock()
    parser.parse_to_markdown.return_value = ParseResult(
        markdown="# Contract\nSample text",
        page_count=2,
        tables_found=1,
        parse_method="docling",
        success=True,
    )
    return parser


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.index_contract.return_value = "contract-123"
    return store


@pytest.fixture
def mock_po_store():
    return MagicMock()


@pytest.fixture
def mock_extraction_engine():
    engine = MagicMock()
    engine.extract_invoice_data.return_value = InvoiceSchema(
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        invoice_date="2024-01-15",
        total_amount=5000.00,
        line_items=[
            LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
        ],
    )
    engine.extract_po_data.return_value = PurchaseOrderSchema(
        po_number="PO-001",
        vendor_name="Extracted Vendor",
        order_date="2024-01-10",
        total_amount=5000.00,
        line_items=[
            LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
        ],
    )
    return engine


@pytest.fixture
def service(mock_parser, mock_vector_store, mock_po_store, mock_extraction_engine):
    return DocumentService(
        parser=mock_parser,
        vector_store=mock_vector_store,
        po_store=mock_po_store,
        extraction_engine=mock_extraction_engine,
    )


@pytest.fixture
def tmp_pdf(tmp_path):
    """Create a temporary PDF file for testing."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake content")
    return str(pdf_path)


# ==================== INGEST CONTRACT ====================


class TestIngestContract:
    """Tests for DocumentService.ingest_contract()."""

    def test_success(self, service, mock_parser, mock_vector_store, tmp_pdf):
        contract_id, result = service.ingest_contract(
            file_path=tmp_pdf,
            vendor_name="Acme Corp",
            contract_type="MSA",
            metadata={"filename": "test.pdf"},
        )

        assert contract_id == "contract-123"
        assert result.success is True
        assert result.page_count == 2

        mock_parser.parse_to_markdown.assert_called_once_with(tmp_pdf)
        mock_vector_store.index_contract.assert_called_once_with(
            text="# Contract\nSample text",
            vendor_name="Acme Corp",
            contract_type="MSA",
            metadata={"filename": "test.pdf"},
        )

    def test_file_not_found(self, service):
        with pytest.raises(DocumentProcessingError, match="File not found"):
            service.ingest_contract(
                file_path="/nonexistent/path.pdf",
                vendor_name="Acme",
            )

    def test_parse_failure(self, service, mock_parser, tmp_pdf):
        mock_parser.parse_to_markdown.return_value = ParseResult(
            markdown="",
            page_count=0,
            tables_found=0,
            parse_method="docling",
            success=False,
            error_message="Corrupt PDF",
        )

        with pytest.raises(DocumentProcessingError, match="Failed to parse.*Corrupt PDF"):
            service.ingest_contract(tmp_pdf, "Acme")

    def test_store_error_propagates(self, service, mock_vector_store, tmp_pdf):
        mock_vector_store.index_contract.side_effect = StoreError("ChromaDB down")

        with pytest.raises(StoreError, match="ChromaDB down"):
            service.ingest_contract(tmp_pdf, "Acme")

    def test_default_metadata(self, service, mock_vector_store, tmp_pdf):
        """Metadata defaults to empty dict when not provided."""
        service.ingest_contract(tmp_pdf, "Acme")

        call_kwargs = mock_vector_store.index_contract.call_args[1]
        assert call_kwargs["metadata"] == {}

    def test_default_contract_type(self, service, mock_vector_store, tmp_pdf):
        """Contract type defaults to MSA."""
        service.ingest_contract(tmp_pdf, "Acme")

        call_kwargs = mock_vector_store.index_contract.call_args[1]
        assert call_kwargs["contract_type"] == "MSA"


# ==================== INGEST PO ====================


class TestIngestPO:
    """Tests for DocumentService.ingest_po()."""

    def test_success(self, service, mock_parser, mock_extraction_engine, mock_po_store, tmp_pdf):
        po, result = service.ingest_po(tmp_pdf, vendor_name="Acme Corp")

        assert po.po_number == "PO-001"
        assert po.vendor_name == "Acme Corp"  # Overridden from "Extracted Vendor"
        assert result.success is True

        mock_parser.parse_to_markdown.assert_called_once()
        mock_extraction_engine.extract_po_data.assert_called_once_with(
            "# Contract\nSample text"
        )
        mock_po_store.index_po.assert_called_once_with(po)

    def test_vendor_name_override(self, service, tmp_pdf):
        """Vendor name from caller overrides LLM-extracted vendor."""
        po, _ = service.ingest_po(tmp_pdf, vendor_name="Override Vendor")
        assert po.vendor_name == "Override Vendor"

    def test_parse_failure(self, service, mock_parser, tmp_pdf):
        mock_parser.parse_to_markdown.return_value = ParseResult(
            markdown="", page_count=0, tables_found=0,
            parse_method="docling", success=False,
            error_message="File too large",
        )

        with pytest.raises(DocumentProcessingError, match="File too large"):
            service.ingest_po(tmp_pdf, "Acme")

    def test_extraction_error_propagates(self, service, mock_extraction_engine, tmp_pdf):
        mock_extraction_engine.extract_po_data.side_effect = ExtractionError(
            "Ollama timeout"
        )

        with pytest.raises(ExtractionError, match="Ollama timeout"):
            service.ingest_po(tmp_pdf, "Acme")

    def test_store_error_propagates(self, service, mock_po_store, tmp_pdf):
        mock_po_store.index_po.side_effect = StoreError("ChromaDB connection lost")

        with pytest.raises(StoreError, match="ChromaDB connection lost"):
            service.ingest_po(tmp_pdf, "Acme")


# ==================== PROCESS INVOICE ====================


class TestProcessInvoice:
    """Tests for DocumentService.process_invoice()."""

    def test_success(self, service, mock_parser, mock_extraction_engine, tmp_pdf):
        invoice, result = service.process_invoice(tmp_pdf)

        assert invoice.invoice_number == "INV-001"
        assert invoice.vendor_name == "Acme Corp"
        assert invoice.total_amount == 5000.00
        assert result.success is True

        mock_parser.parse_to_markdown.assert_called_once()
        mock_extraction_engine.extract_invoice_data.assert_called_once()

    def test_file_not_found(self, service):
        with pytest.raises(DocumentProcessingError, match="File not found"):
            service.process_invoice("/nonexistent/invoice.pdf")

    def test_parse_failure(self, service, mock_parser, tmp_pdf):
        mock_parser.parse_to_markdown.return_value = ParseResult(
            markdown="", page_count=0, tables_found=0,
            parse_method="pdfplumber", success=False,
            error_message="Empty document",
        )

        with pytest.raises(DocumentProcessingError, match="Empty document"):
            service.process_invoice(tmp_pdf)

    def test_extraction_error_propagates(self, service, mock_extraction_engine, tmp_pdf):
        mock_extraction_engine.extract_invoice_data.side_effect = ExtractionError(
            "Model not found"
        )

        with pytest.raises(ExtractionError, match="Model not found"):
            service.process_invoice(tmp_pdf)

    def test_no_storage_call(self, service, mock_vector_store, mock_po_store, tmp_pdf):
        """Invoices are processed but not stored."""
        service.process_invoice(tmp_pdf)

        mock_vector_store.index_contract.assert_not_called()
        mock_po_store.index_po.assert_not_called()
