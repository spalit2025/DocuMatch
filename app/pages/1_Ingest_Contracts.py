"""
Contract Ingestion Page

Upload and index contracts for semantic search.
"""

import streamlit as st
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import settings
from core.parser_engine import ParserEngine
from core.vector_store import VectorStore

# Initialize parser and vector store
parser = ParserEngine(fallback_enabled=settings.parser_fallback_enabled)
vector_store = VectorStore(
    persist_directory=str(settings.chroma_path),
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
)

st.set_page_config(
    page_title="Ingest Contracts - DocuMatch",
    page_icon="📁",
    layout="wide",
)

st.title("📁 Contract Ingestion")
st.markdown("Upload and index your contracts (MSAs, SOWs) for semantic search.")

st.markdown("---")

# Initialize session state
if "parsed_result" not in st.session_state:
    st.session_state.parsed_result = None
if "current_file" not in st.session_state:
    st.session_state.current_file = None

# Upload Section
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Upload Contract")

    uploaded_file = st.file_uploader(
        "Choose a PDF file",
        type=["pdf"],
        help=f"Maximum file size: {settings.max_file_size_mb}MB"
    )

    vendor_name = st.text_input(
        "Vendor Name",
        placeholder="e.g., Acme Corporation",
        help="This will be used to organize and retrieve contract clauses"
    )

    contract_type = st.selectbox(
        "Contract Type",
        options=["MSA", "SOW", "NDA", "Other"],
        format_func=lambda x: {
            "MSA": "MSA (Master Service Agreement)",
            "SOW": "SOW (Statement of Work)",
            "NDA": "NDA (Non-Disclosure Agreement)",
            "Other": "Other"
        }.get(x, x),
        help="Type of contract being uploaded"
    )

    # Parse button (separate from indexing)
    col_parse, col_index = st.columns(2)

    with col_parse:
        if st.button("Parse PDF", disabled=not uploaded_file):
            if uploaded_file:
                with st.spinner("Parsing PDF to Markdown..."):
                    # Save uploaded file temporarily
                    save_path = settings.contracts_path / f"temp_{uploaded_file.name}"
                    save_path.parent.mkdir(parents=True, exist_ok=True)

                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    # Parse the PDF
                    result = parser.parse_to_markdown(str(save_path))

                    if result.success:
                        st.session_state.parsed_result = result
                        st.session_state.current_file = uploaded_file.name
                        st.success(f"Parsed successfully using {result.parse_method}!")
                    else:
                        st.error(f"Parsing failed: {result.error_message}")
                        st.session_state.parsed_result = None

    with col_index:
        index_disabled = not (uploaded_file and vendor_name and st.session_state.parsed_result)
        if st.button("Index Contract", type="primary", disabled=index_disabled):
            if uploaded_file and vendor_name and st.session_state.parsed_result:
                with st.spinner("Indexing contract in vector store..."):
                    try:
                        # Index in ChromaDB
                        contract_id = vector_store.index_contract(
                            text=st.session_state.parsed_result.markdown,
                            vendor_name=vendor_name,
                            contract_type=contract_type,
                            metadata={
                                "filename": uploaded_file.name,
                                "page_count": st.session_state.parsed_result.page_count,
                                "tables_found": st.session_state.parsed_result.tables_found,
                            }
                        )

                        # Rename temp file to permanent
                        temp_path = settings.contracts_path / f"temp_{uploaded_file.name}"
                        final_path = settings.contracts_path / f"{vendor_name}_{uploaded_file.name}"

                        if temp_path.exists():
                            # Remove existing file if any
                            if final_path.exists():
                                final_path.unlink()
                            temp_path.rename(final_path)

                        st.success(f"Contract indexed successfully!")
                        st.info(f"Contract ID: `{contract_id}`")

                        # Get chunk count
                        stats = vector_store.get_stats()
                        vendor_info = next(
                            (v for v in stats["vendors"] if v["vendor_name"] == vendor_name),
                            None
                        )
                        if vendor_info:
                            st.metric("Chunks Created", vendor_info["chunk_count"])

                    except Exception as e:
                        st.error(f"Indexing failed: {str(e)}")

with col2:
    st.subheader("Parse Status")

    if st.session_state.parsed_result:
        result = st.session_state.parsed_result

        if result.success:
            st.success("Parsed!")
            st.metric("Pages", result.page_count)
            st.metric("Tables Found", result.tables_found)
            st.caption(f"Method: {result.parse_method}")
        else:
            st.error("Parse Failed")
            st.caption(result.error_message)
    else:
        st.info("Upload and parse a PDF")

    st.markdown("---")

    # Vector Store Stats
    st.subheader("Vector Store")
    try:
        stats = vector_store.get_stats()
        st.metric("Total Chunks", stats["total_chunks"])
        st.metric("Vendors", stats["total_vendors"])
    except Exception as e:
        st.warning(f"Could not load stats: {e}")

