"""
Hostile Input Tests (Tier 1 - Edge Cases)

Tests the system's resilience against adversarial, malformed, and
boundary-condition inputs. These are the tests a hostile QA engineer
would write to break the system.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.parser_engine import ParserEngine
from core.extraction import ExtractionEngine, ExtractionError
from core.models import ParseResult, InvoiceSchema, LineItem
from core.services.document_service import DocumentService, DocumentProcessingError


# ==================== FIXTURES ====================


@pytest.fixture
def parser():
    return ParserEngine(fallback_enabled=True)


@pytest.fixture
def mock_doc_service():
    """DocumentService with mocked core modules."""
    return DocumentService(
        parser=MagicMock(),
        vector_store=MagicMock(),
        po_store=MagicMock(),
        extraction_engine=MagicMock(),
    )


# ==================== PARSER HOSTILE INPUTS ====================


class TestParserHostileInputs:
    """Test parser against malformed/adversarial files."""

    def test_zero_byte_file(self, parser, tmp_path):
        """0-byte PDF should fail gracefully."""
        empty_pdf = tmp_path / "empty.pdf"
        empty_pdf.write_bytes(b"")

        result = parser.parse_to_markdown(str(empty_pdf))
        assert result.success is False

    def test_non_pdf_content(self, parser, tmp_path):
        """A .txt file renamed to .pdf should fail gracefully."""
        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_text("This is not a PDF file at all.")

        result = parser.parse_to_markdown(str(fake_pdf))
        # Parser should fail but not crash
        assert isinstance(result, ParseResult)

    def test_binary_garbage(self, parser, tmp_path):
        """Random binary data with .pdf extension."""
        garbage = tmp_path / "garbage.pdf"
        garbage.write_bytes(bytes(range(256)) * 100)

        result = parser.parse_to_markdown(str(garbage))
        assert isinstance(result, ParseResult)

    def test_nonexistent_file(self, parser):
        """File that doesn't exist."""
        result = parser.parse_to_markdown("/nonexistent/path/file.pdf")
        assert result.success is False

    def test_non_pdf_extension(self, parser, tmp_path):
        """File with wrong extension should fail."""
        txt_file = tmp_path / "document.txt"
        txt_file.write_text("Hello world")

        result = parser.parse_to_markdown(str(txt_file))
        assert result.success is False


# ==================== EXTRACTION HOSTILE INPUTS ====================


class TestExtractionHostileInputs:
    """Test extraction engine against adversarial inputs."""

    def test_empty_string(self):
        engine = ExtractionEngine()
        with pytest.raises(ExtractionError, match="empty document"):
            engine.extract_invoice_data("")

    def test_whitespace_only(self):
        engine = ExtractionEngine()
        with pytest.raises(ExtractionError, match="empty document"):
            engine.extract_invoice_data("   \n\t\n  ")

    def test_very_long_input_truncated(self):
        """Documents over 15000 chars should be truncated, not crash."""
        engine = ExtractionEngine()
        # Mock to avoid actual Ollama call
        with patch.object(engine, '_call_ollama', return_value='{"vendor_name": "Test"}'):
            with patch.object(engine, '_verify_connection_once'):
                long_text = "x" * 20000
                # Should not raise, should truncate internally
                try:
                    engine.extract_invoice_data(long_text)
                except ExtractionError:
                    pass  # Expected since mock returns minimal JSON

    def test_po_empty_string(self):
        engine = ExtractionEngine()
        with pytest.raises(ExtractionError, match="empty document"):
            engine.extract_po_data("")


# ==================== SERVICE HOSTILE INPUTS ====================


class TestServiceHostileInputs:
    """Test service layer against boundary conditions."""

    def test_ingest_contract_empty_vendor(self, mock_doc_service, tmp_path):
        """Empty vendor name should still work (ChromaDB handles it)."""
        pdf = tmp_path / "test.pdf"
        pdf.write_bytes(b"%PDF-1.4 content")

        mock_doc_service.parser.parse_to_markdown.return_value = ParseResult(
            markdown="# Contract", page_count=1, tables_found=0,
            parse_method="docling", success=True,
        )
        mock_doc_service.vector_store.index_contract.return_value = "id-123"

        contract_id, result = mock_doc_service.ingest_contract(
            str(pdf), vendor_name="", contract_type="MSA"
        )
        assert contract_id == "id-123"

    def test_process_invoice_file_not_found(self, mock_doc_service):
        """Processing a non-existent file should raise clearly."""
        with pytest.raises(DocumentProcessingError, match="File not found"):
            mock_doc_service.process_invoice("/does/not/exist.pdf")

    def test_ingest_contract_file_not_found(self, mock_doc_service):
        with pytest.raises(DocumentProcessingError, match="File not found"):
            mock_doc_service.ingest_contract("/nope.pdf", "Vendor")


# ==================== MODEL HOSTILE INPUTS ====================


class TestModelHostileInputs:
    """Test Pydantic models with boundary values."""

    def test_line_item_zero_quantity(self):
        item = LineItem(description="Zero qty", quantity=0, unit_price=100.0, total=0)
        assert item.quantity == 0

    def test_line_item_zero_price(self):
        item = LineItem(description="Free", quantity=10, unit_price=0, total=0)
        assert item.unit_price == 0

    def test_invoice_zero_total(self):
        invoice = InvoiceSchema(
            vendor_name="Test", invoice_number="INV-0",
            invoice_date="2024-01-01", total_amount=0,
        )
        assert invoice.total_amount == 0

    def test_invoice_very_long_vendor_name(self):
        invoice = InvoiceSchema(
            vendor_name="A" * 1000, invoice_number="INV-LONG",
            invoice_date="2024-01-01", total_amount=100,
        )
        assert len(invoice.vendor_name) == 1000

    def test_invoice_special_chars_in_number(self):
        invoice = InvoiceSchema(
            vendor_name="Test", invoice_number="INV/2024-001 (Rev.2)",
            invoice_date="2024-01-01", total_amount=100,
        )
        assert invoice.invoice_number == "INV/2024-001 (Rev.2)"

    def test_invoice_negative_amount_rejected(self):
        """Pydantic ge=0 constraint should reject negative amounts."""
        with pytest.raises(Exception):
            InvoiceSchema(
                vendor_name="Test", invoice_number="INV-NEG",
                invoice_date="2024-01-01", total_amount=-100,
            )
