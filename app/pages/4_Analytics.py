"""
Analytics Dashboard Page

KPI cards, processing history, and result distribution charts.
Powered by SQLite metadata store and Plotly interactive charts.
"""

import streamlit as st
from pathlib import Path
import sys

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config import settings
from core.database import Database
from app.styles import inject_styles

import plotly.graph_objects as go

# Initialize database
db = Database(db_path=settings.db_path)

st.set_page_config(
    page_title="Analytics - PDM",
    page_icon="📊",
    layout="wide",
)

inject_styles()


# ===== SIDEBAR =====
with st.sidebar:
    st.markdown("### PDM")
    st.caption("Analytics Dashboard")

    st.markdown("---")

    # Filters
    st.markdown("##### Filters")

    filter_status = st.selectbox(
        "Status",
        options=["All", "PASS", "FAIL", "REVIEW"],
        index=0,
    )

    filter_vendor = st.text_input(
        "Vendor",
        placeholder="Filter by vendor name...",
    )

    st.markdown("---")

    with st.expander("About", expanded=False):
        st.markdown("""
        <div style="font-size: 0.8rem; color: #94A3B8; line-height: 1.6;">
        <p>Dashboard powered by SQLite metadata store.</p>
        <p>Data updates automatically as invoices are processed.</p>
        </div>
        """, unsafe_allow_html=True)


# ===== MAIN CONTENT =====

# Page Header
st.markdown("""
<div style="margin-bottom: 24px;">
    <h1 style="font-size: 1.75rem; font-weight: 700; color: #F8FAFC; margin-bottom: 4px; display: flex; align-items: center; gap: 12px;">
        <span style="font-size: 1.5rem;">📊</span> Analytics Dashboard
    </h1>
    <p style="font-size: 0.9rem; color: #94A3B8; margin: 0;">
        Processing metrics and validation results
    </p>
</div>
""", unsafe_allow_html=True)

# Get stats
stats = db.get_stats()

# ===== KPI CARDS =====
kpi_cols = st.columns(4)

