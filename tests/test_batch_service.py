"""
Tests for Batch Processing Service.

Tests concurrent invoice processing, per-file error isolation,
job state tracking, ETA calculation, and cancellation.
All core modules are mocked -- we test orchestration, not business logic.
"""

import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.database import Database
from core.models import (
    InvoiceSchema,
    LineItem,
    MatchDetail,
    ParseResult,
    ThreeWayMatchResult,
)
from core.services.batch_service import (
    BatchFile,
    BatchService,
    BatchStatus,
    MAX_BATCH_SIZE,
)


# ==================== FIXTURES ====================


@pytest.fixture
def db(tmp_path):
    return Database(str(tmp_path / "test.db"))


@pytest.fixture
def mock_doc_service():
    service = MagicMock()
    service.process_invoice.return_value = (
        InvoiceSchema(
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            invoice_date="2024-01-15",
            total_amount=5000.00,
            line_items=[
                LineItem(description="Consulting", quantity=40, unit_price=125.00, total=5000.00)
            ],
        ),
        ParseResult(
            markdown="# Invoice", page_count=1, tables_found=0,
            parse_method="docling", success=True,
        ),
    )
    return service


@pytest.fixture
def mock_match_service():
    service = MagicMock()
    service.validate_three_way.return_value = ThreeWayMatchResult(
        status="PASS",
        vendor_name="Acme Corp",
        invoice_number="INV-001",
        po_number=None,
        invoice_po_match=None,
        invoice_contract_match=MatchDetail(
            match_type="invoice_contract", passed=True, score=0.9, issues=[],
        ),
        po_contract_match=None,
        matches_passed=1,
        total_matches=1,
        overall_score=0.9,
        all_issues=[],
        matched_clauses=[],
    )
    return service


@pytest.fixture
def batch_service(mock_doc_service, mock_match_service, db):
    return BatchService(
        document_service=mock_doc_service,
        match_service=mock_match_service,
        database=db,
        max_workers=2,
    )


# ==================== SUBMIT BATCH ====================


class TestSubmitBatch:
    """Tests for batch submission."""

    def test_submit_returns_batch_id(self, batch_service):
        files = [BatchFile(file_path="/tmp/inv1.pdf")]
        batch_id = batch_service.submit_batch(files)

        assert isinstance(batch_id, int)
        assert batch_id > 0

    def test_empty_batch_raises(self, batch_service):
        with pytest.raises(ValueError, match="cannot be empty"):
            batch_service.submit_batch([])

    def test_oversized_batch_raises(self, batch_service):
        files = [BatchFile(file_path=f"/tmp/inv{i}.pdf") for i in range(MAX_BATCH_SIZE + 1)]
        with pytest.raises(ValueError, match="exceeds limit"):
            batch_service.submit_batch(files)

    def test_creates_parent_job(self, batch_service, db):
        files = [
            BatchFile(file_path="/tmp/inv1.pdf"),
            BatchFile(file_path="/tmp/inv2.pdf"),
        ]
        batch_id = batch_service.submit_batch(files)

        parent = db.get_job(batch_id)
        assert parent is not None
        assert parent.type == "batch_process"
        assert "2 files" in parent.file_name

    def test_creates_child_jobs(self, batch_service, db):
        files = [
            BatchFile(file_path="/tmp/inv1.pdf"),
            BatchFile(file_path="/tmp/inv2.pdf"),
            BatchFile(file_path="/tmp/inv3.pdf"),
        ]
        batch_id = batch_service.submit_batch(files)

        # Give the background thread a moment to start
        time.sleep(0.1)

        # Should have 3 child invoice_process jobs
        children = db.list_jobs(job_type="invoice_process")
        assert len(children) == 3


# ==================== PROCESS SINGLE FILE ====================


class TestProcessSingleFile:
    """Tests for individual file processing within a batch."""

    def test_successful_processing(self, batch_service, db, mock_doc_service, mock_match_service):
        """Process a single file through the full pipeline."""
        from threading import Event
        cancel_event = Event()

        job = db.create_job(job_type="invoice_process", file_name="/tmp/test.pdf")
        batch_file = BatchFile(file_path="/tmp/test.pdf", po_number="PO-001")

        batch_service._process_single_file(job.id, batch_file, cancel_event)

        # Job should be COMPLETE
        updated = db.get_job(job.id)
        assert updated.status == "COMPLETE"
        assert updated.vendor_name == "Acme Corp"

        # Result should be saved
        results = db.get_results(job_id=job.id)
        assert len(results) == 1
        assert results[0].status == "PASS"
        assert results[0].invoice_number == "INV-001"

        # Match service called with PO number
        mock_match_service.validate_three_way.assert_called_once()
        call_kwargs = mock_match_service.validate_three_way.call_args
        assert call_kwargs[1]["po_number"] == "PO-001"

    def test_processing_error_isolates_failure(self, batch_service, db, mock_doc_service):
        """A processing error should mark the job as FAILED, not crash."""
        from threading import Event
        cancel_event = Event()

        mock_doc_service.process_invoice.side_effect = Exception("Ollama timeout")

        job = db.create_job(job_type="invoice_process", file_name="/tmp/bad.pdf")
        batch_file = BatchFile(file_path="/tmp/bad.pdf")

        batch_service._process_single_file(job.id, batch_file, cancel_event)

        updated = db.get_job(job.id)
        assert updated.status == "FAILED"
        assert "Ollama timeout" in updated.error

    def test_cancel_stops_processing(self, batch_service, db):
        """Setting cancel event should stop processing early."""
        from threading import Event
        cancel_event = Event()
        cancel_event.set()  # Pre-cancel

        job = db.create_job(job_type="invoice_process", file_name="/tmp/test.pdf")
        batch_file = BatchFile(file_path="/tmp/test.pdf")

        batch_service._process_single_file(job.id, batch_file, cancel_event)

        updated = db.get_job(job.id)
        assert updated.status == "FAILED"
        assert "Cancelled" in updated.error


