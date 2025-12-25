"""
DocuMatch Architect - Design System & Styles

Modern, minimalistic design with a professional color palette.
"""

# Color Palette
COLORS = {
    # Primary brand color - Modern teal
    "primary": "#0EA5E9",
    "primary_light": "#38BDF8",
    "primary_dark": "#0284C7",

    # Background colors
    "bg_dark": "#0F172A",
    "bg_card": "#1E293B",
    "bg_card_hover": "#334155",
    "bg_input": "#1E293B",

    # Status colors
    "success": "#22C55E",
    "success_bg": "rgba(34, 197, 94, 0.1)",
    "error": "#EF4444",
    "error_bg": "rgba(239, 68, 68, 0.1)",
    "warning": "#F59E0B",
    "warning_bg": "rgba(245, 158, 11, 0.1)",
    "info": "#3B82F6",
    "info_bg": "rgba(59, 130, 246, 0.1)",

    # Text colors
    "text_primary": "#F8FAFC",
    "text_secondary": "#94A3B8",
    "text_muted": "#64748B",

    # Border colors
    "border": "#334155",
    "border_light": "#475569",
}

# Main CSS stylesheet
MAIN_CSS = """
<style>
    /* ===== GLOBAL STYLES ===== */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    .stApp {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    /* ===== SIDEBAR STYLES ===== */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%);
        border-right: 1px solid #334155;
    }

    [data-testid="stSidebar"] .stMarkdown h1 {
        font-size: 1.25rem;
        font-weight: 600;
        color: #F8FAFC;
    }

    /* ===== STATUS INDICATORS ===== */
    .status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    .status-online {
        background: rgba(34, 197, 94, 0.15);
        color: #22C55E;
        border: 1px solid rgba(34, 197, 94, 0.3);
    }

    .status-offline {
        background: rgba(239, 68, 68, 0.15);
        color: #EF4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .status-dot {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }

    .status-dot.online { background: #22C55E; }
    .status-dot.offline { background: #EF4444; }

    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }

    /* ===== CARDS ===== */
    .modern-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 24px;
        transition: all 0.2s ease;
    }

    .modern-card:hover {
        border-color: #0EA5E9;
        box-shadow: 0 4px 20px rgba(14, 165, 233, 0.1);
    }

    .modern-card-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 16px;
    }

    .modern-card-icon {
        width: 48px;
        height: 48px;
        background: linear-gradient(135deg, #0EA5E9 0%, #3B82F6 100%);
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 24px;
    }

    .modern-card-title {
        font-size: 1.125rem;
        font-weight: 600;
        color: #F8FAFC;
        margin: 0;
    }

    .modern-card-subtitle {
        font-size: 0.875rem;
        color: #94A3B8;
        margin: 0;
    }

    /* ===== PROGRESS STEPPER ===== */
    .stepper-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 20px 0 32px 0;
        gap: 0;
    }

    .stepper-item {
        display: flex;
        align-items: center;
        gap: 8px;
    }

    .stepper-circle {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 14px;
        font-weight: 600;
        transition: all 0.3s ease;
    }

    .stepper-circle.completed {
        background: #22C55E;
        color: white;
    }

    .stepper-circle.active {
        background: #0EA5E9;
        color: white;
        box-shadow: 0 0 0 4px rgba(14, 165, 233, 0.2);
    }

    .stepper-circle.pending {
        background: #334155;
        color: #64748B;
    }

    .stepper-label {
        font-size: 0.875rem;
        font-weight: 500;
    }

    .stepper-label.active { color: #F8FAFC; }
    .stepper-label.completed { color: #22C55E; }
    .stepper-label.pending { color: #64748B; }

    .stepper-line {
        width: 60px;
        height: 2px;
        margin: 0 8px;
    }

    .stepper-line.completed { background: #22C55E; }
    .stepper-line.pending { background: #334155; }

    /* ===== VALIDATION RESULTS ===== */
    .validation-hero {
        text-align: center;
        padding: 40px 20px;
        margin-bottom: 32px;
    }

    .validation-status-icon {
        font-size: 72px;
        margin-bottom: 16px;
    }

    .validation-status-text {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .validation-status-text.pass { color: #22C55E; }
    .validation-status-text.fail { color: #EF4444; }
    .validation-status-text.review { color: #F59E0B; }

    .match-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
    }

    .match-card.pass {
        border-color: rgba(34, 197, 94, 0.3);
        background: linear-gradient(180deg, rgba(34, 197, 94, 0.05) 0%, #1E293B 100%);
    }

    .match-card.fail {
        border-color: rgba(239, 68, 68, 0.3);
        background: linear-gradient(180deg, rgba(239, 68, 68, 0.05) 0%, #1E293B 100%);
    }

    .match-card-title {
        font-size: 0.75rem;
        font-weight: 600;
        color: #94A3B8;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 12px;
    }

    .match-card-status {
        font-size: 1.5rem;
        font-weight: 700;
        margin-bottom: 4px;
    }

    .match-card-score {
        font-size: 0.875rem;
        color: #64748B;
    }

    /* ===== THREE-WAY DIAGRAM ===== */
    .diagram-container {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 32px 0;
        gap: 20px;
    }

    .diagram-node {
        width: 100px;
        height: 100px;
        border-radius: 50%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        background: #1E293B;
        border: 2px solid #334155;
        transition: all 0.3s ease;
    }

    .diagram-node.active {
        border-color: #0EA5E9;
        box-shadow: 0 0 20px rgba(14, 165, 233, 0.2);
    }

    .diagram-connector {
        width: 60px;
        height: 3px;
        border-radius: 2px;
    }

    .diagram-connector.pass { background: #22C55E; }
    .diagram-connector.fail { background: #EF4444; }
    .diagram-connector.pending { background: #334155; }

    /* ===== BUTTONS ===== */
    .stButton > button {
        background: linear-gradient(135deg, #0EA5E9 0%, #0284C7 100%);
        color: white;
        border: none;
        border-radius: 8px;
        font-weight: 600;
        padding: 0.5rem 1.5rem;
        transition: all 0.2s ease;
    }

    .stButton > button:hover {
        background: linear-gradient(135deg, #38BDF8 0%, #0EA5E9 100%);
        box-shadow: 0 4px 12px rgba(14, 165, 233, 0.3);
        transform: translateY(-1px);
    }

    .stButton > button:active {
        transform: translateY(0);
    }

    /* Secondary button style */
    .secondary-btn > button {
        background: transparent;
        border: 1px solid #334155;
        color: #94A3B8;
    }

    .secondary-btn > button:hover {
        background: #334155;
        color: #F8FAFC;
        border-color: #475569;
        box-shadow: none;
        transform: none;
    }

    /* ===== FILE UPLOADER ===== */
    [data-testid="stFileUploader"] {
        background: #1E293B;
        border: 2px dashed #334155;
        border-radius: 12px;
        padding: 20px;
        transition: all 0.2s ease;
    }

    [data-testid="stFileUploader"]:hover {
        border-color: #0EA5E9;
        background: rgba(14, 165, 233, 0.05);
    }

    /* ===== METRICS ===== */
    [data-testid="stMetric"] {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 16px;
    }

    [data-testid="stMetricLabel"] {
        color: #94A3B8;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    [data-testid="stMetricValue"] {
        color: #F8FAFC;
        font-size: 1.75rem;
        font-weight: 700;
    }

    /* ===== DATA TABLES ===== */
    .dataframe {
        background: #1E293B;
        border-radius: 8px;
    }

    .dataframe th {
        background: #334155;
        color: #F8FAFC;
        font-weight: 600;
    }

    .dataframe td {
        color: #94A3B8;
    }

    /* ===== EXPANDERS ===== */
    .streamlit-expanderHeader {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #F8FAFC;
    }

    .streamlit-expanderContent {
        background: #1E293B;
        border: 1px solid #334155;
        border-top: none;
        border-radius: 0 0 8px 8px;
    }

    /* ===== INPUT FIELDS ===== */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > div {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        color: #F8FAFC;
    }

    .stTextInput > div > div > input:focus {
        border-color: #0EA5E9;
        box-shadow: 0 0 0 2px rgba(14, 165, 233, 0.2);
    }

    /* ===== ALERTS/MESSAGES ===== */
    .stAlert {
        border-radius: 8px;
        border: none;
    }

    /* ===== PAGE HEADER ===== */
    .page-header {
        margin-bottom: 32px;
    }

    .page-title {
        font-size: 2rem;
        font-weight: 700;
        color: #F8FAFC;
        margin-bottom: 8px;
    }

    .page-subtitle {
        font-size: 1rem;
        color: #94A3B8;
        margin: 0;
    }

    /* ===== SECTION HEADERS ===== */
    .section-header {
        font-size: 1.25rem;
        font-weight: 600;
        color: #F8FAFC;
        margin: 32px 0 16px 0;
        display: flex;
        align-items: center;
        gap: 8px;
    }

    /* ===== EMPTY STATES ===== */
    .empty-state {
        text-align: center;
        padding: 48px 24px;
        background: #1E293B;
        border: 1px dashed #334155;
        border-radius: 12px;
    }

    .empty-state-icon {
        font-size: 48px;
        margin-bottom: 16px;
        opacity: 0.5;
    }

    .empty-state-title {
        font-size: 1.125rem;
        font-weight: 600;
        color: #F8FAFC;
        margin-bottom: 8px;
    }

    .empty-state-text {
        font-size: 0.875rem;
        color: #64748B;
        margin-bottom: 16px;
    }

    /* ===== ISSUE PILLS ===== */
    .issue-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 12px;
        border-radius: 6px;
        font-size: 0.8rem;
        margin: 4px;
    }

    .issue-pill.critical {
        background: rgba(239, 68, 68, 0.15);
        color: #EF4444;
        border: 1px solid rgba(239, 68, 68, 0.3);
    }

    .issue-pill.error {
        background: rgba(249, 115, 22, 0.15);
        color: #F97316;
        border: 1px solid rgba(249, 115, 22, 0.3);
    }

    .issue-pill.warning {
        background: rgba(245, 158, 11, 0.15);
        color: #F59E0B;
        border: 1px solid rgba(245, 158, 11, 0.3);
    }

    .issue-pill.info {
        background: rgba(59, 130, 246, 0.15);
        color: #3B82F6;
        border: 1px solid rgba(59, 130, 246, 0.3);
    }

    /* ===== COMPACT SIDEBAR STATS ===== */
    .sidebar-stat {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 12px;
        background: rgba(14, 165, 233, 0.1);
        border-radius: 8px;
        margin-bottom: 8px;
    }

    .sidebar-stat-label {
        font-size: 0.75rem;
        color: #94A3B8;
    }

    .sidebar-stat-value {
        font-size: 1rem;
        font-weight: 600;
        color: #F8FAFC;
    }

    /* ===== DIVIDERS ===== */
    hr {
        border: none;
        border-top: 1px solid #334155;
        margin: 24px 0;
    }

    /* ===== HIDE ANCHOR LINKS ===== */
    .css-15zrgzn {display: none}
    .css-zt5igj {display: none}

</style>
"""


