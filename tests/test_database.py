"""
Tests for SQLite Metadata Store.

Tests all database operations: jobs, results, audit log, and stats.
Uses temp directories so each test gets a fresh database.
"""

import json
import pytest
from pathlib import Path

from core.database import AuditLog, Base, Database, Job, Result


# ==================== FIXTURES ====================


@pytest.fixture
def db(tmp_path):
    """Create a fresh database for each test."""
    db_path = str(tmp_path / "test.db")
    return Database(db_path)


# ==================== DATABASE INIT ====================


class TestDatabaseInit:
    """Tests for database initialization."""

    def test_creates_db_file(self, tmp_path):
        db_path = str(tmp_path / "new.db")
        db = Database(db_path)
        assert Path(db_path).exists()

    def test_creates_parent_directories(self, tmp_path):
        db_path = str(tmp_path / "nested" / "dir" / "test.db")
        db = Database(db_path)
        assert Path(db_path).exists()

    def test_wal_mode_enabled(self, db):
        """Verify WAL mode is active for concurrent access."""
        with db.engine.connect() as conn:
            result = conn.execute(
                __import__("sqlalchemy").text("PRAGMA journal_mode")
            )
            mode = result.scalar()
            assert mode == "wal"

    def test_tables_created(self, db):
        """All three tables should exist."""
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        assert "jobs" in tables
        assert "results" in tables
        assert "audit_log" in tables


# ==================== JOB OPERATIONS ====================


class TestJobOperations:
    """Tests for job CRUD operations."""

    def test_create_job(self, db):
        job = db.create_job(
            job_type="invoice_process",
            file_name="invoice.pdf",
            vendor_name="Acme Corp",
        )

        assert job.id is not None
        assert job.type == "invoice_process"
        assert job.status == "PENDING"
        assert job.file_name == "invoice.pdf"
        assert job.vendor_name == "Acme Corp"
        assert job.created_at is not None
        assert job.completed_at is None
        assert job.error is None

    def test_create_job_minimal(self, db):
        """Job with only required fields."""
        job = db.create_job(job_type="contract_ingest")
        assert job.id is not None
        assert job.file_name is None
        assert job.vendor_name is None

    def test_update_job_status(self, db):
        job = db.create_job(job_type="invoice_process")
        updated = db.update_job_status(job.id, "PARSING")

        assert updated.status == "PARSING"
        assert updated.completed_at is None

    def test_update_job_to_complete(self, db):
        job = db.create_job(job_type="invoice_process")
        updated = db.update_job_status(job.id, "COMPLETE")

        assert updated.status == "COMPLETE"
        assert updated.completed_at is not None

    def test_update_job_to_failed(self, db):
        job = db.create_job(job_type="invoice_process")
        updated = db.update_job_status(job.id, "FAILED", error="Ollama timeout")

        assert updated.status == "FAILED"
        assert updated.error == "Ollama timeout"
        assert updated.completed_at is not None

    def test_update_nonexistent_job(self, db):
        result = db.update_job_status(999, "COMPLETE")
        assert result is None

    def test_get_job(self, db):
        created = db.create_job(job_type="po_ingest", file_name="po.pdf")
        fetched = db.get_job(created.id)

        assert fetched is not None
        assert fetched.type == "po_ingest"
        assert fetched.file_name == "po.pdf"

    def test_get_nonexistent_job(self, db):
        assert db.get_job(999) is None

    def test_list_jobs(self, db):
        db.create_job(job_type="contract_ingest")
        db.create_job(job_type="invoice_process")
        db.create_job(job_type="invoice_process")

        all_jobs = db.list_jobs()
        assert len(all_jobs) == 3

    def test_list_jobs_filter_by_type(self, db):
        db.create_job(job_type="contract_ingest")
        db.create_job(job_type="invoice_process")
        db.create_job(job_type="invoice_process")

        invoice_jobs = db.list_jobs(job_type="invoice_process")
        assert len(invoice_jobs) == 2

    def test_list_jobs_filter_by_status(self, db):
        job1 = db.create_job(job_type="invoice_process")
        job2 = db.create_job(job_type="invoice_process")
        db.update_job_status(job1.id, "COMPLETE")

        pending = db.list_jobs(status="PENDING")
        assert len(pending) == 1

    def test_list_jobs_limit(self, db):
        for i in range(10):
            db.create_job(job_type="invoice_process")

        limited = db.list_jobs(limit=3)
        assert len(limited) == 3

    def test_list_jobs_ordered_by_created_desc(self, db):
        job1 = db.create_job(job_type="invoice_process", file_name="first.pdf")
        job2 = db.create_job(job_type="invoice_process", file_name="second.pdf")

        jobs = db.list_jobs()
        # Most recent first
        assert jobs[0].file_name == "second.pdf"
        assert jobs[1].file_name == "first.pdf"


