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
from core.po_store import POStore
from app.styles import inject_styles, COLORS

# Initialize stores for stats
vector_store = VectorStore(
    persist_directory=str(settings.chroma_path),
    chunk_size=settings.chunk_size,
    chunk_overlap=settings.chunk_overlap,
)
po_store = POStore(persist_directory=str(settings.chroma_path))


def check_ollama_status() -> tuple[bool, str]:
    """Check if Ollama is running and accessible."""
    try:
        response = requests.get(f"{settings.ollama_host}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name", "").split(":")[0] for m in models]
            return True, f"{', '.join(model_names[:3]) or 'No models'}"
        return False, "Error"
    except requests.exceptions.ConnectionError:
        return False, "Offline"
    except Exception as e:
        return False, "Error"


def get_stats() -> dict:
    """Get all system stats."""
    try:
        vs_stats = vector_store.get_stats()
        po_stats = po_store.get_stats()
        return {
            "vendors": vs_stats.get("total_vendors", 0),
            "chunks": vs_stats.get("total_chunks", 0),
            "pos": po_stats.get("total_pos", 0),
        }
    except Exception:
        return {"vendors": 0, "chunks": 0, "pos": 0}


# Page Configuration
st.set_page_config(
    page_title="Purchasing Document Matcher",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Inject custom styles
inject_styles()

# Get system status
ollama_ok, ollama_msg = check_ollama_status()
stats = get_stats()

# ===== SIDEBAR =====
with st.sidebar:
    st.markdown("### PDM")
    st.caption("Three-Way Invoice Matching")

    st.markdown("---")

    # System Status - Compact
    st.markdown("##### System Status")

    # Ollama Status
    if ollama_ok:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 8px 0;">
            <span style="width: 8px; height: 8px; background: #22C55E; border-radius: 50%; display: inline-block;"></span>
            <span style="color: #F8FAFC; font-size: 0.875rem;">Ollama</span>
            <span style="color: #64748B; font-size: 0.75rem; margin-left: auto;">{ollama_msg}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 8px; padding: 8px 0;">
            <span style="width: 8px; height: 8px; background: #EF4444; border-radius: 50%; display: inline-block;"></span>
            <span style="color: #F8FAFC; font-size: 0.875rem;">Ollama</span>
            <span style="color: #EF4444; font-size: 0.75rem; margin-left: auto;">Offline</span>
        </div>
        """, unsafe_allow_html=True)

    # ChromaDB Status
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 8px; padding: 8px 0;">
        <span style="width: 8px; height: 8px; background: #22C55E; border-radius: 50%; display: inline-block;"></span>
        <span style="color: #F8FAFC; font-size: 0.875rem;">ChromaDB</span>
        <span style="color: #64748B; font-size: 0.75rem; margin-left: auto;">Ready</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    # Quick Stats - Compact cards
    st.markdown("##### Data Summary")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"""
        <div style="background: rgba(14, 165, 233, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 1.5rem; font-weight: 700; color: #0EA5E9;">{stats['vendors']}</div>
            <div style="font-size: 0.7rem; color: #64748B; text-transform: uppercase;">Contracts</div>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
        <div style="background: rgba(34, 197, 94, 0.1); border-radius: 8px; padding: 12px; text-align: center;">
            <div style="font-size: 1.5rem; font-weight: 700; color: #22C55E;">{stats['pos']}</div>
            <div style="font-size: 0.7rem; color: #64748B; text-transform: uppercase;">POs</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Help
    with st.expander("Quick Help", expanded=False):
        st.markdown("""
        <div style="font-size: 0.8rem; color: #94A3B8;">
        <p><strong>1.</strong> Upload contracts first</p>
        <p><strong>2.</strong> Add purchase orders</p>
        <p><strong>3.</strong> Process invoices for validation</p>
        </div>
        """, unsafe_allow_html=True)


# ===== MAIN CONTENT =====

# Hero Section
st.markdown("""
<div style="text-align: center; padding: 40px 0 20px 0;">
    <h1 style="font-size: 2.5rem; font-weight: 700; color: #F8FAFC; margin-bottom: 8px;">
        Purchasing Document Matcher
    </h1>
    <p style="font-size: 1.125rem; color: #94A3B8; margin-bottom: 32px;">
        Privacy-first three-way invoice matching system
    </p>
</div>
""", unsafe_allow_html=True)

# Three-way matching visual
st.markdown("""
<div style="display: flex; justify-content: center; align-items: center; gap: 16px; padding: 24px 0 40px 0;">
    <div style="text-align: center;">
        <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%); border-radius: 16px; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto; font-size: 32px;">📄</div>
        <div style="color: #F8FAFC; font-weight: 600; font-size: 0.875rem;">Invoice</div>
    </div>
    <div style="width: 40px; height: 3px; background: linear-gradient(90deg, #0EA5E9, #22C55E); border-radius: 2px;"></div>
    <div style="text-align: center;">
        <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%); border-radius: 16px; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto; font-size: 32px;">📦</div>
        <div style="color: #F8FAFC; font-weight: 600; font-size: 0.875rem;">PO</div>
    </div>
    <div style="width: 40px; height: 3px; background: linear-gradient(90deg, #22C55E, #8B5CF6); border-radius: 2px;"></div>
    <div style="text-align: center;">
        <div style="width: 80px; height: 80px; background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%); border-radius: 16px; display: flex; align-items: center; justify-content: center; margin: 0 auto 8px auto; font-size: 32px;">📋</div>
        <div style="color: #F8FAFC; font-weight: 600; font-size: 0.875rem;">Contract</div>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# Feature Cards
st.markdown("""
<div style="text-align: center; margin-bottom: 24px;">
    <h2 style="font-size: 1.25rem; font-weight: 600; color: #F8FAFC;">Get Started</h2>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 24px; height: 100%; transition: all 0.2s ease;">
        <div style="width: 48px; height: 48px; background: linear-gradient(135deg, #8B5CF6 0%, #7C3AED 100%); border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; font-size: 24px;">📋</div>
        <h3 style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 8px;">1. Ingest Contracts</h3>
        <p style="font-size: 0.875rem; color: #94A3B8; line-height: 1.5;">
            Upload MSAs and SOWs. We'll parse, chunk, and index them for semantic search.
        </p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Upload Contracts", key="btn_contracts", use_container_width=True):
        st.switch_page("pages/1_Ingest_Contracts.py")

with col2:
    st.markdown("""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 24px; height: 100%; transition: all 0.2s ease;">
        <div style="width: 48px; height: 48px; background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%); border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; font-size: 24px;">📦</div>
        <h3 style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 8px;">2. Process POs</h3>
        <p style="font-size: 0.875rem; color: #94A3B8; line-height: 1.5;">
            Add Purchase Orders linked to contracts for three-way validation.
        </p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Add POs", key="btn_pos", use_container_width=True):
        st.switch_page("pages/2_Process_POs.py")

with col3:
    st.markdown("""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 24px; height: 100%; transition: all 0.2s ease;">
        <div style="width: 48px; height: 48px; background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%); border-radius: 10px; display: flex; align-items: center; justify-content: center; margin-bottom: 16px; font-size: 24px;">📄</div>
        <h3 style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 8px;">3. Validate Invoices</h3>
        <p style="font-size: 0.875rem; color: #94A3B8; line-height: 1.5;">
            Upload invoices and run three-way matching against POs and contracts.
        </p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Process Invoices", key="btn_invoices", use_container_width=True):
        st.switch_page("pages/3_Process_Invoices.py")

st.markdown("---")

# Privacy & Security Section
st.markdown("""
<div style="background: linear-gradient(135deg, rgba(14, 165, 233, 0.1) 0%, rgba(139, 92, 246, 0.1) 100%); border: 1px solid #334155; border-radius: 12px; padding: 32px; text-align: center; margin: 24px 0;">
    <h3 style="font-size: 1.125rem; font-weight: 600; color: #F8FAFC; margin-bottom: 16px;">
        🔒 100% Private & Offline
    </h3>
    <div style="display: flex; justify-content: center; gap: 32px; flex-wrap: wrap;">
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: #22C55E;">✓</span>
            <span style="color: #94A3B8; font-size: 0.875rem;">No cloud APIs</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: #22C55E;">✓</span>
            <span style="color: #94A3B8; font-size: 0.875rem;">No data leaves your machine</span>
        </div>
        <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: #22C55E;">✓</span>
            <span style="color: #94A3B8; font-size: 0.875rem;">Local LLM processing</span>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Footer
st.markdown("""
<div style="text-align: center; padding: 24px 0; color: #64748B; font-size: 0.75rem;">
    Purchasing Document Matcher v1.0 · Built with Streamlit, ChromaDB & Ollama
</div>
""", unsafe_allow_html=True)
