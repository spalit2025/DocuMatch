# DocuMatch Architect

[![CI](https://github.com/spalit2025/DocuMatch/actions/workflows/ci.yml/badge.svg)](https://github.com/spalit2025/DocuMatch/actions/workflows/ci.yml)

Privacy-first, 100% offline document processing system that validates invoices against contracts and purchase orders using local LLMs and semantic search.

Procurement teams spend hours manually matching invoices to purchase orders and contracts -- cross-referencing line items, validating amounts, and flagging discrepancies across PDFs that were never designed to talk to each other. DocuMatch automates this with three-way matching (Invoice ↔ PO ↔ Contract), running entirely on your machine.

## Why I Built This

Enterprise procurement matching is a perfect AI automation target: high-volume, rule-heavy, error-prone, and currently done manually in spreadsheets. I wanted to explore three questions:

1. **Can local LLMs handle structured extraction from messy PDFs?** Using Ollama with phi3.5/llama3.2 for entity extraction -- no API costs, no data privacy concerns.
2. **Does semantic search beat keyword matching for document reconciliation?** Vendor names appear differently across documents. Vector similarity handles this naturally.
3. **What does production AI engineering look like?** Not just a demo -- service layer, REST API, batch processing, SQLite state tracking, 238 automated tests.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        DocuMatch Architect                           │
├──────────────┬───────────────────────────────────────────────────────┤
│              │                                                       │
│  Streamlit   │   FastAPI REST API                                    │
│  UI (8501)   │   (8000)                                              │
│              │   POST /api/contracts/ingest                          │
│  - Contracts │   POST /api/pos/ingest                                │
│  - POs       │   POST /api/invoices/process                          │
│  - Invoices  │   POST /api/batch/process                             │
│  - Analytics │   GET  /api/batch/{id}/status                         │
│              │   GET  /api/results                                   │
│              │   GET  /api/stats                                     │
│              │   GET  /api/health                                    │
├──────────────┴───────────────────────────────────────────────────────┤
│                        Service Layer                                 │
│  DocumentService (parse→extract→store)                               │
│  MatchService (validate + auto PO matching)                          │
│  BatchService (ThreadPoolExecutor + SQLite state)                    │
├──────────────────────────────────────────────────────────────────────┤
│                        Core Modules                                  │
│  ParserEngine    ExtractionEngine    Matcher    ReportGenerator       │
│  (Docling/       (Ollama LLM)       (Rules +   (Text reports)        │
│   pdfplumber)                        Semantic)                       │
├──────────────────────────────────────────────────────────────────────┤
│                        Data Layer                                    │
│  ChromaDB (contracts + POs)    SQLite (jobs, results, audit log)     │
│  FastEmbed (all-MiniLM-L6-v2) WAL mode for concurrent access        │
└──────────────────────────────────────────────────────────────────────┘
```

### Processing Pipeline

```
Contract:  PDF → Parse (Docling) → Chunk → Index to ChromaDB
PO:        PDF → Parse → LLM Extract → PurchaseOrderSchema → Index to ChromaDB
Invoice:   PDF → Parse → LLM Extract → InvoiceSchema → Three-Way Validation

Three-Way Matching:
  Match 1: Invoice ↔ PO     (amounts, quantities, line items)
  Match 2: Invoice ↔ Contract (rates, dates, payment terms)
  Match 3: PO ↔ Contract     (rates, dates)

  Result: ≥2 matches PASS → PASS | <2 → FAIL/REVIEW
```

## Quick Start

### Option 1: Docker Compose (recommended)

```bash
git clone https://github.com/spalit2025/DocuMatch.git
cd DocuMatch
docker compose up
```

This starts three services:
- **Streamlit UI** at `http://localhost:8501`
- **FastAPI API** at `http://localhost:8000/docs`
- **Ollama** with phi3.5 auto-pulled

### Option 2: Local Development

```bash
# Prerequisites: Python 3.10+, Ollama running locally
ollama pull phi3.5

git clone https://github.com/spalit2025/DocuMatch.git
cd DocuMatch
pip install -r requirements.txt

# Launch UI
streamlit run app/main.py

# Launch API (separate terminal)
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

## API

Full OpenAPI docs at `http://localhost:8000/docs` when running.

```bash
# Ingest a contract
curl -X POST http://localhost:8000/api/contracts/ingest \
  -F "file=@contract.pdf" \
  -F "vendor_name=Acme Corp" \
  -F "contract_type=MSA"

# Process an invoice (with three-way matching)
curl -X POST http://localhost:8000/api/invoices/process \
  -F "file=@invoice.pdf" \
  -F "po_number=PO-001"

# Batch process multiple invoices
curl -X POST http://localhost:8000/api/batch/process \
  -H "Content-Type: application/json" \
  -d '{"files": [{"file_path": "/data/inv1.pdf"}, {"file_path": "/data/inv2.pdf"}]}'

# Check batch status
curl http://localhost:8000/api/batch/1/status

# Query results
curl "http://localhost:8000/api/results?status=FAIL&vendor_name=Acme"

# System health
curl http://localhost:8000/api/health
```

## Key Features

| Feature | Description |
|---------|-------------|
| Three-Way Matching | Invoice ↔ PO ↔ Contract validation with configurable tolerance |
| Auto PO Matching | Automatically finds the matching PO by number or vendor+amount fuzzy match |
| Batch Processing | Process 100 invoices concurrently with per-file error isolation |
| REST API | 8 endpoints with OpenAPI docs, proper error codes (422/502/503) |
| Analytics Dashboard | KPI cards, Plotly charts, filterable results table |
| Audit Trail | Every action logged to SQLite with timestamps |
| 100% Offline | No data leaves your machine -- local LLMs + local vector DB |

## Tech Stack

| Component | Technology | Why |
|-----------|------------|-----|
| UI | Streamlit | Rapid prototyping, built-in file upload, session state |
| API | FastAPI | Auto OpenAPI docs, dependency injection, async support |
| LLM | Ollama (phi3.5) | Local inference, no API costs, privacy-first |
| Vector DB | ChromaDB + FastEmbed | Semantic search with all-MiniLM-L6-v2 embeddings |
| PDF Parsing | Docling + pdfplumber | Dual parser with automatic fallback |
| Database | SQLite + SQLAlchemy | WAL mode for concurrent access, zero config |
| Validation | Pydantic v2 | Type-safe schemas with field validators |
| Charts | Plotly | Interactive, publication-quality visualizations |
| Testing | pytest (238 tests) | Unit, API, hostile input, integration tests |
| CI | GitHub Actions | Lint + test on Python 3.11/3.12 |
| Deploy | Docker Compose | One command: `docker compose up` |

## Testing

```bash
# Run all tests (excluding integration tests that need Ollama)
python -m pytest tests/ -v -k "not Integration and not real_extraction"

# Run specific test suites
python -m pytest tests/test_api.py -v              # API contract tests
python -m pytest tests/test_hostile_inputs.py -v    # Adversarial inputs
python -m pytest tests/test_batch_service.py -v     # Batch processing
python -m pytest tests/test_database.py -v          # SQLite operations
python -m pytest tests/test_document_service.py -v  # Service layer
python -m pytest tests/test_match_service.py -v     # Matching + auto PO
```

## Configuration

All settings via `.env` or environment variables:

```bash
OLLAMA_HOST=http://localhost:11434
DEFAULT_MODEL=phi3.5
CHROMA_PERSIST_DIR=./data/chroma_db
DB_PATH=./data/documatch.db
MATCH_TOLERANCE=0.01           # 1% amount tolerance
MAX_FILE_SIZE_MB=50
CHUNK_SIZE=512
CHUNK_OVERLAP=50
LOG_LEVEL=INFO
```

## Project Structure

```
DocuMatch/
├── api/                    # FastAPI REST API
│   ├── app.py              # App creation, exception handlers
│   ├── routes.py           # Endpoint handlers
│   ├── schemas.py          # API request/response models
│   └── dependencies.py     # Dependency injection
├── app/                    # Streamlit UI
│   ├── main.py             # Entry point
│   └── pages/              # Multi-page app
│       ├── 1_Ingest_Contracts.py
│       ├── 2_Process_POs.py
│       ├── 3_Process_Invoices.py
│       └── 4_Analytics.py
├── core/                   # Business logic
│   ├── services/           # Orchestration layer
│   │   ├── document_service.py
│   │   ├── match_service.py
│   │   └── batch_service.py
│   ├── parser_engine.py    # PDF → Markdown
│   ├── extraction.py       # LLM extraction
│   ├── matcher.py          # Validation rules
│   ├── vector_store.py     # ChromaDB operations
│   ├── po_store.py         # PO storage
│   ├── database.py         # SQLite metadata store
│   └── models.py           # Pydantic schemas
├── prompts/                # LLM prompt templates
├── tests/                  # 238 tests
├── docker-compose.yml      # One-command deployment
├── Dockerfile
└── requirements.txt
```

## License

MIT