# ==================== RESULT OPERATIONS ====================


class TestResultOperations:
    """Tests for validation result storage."""

    def test_save_result(self, db):
        job = db.create_job(job_type="invoice_process")
        result = db.save_result(
            job_id=job.id,
            invoice_file="invoice.pdf",
            vendor_name="Acme Corp",
            invoice_number="INV-001",
            status="PASS",
            confidence=0.95,
            matches_passed=3,
            total_matches=3,
            details={"test": "data"},
        )

        assert result.id is not None
        assert result.job_id == job.id
        assert result.status == "PASS"
        assert result.confidence == 0.95
        assert result.matches_passed == 3

    def test_result_details_json(self, db):
        job = db.create_job(job_type="invoice_process")
        details = {"issues": [{"rule": "rate", "severity": "critical"}]}
        result = db.save_result(job_id=job.id, details=details)

        assert result.details_json is not None
        parsed = json.loads(result.details_json)
        assert parsed["issues"][0]["rule"] == "rate"

    def test_result_details_property(self, db):
        job = db.create_job(job_type="invoice_process")
        result = db.save_result(
            job_id=job.id,
            details={"key": "value"},
        )

        assert result.details == {"key": "value"}

    def test_result_details_none(self, db):
        job = db.create_job(job_type="invoice_process")
        result = db.save_result(job_id=job.id)

        assert result.details is None

    def test_get_results_by_job(self, db):
        job1 = db.create_job(job_type="invoice_process")
        job2 = db.create_job(job_type="invoice_process")
        db.save_result(job_id=job1.id, invoice_number="INV-001")
        db.save_result(job_id=job1.id, invoice_number="INV-002")
        db.save_result(job_id=job2.id, invoice_number="INV-003")

        job1_results = db.get_results(job_id=job1.id)
        assert len(job1_results) == 2

    def test_get_results_by_vendor(self, db):
        job = db.create_job(job_type="invoice_process")
        db.save_result(job_id=job.id, vendor_name="Acme", invoice_number="INV-001")
        db.save_result(job_id=job.id, vendor_name="Globex", invoice_number="INV-002")

        acme_results = db.get_results(vendor_name="Acme")
        assert len(acme_results) == 1
        assert acme_results[0].vendor_name == "Acme"

    def test_get_results_by_status(self, db):
        job = db.create_job(job_type="invoice_process")
        db.save_result(job_id=job.id, status="PASS")
        db.save_result(job_id=job.id, status="FAIL")
        db.save_result(job_id=job.id, status="PASS")

        passed = db.get_results(status="PASS")
        assert len(passed) == 2

    def test_job_result_cascade_delete(self, db):
        """Deleting a job should delete its results."""
        job = db.create_job(job_type="invoice_process")
        db.save_result(job_id=job.id, invoice_number="INV-001")
        db.save_result(job_id=job.id, invoice_number="INV-002")

        with db.session() as session:
            job_obj = session.get(Job, job.id)
            session.delete(job_obj)
            session.commit()

        assert db.get_results(job_id=job.id) == []


# ==================== AUDIT LOG ====================


