# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

DocuMatch Architect is a privacy-first, 100% offline document processing system that validates invoices against contracts and purchase orders using local LLMs and semantic search. It supports three-way matching (Invoice ↔ PO ↔ Contract).

## Commands

```bash
# Run the Streamlit application
streamlit run app/main.py

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_parser.py -v
python -m pytest tests/test_vector_store.py -v
python -m pytest tests/test_extraction.py -v
python -m pytest tests/test_matcher.py -v
python -m pytest tests/test_po_store.py -v
python -m pytest tests/test_three_way_match.py -v

# Run a specific test
python -m pytest tests/test_parser.py::TestParserEngine::test_parse_nonexistent_file -v

# Format code
black .

# Lint
flake8 .

# Type check
mypy .
```

**External dependency:** Ollama must be running (`ollama serve`) with `phi3.5` or `llama3.2` model pulled.

## Architecture

### Data Flow Pipeline

```
Contract Onboarding:
PDF → ParserEngine (Docling/pdfplumber) → Markdown → Chunking → ChromaDB (contracts)

PO Processing:
PDF → ParserEngine → Markdown → ExtractionEngine (Ollama LLM) → PurchaseOrderSchema → ChromaDB (POs)

Invoice Processing (Three-Way Match):
PDF → ParserEngine → Markdown → ExtractionEngine → InvoiceSchema
                                                          ↓
                                              Matcher.validate_invoice_three_way()
                                                          ↓
                              ┌─────────────────────┬─────────────────────┐
                              ↓                     ↓                     ↓
                      Match 1: Invoice↔PO    Match 2: Invoice↔Contract    Match 3: PO↔Contract
                              ↓                     ↓                     ↓
                              └─────────────────────┴─────────────────────┘
                                                          ↓
                                              ThreeWayMatchResult
                                              (≥2 matches PASS → PASS)
```

### Core Modules (`/core`)

- **parser_engine.py**: PDF→Markdown conversion. Uses Docling as primary parser, falls back to pdfplumber. Returns `ParseResult`.
- **vector_store.py**: ChromaDB operations for storing/retrieving contract clauses by vendor. Handles text chunking and semantic search.
- **po_store.py**: ChromaDB operations for storing/retrieving Purchase Orders. Supports CRUD and semantic search.
- **extraction.py**: LLM-based structured data extraction via Ollama. Extracts both invoices and POs. Includes retry logic with error feedback.
- **matcher.py**: Business rules engine for two-way and three-way matching. Validates rates, dates, payment terms. Returns `MatchResult` or `ThreeWayMatchResult`.
- **models.py**: Pydantic schemas (`InvoiceSchema`, `PurchaseOrderSchema`, `LineItem`, `ParseResult`, `MatchResult`, `ThreeWayMatchResult`, `MatchDetail`, `ValidationIssue`, `RetrievedClause`).

### Streamlit UI (`/app`)

- **main.py**: Entry point with system status dashboard
- **pages/1_Ingest_Contracts.py**: Contract upload, parsing, and ChromaDB indexing
- **pages/2_Process_POs.py**: PO upload, extraction, and indexing
- **pages/3_Process_Invoices.py**: Invoice processing, extraction, three-way validation, and report generation

### Configuration

Settings are managed via `config.py` using pydantic-settings. Environment variables are loaded from `.env` file:

```python
from config import settings
settings.ollama_host            # http://localhost:11434
settings.default_model          # phi3.5
settings.contracts_path         # Path object for contracts directory
settings.invoices_path          # Path object for invoices directory
settings.purchase_orders_path   # Path object for POs directory
settings.chunk_size             # 512
settings.chunk_overlap          # 50
settings.match_tolerance        # 0.01 (1% tolerance for amount matching)
```

## Key Usage Patterns

### Parser Engine
```python
from core import ParserEngine
parser = ParserEngine(fallback_enabled=True)
result = parser.parse_to_markdown(pdf_path)
# result.parse_method indicates "docling" or "pdfplumber"
```

### Vector Store
```python
from core import VectorStore
store = VectorStore(persist_directory="./data/chroma_db")
contract_id = store.index_contract(text, "VendorA", "MSA")
clauses = store.retrieve_clauses("VendorA", "payment terms", top_k=3)
```

### PO Store
```python
from core import POStore, PurchaseOrderSchema
po_store = POStore(persist_directory="./data/chroma_db")
po = PurchaseOrderSchema(
    po_number="PO-001",
    vendor_name="VendorA",
    order_date="2024-01-15",
    total_amount=5000.00,
    line_items=[...]
)
po_store.index_po(po)
retrieved = po_store.get_po_by_number("PO-001")
vendor_pos = po_store.get_pos_by_vendor("VendorA")
```

### Extraction Engine
```python
from core import ExtractionEngine
engine = ExtractionEngine(model="phi3.5")

# Extract invoice data
invoice = engine.extract_invoice_data(markdown_text)

# Extract PO data
po = engine.extract_po_data(markdown_text)
```

### Matcher (Two-Way)
```python
from core import Matcher
matcher = Matcher(vector_store)
result = matcher.validate_invoice(invoice)
# result.status: "PASS", "FAIL", or "REVIEW"
# result.issues: List[ValidationIssue]
report = matcher.generate_report(result)
```

### Matcher (Three-Way)
```python
from core import Matcher
matcher = Matcher(vector_store, po_store=po_store)
result = matcher.validate_invoice_three_way(invoice, po_number="PO-001")
# result.status: "PASS", "FAIL", or "REVIEW"
# result.matches_passed: Number of matches that passed (0-3)
# result.invoice_po_match: MatchDetail for Invoice ↔ PO
# result.invoice_contract_match: MatchDetail for Invoice ↔ Contract
# result.po_contract_match: MatchDetail for PO ↔ Contract
# result.all_issues: Combined list of all issues
report = matcher.generate_three_way_report(result)
```

## Three-Way Matching Rules

### Match 1: Invoice ↔ PO
- PO number reference matches
- Line item quantities match (within tolerance)
- Line item unit prices match (within tolerance)
- Total amounts match (within tolerance)

### Match 2: Invoice ↔ Contract
- Invoice rates within contract rate card limits
- Invoice date within contract effective period
- Contract exists for vendor

### Match 3: PO ↔ Contract
- PO rates within contract rate card limits
- PO order date within contract effective period

### Result Logic
- **PASS**: ≥2 of 3 matches pass (or 1 of 1 when no PO)
- **FAIL**: <2 matches pass → Manual Review required

## Validation Rules

The Matcher validates:
- **Rate Compliance**: Invoice/PO rates vs contract rate card
- **Date Validation**: Invoice/PO date within contract period
- **Line Item Math**: quantity × unit_price = total
- **Total Sum**: Line items sum matches document total
- **Payment Terms**: Invoice terms align with contract
- **Vendor Existence**: Contract exists for vendor
- **PO Match**: Invoice amounts/quantities match linked PO
