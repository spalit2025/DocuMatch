"""
API tests for DocuMatch Architect.

Uses FastAPI TestClient with mocked services to test:
- Request/response contracts for all 4 endpoints
- Error handling (422, 502, 503)
- File upload handling
- Health check component status

All core modules are mocked -- we test the API layer, not business logic.
"""

import io
import pytest
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.app import app
from api.dependencies import get_batch_service, get_database, get_document_service, get_match_service
from core.exceptions import StoreError
from core.extraction import ExtractionError
from core.models import (
    InvoiceSchema,
    LineItem,
    MatchDetail,
    MatchResult,
    ParseResult,
    PurchaseOrderSchema,
    ThreeWayMatchResult,
    ValidationIssue,
)
from core.services import DocumentProcessingError


# ==================== FIXTURES ====================


@pytest.fixture
def mock_doc_service():
    service = MagicMock()

    # Default: parser available, extraction engine connected
    service.parser._docling_available = True
    service.extraction_engine.check_connection.return_value = (True, "Connected. Model 'phi3.5' available.")
    service.vector_store.get_stats.return_value = {"total_chunks": 10, "total_vendors": 2}

    return service


@pytest.fixture
def mock_match_service():
    return MagicMock()


@pytest.fixture
def mock_batch_service():
    return MagicMock()


@pytest.fixture
def mock_database():
    return MagicMock()


@pytest.fixture
def client(mock_doc_service, mock_match_service, mock_batch_service, mock_database):
    """TestClient with mocked dependencies."""
    app.dependency_overrides[get_document_service] = lambda: mock_doc_service
    app.dependency_overrides[get_match_service] = lambda: mock_match_service
    app.dependency_overrides[get_batch_service] = lambda: mock_batch_service
    app.dependency_overrides[get_database] = lambda: mock_database
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def fake_pdf():
    """A fake PDF file for upload testing."""
    return ("test.pdf", io.BytesIO(b"%PDF-1.4 fake content"), "application/pdf")


@pytest.fixture
def sample_parse_result():
    return ParseResult(
        markdown="# Document\nContent here",
        page_count=3,
        tables_found=1,
        parse_method="docling",
        success=True,
    )


@pytest.fixture
def sample_invoice():
    return InvoiceSchema(
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        invoice_date="2024-01-15",
        total_amount=5000.00,
        currency="USD",
        payment_terms="Net 30",
        po_number="PO-001",
        line_items=[
            LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
        ],
    )


@pytest.fixture
def sample_po():
    return PurchaseOrderSchema(
        po_number="PO-001",
        vendor_name="Acme Corp",
        order_date="2024-01-10",
        total_amount=5000.00,
        currency="USD",
        line_items=[
            LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
        ],
    )


@pytest.fixture
def sample_three_way_result():
    return ThreeWayMatchResult(
        status="PASS",
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        po_number="PO-001",
        invoice_po_match=MatchDetail(
            match_type="invoice_po", passed=True, score=0.95,
            issues=[],
        ),
        invoice_contract_match=MatchDetail(
            match_type="invoice_contract", passed=True, score=0.90,
            issues=[
                ValidationIssue(
                    rule="rate_card_found", severity="info",
                    message="Could not find specific rates",
                    invoice_value=None, match_type="invoice_contract",
                )
            ],
        ),
        po_contract_match=None,
        matches_passed=2,
        total_matches=2,
        overall_score=0.925,
        all_issues=[
            ValidationIssue(
                rule="rate_card_found", severity="info",
                message="Could not find specific rates",
                invoice_value=None, match_type="invoice_contract",
            )
        ],
        matched_clauses=[],
    )


# ==================== CONTRACT INGESTION ====================


