# TODOS.md - DocuMatch Architect Expansion Plan

Generated from CEO-level plan review (SCOPE EXPANSION mode).
Refined via engineering review (BIG CHANGE mode).
Primary objective: Portfolio-grade AI-native product + SaaS exploration.

---

## Phase 1: Foundation (P1 - Do First)

### 1.1 Error Hardening Pass ✅ DONE
- [x] Enforce max file size check in parser_engine.py (prevent MemoryError)
- [x] Introduce `StoreError` exception class in core/exceptions.py
- [x] In vector_store.py and po_store.py: raise `StoreError` on ChromaDB connection/infra errors, return None/[] only for "not found"
- [x] Guard against empty text indexing in vector_store.py (already existed)
- [x] Guard against ZeroDivisionError in matcher.py tolerance calculations (quantity=0, unit_price=0)
- [x] Add model existence check in extraction.py (lazy verify on first use)
- [x] Add embedding model availability check in vector_store.py (StoreError on collection init failure)
- **Pattern:** Distinguish infrastructure errors (raise) from business-logic not-found (return None/[]). Callers must handle both.
- **Effort:** S (2 hours)
- **Why:** Silent crashes are unacceptable in a portfolio project. Shows defensive engineering.

### 1.2 Extraction Engine DRY Refactor ✅ DONE
- [x] Create generic `_extract_with_retry(document_text, system_prompt, user_prompt, retry_prompt, validator_fn)` method
- [x] Refactor `extract_invoice_data` and `extract_po_data` to call the generic method (~120 lines of duplication removed)
- [x] Extract shared `_parse_line_items(data)` helper from `_validate_invoice` and `_validate_po`
- [x] Unified `_call_ollama` method replaces 4 separate call methods
- **Effort:** S (1-2 hours)
- **Why:** DRY is non-negotiable. Both methods share identical retry loops, truncation, and error handling. Must be done before prompt template extraction.

### 1.3 Matcher Partial Decomposition ✅ DONE
- [x] Extract `report_generator.py` from matcher.py (166 lines, two report functions)
- [x] Fix DRY violation: `validate_invoice` now uses `_get_all_contract_clauses` instead of duplicated retrieval logic
- [x] Matcher delegates to `report_generator.generate_report()` and `generate_three_way_report()`
- [x] Fixed pre-existing test bug in test_three_way_match.py (wrong assertion string)
- [x] matcher.py reduced from 1,135 to 961 lines
- **Note:** Full validator extraction (rate_validator, date_validator, etc.) deferred to Phase 2 alongside service layer
- **Effort:** S (2 hours)
- **Why:** Gets matcher.py from 1,135 to ~540 lines. Eliminates the biggest code smell without double-touching files.

### 1.4 Prompt Template System ✅ DONE
- [x] Create `prompts/` directory
- [x] Move invoice extraction prompts to `prompts/extract_invoice_{system,user,retry}.txt`
- [x] Move PO extraction prompts to `prompts/extract_po_{system,user,retry}.txt`
- [x] Move rate comparison prompt to `prompts/rate_comparison.txt`
- [x] Update ExtractionEngine to load templates at runtime with caching
- [ ] Add prompt versioning (v1, v2, etc.) for A/B testing (deferred to Phase 4)
- **Effort:** S (2 hours)
- **Why:** Prompts as first-class engineering artifacts signals AI-native product thinking.
- **Depends on:** 1.2 (extraction DRY refactor makes this cleaner)

---

## Phase 2: Architecture (P1 - Core Features)

### 2.1 Service Layer ✅ DONE
- [x] Create `core/services/` package
- [x] `DocumentService` - orchestrates all document ingestion (contracts, POs, invoices): parse -> extract -> store
- [x] `MatchService` - orchestrates validation, matching, and batch processing
- [x] Both Streamlit and FastAPI consume the service layer
- [ ] Extract remaining matcher validators (rate_validator, date_validator, terms_validator, line_item_validator) into `core/validators/` (deferred to Phase 2.4)
- **Architecture:** 2 services, not 4. Constructor injection for testability. Streamlit pages continue using core modules directly for step-by-step UX; services provide one-shot orchestration for FastAPI/batch.
- **Effort:** M (4-6 hours)
- **Why:** Decouples business logic from presentation. Enables API + UI from same codebase.

### 2.2 FastAPI Layer ✅ DONE (core endpoints)
- [x] Create `api/` package with FastAPI app
- [x] POST /api/contracts/ingest - upload and index contract
- [x] POST /api/pos/ingest - upload and index PO
- [x] POST /api/invoices/process - upload, extract, and match invoice
- [ ] POST /api/batch/process - batch process multiple invoices (deferred to 2.4)
- [ ] GET /api/batch/{job_id}/status - check batch job status (deferred to 2.4)
- [ ] GET /api/results - query match results (deferred to 2.3)
- [x] GET /api/health - system health check
- [x] OpenAPI docs with examples and descriptions (auto-generated at /docs and /redoc)
- [x] Exception handlers: 422 (DocumentProcessingError), 502 (ExtractionError), 503 (StoreError)
- [x] 17 API tests with mocked services
- **Deployment:** Runs as separate process from Streamlit (port 8000 vs 8501). Both share data directory.
- **Run:** `uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload`
- **Effort:** L (8-12 hours)
- **Why:** The single biggest credibility gap. Every serious AI product has an API.
- **Depends on:** 2.1 Service Layer

