# DocuMatch Architect

A privacy-first document processing system that runs 100% offline. It ingests complex PDFs (Invoices, Contracts, Purchase Orders), understands their layout, extracts structured data, and performs **three-way matching** to validate invoices against contracts and POs.

## Features

- **100% Offline**: No cloud APIs, all processing happens locally
- **Smart Parsing**: Uses Docling for intelligent PDF-to-Markdown conversion
- **AI-Powered Extraction**: Local LLM (Phi-3.5/Llama3.2) extracts structured data from invoices and POs
- **Semantic Search**: ChromaDB stores and retrieves contract clauses
- **Three-Way Matching**: Validates Invoice ↔ PO ↔ Contract with configurable tolerance
- **Validation Engine**: Compares rates, dates, quantities, and terms

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) with phi3.5 or llama3.2 model
- 8GB+ RAM (16GB recommended)

## Quick Start

### 1. Clone and Setup

```bash
cd documatch-architect
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env if needed (defaults work for most setups)
```

### 3. Start Ollama

```bash
# In a separate terminal
ollama serve

# Pull the model (first time only)
ollama pull phi3.5
```

### 4. Run the Application

```bash
streamlit run app/main.py
```

Open http://localhost:8501 in your browser.

## Project Structure

```
/documatch-architect
├── /app
│   ├── main.py                    # Streamlit entry point
│   ├── /pages
│   │   ├── 1_Ingest_Contracts.py  # Contract ingestion
│   │   ├── 2_Process_POs.py       # PO processing
│   │   └── 3_Process_Invoices.py  # Invoice validation
│   └── /components                # Reusable UI widgets
├── /core
│   ├── parser_engine.py           # PDF to Markdown conversion
│   ├── vector_store.py            # ChromaDB contract storage
│   ├── po_store.py                # ChromaDB PO storage
│   ├── extraction.py              # LLM data extraction (Invoice & PO)
│   ├── matcher.py                 # Three-way validation logic
│   └── models.py                  # Pydantic schemas
├── /data
│   ├── /contracts                 # Uploaded contract PDFs
│   ├── /invoices                  # Uploaded invoice PDFs
│   ├── /purchase_orders           # Uploaded PO PDFs
│   └── /chroma_db                 # Vector database storage
├── /tests                         # Test suite
├── config.py                      # Configuration management
├── requirements.txt               # Python dependencies
└── .env.example                   # Environment template
```

## Usage

### Ingesting Contracts

1. Navigate to "Ingest Contracts" page
2. Upload a contract PDF (MSA, SOW, etc.)
3. Enter the vendor name
4. Click "Index Contract"

The system will:
- Parse the PDF to Markdown
- Chunk the text into semantic segments
- Store embeddings in ChromaDB

### Processing Purchase Orders

1. Navigate to "Process POs" page
2. Upload a PO PDF
3. Select the vendor (must have contract indexed first)
4. Click "Parse PO" then "Extract PO Data"
5. Review extracted fields
6. Click "Index PO"

The system will:
- Extract PO data (number, vendor, line items, amounts)
- Store in ChromaDB for three-way matching

### Processing Invoices (Three-Way Matching)

1. Navigate to "Process Invoices" page
2. Upload an invoice PDF
3. Click "Parse Invoice" then "Extract Invoice Data"
4. Select a linked PO (optional, for three-way matching)
5. Click "Validate Invoice"

The system performs three-way matching:
- **Match 1**: Invoice ↔ PO (quantities, prices, totals)
- **Match 2**: Invoice ↔ Contract (rates, dates)
- **Match 3**: PO ↔ Contract (rates, dates)

**Result**: If ≥2 matches pass → **PASS**; otherwise → **FAIL** (Manual Review)

## Three-Way Matching Rules

| Match | Checks |
|-------|--------|
| Invoice ↔ PO | PO number, line item quantities, unit prices, totals |
| Invoice ↔ Contract | Rates within limits, invoice date within contract period |
| PO ↔ Contract | PO rates within limits, order date within contract period |

## Configuration

Key settings in `.env`:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | http://localhost:11434 | Ollama API endpoint |
| `DEFAULT_MODEL` | phi3.5 | LLM for extraction |
| `CHUNK_SIZE` | 512 | Text chunk size (tokens) |
| `MAX_FILE_SIZE_MB` | 50 | Maximum upload size |
| `MATCH_TOLERANCE` | 0.01 | Amount matching tolerance (1%) |
| `PURCHASE_ORDERS_DIR` | ./data/purchase_orders | PO storage directory |

## Tech Stack

- **Frontend**: Streamlit
- **PDF Parsing**: Docling (with pdfplumber fallback)
- **AI/LLM**: Ollama (Phi-3.5 / Llama3.2)
- **Vector Store**: ChromaDB
- **Embeddings**: FastEmbed (all-MiniLM-L6-v2)
- **Validation**: Pydantic

## Development

### Running Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_po_store.py -v
python -m pytest tests/test_three_way_match.py -v
```

### Code Style

```bash
# Install dev dependencies
pip install black flake8 mypy

# Format code
black .

# Lint
flake8 .

# Type check
mypy .
```

## Troubleshooting

### Ollama not connecting
- Ensure Ollama is running: `ollama serve`
- Check if model is pulled: `ollama list`
- Verify endpoint: `curl http://localhost:11434/api/tags`

### PDF parsing fails
- The system will automatically fall back to pdfplumber
- Ensure the PDF is not password-protected
- Check file size limits

### Memory issues
- Reduce `CHUNK_SIZE` in `.env`
- Use a smaller model (llama3.2 instead of phi3.5)
- Process files one at a time

### Three-way matching issues
- Ensure contract is indexed before adding POs
- Verify vendor names match exactly across documents
- Check `MATCH_TOLERANCE` setting for amount comparisons

## License

MIT

## Version

2.0.0
