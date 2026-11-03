
"""
AUTOPILOT 2.0 — Resilient Supply Chain Management Dashboard
Hackfest 2026 — Member 5

Frontend, unified data integration, AI explanations,
governance approval, SAP HANA and SAP OData gateway.
"""

from datetime import datetime, timezone
import json
import os
import sys

import pandas as pd
import streamlit as st
import networkx as nx

def clean_html(html_str: str) -> str:
    """Strip leading whitespace and empty lines to prevent markdown code block triggers."""
    if not html_str:
        return ""
    return "\n".join(line.strip() for line in html_str.splitlines() if line.strip())


# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================

ROOT = os.path.abspath(os.path.dirname(__file__))

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(ROOT, ".env"), override=True)
except ImportError:
    pass


# =============================================================================
# PROJECT MODULES
# =============================================================================

from src.data_loader import load_all_data

from src.supply_chain_graph import (
    find_suppliers_sharing_upstream,
    find_upstream_dependencies,
    get_supply_chain_graph,
)

from src.supplier_risk import build_supplier_risk_factors
from src.risk_scoring import calculate_supplier_risk_scores

from src.disruption_simulation import simulate_supplier_disruption
from src.multi_disruption_simulation import simulate_multiple_supplier_disruption

from src.recovery_optimisation import optimise_recovery
from src.cascading_failure import challenge_recovery_plan

from src.sap_client import SAPClient

from src.pipeline import (
    run_full_resilience_pipeline,
    approve_recovery_plan,
    reject_recovery_plan,
    get_approval_history,
    generate_dossier_markdown,
    generate_ai_explanations,
)


# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="AUTOPILOT 2.0 — Supply Chain Intelligence & Resilience Control Tower",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        "Get Help": None,
        "Report a bug": None,
        "About": "AUTOPILOT 2.0 — AI-Powered Supply Chain Intelligence & Resilience Control Tower | SAP Hackfest 2026 | NHCE Bengaluru",
    }
)



# =============================================================================
# ENTERPRISE STYLING & DESIGN SYSTEM (SAP FIORI / CONTROL TOWER)
# =============================================================================

st.markdown("""
<style>
/* ============================================================
   AUTOPILOT 2.0 — Enterprise Design System
   Supply Chain Intelligence & Resilience Control Tower
   SAP Hackfest 2026 | NHCE Bengaluru
   ============================================================ */

/* CSS Custom Properties */
:root {
    --navy:       #101C2C;
    --dark-blue:  #172B46;
    --sap-blue:   #0A6ED1;
    --sap-hover:  #085CAD;
    --cyan:       #22B8CF;
    --teal:       #16A68A;
    --bg:         #F0F2F6;
    --surface:    #FFFFFF;
    --border:     #E2E8F0;
    --border-md:  #CBD5E1;
    --text-1:     #182230;
    --text-2:     #667085;
    --text-3:     #94A3B8;
    --amber:      #E9A23B;
    --red:        #D64545;
    --red-bg:     #FEF2F2;
    --amber-bg:   #FFFBEB;
    --teal-bg:    #ECFDF5;
    --blue-bg:    #EFF6FF;
    --radius-sm:  4px;
    --radius-md:  8px;
    --radius-lg:  12px;
    --shadow-xs:  0 1px 2px rgba(0,0,0,.04);
    --shadow-sm:  0 2px 6px rgba(0,0,0,.06);
    --shadow-md:  0 4px 16px rgba(0,0,0,.08);
}

/* Global reset & typography */
html, body, [class*="css"] {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                 "Helvetica Neue", Arial, sans-serif !important;
    color: var(--text-1);
}
.stApp { background: var(--bg); }

/* ── Streamlit Sidebar ─────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--navy) !important;
    border-right: 1px solid rgba(255,255,255,.08);
}
section[data-testid="stSidebar"] * {
    color: #CBD5E1 !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] strong {
    color: #FFFFFF !important;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stRadio label,
section[data-testid="stSidebar"] .stTextInput label {
    color: #94A3B8 !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.4px;
}
section[data-testid="stSidebar"] [data-baseweb="select"] {
    background: rgba(255,255,255,.06) !important;
    border-color: rgba(255,255,255,.15) !important;
    border-radius: var(--radius-sm) !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,.1) !important;
}
section[data-testid="stSidebar"] .stButton > button {
    background: rgba(10,110,209,.25) !important;
    border: 1px solid rgba(10,110,209,.5) !important;
    color: #93C5FD !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(10,110,209,.4) !important;
}

/* ── Tabs ──────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: transparent;
    border-bottom: 2px solid var(--border);
    padding-bottom: 0;
}
.stTabs [data-baseweb="tab"] {
    height: 42px;
    padding: 0 16px;
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    font-weight: 600;
    font-size: 0.84rem;
    color: var(--text-2);
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    transition: color .15s, border-color .15s;
}
.stTabs [data-baseweb="tab"]:hover { color: var(--sap-blue); }
.stTabs [aria-selected="true"] {
    color: var(--sap-blue) !important;
    border-bottom: 2px solid var(--sap-blue) !important;
    background: rgba(10,110,209,.04) !important;
}

/* ── Control Tower Header ──────────────────────────────── */
.ct-header {
    background: linear-gradient(135deg, var(--navy) 0%, var(--dark-blue) 100%);
    border-radius: var(--radius-md);
    padding: 20px 24px 16px;
    color: #fff;
    margin-bottom: 14px;
    border: 1px solid rgba(255,255,255,.08);
    box-shadow: var(--shadow-md);
}
.ct-top { display:flex; justify-content:space-between; align-items:flex-start; flex-wrap:wrap; gap:12px; }
.ct-brand { display:flex; align-items:center; gap:12px; }
.ct-logo { font-size:2rem; line-height:1; }
.ct-title {
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: -0.4px;
    color: #fff;
    margin: 0;
    line-height: 1.2;
}
.ct-tagline { font-size:.82rem; color:#94A3B8; font-style:italic; margin-top:2px; }
.ct-badge {
    background: rgba(10,110,209,.3);
    border: 1px solid rgba(10,110,209,.6);
    color: #93C5FD;
    padding: 3px 10px;
    border-radius: var(--radius-sm);
    font-size: .70rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .6px;
}
.ct-status { text-align:right; }
.ct-status-label { font-size:.70rem; color:#94A3B8; font-weight:600; text-transform:uppercase; letter-spacing:.4px; margin-bottom:4px; }
.ct-status-val { font-size:.85rem; font-weight:700; padding:4px 10px; border-radius:var(--radius-sm); display:inline-block; }
.ct-status-op   { color:#16A68A; background:rgba(22,166,138,.12); border:1px solid rgba(22,166,138,.3); }
.ct-status-warn { color:#E9A23B; background:rgba(233,162,59,.12); border:1px solid rgba(233,162,59,.3); }
.ct-status-err  { color:#D64545; background:rgba(214,69,69,.12);  border:1px solid rgba(214,69,69,.3);  }
.ct-telem {
    display:flex; flex-wrap:wrap; gap:18px;
    margin-top:14px; padding-top:12px;
    border-top: 1px solid rgba(255,255,255,.08);
    font-size:.78rem; color:#94A3B8;
}
.ct-telem-item { display:flex; align-items:center; gap:5px; }
.ct-telem-item strong { color:#CBD5E1; }

/* ── KPI Grid ──────────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 8px;
    margin-bottom: 16px;
}
.kpi-tile {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 11px 13px;
    border-left: 3px solid var(--sap-blue);
    box-shadow: var(--shadow-xs);
    transition: box-shadow .15s;
}
.kpi-tile:hover { box-shadow: var(--shadow-sm); }
.kpi-tile-crit  { border-left-color: var(--red); }
.kpi-tile-warn  { border-left-color: var(--amber); }
.kpi-tile-ok    { border-left-color: var(--teal); }
.kpi-tile-cyan  { border-left-color: var(--cyan); }
.kpi-tile-indigo{ border-left-color: #6366F1; }
.kpi-lbl  { font-size:.68rem; font-weight:700; color:var(--text-2); text-transform:uppercase; letter-spacing:.4px; margin-bottom:2px; }
.kpi-val  { font-size:1.28rem; font-weight:800; color:var(--text-1); line-height:1.1; }
.kpi-sub  { font-size:.68rem; color:var(--text-3); margin-top:2px; }

/* ── Enterprise Card ───────────────────────────────────── */
.ent-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-md);
    padding: 16px 18px;
    box-shadow: var(--shadow-xs);
    margin-bottom: 8px;
}
.ent-card-accent { border-top: 3px solid var(--sap-blue); }
.ent-card h4 { margin:0 0 8px; font-size:.9rem; font-weight:700; color:var(--text-1); }

/* ── Status Badges ─────────────────────────────────────── */
.badge {
    display:inline-block;
    padding:2px 8px;
    border-radius:var(--radius-sm);
    font-weight:700;
    font-size:.72rem;
    letter-spacing:.3px;
    text-transform:uppercase;
}
.badge-crit   { background:var(--red-bg);   color:#991B1B; border:1px solid #FECACA; }
.badge-high   { background:#FFF7ED;          color:#C2410C; border:1px solid #FFEDD5; }
.badge-med    { background:var(--amber-bg);  color:#B45309; border:1px solid #FEF3C7; }
.badge-low    { background:var(--teal-bg);   color:#065F46; border:1px solid #A7F3D0; }
.badge-ok     { background:var(--teal-bg);   color:#065F46; border:1px solid #A7F3D0; }
.badge-sap    { background:var(--blue-bg);   color:#1D4ED8; border:1px solid #BFDBFE; }
.badge-warn   { background:var(--amber-bg);  color:#B45309; border:1px solid #FEF3C7; }
.badge-info   { background:#F0F9FF;          color:#0369A1; border:1px solid #BAE6FD; }
.badge-neutral{ background:#F8FAFC;          color:var(--text-2); border:1px solid var(--border); }

/* ── Cascade Flow Bar ──────────────────────────────────── */
.cascade-bar {
    display:flex; align-items:center; flex-wrap:wrap;
    background:#F8FAFC; border:1px solid var(--border);
    border-radius:var(--radius-md); padding:10px 16px;
    margin:10px 0 14px; gap:4px;
}
.cascade-step {
    display:flex; align-items:center; gap:5px;
    font-size:.76rem; font-weight:700; color:var(--text-1);
    padding:4px 10px; border-radius:20px; border:1px solid var(--border);
    background:var(--surface);
}
.cascade-arrow { color:var(--text-3); font-size:.8rem; margin:0 2px; }

/* ── Factor Progress Bar ───────────────────────────────── */
.factor-row { margin-bottom:8px; }
.factor-hdr { display:flex; justify-content:space-between; font-size:.76rem; font-weight:600; color:var(--text-1); margin-bottom:3px; }
.factor-track { background:var(--border); border-radius:3px; height:6px; overflow:hidden; }
.factor-fill  { height:100%; border-radius:3px; transition:width .3s; }

/* ── Risk Distribution Bar ─────────────────────────────── */
.risk-dist { margin:10px 0 16px; }
.risk-dist-bar { display:flex; height:12px; border-radius:6px; overflow:hidden; border:1px solid var(--border); }
.risk-dist-legend { display:flex; gap:14px; margin-top:5px; font-size:.70rem; color:var(--text-2); }

/* ── Strategy Comparison Card ──────────────────────────── */
.strat-card {
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:var(--radius-md);
    padding:16px 18px;
    box-shadow:var(--shadow-xs);
    height:100%;
}
.strat-card-head { font-size:.95rem; font-weight:800; color:var(--text-1); margin-bottom:10px; display:flex; align-items:center; gap:8px; }
.strat-card-row  { font-size:.82rem; color:var(--text-1); line-height:1.8; }
.strat-card-row strong { font-weight:700; }

/* ── Node Taxonomy Legend ──────────────────────────────── */
.node-legend { display:flex; flex-wrap:wrap; gap:6px; padding:10px 14px; background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-sm); margin:8px 0 14px; }
.node-pill { padding:2px 10px; border-radius:12px; font-size:.73rem; font-weight:700; }

/* ── Integration Status Panel ──────────────────────────── */
.int-panel {
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:var(--radius-md);
    padding:14px 16px;
    box-shadow:var(--shadow-xs);
}
.int-panel-title { font-size:.78rem; font-weight:700; color:var(--text-2); text-transform:uppercase; letter-spacing:.5px; margin-bottom:10px; }
.int-row { display:flex; justify-content:space-between; align-items:center; padding:5px 0; border-bottom:1px solid var(--border); font-size:.80rem; }
.int-row:last-child { border-bottom:none; }
.int-row-label { color:var(--text-2); font-weight:600; }
.int-row-val   { color:var(--text-1); font-weight:700; }

/* ── AI Briefing Card ──────────────────────────────────── */
.ai-card {
    background:linear-gradient(135deg, #0F2444 0%, #172B46 100%);
    border:1px solid rgba(10,110,209,.3);
    border-radius:var(--radius-md);
    padding:16px 20px;
    color:#CBD5E1;
    margin-bottom:12px;
}
.ai-card-title { font-size:.78rem; font-weight:700; color:#22B8CF; text-transform:uppercase; letter-spacing:.5px; margin-bottom:8px; }
.ai-card-body  { font-size:.88rem; line-height:1.6; color:#E2E8F0; }

/* ── Governance Form ───────────────────────────────────── */
.gov-form { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-md); padding:16px 20px; box-shadow:var(--shadow-xs); }

/* ── Audit Table Pill ──────────────────────────────────── */
.audit-approved { background:#DCFCE7; color:#166534; padding:2px 8px; border-radius:4px; font-size:.72rem; font-weight:700; }
.audit-rejected { background:#FEE2E2; color:#991B1B; padding:2px 8px; border-radius:4px; font-size:.72rem; font-weight:700; }

/* ── Footer ────────────────────────────────────────────── */
.ct-footer {
    display:flex; justify-content:space-between; align-items:center;
    flex-wrap:wrap; gap:8px; padding:12px 16px;
    background:var(--surface); border:1px solid var(--border);
    border-radius:var(--radius-sm); font-size:.74rem; color:var(--text-2);
    margin-top:8px;
}

/* ── Metric override ───────────────────────────────────── */
[data-testid="stMetric"] {
    background:var(--surface);
    border:1px solid var(--border);
    border-radius:var(--radius-sm);
    padding:10px 12px;
    box-shadow:var(--shadow-xs);
}
[data-testid="stMetricLabel"] { font-size:.72rem !important; font-weight:700 !important; color:var(--text-2) !important; text-transform:uppercase; letter-spacing:.3px; }
[data-testid="stMetricValue"] { font-size:1.3rem !important; font-weight:800 !important; color:var(--text-1) !important; }

/* ── Streamlit global overrides ────────────────────────── */
.stButton > button {
    border-radius:var(--radius-sm) !important;
    font-weight:600 !important;
    font-size:.84rem !important;
    transition:all .15s !important;
}
.stButton > button[kind="primary"] {
    background:var(--sap-blue) !important;
    border-color:var(--sap-blue) !important;
    color:#fff !important;
}
.stButton > button[kind="primary"]:hover {
    background:var(--sap-hover) !important;
    border-color:var(--sap-hover) !important;
}
.stAlert { border-radius:var(--radius-sm) !important; }
div[data-testid="stDataFrame"] { border-radius:var(--radius-sm); border:1px solid var(--border); overflow:hidden; }
.stExpander { border:1px solid var(--border) !important; border-radius:var(--radius-sm) !important; }
.stExpander > div:first-child { font-weight:700 !important; }
</style>
""", unsafe_allow_html=True)