with kpi_cols[0]:
    st.markdown(f"""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center;">
        <div style="font-size: 2rem; font-weight: 700; color: #0EA5E9;">{stats['total_results']}</div>
        <div style="font-size: 0.75rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px;">Total Processed</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_cols[1]:
    pass_rate_pct = f"{stats['pass_rate']:.0%}" if stats['total_results'] > 0 else "N/A"
    pass_color = "#22C55E" if stats['pass_rate'] >= 0.8 else "#F59E0B" if stats['pass_rate'] >= 0.5 else "#EF4444"
    if stats['total_results'] == 0:
        pass_color = "#64748B"
    st.markdown(f"""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center;">
        <div style="font-size: 2rem; font-weight: 700; color: {pass_color};">{pass_rate_pct}</div>
        <div style="font-size: 0.75rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px;">Pass Rate</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_cols[2]:
    st.markdown(f"""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center;">
        <div style="font-size: 2rem; font-weight: 700; color: #F8FAFC;">{stats['total_jobs']}</div>
        <div style="font-size: 0.75rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px;">Total Jobs</div>
    </div>
    """, unsafe_allow_html=True)

with kpi_cols[3]:
    pending = stats['pending_jobs']
    pending_color = "#F59E0B" if pending > 0 else "#22C55E"
    st.markdown(f"""
    <div style="background: #1E293B; border: 1px solid #334155; border-radius: 12px; padding: 20px; text-align: center;">
        <div style="font-size: 2rem; font-weight: 700; color: {pending_color};">{pending}</div>
        <div style="font-size: 0.75rem; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px;">Pending</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ===== CHARTS =====
chart_cols = st.columns([1, 1])

with chart_cols[0]:
    st.markdown("""
    <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 12px;">
        Result Distribution
    </div>
    """, unsafe_allow_html=True)

    if stats['total_results'] > 0:
        labels = []
        values = []
        colors = []

        if stats['pass_count'] > 0:
            labels.append("PASS")
            values.append(stats['pass_count'])
            colors.append("#22C55E")
        if stats['fail_count'] > 0:
            labels.append("FAIL")
            values.append(stats['fail_count'])
            colors.append("#EF4444")
        if stats['review_count'] > 0:
            labels.append("REVIEW")
            values.append(stats['review_count'])
            colors.append("#F59E0B")

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.55,
            marker=dict(colors=colors),
            textinfo="label+value",
            textfont=dict(size=13, color="#F8FAFC"),
            hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
        )])
        fig.update_layout(
            showlegend=False,
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=10, l=10, r=10),
            height=280,
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 48px; text-align: center;">
            <div style="font-size: 32px; margin-bottom: 8px; opacity: 0.5;">📊</div>
            <div style="color: #64748B; font-size: 0.85rem;">No results yet</div>
        </div>
        """, unsafe_allow_html=True)

with chart_cols[1]:
    st.markdown("""
    <div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin-bottom: 12px;">
        Job Status
    </div>
    """, unsafe_allow_html=True)

    completed = stats['completed_jobs']
    failed = stats['failed_jobs']
    pending_jobs = stats['pending_jobs']

    if stats['total_jobs'] > 0:
        categories = []
        counts = []
        bar_colors = []

        if completed > 0:
            categories.append("Completed")
            counts.append(completed)
            bar_colors.append("#22C55E")
        if failed > 0:
            categories.append("Failed")
            counts.append(failed)
            bar_colors.append("#EF4444")
        if pending_jobs > 0:
            categories.append("Pending")
            counts.append(pending_jobs)
            bar_colors.append("#F59E0B")

        fig = go.Figure(data=[go.Bar(
            x=categories,
            y=counts,
            marker_color=bar_colors,
            text=counts,
            textposition="outside",
            textfont=dict(color="#F8FAFC", size=14),
        )])
        fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=30, l=30, r=10),
            height=280,
            xaxis=dict(
                tickfont=dict(color="#94A3B8", size=12),
                showgrid=False,
            ),
            yaxis=dict(
                tickfont=dict(color="#64748B", size=11),
                gridcolor="rgba(51, 65, 85, 0.5)",
                showgrid=True,
            ),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.markdown("""
        <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 48px; text-align: center;">
            <div style="font-size: 32px; margin-bottom: 8px; opacity: 0.5;">📋</div>
            <div style="color: #64748B; font-size: 0.85rem;">No jobs yet</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("---")

# ===== RECENT RESULTS TABLE =====
st.markdown("""
<div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin: 8px 0 16px 0;">
    Recent Validation Results
</div>
""", unsafe_allow_html=True)

# Apply filters
result_filters = {}
if filter_status != "All":
    result_filters["status"] = filter_status
if filter_vendor:
    result_filters["vendor_name"] = filter_vendor

results = db.get_results(**result_filters, limit=50)

if results:
    for r in results:
        # Status badge
        status_colors = {
            "PASS": ("#22C55E", "rgba(34, 197, 94, 0.2)"),
            "FAIL": ("#EF4444", "rgba(239, 68, 68, 0.2)"),
            "REVIEW": ("#F59E0B", "rgba(245, 158, 11, 0.2)"),
        }
        s_color, s_bg = status_colors.get(r.status, ("#64748B", "rgba(100, 116, 139, 0.2)"))

        confidence_pct = f"{r.confidence:.0%}" if r.confidence else "N/A"
        matches_str = f"{r.matches_passed}/{r.total_matches}" if r.matches_passed is not None else "N/A"
        created = r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "N/A"

        st.markdown(f"""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 16px;">
                <span style="background: {s_bg}; color: {s_color}; padding: 4px 12px; border-radius: 12px; font-size: 0.7rem; font-weight: 700; letter-spacing: 0.5px;">{r.status or 'N/A'}</span>
                <span style="color: #F8FAFC; font-weight: 500; font-size: 0.875rem;">{r.invoice_number or 'Unknown'}</span>
                <span style="color: #64748B; font-size: 0.8rem;">{r.vendor_name or ''}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 20px;">
                <span style="color: #94A3B8; font-size: 0.8rem;">Matches: {matches_str}</span>
                <span style="color: #94A3B8; font-size: 0.8rem;">Confidence: {confidence_pct}</span>
                <span style="color: #475569; font-size: 0.75rem;">{created}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.caption(f"Showing {len(results)} results")
else:
    st.markdown("""
    <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 48px; text-align: center;">
        <div style="font-size: 32px; margin-bottom: 8px; opacity: 0.5;">📋</div>
        <div style="color: #94A3B8; font-size: 0.875rem;">No validation results yet</div>
        <div style="color: #64748B; font-size: 0.8rem; margin-top: 4px;">Process invoices to see results here</div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("---")

# ===== RECENT JOBS TABLE =====
st.markdown("""
<div style="font-size: 1rem; font-weight: 600; color: #F8FAFC; margin: 8px 0 16px 0;">
    Recent Jobs
</div>
""", unsafe_allow_html=True)

jobs = db.list_jobs(limit=20)

if jobs:
    for job in jobs:
        status_colors = {
            "COMPLETE": ("#22C55E", "rgba(34, 197, 94, 0.2)"),
            "FAILED": ("#EF4444", "rgba(239, 68, 68, 0.2)"),
            "PENDING": ("#F59E0B", "rgba(245, 158, 11, 0.2)"),
            "PARSING": ("#0EA5E9", "rgba(14, 165, 233, 0.2)"),
            "EXTRACTING": ("#8B5CF6", "rgba(139, 92, 246, 0.2)"),
            "MATCHING": ("#0EA5E9", "rgba(14, 165, 233, 0.2)"),
        }
        j_color, j_bg = status_colors.get(job.status, ("#64748B", "rgba(100, 116, 139, 0.2)"))

        type_labels = {
            "contract_ingest": "Contract",
            "po_ingest": "PO",
            "invoice_process": "Invoice",
            "batch_process": "Batch",
        }
        type_label = type_labels.get(job.type, job.type)

        duration = ""
        if job.completed_at and job.created_at:
            secs = (job.completed_at - job.created_at).total_seconds()
            duration = f"{secs:.1f}s"

        created = job.created_at.strftime("%Y-%m-%d %H:%M") if job.created_at else "N/A"

        st.markdown(f"""
        <div style="background: #1E293B; border: 1px solid #334155; border-radius: 8px; padding: 10px 16px; margin-bottom: 6px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="background: {j_bg}; color: {j_color}; padding: 3px 10px; border-radius: 10px; font-size: 0.65rem; font-weight: 700; letter-spacing: 0.5px;">{job.status}</span>
                <span style="color: #94A3B8; font-size: 0.8rem; font-weight: 500;">{type_label}</span>
                <span style="color: #64748B; font-size: 0.75rem;">{job.file_name or ''}</span>
            </div>
            <div style="display: flex; align-items: center; gap: 16px;">
                {f'<span style="color: #94A3B8; font-size: 0.75rem;">{duration}</span>' if duration else ''}
                <span style="color: #475569; font-size: 0.7rem;">{created}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div style="background: #1E293B; border: 1px dashed #334155; border-radius: 8px; padding: 32px; text-align: center;">
        <div style="font-size: 32px; margin-bottom: 8px; opacity: 0.5;">📋</div>
        <div style="color: #94A3B8; font-size: 0.875rem;">No jobs yet</div>
    </div>
    """, unsafe_allow_html=True)
