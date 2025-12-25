"""
Invoice Processing Page

Upload invoices and validate them against indexed contracts and POs.
Supports three-way matching: Invoice <-> PO <-> Contract.
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
from core.matcher import Matcher
from core.models import ThreeWayMatchResult
from app.styles import inject_styles, COLORS

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
matcher = Matcher(
    vector_store=vector_store,
    po_store=po_store,
    ollama_host=settings.ollama_host,
    model=settings.default_model,
)

st.set_page_config(
    page_title="Process Invoices - PDM",
    page_icon="📄",
    layout="wide",
)

# Inject styles
inject_styles()

# Initialize session state
if "invoice_parsed" not in st.session_state:
    st.session_state.invoice_parsed = None
if "invoice_extracted" not in st.session_state:
    st.session_state.invoice_extracted = None
if "matched_clauses" not in st.session_state:
    st.session_state.matched_clauses = []
if "validation_result" not in st.session_state:
    st.session_state.validation_result = None
if "selected_po" not in st.session_state:
    st.session_state.selected_po = None
if "three_way_result" not in st.session_state:
    st.session_state.three_way_result = None

# Check Ollama status
ollama_ok, ollama_msg = extraction_engine.check_connection()

# Get stats
try:
    vs_stats = vector_store.get_stats()
    po_stats = po_store.get_stats()
except Exception:
    vs_stats = {"total_vendors": 0, "total_chunks": 0}
    po_stats = {"total_pos": 0, "total_vendors": 0}


# ===== SIDEBAR =====
with st.sidebar:
    st.markdown("### PDM")
    st.caption("Invoice Processing")

    st.markdown("---")

    # System Status - Compact
    st.markdown("##### Status")

    # Compact status rows
    status_html = ""

    # Parser
    parser_status = "Docling" if parser._docling_available else "pdfplumber"
    status_html += f"""
    <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.8rem;">
        <span style="width: 6px; height: 6px; background: #22C55E; border-radius: 50%;"></span>
        <span style="color: #94A3B8;">Parser</span>
        <span style="color: #64748B; margin-left: auto;">{parser_status}</span>
    </div>
    """

    # LLM
    if ollama_ok:
        status_html += f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.8rem;">
            <span style="width: 6px; height: 6px; background: #22C55E; border-radius: 50%;"></span>
            <span style="color: #94A3B8;">LLM</span>
            <span style="color: #64748B; margin-left: auto;">{settings.default_model}</span>
        </div>
        """
    else:
        status_html += f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 6px 0; font-size: 0.8rem;">
            <span style="width: 6px; height: 6px; background: #EF4444; border-radius: 50%;"></span>
            <span style="color: #94A3B8;">LLM</span>
            <span style="color: #EF4444; margin-left: auto;">Offline</span>
        </div>
        """

    st.markdown(status_html, unsafe_allow_html=True)

    st.markdown("---")

    # Data counts
    st.markdown("##### Data")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background: rgba(139, 92, 246, 0.1); border-radius: 6px; padding: 10px; text-align: center;">
            <div style="font-size: 1.25rem; font-weight: 600; color: #8B5CF6;">{vs_stats.get('total_vendors', 0)}</div>
            <div style="font-size: 0.65rem; color: #64748B;">CONTRACTS</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div style="background: rgba(34, 197, 94, 0.1); border-radius: 6px; padding: 10px; text-align: center;">
            <div style="font-size: 1.25rem; font-weight: 600; color: #22C55E;">{po_stats.get('total_pos', 0)}</div>
            <div style="font-size: 0.65rem; color: #64748B;">POs</div>
        </div>
        """, unsafe_allow_html=True)

    # Current session info
    if st.session_state.three_way_result:
        result = st.session_state.three_way_result
        st.markdown("---")
        st.markdown("##### Current Invoice")
        st.markdown(f"""
        <div style="font-size: 0.8rem; color: #94A3B8; padding: 8px 0;">
            <div><strong style="color: #F8FAFC;">{result.invoice_number}</strong></div>
            <div>{result.vendor_name}</div>
            {f'<div>PO: {result.po_number}</div>' if result.po_number else ''}
        </div>
        """, unsafe_allow_html=True)


# ===== MAIN CONTENT =====