class TestAuditLog:
    """Tests for audit trail."""

    def test_job_creation_audited(self, db):
        db.create_job(job_type="contract_ingest", file_name="contract.pdf")

        logs = db.get_audit_log()
        assert len(logs) >= 1
        assert any(log.action == "job_created" for log in logs)

    def test_status_change_audited(self, db):
        job = db.create_job(job_type="invoice_process")
        db.update_job_status(job.id, "PARSING")

        logs = db.get_audit_log(entity_type="job")
        status_logs = [l for l in logs if l.action == "job_status_changed"]
        assert len(status_logs) == 1

        metadata = json.loads(status_logs[0].extra_data)
        assert metadata["new_status"] == "PARSING"

    def test_result_save_audited(self, db):
        job = db.create_job(job_type="invoice_process")
        db.save_result(job_id=job.id, invoice_number="INV-001", status="PASS")

        logs = db.get_audit_log(entity_type="result")
        assert len(logs) >= 1
        assert any(log.action == "result_saved" for log in logs)

    def test_audit_log_filter_by_entity_type(self, db):
        job = db.create_job(job_type="invoice_process")
        db.save_result(job_id=job.id, status="PASS")

        job_logs = db.get_audit_log(entity_type="job")
        result_logs = db.get_audit_log(entity_type="result")

        # Job logs: job_created + job event for the create
        # Result logs: result_saved
        assert all(log.entity_type == "job" for log in job_logs)
        assert all(log.entity_type == "result" for log in result_logs)

    def test_audit_log_limit(self, db):
        for _ in range(10):
            db.create_job(job_type="invoice_process")

        limited = db.get_audit_log(limit=3)
        assert len(limited) == 3


# ==================== STATS ====================


class TestStats:
    """Tests for aggregate statistics."""

    def test_empty_stats(self, db):
        stats = db.get_stats()
        assert stats["total_jobs"] == 0
        assert stats["total_results"] == 0
        assert stats["pass_rate"] == 0.0

    def test_stats_with_data(self, db):
        # Create some jobs
        job1 = db.create_job(job_type="invoice_process")
        job2 = db.create_job(job_type="invoice_process")
        job3 = db.create_job(job_type="invoice_process")

        db.update_job_status(job1.id, "COMPLETE")
        db.update_job_status(job2.id, "COMPLETE")
        db.update_job_status(job3.id, "FAILED", error="timeout")

        # Create some results
        db.save_result(job_id=job1.id, status="PASS")
        db.save_result(job_id=job1.id, status="PASS")
        db.save_result(job_id=job2.id, status="FAIL")
        db.save_result(job_id=job2.id, status="REVIEW")

        stats = db.get_stats()
        assert stats["total_jobs"] == 3
        assert stats["completed_jobs"] == 2
        assert stats["failed_jobs"] == 1
        assert stats["pending_jobs"] == 0
        assert stats["total_results"] == 4
        assert stats["pass_count"] == 2
        assert stats["fail_count"] == 1
        assert stats["review_count"] == 1
        assert stats["pass_rate"] == 0.5

    def test_pass_rate_calculation(self, db):
        job = db.create_job(job_type="invoice_process")
        db.save_result(job_id=job.id, status="PASS")
        db.save_result(job_id=job.id, status="PASS")
        db.save_result(job_id=job.id, status="PASS")
        db.save_result(job_id=job.id, status="FAIL")

        stats = db.get_stats()
        assert stats["pass_rate"] == 0.75


# ==================== CONCURRENCY ====================


class TestConcurrency:
    """Tests for concurrent access patterns."""

    def test_multiple_sessions(self, db):
        """Multiple sessions should work without conflicts (WAL mode)."""
        job = db.create_job(job_type="invoice_process")

        # Read from one session while writing from another
        with db.session() as s1:
            j1 = s1.get(Job, job.id)
            assert j1.status == "PENDING"

        db.update_job_status(job.id, "COMPLETE")

        with db.session() as s2:
            j2 = s2.get(Job, job.id)
            assert j2.status == "COMPLETE"
