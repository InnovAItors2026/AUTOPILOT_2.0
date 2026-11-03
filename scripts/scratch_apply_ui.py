"""
Script to apply the enterprise UI/UX transformation to app.py.
Preserves 100% of the backend calculations, imports, queries, and logic,
while transforming the interface into a world-class enterprise control tower.
"""
import re

with open(r"C:\Users\Spandana B S\Downloads\AUTOPILOT_2.0-main\AUTOPILOT_2.0-main\app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Normalize line endings to LF
content = content.replace("\r\n", "\n")

# 1. Update the CSS section (between st.set_page_config and DATA NORMALIZATION)
css_replacement = '''
# =============================================================================
# ENTERPRISE STYLING & DESIGN SYSTEM (SAP FIORI / CONTROL TOWER)
# =============================================================================

st.markdown(
    """
    <style>
    /* CSS Variables & Enterprise Color Palette */
    :root {
        --primary-navy: #101C2C;
        --dark-blue: #172B46;
        --sap-blue: #0A6ED1;
        --sap-blue-hover: #085CAD;
        --cyan-accent: #22B8CF;
        --teal-success: #16A68A;
        --neutral-bg: #F5F7FA;
        --surface-white: #FFFFFF;
        --text-primary: #172B4D;
        --text-secondary: #68778D;
        --text-muted: #94A3B8;
        --border-subtle: #E2E8F0;
        --border-medium: #CBD5E1;
        --warning-amber: #E9A23B;
        --critical-red: #D64545;
    }

    /* Global Typography & Font Styling */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        color: #172B4D;
    }

    /* Executive Control Tower Header */
    .control-tower-header {
        background: linear-gradient(135deg, #101C2C 0%, #172B46 100%);
        border-radius: 8px;
        padding: 18px 24px;
        color: #FFFFFF;
        margin-bottom: 16px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: 0 4px 16px rgba(16, 28, 44, 0.08);
    }
    .tower-top-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 12px;
    }
    .tower-title {
        font-size: 1.85rem;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: #FFFFFF;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .tower-badge {
        background: rgba(10, 110, 209, 0.35);
        border: 1px solid #0A6ED1;
        color: #93C5FD;
        padding: 3px 10px;
        border-radius: 4px;
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .tower-subtitle {
        font-size: 0.90rem;
        color: #94A3B8;
        margin-top: 4px;
        margin-bottom: 0;
    }
    .telemetry-strip {
        display: flex;
        flex-wrap: wrap;
        gap: 16px;
        margin-top: 14px;
        padding-top: 12px;
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        font-size: 0.80rem;
        color: #CBD5E1;
    }
    .telemetry-item {
        display: flex;
        align-items: center;
        gap: 6px;
    }

    /* Executive KPI Grid & Tiles */
    .kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
        gap: 10px;
        margin-bottom: 18px;
    }
    .kpi-tile {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 12px 14px;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
        border-left: 3px solid #0A6ED1;
    }
    .kpi-tile-critical { border-left-color: #D64545; }
    .kpi-tile-warning { border-left-color: #E9A23B; }
    .kpi-tile-success { border-left-color: #16A68A; }
    .kpi-tile-cyan { border-left-color: #22B8CF; }

    .kpi-label {
        font-size: 0.70rem;
        font-weight: 700;
        color: #68778D;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-bottom: 2px;
    }
    .kpi-value {
        font-size: 1.35rem;
        font-weight: 800;
        color: #172B4D;
        line-height: 1.2;
    }
    .kpi-sub {
        font-size: 0.72rem;
        color: #94A3B8;
        margin-top: 2px;
    }

    /* Enterprise Metric Card */
    .metric-card {
        background-color: #FFFFFF;
        border-radius: 6px;
        padding: 14px 16px;
        border: 1px solid #E2E8F0;
        box-shadow: 0 1px 2px rgba(0,0,0,0.02);
    }

    /* Status Badges */
    .status-badge {
        display: inline-block;
        padding: 3px 8px;
        border-radius: 4px;
        font-weight: 700;
        font-size: 0.75rem;
        letter-spacing: 0.3px;
        text-transform: uppercase;
    }
    .badge-critical { background-color: #FEF2F2; color: #991B1B; border: 1px solid #FECACA; }
    .badge-high { background-color: #FFF7ED; color: #C2410C; border: 1px solid #FFEDD5; }
    .badge-medium { background-color: #FFFBEB; color: #B45309; border: 1px solid #FEF3C7; }
    .badge-low { background-color: #ECFDF5; color: #065F46; border: 1px solid #A7F3D0; }
    .badge-sap { background-color: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; }

    /* Streamlit Tab Styling Overrides */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        border-bottom: 1px solid #E2E8F0;
        padding-bottom: 2px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 44px;
        padding: 0 18px;
        border-radius: 6px 6px 0 0;
        font-weight: 600;
        font-size: 0.88rem;
        color: #475569;
        background-color: transparent;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        color: #0A6ED1 !important;
        border-bottom: 3px solid #0A6ED1 !important;
        background-color: #F8FAFC !important;
    }

    /* Disruption Cascade Flow Banner */
    .cascade-flow-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 6px;
        padding: 10px 16px;
        margin: 12px 0 16px 0;
    }
    .flow-step {
        display: flex;
        align-items: center;
        gap: 6px;
        font-size: 0.78rem;
        font-weight: 700;
        color: #334155;
    }
    .flow-arrow {
        color: #94A3B8;
        font-size: 0.85rem;
    }

    /* Factor Progress Bar Component */
    .factor-container {
        margin-bottom: 8px;
    }
    .factor-header {
        display: flex;
        justify-content: space-between;
        font-size: 0.78rem;
        font-weight: 600;
        color: #334155;
        margin-bottom: 2px;
    }
    .factor-track {
        background-color: #E2E8F0;
        border-radius: 4px;
        height: 7px;
        width: 100%;
        overflow: hidden;
    }
    .factor-fill {
        height: 100%;
        border-radius: 4px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
'''

# Find the styling block and replace it
style_pattern = re.compile(
    r"# =============================================================================\n# STYLING\n# =============================================================================\n.*?# =============================================================================\n# DATA NORMALIZATION AND VALIDATION",
    re.DOTALL
)

if style_pattern.search(content):
    content = style_pattern.sub(css_replacement + "\n# =============================================================================\n# DATA NORMALIZATION AND VALIDATION", content, count=1)
    print("SUCCESS: Injected Enterprise Design System CSS.")
else:
    print("FAILED to find style block pattern.")

with open(r"C:\Users\Spandana B S\Downloads\AUTOPILOT_2.0-main\AUTOPILOT_2.0-main\app.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Updated app.py with CSS.")