# Page Header
st.markdown("""
<div style="margin-bottom: 24px;">
    <h1 style="font-size: 1.75rem; font-weight: 700; color: #F8FAFC; margin-bottom: 4px; display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📄</span> Invoice Processing
    </h1>
    <p style="font-size: 0.9rem; color: #94A3B8; margin: 0;">
        Upload invoices and validate with three-way matching
    </p>
</div>
""", unsafe_allow_html=True)

# Progress indicator based on current state
current_step = 0
if st.session_state.invoice_parsed:
    current_step = 1
if st.session_state.invoice_extracted:
    current_step = 2
if st.session_state.three_way_result:
    current_step = 3

steps = ["Upload", "Parse", "Extract", "Validate"]
step_html = '<div style="display: flex; align-items: center; justify-content: center; gap: 8px; padding: 16px 0; margin-bottom: 24px;">'
for i, step in enumerate(steps):
    if i < current_step:
        color = "#22C55E"
        bg = "rgba(34, 197, 94, 0.2)"
        icon = "✓"
    elif i == current_step:
        color = "#0EA5E9"
        bg = "rgba(14, 165, 233, 0.2)"
        icon = str(i + 1)
    else:
        color = "#64748B"
        bg = "#334155"
        icon = str(i + 1)

    step_html += f'''
    <div style="display: flex; align-items: center; gap: 6px;">
        <div style="width: 28px; height: 28px; background: {bg}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: {color}; font-size: 0.75rem; font-weight: 600;">{icon}</div>
        <span style="color: {color}; font-size: 0.8rem; font-weight: 500;">{step}</span>
    </div>
    '''
    if i < len(steps) - 1:
        line_color = "#22C55E" if i < current_step else "#334155"
        step_html += f'<div style="width: 40px; height: 2px; background: {line_color}; border-radius: 1px;"></div>'
step_html += '</div>'
st.markdown(step_html, unsafe_allow_html=True)

# ===== UPLOAD & EXTRACTION SECTION =====
uploaded_file = st.file_uploader(
    "Drop your invoice PDF here",
    type=["pdf"],
    help=f"Maximum file size: {settings.max_file_size_mb}MB",
    key="invoice_uploader"
)

