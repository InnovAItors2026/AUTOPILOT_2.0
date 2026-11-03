"""
pipeline.py
-----------
Unified Resilience & Recovery Integration Engine for AUTOPILOT 2.0 (Member 5).

Chains together the work of all team members:
- Member 1: Data Management & NetworkX Digital Twin
- Member 2: Supplier Risk Scoring & Disruption Simulation
- Member 3: Backup Supplier Intelligence & Recovery Optimisation
- Member 4: Cascading Failure Simulation & Recovery Challenger
- Member 5: AI Explanation Engine, Governance Approval, and Dossier Export

All inputs and intermediate results are validated and JSON-serialisable.
"""

from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.data_loader import load_all_data
from src.supply_chain_graph import SupplyChainGraph, get_supply_chain_graph
from src.supplier_risk import build_supplier_risk_factors
from src.risk_scoring import calculate_supplier_risk_scores
from src.disruption_simulation import simulate_supplier_disruption
from src.multi_disruption_simulation import simulate_multiple_supplier_disruption
from src.recovery_optimisation import (
    optimise_recovery,
    optimise_from_disruption_report,
)
from src.cascading_failure import challenge_recovery_plan

AUDIT_LOG_FILE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "approval_audit_log.json")
)


def run_full_resilience_pipeline(
    failed_supplier_ids: Optional[List[str]] = None,
    duration_days: int = 7,
    additional_challenger_suppliers: Optional[List[str]] = None,
    failed_routes: Optional[List[str]] = None,
    target_material_id: Optional[str] = None,
    required_quantity: Optional[float] = None,
    data: Optional[Dict[str, pd.DataFrame]] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Run the end-to-end AUTOPILOT 2.0 resilience workflow.

    Returns a comprehensive result dictionary with:
      - 'data_status': information on active data source (SAP vs CSV)
      - 'network_summary': twin node/edge counts
      - 'risk_scores': DataFrame of evaluated supplier risk scores
      - 'disruption_report': output from Member 2 simulation
      - 'recovery_plan': output from Member 3 optimiser
      - 'challenger_result': output from Member 4 recovery stress-test
      - 'ai_explanations': structured executive & technical briefings
    """
    if failed_supplier_ids is None:
        failed_supplier_ids = ["SUP-T1-03"]
    if additional_challenger_suppliers is None:
        additional_challenger_suppliers = []
    if failed_routes is None:
        failed_routes = []

    # 1. Load data
    if data is None:
        data = load_all_data(verbose=False)

    data_mode = "CSV Baseline"
    if "_sap_status" in data and not data["_sap_status"].empty:
        r0 = data["_sap_status"].iloc[0]
        data_mode = str(r0.get("active_source") or r0.get("mode") or "CSV Baseline")

    # 2. Build or obtain Supply Chain Digital Twin
    if graph is None:
        graph = get_supply_chain_graph(data)

    node_types = {}
    for node_id in graph.nodes:
        nt = graph.nodes[node_id].get("node_type", "unknown")
        node_types[nt] = node_types.get(nt, 0) + 1

    network_summary = {
        "total_nodes": graph.number_of_nodes(),
        "total_edges": graph.number_of_edges(),
        "node_counts": node_types,
        "data_mode": data_mode,
    }

    # 3. Calculate Supplier Risk Scores (Member 2)
    risk_factors = build_supplier_risk_factors(data=data, graph=graph)
    risk_scores_df = calculate_supplier_risk_scores(risk_factors)

    # 4. Run Disruption Impact Analysis (Member 2)
    valid_failed = [s for s in failed_supplier_ids if s in graph]
    if len(valid_failed) == 1:
        disruption_report = simulate_supplier_disruption(
            supplier_id=valid_failed[0],
            duration_days=duration_days,
            data=data,
            graph=graph,
        )
    elif len(valid_failed) > 1:
        disruption_report = simulate_multiple_supplier_disruption(
            supplier_ids=valid_failed,
            duration_days=duration_days,
            data=data,
            graph=graph,
        )
    else:
        disruption_report = {
            "status": "NO_VALID_SUPPLIERS",
            "failed_suppliers": failed_supplier_ids,
            "affected_materials": [],
            "affected_customer_orders": [],
            "combined_potential_financial_exposure_inr": 0,
        }

    # 5. Determine material and quantity to re-source (Member 3)
    affected_materials = disruption_report.get("affected_materials", [])
    if not target_material_id:
        if affected_materials:
            first_mat = affected_materials[0]
            target_material_id = (
                first_mat.get("material_id")
                if isinstance(first_mat, dict)
                else str(first_mat)
            )
        else:
            target_material_id = "MAT-02"

    if required_quantity is None or required_quantity <= 0:
        required_quantity = 1000.0

    # Execute Member 3 Recovery Optimisation
    recovery_plan = optimise_recovery(
        material_id=target_material_id,
        required_quantity=required_quantity,
        failed_supplier_ids=valid_failed,
        data=data,
        graph=graph,
    )

    # 6. Execute Member 4 Cascading Challenger
    challenger_result = None
    if additional_challenger_suppliers or failed_routes:
        challenger_result = challenge_recovery_plan(
            original_plan=recovery_plan,
            additional_failed_supplier_ids=additional_challenger_suppliers,
            failed_route_ids=failed_routes,
            data=data,
            graph=graph,
        )

    # 7. Generate AI Explanations
    ai_explanations = generate_ai_explanations(
        disruption_report=disruption_report,
        recovery_plan=recovery_plan,
        challenger_result=challenger_result,
        risk_scores_df=risk_scores_df,
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "network_summary": network_summary,
        "failed_suppliers": valid_failed,
        "duration_days": duration_days,
        "risk_scores_df": risk_scores_df,
        "disruption_report": disruption_report,
        "recovery_plan": recovery_plan,
        "challenger_result": challenger_result,
        "ai_explanations": ai_explanations,
    }


def generate_ai_explanations(
    disruption_report: Dict[str, Any],
    recovery_plan: Dict[str, Any],
    challenger_result: Optional[Dict[str, Any]],
    risk_scores_df: pd.DataFrame,
) -> Dict[str, str]:
    """
    Construct clear, executive-grade AI explanations from real module metrics.
    """
    failed_sids = disruption_report.get("failed_suppliers", [])
    if not failed_sids and "failed_supplier" in disruption_report:
        single_s = disruption_report["failed_supplier"]
        if isinstance(single_s, dict):
            failed_sids = [single_s.get("supplier_id")]
        else:
            failed_sids = [str(single_s)]

    failed_names = []
    for sid in failed_sids:
        # BUG-02 FIX: failed_sids from multi-disruption contains dicts, not strings.
        # Extract supplier_id string before using it in a pandas Series comparison.
        if isinstance(sid, dict):
            sid_str = sid.get("supplier_id", str(sid))
        else:
            sid_str = str(sid) if sid is not None else ""
        match = risk_scores_df[risk_scores_df["supplier_id"] == sid_str]
        if not match.empty:
            failed_names.append(f"{match.iloc[0]['supplier_name']} ({sid_str})")
        else:
            failed_names.append(sid_str)
    failed_str = ", ".join(failed_names) if failed_names else "None"

    # BUG-01 FIX: The disruption report stores exposure and order counts inside
    # a nested 'summary' sub-dict and overlap inside 'overlap_summary'.
    # The old keys (combined_potential_financial_exposure_inr, affected_customer_orders,
    # double_counting_avoided) do not exist at the top level of the report.
    _summary = disruption_report.get("summary", {})
    _overlap = disruption_report.get("overlap_summary", {})
    financial_exposure = (
        _summary.get("headline_potential_order_value_exposure_inr")
        or _overlap.get("combined_unique_headline_potential_value_exposure_inr")
        or disruption_report.get("combined_potential_financial_exposure_inr")
        or disruption_report.get("potential_financial_exposure_inr")
        or 0
    )
    order_count = (
        _summary.get("headline_order_count")
        or _overlap.get("combined_unique_headline_order_count")
        or disruption_report.get("affected_customer_orders_count")
        or 0
    )
    double_count_avoided = (
        _overlap.get("order_count_overlap_avoided")
        or disruption_report.get("double_counting_avoided")
        or 0
    )

    # 1. Root Cause & Exposure Narrative
    if order_count == 0 and financial_exposure == 0 and any("SUP-SAP-" in s for s in failed_names):
        disruption_narrative = (
            f"A disruption scenario has been evaluated for live SAP S/4HANA Business Partner(s): {failed_str}. "
            f"Because Purchasing Info Records (material mapping) and customer sales orders are not exposed by the active "
            f"SAP OData endpoint (A_Supplier master data only), calculated downstream exposure is ₹0.00. "
            f"No committed customer orders are directly mapped to this supplier in the live gateway."
        )
    else:
        disruption_narrative = (
            f"A disruption of {disruption_report.get('duration_days', 7)} days has been declared "
            f"for {failed_str}. This failure propagates downstream across the multi-tier digital twin, "
            f"placing {order_count} customer orders at risk with a potential financial exposure "
            f"of ₹{financial_exposure:,.2f}. "
        )
        if double_count_avoided > 0:
            disruption_narrative += (
                f"By analyzing joint multi-tier supplier overlap, the system eliminated {double_count_avoided} "
                f"duplicate order exposures, ensuring accurate risk assessment."
            )

    # 2. Recovery Decision Narrative (Member 3)
    rec_plan = recovery_plan.get("recommended_plan", {})
    plan_status = rec_plan.get("status", "UNKNOWN")
    allocated_qty = rec_plan.get("allocated_quantity", 0) or 0
    req_qty = rec_plan.get("required_quantity", 0) or 0
    cost = rec_plan.get("total_procurement_cost_inr", 0) or 0
    lead_time = rec_plan.get("effective_delivery_days", "N/A")
    selected = rec_plan.get("selected_suppliers", [])

    sel_summary = []
    for s in selected:
        sel_summary.append(
            f"{s.get('supplier_name')} ({s.get('supplier_id')}, allocating {s.get('allocated_quantity')} units @ ₹{s.get('unit_cost_inr')}/unit)"
        )
    sel_str = "; ".join(sel_summary) if sel_summary else "No suppliers selected"

    recovery_narrative = (
        f"The Recovery Optimiser evaluated candidate backup suppliers for {recovery_plan.get('material_id', 'target material')}. "
        f"Verdict: {plan_status}. The recommended BALANCED plan successfully allocates {allocated_qty:,.0f} "
        f"out of {req_qty:,.0f} required units across {len(selected)} supplier(s): {sel_str}. "
        f"Total procurement cost is ₹{cost:,.2f} with an estimated delivery timeline of {lead_time} days. "
        f"Candidate ranking prioritized material compatibility, capacity feasibility, and upstream supplier independence."
    )

    # 3. Challenger Narrative (Member 4)
    if challenger_result:
        comp = challenger_result.get("comparison", {})
        rev_status = comp.get("revised_status", "UNKNOWN")
        unmet = comp.get("unmet_quantity", 0)
        feas_changed = comp.get("feasibility_changed", False)
        warnings = challenger_result.get("dependency_warnings", [])
        warn_str = " ".join(warnings) if warnings else "No shared upstream vulnerabilities detected."

        challenger_narrative = (
            f"The Cascading Failure Challenger stress-tested the proposed recovery plan against secondary failures. "
            f"Post-stress test resilience status: {rev_status}. "
            f"Feasibility status changed: {'YES - Plan Compromised' if feas_changed else 'NO - Plan Remains Robust'}. "
            f"Unmet demand under cascading stress: {unmet:,.0f} units. "
            f"Vulnerability insights: {warn_str}"
        )
    else:
        challenger_narrative = (
            "The initial recovery plan has not yet been challenged with secondary cascade or logistics route failures. "
            "Execute the Challenger in the dashboard to verify resilience under combined disruptions."
        )

    # 4. Executive Summary for Jury / C-Suite
    if order_count == 0 and financial_exposure == 0 and any("SUP-SAP-" in s for s in failed_names):
        executive_summary = (
            f"EXECUTIVE BRIEFING (SAP LIVE GATEWAY ACTIVE):\n"
            f"• Live Data Context: Disruption evaluated for SAP Business Partner {failed_str} (OData A_Supplier).\n"
            f"• Scope Limitation: In SAP S/4HANA, A_Supplier provides master vendor data only; Purchasing Info Records (material mapping) are unmapped in this endpoint, resulting in ₹0.00 downstream customer exposure.\n"
            f"• Mitigation Status: {rec_plan.get('status', 'NO_FEASIBLE_PLAN')} (No candidate alternative suppliers mapped in live gateway).\n"
            f"• Recommendation: To test full multi-tier cascading failure recovery across materials and orders, switch to SAP HANA Cloud or CSV Baseline."
        )
    else:
        executive_summary = (
            f"EXECUTIVE BRIEFING:\n"
            f"• Incident: Disruption at {failed_str} risking ₹{financial_exposure:,.2f} across {order_count} customer orders.\n"
            f"• Autonomous Mitigation: Selected {len(selected)} qualified backup supplier(s) covering {allocated_qty:,.0f}/{req_qty:,.0f} units.\n"
            f"• Financial Impact: Additional procurement investment of ₹{cost:,.2f} with {lead_time} days replenishment cycle.\n"
            f"• Resilience Recommendation: {rec_plan.get('selection_explanation', 'Approve balanced recovery strategy.')}"
        )

    return {
        "disruption_narrative": disruption_narrative,
        "recovery_narrative": recovery_narrative,
        "challenger_narrative": challenger_narrative,
        "executive_summary": executive_summary,
    }


def approve_recovery_plan(
    material_id: str,
    allocated_quantity: float,
    total_cost_inr: float,
    selected_suppliers: List[Dict[str, Any]],
    approver_name: str,
    approver_role: str,
    justification: str,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Formally records managerial approval for a recovery plan with audit trail.
    Persists to data/approval_audit_log.json.
    """
    approval_record = {
        "approval_id": f"APV-{int(datetime.now(timezone.utc).timestamp())}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "APPROVED",
        "material_id": material_id,
        "allocated_quantity": allocated_quantity,
        "total_cost_inr": total_cost_inr,
        "selected_suppliers": [
            {
                "supplier_id": s.get("supplier_id"),
                "supplier_name": s.get("supplier_name"),
                "allocated_quantity": s.get("allocated_quantity"),
                "unit_cost_inr": s.get("unit_cost_inr"),
            }
            for s in selected_suppliers
        ],
        "approver_name": approver_name or "Manager 5",
        "approver_role": approver_role or "Operations Director",
        "justification": justification or "Automated recovery plan approved to prevent production downtime.",
        "notes": notes,
    }

    audit_history = get_approval_history()
    audit_history.insert(0, approval_record)

    os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_history, f, indent=2)

    return approval_record