### 2.3 SQLite Metadata Store ✅ DONE
- [x] Create `core/database.py` with SQLAlchemy models
- [x] Jobs table (id, type, status, file_name, vendor_name, created_at, completed_at, error)
- [x] Results table (id, job_id, invoice_file, vendor, invoice_number, status, confidence, matches_passed, total_matches, details_json)
- [x] AuditLog table (id, action, entity_type, entity_id, timestamp, metadata_json)
- [x] Enable WAL mode (`PRAGMA journal_mode=WAL`) + busy_timeout for concurrent access
- [x] Database manager class with CRUD operations, stats, and audit logging
- [x] GET /api/results and GET /api/stats API endpoints wired up
- [x] 34 database tests (init, jobs, results, audit, stats, concurrency)
- [ ] Migration support (Alembic) - deferred until schema stabilizes
- **Effort:** M (4-6 hours)
- **Why:** Structured data needs a structured store. Enables history, analytics, audit trail.

### 2.4 Batch Processing Pipeline ✅ DONE
- [x] `ThreadPoolExecutor` with configurable max_workers (default 3)
- [x] Job state machine per-file: PENDING -> PARSING -> EXTRACTING -> MATCHING -> COMPLETE/FAILED
- [x] State tracked in SQLite per-file (not in-memory)
- [x] Per-file error isolation: one failure doesn't kill the batch
- [x] Progress tracking via SQLite + GET /api/batch/{batch_id}/status polling
- [x] ETA display based on average per-invoice processing time
- [x] Batch size limit (default 100 files)
- [x] Cancel batch endpoint (POST /api/batch/{batch_id}/cancel)
- [x] 17 batch service tests (submit, process, status, cancel, integration)
- **Implementation:** ThreadPoolExecutor (not asyncio) because core modules use synchronous `requests` calls to Ollama. No async rewrite needed.
- **Effort:** L (8-12 hours)
- **Why:** Processing 50 invoices with a dashboard is the hero demo. Shows production engineering.
- **Depends on:** 2.1, 2.2, 2.3

### 2.5 Auto PO Matching ✅ DONE
- [x] Use extracted invoice.po_number to auto-lookup PO from POStore (exact match)
- [x] Fallback: fuzzy match on vendor_name + total_amount (5% tolerance) via POStore.get_pos_by_vendor()
- [x] If 1 fuzzy match found, use it; if 0 or 2+, skip (two-way only)
- [x] POMatchResult with confidence score and match method
- [x] Auto-match integrated into MatchService.validate_three_way()
- [x] 11 new auto PO matching tests (exact, fuzzy, edge cases)
- **Effort:** S (2-3 hours)
- **Why:** Makes the product feel intelligent. Removes manual dropdown friction.

---

## Phase 3: Polish & Presentation (P1 - Ship Quality)

### 3.1 Analytics Dashboard ✅ DONE
- [x] KPI cards: total processed, pass rate, total jobs, pending count
- [x] Recent results table with status badges, vendor, confidence, timestamps
- [x] Recent jobs table with status, type, duration, timestamps
- [x] Match results distribution chart (PASS/FAIL/REVIEW donut chart via Plotly)
- [x] Job status bar chart (Completed/Failed/Pending via Plotly)
- [x] Filter by vendor name and status
- [ ] Processing time trend chart (deferred -- needs more historical data)
- [ ] Date range filter (deferred -- dashboard is already functional)
- **Effort:** M (4-6 hours)
- **Why:** This is THE portfolio screenshot. Transforms the project from tool to product.
- **Depends on:** 2.3 SQLite

### 3.2 Docker Compose + CI ✅ DONE
- [x] Dockerfile for Python app (python:3.12-slim + poppler-utils)
- [x] docker-compose.yml with 3 services:
  - `app-ui` (Streamlit on port 8501)
  - `app-api` (FastAPI on port 8000)
  - `ollama` (Ollama with model auto-pull)
- [x] Shared data volume for ChromaDB and SQLite between app-ui and app-api
- [x] SQLite WAL mode for concurrent access from both services
- [x] GitHub Actions workflow: lint (flake8) + tests (pytest) on Python 3.11/3.12
- [x] .dockerignore for clean builds
- [x] Updated requirements.txt with all dependencies
- [ ] Badge in README for CI status (will add in 3.4 README overhaul)
- **Effort:** M (4-6 hours)
- **Why:** `docker compose up` = instant demo. CI badge = credibility.

