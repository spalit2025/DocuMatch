"""
Tests for the Extraction Engine.

Run with: pytest tests/test_extraction.py -v

Note: Integration tests require Ollama to be running with phi3.5 model.
"""

import json
from unittest.mock import Mock, patch

import pytest

from core.extraction import ExtractionEngine, ExtractionError, extract_invoice
from core.models import InvoiceSchema, LineItem


# Sample invoice markdown for testing
SAMPLE_INVOICE_MARKDOWN = """
# INVOICE

**Invoice Number:** INV-2024-001
**Date:** January 15, 2024
**Due Date:** February 14, 2024

## From:
Acme Consulting Services
123 Business Street
New York, NY 10001

## Bill To:
Client Corporation
456 Client Avenue
Los Angeles, CA 90001

## Services Rendered

| Description | Quantity | Unit Price | Total |
|-------------|----------|------------|-------|
| Senior Consultant - Project Alpha | 40 hours | $150.00 | $6,000.00 |
| Junior Developer - Support | 20 hours | $85.00 | $1,700.00 |
| Project Management | 10 hours | $125.00 | $1,250.00 |

## Summary

**Subtotal:** $8,950.00
**Tax (0%):** $0.00
**Total Due:** $8,950.00

**Payment Terms:** Net 30

Please make payment to:
Bank: First National Bank
Account: 1234567890
"""


SAMPLE_EXTRACTED_JSON = {
    "vendor_name": "Acme Consulting Services",
    "invoice_number": "INV-2024-001",
    "invoice_date": "2024-01-15",
    "due_date": "2024-02-14",
    "total_amount": 8950.00,
    "currency": "USD",
    "line_items": [
        {
            "description": "Senior Consultant - Project Alpha",
            "quantity": 40,
            "unit_price": 150.00,
            "total": 6000.00
        },
        {
            "description": "Junior Developer - Support",
            "quantity": 20,
            "unit_price": 85.00,
            "total": 1700.00
        },
        {
            "description": "Project Management",
            "quantity": 10,
            "unit_price": 125.00,
            "total": 1250.00
        }
    ],
    "payment_terms": "Net 30",
    "billing_address": "Client Corporation, 456 Client Avenue, Los Angeles, CA 90001",
    "notes": None
}


class TestExtractionEngineInit:
    """Test cases for ExtractionEngine initialization."""

    def test_default_init(self):
        """Test default initialization."""
        engine = ExtractionEngine()
        assert engine.model == "phi3.5"
        assert engine.temperature == 0.1
        assert "localhost:11434" in engine.ollama_host

    def test_custom_init(self):
        """Test custom initialization."""
        engine = ExtractionEngine(
            model="llama3.2",
            ollama_host="http://custom:8080",
            temperature=0.5,
            timeout=60
        )
        assert engine.model == "llama3.2"
        assert engine.ollama_host == "http://custom:8080"
        assert engine.temperature == 0.5
        assert engine.timeout == 60


class TestJsonParsing:
    """Test cases for JSON parsing logic."""

    @pytest.fixture
    def engine(self):
        return ExtractionEngine()

    def test_parse_clean_json(self, engine):
        """Test parsing clean JSON response."""
        response = json.dumps(SAMPLE_EXTRACTED_JSON)
        result = engine._parse_json_response(response)
        assert result["vendor_name"] == "Acme Consulting Services"

    def test_parse_json_with_whitespace(self, engine):
        """Test parsing JSON with extra whitespace."""
        response = f"\n\n  {json.dumps(SAMPLE_EXTRACTED_JSON)}  \n\n"
        result = engine._parse_json_response(response)
        assert result["vendor_name"] == "Acme Consulting Services"

    def test_parse_json_in_markdown_block(self, engine):
        """Test parsing JSON wrapped in markdown code block."""
        response = f"```json\n{json.dumps(SAMPLE_EXTRACTED_JSON)}\n```"
        result = engine._parse_json_response(response)
        assert result["vendor_name"] == "Acme Consulting Services"

    def test_parse_json_with_preamble(self, engine):
        """Test parsing JSON with text before it."""
        response = f"Here is the extracted data:\n{json.dumps(SAMPLE_EXTRACTED_JSON)}"
        result = engine._parse_json_response(response)
        assert result["vendor_name"] == "Acme Consulting Services"

    def test_parse_invalid_json_fails(self, engine):
        """Test that invalid JSON raises error."""
        with pytest.raises(json.JSONDecodeError):
            engine._parse_json_response("This is not JSON at all")


class TestInvoiceValidation:
    """Test cases for invoice validation."""

    @pytest.fixture
    def engine(self):
        return ExtractionEngine()

    def test_validate_complete_invoice(self, engine):
        """Test validating a complete invoice."""
        invoice = engine._validate_invoice(SAMPLE_EXTRACTED_JSON)

        assert isinstance(invoice, InvoiceSchema)
        assert invoice.vendor_name == "Acme Consulting Services"
        assert invoice.invoice_number == "INV-2024-001"
        assert invoice.total_amount == 8950.00
        assert len(invoice.line_items) == 3

    def test_validate_minimal_invoice(self, engine):
        """Test validating invoice with minimal data."""
        minimal_data = {
            "vendor_name": "Test Vendor",
            "invoice_number": "123",
            "invoice_date": "2024-01-01",
            "total_amount": 100.00
        }

        invoice = engine._validate_invoice(minimal_data)

        assert invoice.vendor_name == "Test Vendor"
        assert invoice.currency == "USD"  # Default
        assert invoice.line_items == []

    def test_validate_with_missing_required_uses_defaults(self, engine):
        """Test that missing required fields get defaults."""
        incomplete_data = {
            "total_amount": 500
        }

        invoice = engine._validate_invoice(incomplete_data)

        assert invoice.vendor_name == "Unknown Vendor"
        assert invoice.invoice_number == "N/A"

    def test_validate_line_items(self, engine):
        """Test line item validation."""
        data = {
            "vendor_name": "Test",
            "invoice_number": "001",
            "invoice_date": "2024-01-01",
            "total_amount": 100,
            "line_items": [
                {"description": "Item 1", "quantity": 2, "unit_price": 25, "total": 50},
                {"description": "Item 2", "quantity": 1, "unit_price": 50, "total": 50}
            ]
        }

        invoice = engine._validate_invoice(data)

        assert len(invoice.line_items) == 2
        assert invoice.line_items[0].description == "Item 1"
        assert invoice.line_items[0].quantity == 2


