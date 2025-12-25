"""
Purchase Order Processing Page

Upload POs and index them for three-way matching with invoices.
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
from core.po_store import POStore
from core.extraction import ExtractionEngine, ExtractionError
from app.styles import inject_styles

# Initialize components
parser = ParserEngine(fallback_enabled=settings.parser_fallback_enabled)
vector_store = VectorStore(
    persist_directory=str(settings.chroma_path),
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
)
po_store = POStore(persist_directory=str(settings.chroma_path))
extraction_engine = ExtractionEngine(
    model=settings.default_model,
    ollama_host=settings.ollama_host,
)

st.set_page_config(
    page_title="Process POs - PDM",
    page_icon="📦",
    layout="wide",
)

# Inject styles
inject_styles()

# Initialize session state
if "po_parsed" not in st.session_state:
    st.session_state.po_parsed = None
if "po_extracted" not in st.session_state:
    st.session_state.po_extracted = None
if "po_file_path" not in st.session_state:
    st.session_state.po_file_path = None
if "po_file_name" not in st.session_state:
    st.session_state.po_file_name = None
if "po_vendor" not in st.session_state:
    st.session_state.po_vendor = None

# Check Ollama status
ollama_ok, ollama_msg = extraction_engine.check_connection()

# Get list of vendors from indexed contracts
vendors = vector_store.list_vendors()
vendor_names = [v["vendor_name"] for v in vendors]

# Get PO stats
try:
    po_stats = po_store.get_stats()
except Exception:
    po_stats = {"total_pos": 0, "total_vendors": 0}


# ===== SIDEBAR =====
with st.sidebar:
    st.markdown("### PDM")
    st.caption("PO Processing")

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
    """, unsafe_allow_html=True)

    if ollama_ok:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.8rem;">
            <span style="width: 6px; height: 6px; background: #22C55E; border-radius: 50%;"></span>
            <span style="color: #94A3B8;">LLM</span>
            <span style="color: #64748B; margin-left: auto;">{settings.default_model}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.8rem;">
            <span style="width: 6px; height: 6px; background: #EF4444; border-radius: 50%;"></span>
            <span style="color: #94A3B8;">LLM</span>
            <span style="color: #EF4444; margin-left: auto;">Offline</span>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Data counts
    st.markdown("##### Data Summary")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background: rgba(34, 197, 94, 0.1); border-radius: 6px; padding: 10px; text-align: center;">
            <div style="font-size: 1.25rem; font-weight: 600; color: #22C55E;">{po_stats.get('total_pos', 0)}</div>
            <div style="font-size: 0.65rem; color: #64748B;">POs</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div style="background: rgba(139, 92, 246, 0.1); border-radius: 6px; padding: 10px; text-align: center;">
            <div style="font-size: 1.25rem; font-weight: 600; color: #8B5CF6;">{len(vendor_names)}</div>
            <div style="font-size: 0.65rem; color: #64748B;">VENDORS</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Workflow steps
    with st.expander("Workflow", expanded=False):
        st.markdown("""
        <div style="font-size: 0.8rem; color: #94A3B8; line-height: 1.6;">
        <p><strong>1.</strong> Ensure contract is indexed</p>
        <p><strong>2.</strong> Upload PO PDF</p>
        <p><strong>3.</strong> Parse and extract data</p>
        <p><strong>4.</strong> Index PO for matching</p>
        </div>
        """, unsafe_allow_html=True)


# ===== MAIN CONTENT =====

# Page Header
st.markdown("""
<div style="margin-bottom: 24px;">
    <h1 style="font-size: 1.75rem; font-weight: 700; color: #F8FAFC; margin-bottom: 4px; display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📦</span> Purchase Order Processing
    </h1>
    <p style="font-size: 0.9rem; color: #94A3B8; margin: 0;">
        Upload and index POs for three-way invoice matching
    </p>
</div>
""", unsafe_allow_html=True)

# Upload Section
col_upload, col_vendor = st.columns([2, 1])