def reject_recovery_plan(
    material_id: str,
    allocated_quantity: float,
    total_cost_inr: float,
    selected_suppliers: List[Dict[str, Any]],
    approver_name: str,
    approver_role: str,
    rejection_reason: str,
    notes: str = "",
) -> Dict[str, Any]:
    """
    Phase 9 — Formally records managerial REJECTION of a recovery plan.

    The rejection is written to the same audit log as approvals so that the
    complete decision history is preserved in one place.  The record uses
    status='REJECTED' to distinguish it from an approval.

    Persists to data/approval_audit_log.json.
    """
    if not rejection_reason.strip():
        raise ValueError("rejection_reason must not be empty for a rejected plan.")

    rejection_record = {
        "approval_id": f"REJ-{int(datetime.now(timezone.utc).timestamp())}",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "REJECTED",
        "material_id": material_id,
        "allocated_quantity": allocated_quantity,
        "total_cost_inr": total_cost_inr,
        "selected_suppliers": [
            {
                "supplier_id": s.get("supplier_id"),
                "supplier_name": s.get("supplier_name"),
                "allocated_quantity": s.get("allocated_quantity"),
                "unit_cost_inr": s.get("unit_cost_inr"),
            }
            for s in selected_suppliers
        ],
        "approver_name": approver_name or "Manager 5",
        "approver_role": approver_role or "Operations Director",
        "justification": rejection_reason.strip(),
        "notes": notes,
    }

    audit_history = get_approval_history()
    audit_history.insert(0, rejection_record)

    os.makedirs(os.path.dirname(AUDIT_LOG_FILE), exist_ok=True)
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_history, f, indent=2)

    return rejection_record