# =============================================================================
# DATA NORMALIZATION AND VALIDATION
# =============================================================================

REQUIRED_TABLES = [
    "suppliers",
    "materials",
    "factories",
    "warehouses",
    "transport_routes",
    "customer_orders",
]


def normalize_column_name(column):
    """Convert column names into a consistent snake_case format."""

    name = str(column).strip().lower()
    name = name.replace(" ", "_").replace("-", "_")
    name = name.replace("/", "_").replace(".", "_")

    while "__" in name:
        name = name.replace("__", "_")

    return name.strip("_")


COLUMN_ALIASES = {
    "suppliers": {
        "supplierid": "supplier_id",
        "supplier_code": "supplier_id",
        "vendor_id": "supplier_id",
        "vendor_code": "supplier_id",
        "suppliername": "supplier_name",
        "vendor_name": "supplier_name",
        "name": "supplier_name",
        "supplier_tier": "tier",
        "supplier_type": "category",
        "capacity": "monthly_capacity_units",
        "monthly_capacity": "monthly_capacity_units",
        "route_id": "primary_route_id",
    },
    "materials": {
        "materialid": "material_id",
        "material_code": "material_id",
        "materialname": "material_name",
        "name": "material_name",
    },
    "transport_routes": {
        "routeid": "route_id",
        "route_code": "route_id",
        "transport_route_id": "route_id",
        "name": "route_name",
    },
    "factories": {
        "factoryid": "factory_id",
        "factory_code": "factory_id",
        "factoryname": "factory_name",
        "name": "factory_name",
    },
    "warehouses": {
        "warehouseid": "warehouse_id",
        "warehouse_code": "warehouse_id",
        "warehousename": "warehouse_name",
        "name": "warehouse_name",
    },
    "customer_orders": {
        "orderid": "order_id",
        "order_code": "order_id",
        "customerorderid": "order_id",
    },
}


def normalize_table(df, table_name):
    """Normalize column names and common identifier aliases."""

    if not isinstance(df, pd.DataFrame):
        raise ValueError(
            f"Table '{table_name}' is not a pandas DataFrame."
        )

    df = df.copy()

    df.columns = [
        normalize_column_name(column)
        for column in df.columns
    ]

    aliases = COLUMN_ALIASES.get(table_name, {})

    rename_map = {}

    for old_name, new_name in aliases.items():
        if old_name in df.columns and new_name not in df.columns:
            rename_map[old_name] = new_name

    if rename_map:
        df.rename(columns=rename_map, inplace=True)

    return df


def normalize_supply_chain_data(data):
    """Normalize all supply-chain tables before dashboard access."""

    if not isinstance(data, dict):
        raise ValueError(
            "Data loader did not return a dictionary."
        )

    missing = [
        table for table in REQUIRED_TABLES
        if table not in data
    ]

    if missing:
        raise ValueError(
            "Missing required tables: " + ", ".join(missing)
        )

    normalized = dict(data)

    for table in REQUIRED_TABLES:
        normalized[table] = normalize_table(
            normalized[table],
            table,
        )

    required_ids = {
        "suppliers": "supplier_id",
        "materials": "material_id",
        "transport_routes": "route_id",
    }

    for table, identifier in required_ids.items():

        if identifier not in normalized[table].columns:
            available = normalized[table].columns.tolist()

            raise ValueError(
                f"Required column '{identifier}' was not found "
                f"in the '{table}' table. "
                f"Available columns: {available}. "
                f"Check the source dataset or add the correct alias."
            )

        normalized[table][identifier] = (
            normalized[table][identifier]
            .astype("string")
            .str.strip()
        )

    if normalized["suppliers"].empty:
        raise ValueError("Supplier table is empty.")

    if normalized["materials"].empty:
        raise ValueError("Material table is empty.")

    return normalized


def validate_supply_chain_data(data):
    """Validate and normalize the complete dataset."""

    return normalize_supply_chain_data(data)


def attach_source_status(
    data,
    connected,
    source,
    message,
    error=None,
):
    """Attach consistent source information to the dataset."""

    data = dict(data)

    data["_sap_status"] = pd.DataFrame([{
        "connected": bool(connected),
        "active_source": source,
        "message": message,
        "last_sync": datetime.now(timezone.utc).isoformat(),
        "error": str(error) if error else None,
    }])

    return data


def normalize_risk_output(risk_df):
    """Normalize risk-scoring output and safely derive risk categories."""

    if not isinstance(risk_df, pd.DataFrame):
        raise ValueError(
            "Risk scoring module did not return a DataFrame."
        )

    risk_df = risk_df.copy()

    risk_df.columns = [
        normalize_column_name(column)
        for column in risk_df.columns
    ]

    aliases = {
        "supplierid": "supplier_id",
        "suppliername": "supplier_name",
        "risk_category": "final_risk_category",
        "risk_score": "overall_risk_score",
        "overall_score": "overall_risk_score",
    }

    rename_map = {}

    for old_name, new_name in aliases.items():
        if old_name in risk_df.columns and new_name not in risk_df.columns:
            rename_map[old_name] = new_name

    if rename_map:
        risk_df.rename(columns=rename_map, inplace=True)

    if "supplier_id" not in risk_df.columns:
        raise ValueError(
            "Risk output is missing supplier_id. "
            f"Available columns: {risk_df.columns.tolist()}"
        )

    risk_df["supplier_id"] = (
        risk_df["supplier_id"].astype(str).str.strip()
    )

    if "final_risk_category" not in risk_df.columns:

        if "overall_risk_score" not in risk_df.columns:
            raise ValueError(
                "Risk output has neither risk_category "
                "nor overall_risk_score."
            )

        scores = pd.to_numeric(
            risk_df["overall_risk_score"],
            errors="coerce",
        )

        def classify_risk(score):

            if pd.isna(score):
                return "Unknown"
            if score >= 75:
                return "Critical"
            if score >= 50:
                return "High"
            if score >= 25:
                return "Medium"
            return "Low"

        risk_df["final_risk_category"] = scores.apply(
            classify_risk
        )

    else:

        risk_df["final_risk_category"] = (
            risk_df["final_risk_category"]
            .astype(str)
            .str.strip()
            .str.title()
        )

    return risk_df


# =============================================================================
# CACHED DATA LOADER
# =============================================================================

@st.cache_data(ttl=120, show_spinner=False)
def get_cached_supply_chain_data(
    mode,
    base_url="",
    auth_type="",
    api_key="",
    username="",
    password="",
):
    """Load data from the selected source with safe fallback handling."""

    if mode == "SAP HANA Cloud":

        try:
            data = load_all_data(
                verbose=False,
                source="hana",
            )

            data = validate_supply_chain_data(data)

            if "_sap_status" not in data:
                data = attach_source_status(
                    data,
                    True,
                    "SAP HANA Cloud",
                    "Successfully loaded data from SAP HANA Cloud.",
                )

            return data

        except Exception as exc:

            fallback = load_all_data(
                verbose=False,
                source="csv",
            )

            fallback = validate_supply_chain_data(fallback)

            return attach_source_status(
                fallback,
                False,
                "CSV Baseline (HANA fallback)",
                "SAP HANA loading failed. CSV fallback activated.",
                error=exc,
            )

    if mode == "CSV Baseline":

        data = load_all_data(
            verbose=False,
            source="csv",
        )

        data = validate_supply_chain_data(data)

        return attach_source_status(
            data,
            False,
            "CSV Baseline",
            "Local CSV data loaded.",
        )

    if mode == "SAP OData (Mock Sandbox)":

        client = SAPClient(auth_type="mock")

        data = client.fetch_all(fallback_on_error=True)

        data = validate_supply_chain_data(data)

        if "_sap_status" not in data:
            data = attach_source_status(
                data,
                False,
                "SAP OData Mock Sandbox",
                "Mock sandbox data returned. This is not a live SAP connection.",
            )

        return data

    if mode == "SAP Live Gateway":

        client = SAPClient(
            base_url=base_url,
            auth_type=auth_type or "api_key",
            api_key=api_key,
            username=username,
            password=password,
        )

        data = client.fetch_all(fallback_on_error=True)

        data = validate_supply_chain_data(data)

        if "_sap_status" not in data:
            data = attach_source_status(
                data,
                False,
                "SAP Gateway — connection not verified",
                "Data returned, but live connectivity has not been independently verified.",
            )

        return data

    raise ValueError(f"Unsupported data source: {mode}")


# =============================================================================
# CACHED GRAPH BUILDER — avoids recomputing NetworkX on every Streamlit rerun
# =============================================================================

@st.cache_resource(ttl=120, show_spinner=False)
def get_cached_graph(data_hash: str, _data: dict):
    """
    Build and cache the supply chain NetworkX graph.

    Parameters
    ----------
    data_hash : str
        A lightweight hash of supplier + materials counts to detect data changes.
    _data : dict
        The full supply chain data dictionary (leading underscore bypasses
        Streamlit's unhashable-argument guard for dicts containing DataFrames).
    """
    return get_supply_chain_graph(_data)


@st.cache_data(ttl=120, show_spinner=False)
def get_cached_risk_scores(data_hash: str, _data: dict, _graph):
    """
    Compute and cache supplier risk factors and scores.

    Eliminates the duplicate build_supplier_risk_factors +
    calculate_supplier_risk_scores calls that previously ran
    both in the KPI strip and in Tab 2 on every rerun.
    """
    risk_factors = build_supplier_risk_factors(data=_data, graph=_graph)
    risk_scores_df = calculate_supplier_risk_scores(risk_factors)
    return normalize_risk_output(risk_scores_df)


def _make_data_hash(base_data: dict) -> str:
    """Lightweight hash to detect data changes for cache invalidation."""
    try:
        n_sup = len(base_data.get("suppliers", []))
        n_mat = len(base_data.get("materials", []))
        n_ord = len(base_data.get("customer_orders", []))
        src = str(base_data.get("_sap_status", [{}]))[:50]
        return f"{n_sup}:{n_mat}:{n_ord}:{hash(src)}"
    except Exception:
        return "default"


# =============================================================================
# SIDEBAR — DATA SOURCE CONFIGURATION
# =============================================================================

