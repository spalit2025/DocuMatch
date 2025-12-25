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
from app.styles import inject_styles

# Initialize parser and vector store
parser = ParserEngine(fallback_enabled=settings.parser_fallback_enabled)
vector_store = VectorStore(
    persist_directory=str(settings.chroma_path),
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
)

st.set_page_config(
    page_title="Ingest Contracts - PDM",
    page_icon="📋",
    layout="wide",
)

# Inject styles
inject_styles()

# Initialize session state
if "parsed_result" not in st.session_state:
    st.session_state.parsed_result = None
if "current_file" not in st.session_state:
    st.session_state.current_file = None
if "current_file_name" not in st.session_state:
    st.session_state.current_file_name = None

# Get stats
try:
    stats = vector_store.get_stats()
except Exception:
    stats = {"total_chunks": 0, "total_vendors": 0, "vendors": []}


# ===== SIDEBAR =====
with st.sidebar:
    st.markdown("### PDM")
    st.caption("Contract Ingestion")

    st.markdown("---")

    # System Status
    st.markdown("##### Status")
    parser_name = "Docling" if parser._docling_available else "pdfplumber"
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.8rem;">
        <span style="width: 6px; height: 6px; background: #22C55E; border-radius: 50%;"></span>
        <span style="color: #94A3B8;">Parser</span>
        <span style="color: #64748B; margin-left: auto;">{parser_name}</span>
    </div>
    <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.8rem;">
        <span style="width: 6px; height: 6px; background: #22C55E; border-radius: 50%;"></span>
        <span style="color: #94A3B8;">ChromaDB</span>
        <span style="color: #64748B; margin-left: auto;">Ready</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Quick Stats
    st.markdown("##### Data Summary")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background: rgba(139, 92, 246, 0.1); border-radius: 6px; padding: 10px; text-align: center;">
            <div style="font-size: 1.25rem; font-weight: 600; color: #8B5CF6;">{stats.get('total_vendors', 0)}</div>
            <div style="font-size: 0.65rem; color: #64748B;">VENDORS</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div style="background: rgba(14, 165, 233, 0.1); border-radius: 6px; padding: 10px; text-align: center;">
            <div style="font-size: 1.25rem; font-weight: 600; color: #0EA5E9;">{stats.get('total_chunks', 0)}</div>
            <div style="font-size: 0.65rem; color: #64748B;">CHUNKS</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # How it works
    with st.expander("How it works", expanded=False):
        st.markdown("""
        <div style="font-size: 0.8rem; color: #94A3B8; line-height: 1.6;">
        <p><strong>1.</strong> Upload a PDF contract</p>
        <p><strong>2.</strong> Parser converts PDF to Markdown</p>
        <p><strong>3.</strong> Text is chunked into semantic segments</p>
        <p><strong>4.</strong> Chunks are embedded and stored</p>
        </div>
        """, unsafe_allow_html=True)


# ===== MAIN CONTENT =====

# Page Header
st.markdown("""
<div style="margin-bottom: 24px;">
    <h1 style="font-size: 1.75rem; font-weight: 700; color: #F8FAFC; margin-bottom: 4px; display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📋</span> Contract Ingestion
    </h1>
    <p style="font-size: 0.9rem; color: #94A3B8; margin: 0;">
        Upload and index contracts for semantic search
    </p>
</div>
""", unsafe_allow_html=True)

# Upload Section
col_upload, col_status = st.columns([2, 1])