def get_approval_history() -> List[Dict[str, Any]]:
    """Retrieve historical approval records from audit log."""
    if not os.path.exists(AUDIT_LOG_FILE):
        return []
    try:
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def generate_dossier_markdown(pipeline_result: Dict[str, Any]) -> str:
    """Export complete incident and recovery dossier in Markdown format."""
    ts = pipeline_result.get("timestamp", datetime.now(timezone.utc).isoformat())
    net = pipeline_result.get("network_summary", {})
    dis = pipeline_result.get("disruption_report", {})
    rec = pipeline_result.get("recovery_plan", {}).get("recommended_plan", {})
    ai = pipeline_result.get("ai_explanations", {})

    # BUG-08 FIX: total_procurement_cost_inr can be None or "UNKNOWN" when
    # the plan is NO_FEASIBLE_PLAN. Guard numeric format calls accordingly.
    def _fmt_cost(val: Any, default: float = 0.0) -> str:
        try:
            return f"{float(val):,.2f}"
        except (TypeError, ValueError):
            return str(val) if val is not None else "N/A"

    def _fmt_int(val: Any, default: int = 0) -> str:
        try:
            return f"{int(float(val)):,}"
        except (TypeError, ValueError):
            return str(val) if val is not None else "N/A"

    # Dossier financial values use raw disruption report (may be nested).
    _dis_summary = dis.get("summary", {})
    _dis_overlap = dis.get("overlap_summary", {})
    dis_financial = (
        _dis_summary.get("headline_potential_order_value_exposure_inr")
        or _dis_overlap.get("combined_unique_headline_potential_value_exposure_inr")
        or dis.get("combined_potential_financial_exposure_inr")
        or dis.get("potential_financial_exposure_inr")
        or 0
    )
    dis_orders_count = len(dis.get("affected_customer_orders", []))

    lines = [
        "# AUTOPILOT 2.0 — Disruption Recovery Dossier",
        f"**Generated:** {ts} | **Data Mode:** {net.get('data_mode', 'CSV Baseline')}",
        "",
        "## 1. Executive Summary",
        ai.get("executive_summary", "N/A"),
        "",
        "## 2. Disruption Scope & Downstream Impact",
        ai.get("disruption_narrative", "N/A"),
        f"- **Failed Supplier IDs:** {', '.join(pipeline_result.get('failed_suppliers', []))}",
        f"- **Duration:** {pipeline_result.get('duration_days', 7)} days",
        f"- **Customer Orders Exposed:** {dis_orders_count}",
        f"- **Combined Potential Financial Exposure:** \u20b9{_fmt_cost(dis_financial)}",
        "",
        "## 3. Recommended Recovery Plan (BALANCED)",
        ai.get("recovery_narrative", "N/A"),
        f"- **Plan Status:** {rec.get('status', 'UNKNOWN')}",
        f"- **Total Allocated Quantity:** {_fmt_int(rec.get('allocated_quantity', 0))} units",
        f"- **Unmet Quantity:** {_fmt_int(rec.get('unmet_quantity', 0))} units",
        f"- **Total Procurement Cost:** \u20b9{_fmt_cost(rec.get('total_procurement_cost_inr', 0))}",
        f"- **Effective Lead Time:** {rec.get('effective_delivery_days', 'N/A')} days",
        "",
        "### Selected Suppliers:",
    ]

    for s in rec.get("selected_suppliers", []):
        lines.append(
            f"- **{s.get('supplier_name')}** ({s.get('supplier_id')}): "
            f"{s.get('allocated_quantity')} units @ \u20b9{s.get('unit_cost_inr')}/unit "
            f"(Lead time: {s.get('lead_time_days')} days)"
        )

    if pipeline_result.get("challenger_result"):
        lines.extend([
            "",
            "## 4. Cascading Failure Stress-Test (Member 4 Challenger)",
            ai.get("challenger_narrative", "N/A"),
        ])

    lines.extend([
        "",
        "---",
        "*Confidential — Generated by AUTOPILOT 2.0 Resilience Engine (Member 5 Integration)*",
    ])

    return "\n".join(lines)