# ==================== BATCH STATUS ====================


class TestBatchStatus:
    """Tests for batch status reporting."""

    def test_status_not_found(self, batch_service):
        assert batch_service.get_batch_status(999) is None

    def test_status_wrong_type(self, batch_service, db):
        """Non-batch jobs should not be returned."""
        job = db.create_job(job_type="invoice_process")
        assert batch_service.get_batch_status(job.id) is None

    def test_status_tracks_progress(self, batch_service, db):
        """Status should aggregate child job states."""
        # Create batch parent
        parent = db.create_job(job_type="batch_process", file_name="3 files")
        db.update_job_status(parent.id, "PARSING")

        # Create child jobs
        child1 = db.create_job(job_type="invoice_process", file_name="inv1.pdf")
        child2 = db.create_job(job_type="invoice_process", file_name="inv2.pdf")
        child3 = db.create_job(job_type="invoice_process", file_name="inv3.pdf")

        # Simulate progress
        db.update_job_status(child1.id, "COMPLETE")
        db.update_job_status(child2.id, "FAILED", error="Parse error")
        # child3 stays PENDING

        status = batch_service.get_batch_status(parent.id)
        assert status is not None
        assert status.total_files == 3
        assert status.completed == 1
        assert status.failed == 1
        assert status.pending == 1
        assert status.processing == 0
        assert len(status.errors) == 1
        assert status.errors[0]["error"] == "Parse error"

    def test_status_with_processing_jobs(self, batch_service, db):
        """Jobs in intermediate states count as processing."""
        parent = db.create_job(job_type="batch_process", file_name="2 files")
        db.update_job_status(parent.id, "PARSING")

        child1 = db.create_job(job_type="invoice_process", file_name="inv1.pdf")
        child2 = db.create_job(job_type="invoice_process", file_name="inv2.pdf")

        db.update_job_status(child1.id, "EXTRACTING")  # In progress
        # child2 stays PENDING

        status = batch_service.get_batch_status(parent.id)
        assert status.processing == 1
        assert status.pending == 1


# ==================== CANCEL BATCH ====================


class TestCancelBatch:
    """Tests for batch cancellation."""

    def test_cancel_nonexistent_batch(self, batch_service):
        assert batch_service.cancel_batch(999) is False

    def test_cancel_finished_batch(self, batch_service, db):
        job = db.create_job(job_type="batch_process")
        db.update_job_status(job.id, "COMPLETE")
        assert batch_service.cancel_batch(job.id) is False

    def test_cancel_running_batch(self, batch_service):
        """Submit a batch, then cancel it."""
        # Slow down processing so we can cancel
        batch_service.document_service.process_invoice.side_effect = (
            lambda path: time.sleep(5)
        )

        files = [BatchFile(file_path=f"/tmp/inv{i}.pdf") for i in range(3)]
        batch_id = batch_service.submit_batch(files)

        # Small delay to let the batch start
        time.sleep(0.2)

        result = batch_service.cancel_batch(batch_id)
        assert result is True


# ==================== INTEGRATION ====================


class TestBatchIntegration:
    """Integration tests for full batch processing flow."""

    def test_full_batch_completes(self, batch_service, db):
        """Submit batch, wait for completion, verify results."""
        files = [
            BatchFile(file_path="/tmp/inv1.pdf", po_number="PO-001"),
            BatchFile(file_path="/tmp/inv2.pdf"),
        ]

        batch_id = batch_service.submit_batch(files)

        # Wait for completion (with timeout)
        for _ in range(50):
            status = batch_service.get_batch_status(batch_id)
            if status and status.status in ("COMPLETE", "FAILED"):
                break
            time.sleep(0.1)

        status = batch_service.get_batch_status(batch_id)
        assert status is not None
        assert status.status == "COMPLETE"
        assert status.completed == 2
        assert status.failed == 0

        # Results should be saved
        results = db.get_results()
        assert len(results) == 2

    def test_partial_failure_batch(self, batch_service, db, mock_doc_service):
        """One file failing should not affect others."""
        call_count = 0

        def process_with_failure(path):
            nonlocal call_count
            call_count += 1
            if "bad" in path:
                raise Exception("Corrupt PDF")
            return mock_doc_service.process_invoice.return_value

        mock_doc_service.process_invoice.side_effect = process_with_failure

        files = [
            BatchFile(file_path="/tmp/good1.pdf"),
            BatchFile(file_path="/tmp/bad.pdf"),
            BatchFile(file_path="/tmp/good2.pdf"),
        ]

        batch_id = batch_service.submit_batch(files)

        # Wait for completion
        for _ in range(50):
            status = batch_service.get_batch_status(batch_id)
            if status and status.status in ("COMPLETE", "FAILED"):
                break
            time.sleep(0.1)

        status = batch_service.get_batch_status(batch_id)
        assert status is not None
        assert status.completed == 2
        assert status.failed == 1
        assert status.status == "COMPLETE"  # Partial success = COMPLETE
        assert len(status.errors) == 1
        assert "Corrupt PDF" in status.errors[0]["error"]