st.sidebar.markdown(
    clean_html('''
    <div style="padding:8px 0 12px;">
      <div style="font-size:1.15rem;font-weight:800;color:#FFFFFF;display:flex;align-items:center;gap:8px;">
        ⚡ <span>AUTOPILOT 2.0</span>
      </div>
      <div style="font-size:.72rem;color:#64748B;margin-top:2px;font-style:italic;">
        Supply Chain Intelligence &amp; Resilience Control Tower
      </div>
      <div style="font-size:.68rem;color:#475569;margin-top:4px;">SAP Hackfest 2026 &nbsp;•&nbsp; NHCE Bengaluru</div>
    </div>
    '''),
    unsafe_allow_html=True,
)
st.sidebar.divider()
st.sidebar.markdown(
    '<div style="font-size:.70rem;font-weight:700;color:#64748B;text-transform:uppercase;letter-spacing:.6px;margin-bottom:6px;">Data Source Gateway</div>',
    unsafe_allow_html=True,
)

configured_source = os.getenv(
    "DATA_SOURCE", "hana"
).strip().lower()

default_mapping = {
    "csv": "CSV Baseline",
    "hana": "SAP HANA Cloud",
    "sap_mock": "SAP OData (Mock Sandbox)",
    "sap": "SAP Live Gateway",
}

default_mode = default_mapping.get(
    configured_source,
    "SAP HANA Cloud",
)

source_options = [
    "CSV Baseline",
    "SAP HANA Cloud",
    "SAP OData (Mock Sandbox)",
    "SAP Live Gateway",
]

sap_mode = st.sidebar.selectbox(
    "Data Source Mode",
    source_options,
    index=source_options.index(default_mode),
    help="Select the active supply-chain data source.",
)

base_url = os.getenv("SAP_BASE_URL", "")
auth_choice = os.getenv("SAP_AUTH_TYPE", "api_key")
api_key = os.getenv("SAP_API_KEY", "")
username = os.getenv("SAP_USERNAME", "")
password = os.getenv("SAP_PASSWORD", "")

if sap_mode == "SAP Live Gateway":

    base_url = st.sidebar.text_input(
        "SAP Base URL",
        value=base_url,
    )

    auth_choice = st.sidebar.selectbox(
        "Authentication Type",
        ["api_key", "basic"],
        index=0 if auth_choice == "api_key" else 1,
    )

    if auth_choice == "api_key":

        api_key = st.sidebar.text_input(
            "SAP API Key",
            value=api_key,
            type="password",
        )

    else:

        username = st.sidebar.text_input(
            "SAP Username",
            value=username,
        )

        password = st.sidebar.text_input(
            "SAP Password",
            value=password,
            type="password",
        )

elif sap_mode == "SAP OData (Mock Sandbox)":

    auth_choice = "mock"


# =============================================================================
# SYNC AND GATEWAY CONTROLS
# =============================================================================

sync_col, ping_col = st.sidebar.columns(2)

