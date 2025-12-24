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
    page_title="Process POs - DocuMatch",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Purchase Order Processing")
st.markdown("Upload and index Purchase Orders for three-way invoice validation.")

st.markdown("---")

# Initialize session state
if "po_parsed" not in st.session_state:
    st.session_state.po_parsed = None
if "po_extracted" not in st.session_state:
    st.session_state.po_extracted = None

# Check Ollama status
ollama_ok, ollama_msg = extraction_engine.check_connection()

# Get list of vendors from indexed contracts
vendors = vector_store.list_vendors()
vendor_names = [v["vendor_name"] for v in vendors]

# Upload Section
col_upload, col_vendor = st.columns([2, 1])

with col_upload:
    uploaded_file = st.file_uploader(
        "Upload Purchase Order PDF",
        type=["pdf"],
        help=f"Maximum file size: {settings.max_file_size_mb}MB"
    )

with col_vendor:
    if vendor_names:
        selected_vendor = st.selectbox(
            "Select Vendor",
            options=vendor_names,
            help="Select the vendor for this PO (must have contract indexed)"
        )
    else:
        st.warning("No contracts indexed yet")
        st.info("Go to Contract Ingestion first")
        selected_vendor = None

if uploaded_file and selected_vendor:
    # Save the file
    po_dir = settings.data_path / "purchase_orders"
    po_dir.mkdir(parents=True, exist_ok=True)
    save_path = po_dir / uploaded_file.name

    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Split screen layout
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("PO Document")

        # Parse button
        if st.button("Parse PO", key="parse_po_btn"):
            with st.spinner("Parsing PDF..."):
                result = parser.parse_to_markdown(str(save_path))
                if result.success:
                    st.session_state.po_parsed = result
                    st.session_state.po_extracted = None  # Reset extraction
                    st.success(f"Parsed with {result.parse_method}")
                else:
                    st.error(f"Parse failed: {result.error_message}")

        # Show parsed content
        if st.session_state.po_parsed:
            result = st.session_state.po_parsed
            st.metric("Pages", result.page_count)

            with st.expander("View Parsed Content", expanded=False):
                preview = result.markdown[:5000]
                if len(result.markdown) > 5000:
                    preview += "\n\n... (truncated)"
                st.markdown(preview)
        else:
            st.info("Click 'Parse PO' to extract text from PDF")

        # File info
        st.markdown("---")
        st.caption(f"**File:** {uploaded_file.name}")
        st.caption(f"**Size:** {uploaded_file.size / 1024:.1f} KB")
        st.caption(f"**Vendor:** {selected_vendor}")

    with right_col:
        st.subheader("Extracted PO Data")

        # Ollama status
        if not ollama_ok:
            st.error(f"Ollama: {ollama_msg}")
            st.info("Start Ollama with: `ollama serve`")

        # Extract button
        extract_disabled = not (st.session_state.po_parsed and ollama_ok)
        if st.button("Extract PO Data", type="primary", disabled=extract_disabled, key="extract_po_btn"):
            with st.spinner("Extracting data with AI..."):
                try:
                    po = extraction_engine.extract_po_data(
                        st.session_state.po_parsed.markdown
                    )
                    # Override vendor name with selected vendor
                    po.vendor_name = selected_vendor
                    st.session_state.po_extracted = po
                    st.success("Extraction successful!")

                except ExtractionError as e:
                    st.error(f"Extraction failed: {str(e)}")
                except Exception as e:
                    st.error(f"Unexpected error: {str(e)}")

        # Display extracted data
        if st.session_state.po_extracted:
            po = st.session_state.po_extracted

            st.markdown("---")

            # Key fields
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("PO Number", value=po.po_number, key="po_num_edit", disabled=True)
                st.text_input("Vendor Name", value=po.vendor_name, key="vendor_edit", disabled=True)
                st.text_input("Order Date", value=po.order_date, key="order_date_edit", disabled=True)

            with col2:
                st.text_input("Expected Delivery", value=po.expected_delivery_date or "", key="delivery_edit", disabled=True)
                st.text_input("Total Amount", value=f"${po.total_amount:,.2f}", key="total_edit", disabled=True)
                st.text_input("Currency", value=po.currency, key="currency_edit", disabled=True)

            # Line items
            st.markdown("#### Line Items")
            if po.line_items:
                items_data = [
                    {
                        "Description": item.description,
                        "Qty": item.quantity,
                        "Unit Price": f"${item.unit_price:.2f}",
                        "Total": f"${item.total:.2f}"
                    }
                    for item in po.line_items
                ]
                st.dataframe(items_data, use_container_width=True)
            else:
                st.info("No line items extracted")

            # Additional fields
            with st.expander("Additional Details"):
                st.text_input("Payment Terms", value=po.payment_terms or "", disabled=True)
                st.text_input("Contract Reference", value=po.contract_reference or "", disabled=True)
                st.text_area("Billing Address", value=po.billing_address or "", disabled=True)
                st.text_area("Shipping Address", value=po.shipping_address or "", disabled=True)

            # Raw JSON view
            with st.expander("Raw JSON"):
                st.json(po.model_dump())

            # Index PO button
            st.markdown("---")
            if st.button("Index PO", type="primary", key="index_po_btn"):
                with st.spinner("Indexing PO..."):
                    try:
                        po_store.index_po(po)
                        st.success(f"PO {po.po_number} indexed successfully!")
                        # Clear session state for next upload
                        st.session_state.po_parsed = None
                        st.session_state.po_extracted = None
                    except Exception as e:
                        st.error(f"Indexing failed: {str(e)}")

        elif st.session_state.po_parsed:
            st.info("Click 'Extract PO Data' to process with AI")

