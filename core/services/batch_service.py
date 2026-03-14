"""
Batch Processing Service for DocuMatch Architect.

Processes multiple invoices concurrently using ThreadPoolExecutor,
tracking per-file state in SQLite.

Job State Machine (per file):
    PENDING ──▶ PARSING ──▶ EXTRACTING ──▶ MATCHING ──▶ COMPLETE
       │           │            │              │
       └───────────┴────────────┴──────────────┴──▶ FAILED

Processing Pipeline:
    ┌────────────────┐
    │  Batch Request  │  (list of file paths + optional PO numbers)
    │  max 100 files  │
    └───────┬────────┘
            ▼
    ┌────────────────┐
    │ Create parent   │  batch_process job in SQLite
    │ job (PENDING)   │
    └───────┬────────┘
            ▼
    ┌────────────────────────────────────┐
    │ ThreadPoolExecutor (max_workers=3) │
    │                                    │
    │  ┌──────┐ ┌──────┐ ┌──────┐       │
    │  │File 1│ │File 2│ │File 3│  ...   │  Each file = child job
    │  │PARSE │ │PARSE │ │PARSE │       │  State tracked in SQLite
    │  │EXTR. │ │EXTR. │ │EXTR. │       │  Errors isolated per-file
    │  │MATCH │ │MATCH │ │MATCH │       │
    │  └──────┘ └──────┘ └──────┘       │
    └───────────────┬────────────────────┘
                    ▼
    ┌────────────────┐
    │ Parent job      │
    │ COMPLETE/FAILED │
    └────────────────┘
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import Event
from typing import Optional

from ..database import Database
from .document_service import DocumentService, DocumentProcessingError
from .match_service import MatchService

logger = logging.getLogger(__name__)

# Limits
MAX_BATCH_SIZE = 100
DEFAULT_MAX_WORKERS = 3


@dataclass
class BatchFile:
    """A single file in a batch processing request."""

    file_path: str
    po_number: Optional[str] = None


@dataclass
class BatchStatus:
    """Status snapshot of a batch job."""

    job_id: int
    status: str
    total_files: int
    completed: int
    failed: int
    pending: int
    processing: int
    eta_seconds: Optional[float] = None
    errors: list[dict] = field(default_factory=list)


class BatchService:
    """
    Orchestrates batch invoice processing with concurrent execution.

    Uses ThreadPoolExecutor for parallelism and SQLite for state tracking.
    Each file is processed independently -- one failure does not affect others.

    Usage:
        service = BatchService(doc_service, match_service, db)
        batch_id = service.submit_batch(files)
        status = service.get_batch_status(batch_id)
        service.cancel_batch(batch_id)
    """

    def __init__(
        self,
        document_service: DocumentService,
        match_service: MatchService,
        database: Database,
        max_workers: int = DEFAULT_MAX_WORKERS,
    ):
        self.document_service = document_service
        self.match_service = match_service
        self.database = database
        self.max_workers = max_workers
        self._cancel_events: dict[int, Event] = {}

    def submit_batch(self, files: list[BatchFile]) -> int:
        """
        Submit a batch of invoice files for processing.

        Creates a parent job and spawns worker threads for each file.
        Returns immediately with the batch job ID for status polling.

        Args:
            files: List of BatchFile with file_path and optional po_number

        Returns:
            Batch job ID for status polling

        Raises:
            ValueError: If batch exceeds MAX_BATCH_SIZE or is empty
        """
        if not files:
            raise ValueError("Batch cannot be empty")
        if len(files) > MAX_BATCH_SIZE:
            raise ValueError(
                f"Batch size {len(files)} exceeds limit of {MAX_BATCH_SIZE}"
            )

        # Create parent batch job
        parent_job = self.database.create_job(
            job_type="batch_process",
            file_name=f"{len(files)} files",
        )
        parent_id = parent_job.id
        self.database.update_job_status(parent_id, "PARSING")

        # Create cancel event for this batch
        cancel_event = Event()
        self._cancel_events[parent_id] = cancel_event

        # Create child jobs for each file
        child_ids = []
        for batch_file in files:
            child_job = self.database.create_job(
                job_type="invoice_process",
                file_name=batch_file.file_path,
                vendor_name=None,  # Will be extracted
            )
            child_ids.append((child_job.id, batch_file))

        # Submit to thread pool (fire and forget)
        executor = ThreadPoolExecutor(
            max_workers=self.max_workers,
            thread_name_prefix=f"batch-{parent_id}",
        )

        def run_batch():
            try:
                self._execute_batch(parent_id, child_ids, cancel_event, executor)
            finally:
                executor.shutdown(wait=False)
                self._cancel_events.pop(parent_id, None)

        # Run the batch orchestrator in a separate thread
        import threading
        thread = threading.Thread(target=run_batch, daemon=True)
        thread.start()

        logger.info(f"Batch {parent_id} submitted: {len(files)} files")
        return parent_id

    def _execute_batch(
        self,
        parent_id: int,
        child_ids: list[tuple[int, BatchFile]],
        cancel_event: Event,
        executor: ThreadPoolExecutor,
    ):
        """Execute the batch using ThreadPoolExecutor."""
        start_time = time.monotonic()
        completed_times: list[float] = []

        futures = {}
        for child_id, batch_file in child_ids:
            if cancel_event.is_set():
                break
            future = executor.submit(
                self._process_single_file,
                child_id,
                batch_file,
                cancel_event,
            )
            futures[future] = (child_id, batch_file)

        # Wait for all futures
        for future in as_completed(futures):
            child_id, batch_file = futures[future]
            try:
                future.result()
                elapsed = time.monotonic() - start_time
                completed_times.append(elapsed)
            except Exception as e:
                logger.error(
                    f"Batch {parent_id}: unexpected error for "
                    f"{batch_file.file_path}: {e}"
                )

        # Finalize parent job
        if cancel_event.is_set():
            self.database.update_job_status(parent_id, "FAILED", error="Cancelled")
        else:
            # Check if all children completed
            child_jobs = [cid for cid, _ in child_ids]
            all_failed = all(
                self.database.get_job(cid).status == "FAILED"
                for cid in child_jobs
            )
            if all_failed:
                self.database.update_job_status(
                    parent_id, "FAILED", error="All files failed"
                )
            else:
                self.database.update_job_status(parent_id, "COMPLETE")

        logger.info(f"Batch {parent_id} finished")

    def _process_single_file(
        self,
        job_id: int,
        batch_file: BatchFile,
        cancel_event: Event,
    ):
        """
        Process a single invoice file through the full pipeline.

        State machine: PENDING → PARSING → EXTRACTING → MATCHING → COMPLETE/FAILED
        Each transition is persisted to SQLite.
        """
        file_path = batch_file.file_path

        try:
            # PARSING
            if cancel_event.is_set():
                self.database.update_job_status(job_id, "FAILED", error="Cancelled")
                return
            self.database.update_job_status(job_id, "PARSING")

            # EXTRACTING
            if cancel_event.is_set():
                self.database.update_job_status(job_id, "FAILED", error="Cancelled")
                return
            self.database.update_job_status(job_id, "EXTRACTING")

            invoice, parse_result = self.document_service.process_invoice(file_path)

            # Update job with extracted vendor
            with self.database.session() as session:
                from ..database import Job
                job = session.get(Job, job_id)
                if job:
                    job.vendor_name = invoice.vendor_name
                    session.commit()

            # MATCHING
            if cancel_event.is_set():
                self.database.update_job_status(job_id, "FAILED", error="Cancelled")
                return
            self.database.update_job_status(job_id, "MATCHING")

            result = self.match_service.validate_three_way(
                invoice, po_number=batch_file.po_number
            )

            # Save result to database
            self.database.save_result(
                job_id=job_id,
                invoice_file=file_path,
                vendor_name=invoice.vendor_name,
                invoice_number=invoice.invoice_number,
                status=result.status,
                confidence=result.overall_score,
                matches_passed=result.matches_passed,
                total_matches=result.total_matches,
                details={
                    "total_amount": invoice.total_amount,
                    "po_number": batch_file.po_number,
                    "issues_count": len(result.all_issues),
                },
            )

            # COMPLETE
            self.database.update_job_status(job_id, "COMPLETE")
            logger.info(f"Job {job_id}: {file_path} -> {result.status}")

        except (DocumentProcessingError, Exception) as e:
            error_msg = f"{type(e).__name__}: {str(e)}"
            self.database.update_job_status(job_id, "FAILED", error=error_msg)
            logger.error(f"Job {job_id}: {file_path} -> FAILED: {error_msg}")

    def get_batch_status(self, batch_id: int) -> Optional[BatchStatus]:
        """
        Get the current status of a batch job.

        Aggregates child job statuses and estimates ETA based on
        average processing time of completed files.

        Args:
            batch_id: The parent batch job ID

        Returns:
            BatchStatus snapshot, or None if batch not found
        """
        parent = self.database.get_job(batch_id)
        if not parent or parent.type != "batch_process":
            return None

        # Get all child jobs for this batch
        # Child jobs are invoice_process jobs created right after the batch job
        with self.database.session() as session:
            from ..database import Job
            children = (
                session.query(Job)
                .filter(
                    Job.type == "invoice_process",
                    Job.id > batch_id,
                )
                .order_by(Job.id)
                .all()
            )

            # Find children that belong to this batch
            # (created between this batch and the next batch or end)
            next_batch = (
                session.query(Job)
                .filter(Job.type == "batch_process", Job.id > batch_id)
                .order_by(Job.id)
                .first()
            )
            max_child_id = next_batch.id if next_batch else float("inf")
            batch_children = [c for c in children if c.id < max_child_id]

        total = len(batch_children)
        completed = sum(1 for c in batch_children if c.status == "COMPLETE")
        failed = sum(1 for c in batch_children if c.status == "FAILED")
        pending = sum(
            1 for c in batch_children if c.status == "PENDING"
        )
        processing = total - completed - failed - pending

        # Calculate ETA from completed jobs
        eta = None
        if completed > 0 and (pending + processing) > 0:
            completed_jobs = [
                c for c in batch_children
                if c.status == "COMPLETE" and c.completed_at and c.created_at
            ]
            if completed_jobs:
                total_time = sum(
                    (c.completed_at - c.created_at).total_seconds()
                    for c in completed_jobs
                )
                avg_time = total_time / len(completed_jobs)
                remaining = pending + processing
                eta = avg_time * remaining

        # Collect errors
        errors = [
            {"file": c.file_name, "error": c.error}
            for c in batch_children
            if c.status == "FAILED" and c.error
        ]

        return BatchStatus(
            job_id=batch_id,
            status=parent.status,
            total_files=total,
            completed=completed,
            failed=failed,
            pending=pending,
            processing=processing,
            eta_seconds=eta,
            errors=errors,
        )

    def cancel_batch(self, batch_id: int) -> bool:
        """
        Cancel a running batch job.

        Sets the cancel event so worker threads stop picking up new work.
        Already-running files will complete, but no new files will start.

        Args:
            batch_id: The parent batch job ID

        Returns:
            True if cancellation was signaled, False if batch not found
        """
        cancel_event = self._cancel_events.get(batch_id)
        if cancel_event:
            cancel_event.set()
            logger.info(f"Batch {batch_id}: cancellation requested")
            return True

        # Batch may have already finished
        parent = self.database.get_job(batch_id)
        if parent and parent.status in ("COMPLETE", "FAILED"):
            return False

        return False