class TestExtractionErrors:
    """Test cases for error handling."""

    @pytest.fixture
    def engine(self):
        return ExtractionEngine()

    def test_empty_document_raises_error(self, engine):
        """Test that empty document raises error."""
        with pytest.raises(ExtractionError, match="empty"):
            engine.extract_invoice_data("")

    def test_whitespace_document_raises_error(self, engine):
        """Test that whitespace-only document raises error."""
        with pytest.raises(ExtractionError, match="empty"):
            engine.extract_invoice_data("   \n\n   ")


class TestExtractionWithMocking:
    """Test extraction with mocked Ollama responses."""

    @pytest.fixture
    def engine(self):
        e = ExtractionEngine()
        e._connection_verified = True  # Skip pre-flight check in unit tests
        return e

    def test_successful_extraction(self, engine):
        """Test successful extraction with mocked API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": json.dumps(SAMPLE_EXTRACTED_JSON)}
        }

        with patch("requests.post", return_value=mock_response):
            invoice = engine.extract_invoice_data(SAMPLE_INVOICE_MARKDOWN)

        assert invoice.vendor_name == "Acme Consulting Services"
        assert invoice.total_amount == 8950.00

    def test_retry_on_invalid_json(self, engine):
        """Test that retry happens on invalid JSON."""
        # First response is invalid, second is valid
        mock_responses = [
            Mock(status_code=200, json=Mock(return_value={
                "message": {"content": "Not valid JSON"}
            })),
            Mock(status_code=200, json=Mock(return_value={
                "message": {"content": json.dumps(SAMPLE_EXTRACTED_JSON)}
            })),
        ]

        with patch("requests.post", side_effect=mock_responses):
            invoice = engine.extract_invoice_data(SAMPLE_INVOICE_MARKDOWN, max_retries=2)

        assert invoice.vendor_name == "Acme Consulting Services"

    def test_all_retries_exhausted(self, engine):
        """Test that error is raised after all retries fail."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": "Invalid response every time"}
        }

        with patch("requests.post", return_value=mock_response):
            with pytest.raises(ExtractionError, match="failed after"):
                engine.extract_invoice_data(SAMPLE_INVOICE_MARKDOWN, max_retries=1)


class TestConnectionCheck:
    """Test cases for connection checking."""

    def test_connection_success(self):
        """Test successful connection check."""
        engine = ExtractionEngine(model="phi3.5")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "phi3.5:latest"}]
        }

        with patch("requests.get", return_value=mock_response):
            ok, msg = engine.check_connection()

        assert ok is True
        assert "available" in msg.lower()

    def test_connection_model_not_found(self):
        """Test when model is not available."""
        engine = ExtractionEngine(model="nonexistent-model")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "models": [{"name": "phi3.5:latest"}]
        }

        with patch("requests.get", return_value=mock_response):
            ok, msg = engine.check_connection()

        assert ok is False
        assert "not found" in msg.lower()

    def test_connection_ollama_not_running(self):
        """Test when Ollama is not running."""
        engine = ExtractionEngine()

        with patch("requests.get", side_effect=Exception("Connection refused")):
            ok, msg = engine.check_connection()

        assert ok is False


class TestConvenienceFunction:
    """Test the convenience function."""

    def test_extract_invoice_function(self):
        """Test extract_invoice convenience function."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "message": {"content": json.dumps(SAMPLE_EXTRACTED_JSON)}
        }

        with patch("requests.post", return_value=mock_response), \
             patch.object(ExtractionEngine, '_verify_connection_once'):
            invoice = extract_invoice(
                SAMPLE_INVOICE_MARKDOWN,
                model="phi3.5"
            )

        assert isinstance(invoice, InvoiceSchema)
        assert invoice.vendor_name == "Acme Consulting Services"


class TestIntegration:
    """
    Integration tests requiring actual Ollama instance.

    These tests are skipped if Ollama is not running.
    """

    @pytest.fixture
    def engine(self):
        engine = ExtractionEngine(model="phi3.5")
        ok, _ = engine.check_connection()
        if not ok:
            pytest.skip("Ollama not running or model not available")
        return engine

    def test_real_extraction(self, engine):
        """Test extraction with real Ollama instance."""
        invoice = engine.extract_invoice_data(SAMPLE_INVOICE_MARKDOWN)

        assert isinstance(invoice, InvoiceSchema)
        assert invoice.vendor_name is not None
        assert invoice.total_amount > 0

    def test_real_extraction_simple_invoice(self, engine):
        """Test extraction with simpler invoice."""
        simple_invoice = """
        INVOICE #: 12345
        Date: 2024-03-15
        From: Simple Vendor LLC
        To: Customer Inc

        Services: Consulting - $500.00

        Total: $500.00
        Due: Net 15
        """

        invoice = engine.extract_invoice_data(simple_invoice)

        assert invoice.vendor_name is not None
        assert "12345" in invoice.invoice_number or invoice.invoice_number != "N/A"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
