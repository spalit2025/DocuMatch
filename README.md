# DocuMatch                                                                                          
                                                                                                       
  Procurement teams spend hours manually matching invoices to purchase orders                          
  and contracts -- cross-referencing line items, validating amounts, and flagging                      
  discrepancies across PDFs that were never designed to talk to each other.                            
                                                                                                       
  DocuMatch automates three-way invoice matching (Invoice <> PO <> Contract)                           
  using local LLMs and vector search. Upload your documents, and the system                            
  extracts structured data, matches entities semantically, and validates
  amounts with configurable tolerance rules. Everything runs offline -- no
  data leaves your machine.

  ## Why I built this

  Enterprise procurement matching is a perfect AI automation target:
  high-volume, rule-heavy, error-prone, and currently done manually in
  spreadsheets. I wanted to explore:

  1. **Can local LLMs handle structured extraction from messy PDFs?** Using
     Ollama with phi3.5/llama3.2 for entity extraction from real procurement
     documents -- no API costs, no data privacy concerns.
  2. **Does semantic search beat keyword matching for document reconciliation?**
     Vendor names appear differently across contracts, POs, and invoices.
     Vector similarity (ChromaDB + FastEmbed) handles this naturally.
  3. **What does a privacy-first AI workflow look like?** 100% offline
     processing -- critical for finance teams handling sensitive vendor
     agreements and pricing data.

  ## Demo

  <!-- TODO: Add screenshot of the Streamlit dashboard showing three-way match results -->

   ## How it works
                                                                                                       
  ```                                                       
  Upload PDFs
      |
  Parser Engine (Docling + pdfplumber)
      |
      ├── Contracts → LLM extracts entities → ChromaDB (vector store)
      ├── Purchase Orders → LLM extracts line items → PO Store
      └── Invoices → LLM extracts line items → Three-Way Matcher
                                                      |
                                                ┌─────┴─────┐
                                                |           |
                                          Match to PO  Match to Contract
                                                |           |
                                                └─────┬─────┘
                                                      |
                                              Validation Report
                                          (amounts, quantities, terms)
  ```

  **Three-way matching rules:**
  - Invoice line items matched to PO line items by description similarity
  - PO matched to contract by vendor name (semantic) + amount tolerance
  - Amount validation: configurable tolerance (default 1%)
  - Flags: overcharges, missing PO references, unmatched line items

  ## Quick start

  ```bash
  # Prerequisites: Python 3.10+, Ollama running locally
  ollama pull phi3.5

  # Clone and install
  git clone https://github.com/spalit2025/DocuMatch.git
  cd DocuMatch
  pip install -r requirements.txt

  # Configure (defaults work out of the box)
  cp .env.example .env

  # Launch
  streamlit run app/main.py
  ```

  **Workflow:**
  1. **Upload Contracts** -- ingest vendor contracts, LLM extracts key terms
  2. **Add POs** -- process purchase orders, match to existing contracts
  3. **Process Invoices** -- validate invoices against POs and contracts

  ## Architecture

  - `app/main.py` -- Streamlit dashboard with three workflow pages
  - `core/parser_engine.py` -- PDF to structured markdown (Docling + pdfplumber fallback)
  - `core/extraction.py` -- LLM-powered entity extraction from parsed documents
  - `core/vector_store.py` -- ChromaDB contract storage with semantic search
  - `core/po_store.py` -- Purchase order storage and retrieval
  - `core/matcher.py` -- Three-way validation logic with configurable rules
  - `core/models.py` -- Pydantic schemas for contracts, POs, invoices
  - `config.py` -- Pydantic settings with environment variable overrides

  ## Key design decisions

  - **Local LLMs over API calls:** Finance documents contain sensitive pricing and vendor data. Running
   Ollama locally means zero data exposure -- a hard requirement for any real procurement team. Also
  eliminates per-document API costs.

  - **Semantic matching over exact string matching:** Vendor names appear as "Acme Corp", "ACME
  Corporation", and "Acme" across different documents. Vector similarity handles this without brittle
  normalization rules.

  - **Dual parser with fallback:** Docling handles most PDFs well, but some scanned or poorly-formatted
   documents need pdfplumber as a fallback. The system tries both rather than failing.

  - **Configurable tolerance:** A 1% default tolerance for amount matching catches real discrepancies
  while ignoring rounding differences. Adjustable per-deployment via environment variables.

  ## Tech stack

  - **UI:** Streamlit
  - **LLM:** Ollama (phi3.5 / llama3.2)
  - **Vector DB:** ChromaDB with FastEmbed (all-MiniLM-L6-v2)
  - **PDF parsing:** Docling + pdfplumber fallback
  - **Validation:** Pydantic v2
  - **Python:** 3.10+

  ## Configuration

  All settings configurable via `.env` or environment variables:

  ```bash
  OLLAMA_HOST=http://localhost:11434
  OLLAMA_DEFAULT_MODEL=phi3.5
  CHROMA_PERSIST_DIR=./data/chroma_db
  MATCHING_TOLERANCE=0.01           # 1% amount tolerance
  PARSER_MAX_FILE_SIZE=52428800     # 50MB max
  CHUNK_SIZE=512                    # tokens per chunk
  LOG_LEVEL=INFO
  ```

  ## License

  MIT