def inject_styles():
    """Inject the main CSS styles into the Streamlit app."""
    import streamlit as st
    st.markdown(MAIN_CSS, unsafe_allow_html=True)


def render_stepper(steps: list, current_step: int):
    """
    Render a progress stepper.

    Args:
        steps: List of step names, e.g., ["Contracts", "POs", "Invoices", "Results"]
        current_step: 0-indexed current step (use -1 for none active)
    """
    import streamlit as st

    html = '<div class="stepper-container">'

    for i, step in enumerate(steps):
        # Determine status
        if i < current_step:
            status = "completed"
            icon = "✓"
        elif i == current_step:
            status = "active"
            icon = str(i + 1)
        else:
            status = "pending"
            icon = str(i + 1)

        html += f'''
        <div class="stepper-item">
            <div class="stepper-circle {status}">{icon}</div>
            <span class="stepper-label {status}">{step}</span>
        </div>
        '''

        # Add connector line (except after last step)
        if i < len(steps) - 1:
            line_status = "completed" if i < current_step else "pending"
            html += f'<div class="stepper-line {line_status}"></div>'

    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)


def render_status_badge(status: str, label: str):
    """Render a status badge (online/offline)."""
    import streamlit as st

    dot_class = "online" if status == "online" else "offline"
    badge_class = "status-online" if status == "online" else "status-offline"

    html = f'''
    <span class="status-badge {badge_class}">
        <span class="status-dot {dot_class}"></span>
        {label}
    </span>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_validation_hero(status: str, score: float, matches_passed: int, total_matches: int):
    """Render the validation result hero section."""
    import streamlit as st

    if status == "PASS":
        icon = "✅"
        text = "Approved"
        css_class = "pass"
    elif status == "FAIL":
        icon = "❌"
        text = "Failed"
        css_class = "fail"
    else:
        icon = "⚠️"
        text = "Review Required"
        css_class = "review"

    html = f'''
    <div class="validation-hero">
        <div class="validation-status-icon">{icon}</div>
        <div class="validation-status-text {css_class}">{text}</div>
        <p style="color: #94A3B8; font-size: 1.125rem;">
            {matches_passed}/{total_matches} matches passed · {score:.0%} confidence
        </p>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_match_card(title: str, passed: bool, score: float):
    """Render a match result card."""
    import streamlit as st

    status_class = "pass" if passed else "fail"
    status_icon = "✓" if passed else "✗"
    status_text = "PASS" if passed else "FAIL"
    status_color = "#22C55E" if passed else "#EF4444"

    html = f'''
    <div class="match-card {status_class}">
        <div class="match-card-title">{title}</div>
        <div class="match-card-status" style="color: {status_color}">
            {status_icon} {status_text}
        </div>
        <div class="match-card-score">{score:.0%}</div>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_empty_state(icon: str, title: str, message: str, button_label: str = None):
    """Render an empty state placeholder."""
    import streamlit as st

    html = f'''
    <div class="empty-state">
        <div class="empty-state-icon">{icon}</div>
        <div class="empty-state-title">{title}</div>
        <div class="empty-state-text">{message}</div>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)

    if button_label:
        st.button(button_label)