st.markdown("---")

# Indexed POs Section
st.subheader("Indexed Purchase Orders")

# Get all indexed POs
indexed_pos = po_store.list_pos()

if indexed_pos:
    # Search/filter
    search_query = st.text_input("Search POs", placeholder="Search by PO number or vendor...")

    # Filter POs based on search
    if search_query:
        filtered_pos = [
            po for po in indexed_pos
            if search_query.lower() in po["po_number"].lower()
            or search_query.lower() in po["vendor_name"].lower()
        ]
    else:
        filtered_pos = indexed_pos

    st.caption(f"Showing {len(filtered_pos)} of {len(indexed_pos)} POs")

    # Display POs
    for po in filtered_pos:
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

        with col1:
            st.markdown(f"**{po['po_number']}**")
        with col2:
            st.caption(po["vendor_name"])
        with col3:
            st.caption(f"${po['total_amount']:,.2f} | {po['order_date']}")
        with col4:
            if st.button("Delete", key=f"del_{po['po_number']}", type="secondary"):
                if po_store.delete_po(po["po_number"]):
                    st.success(f"Deleted PO {po['po_number']}")
                    st.rerun()
                else:
                    st.error("Delete failed")
else:
    st.info("No Purchase Orders indexed yet. Upload and index a PO above.")

# Sidebar
with st.sidebar:
    st.markdown("### System Status")

    # Parser status
    if parser._docling_available:
        st.success("Parser: Docling")
    else:
        st.warning("Parser: pdfplumber")

    # Ollama status
    if ollama_ok:
        st.success(f"LLM: {settings.default_model}")
    else:
        st.error("LLM: Offline")
        st.caption(ollama_msg)

    # PO Store status
    try:
        stats = po_store.get_stats()
        st.success(f"POs: {stats['total_pos']} indexed")
        st.caption(f"From {stats['total_vendors']} vendors")
    except Exception:
        st.warning("PO Store: Error")

    st.markdown("---")

    st.markdown("### Workflow")
    st.markdown("""
    **Step 1:** Ensure contract is indexed for vendor

    **Step 2:** Upload PO PDF

    **Step 3:** Parse and extract PO data

    **Step 4:** Review and index PO

    **Step 5:** Go to Invoice Processing for three-way matching
    """)

    st.markdown("---")

    st.markdown("### Indexed Vendors")
    try:
        if vendors:
            for v in vendors:
                st.caption(f"- {v['vendor_name']} ({v['chunk_count']} chunks)")
        else:
            st.caption("No vendors indexed")
            st.info("Go to Contract Ingestion to add contracts")
    except Exception:
        st.caption("Could not load vendors")