### 3.3 4-Tier Test Suite
- [ ] **Tier 3 (do first):** API tests - FastAPI TestClient for all 7 endpoints with mocked Ollama. Highest portfolio visibility.
- [ ] **Tier 1:** Unit tests - fill gaps (PO extraction, three-way report generation, error paths, negative cases)
- [ ] **Tier 2:** Integration tests - mocked Ollama, real ChromaDB
- [ ] **Tier 4:** E2E tests - full pipeline with sample PDFs
- [ ] Hostile tests: 0-byte PDF, huge PDF, .exe renamed to .pdf, empty text
- [ ] CI integration via GitHub Actions
- **Priority order:** API tests first (prove the API contract), then unit gaps, then integration, then E2E.
- **Effort:** L (8-12 hours)
- **Why:** Test quality is as visible as code quality. Non-negotiable for portfolio.
- **Depends on:** 2.2 FastAPI

### 3.4 README Overhaul
- [ ] Hero GIF showing batch processing dashboard
- [ ] Updated architecture diagram (expanded architecture)
- [ ] "Why I Built This" narrative section
- [ ] Quick start with Docker Compose
- [ ] API documentation link
- [ ] Screenshots of key workflows
- [ ] Benchmark/eval results table
- [ ] Tech stack with brief rationale for each choice
- **Effort:** M (3-4 hours)
- **Why:** The README IS the product page. This is where portfolio visitors form their opinion.
- **Depends on:** Everything else (do last)

---

## Phase 4: AI Engineering Depth (P2 - Differentiation)

### 4.1 Eval Framework Integration
- [ ] Connect evals/ to CI pipeline
- [ ] Add extraction accuracy metrics (precision, recall, F1)
- [ ] Benchmark suite with regression detection
- [ ] Results table in README
- **Effort:** M (4-6 hours)
- **Why:** Measuring LLM output quality systematically is THE AI engineering differentiator.

### 4.2 Multi-Model Support
- [ ] Model selector in UI and API
- [ ] Run eval suite per model
- [ ] Comparison table (model vs accuracy vs speed)
- [ ] Config-driven model selection
- **Effort:** M (4-6 hours)
- **Why:** "Which model works best? Here are the numbers." Shows systematic AI engineering.

### 4.3 Export System
- [ ] PDF report generation (reportlab or weasyprint)
- [ ] Excel export for match results (openpyxl)
- [ ] API endpoint for report download
- [ ] Professional formatting with summary tables
- **Effort:** M (4-6 hours)
- **Why:** For SaaS, the output artifact IS the product.

---

## Phase 5: Delight Opportunities (P3 - Polish)

### 5.1 "Try with Sample Data" Button
- [ ] Pre-built sample contracts, POs, and invoices
- [ ] One-click demo loader in UI
- [ ] Showcase full pipeline without user documents
- **Effort:** S (30 min)

### 5.2 Side-by-Side Comparison View
- [ ] Invoice clause vs contract clause side-by-side
- [ ] Discrepancy highlighting in red
- [ ] Expandable detail view per match
- **Effort:** S (30 min)

### 5.3 Processing Step Animation
- [ ] Step-by-step progress: Parse -> Extract -> Match -> Done
- [ ] Checkmarks as each step completes
- [ ] Time elapsed per step
- **Effort:** S (20 min)

### 5.4 Auto-Detect Vendor Name
- [ ] LLM-based vendor name extraction from contract PDFs
- [ ] Pre-fill vendor field with manual override
- **Effort:** S (30 min)

### 5.5 Confidence Score Visualization
- [ ] Gauge/meter component (0-100%)
- [ ] Color gradient (red -> yellow -> green)
- [ ] Per-match confidence breakdown
- **Effort:** S (20 min)

---

## Implementation Order

```
Phase 1 (Foundation):     1.1 -> 1.2 -> 1.3 -> 1.4
Phase 2 (Architecture):   2.1 -> 2.2 + 2.3 (parallel) -> 2.4 -> 2.5
Phase 3 (Polish):         3.1 + 3.2 (parallel) -> 3.3 -> 3.4
Phase 4 (Depth):          4.1 -> 4.2 -> 4.3
Phase 5 (Delight):        Any order, each independent
```

## Key Architecture Decisions (from eng review)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Service layer | 2 services (DocumentService + MatchService) | IngestService/ProcessService split is artificial |
| Deployment | Separate processes, shared data volume | Simple, scalable, avoids process coupling |
| Batch processing | ThreadPoolExecutor + SQLite | Works with existing sync code, no async rewrite |
| Matcher decomposition | Partial in Phase 1, full in Phase 2 | Avoids double-touching files |
| Error handling | StoreError for infra, None/[] for not-found | Explicit distinction prevents silent failures |
| Test priority | API tests first (Tier 3) | Highest portfolio visibility and API contract proof |

## Estimated Total Effort

| Phase | Effort | Priority |
|-------|--------|----------|
| Phase 1: Foundation | S-M (~7-10 hours) | P1 |
| Phase 2: Architecture | L (~26-39 hours) | P1 |
| Phase 3: Polish | L (~19-28 hours) | P1 |
| Phase 4: Depth | M (~12-18 hours) | P2 |
| Phase 5: Delight | S (~3 hours) | P3 |
| **Total** | **~67-98 hours** | |