with col_upload:
    uploaded_file = st.file_uploader(
        "Drop your PO PDF here",
        type=["pdf"],
        help=f"Maximum file size: {settings.max_file_size_mb}MB",
        key="po_uploader"
    )

with col_vendor:
    st.markdown("""
    <div style="font-size: 0.85rem; font-weight: 500; color: #94A3B8; margin-bottom: 8px;">
        Select Vendor
    </div>
    """, unsafe_allow_html=True)

    if vendor_names:
        selected_vendor = st.selectbox(
            "Vendor",
            options=vendor_names,
            help="Select the vendor for this PO",
            label_visibility="collapsed"
        )
    else:
        st.markdown("""
        <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 12px;">
            <div style="color: #F59E0B; font-size: 0.85rem; font-weight: 500;">No contracts indexed</div>
            <div style="color: #94A3B8; font-size: 0.75rem;">Add contracts first in Contract Ingestion</div>
        </div>
        """, unsafe_allow_html=True)
        selected_vendor = None

# Store file info in session state when new file is uploaded
if uploaded_file and selected_vendor:
    po_dir = settings.purchase_orders_path
    po_dir.mkdir(parents=True, exist_ok=True)
    save_path = po_dir / uploaded_file.name

    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Store in session state for persistence across reruns
    st.session_state.po_file_path = str(save_path)
    st.session_state.po_file_name = uploaded_file.name
    st.session_state.po_vendor = selected_vendor

# Show processing section if we have file info (either from upload or session state)
has_po_file = st.session_state.po_file_path is not None
current_vendor = st.session_state.po_vendor or selected_vendor