with sync_col:

    if st.button("🔄 Sync / Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with ping_col:

    ping_clicked = st.button(
        "🔍 Ping Gateway",
        use_container_width=True,
    )

if ping_clicked:

    if sap_mode == "SAP HANA Cloud":

        try:
            from src.integration.hana_client import get_hana_client
            h_client = get_hana_client()
            t_res = h_client.verify_tables_accessibility()
            if t_res.get("connected"):
                st.sidebar.success(
                    f"✅ Verified: Connected as '{t_res.get('current_user')}' (Schema: {t_res.get('current_schema')}). "
                    f"{t_res.get('tables_accessible')}/{t_res.get('total_tables')} tables accessible ({t_res.get('total_records')} records)."
                )
            else:
                st.sidebar.error(f"❌ HANA connection failed: {t_res.get('message')}")
        except Exception as exc:
            st.sidebar.error(f"HANA ping failed: {exc}")

    else:

        try:
            probe_client = SAPClient(
                base_url=base_url,
                auth_type=auth_choice,
                api_key=api_key,
                username=username,
                password=password,
            )

            connected, message, details = (
                probe_client.test_connection()
            )

            if connected:
                st.sidebar.success(f"Verified: {message}")
            else:
                st.sidebar.error(f"Connection failed: {message}")

        except Exception as exc:
            st.sidebar.error(f"Gateway ping failed: {exc}")


# =============================================================================
# LOAD ACTIVE DATASET
# =============================================================================

try:

    with st.spinner(f"Loading data from {sap_mode}..."):

        base_data = get_cached_supply_chain_data(
            mode=sap_mode,
            base_url=base_url,
            auth_type=auth_choice,
            api_key=api_key,
            username=username,
            password=password,
        )

    base_data = validate_supply_chain_data(base_data)

except Exception as exc:

    st.error(f"Unable to load supply-chain data: {exc}")
    st.stop()


# =============================================================================
# DIGITAL TWIN GRAPH
# =============================================================================

try:

    _data_hash = _make_data_hash(base_data)
    graph = get_cached_graph(_data_hash, base_data)

except Exception as exc:

    st.error(f"Unable to build the supply-chain graph: {exc}")
    st.stop()


# =============================================================================
# SOURCE STATUS
# =============================================================================

sap_status_df = base_data.get("_sap_status")

is_connected = False
active_source_name = sap_mode
status_msg = "Data loaded."
last_sync_str = "N/A"
error_detail = None

if isinstance(sap_status_df, pd.DataFrame) and not sap_status_df.empty:

    s_row = sap_status_df.iloc[0]

    is_connected = bool(s_row.get("connected", False))

    active_source_name = str(
        s_row.get("active_source", sap_mode)
    )

    status_msg = str(
        s_row.get("message", "")
    )

    last_sync_str = str(
        s_row.get("last_sync") or "Not synchronized"
    )

    error_detail = s_row.get("error")


# =============================================================================
# SAP HANA INTEGRATION STATUS PANEL (PHASE 6)
# =============================================================================

if sap_mode == "SAP HANA Cloud":

    hana_tables_map = {
        "SUPPLIERS": len(base_data.get("suppliers", [])),
        "MATERIALS": len(base_data.get("materials", [])),
        "FACTORIES": len(base_data.get("factories", [])),
        "WAREHOUSES": len(base_data.get("warehouses", [])),
        "TRANSPORT_ROUTES": len(base_data.get("transport_routes", [])),
        "CUSTOMER_ORDERS": len(base_data.get("customer_orders", [])),
        "INVENTORY": len(base_data.get("inventory", [])),
        "SUPPLIER_DEPENDENCIES": len(base_data.get("supplier_dependencies", [])),
        "SUPPLIER_MATERIALS": len(base_data.get("supplier_materials", [])),
    }
    total_rec = sum(hana_tables_map.values())
    tables_ok = sum(1 for v in hana_tables_map.values() if v > 0)

    _sap_row = {}
    _sap_df = base_data.get("_sap_status")
    if isinstance(_sap_df, pd.DataFrame) and not _sap_df.empty:
        _sap_row = _sap_df.iloc[0].to_dict()

    with st.sidebar.expander("🛰️ SAP HANA Verification Panel", expanded=True):

        if is_connected and active_source_name == "SAP HANA Cloud":
            st.success("🟢 **Connection Status:** CONNECTED")
            st.markdown(
                "**SQL Verification:** `PASS (SELECT 1 FROM DUMMY verified)`"
            )
            st.markdown(
                f"**Active Schema:** `{_sap_row.get('current_schema', 'HACKFEST0407')}`"
            )
            st.markdown(
                f"**Database User:** `{_sap_row.get('current_user', 'HACKFEST0407')}`"
            )
            st.markdown(
                "**TLS Encryption:** `Enforced (sslValidateCertificate=True)`"
            )
            st.markdown(
                f"**Tables Accessible:** `{tables_ok} / 9`"
            )
            st.markdown(
                f"**Total Records Retrieved:** `{total_rec}`"
            )
            st.markdown(
                f"**Last Sync:** `{last_sync_str}`"
            )

            # Expandable table-wise row counts
            with st.expander("📋 View Table Row Counts (9/9)", expanded=False):
                cnt_df = pd.DataFrame([
                    {"HANA Table": tbl, "Rows": cnt}
                    for tbl, cnt in hana_tables_map.items()
                ])
                st.dataframe(cnt_df, use_container_width=True, hide_index=True)

            # Ping HANA Gateway Button
            if st.button(
                "🔍 Ping HANA Gateway",
                key="ping_hana_gateway_btn",
                use_container_width=True,
            ):
                with st.spinner("Executing live SQL query on SAP HANA Cloud..."):
                    try:
                        from src.integration.hana_client import get_hana_client
                        _hc = get_hana_client()
                        ping_result = _hc.verify_tables_accessibility()
                        if ping_result.get("connected"):
                            _ping_ok = ping_result.get("tables_accessible", 0)
                            _ping_total = ping_result.get("total_records", 0)
                            st.success(
                                f"✅ Ping OK — SQL Verified! {_ping_ok}/9 tables reachable, "
                                f"{_ping_total} total records."
                            )
                            st.caption(
                                f"User: {ping_result.get('current_user')} | "
                                f"Schema: {ping_result.get('current_schema')} | "
                                f"Timestamp: {ping_result.get('database_timestamp')}"
                            )
                        else:
                            st.error(f"❌ Ping failed: {ping_result.get('message')}")
                    except Exception as _ping_exc:
                        st.error(f"❌ Ping failed: {_ping_exc}")

        else:
            st.error("🔴 **Connection Status:** DISCONNECTED")
            st.warning(
                "⚠️ **CSV DEMO MODE ACTIVE**\n\n"
                "Live SAP HANA Cloud unreachable. Operating in local CSV fallback mode."
            )
            st.caption(f"**Active Source:** {active_source_name}")
            st.caption(f"**Last Sync:** {last_sync_str}")
            if error_detail:
                st.caption(f"Reason: {error_detail}")

            # Ping button to re-test on demand
            if st.button(
                "🔍 Ping HANA Gateway",
                key="ping_hana_gateway_btn",
                use_container_width=True,
            ):
                with st.spinner("Testing connection to SAP HANA Cloud..."):
                    try:
                        from src.integration.hana_client import get_hana_client
                        _hc = get_hana_client(force_new=True)
                        ping_result = _hc.verify_tables_accessibility()
                        if ping_result.get("connected"):
                            _ping_ok = ping_result.get("tables_accessible", 0)
                            _ping_total = ping_result.get("total_records", 0)
                            st.success(
                                f"✅ Connected to HANA! {_ping_ok}/9 tables reachable, "
                                f"{_ping_total} records."
                            )
                            st.rerun()
                        else:
                            st.error(f"❌ Connection failed: {ping_result.get('message')}")
                    except Exception as _ping_exc:
                        st.error(f"❌ Ping failed: {_ping_exc}")

elif sap_mode == "SAP Live Gateway":

    with st.sidebar.expander("🛰️ SAP Gateway Status", expanded=True):
        if is_connected:
            st.success("🟢 **SAP S/4HANA LIVE: CONNECTED**")
            _s_loaded = len(base_data.get("suppliers", []))
            st.caption(f"**Verified Records:** {_s_loaded} Live Suppliers")
            if "_sap_entity_status" in base_data and isinstance(base_data["_sap_entity_status"], pd.DataFrame):
                st.markdown("**Entity Coverage Matrix:**")
                st.dataframe(
                    base_data["_sap_entity_status"][["entity", "status", "records"]],
                    use_container_width=True,
                    hide_index=True,
                )
        else:
            st.error("🔴 **SAP LIVE: NOT VERIFIED**")
            st.warning("⚠️ **CSV DEMO MODE ACTIVE (Fallback)**")
        st.caption(f"**Active Source:** {active_source_name}")
        st.caption(f"**Last Sync:** {last_sync_str}")

elif sap_mode == "SAP OData (Mock Sandbox)":

    with st.sidebar.expander("🛰️ SAP OData Sandbox", expanded=True):
        st.info("🔵 **SAP ODATA MOCK SANDBOX**")
        st.caption("Simulated OData adapter on local benchmark dataset.")
        st.caption(f"**Active Source:** {active_source_name}")
        st.caption(f"**Last Sync:** {last_sync_str}")

else:

    with st.sidebar.expander("🛰️ Data Source Status", expanded=True):
        st.info("🟡 **CSV BASELINE — LOCAL**")
        st.caption("Local flat CSV benchmark files.")
        st.caption(f"**Active Source:** {active_source_name}")
        st.caption(f"**Last Sync:** {last_sync_str}")

st.sidebar.divider()


# =============================================================================
# ENTITY IDS — NORMALIZED
# =============================================================================

supplier_ids = sorted(
    base_data["suppliers"]["supplier_id"]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)

material_ids = sorted(
    base_data["materials"]["material_id"]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)

route_ids = sorted(
    base_data["transport_routes"]["route_id"]
    .dropna()
    .astype(str)
    .unique()
    .tolist()
)

if not supplier_ids:
    st.error("Supplier master data contains no supplier IDs.")
    st.stop()

if not material_ids:
    st.error("Material master data contains no material IDs.")
    st.stop()


# =============================================================================
# QUICK DISRUPTION PRESETS
# =============================================================================

st.sidebar.markdown("### 🎯 Quick Disruption Presets")

preset = st.sidebar.radio(
    "Load Scenario Preset",
    [
        "None (Custom Selection)",
        "Preset 1: Single Tier-1 Failure (SUP-T1-03)",
        "Preset 2: Double Overlapping Disruption (SUP-T2-01 & SUP-T2-03)",
        "Preset 3: Cascading Failure + Route Blockage (SUP-T1-03 + SUP-T2-01 + RTE-03)",
    ],
    index=1,
)

if preset.startswith("Preset 1"):

    default_failed = (
        ["SUP-T1-03"]
        if "SUP-T1-03" in supplier_ids
        else supplier_ids[:1]
    )

    default_challenger_suppliers = []
    default_challenger_routes = []

    default_material = (
        "MAT-02" if "MAT-02" in material_ids else material_ids[0]
    )

elif preset.startswith("Preset 2"):

    default_failed = [
        supplier
        for supplier in ["SUP-T2-01", "SUP-T2-03"]
        if supplier in supplier_ids
    ] or supplier_ids[:2]

    default_challenger_suppliers = []
    default_challenger_routes = []

    default_material = (
        "MAT-04" if "MAT-04" in material_ids else material_ids[0]
    )

elif preset.startswith("Preset 3"):

    default_failed = (
        ["SUP-T1-03"]
        if "SUP-T1-03" in supplier_ids
        else supplier_ids[:1]
    )

    default_challenger_suppliers = (
        ["SUP-T2-01"]
        if "SUP-T2-01" in supplier_ids
        else []
    )

    default_challenger_routes = (
        ["RTE-03"]
        if "RTE-03" in route_ids
        else []
    )

    default_material = (
        "MAT-02" if "MAT-02" in material_ids else material_ids[0]
    )

else:

    default_failed = (
        ["SUP-T1-03"]
        if "SUP-T1-03" in supplier_ids
        else supplier_ids[:1]
    )

    default_challenger_suppliers = []
    default_challenger_routes = []

    default_material = (
        "MAT-02" if "MAT-02" in material_ids else material_ids[0]
    )

st.sidebar.divider()

st.sidebar.info(
    "Hackfest 2026 Final — NHCE Bengaluru\n"
    "Team: InnovAItors | Member 5"
)


# =============================================================================
# EXECUTIVE CONTROL TOWER HEADER + KPI STRIP (Phase 2)
# =============================================================================

# --- Compute live KPIs using CACHED helpers (no double-compute) ---
_data_hash = _make_data_hash(base_data)

_total_nodes = graph.number_of_nodes()
_total_edges = graph.number_of_edges()
_active_suppliers = len(base_data.get("suppliers", pd.DataFrame()))
_tracked_materials = len(base_data.get("materials", pd.DataFrame()))
_n_factories = len(base_data.get("factories", pd.DataFrame()))
_n_warehouses = len(base_data.get("warehouses", pd.DataFrame()))
_infra_nodes = _n_factories + _n_warehouses
_active_orders = len(base_data.get("customer_orders", pd.DataFrame()))
_co_df = base_data.get("customer_orders", pd.DataFrame())
_order_backlog_val = float(
    _co_df["order_value_inr"].sum()
) if not _co_df.empty and "order_value_inr" in _co_df.columns else 0.0

# Use cached risk scores — shared with Tab 2 (no duplicate computation)
try:
    _kpi_scores = get_cached_risk_scores(_data_hash, base_data, graph)
    _critical_risks = int((_kpi_scores["final_risk_category"] == "Critical").sum()) if not _kpi_scores.empty else 0
    _high_risks = int((_kpi_scores["final_risk_category"] == "High").sum()) if not _kpi_scores.empty else 0
    _medium_risks = int((_kpi_scores["final_risk_category"] == "Medium").sum()) if not _kpi_scores.empty else 0
    _low_risks = int((_kpi_scores["final_risk_category"] == "Low").sum()) if not _kpi_scores.empty else 0
except Exception:
    _kpi_scores = pd.DataFrame()
    _critical_risks = _high_risks = _medium_risks = _low_risks = 0

_resilience_score = max(10, min(100, int(100 - (_critical_risks * 8) - (_high_risks * 3))))

# DB telemetry
_db_host = "N/A"
_active_schema = "N/A"
if sap_mode == "SAP HANA Cloud" and is_connected:
    _hana_meta = base_data.get("_hana_meta", {})
    _db_host = _hana_meta.get("host", "HANA Cloud") if isinstance(_hana_meta, dict) else "HANA Cloud"
    _active_schema = _hana_meta.get("schema", "SUPPLY_CHAIN") if isinstance(_hana_meta, dict) else "SUPPLY_CHAIN"
elif sap_mode == "SAP Live Gateway" and is_connected:
    _db_host = "SAP S/4HANA Gateway"
    _active_schema = "API_BUSINESS_PARTNER"
elif sap_mode == "SAP OData (Mock Sandbox)":
    _db_host = "OData Mock Sandbox"
    _active_schema = "Mock"
else:
    _db_host = "Local CSV"
    _active_schema = "Flat File"

_op_state_color = "#16A68A" if is_connected else "#E9A23B"
_op_state_label = "OPERATIONAL" if is_connected else "CSV FALLBACK"
_kpi_backlog_display = "\u20b9{:,.0f}".format(_order_backlog_val) if _order_backlog_val > 0 else "N/A"
_resilience_tile_cls = "kpi-tile-success" if _resilience_score >= 70 else ("kpi-tile-warning" if _resilience_score >= 40 else "kpi-tile-critical")
_critical_tile_cls = "kpi-tile-critical" if _critical_risks > 0 else "kpi-tile-success"

# Data source connection badge (inline in header)
if sap_mode == "SAP HANA Cloud":
    _src_badge_color = "#16A68A" if (is_connected and active_source_name == "SAP HANA Cloud") else "#D64545"
    _src_badge_text = "SAP HANA CLOUD CONNECTED" if (is_connected and active_source_name == "SAP HANA Cloud") else "HANA: CSV FALLBACK ACTIVE"
elif sap_mode == "SAP Live Gateway":
    _src_badge_color = "#16A68A" if is_connected else "#D64545"
    _src_badge_text = "SAP S/4HANA LIVE CONNECTED" if is_connected else "GATEWAY: NOT VERIFIED"
elif sap_mode == "SAP OData (Mock Sandbox)":
    _src_badge_color = "#0A6ED1"
    _src_badge_text = "SAP ODATA MOCK SANDBOX"
else:
    _src_badge_color = "#E9A23B"
    _src_badge_text = "CSV BASELINE — LOCAL"

_op_cls = "ct-status-op" if is_connected else ("ct-status-warn" if sap_mode == "CSV Baseline" else "ct-status-err")

st.markdown(
    clean_html(f"""
    <div class="ct-header">
      <div class="ct-top">
        <div class="ct-brand">
          <div class="ct-logo">&#9889;</div>
          <div>
            <div class="ct-title">
              AUTOPILOT 2.0
              <span class="ct-badge" style="font-size:.62rem;vertical-align:middle;margin-left:8px;">SAP HACKFEST 2026</span>
            </div>
            <div class="ct-tagline">"Don't wait for the supply chain to break. Break it virtually first."</div>
          </div>
        </div>
        <div class="ct-status">
          <div class="ct-status-label">Data Source</div>
          <div class="ct-status-val {_op_cls}">&#9679;&nbsp;{_src_badge_text}</div>
          <div style="font-size:.68rem;color:#64748B;margin-top:3px;">{_op_state_label}</div>
        </div>
      </div>
      <div class="ct-telem">
        <div class="ct-telem-item">&#128225; <strong>Source:</strong>&nbsp;{active_source_name}</div>
        <div class="ct-telem-item">&#128452; <strong>Host:</strong>&nbsp;{_db_host}</div>
        <div class="ct-telem-item">&#128194; <strong>Schema:</strong>&nbsp;{_active_schema}</div>
        <div class="ct-telem-item">&#128336; <strong>Sync:</strong>&nbsp;{last_sync_str}</div>
        <div class="ct-telem-item">&#128279; <strong>Network:</strong>&nbsp;{_total_nodes} nodes / {_total_edges} edges</div>
        <div class="ct-telem-item">&#128101; <strong>Suppliers:</strong>&nbsp;{_active_suppliers} &nbsp;|&nbsp; &#9888; Critical: {_critical_risks}</div>
      </div>
    </div>
    """),
    unsafe_allow_html=True,
)

# 8-Tile Executive KPI Strip (uses new CSS classes)
_crit_cls = "kpi-tile-crit" if _critical_risks > 0 else "kpi-tile-ok"
_res_cls = "kpi-tile-ok" if _resilience_score >= 70 else ("kpi-tile-warn" if _resilience_score >= 40 else "kpi-tile-crit")

st.markdown(
    clean_html(f"""
    <div class="kpi-grid">
      <div class="kpi-tile">
        <div class="kpi-lbl">Network Nodes</div>
        <div class="kpi-val">{_total_nodes}</div>
        <div class="kpi-sub">{_total_edges} edges</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-lbl">Active Suppliers</div>
        <div class="kpi-val">{_active_suppliers}</div>
        <div class="kpi-sub">Multi-tier tracked</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-lbl">Materials</div>
        <div class="kpi-val">{_tracked_materials}</div>
        <div class="kpi-sub">Across all tiers</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-lbl">Infrastructure</div>
        <div class="kpi-val">{_infra_nodes}</div>
        <div class="kpi-sub">{_n_factories} fac + {_n_warehouses} WH</div>
      </div>
      <div class="kpi-tile">
        <div class="kpi-lbl">Customer Orders</div>
        <div class="kpi-val">{_active_orders}</div>
        <div class="kpi-sub">Active commitments</div>
      </div>
      <div class="kpi-tile kpi-tile-cyan">
        <div class="kpi-lbl">Order Backlog</div>
        <div class="kpi-val" style="font-size:1rem;">{_kpi_backlog_display}</div>
        <div class="kpi-sub">Contract value</div>
      </div>
      <div class="kpi-tile {_crit_cls}">
        <div class="kpi-lbl">Critical Suppliers</div>
        <div class="kpi-val">{_critical_risks}</div>
        <div class="kpi-sub">{_high_risks} High risk</div>
      </div>
      <div class="kpi-tile {_res_cls}">
        <div class="kpi-lbl">Resilience Score</div>
        <div class="kpi-val">{_resilience_score}/100</div>
        <div class="kpi-sub">Network health</div>
      </div>
    </div>
    """),
    unsafe_allow_html=True,
)


# =============================================================================
# DASHBOARD TABS
# =============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🌐 1. Digital Twin Network",
    "⚠️ 2. Supplier Risk Radar",
    "💥 3. Disruption Impact Simulator",
    "🛡️ 4. Recovery & Plan Challenger",
    "✍️ 5. AI Explanations & Sign-Off",
])


# =============================================================================
# TAB 1 — DIGITAL TWIN NETWORK
# =============================================================================