st.markdown("---")

# Preview Section
st.subheader("Markdown Preview")

if st.session_state.parsed_result and st.session_state.parsed_result.success:
    result = st.session_state.parsed_result

    # Show preview with tabs
    tab_preview, tab_raw = st.tabs(["Formatted", "Raw Markdown"])

    with tab_preview:
        # Render markdown (limit to prevent performance issues)
        preview_text = result.markdown
        if len(preview_text) > 10000:
            st.warning(f"Showing first 10,000 characters of {len(preview_text)} total")
            preview_text = preview_text[:10000] + "\n\n... (truncated)"

        st.markdown(preview_text)

    with tab_raw:
        st.code(result.markdown[:20000] if len(result.markdown) > 20000 else result.markdown, language="markdown")

elif uploaded_file:
    st.info("Click 'Parse PDF' to see the content preview")
else:
    st.info("Upload a contract to see the parsed content preview")

st.markdown("---")

# Indexed Contracts List
st.subheader("Indexed Contracts")

# Get vendors from vector store
try:
    vendors = vector_store.list_vendors()

    if vendors:
        for vendor_info in vendors:
            col_name, col_chunks, col_type, col_delete = st.columns([3, 1, 1, 1])

            with col_name:
                st.markdown(f"**{vendor_info['vendor_name']}**")

            with col_chunks:
                st.caption(f"{vendor_info['chunk_count']} chunks")

            with col_type:
                types = ", ".join(vendor_info.get("contract_types", []))
                st.caption(types or "N/A")

            with col_delete:
                if st.button("Delete", key=f"del_vendor_{vendor_info['vendor_name']}"):
                    deleted = vector_store.delete_contract(vendor_info['vendor_name'])
                    st.success(f"Deleted {deleted} chunks")
                    st.rerun()
    else:
        st.info("No contracts indexed yet. Upload a contract above to get started.")

except Exception as e:
    st.error(f"Could not list vendors: {e}")

# Also list PDF files that might not be indexed
st.markdown("---")
st.subheader("PDF Files on Disk")

contracts_path = settings.contracts_path
if contracts_path.exists():
    pdf_files = list(contracts_path.glob("*.pdf"))
    pdf_files = [f for f in pdf_files if not f.name.startswith("temp_")]

    if pdf_files:
        for pdf_file in pdf_files:
            col_name, col_size, col_delete = st.columns([3, 1, 1])
            with col_name:
                st.caption(pdf_file.name)
            with col_size:
                size_kb = pdf_file.stat().st_size / 1024
                st.caption(f"{size_kb:.1f} KB")
            with col_delete:
                if st.button("Remove File", key=f"del_file_{pdf_file.name}"):
                    pdf_file.unlink()
                    st.rerun()
    else:
        st.caption("No PDF files stored")
else:
    st.caption("No PDF files stored")

# Sidebar info
with st.sidebar:
    st.markdown("### About Contract Ingestion")
    st.markdown("""
    **How it works:**

    1. Upload a PDF contract
    2. Docling parses the PDF to Markdown
    3. Text is chunked into semantic segments
    4. Chunks are embedded and stored in ChromaDB

    **Supported formats:**
    - PDF files up to 50MB
    - Multi-page documents
    - Documents with tables
    """)

    st.markdown("---")
    st.markdown("### System Status")

    # Parser status
    if parser._docling_available:
        st.success("Docling: Available")
    else:
        st.warning("Docling: Not available")
        st.caption("Using pdfplumber fallback")

    # Vector store status
    st.success("ChromaDB: Connected")
    st.caption(f"Path: {settings.chroma_path}")

    st.markdown("---")

    # Search test
    st.markdown("### Quick Search Test")
    test_vendor = st.text_input("Vendor", key="test_vendor")
    test_query = st.text_input("Query", key="test_query", placeholder="e.g., payment terms")

    if st.button("Search", key="test_search"):
        if test_vendor and test_query:
            with st.spinner("Searching..."):
                results = vector_store.retrieve_clauses(test_vendor, test_query, top_k=3)

                if results:
                    st.success(f"Found {len(results)} results")
                    for i, clause in enumerate(results):
                        with st.expander(f"Result {i+1} (score: {clause.similarity_score:.2f})"):
                            st.markdown(clause.text[:500] + "..." if len(clause.text) > 500 else clause.text)
                else:
                    st.info("No results found")
        else:
            st.warning("Enter vendor and query")