def render_issue_pill(severity: str, message: str):
    """Render an issue pill with color-coded severity."""
    import streamlit as st

    icons = {
        "critical": "🔴",
        "error": "🟠",
        "warning": "🟡",
        "info": "🔵"
    }

    icon = icons.get(severity, "⚪")

    html = f'''
    <span class="issue-pill {severity}">
        {icon} {message}
    </span>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_page_header(title: str, subtitle: str, icon: str = ""):
    """Render a page header with title and subtitle."""
    import streamlit as st

    html = f'''
    <div class="page-header">
        <h1 class="page-title">{icon} {title}</h1>
        <p class="page-subtitle">{subtitle}</p>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_section_header(title: str, icon: str = ""):
    """Render a section header."""
    import streamlit as st

    html = f'''
    <div class="section-header">
        {icon} {title}
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_sidebar_stat(label: str, value: str):
    """Render a compact sidebar statistic."""
    import streamlit as st

    html = f'''
    <div class="sidebar-stat">
        <span class="sidebar-stat-label">{label}</span>
        <span class="sidebar-stat-value">{value}</span>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)


def render_modern_card(icon: str, title: str, subtitle: str, content: str):
    """Render a modern card with icon header."""
    import streamlit as st

    html = f'''
    <div class="modern-card">
        <div class="modern-card-header">
            <div class="modern-card-icon">{icon}</div>
            <div>
                <h3 class="modern-card-title">{title}</h3>
                <p class="modern-card-subtitle">{subtitle}</p>
            </div>
        </div>
        <div style="color: #94A3B8; font-size: 0.875rem;">
            {content}
        </div>
    </div>
    '''
    st.markdown(html, unsafe_allow_html=True)