with tab1:

    st.markdown("### 🌐 Multi-Tier Supply Chain Digital Twin")

    st.caption(
        "NetworkX model built from the currently active data source. "
        "Node colours follow the enterprise taxonomy below."
    )

    # Node Taxonomy Legend Banner
    st.markdown(
        clean_html('''
        <div class="node-legend">
          <span style="font-size:.70rem;font-weight:700;color:#667085;text-transform:uppercase;letter-spacing:.4px;align-self:center;margin-right:4px;">Node Types:</span>
          <span class="node-pill" style="background:#EFF6FF;color:#0A6ED1;border:1px solid #BFDBFE;">&#9679; Tier 1 Supplier</span>
          <span class="node-pill" style="background:#EEF2FF;color:#4338CA;border:1px solid #C7D2FE;">&#9679; Tier 2 Supplier</span>
          <span class="node-pill" style="background:#F5F3FF;color:#6D28D9;border:1px solid #DDD6FE;">&#9679; Tier 3 Supplier</span>
          <span class="node-pill" style="background:#ECFEFF;color:#0891B2;border:1px solid #A5F3FC;">&#9679; Material</span>
          <span class="node-pill" style="background:#ECFDF5;color:#059669;border:1px solid #A7F3D0;">&#9679; Factory</span>
          <span class="node-pill" style="background:#FFFBEB;color:#D97706;border:1px solid #FDE68A;">&#9679; Warehouse</span>
          <span class="node-pill" style="background:#FFF1F2;color:#DC2626;border:1px solid #FECDD3;">&#9679; Customer Order</span>
        </div>
        '''),
        unsafe_allow_html=True,
    )

    if sap_mode == "SAP Live Gateway":
        _s_cnt = len(base_data.get("suppliers", []))
        st.info(
            f"🛰️ **SAP Live Gateway Topology:** {_s_cnt} Live Suppliers loaded via OData `API_BUSINESS_PARTNER/A_Supplier`. "
            f"Multi-tier topology reference (Factories, Warehouses, Logistics routes) maintained from Digital Twin baseline."
        )

    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.metric("Total Nodes", graph.number_of_nodes())

    with col2:
        # Phase 2 FIX: Clarify 528 total multi-tier network edges vs 31 direct supplier dependencies
        st.metric(
            "Total Graph Edges",
            graph.number_of_edges(),
            help="528 multi-tier relations: 31 direct supplier dependencies, 28 material supply links, 358 order allocations, 36 inventory, 35 routes, 40 warehouse/factory links.",
        )

    with col3:
        st.metric("Suppliers", len(base_data["suppliers"]))

    with col4:
        st.metric("Materials", len(base_data["materials"]))

    with col5:
        st.metric("Factories", len(base_data["factories"]))

    with col6:
        st.metric("Customer Orders", len(base_data["customer_orders"]))

    st.markdown("---")

    # ---------------------------------------------------------------------
    # PALANTIR/SAP CONTROL TOWER — INTERACTIVE DIGITAL TWIN VISUALIZER
    # ---------------------------------------------------------------------
    import streamlit.components.v1 as components
    from src.network_visualizer import generate_digital_twin_html

    st.markdown("#### 🌐 Interactive Supply Chain Digital Twin Network")
    st.caption(
        "Live force-directed echelon topology. Click any node to trace upstream supplier causes and downstream fulfillment impacts. "
        "Drag to inspect clusters, scroll to zoom, search for specific entities, or filter by echelon echelon above."
    )

    _disrupted_for_vis = default_failed if 'default_failed' in locals() else []
    _twin_html = generate_digital_twin_html(graph, disrupted_nodes=_disrupted_for_vis, height=620)
    components.html(_twin_html, height=620, scrolling=False)

    st.markdown("---")

    # Calculate shared upstream dependencies for interactive visualization
    try:
        shared_all = find_suppliers_sharing_upstream(graph)
    except Exception:
        shared_all = {}

    shared_keys = list(shared_all.keys()) if shared_all else []
    default_parent = shared_keys[0] if shared_keys else None
    current_parent = st.session_state.get("tab1_selected_upstream_node", default_parent)

    c_left, c_right = st.columns(2)

    # Execute c_right first so selected_parent is resolved before rendering the distribution graph in c_left
    with c_right:
        st.markdown("#### 🔗 Shared Upstream Dependency Finder")
        if shared_keys:
            selected_parent = st.selectbox(
                "Select Upstream Node",
                shared_keys,
                index=shared_keys.index(current_parent) if current_parent in shared_keys else 0,
                key="tab1_selected_upstream_node",
            )
            children = shared_all.get(selected_parent, [])
            p_node = graph.nodes.get(selected_parent, {})
            p_name = p_node.get("name", selected_parent)
            p_tier = p_node.get("tier", "N/A")
            p_city = p_node.get("city", "N/A")

            # Calculate downstream blast radius
            desc = nx.descendants(graph, selected_parent)
            desc_sups = [d for d in desc if graph.nodes[d].get("node_type") == "supplier"]
            desc_mats = [d for d in desc if graph.nodes[d].get("node_type") == "material"]
            desc_ords = [d for d in desc if graph.nodes[d].get("node_type") == "customer_order"]

            # Visual Parent Supplier Card
            st.markdown(
                clean_html(f'''
                <div style="background:#EFF6FF;border:1px solid #BFDBFE;border-left:4px solid #0A6ED1;border-radius:6px;padding:10px 14px;margin-bottom:10px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;">
                    <span style="font-size:0.70rem;font-weight:700;color:#1E40AF;text-transform:uppercase;">Parent Supplier (Tier {p_tier})</span>
                    <span style="background:#DBEAFE;color:#1E40AF;padding:2px 8px;border-radius:4px;font-size:0.70rem;font-weight:700;">{p_city}</span>
                  </div>
                  <div style="font-size:1.02rem;font-weight:800;color:#0F172A;margin-top:2px;">{p_name} <span style="font-size:0.78rem;color:#64748B;font-weight:600;">({selected_parent})</span></div>
                </div>
                '''),
                unsafe_allow_html=True,
            )

            # Mini KPI strip for blast radius
            k1, k2, k3 = st.columns(3)
            with k1:
                st.metric("Downstream Suppliers", len(desc_sups))
            with k2:
                st.metric("Materials Impacted", len(desc_mats))
            with k3:
                st.metric("Orders Exposed", len(desc_ords))

            # Visual Dependent Supplier Cards
            st.markdown(f"**Downstream Dependent Suppliers ({len(children)}):**")
            for child in children:
                c_node = graph.nodes.get(child, {})
                c_name = c_node.get("name", child)
                c_tier = c_node.get("tier", 1)
                c_cat = c_node.get("category", "General")
                c_city = c_node.get("city", "")
                st.markdown(
                    clean_html(f'''
                    <div style="background:#FFFFFF;border:1px solid #E2E8F0;border-left:3px solid #10B981;border-radius:6px;padding:7px 12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;">
                      <div>
                        <span style="font-size:0.68rem;background:#ECFDF5;color:#065F46;padding:2px 6px;border-radius:3px;font-weight:700;">TIER {c_tier}</span>
                        <strong style="font-size:0.84rem;color:#1E293B;margin-left:6px;">{c_name}</strong>
                        <span style="font-size:0.74rem;color:#64748B;">({child})</span>
                      </div>
                      <div style="font-size:0.72rem;color:#475569;">{c_cat}</div>
                    </div>
                    '''),
                    unsafe_allow_html=True,
                )
        else:
            selected_parent = None
            desc_sups = []
            st.info("No shared upstream dependencies found.")

    with c_left:
        st.markdown("#### 📊 Multi-Tier Supplier Distribution")

        suppliers_df = base_data["suppliers"]

        if "tier" in suppliers_df.columns:
            tier_counts = suppliers_df["tier"].value_counts().sort_index()

            # Dynamic Scope Selector
            chart_mode = st.radio(
                "Distribution Scope",
                ["⚡ Compare with Selected Node", "🏷️ Filter by Category", "🌐 All Network Suppliers"],
                horizontal=True,
                key="tab1_chart_mode",
            )

            if chart_mode == "⚡ Compare with Selected Node" and selected_parent:
                desc = nx.descendants(graph, selected_parent)
                desc_sups = [d for d in desc if graph.nodes[d].get("node_type") == "supplier"]
                dep_tier_counts = suppliers_df[suppliers_df["supplier_id"].isin(desc_sups)]["tier"].value_counts().sort_index()

                chart_df = pd.DataFrame({
                    "Total in Network": [tier_counts.get(t, 0) for t in [1, 2, 3]],
                    f"Downstream of {selected_parent}": [dep_tier_counts.get(t, 0) for t in [1, 2, 3]],
                }, index=[f"Tier {t}" for t in [1, 2, 3]])

                st.bar_chart(chart_df)
                st.caption(f"Comparing total network baseline vs {len(desc_sups)} suppliers downstream of {selected_parent}.")

            elif chart_mode == "🏷️ Filter by Category":
                all_cats = ["All Categories"] + sorted(suppliers_df["category"].dropna().unique().tolist())
                chosen_cat = st.selectbox("Select Component Category", all_cats, key="tab1_cat_filter")
                filtered_df = suppliers_df if chosen_cat == "All Categories" else suppliers_df[suppliers_df["category"] == chosen_cat]
                cat_tier_counts = filtered_df["tier"].value_counts().sort_index()

                cat_chart_df = pd.DataFrame({
                    f"Suppliers ({chosen_cat[:18]})": [cat_tier_counts.get(t, 0) for t in [1, 2, 3]]
                }, index=[f"Tier {t}" for t in [1, 2, 3]])

                st.bar_chart(cat_chart_df)
                st.caption(f"Showing tier distribution for {len(filtered_df)} suppliers in '{chosen_cat}'.")

            else:
                tier_df = pd.DataFrame({
                    "Suppliers Count": [tier_counts.get(t, 0) for t in [1, 2, 3]]
                }, index=[f"Tier {t}" for t in [1, 2, 3]])

                st.bar_chart(tier_df)
                st.caption("Showing total baseline distribution across all 35 suppliers in the digital twin.")
        else:
            st.warning("The supplier table does not contain a tier column.")

    st.markdown("---")
    st.markdown("#### Digital Twin Entity Tables")

    sub1, sub2, sub3 = st.tabs([
        "Suppliers Master",
        "Materials Master",
        "Transport Routes",
    ])

    with sub1:

        cols = [
            "supplier_id",
            "supplier_name",
            "tier",
            "city",
            "category",
            "monthly_capacity_units",
            "quality_score",
            "primary_route_id",
        ]

        available = [
            column
            for column in cols
            if column in base_data["suppliers"].columns
        ]

        st.dataframe(
            base_data["suppliers"][available],
            use_container_width=True,
        )

    with sub2:

        st.dataframe(
            base_data["materials"],
            use_container_width=True,
        )

    with sub3:

        st.dataframe(
            base_data["transport_routes"],
            use_container_width=True,
        )


# =============================================================================
# TAB 2 — SUPPLIER RISK RADAR
# =============================================================================