class TestContractIngest:
    """Tests for POST /api/contracts/ingest."""

    def test_success(self, client, mock_doc_service, fake_pdf, sample_parse_result):
        mock_doc_service.ingest_contract.return_value = ("contract-abc", sample_parse_result)

        response = client.post(
            "/api/contracts/ingest",
            files={"file": fake_pdf},
            data={"vendor_name": "Acme Corp", "contract_type": "MSA"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["contract_id"] == "contract-abc"
        assert data["vendor_name"] == "Acme Corp"
        assert data["contract_type"] == "MSA"
        assert data["parse_info"]["page_count"] == 3
        assert data["parse_info"]["parse_method"] == "docling"

    def test_default_contract_type(self, client, mock_doc_service, fake_pdf, sample_parse_result):
        mock_doc_service.ingest_contract.return_value = ("contract-abc", sample_parse_result)

        response = client.post(
            "/api/contracts/ingest",
            files={"file": fake_pdf},
            data={"vendor_name": "Acme"},
        )

        assert response.status_code == 200
        assert response.json()["contract_type"] == "MSA"

    def test_parse_failure_returns_422(self, client, mock_doc_service, fake_pdf):
        mock_doc_service.ingest_contract.side_effect = DocumentProcessingError(
            "Failed to parse test.pdf: Corrupt PDF"
        )

        response = client.post(
            "/api/contracts/ingest",
            files={"file": fake_pdf},
            data={"vendor_name": "Acme"},
        )

        assert response.status_code == 422
        assert response.json()["error"] == "document_processing_error"
        assert "Corrupt PDF" in response.json()["detail"]

    def test_store_error_returns_503(self, client, mock_doc_service, fake_pdf):
        mock_doc_service.ingest_contract.side_effect = StoreError("ChromaDB down")

        response = client.post(
            "/api/contracts/ingest",
            files={"file": fake_pdf},
            data={"vendor_name": "Acme"},
        )

        assert response.status_code == 503
        assert response.json()["error"] == "store_error"

    def test_missing_vendor_name_returns_422(self, client, fake_pdf):
        response = client.post(
            "/api/contracts/ingest",
            files={"file": fake_pdf},
        )

        assert response.status_code == 422

    def test_missing_file_returns_422(self, client):
        response = client.post(
            "/api/contracts/ingest",
            data={"vendor_name": "Acme"},
        )

        assert response.status_code == 422


# ==================== PO INGESTION ====================


class TestPOIngest:
    """Tests for POST /api/pos/ingest."""

    def test_success(self, client, mock_doc_service, fake_pdf, sample_po, sample_parse_result):
        mock_doc_service.ingest_po.return_value = (sample_po, sample_parse_result)

        response = client.post(
            "/api/pos/ingest",
            files={"file": fake_pdf},
            data={"vendor_name": "Acme Corp"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["po_number"] == "PO-001"
        assert data["vendor_name"] == "Acme Corp"
        assert data["total_amount"] == 5000.00
        assert len(data["line_items"]) == 1
        assert data["line_items"][0]["description"] == "Consulting"
        assert data["parse_info"]["page_count"] == 3

    def test_extraction_error_returns_502(self, client, mock_doc_service, fake_pdf):
        mock_doc_service.ingest_po.side_effect = ExtractionError(
            "Request timed out after 120s"
        )

        response = client.post(
            "/api/pos/ingest",
            files={"file": fake_pdf},
            data={"vendor_name": "Acme"},
        )

        assert response.status_code == 502
        assert response.json()["error"] == "extraction_error"
        assert "timed out" in response.json()["detail"]

    def test_parse_failure_returns_422(self, client, mock_doc_service, fake_pdf):
        mock_doc_service.ingest_po.side_effect = DocumentProcessingError(
            "File too large: 75.0MB exceeds limit"
        )

        response = client.post(
            "/api/pos/ingest",
            files={"file": fake_pdf},
            data={"vendor_name": "Acme"},
        )

        assert response.status_code == 422


# ==================== INVOICE PROCESSING ====================


class TestInvoiceProcess:
    """Tests for POST /api/invoices/process."""

    def test_success_with_po(
        self, client, mock_doc_service, mock_match_service,
        fake_pdf, sample_invoice, sample_parse_result, sample_three_way_result,
    ):
        mock_doc_service.process_invoice.return_value = (sample_invoice, sample_parse_result)
        mock_match_service.validate_three_way.return_value = sample_three_way_result

        response = client.post(
            "/api/invoices/process",
            files={"file": fake_pdf},
            data={"po_number": "PO-001"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["invoice_number"] == "INV-001"
        assert data["vendor_name"] == "Acme Corp"
        assert data["total_amount"] == 5000.00
        assert data["po_number"] == "PO-001"

        # Validation section
        v = data["validation"]
        assert v["status"] == "PASS"
        assert v["matches_passed"] == 2
        assert v["total_matches"] == 2
        assert v["invoice_po_match"]["passed"] is True
        assert v["invoice_contract_match"]["passed"] is True
        assert v["po_contract_match"] is None
        assert len(v["issues"]) == 1

    def test_success_without_po(
        self, client, mock_doc_service, mock_match_service,
        fake_pdf, sample_invoice, sample_parse_result, sample_three_way_result,
    ):
        mock_doc_service.process_invoice.return_value = (sample_invoice, sample_parse_result)
        mock_match_service.validate_three_way.return_value = sample_three_way_result

        response = client.post(
            "/api/invoices/process",
            files={"file": fake_pdf},
        )

        assert response.status_code == 200
        # po_number should come from invoice's po_number field
        assert response.json()["po_number"] == "PO-001"

    def test_extraction_error_returns_502(self, client, mock_doc_service, fake_pdf):
        mock_doc_service.process_invoice.side_effect = ExtractionError(
            "Cannot connect to Ollama. Is it running?"
        )

        response = client.post(
            "/api/invoices/process",
            files={"file": fake_pdf},
        )

        assert response.status_code == 502
        assert "Ollama" in response.json()["detail"]

    def test_validation_fail_result(
        self, client, mock_doc_service, mock_match_service,
        fake_pdf, sample_invoice, sample_parse_result,
    ):
        mock_doc_service.process_invoice.return_value = (sample_invoice, sample_parse_result)
        mock_match_service.validate_three_way.return_value = ThreeWayMatchResult(
            status="FAIL",
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            po_number=None,
            invoice_po_match=None,
            invoice_contract_match=MatchDetail(
                match_type="invoice_contract", passed=False, score=0.2,
                issues=[
                    ValidationIssue(
                        rule="contract_exists", severity="critical",
                        message="No contract found for vendor 'Acme Corp'",
                        invoice_value="Acme Corp",
                        match_type="invoice_contract",
                    )
                ],
            ),
            po_contract_match=None,
            matches_passed=0,
            total_matches=1,
            overall_score=0.2,
            all_issues=[
                ValidationIssue(
                    rule="contract_exists", severity="critical",
                    message="No contract found for vendor 'Acme Corp'",
                    invoice_value="Acme Corp",
                    match_type="invoice_contract",
                )
            ],
            matched_clauses=[],
        )

        response = client.post(
            "/api/invoices/process",
            files={"file": fake_pdf},
        )

        assert response.status_code == 200  # HTTP 200, but validation FAIL
        v = response.json()["validation"]
        assert v["status"] == "FAIL"
        assert v["matches_passed"] == 0
        assert v["issues"][0]["severity"] == "critical"


# ==================== HEALTH CHECK ====================


class TestHealthCheck:
    """Tests for GET /api/health."""

    def test_healthy(self, client, mock_doc_service):
        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["components"]["parser"]["status"] == "ok"
        assert data["components"]["ollama"]["status"] == "ok"
        assert data["components"]["chromadb"]["status"] == "ok"

    def test_degraded_ollama_down(self, client, mock_doc_service):
        mock_doc_service.extraction_engine.check_connection.return_value = (
            False, "Ollama not running"
        )

        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["components"]["ollama"]["status"] == "error"
        assert data["components"]["parser"]["status"] == "ok"

    def test_degraded_chromadb_down(self, client, mock_doc_service):
        mock_doc_service.vector_store.get_stats.side_effect = Exception("Connection refused")

        response = client.get("/api/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["components"]["chromadb"]["status"] == "error"
        assert "Connection refused" in data["components"]["chromadb"]["detail"]

    def test_pdfplumber_fallback(self, client, mock_doc_service):
        mock_doc_service.parser._docling_available = False

        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["components"]["parser"]["detail"] == "pdfplumber"


# ==================== BATCH PROCESSING ====================


class TestBatchAPI:
    """Tests for batch processing API endpoints."""

    def test_submit_batch(self, client, mock_batch_service):
        mock_batch_service.submit_batch.return_value = 42

        response = client.post(
            "/api/batch/process",
            json={
                "files": [
                    {"file_path": "/tmp/inv1.pdf", "po_number": "PO-001"},
                    {"file_path": "/tmp/inv2.pdf"},
                ]
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["batch_id"] == 42
        assert data["total_files"] == 2
        assert data["status"] == "PARSING"

    def test_submit_empty_batch(self, client):
        response = client.post(
            "/api/batch/process",
            json={"files": []},
        )
        assert response.status_code == 422

    def test_get_batch_status(self, client, mock_batch_service):
        from core.services.batch_service import BatchStatus
        mock_batch_service.get_batch_status.return_value = BatchStatus(
            job_id=42,
            status="PARSING",
            total_files=3,
            completed=1,
            failed=0,
            pending=1,
            processing=1,
            eta_seconds=30.5,
            errors=[],
        )

        response = client.get("/api/batch/42/status")

        assert response.status_code == 200
        data = response.json()
        assert data["job_id"] == 42
        assert data["total_files"] == 3
        assert data["completed"] == 1
        assert data["eta_seconds"] == 30.5

    def test_get_batch_status_not_found(self, client, mock_batch_service):
        mock_batch_service.get_batch_status.return_value = None

        response = client.get("/api/batch/999/status")
        assert response.status_code == 404

    def test_cancel_batch(self, client, mock_batch_service):
        mock_batch_service.cancel_batch.return_value = True

        response = client.post("/api/batch/42/cancel")

        assert response.status_code == 200
        assert "cancellation" in response.json()["message"]

    def test_cancel_batch_not_found(self, client, mock_batch_service):
        mock_batch_service.cancel_batch.return_value = False

        response = client.post("/api/batch/999/cancel")
        assert response.status_code == 404


# ==================== RESULTS & STATS ====================


class TestResultsAPI:
    """Tests for GET /api/results and GET /api/stats."""

    def test_get_results_empty(self, client, mock_database):
        mock_database.get_results.return_value = []

        response = client.get("/api/results")

        assert response.status_code == 200
        assert response.json() == []

    def test_get_results_with_data(self, client, mock_database):
        from datetime import datetime, timezone
        mock_result = MagicMock()
        mock_result.id = 1
        mock_result.job_id = 10
        mock_result.invoice_file = "invoice.pdf"
        mock_result.vendor_name = "Acme"
        mock_result.invoice_number = "INV-001"
        mock_result.status = "PASS"
        mock_result.confidence = 0.95
        mock_result.matches_passed = 2
        mock_result.total_matches = 2
        mock_result.created_at = datetime(2024, 1, 15, tzinfo=timezone.utc)
        mock_database.get_results.return_value = [mock_result]

        response = client.get("/api/results")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["invoice_number"] == "INV-001"
        assert data[0]["status"] == "PASS"

    def test_get_results_with_filters(self, client, mock_database):
        mock_database.get_results.return_value = []

        client.get("/api/results?vendor_name=Acme&status=PASS&limit=10")

        mock_database.get_results.assert_called_once_with(
            vendor_name="Acme", status="PASS", job_id=None, limit=10,
        )

    def test_get_stats(self, client, mock_database):
        mock_database.get_stats.return_value = {
            "total_jobs": 10,
            "completed_jobs": 8,
            "failed_jobs": 1,
            "pending_jobs": 1,
            "total_results": 15,
            "pass_count": 12,
            "fail_count": 2,
            "review_count": 1,
            "pass_rate": 0.8,
        }

        response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 10
        assert data["pass_rate"] == 0.8
        assert data["pass_count"] == 12