with col_upload:
    st.markdown("""
    <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 12px;">
        Upload Contract
    </div>
    """, unsafe_allow_html=True)

    uploaded_file = st.file_uploader(
        "Drop your contract PDF here",
        type=["pdf"],
        help=f"Maximum file size: {settings.max_file_size_mb}MB",
        key="contract_uploader"
    )

    # Vendor and Contract Type
    col_vendor, col_type = st.columns([2, 1])

    with col_vendor:
        vendor_name = st.text_input(
            "Vendor Name *",
            placeholder="e.g., Acme Corporation",
            help="Required - Used to organize and retrieve contract clauses"
        )
        # Show hint if parsed but no vendor name
        if st.session_state.parsed_result and not vendor_name:
            st.markdown("""
            <div style="color: #F59E0B; font-size: 0.75rem; margin-top: -10px;">
                ⚠️ Enter vendor name to enable indexing
            </div>
            """, unsafe_allow_html=True)

    with col_type:
        contract_type = st.selectbox(
            "Type",
            options=["MSA", "SOW", "NDA", "Other"],
            format_func=lambda x: {
                "MSA": "MSA",
                "SOW": "SOW",
                "NDA": "NDA",
                "Other": "Other"
            }.get(x, x)
        )

    # Action buttons
    btn_col1, btn_col2 = st.columns(2)

    with btn_col1:
        if st.button("1. Parse PDF", disabled=not uploaded_file, use_container_width=True):
            if uploaded_file:
                with st.spinner("Parsing PDF..."):
                    save_path = settings.contracts_path / f"temp_{uploaded_file.name}"
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())

                    result = parser.parse_to_markdown(str(save_path))

                    if result.success:
                        st.session_state.parsed_result = result
                        st.session_state.current_file = uploaded_file.name
                        st.session_state.current_file_name = uploaded_file.name
                        st.rerun()
                    else:
                        st.error(f"Parsing failed: {result.error_message}")
                        st.session_state.parsed_result = None

    with btn_col2:
        # Use session state filename since uploaded_file clears after rerun
        has_parsed = st.session_state.parsed_result is not None
        has_filename = st.session_state.current_file_name is not None
        index_disabled = not (has_parsed and has_filename and vendor_name)
        if st.button("2. Index Contract", type="primary", disabled=index_disabled, use_container_width=True):
            with st.spinner("Indexing..."):
                try:
                    filename = st.session_state.current_file_name
                    contract_id = vector_store.index_contract(
                        text=st.session_state.parsed_result.markdown,
                        vendor_name=vendor_name,
                        contract_type=contract_type,
                        metadata={
                            "filename": filename,
                            "page_count": st.session_state.parsed_result.page_count,
                            "tables_found": st.session_state.parsed_result.tables_found,
                        }
                    )

                    # Rename temp file
                    temp_path = settings.contracts_path / f"temp_{filename}"
                    final_path = settings.contracts_path / f"{vendor_name}_{filename}"
                    if temp_path.exists():
                        if final_path.exists():
                            final_path.unlink()
                        temp_path.rename(final_path)

                    st.success(f"Contract indexed successfully!")
                    st.session_state.parsed_result = None
                    st.session_state.current_file_name = None
                    st.rerun()

                except Exception as e:
                    st.error(f"Indexing failed: {str(e)}")

    # Parse status
    if st.session_state.parsed_result:
        st.markdown(f"""
        <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 8px; padding: 12px; margin-top: 12px;">
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="color: #22C55E;">✓</span>
                <span style="color: #22C55E; font-size: 0.875rem;">Parsed with {st.session_state.parsed_result.parse_method}</span>
                <span style="color: #64748B; font-size: 0.75rem; margin-left: auto;">{st.session_state.parsed_result.page_count} page(s), {st.session_state.parsed_result.tables_found} table(s)</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

with col_status:
    st.markdown("""
    <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 12px;">
        Parse Results
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.parsed_result:
        result = st.session_state.parsed_result
        st.markdown(f"""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 16px;">
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
                <div style="text-align: center;">
                    <div style="font-size: 1.5rem; font-weight: 700; color: #F8FAFC;">{result.page_count}</div>
                    <div style="font-size: 0.7rem; color: #64748B; text-transform: uppercase;">Pages</div>
                </div>
                <div style="text-align: center;">
                    <div style="font-size: 1.5rem; font-weight: 700; color: #F8FAFC;">{result.tables_found}</div>
                    <div style="font-size: 0.7rem; color: #64748B; text-transform: uppercase;">Tables</div>
                </div>
            </div>
            <div style="border-top: 1px solid #334155; margin-top: 12px; padding-top: 12px; text-align: center;">
                <span style="color: #64748B; font-size: 0.75rem;">Method: {result.parse_method}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 32px; text-align: center;">
            <div style="font-size: 24px; margin-bottom: 8px; opacity: 0.5;">📄</div>
            <div style="color: #64748B; font-size: 0.8rem;">Upload and parse a PDF</div>
        </div>
        """, unsafe_allow_html=True)

# Preview Section
if st.session_state.parsed_result and st.session_state.parsed_result.success:
    st.markdown("---")
    st.markdown("""
    <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin: 16px 0 12px 0;">
        Content Preview
    </div>
    """, unsafe_allow_html=True)

    with st.expander("View parsed content", expanded=False):
        preview_text = st.session_state.parsed_result.markdown
        if len(preview_text) > 5000:
            preview_text = preview_text[:5000] + "\n\n... (truncated)"
        st.code(preview_text, language="markdown")

st.markdown("---")

# Indexed Contracts List
st.markdown("""
<div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin: 8px 0 16px 0;">
    Indexed Contracts
</div>
""", unsafe_allow_html=True)

try:
    vendors = vector_store.list_vendors()

    if vendors:
        for vendor_info in vendors:
            st.markdown(f"""
            <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
                <div>
                    <span style="color: #F8FAFC; font-weight: 500;">{vendor_info['vendor_name']}</span>
                    <span style="color: #64748B; font-size: 0.8rem; margin-left: 12px;">{vendor_info['chunk_count']} chunks</span>
                </div>
                <span style="background: rgba(139, 92, 246, 0.2); color: #8B5CF6; padding: 4px 10px; border-radius: 12px; font-size: 0.7rem; font-weight: 600;">
                    {', '.join(vendor_info.get('contract_types', ['N/A']))}
                </span>
            </div>
            """, unsafe_allow_html=True)

            if st.button("Delete", key=f"del_vendor_{vendor_info['vendor_name']}", type="secondary"):
                deleted = vector_store.delete_contract(vendor_info['vendor_name'])
                st.success(f"Deleted {deleted} chunks")
                st.rerun()
    else:
        st.markdown("""
        <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 32px; text-align: center;">
            <div style="font-size: 32px; margin-bottom: 8px; opacity: 0.5;">📋</div>
            <div style="color: #94A3B8; font-size: 0.875rem;">No contracts indexed yet</div>
            <div style="color: #64748B; font-size: 0.8rem; margin-top: 4px;">Upload a contract above to get started</div>
        </div>
        """, unsafe_allow_html=True)

except Exception as e:
    st.error(f"Could not list vendors: {e}")