if has_po_file and current_vendor:

    st.markdown("---")

    # Two column layout
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("""
        <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 12px;">
            Document Processing
        </div>
        """, unsafe_allow_html=True)

        # File info card
        file_name = st.session_state.po_file_name
        st.markdown(f"""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="width: 40px; height: 40px; background: rgba(34, 197, 94, 0.2); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 20px;">📦</div>
                <div>
                    <div style="color: #F8FAFC; font-weight: 500; font-size: 0.875rem;">{file_name}</div>
                    <div style="color: #64748B; font-size: 0.75rem;">{current_vendor}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Buttons
        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("1. Parse PO", key="parse_po_btn", use_container_width=True,
                        disabled=st.session_state.po_parsed is not None):
                with st.spinner("Parsing..."):
                    result = parser.parse_to_markdown(st.session_state.po_file_path)
                    if result.success:
                        st.session_state.po_parsed = result
                        st.session_state.po_extracted = None
                        st.rerun()
                    else:
                        st.error(f"Parse failed: {result.error_message}")

        with btn_col2:
            extract_disabled = not (st.session_state.po_parsed and ollama_ok)
            if st.button("2. Extract Data", key="extract_po_btn", use_container_width=True,
                        disabled=extract_disabled, type="primary"):
                with st.spinner("Extracting with AI..."):
                    try:
                        po = extraction_engine.extract_po_data(
                            st.session_state.po_parsed.markdown
                        )
                        po.vendor_name = current_vendor
                        st.session_state.po_extracted = po
                        st.rerun()
                    except Exception as e:
                        st.error(f"Extraction failed: {str(e)}")

        # Parse status
        if st.session_state.po_parsed:
            st.markdown(f"""
            <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 8px; padding: 12px; margin-top: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #22C55E;">✓</span>
                    <span style="color: #22C55E; font-size: 0.875rem;">Parsed with {st.session_state.po_parsed.parse_method}</span>
                    <span style="color: #64748B; font-size: 0.75rem; margin-left: auto;">{st.session_state.po_parsed.page_count} page(s)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("View parsed content"):
                preview = st.session_state.po_parsed.markdown[:3000]
                if len(st.session_state.po_parsed.markdown) > 3000:
                    preview += "\n\n... (truncated)"
                st.code(preview, language="markdown")

    with col_right:
        st.markdown("""
        <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 12px;">
            Extracted PO Data
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.po_extracted:
            po = st.session_state.po_extracted

            # PO summary card
            st.markdown(f"""
            <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 16px;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">PO Number</div>
                        <div style="color: #F8FAFC; font-weight: 600;">{po.po_number}</div>
                    </div>
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">Vendor</div>
                        <div style="color: #F8FAFC; font-weight: 600;">{po.vendor_name}</div>
                    </div>
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">Order Date</div>
                        <div style="color: #94A3B8;">{po.order_date}</div>
                    </div>
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">Total</div>
                        <div style="color: #22C55E; font-weight: 700; font-size: 1.25rem;">${po.total_amount:,.2f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Line items
            if po.line_items:
                st.markdown("""
                <div style="color: #94A3B8; font-size: 0.8rem; font-weight: 500; margin: 16px 0 8px 0;">
                    Line Items
                </div>
                """, unsafe_allow_html=True)

                items_data = [
                    {
                        "Description": item.description[:30] + "..." if len(item.description) > 30 else item.description,
                        "Qty": item.quantity,
                        "Rate": f"${item.unit_price:.2f}",
                        "Total": f"${item.total:.2f}"
                    }
                    for item in po.line_items
                ]
                st.dataframe(items_data, use_container_width=True, hide_index=True)

            # Index button
            st.markdown("---")
            if st.button("📥 Index PO", type="primary", key="index_po_btn", use_container_width=True):
                with st.spinner("Indexing..."):
                    try:
                        po_store.index_po(po)
                        st.success(f"PO {po.po_number} indexed successfully!")
                        # Clear all session state
                        st.session_state.po_parsed = None
                        st.session_state.po_extracted = None
                        st.session_state.po_file_path = None
                        st.session_state.po_file_name = None
                        st.session_state.po_vendor = None
                        st.rerun()
                    except Exception as e:
                        st.error(f"Indexing failed: {str(e)}")
        else:
            # Empty state
            st.markdown("""
            <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 40px; text-align: center;">
                <div style="font-size: 32px; margin-bottom: 12px; opacity: 0.5;">📋</div>
                <div style="color: #64748B; font-size: 0.875rem;">Extract PO data to see details here</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")

# Indexed POs Section
st.markdown("""
<div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin: 8px 0 16px 0;">
    Indexed Purchase Orders
</div>
""", unsafe_allow_html=True)

indexed_pos = po_store.list_pos()

if indexed_pos:
    search_query = st.text_input("Search POs", placeholder="Search by PO number or vendor...", label_visibility="collapsed")

    if search_query:
        filtered_pos = [
            po for po in indexed_pos
            if search_query.lower() in po["po_number"].lower()
            or search_query.lower() in po["vendor_name"].lower()
        ]
    else:
        filtered_pos = indexed_pos

    st.caption(f"Showing {len(filtered_pos)} of {len(indexed_pos)} POs")

    for po in filtered_pos:
        st.markdown(f"""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 16px;">
                <span style="color: #F8FAFC; font-weight: 600;">{po['po_number']}</span>
                <span style="color: #64748B; font-size: 0.85rem;">{po['vendor_name']}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 16px;">
                <span style="color: #22C55E; font-weight: 600;">${po['total_amount']:,.2f}</span>
                <span style="color: #64748B; font-size: 0.8rem;">{po['order_date']}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if st.button("Delete", key=f"del_{po['po_number']}", type="secondary"):
            if po_store.delete_po(po["po_number"]):
                st.success(f"Deleted PO {po['po_number']}")
                st.rerun()
            else:
                st.error("Delete failed")
else:
    st.markdown("""
    <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 32px; text-align: center;">
        <div style="font-size: 32px; margin-bottom: 8px; opacity: 0.5;">📦</div>
        <div style="color: #94A3B8; font-size: 0.875rem;">No Purchase Orders indexed yet</div>
        <div style="color: #64748B; font-size: 0.8rem; margin-top: 4px;">Upload and index a PO above</div>
    </div>
    """, unsafe_allow_html=True)
