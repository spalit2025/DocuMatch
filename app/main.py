"""
DocuMatch Architect - Main Application Entry Point

A privacy-first document processing system for invoice-contract matching.
Run with: streamlit run app/main.py
"""

import streamlit as st
import requests
from pathlib import Path
import sys

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import settings
from core.vector_store import VectorStore

# Initialize vector store for stats
vector_store = VectorStore(
    persist_directory=str(settings.chroma_path),
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
)


def check_ollama_status() -> tuple[bool, str]:
    """Check if Ollama is running and accessible."""
    try:
        response = requests.get(f"{settings.ollama_host}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "").split(":")[0] for m in models]
            return True, f"Connected. Models: {', '.join(model_names) or 'None'}"
        return False, f"Error: Status {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, "Not running. Start with: ollama serve"
    except Exception as e:
        return False, f"Error: {str(e)}"


def check_chroma_status() -> tuple[bool, str, dict]:
    """Check ChromaDB data directory status and get stats."""
    try:
        stats = vector_store.get_stats()
        chroma_path = settings.chroma_path
        return True, f"Ready at {chroma_path}", stats
    except Exception as e:
        return False, f"Error: {str(e)}", {}


def get_indexed_contracts_count() -> tuple[int, int]:
    """Get count of indexed vendors and chunks."""
    try:
        stats = vector_store.get_stats()
        return stats["total_vendors"], stats["total_chunks"]
    except Exception:
        return 0, 0


# Page Configuration
st.set_page_config(
    page_title="DocuMatch Architect",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Custom CSS
st.markdown("""
<style>
    .status-ok { color: #28a745; font-weight: bold; }
    .status-error { color: #dc3545; font-weight: bold; }
    .status-warning { color: #ffc107; font-weight: bold; }
    .main-header { font-size: 2.5rem; margin-bottom: 0; }
    .sub-header { color: #6c757d; margin-top: 0; }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.title("DocuMatch Architect")
    st.markdown("---")

    st.subheader("System Status")

    # Ollama Status
    ollama_ok, ollama_msg = check_ollama_status()
    if ollama_ok:
        st.markdown(f"**Ollama:** <span class='status-ok'>Online</span>", unsafe_allow_html=True)
        st.caption(ollama_msg)
    else:
        st.markdown(f"**Ollama:** <span class='status-error'>Offline</span>", unsafe_allow_html=True)
        st.caption(ollama_msg)

    # ChromaDB Status
    chroma_ok, chroma_msg, chroma_stats = check_chroma_status()
    if chroma_ok:
        st.markdown(f"**ChromaDB:** <span class='status-ok'>Ready</span>", unsafe_allow_html=True)
    else:
        st.markdown(f"**ChromaDB:** <span class='status-error'>Error</span>", unsafe_allow_html=True)
    st.caption(chroma_msg)

    st.markdown("---")

    # Quick Stats
    st.subheader("Quick Stats")
    vendors_count, chunks_count = get_indexed_contracts_count()
    st.metric("Indexed Vendors", vendors_count)
    st.metric("Total Chunks", chunks_count)

    st.markdown("---")

    # Configuration
    with st.expander("Configuration"):
        st.text(f"Model: {settings.default_model}")
        st.text(f"Chunk Size: {settings.chunk_size}")
        st.text(f"Max File: {settings.max_file_size_mb}MB")

# Main Content
st.markdown("<h1 class='main-header'>DocuMatch Architect</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-header'>Privacy-first invoice-contract matching system</p>", unsafe_allow_html=True)

st.markdown("---")

# Feature Cards
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("### 📁 Ingest Contracts")
    st.markdown("""
    Upload and index your contracts (MSAs, SOWs) for semantic search.

    - PDF parsing with Docling
    - Automatic chunking
    - Vendor-based organization
    """)
    if st.button("Go to Contract Ingestion", key="btn_contracts"):
        st.switch_page("pages/1_Ingest_Contracts.py")

with col2:
    st.markdown("### 📄 Process Invoices")
    st.markdown("""
    Upload invoices and validate them against indexed contracts.

    - AI-powered data extraction
    - Rate & terms validation
    - Detailed match reports
    """)
    if st.button("Go to Invoice Processing", key="btn_invoices"):
        st.switch_page("pages/2_Process_Invoices.py")

with col3:
    st.markdown("### 100% Offline")
    st.markdown("""
    All processing happens locally on your machine.

    - No cloud APIs
    - No data leaves your system
    - Full privacy control
    """)

st.markdown("---")

# Getting Started
st.markdown("### Getting Started")

st.markdown("""
1. **Ensure Ollama is running** with the required model:
   ```bash
   ollama serve
   ollama pull phi3.5
   ```

2. **Upload your contracts** using the Contract Ingestion page

3. **Process invoices** and validate them against your contracts
""")

# Footer
st.markdown("---")
st.caption("DocuMatch Architect v1.0 | Built with Streamlit, Docling, ChromaDB, and Ollama")