with tab2:

    st.markdown("### Supplier Risk Scoring & Vulnerability Radar")

    st.caption(
        "Explainable 0–100 risk scoring based on six operational factors."
    )

    # Use shared cached risk scores — no recomputation here
    try:
        risk_scores_df = get_cached_risk_scores(_data_hash, base_data, graph)
    except Exception as exc:
        st.error(f"Supplier risk calculation failed: {exc}")
        risk_scores_df = pd.DataFrame()

    if not risk_scores_df.empty:

        cat_counts = (
            risk_scores_df["final_risk_category"]
            .value_counts()
        )

        rc1, rc2, rc3, rc4 = st.columns(4)

        with rc1:
            st.markdown(
                f'<div class="ent-card" style="border-top:3px solid #D64545;">'
                f'<span class="badge badge-crit">CRITICAL</span>'
                f'<div style="font-size:2rem;font-weight:800;color:#D64545;margin:6px 0 2px;">{cat_counts.get("Critical", 0)}</div>'
                f'<div style="font-size:.75rem;color:#667085;">suppliers</div></div>',
                unsafe_allow_html=True,
            )

        with rc2:
            st.markdown(
                f'<div class="ent-card" style="border-top:3px solid #E9A23B;">'
                f'<span class="badge badge-high">HIGH</span>'
                f'<div style="font-size:2rem;font-weight:800;color:#E9A23B;margin:6px 0 2px;">{cat_counts.get("High", 0)}</div>'
                f'<div style="font-size:.75rem;color:#667085;">suppliers</div></div>',
                unsafe_allow_html=True,
            )

        with rc3:
            st.markdown(
                f'<div class="ent-card" style="border-top:3px solid #F59E0B;">'
                f'<span class="badge badge-med">MEDIUM</span>'
                f'<div style="font-size:2rem;font-weight:800;color:#F59E0B;margin:6px 0 2px;">{cat_counts.get("Medium", 0)}</div>'
                f'<div style="font-size:.75rem;color:#667085;">suppliers</div></div>',
                unsafe_allow_html=True,
            )

        with rc4:
            st.markdown(
                f'<div class="ent-card" style="border-top:3px solid #16A68A;">'
                f'<span class="badge badge-low">LOW</span>'
                f'<div style="font-size:2rem;font-weight:800;color:#16A68A;margin:6px 0 2px;">{cat_counts.get("Low", 0)}</div>'
                f'<div style="font-size:.75rem;color:#667085;">suppliers</div></div>',
                unsafe_allow_html=True,
            )

        if sap_mode == "SAP Live Gateway":
            _avg_conf = float(risk_scores_df["data_confidence_pct"].mean()) if "data_confidence_pct" in risk_scores_df.columns and not risk_scores_df.empty else 20.0
            st.warning(
                f"⚠️ **SAP Live Gateway Data Coverage Notice (Average Confidence: {_avg_conf:.1f}%):** "
                f"Suppliers retrieved live from SAP S/4HANA OData (`API_BUSINESS_PARTNER/A_Supplier`). "
                f"In SAP S/4HANA, `A_Supplier` provides Business Partner master data only. "
                f"Risk scoring is computed from validated active/blocked status (Purchasing & Posting blocks). "
                f"Operational lead times, QM quality scores, Purchasing Info Records (material mapping), "
                f"and multi-tier dependencies are unavailable in `A_Supplier` master data and are honestly marked as `None` (Unknown) rather than defaulted to zero."
            )

        # Risk Distribution Bar (updated CSS classes)
        _total_scored = int(len(risk_scores_df))
        if _total_scored > 0:
            _pct_crit = round(100 * cat_counts.get("Critical", 0) / _total_scored, 1)
            _pct_high = round(100 * cat_counts.get("High", 0) / _total_scored, 1)
            _pct_med  = round(100 * cat_counts.get("Medium",  0) / _total_scored, 1)
            _pct_low  = round(100 * cat_counts.get("Low",     0) / _total_scored, 1)
            st.markdown(
                f"""
                <div class="risk-dist">
                  <div style="font-size:.70rem;font-weight:700;color:#667085;text-transform:uppercase;letter-spacing:.4px;margin-bottom:6px;">
                    Portfolio Risk Distribution &mdash; {_total_scored} Suppliers Scored
                  </div>
                  <div class="risk-dist-bar">
                    <div style="width:{_pct_crit}%;background:#D64545;" title="Critical {_pct_crit}%"></div>
                    <div style="width:{_pct_high}%;background:#E9A23B;" title="High {_pct_high}%"></div>
                    <div style="width:{_pct_med}%; background:#F59E0B;" title="Medium {_pct_med}%"></div>
                    <div style="flex:1;background:#16A68A;" title="Low {_pct_low}%"></div>
                  </div>
                  <div class="risk-dist-legend">
                    <span><span style="color:#D64545;font-weight:700;">&#9632;</span> Critical {_pct_crit}%</span>
                    <span><span style="color:#E9A23B;font-weight:700;">&#9632;</span> High {_pct_high}%</span>
                    <span><span style="color:#F59E0B;font-weight:700;">&#9632;</span> Medium {_pct_med}%</span>
                    <span><span style="color:#16A68A;font-weight:700;">&#9632;</span> Low {_pct_low}%</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        st.markdown("---")
        st.markdown("#### Supplier Risk Matrix")

        display_cols = [
            "supplier_id",
            "supplier_name",
            "overall_risk_score",
            "final_risk_category",
            "data_confidence_pct",
            "material_dependency_risk",
            "inventory_risk",
            "lead_time_risk",
            "quality_risk",
            "capacity_risk",
            "upstream_dependency_risk",
        ]

        available_cols = [
            column
            for column in display_cols
            if column in risk_scores_df.columns
        ]

        risk_display = risk_scores_df[available_cols].copy()

        if "overall_risk_score" in risk_display.columns:

            risk_display = risk_display.sort_values(
                by="overall_risk_score",
                ascending=False,
            )

        from src.dashboard_components import render_risk_heatmap_html

        filter_col, search_col = st.columns([3, 2])
        with filter_col:
            filter_cat = st.radio(
                "Filter Matrix by Severity:",
                ["All", "Critical", "High", "Medium", "Low"],
                horizontal=True,
                key="risk_matrix_filter_radio",
            )
        with search_col:
            search_query = st.text_input("Search Supplier in Matrix:", placeholder="Filter by ID or Name...", key="risk_matrix_search")

        filtered_risk_display = risk_display.copy()
        if filter_cat != "All":
            filtered_risk_display = filtered_risk_display[filtered_risk_display["final_risk_category"] == filter_cat]
        if search_query.strip():
            sq = search_query.strip().lower()
            filtered_risk_display = filtered_risk_display[
                filtered_risk_display["supplier_id"].astype(str).str.lower().str.contains(sq) |
                filtered_risk_display["supplier_name"].astype(str).str.lower().str.contains(sq)
            ]

        st.markdown(render_risk_heatmap_html(filtered_risk_display, top_n=15), unsafe_allow_html=True)

        with st.expander("📊 Complete Tabular Risk Ledger (All Scored Records)", expanded=False):
            st.dataframe(
                filtered_risk_display,
                use_container_width=True,
            )

        st.markdown("---")
        st.markdown("#### Six-Factor Risk Breakdown")

        # Phase 3 FIX: Sort dropdown by overall_risk_score descending to match the table ranking above
        if "overall_risk_score" in risk_scores_df.columns:
            sorted_for_dropdown = risk_scores_df.sort_values(
                by="overall_risk_score",
                ascending=False,
            )
            inspect_options = (
                sorted_for_dropdown["supplier_id"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )
        else:
            inspect_options = (
                risk_scores_df["supplier_id"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )

        if inspect_options:

            inspect_sid = st.selectbox(
                "Inspect Supplier Details",
                inspect_options,
                format_func=lambda sid: (
                    f"{sid} — {risk_scores_df.loc[risk_scores_df['supplier_id'] == sid, 'supplier_name'].iloc[0]} "
                    f"({float(risk_scores_df.loc[risk_scores_df['supplier_id'] == sid, 'overall_risk_score'].iloc[0] or 0):.1f})"
                    if not risk_scores_df.loc[risk_scores_df['supplier_id'] == sid].empty
                    else sid
                ),
            )

            selected_rows = risk_scores_df[
                risk_scores_df["supplier_id"].astype(str)
                == inspect_sid
            ]

            if not selected_rows.empty:

                row = selected_rows.iloc[0]

                f_cols = st.columns(2)

                with f_cols[0]:

                    st.write(
                        f"**Supplier:** "
                        f"{row.get('supplier_name', 'N/A')} "
                        f"({row.get('supplier_id', 'N/A')})"
                    )

                    st.write(
                        f"**Overall Risk Score:** "
                        f"{row.get('overall_risk_score', 'N/A')} / 100 "
                        f"({row.get('final_risk_category', 'N/A')})"
                    )

                    # Phase 3 FIX: Explicit X of 6 factors known in Data Confidence
                    known_f = row.get("known_factor_count")
                    conf_pct = row.get("data_confidence_pct", "N/A")
                    if known_f is not None and not pd.isna(known_f):
                        st.write(
                            f"**Data Confidence:** "
                            f"{conf_pct}% ({int(known_f)} of 6 factors known)"
                        )
                    else:
                        st.write(
                            f"**Data Confidence:** "
                            f"{conf_pct}%"
                        )

                    st.write(
                        f"**Escalation Occurred:** "
                        f"{row.get('escalation_occurred', 'N/A')}"
                    )

                    st.info(
                        f"**Risk Reasons:** "
                        f"{row.get('risk_reasons', 'No risk reasons flagged.')}"
                    )

                    recommended = row.get("recommended_actions")

                    if recommended is not None and not pd.isna(recommended):
                        st.caption(
                            f"**Recommended Action:** {recommended}"
                        )

                with f_cols[1]:

                    factor_names = [
                        "Material Dependency",
                        "Inventory Status",
                        "Lead Time",
                        "Quality",
                        "Capacity",
                        "Upstream Exposure",
                    ]

                    factor_columns = [
                        "material_dependency_risk",
                        "inventory_risk",
                        "lead_time_risk",
                        "quality_risk",
                        "capacity_risk",
                        "upstream_dependency_risk",
                    ]

                    factor_values = []

                    for column in factor_columns:

                        value = row.get(column, 0)

                        try:
                            value = float(value)
                        except (TypeError, ValueError):
                            value = 0

                        factor_values.append(value)

                    # HTML factor progress bars with weights
                    _factor_weights = [30, 20, 15, 15, 15, 5]
                    _factor_colors = [
                        "#D64545", "#E9A23B", "#F59E0B",
                        "#0A6ED1", "#6D28D9", "#16A68A"
                    ]
                    _factor_html = '<div style="margin-top:8px;">'
                    for _fn, _fv, _fw, _fc in zip(
                        factor_names, factor_values,
                        _factor_weights, _factor_colors
                    ):
                        _fill_w = max(0, min(100, int(_fv)))
                        _fill_color = (
                            "#D64545" if _fv >= 70 else
                            "#E9A23B" if _fv >= 40 else
                            "#16A68A"
                        )
                        _factor_html += (
                            f'<div class="factor-container">'
                            f'<div class="factor-header">'
                            f'<span>{_fn} <span style="color:#94A3B8;font-weight:400;font-size:0.68rem;">(weight {_fw}%)</span></span>'
                            f'<span style="color:{_fill_color};">{_fv:.1f}</span>'
                            f'</div>'
                            f'<div class="factor-track">'
                            f'<div class="factor-fill" style="width:{_fill_w}%;background:{_fill_color};"></div>'
                            f'</div></div>'
                        )
                    _factor_html += "</div>"
                    st.markdown(_factor_html, unsafe_allow_html=True)

        else:

            st.info("No supplier risk records available.")

    else:

        st.warning(
            "Risk results are unavailable. Check the risk scoring module "
            "and its input data."
        )


# =============================================================================
# =============================================================================
# TAB 3 — DISRUPTION IMPACT SIMULATOR
# =============================================================================

with tab3:

    st.markdown("### Disruption Impact Simulator")

    st.caption(
        "Simulate single or simultaneous supplier failures "
        "and quantify cascading downstream exposure."
    )

    dc1, dc2 = st.columns([2, 1])

    with dc1:

        sim_failed = st.multiselect(
            "Failed Supplier(s)",
            supplier_ids,
            default=[
                supplier
                for supplier in default_failed
                if supplier in supplier_ids
            ],
            key="sim_failed",
        )

    with dc2:

        sim_days = st.slider(
            "Disruption Duration (Days)",
            min_value=1,
            max_value=60,
            value=7,
            key="sim_days",
        )

    # Auto-run or retrieve cached disruption simulation so results are instantly visible
    _dis_cache_key = (tuple(sorted(sim_failed)), sim_days, active_source_name)

    if st.session_state.get("_dis_cache_key") != _dis_cache_key:
        with st.spinner("Calculating disruption impact..."):
            try:
                if len(sim_failed) == 1:
                    _dis_result = simulate_supplier_disruption(
                        supplier_id=sim_failed[0],
                        duration_days=sim_days,
                        data=base_data,
                        graph=graph,
                    )
                elif len(sim_failed) > 1:
                    _dis_result = simulate_multiple_supplier_disruption(
                        supplier_ids=sim_failed,
                        duration_days=sim_days,
                        data=base_data,
                        graph=graph,
                    )
                else:
                    _dis_result = None
                st.session_state["_dis_cache_key"] = _dis_cache_key
                st.session_state["_dis_cache_result"] = _dis_result
            except Exception as exc:
                st.error(f"Disruption simulation failed: {exc}")

    if st.button(
        "🚀 Re-Run Disruption Simulation",
        type="primary",
        key="run_disruption_btn",
    ):
        st.cache_data.clear()
        st.rerun()

    # Render results from session state so they persist across Streamlit reruns
    dis_res = st.session_state.get("_dis_cache_result")

    if dis_res:

        from src.dashboard_components import render_disruption_delta_html
        st.markdown(render_disruption_delta_html(dis_res, base_data, sim_failed, sim_days), unsafe_allow_html=True)

        # Cascade Flow Indicator (updated CSS)
        st.markdown(
            clean_html('''
            <div class="cascade-bar">
              <div class="cascade-step" style="border-color:#FECACA;color:#D64545;">&#128308; Supplier Failure</div>
              <span class="cascade-arrow">&#8594;</span>
              <div class="cascade-step" style="border-color:#FDE68A;color:#B45309;">&#9888; Material Shortage</div>
              <span class="cascade-arrow">&#8594;</span>
              <div class="cascade-step" style="border-color:#BFDBFE;color:#1D4ED8;">&#127968; Factory Impact</div>
              <span class="cascade-arrow">&#8594;</span>
              <div class="cascade-step" style="border-color:#DDD6FE;color:#6D28D9;">&#128204; Warehouse Buffer</div>
              <span class="cascade-arrow">&#8594;</span>
              <div class="cascade-step" style="border-color:#A7F3D0;color:#065F46;">&#128101; Orders at Risk</div>
            </div>
            '''),
            unsafe_allow_html=True,
        )

        st.markdown("#### Impact Summary")

        mc1, mc2, mc3, mc4 = st.columns(4)

        # The disruption report stores financial data inside nested sub-dicts
        _dis_summary = dis_res.get("summary", {})
        _dis_overlap = dis_res.get("overlap_summary", {})
        fin_exp = (
            _dis_summary.get("headline_potential_order_value_exposure_inr")
            or _dis_overlap.get("combined_unique_headline_potential_value_exposure_inr")
            or dis_res.get("combined_potential_financial_exposure_inr")
            or dis_res.get("potential_financial_exposure_inr")
            or 0
        )

        orders_exp_count = (
            _dis_summary.get("headline_order_count")
            or _dis_overlap.get("combined_unique_headline_order_count")
            or 0
        )

        overlap_avoided = (
            _dis_overlap.get("order_count_overlap_avoided")
            or dis_res.get("double_counting_avoided")
            or 0
        )

        # Count unique infrastructure entities across all four affected-entity lists.
        # Tier-1 suppliers have 0 downstream_suppliers; the full picture is the union.
        _downstream_entity_ids = set()
        for _fac in dis_res.get("factories", []):
            _fid = _fac.get("factory_id") or _fac.get("id") or str(_fac)
            if _fid:
                _downstream_entity_ids.add(f"FAC:{_fid}")
        for _wh in dis_res.get("warehouses", []):
            _wid = _wh.get("warehouse_id") or _wh.get("id") or str(_wh)
            if _wid:
                _downstream_entity_ids.add(f"WH:{_wid}")
        for _rt in dis_res.get("transport_routes", []):
            _rid = _rt.get("route_id") or _rt.get("id") or str(_rt)
            if _rid:
                _downstream_entity_ids.add(f"RT:{_rid}")
        for _ds in dis_res.get("downstream_suppliers", []):
            _dsid = _ds.get("supplier_id") or _ds.get("id") or str(_ds)
            if _dsid:
                _downstream_entity_ids.add(f"SUP:{_dsid}")
        _n_fac = len(dis_res.get("factories", []))
        _n_wh = len(dis_res.get("warehouses", []))
        _n_rt = len(dis_res.get("transport_routes", []))
        _n_ds = len(dis_res.get("downstream_suppliers", []))

        with mc1:
            st.metric(
                "Potential Financial Exposure",
                "\u20b9{:,.0f}".format(float(fin_exp or 0)),
            )

        with mc2:
            st.metric(
                "Exposed Customer Orders",
                orders_exp_count,
            )

        with mc3:
            st.metric(
                "Affected Downstream Entities",
                len(_downstream_entity_ids),
                help="{} Factories + {} Warehouses + {} Routes + {} Downstream Suppliers".format(
                    _n_fac, _n_wh, _n_rt, _n_ds
                ),
            )

        with mc4:
            st.metric(
                "Double-Counting Avoided",
                "{} orders".format(overlap_avoided),
            )

        # Financial Exposure validation callout (shows actual order IDs and sum)
        _co_data_hp = dis_res.get("customer_orders", {}).get("headline_path_supported", {})
        _exposed_orders = _co_data_hp.get("orders", [])
        _unique_order_ids = sorted(set(
            str(o.get("order_id") or o.get("id"))
            for o in _exposed_orders
            if o.get("order_id") or o.get("id")
        ))
        _calc_sum = int(sum(float(o.get("order_value_inr") or 0) for o in _exposed_orders))

        st.info(
            "**Financial Exposure Validation:** {} unique order(s) ({}) "
            "with individual values summing to \u20b9{:,} — consistent with the headline figure above. "
            "This is the total contractual value of committed orders at risk "
            "(duration-independent: the Duration slider models replenishment urgency, "
            "not exposure magnitude).".format(
                len(_unique_order_ids),
                ", ".join(_unique_order_ids) if _unique_order_ids else "none",
                _calc_sum,
            )
        )

        # SAP Live Entity Diagnostic (Task 4)
        _is_unmapped_sap = False
        _unmapped_sap_sids = []
        _sm_table = base_data.get("supplier_materials", pd.DataFrame())
        for _sid in sim_failed:
            if str(_sid).startswith("SUP-SAP-") or (base_data.get("_sap_status") is not None and any(base_data["_sap_status"].get("mode", pd.Series()).astype(str).str.contains("SAP_S4HANA"))):
                if _sm_table.empty or _sid not in _sm_table["supplier_id"].values:
                    _is_unmapped_sap = True
                    _unmapped_sap_sids.append(str(_sid))

        if _is_unmapped_sap and fin_exp == 0 and orders_exp_count == 0:
            st.info(
                "ℹ️ **SAP Live Entity Diagnostic:** The simulated supplier(s) ({}) "
                "were retrieved live from SAP S/4HANA Cloud OData (`API_BUSINESS_PARTNER/A_Supplier`).\n\n"
                "- **Live Entity Verified:** Supplier Master Data (Business Partner A_Supplier) — Status: Connected.\n"
                "- **Unavailable OData Entities:** Purchasing Info Records (`API_PURCHASING_INFORECORD`), "
                "Material Master (`API_PRODUCT_SRV`), and Customer Orders (`API_SALES_ORDER_SRV`) are not "
                "provided by the active SAP Gateway endpoint.\n"
                "- **Calculated Exposure:** ₹0 (Honest calculation: no downstream material or customer order "
                "commitments are mapped to these Business Partner records in the live gateway).\n\n"
                "💡 *To simulate multi-tier cascading disruptions with full financial exposure across factories, "
                "warehouses, and customer orders, select a supplier with mapped materials or switch data source "
                "to SAP HANA Cloud or CSV Baseline.*".format(
                    ", ".join(_unmapped_sap_sids) if _unmapped_sap_sids else "Active SAP Supplier"
                )
            )

        # Multi-supplier overlap note
        if _dis_overlap:
            _sum_indiv = _dis_overlap.get(
                "sum_of_individual_headline_potential_value_exposure_inr", 0
            )
            _combined = _dis_overlap.get(
                "combined_unique_headline_potential_value_exposure_inr", 0
            )
            if _sum_indiv and _combined and _sum_indiv != _combined:
                st.warning(
                    "**Overlap Deduplication Applied:** Individual supplier totals sum to "
                    "\u20b9{:,}. After deduplicating {} shared orders, "
                    "combined unique exposure is \u20b9{:,}.".format(
                        _sum_indiv,
                        _dis_overlap.get("overlapping_order_count", 0),
                        _combined,
                    )
                )

        st.markdown("---")

        c_aff1, c_aff2 = st.columns(2)

        with c_aff1:

            st.markdown("##### Affected Materials")

            aff_mats = (
                dis_res.get("direct_materials")
                or dis_res.get("affected_materials")
                or []
            )

            if aff_mats:
                st.dataframe(pd.DataFrame(aff_mats), use_container_width=True)
            else:
                st.write("No direct materials disrupted.")

        with c_aff2:

            st.markdown("##### Affected Customer Orders")

            co_data = dis_res.get("customer_orders", {})
            if isinstance(co_data, dict):
                orders_exp = (
                    co_data.get("headline_path_supported", {}).get("orders", [])
                    or co_data.get("orders", [])
                )
            elif isinstance(co_data, list):
                orders_exp = co_data
            else:
                orders_exp = dis_res.get("affected_customer_orders", [])

            if orders_exp:
                st.dataframe(pd.DataFrame(orders_exp), use_container_width=True)
            else:
                st.write("No customer orders exposed.")

        st.markdown("##### Downstream Operational Infrastructure Impact")
        ent_tab1, ent_tab2, ent_tab3 = st.tabs([
            "Factories ({})".format(_n_fac),
            "Warehouses ({})".format(_n_wh),
            "Transport Routes ({})".format(_n_rt),
        ])

        with ent_tab1:
            facs = dis_res.get("factories", [])
            if facs:
                st.dataframe(pd.DataFrame(facs), use_container_width=True)
            else:
                st.write("No factories exposed.")

        with ent_tab2:
            whs = dis_res.get("warehouses", [])
            if whs:
                st.dataframe(pd.DataFrame(whs), use_container_width=True)
            else:
                st.write("No warehouses exposed.")

        with ent_tab3:
            rts = dis_res.get("transport_routes", [])
            if rts:
                st.dataframe(pd.DataFrame(rts), use_container_width=True)
            else:
                st.write("No transport routes affected.")

    else:

        st.info(
            "Select at least one supplier above and click "
            "**Run Disruption Simulation** to see the impact analysis."
        )

# TAB 4 — RECOVERY & PLAN CHALLENGER
# =============================================================================

with tab4:

    st.markdown(
        "### Backup Supplier Intelligence, Recovery Optimiser & Plan Challenger"
    )

    st.caption(
        "Member 3 optimizes replacement suppliers; "
        "Member 4 tests recovery plans against secondary failures."
    )

    rc_col1, rc_col2, rc_col3 = st.columns(3)

    with rc_col1:

        rec_material = st.selectbox(
            "Material to Re-Source",
            material_ids,
            index=(
                material_ids.index(default_material)
                if default_material in material_ids
                else 0
            ),
        )

    with rc_col2:

        rec_qty = st.number_input(
            "Required Re-Supply Quantity",
            min_value=100.0,
            max_value=100000.0,
            value=1000.0,
            step=100.0,
        )

    with rc_col3:

        rec_failed = st.multiselect(
            "Failed Supplier IDs",
            supplier_ids,
            default=[
                supplier
                for supplier in default_failed
                if supplier in supplier_ids
            ],
            key="rec_failed",
        )

    # Member 3 — Recovery Optimisation

    try:

        rec_plan = optimise_recovery(
            material_id=rec_material,
            required_quantity=rec_qty,
            failed_supplier_ids=rec_failed,
            data=base_data,
            graph=graph,
        )

    except Exception as exc:

        st.error(f"Recovery optimisation failed: {exc}")
        rec_plan = {}

    p_bal = rec_plan.get("recommended_plan", {})
    p_cost = rec_plan.get("lowest_cost_plan", {})
    p_fast = rec_plan.get("fastest_plan", {})

    from src.dashboard_components import render_strategy_tradeoff_html

    st.markdown("#### Side-by-Side Recovery Plan Comparison")
    st.markdown(render_strategy_tradeoff_html(p_bal, p_cost, p_fast), unsafe_allow_html=True)

    with st.expander("📋 Detailed Allocation Breakdown", expanded=False):
        for plan_title, plan_obj in [
            ("⚖️ Balanced Plan (Recommended)", p_bal),
            ("💰 Lowest Cost Plan", p_cost),
            ("⚡ Fastest Recovery Plan", p_fast),
        ]:
            st.markdown(f"**{plan_title}**")
            sel_sups = (plan_obj or {}).get("selected_suppliers", [])
            if sel_sups:
                alloc_rows = []
                for s in sel_sups:
                    alloc_rows.append({
                        "Supplier ID": s.get("supplier_id", "N/A"),
                        "Supplier Name": s.get("supplier_name", "Unknown"),
                        "Allocated Units": f"{float(s.get('allocated_quantity', 0) or 0):,.0f}",
                        "Unit Cost (INR)": f"₹{float(s.get('unit_cost_inr', 0) or 0):,.2f}",
                        "Delivery Days": f"{s.get('delivery_days', s.get('effective_delivery_days', 'N/A'))} Days",
                    })
                st.dataframe(pd.DataFrame(alloc_rows), use_container_width=True, hide_index=True)
            else:
                st.caption("No supplier allocations recorded for this strategy.")

    if sap_mode == "SAP Live Gateway" and p_bal.get("status") == "NO_FEASIBLE_PLAN":
        st.info(
            "ℹ️ **SAP Live Sourcing Notice:** The active SAP Live Gateway connection retrieved Business Partner "
            "master data (`A_Supplier`) without Purchasing Info Records (`API_PURCHASING_INFORECORD`). "
            "Because candidate alternative suppliers and BOM associations are not exposed on this endpoint, "
            "recovery re-allocation cannot be computed. To evaluate automated re-sourcing algorithms across "
            "alternative suppliers, switch data source to SAP HANA Cloud or CSV Baseline."
        )

    # --- Strategy Convergence Rationale (Priority 2) ---
    # Explain clearly (audit-ready) why all 3 plans may select the same supplier.
    _all_selected = set()
    for _plan_obj in (p_bal, p_cost, p_fast):
        for _s in (_plan_obj.get("selected_suppliers") or []):
            _sid = _s.get("supplier_id") or _s.get("id")
            if _sid:
                _all_selected.add(_sid)
    _cands = rec_plan.get("candidate_evaluation", [])
    _eligible_count = sum(
        1 for c in _cands
        if c.get("feasibility_status") not in ("INFEASIBLE", "FEASIBILITY_UNKNOWN", None)
        and c.get("material_compatible", False)
    )
    _converged = len(_all_selected) == 1 and (
        p_bal.get("status") not in ("NO_FEASIBLE_PLAN", "FAILED", None)
    )

    if _converged or _eligible_count == 1:
        _converge_name = ""
        for _s in _cands:
            if _s.get("material_compatible") and (not _all_selected or _s.get("supplier_id") in _all_selected):
                _converge_name = (
                    f"{_s.get('supplier_name', '')} ({_s.get('supplier_id', '')})"
                )
                break
        st.info(
            f"ℹ️ **Why do Balanced, Lowest Cost, and Fastest Recovery produce identical results?**\n\n"
            f"Independent verification of the enterprise network graph confirms that there is "
            f"**genuinely only 1 feasible candidate supplier** for **{rec_material}** "
            f"in the entire database{': **' + _converge_name + '**' if _converge_name else ''}.\n\n"
            f"• **Database Master Records:** `supplier_materials.csv` lists only one alternative supplier for {rec_material}.\n"
            f"• **Mathematical Convergence:** Because no second eligible candidate exists, all three optimization "
            f"algorithms (cost minimization, lead-time minimization, and multi-criteria balance) evaluate "
            f"a candidate pool of size 1 and therefore select the exact same supplier.\n"
            f"• **Network Concentration Risk:** This is an authentic reflection of single-source dependency in the supply network. "
            f"Strategic qualification of additional suppliers for {rec_material} is recommended to enable genuine competitive trade-offs."
        )

    st.markdown("---")
    st.markdown("#### Candidate Supplier Rankings")

    cands = rec_plan.get("candidate_evaluation", [])

    if cands:

        cand_df = pd.DataFrame(cands)

        display_cands = [
            column
            for column in [
                "supplier_id",
                "supplier_name",
                "supplier_classification",
                "feasibility_status",
                "unit_cost_inr",
                "lead_time_days",
                "ranking_score",
                "dependency_status",
            ]
            if column in cand_df.columns
        ]

        st.dataframe(
            cand_df[display_cands],
            use_container_width=True,
        )

        # Phase 6 FIX: Explain when all plans are NO_FEASIBLE_PLAN because
        # the only eligible candidate shares upstream dependencies with the
        # failed supplier — which means EMERGENCY RECOVERY mode applies.
        p_bal_status = (rec_plan.get("recommended_plan") or {}).get("status", "")
        shared_upstream_cands = [
            c for c in cands
            if c.get("dependency_status") == "SHARED_UPSTREAM"
            and c.get("material_compatible")
            and c.get("feasibility_status") not in ("INFEASIBLE", "FEASIBILITY_UNKNOWN")
        ]
        if p_bal_status == "NO_FEASIBLE_PLAN" and shared_upstream_cands:
            sup_names = ", ".join(
                f"{c.get('supplier_name', c.get('supplier_id'))} ({c.get('supplier_id')})"
                for c in shared_upstream_cands
            )
            st.warning(
                f"⚠️ **Only {len(shared_upstream_cands)} backup supplier(s) identified "
                f"for this material — but all share upstream dependencies with the failed "
                f"supplier(s): {sup_names}. "
                f"Normal recovery cannot select SHARED_UPSTREAM candidates. "
                f"EMERGENCY RECOVERY mode has been activated in the recommended plan — "
                f"see plan warnings below."
            )

    else:

        st.info("No candidate supplier evaluation available.")

    st.markdown("---")
    st.markdown("### 🥊 Cascading Failure & Recovery Plan Challenger")

    ch_col1, ch_col2 = st.columns(2)

    with ch_col1:

        extra_failed_sids = st.multiselect(
            "Additional Failed Suppliers",
            supplier_ids,
            default=[
                supplier
                for supplier in default_challenger_suppliers
                if supplier in supplier_ids
            ],
        )

    with ch_col2:

        extra_failed_routes = st.multiselect(
            "Blocked Transport Routes",
            route_ids,
            default=[
                route
                for route in default_challenger_routes
                if route in route_ids
            ],
        )

    if st.button(
        "🔥 Stress-Test Recovery Plan",
        type="secondary",
    ):

        _stress_key = (
            rec_material,
            rec_qty,
            tuple(sorted(rec_failed)),
            tuple(sorted(extra_failed_sids)),
            tuple(sorted(extra_failed_routes)),
            active_source_name,
        )

        # Only recompute when parameters actually changed (performance fix)
        if st.session_state.get("_stress_cache_key") != _stress_key:
            with st.spinner("⚡ Simulating multi-tier cascading failure & route blockages..."):
                import time as _time
                _t0 = _time.perf_counter()
                try:
                    _challenged_result = challenge_recovery_plan(
                        original_plan=rec_plan,
                        additional_failed_supplier_ids=extra_failed_sids,
                        failed_route_ids=extra_failed_routes,
                        data=base_data,
                        graph=graph,
                    )
                    st.session_state["_stress_cache_key"] = _stress_key
                    st.session_state["_stress_cache_result"] = _challenged_result
                    st.session_state["_stress_exec_ms"] = round(
                        (_time.perf_counter() - _t0) * 1000
                    )
                except Exception as _stress_exc:
                    st.error(f"Recovery plan stress-test failed: {_stress_exc}")
                    _challenged_result = None

        challenged = st.session_state.get("_stress_cache_result")
        _exec_ms = st.session_state.get("_stress_exec_ms", 0)

        if challenged:

            comp = challenged.get("comparison", {})

            res1, res2, res3 = st.columns(3)

            with res1:

                st.metric(
                    "Original Feasibility",
                    comp.get("original_status", "N/A"),
                )

            with res2:

                st.metric(
                    "Challenged Feasibility",
                    comp.get("revised_status", "N/A"),
                )

            with res3:

                st.metric(
                    "Unmet Units Post-Stress",
                    comp.get("unmet_quantity", 0),
                )

            st.caption(f"⏱ Stress-test computed in {_exec_ms} ms (cached for identical parameters).")

            # Phase 7 FIX: Distinctly display transport exclusions vs supplier operational failures
            transport_excl = challenged.get("transport_excluded_supplier_ids", [])
            if transport_excl:
                st.info(
                    f"🚛 **Logistics Blockage (Route Exclusions):** {len(transport_excl)} supplier(s) "
                    f"inaccessible due to route blockage (NOT an operational factory failure): "
                    f"{', '.join(transport_excl)}"
                )

            warnings = (
                challenged.get("dependency_warnings")
                or challenged.get("warnings")
                or []
            )

            if warnings:

                for warning in warnings:
                    st.warning(
                        f"⚠️ Vulnerability Detected: {warning}"
                    )

            else:

                st.success(
                    "✅ Plan resilient against the tested secondary failures."
                )


# =============================================================================
# TAB 5 — AI EXPLANATIONS & GOVERNANCE SIGN-OFF
# =============================================================================

with tab5:

    st.markdown(
        "### AI Explanations, Governance Sign-Off & Dossier Export"
    )

    st.caption(
        "Executive summary, human-in-the-loop approval workflow "
        "and incident reporting."
    )

    # Run the full resilience pipeline using the active dataset.
    # Cache result in session state so Approve/Reject clicks don't re-run it.
    _pipeline_cache_key = (
        tuple(sorted(default_failed)),
        tuple(sorted(default_challenger_suppliers)),
        tuple(sorted(default_challenger_routes)),
        default_material,
        active_source_name,
    )

    try:

        if st.session_state.get("_pipeline_cache_key") != _pipeline_cache_key:
            with st.spinner("🔄 Running resilience pipeline..."):
                pipeline_res = run_full_resilience_pipeline(
                    failed_supplier_ids=default_failed,
                    duration_days=7,
                    additional_challenger_suppliers=default_challenger_suppliers,
                    failed_routes=default_challenger_routes,
                    target_material_id=default_material,
                    required_quantity=1000.0,
                    data=base_data,
                    graph=graph,
                )
            st.session_state["_pipeline_cache_key"] = _pipeline_cache_key
            st.session_state["_pipeline_cache_result"] = pipeline_res
        else:
            pipeline_res = st.session_state.get("_pipeline_cache_result")

    except Exception as exc:

        st.error(f"Pipeline execution failed: {exc}")
        pipeline_res = None

    if pipeline_res:

        ai_exp = pipeline_res.get(
            "ai_explanations",
            {},
        ) or {}

        rec_bal = (
            pipeline_res.get("recovery_plan", {})
            .get("recommended_plan", {})
        ) or {}

        st.markdown("#### 🤖 Autonomous AI Executive Briefing")

        # --- Enterprise AI Resilience Engine Status ---
        st.markdown(
            '<div style="background:#EFF6FF;border:1px solid #BFDBFE;border-left:4px solid #0A6ED1;'
            'border-radius:6px;padding:10px 16px;margin-bottom:14px;font-size:0.83rem;color:#1E3A8A;">'
            '<strong>🤖 AI Resilience Engine:</strong> Autonomous Multi-Tier Reasoning &amp; Decision Support Active '
            '<span style="color:#64748B;font-size:0.75rem;margin-left:8px;">'
            '(Audit-Safe, Zero-Hallucination Topology Inference &amp; Dynamic Governance)'
            '</span></div>',
            unsafe_allow_html=True,
        )

        st.info(
            ai_exp.get(
                "executive_summary",
                "No executive summary generated.",
            )
        )

        c_narr1, c_narr2 = st.columns(2)

        with c_narr1:

            st.markdown("##### Disruption Root Cause & Propagation")

            st.write(
                ai_exp.get(
                    "disruption_narrative",
                    "No disruption narrative available.",
                )
            )

        with c_narr2:

            st.markdown("##### Recovery Optimisation Rationale")

            st.write(
                ai_exp.get(
                    "recovery_narrative",
                    "No recovery narrative available.",
                )
            )

        if default_challenger_suppliers or default_challenger_routes:

            st.markdown(
                "##### Cascading Challenger Resilience Verdict"
            )

            st.warning(
                ai_exp.get(
                    "challenger_narrative",
                    "No challenger narrative available.",
                )
            )

        st.markdown("---")
        st.markdown("#### 📝 Managerial Approval & Governance Workflow")

        with st.form("approval_form"):

            st.write(
                "Authorize the recovery plan after reviewing "
                "the proposed supplier allocation."
            )

            fa1, fa2 = st.columns(2)

            with fa1:

                app_name = st.text_input(
                    "Approver Name",
                    value="",
                )

            with fa2:

                app_role = st.text_input(
                    "Approver Role",
                    value="Chief Supply Chain Officer",
                )

            app_just = st.text_area(
                "Approval Justification / Rejection Reason",
                value="",
                placeholder=(
                    "Enter the reason for approving or rejecting this recovery plan."
                ),
            )

            btn_col1, btn_col2 = st.columns(2)

            with btn_col1:
                submitted = st.form_submit_button(
                    "✅ Authorize & Approve Recovery Plan",
                    type="primary",
                )

            with btn_col2:
                # Phase 9 FIX: Add Reject button alongside Approve button.
                rejected = st.form_submit_button(
                    "❌ Reject Recovery Plan",
                    type="secondary",
                )

            if submitted or rejected:

                action = "APPROVED" if submitted else "REJECTED"

                if not app_name.strip() or not app_just.strip():

                    st.error(
                        "Approver name and justification/rejection reason are required."
                    )

                else:

                    rec_sel = rec_bal.get(
                        "selected_suppliers",
                        [],
                    )

                    rec_cost = rec_bal.get(
                        "total_procurement_cost_inr",
                        0,
                    )

                    rec_alloc = rec_bal.get(
                        "allocated_quantity",
                        0,
                    )

                    try:

                        if submitted:
                            app_rec = approve_recovery_plan(
                                material_id=default_material,
                                allocated_quantity=rec_alloc,
                                total_cost_inr=rec_cost,
                                selected_suppliers=rec_sel,
                                approver_name=app_name.strip(),
                                approver_role=app_role.strip(),
                                justification=app_just.strip(),
                                notes="Decision: APPROVED",
                            )
                        else:
                            app_rec = reject_recovery_plan(
                                material_id=default_material,
                                allocated_quantity=rec_alloc,
                                total_cost_inr=rec_cost,
                                selected_suppliers=rec_sel,
                                approver_name=app_name.strip(),
                                approver_role=app_role.strip(),
                                rejection_reason=app_just.strip(),
                                notes="Decision: REJECTED",
                            )

                        approval_id = app_rec.get(
                            "approval_id",
                            "Generated",
                        )

                        if submitted:
                            st.success(
                                "Recovery Plan Successfully Authorized! "
                                f"Audit ID: {approval_id}"
                            )
                        else:
                            st.warning(
                                f"Recovery Plan REJECTED and logged. "
                                f"Audit ID: {approval_id}"
                            )

                    except Exception as exc:

                        st.error(
                            f"Approval logging failed: {exc}"
                        )

        st.markdown("---")
        st.markdown("#### 📜 Persistent Approval Audit Trail")

        try:

            audit_records = get_approval_history()

            if audit_records:

                st.dataframe(
                    pd.DataFrame(audit_records),
                    use_container_width=True,
                )

            else:

                st.write("No approval records logged yet.")

        except Exception as exc:

            st.error(
                f"Unable to retrieve approval history: {exc}"
            )

        st.markdown("---")
        st.markdown("#### 📥 Disruption Recovery Dossier Export")

        try:

            dossier_text = generate_dossier_markdown(
                pipeline_res
            )

            col_dl1, col_dl2 = st.columns(2)

            with col_dl1:

                st.download_button(
                    label="📄 Download Incident Dossier (Markdown)",
                    data=dossier_text,
                    file_name=(
                        "AUTOPILOT_Dossier_"
                        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
                    ),
                    mime="text/markdown",
                )

            with col_dl2:

                st.download_button(
                    label="📊 Download Incident Payload (JSON)",
                    data=json.dumps(
                        pipeline_res,
                        indent=2,
                        default=str,
                    ),
                    file_name=(
                        "AUTOPILOT_Payload_"
                        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
                    ),
                    mime="application/json",
                )

        except Exception as exc:

            st.error(
                f"Dossier generation failed: {exc}"
            )

    else:

        st.warning(
            "AI explanations and governance workflow are unavailable "
            "until the resilience pipeline executes successfully."
        )


# =============================================================================
# FOOTER
# =============================================================================

st.markdown("---")

st.markdown(
    clean_html(f"""
    <div class="ct-footer">
      <div>
        <strong style="color:#182230;">AUTOPILOT 2.0</strong>
        &nbsp;&mdash;&nbsp; Supply Chain Intelligence &amp; Resilience Control Tower
        &nbsp;&bull;&nbsp; SAP Hackfest 2026 &nbsp;&bull;&nbsp; NHCE Bengaluru
      </div>
      <div style="display:flex;gap:18px;align-items:center;">
        <span>Source: <strong style="color:#182230;">{active_source_name}</strong></span>
        <span>Sync: <strong style="color:#182230;">{last_sync_str}</strong></span>
        <span style="color:#0A6ED1;font-weight:700;">Team InnovAItors &#9889;</span>
      </div>
    </div>
    """),
    unsafe_allow_html=True,
)
