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
    page_title="Process Invoices - DocuMatch",
    page_icon="📄",
    layout="wide",
)

st.title("📄 Invoice Processing")
st.markdown("Upload invoices and validate them using **three-way matching** (Invoice ↔ PO ↔ Contract).")

st.markdown("---")

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

# Upload Section
uploaded_file = st.file_uploader(
    "Upload Invoice PDF",
    type=["pdf"],
    help=f"Maximum file size: {settings.max_file_size_mb}MB"
)

if uploaded_file:
    # Save the file
    save_path = settings.invoices_path / uploaded_file.name
    save_path.parent.mkdir(parents=True, exist_ok=True)

    with open(save_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    # Split screen layout
    left_col, right_col = st.columns(2)

    with left_col:
        st.subheader("Invoice Document")

        # Parse button
        if st.button("Parse Invoice", key="parse_btn"):
            with st.spinner("Parsing PDF..."):
                result = parser.parse_to_markdown(str(save_path))
                if result.success:
                    st.session_state.invoice_parsed = result
                    st.session_state.validation_result = None  # Reset validation
                    st.success(f"Parsed with {result.parse_method}")
                else:
                    st.error(f"Parse failed: {result.error_message}")

        # Show parsed content
        if st.session_state.invoice_parsed:
            result = st.session_state.invoice_parsed
            st.metric("Pages", result.page_count)

            with st.expander("View Parsed Content", expanded=False):
                preview = result.markdown[:5000]
                if len(result.markdown) > 5000:
                    preview += "\n\n... (truncated)"
                st.markdown(preview)
        else:
            st.info("Click 'Parse Invoice' to extract text from PDF")

        # File info
        st.markdown("---")
        st.caption(f"**File:** {uploaded_file.name}")
        st.caption(f"**Size:** {uploaded_file.size / 1024:.1f} KB")

    with right_col:
        st.subheader("Extracted Data")

        # Ollama status
        if not ollama_ok:
            st.error(f"Ollama: {ollama_msg}")
            st.info("Start Ollama with: `ollama serve`")

        # Extract button
        extract_disabled = not (st.session_state.invoice_parsed and ollama_ok)
        if st.button("Extract Invoice Data", type="primary", disabled=extract_disabled, key="extract_btn"):
            with st.spinner("Extracting data with AI..."):
                try:
                    invoice = extraction_engine.extract_invoice_data(
                        st.session_state.invoice_parsed.markdown
                    )
                    st.session_state.invoice_extracted = invoice
                    st.session_state.validation_result = None  # Reset validation
                    st.success("Extraction successful!")

                    # Automatically fetch matching clauses
                    if invoice.vendor_name:
                        clauses = vector_store.retrieve_clauses(
                            vendor_name=invoice.vendor_name,
                            query="payment terms rates",
                            top_k=5
                        )
                        st.session_state.matched_clauses = clauses

                except ExtractionError as e:
                    st.error(f"Extraction failed: {str(e)}")
                except Exception as e:
                    st.error(f"Unexpected error: {str(e)}")

        # Display extracted data
        if st.session_state.invoice_extracted:
            invoice = st.session_state.invoice_extracted

            st.markdown("---")

            # Key fields
            col1, col2 = st.columns(2)
            with col1:
                st.text_input("Vendor Name", value=invoice.vendor_name, key="vendor_edit", disabled=True)
                st.text_input("Invoice Number", value=invoice.invoice_number, key="inv_num_edit", disabled=True)
                st.text_input("Invoice Date", value=invoice.invoice_date, key="date_edit", disabled=True)

            with col2:
                st.text_input("Due Date", value=invoice.due_date or "", key="due_edit", disabled=True)
                st.text_input("Total Amount", value=f"${invoice.total_amount:,.2f}", key="total_edit", disabled=True)
                st.text_input("Currency", value=invoice.currency, key="currency_edit", disabled=True)

            # Line items
            st.markdown("#### Line Items")
            if invoice.line_items:
                items_data = [
                    {
                        "Description": item.description,
                        "Qty": item.quantity,
                        "Unit Price": f"${item.unit_price:.2f}",
                        "Total": f"${item.total:.2f}"
                    }
                    for item in invoice.line_items
                ]
                st.dataframe(items_data, use_container_width=True)
            else:
                st.info("No line items extracted")

            # Additional fields
            with st.expander("Additional Details"):
                st.text_input("Payment Terms", value=invoice.payment_terms or "", disabled=True)
                st.text_area("Billing Address", value=invoice.billing_address or "", disabled=True)

            # Raw JSON view
            with st.expander("Raw JSON"):
                st.json(invoice.model_dump())

            # PO Selection Section
            st.markdown("---")
            st.markdown("#### Link Purchase Order")

            # Get available POs for this vendor
            vendor_pos = po_store.get_pos_by_vendor(invoice.vendor_name)

            if vendor_pos:
                po_options = ["None (Skip PO matching)"] + [
                    f"{po.po_number} - ${po.total_amount:,.2f} ({po.order_date})"
                    for po in vendor_pos
                ]

                # Auto-detect PO from invoice if available
                default_index = 0
                if invoice.po_number:
                    for i, po in enumerate(vendor_pos):
                        if po.po_number.lower() == invoice.po_number.lower():
                            default_index = i + 1
                            break

                selected_po_display = st.selectbox(
                    "Select PO for Three-Way Matching",
                    options=po_options,
                    index=default_index,
                    help="Select a PO to enable full three-way matching",
                    key="po_selector"
                )

                if selected_po_display != "None (Skip PO matching)":
                    po_number = selected_po_display.split(" - ")[0]
                    st.session_state.selected_po = po_number
                else:
                    st.session_state.selected_po = None

                if invoice.po_number:
                    st.caption(f"Invoice references PO: {invoice.po_number}")
            else:
                st.info(f"No POs indexed for vendor '{invoice.vendor_name}'")
                st.caption("Go to 'Process POs' to add Purchase Orders")
                st.session_state.selected_po = None

        elif st.session_state.invoice_parsed:
            st.info("Click 'Extract Invoice Data' to process with AI")

st.markdown("---")

# Matched Clauses Section
st.subheader("Matched Contract Clauses")

if st.session_state.invoice_extracted:
    vendor_name = st.session_state.invoice_extracted.vendor_name

    # Manual search
    col_search, col_btn = st.columns([3, 1])
    with col_search:
        search_query = st.text_input(
            "Search Query",
            value="payment terms rates",
            key="clause_search",
            placeholder="e.g., payment terms, hourly rate"
        )
    with col_btn:
        if st.button("Search Clauses", key="search_clauses_btn"):
            with st.spinner("Searching..."):
                clauses = vector_store.retrieve_clauses(
                    vendor_name=vendor_name,
                    query=search_query,
                    top_k=5
                )
                st.session_state.matched_clauses = clauses

    # Display matched clauses
    if st.session_state.matched_clauses:
        st.success(f"Found {len(st.session_state.matched_clauses)} matching clauses for '{vendor_name}'")

        for i, clause in enumerate(st.session_state.matched_clauses):
            with st.expander(f"Clause {i+1} (Score: {clause.similarity_score:.2f})"):
                st.markdown(clause.text)
                st.caption(f"Contract Type: {clause.metadata.get('contract_type', 'N/A')}")
    else:
        # Check if vendor exists
        vendors = vector_store.list_vendors()
        vendor_names = [v["vendor_name"] for v in vendors]

        if vendor_name and vendor_name in vendor_names:
            st.info(f"No clauses found matching your query for '{vendor_name}'")
        elif vendor_name:
            st.warning(f"No contract indexed for vendor '{vendor_name}'")
            if vendors:
                st.info(f"Available vendors: {', '.join(vendor_names)}")
        else:
            st.info("Extract invoice data to find matching contract clauses")
else:
    st.info("Upload and extract an invoice to see matching contract clauses")

st.markdown("---")

# Three-Way Matching Section
st.subheader("Three-Way Match Validation")

if st.session_state.invoice_extracted:
    invoice = st.session_state.invoice_extracted

    # Show matching mode info
    if st.session_state.selected_po:
        st.info(f"Three-way matching: Invoice ↔ PO ({st.session_state.selected_po}) ↔ Contract")
    else:
        st.info("Two-way matching: Invoice ↔ Contract (No PO selected)")

    col_validate, col_clear = st.columns([3, 1])

    with col_validate:
        if st.button("Validate Invoice", type="primary", key="validate_btn"):
            with st.spinner("Running three-way validation..."):
                result = matcher.validate_invoice_three_way(
                    invoice=invoice,
                    po_number=st.session_state.selected_po
                )
                st.session_state.three_way_result = result
                st.session_state.matched_clauses = result.matched_clauses

    with col_clear:
        if st.button("Clear Session", key="clear_btn"):
            st.session_state.invoice_parsed = None
            st.session_state.invoice_extracted = None
            st.session_state.matched_clauses = []
            st.session_state.validation_result = None
            st.session_state.three_way_result = None
            st.session_state.selected_po = None
            st.rerun()

    # Display three-way match result
    if st.session_state.three_way_result:
        result = st.session_state.three_way_result

        st.markdown("---")

        # Status and summary row
        col_status, col_score, col_matches = st.columns(3)

        with col_status:
            st.markdown("### Overall Status")
            if result.status == "PASS":
                st.success(f"✅ {result.status}")
            elif result.status == "FAIL":
                st.error(f"❌ {result.status}")
            else:
                st.warning(f"⚠️ {result.status}")

        with col_score:
            st.markdown("### Confidence")
            st.metric("Score", f"{result.overall_score:.0%}")

        with col_matches:
            st.markdown("### Matches")
            st.metric("Passed", f"{result.matches_passed} / {result.total_matches}")

        # Three-Way Match Summary
        st.markdown("---")
        st.markdown("### Match Summary")

        match_col1, match_col2, match_col3 = st.columns(3)

        # Match 1: Invoice ↔ PO
        with match_col1:
            st.markdown("**Match 1: Invoice ↔ PO**")
            if result.invoice_po_match:
                match = result.invoice_po_match
                if match.passed:
                    st.success(f"✅ PASS ({match.score:.0%})")
                else:
                    st.error(f"❌ FAIL ({match.score:.0%})")
                if match.issues:
                    st.caption(f"{len(match.issues)} issue(s)")
            else:
                st.info("N/A - No PO linked")

        # Match 2: Invoice ↔ Contract
        with match_col2:
            st.markdown("**Match 2: Invoice ↔ Contract**")
            if result.invoice_contract_match:
                match = result.invoice_contract_match
                if match.passed:
                    st.success(f"✅ PASS ({match.score:.0%})")
                else:
                    st.error(f"❌ FAIL ({match.score:.0%})")
                if match.issues:
                    st.caption(f"{len(match.issues)} issue(s)")
            else:
                st.warning("No contract found")

        # Match 3: PO ↔ Contract
        with match_col3:
            st.markdown("**Match 3: PO ↔ Contract**")
            if result.po_contract_match:
                match = result.po_contract_match
                if match.passed:
                    st.success(f"✅ PASS ({match.score:.0%})")
                else:
                    st.error(f"❌ FAIL ({match.score:.0%})")
                if match.issues:
                    st.caption(f"{len(match.issues)} issue(s)")
            else:
                st.info("N/A - No PO linked")

        # Detailed issues by match type
        if result.all_issues:
            st.markdown("---")
            st.markdown("### All Validation Issues")

            # Group issues by match type
            for issue in result.all_issues:
                match_label = {
                    "invoice_po": "Invoice↔PO",
                    "invoice_contract": "Invoice↔Contract",
                    "po_contract": "PO↔Contract"
                }.get(issue.match_type, "General")

                if issue.severity == "critical":
                    st.error(f"[{match_label}] **{issue.rule}**: {issue.message}")
                elif issue.severity == "error":
                    st.warning(f"[{match_label}] **{issue.rule}**: {issue.message}")
                elif issue.severity == "warning":
                    st.info(f"[{match_label}] **{issue.rule}**: {issue.message}")
                else:
                    st.caption(f"[{match_label}] **{issue.rule}**: {issue.message}")

                if issue.invoice_value is not None or issue.contract_value is not None:
                    st.caption(f"  Invoice: {issue.invoice_value} | Contract/PO: {issue.contract_value}")

        # Full report
        with st.expander("Full Validation Report"):
            report = matcher.generate_three_way_report(result)
            st.code(report)

        # Download report
        report_text = matcher.generate_three_way_report(result)
        st.download_button(
            label="Download Report",
            data=report_text,
            file_name=f"three_way_report_{result.invoice_number}.txt",
            mime="text/plain"
        )

    else:
        st.info("Click 'Validate Invoice' to run three-way matching")

else:
    st.info("Extract invoice data to enable validation")

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

    # Vector store status
    try:
        stats = vector_store.get_stats()
        st.success(f"Contracts: {stats['total_vendors']} vendors")
        st.caption(f"{stats['total_chunks']} chunks indexed")
    except Exception:
        st.warning("Vector Store: Error")

    # PO store status
    try:
        po_stats = po_store.get_stats()
        st.success(f"POs: {po_stats['total_pos']} indexed")
        st.caption(f"From {po_stats['total_vendors']} vendors")
    except Exception:
        st.warning("PO Store: Error")

    st.markdown("---")

    st.markdown("### Three-Way Match Rules")
    st.markdown("""
    **Match 1: Invoice ↔ PO**
    - PO number reference
    - Line item quantities match
    - Line item prices match
    - Total amounts match

    **Match 2: Invoice ↔ Contract**
    - Rates within contract limits
    - Date within contract period
    - Contract exists for vendor

    **Match 3: PO ↔ Contract**
    - PO rates within limits
    - PO date within contract period

    **Result:** ≥2 matches pass → PASS
    """)

    st.markdown("---")

    st.markdown("### Indexed Vendors")
    try:
        vendors = vector_store.list_vendors()
        if vendors:
            for v in vendors:
                st.caption(f"- {v['vendor_name']} ({v['chunk_count']} chunks)")
        else:
            st.caption("No vendors indexed")
            st.info("Go to Contract Ingestion to add contracts")
    except Exception:
        st.caption("Could not load vendors")

    st.markdown("---")

    # Quick stats
    if st.session_state.three_way_result:
        result = st.session_state.three_way_result
        st.markdown("### Current Invoice")
        st.caption(f"Vendor: {result.vendor_name}")
        st.caption(f"Invoice: {result.invoice_number}")
        if result.po_number:
            st.caption(f"PO: {result.po_number}")
        st.caption(f"Status: {result.status}")
        st.caption(f"Matches: {result.matches_passed}/{result.total_matches}")