if uploaded_file:
    # Save the file
    save_path = settings.invoices_path / uploaded_file.name
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Two column layout
    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("""
        <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin: 16px 0 12px 0;">
            Document Processing
        </div>
        """, unsafe_allow_html=True)

        # File info card
        st.markdown(f"""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 16px; margin-bottom: 16px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="width: 40px; height: 40px; background: rgba(14, 165, 233, 0.2); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 20px;">📄</div>
                <div>
                    <div style="color: #F8FAFC; font-weight: 500; font-size: 0.875rem;">{uploaded_file.name}</div>
                    <div style="color: #64748B; font-size: 0.75rem;">{uploaded_file.size / 1024:.1f} KB</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Parse & Extract buttons
        btn_col1, btn_col2 = st.columns(2)

        with btn_col1:
            if st.button("1. Parse PDF", key="parse_btn", use_container_width=True,
                        disabled=st.session_state.invoice_parsed is not None):
                with st.spinner("Parsing..."):
                    result = parser.parse_to_markdown(str(save_path))
                    if result.success:
                        st.session_state.invoice_parsed = result
                        st.session_state.invoice_extracted = None
                        st.session_state.three_way_result = None
                        st.rerun()
                    else:
                        st.error(f"Parse failed: {result.error_message}")

        with btn_col2:
            extract_disabled = not (st.session_state.invoice_parsed and ollama_ok)
            if st.button("2. Extract Data", key="extract_btn", use_container_width=True,
                        disabled=extract_disabled, type="primary"):
                with st.spinner("Extracting with AI..."):
                    try:
                        invoice = extraction_engine.extract_invoice_data(
                            st.session_state.invoice_parsed.markdown
                        )
                        st.session_state.invoice_extracted = invoice
                        st.session_state.three_way_result = None

                        # Auto-fetch clauses
                        if invoice.vendor_name:
                            clauses = vector_store.retrieve_clauses(
                                vendor_name=invoice.vendor_name,
                                query="payment terms rates",
                                top_k=5
                            )
                            st.session_state.matched_clauses = clauses
                        st.rerun()
                    except Exception as e:
                        st.error(f"Extraction failed: {str(e)}")

        # Parse status
        if st.session_state.invoice_parsed:
            st.markdown(f"""
            <div style="background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 8px; padding: 12px; margin-top: 8px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="color: #22C55E;">✓</span>
                    <span style="color: #22C55E; font-size: 0.875rem;">Parsed with {st.session_state.invoice_parsed.parse_method}</span>
                    <span style="color: #64748B; font-size: 0.75rem; margin-left: auto;">{st.session_state.invoice_parsed.page_count} page(s)</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            with st.expander("View parsed content"):
                preview = st.session_state.invoice_parsed.markdown[:3000]
                if len(st.session_state.invoice_parsed.markdown) > 3000:
                    preview += "\n\n... (truncated)"
                st.code(preview, language="markdown")

    with col_right:
        st.markdown("""
        <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin: 16px 0 12px 0;">
            Extracted Invoice Data
        </div>
        """, unsafe_allow_html=True)

        if st.session_state.invoice_extracted:
            invoice = st.session_state.invoice_extracted

            # Invoice summary card
            st.markdown(f"""
            <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 16px;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">Vendor</div>
                        <div style="color: #F8FAFC; font-weight: 600;">{invoice.vendor_name}</div>
                    </div>
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">Invoice #</div>
                        <div style="color: #F8FAFC; font-weight: 600;">{invoice.invoice_number}</div>
                    </div>
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">Date</div>
                        <div style="color: #94A3B8;">{invoice.invoice_date}</div>
                    </div>
                    <div>
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 4px;">Total</div>
                        <div style="color: #0EA5E9; font-weight: 700; font-size: 1.25rem;">${invoice.total_amount:,.2f}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Line items
            if invoice.line_items:
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
                    for item in invoice.line_items
                ]
                st.dataframe(items_data, use_container_width=True, hide_index=True)

            # PO Selection
            st.markdown("---")
            vendor_pos = po_store.get_pos_by_vendor(invoice.vendor_name)

            if vendor_pos:
                po_options = ["No PO (two-way match only)"] + [
                    f"{po.po_number} (${po.total_amount:,.2f})"
                    for po in vendor_pos
                ]

                default_index = 0
                if invoice.po_number:
                    for i, po in enumerate(vendor_pos):
                        if po.po_number.lower() == invoice.po_number.lower():
                            default_index = i + 1
                            break

                selected = st.selectbox(
                    "Link Purchase Order",
                    options=po_options,
                    index=default_index,
                    key="po_selector"
                )

                if selected != "No PO (two-way match only)":
                    st.session_state.selected_po = selected.split(" (")[0]
                else:
                    st.session_state.selected_po = None
            else:
                st.markdown(f"""
                <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 12px;">
                    <div style="color: #F59E0B; font-size: 0.8rem;">No POs found for this vendor</div>
                    <div style="color: #94A3B8; font-size: 0.75rem;">Two-way matching will be used</div>
                </div>
                """, unsafe_allow_html=True)
                st.session_state.selected_po = None

        else:
            # Empty state
            st.markdown("""
            <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 40px; text-align: center;">
                <div style="font-size: 32px; margin-bottom: 12px; opacity: 0.5;">📋</div>
                <div style="color: #64748B; font-size: 0.875rem;">Extract invoice data to see details here</div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("---")

# ===== VALIDATION SECTION =====
st.markdown("""
<div style="font-size: 1.125rem; font-weight: 600; color: #F8FAFC; margin: 8px 0 16px 0; display: flex; align-items: center; gap: 8px;">
    <span>Three-Way Validation</span>
</div>
""", unsafe_allow_html=True)

if st.session_state.invoice_extracted:
    invoice = st.session_state.invoice_extracted

    # Validation controls
    col_btn, col_info = st.columns([1, 2])

    with col_btn:
        if st.button("🔍 Validate Invoice", type="primary", key="validate_btn", use_container_width=True):
            with st.spinner("Running three-way validation..."):
                result = matcher.validate_invoice_three_way(
                    invoice=invoice,
                    po_number=st.session_state.selected_po
                )
                st.session_state.three_way_result = result
                st.session_state.matched_clauses = result.matched_clauses
                st.rerun()

    with col_info:
        if st.session_state.selected_po:
            st.markdown(f"""
            <div style="background: rgba(14, 165, 233, 0.1); border-radius: 8px; padding: 12px; display: flex; align-items: center; gap: 8px;">
                <span style="color: #0EA5E9;">📦</span>
                <span style="color: #94A3B8; font-size: 0.85rem;">Three-way: Invoice ↔ <strong style="color: #F8FAFC;">{st.session_state.selected_po}</strong> ↔ Contract</span>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="background: rgba(100, 116, 139, 0.1); border-radius: 8px; padding: 12px; display: flex; align-items: center; gap: 8px;">
                <span style="color: #64748B;">📋</span>
                <span style="color: #94A3B8; font-size: 0.85rem;">Two-way: Invoice ↔ Contract (no PO selected)</span>
            </div>
            """, unsafe_allow_html=True)

    # ===== VALIDATION RESULTS =====
    if st.session_state.three_way_result:
        result = st.session_state.three_way_result

        st.markdown("---")

        # Hero Result Section
        if result.status == "PASS":
            status_color = "#22C55E"
            status_bg = "rgba(34, 197, 94, 0.1)"
            status_icon = "✅"
            status_text = "Approved"
        elif result.status == "FAIL":
            status_color = "#EF4444"
            status_bg = "rgba(239, 68, 68, 0.1)"
            status_icon = "❌"
            status_text = "Failed"
        else:
            status_color = "#F59E0B"
            status_bg = "rgba(245, 158, 11, 0.1)"
            status_icon = "⚠️"
            status_text = "Review Required"

        st.markdown(f"""
        <div style="background: {status_bg}; border: 1px solid {status_color}33; border-radius: 16px; padding: 32px; text-align: center; margin: 16px 0;">
            <div style="font-size: 48px; margin-bottom: 8px;">{status_icon}</div>
            <div style="font-size: 1.75rem; font-weight: 700; color: {status_color}; margin-bottom: 8px;">{status_text}</div>
            <div style="color: #94A3B8; font-size: 1rem;">
                {result.matches_passed}/{result.total_matches} matches passed · {result.overall_score:.0%} confidence
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Match Cards
        st.markdown("""
        <div style="color: #94A3B8; font-size: 0.85rem; font-weight: 500; margin: 24px 0 12px 0; text-transform: uppercase; letter-spacing: 0.5px;">
            Match Details
        </div>
        """, unsafe_allow_html=True)

        match_cols = st.columns(3)

        # Match 1: Invoice ↔ PO
        with match_cols[0]:
            if result.invoice_po_match:
                m = result.invoice_po_match
                if m.passed:
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(34, 197, 94, 0.1) 0%, #1E293B 100%); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">Invoice ↔ PO</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #22C55E; margin-bottom: 4px;">✓ PASS</div>
                        <div style="color: #64748B; font-size: 0.85rem;">{m.score:.0%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(239, 68, 68, 0.1) 0%, #1E293B 100%); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">Invoice ↔ PO</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #EF4444; margin-bottom: 4px;">✗ FAIL</div>
                        <div style="color: #64748B; font-size: 0.85rem;">{m.score:.0%}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">Invoice ↔ PO</div>
                    <div style="font-size: 1.25rem; font-weight: 600; color: #64748B; margin-bottom: 4px;">N/A</div>
                    <div style="color: #475569; font-size: 0.8rem;">No PO linked</div>
                </div>
                """, unsafe_allow_html=True)

        # Match 2: Invoice ↔ Contract
        with match_cols[1]:
            if result.invoice_contract_match:
                m = result.invoice_contract_match
                if m.passed:
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(34, 197, 94, 0.1) 0%, #1E293B 100%); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">Invoice ↔ Contract</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #22C55E; margin-bottom: 4px;">✓ PASS</div>
                        <div style="color: #64748B; font-size: 0.85rem;">{m.score:.0%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(239, 68, 68, 0.1) 0%, #1E293B 100%); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">Invoice ↔ Contract</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #EF4444; margin-bottom: 4px;">✗ FAIL</div>
                        <div style="color: #64748B; font-size: 0.85rem;">{m.score:.0%}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">Invoice ↔ Contract</div>
                    <div style="font-size: 1.25rem; font-weight: 600; color: #F59E0B; margin-bottom: 4px;">Missing</div>
                    <div style="color: #475569; font-size: 0.8rem;">No contract found</div>
                </div>
                """, unsafe_allow_html=True)

        # Match 3: PO ↔ Contract
        with match_cols[2]:
            if result.po_contract_match:
                m = result.po_contract_match
                if m.passed:
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(34, 197, 94, 0.1) 0%, #1E293B 100%); border: 1px solid rgba(34, 197, 94, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">PO ↔ Contract</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #22C55E; margin-bottom: 4px;">✓ PASS</div>
                        <div style="color: #64748B; font-size: 0.85rem;">{m.score:.0%}</div>
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(f"""
                    <div style="background: linear-gradient(180deg, rgba(239, 68, 68, 0.1) 0%, #1E293B 100%); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">PO ↔ Contract</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #EF4444; margin-bottom: 4px;">✗ FAIL</div>
                        <div style="color: #64748B; font-size: 0.85rem;">{m.score:.0%}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.markdown("""
                <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center;">
                    <div style="color: #64748B; font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px;">PO ↔ Contract</div>
                    <div style="font-size: 1.25rem; font-weight: 600; color: #64748B; margin-bottom: 4px;">N/A</div>
                    <div style="color: #475569; font-size: 0.8rem;">No PO linked</div>
                </div>
                """, unsafe_allow_html=True)

        # Issues Section
        if result.all_issues:
            st.markdown("---")

            # Count issues by severity
            critical_count = sum(1 for i in result.all_issues if i.severity == "critical")
            error_count = sum(1 for i in result.all_issues if i.severity == "error")
            warning_count = sum(1 for i in result.all_issues if i.severity == "warning")
            info_count = sum(1 for i in result.all_issues if i.severity == "info")

            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
                <span style="color: #94A3B8; font-size: 0.85rem; font-weight: 500;">Issues Found:</span>
                {f'<span style="background: rgba(239, 68, 68, 0.2); color: #EF4444; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">{critical_count} Critical</span>' if critical_count else ''}
                {f'<span style="background: rgba(249, 115, 22, 0.2); color: #F97316; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">{error_count} Error</span>' if error_count else ''}
                {f'<span style="background: rgba(245, 158, 11, 0.2); color: #F59E0B; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">{warning_count} Warning</span>' if warning_count else ''}
                {f'<span style="background: rgba(59, 130, 246, 0.2); color: #3B82F6; padding: 4px 10px; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">{info_count} Info</span>' if info_count else ''}
            </div>
            """, unsafe_allow_html=True)

            with st.expander("View all issues", expanded=critical_count > 0 or error_count > 0):
                for issue in result.all_issues:
                    colors = {
                        "critical": ("#EF4444", "rgba(239, 68, 68, 0.1)"),
                        "error": ("#F97316", "rgba(249, 115, 22, 0.1)"),
                        "warning": ("#F59E0B", "rgba(245, 158, 11, 0.1)"),
                        "info": ("#3B82F6", "rgba(59, 130, 246, 0.1)")
                    }
                    color, bg = colors.get(issue.severity, ("#64748B", "rgba(100, 116, 139, 0.1)"))

                    st.markdown(f"""
                    <div style="background: {bg}; border-left: 3px solid {color}; padding: 12px 16px; margin-bottom: 8px; border-radius: 0 8px 8px 0;">
                        <div style="color: {color}; font-size: 0.8rem; font-weight: 600; margin-bottom: 4px;">{issue.severity.upper()}: {issue.rule}</div>
                        <div style="color: #94A3B8; font-size: 0.85rem;">{issue.message}</div>
                    </div>
                    """, unsafe_allow_html=True)

        # Download & Actions
        st.markdown("---")
        col_dl, col_clear = st.columns([1, 1])

        with col_dl:
            report_text = matcher.generate_three_way_report(result)
            st.download_button(
                label="📥 Download Report",
                data=report_text,
                file_name=f"validation_report_{result.invoice_number}.txt",
                mime="text/plain",
                use_container_width=True
            )

        with col_clear:
            if st.button("🔄 Start New", key="clear_btn", use_container_width=True):
                st.session_state.invoice_parsed = None
                st.session_state.invoice_extracted = None
                st.session_state.matched_clauses = []
                st.session_state.validation_result = None
                st.session_state.three_way_result = None
                st.session_state.selected_po = None
                st.rerun()

else:
    # Empty state for validation
    st.markdown("""
    <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 12px; padding: 48px; text-align: center;">
        <div style="font-size: 40px; margin-bottom: 12px; opacity: 0.5;">🔍</div>
        <div style="color: #94A3B8; font-size: 0.9rem;">Upload and extract an invoice to enable validation</div>
    </div>
    """, unsafe_allow_html=True)
