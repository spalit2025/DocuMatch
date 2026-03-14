"""
SQLite Metadata Store for DocuMatch Architect.

Provides persistent storage for jobs, validation results, and audit logs.
Uses SQLAlchemy ORM with SQLite backend and WAL mode for concurrent access.

Tables:
    ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐
    │    jobs       │     │    results        │     │  audit_log   │
    ├──────────────┤     ├──────────────────┤     ├──────────────┤
    │ id (PK)      │──┐  │ id (PK)          │     │ id (PK)      │
    │ type         │  └─▶│ job_id (FK)       │     │ action       │
    │ status       │     │ invoice_file      │     │ entity_type  │
    │ file_name    │     │ vendor_name       │     │ entity_id    │
    │ vendor_name  │     │ invoice_number    │     │ timestamp    │
    │ created_at   │     │ status            │     │ metadata_json│
    │ completed_at │     │ confidence        │     └──────────────┘
    │ error        │     │ details_json      │
    └──────────────┘     │ created_at        │
                         └──────────────────┘

Job State Machine:
    PENDING ──▶ PARSING ──▶ EXTRACTING ──▶ MATCHING ──▶ COMPLETE
       │           │            │              │
       └───────────┴────────────┴──────────────┴──▶ FAILED
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

logger = logging.getLogger(__name__)

# Valid job statuses
JOB_STATUSES = ("PENDING", "PARSING", "EXTRACTING", "MATCHING", "COMPLETE", "FAILED")

# Valid job types
JOB_TYPES = ("contract_ingest", "po_ingest", "invoice_process", "batch_process")


# ==================== ORM MODELS ====================


class Base(DeclarativeBase):
    pass


class Job(Base):
    """Tracks processing jobs (contract ingestion, PO processing, invoice validation)."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    file_name = Column(String(255), nullable=True)
    vendor_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)

    # Relationship to results
    results = relationship("Result", back_populates="job", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Job(id={self.id}, type={self.type}, status={self.status})>"


class Result(Base):
    """Stores validation results for processed invoices."""

    __tablename__ = "results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    invoice_file = Column(String(255), nullable=True)
    vendor_name = Column(String(255), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    status = Column(String(20), nullable=True)  # PASS, FAIL, REVIEW
    confidence = Column(Float, nullable=True)
    matches_passed = Column(Integer, nullable=True)
    total_matches = Column(Integer, nullable=True)
    details_json = Column(Text, nullable=True)  # Full result as JSON
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship to job
    job = relationship("Job", back_populates="results")

    @property
    def details(self) -> Optional[dict]:
        """Parse details_json into a dict."""
        if self.details_json:
            return json.loads(self.details_json)
        return None

    @details.setter
    def details(self, value: dict):
        """Serialize dict to details_json."""
        self.details_json = json.dumps(value) if value else None

    def __repr__(self):
        return f"<Result(id={self.id}, invoice={self.invoice_number}, status={self.status})>"


class AuditLog(Base):
    """Audit trail for significant system actions."""

    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)  # contract, po, invoice, job
    entity_id = Column(String(100), nullable=True)
    timestamp = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    extra_data = Column("metadata_json", Text, nullable=True)

    @property
    def audit_metadata(self) -> Optional[dict]:
        """Parse extra_data JSON into a dict."""
        if self.extra_data:
            return json.loads(self.extra_data)
        return None

    def __repr__(self):
        return f"<AuditLog(id={self.id}, action={self.action})>"


# ==================== DATABASE MANAGER ====================


class Database:
    """
    Manages SQLite database connection and session lifecycle.

    Uses WAL mode for concurrent read/write access from
    both Streamlit and FastAPI processes.

    Usage:
        db = Database("./data/documatch.db")
        with db.session() as session:
            job = Job(type="invoice_process", status="PENDING")
            session.add(job)
            session.commit()
    """

    def __init__(self, db_path: str = "./data/documatch.db"):
        self.db_path = db_path

        # Ensure parent directory exists
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # Create engine with SQLite-specific settings
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        # Enable WAL mode for concurrent access
        @event.listens_for(self.engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        # Create session factory (expire_on_commit=False so returned objects
        # remain usable after session close)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

        # Create tables
        Base.metadata.create_all(self.engine)

        logger.info(f"Database initialized at {db_path} (WAL mode)")

    def session(self) -> Session:
        """Create a new database session. Use with context manager."""
        return self.SessionLocal()

    # ==================== JOB OPERATIONS ====================

    def create_job(
        self,
        job_type: str,
        file_name: Optional[str] = None,
        vendor_name: Optional[str] = None,
    ) -> Job:
        """Create a new processing job."""
        with self.session() as session:
            job = Job(
                type=job_type,
                status="PENDING",
                file_name=file_name,
                vendor_name=vendor_name,
            )
            session.add(job)
            session.commit()
            session.refresh(job)
            job_id = job.id

            # Audit log
            self._audit(session, "job_created", "job", str(job_id), {
                "type": job_type, "file_name": file_name,
            })
            session.commit()

            logger.info(f"Created job {job_id}: type={job_type}")
            return job

    def update_job_status(
        self,
        job_id: int,
        status: str,
        error: Optional[str] = None,
    ) -> Optional[Job]:
        """Update a job's status. Sets completed_at for terminal states."""
        with self.session() as session:
            job = session.get(Job, job_id)
            if not job:
                return None

            job.status = status
            if error:
                job.error = error
            if status in ("COMPLETE", "FAILED"):
                job.completed_at = datetime.now(timezone.utc)

            self._audit(session, "job_status_changed", "job", str(job_id), {
                "new_status": status, "error": error,
            })
            session.commit()
            session.refresh(job)

            return job

    def get_job(self, job_id: int) -> Optional[Job]:
        """Get a job by ID."""
        with self.session() as session:
            return session.get(Job, job_id)

    def list_jobs(
        self,
        job_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[Job]:
        """List jobs with optional filters."""
        with self.session() as session:
            query = session.query(Job)
            if job_type:
                query = query.filter(Job.type == job_type)
            if status:
                query = query.filter(Job.status == status)
            return query.order_by(Job.created_at.desc()).limit(limit).all()

    # ==================== RESULT OPERATIONS ====================

    def save_result(
        self,
        job_id: int,
        invoice_file: Optional[str] = None,
        vendor_name: Optional[str] = None,
        invoice_number: Optional[str] = None,
        status: Optional[str] = None,
        confidence: Optional[float] = None,
        matches_passed: Optional[int] = None,
        total_matches: Optional[int] = None,
        details: Optional[dict] = None,
    ) -> Result:
        """Save a validation result linked to a job."""
        with self.session() as session:
            result = Result(
                job_id=job_id,
                invoice_file=invoice_file,
                vendor_name=vendor_name,
                invoice_number=invoice_number,
                status=status,
                confidence=confidence,
                matches_passed=matches_passed,
                total_matches=total_matches,
                details_json=json.dumps(details) if details else None,
            )
            session.add(result)

            self._audit(session, "result_saved", "result", invoice_number, {
                "job_id": job_id, "status": status,
            })
            session.commit()
            session.refresh(result)

            return result

    def get_results(
        self,
        job_id: Optional[int] = None,
        vendor_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> list[Result]:
        """Query results with optional filters."""
        with self.session() as session:
            query = session.query(Result)
            if job_id:
                query = query.filter(Result.job_id == job_id)
            if vendor_name:
                query = query.filter(Result.vendor_name == vendor_name)
            if status:
                query = query.filter(Result.status == status)
            return query.order_by(Result.created_at.desc()).limit(limit).all()

    # ==================== AUDIT OPERATIONS ====================

    def _audit(
        self,
        session: Session,
        action: str,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """Add an audit log entry (called within an existing session)."""
        log = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            extra_data=json.dumps(metadata) if metadata else None,
        )
        session.add(log)

    def get_audit_log(
        self,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """Query audit log entries."""
        with self.session() as session:
            query = session.query(AuditLog)
            if entity_type:
                query = query.filter(AuditLog.entity_type == entity_type)
            return query.order_by(AuditLog.timestamp.desc()).limit(limit).all()

    # ==================== STATS ====================

    def get_stats(self) -> dict:
        """Get aggregate statistics for the dashboard."""
        with self.session() as session:
            total_jobs = session.query(Job).count()
            completed_jobs = session.query(Job).filter(Job.status == "COMPLETE").count()
            failed_jobs = session.query(Job).filter(Job.status == "FAILED").count()
            pending_jobs = session.query(Job).filter(
                Job.status.in_(("PENDING", "PARSING", "EXTRACTING", "MATCHING"))
            ).count()

            total_results = session.query(Result).count()
            pass_count = session.query(Result).filter(Result.status == "PASS").count()
            fail_count = session.query(Result).filter(Result.status == "FAIL").count()
            review_count = session.query(Result).filter(Result.status == "REVIEW").count()

            return {
                "total_jobs": total_jobs,
                "completed_jobs": completed_jobs,
                "failed_jobs": failed_jobs,
                "pending_jobs": pending_jobs,
                "total_results": total_results,
                "pass_count": pass_count,
                "fail_count": fail_count,
                "review_count": review_count,
                "pass_rate": pass_count / total_results if total_results > 0 else 0.0,
            }
