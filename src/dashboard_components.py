"""
dashboard_components.py
------------------------
Enterprise visual components for AUTOPILOT 2.0 Supply Chain Control Tower.
Generates responsive, interactive HTML/SVG components matching SAP Fiori and
Palantir Foundry operational intelligence aesthetics.
Runs 100% offline with zero external dependencies.
"""

from typing import Any, Dict, List, Optional
import pandas as pd


def clean_html(html_str: str) -> str:
    """
    Sanitize HTML strings by stripping leading whitespace from all lines
    and removing blank lines. This strictly prevents Markdown parsers from
    interpreting 4+ space indented HTML as code blocks (<pre><code>).
    """
    if not html_str:
        return ""
    return "\n".join(line.strip() for line in html_str.splitlines() if line.strip())


def render_risk_heatmap_html(risk_scores_df: pd.DataFrame, top_n: int = 15) -> str:
    """
    Render an interactive 2D supplier risk matrix heatmap.
    Rows: Top riskiest suppliers
    Columns: 6 Operational Risk Factors + Overall Score + Status
    """
    if risk_scores_df.empty:
        return "<div style='color:#94A3B8;padding:20px;text-align:center;'>No risk scores available.</div>"

    cols = [
        "supplier_id", "supplier_name", "overall_risk_score", "final_risk_category",
        "material_dependency_risk", "inventory_risk", "lead_time_risk",
        "quality_risk", "capacity_risk", "upstream_dependency_risk"
    ]
    avail = [c for c in cols if c in risk_scores_df.columns]
    sorted_df = risk_scores_df[avail].sort_values(by="overall_risk_score", ascending=False).head(top_n)

    def get_color(val):
        if val is None or pd.isna(val):
            return "#F1F5F9", "#64748B"
        try:
            v = float(val)
        except (ValueError, TypeError):
            return "#F1F5F9", "#64748B"
        if v >= 75:
            return "#FEF2F2", "#DC2626"
        elif v >= 50:
            return "#FFF7ED", "#EA580C"
        elif v >= 25:
            return "#FFFBEB", "#D97706"
        else:
            return "#ECFDF5", "#059669"

    rows_html = ""
    for _, row in sorted_df.iterrows():
        sid = row.get("supplier_id", "")
        sname = str(row.get("supplier_name", sid))[:20]
        overall = float(row.get("overall_risk_score", 0) or 0)
        cat = str(row.get("final_risk_category", "Low"))
        
        cat_badge = {
            "Critical": "<span style='background:#FEF2F2;color:#991B1B;padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.72rem;border:1px solid #FECACA;'>CRITICAL</span>",
            "High": "<span style='background:#FFF7ED;color:#C2410C;padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.72rem;border:1px solid #FFEDD5;'>HIGH</span>",
            "Medium": "<span style='background:#FFFBEB;color:#B45309;padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.72rem;border:1px solid #FEF3C7;'>MEDIUM</span>",
            "Low": "<span style='background:#ECFDF5;color:#065F46;padding:2px 8px;border-radius:4px;font-weight:700;font-size:0.72rem;border:1px solid #A7F3D0;'>LOW</span>",
        }.get(cat, f"<span>{cat}</span>")

        # 6 Factors
        f_cells = ""
        for fkey in [
            "material_dependency_risk", "inventory_risk", "lead_time_risk",
            "quality_risk", "capacity_risk", "upstream_dependency_risk"
        ]:
            val = row.get(fkey, 0)
            bg, fg = get_color(val)
            val_str = f"{float(val):.1f}" if val is not None and not pd.isna(val) else "N/A"
            f_cells += f"<td style='background:{bg};color:{fg};font-weight:700;text-align:center;padding:7px 4px;font-size:0.78rem;border:1px solid #E2E8F0;'>{val_str}</td>"

        rows_html += f"""<tr style='border-bottom:1px solid #E2E8F0;transition:background 0.15s;' onmouseover="this.style.background='#F8FAFC'" onmouseout="this.style.background='transparent'">
<td style='padding:8px 10px;font-weight:700;color:#1E293B;font-size:0.80rem;white-space:nowrap;'>{sid}</td>
<td style='padding:8px 10px;color:#334155;font-size:0.80rem;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' title='{row.get("supplier_name", "")}'>{sname}</td>
<td style='padding:8px 6px;text-align:center;'>{cat_badge}</td>
<td style='padding:8px 6px;font-weight:800;color:#0F172A;text-align:center;font-size:0.85rem;background:#F8FAFC;'>{overall:.1f}</td>
{f_cells}
</tr>"""

    html = f"""<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-radius:8px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,0.04);overflow-x:auto;'>
<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;'>
<div style='font-size:0.84rem;font-weight:700;color:#1E293B;text-transform:uppercase;letter-spacing:0.5px;'>
🎯 Operational Risk Heatmap Matrix (Top {len(sorted_df)} Riskiest Suppliers)
</div>
<div style='display:flex;gap:8px;font-size:0.70rem;color:#64748B;'>
<span style='display:flex;align-items:center;gap:3px;'><span style='width:10px;height:10px;background:#FEF2F2;border:1px solid #FECACA;border-radius:2px;'></span> Critical (≥75)</span>
<span style='display:flex;align-items:center;gap:3px;'><span style='width:10px;height:10px;background:#FFF7ED;border:1px solid #FFEDD5;border-radius:2px;'></span> High (50-74)</span>
<span style='display:flex;align-items:center;gap:3px;'><span style='width:10px;height:10px;background:#FFFBEB;border:1px solid #FEF3C7;border-radius:2px;'></span> Medium (25-49)</span>
<span style='display:flex;align-items:center;gap:3px;'><span style='width:10px;height:10px;background:#ECFDF5;border:1px solid #A7F3D0;border-radius:2px;'></span> Low (&lt;25)</span>
</div>
</div>
<table style='width:100%;border-collapse:collapse;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;'>
<thead>
<tr style='background:#F1F5F9;border-bottom:2px solid #CBD5E1;'>
<th style='padding:8px 10px;text-align:left;font-size:0.72rem;font-weight:700;color:#475569;text-transform:uppercase;'>Supplier ID</th>
<th style='padding:8px 10px;text-align:left;font-size:0.72rem;font-weight:700;color:#475569;text-transform:uppercase;'>Name</th>
<th style='padding:8px 6px;text-align:center;font-size:0.72rem;font-weight:700;color:#475569;text-transform:uppercase;'>Category</th>
<th style='padding:8px 6px;text-align:center;font-size:0.72rem;font-weight:700;color:#0F172A;text-transform:uppercase;background:#E2E8F0;'>Score</th>
<th style='padding:8px 4px;text-align:center;font-size:0.70rem;font-weight:600;color:#475569;'>Material (30%)</th>
<th style='padding:8px 4px;text-align:center;font-size:0.70rem;font-weight:600;color:#475569;'>Inventory (20%)</th>
<th style='padding:8px 4px;text-align:center;font-size:0.70rem;font-weight:600;color:#475569;'>Lead Time (15%)</th>
<th style='padding:8px 4px;text-align:center;font-size:0.70rem;font-weight:600;color:#475569;'>Quality (15%)</th>
<th style='padding:8px 4px;text-align:center;font-size:0.70rem;font-weight:600;color:#475569;'>Capacity (15%)</th>
<th style='padding:8px 4px;text-align:center;font-size:0.70rem;font-weight:600;color:#475569;'>Upstream (5%)</th>
</tr>
</thead>
<tbody>
{rows_html}
</tbody>
</table>
</div>"""
    return clean_html(html)


def render_disruption_delta_html(
    dis_res: Dict[str, Any],
    base_data: Dict[str, Any],
    sim_failed: List[str],
    sim_days: int,
) -> str:
    """
    Render comparative command console showing Baseline Nominal vs Simulated Disrupted State.
    """
    total_orders = len(base_data.get("customer_orders", []))
    total_fac = len(base_data.get("factories", []))
    total_wh = len(base_data.get("warehouses", []))
    
    order_data = base_data.get("customer_orders", pd.DataFrame())
    if isinstance(order_data, pd.DataFrame) and not order_data.empty and "order_value_inr" in order_data.columns:
        total_book_val = float(order_data["order_value_inr"].sum())
    elif isinstance(order_data, list):
        total_book_val = float(sum(float(o.get("order_value_inr", 0) or 0) for o in order_data if isinstance(o, dict)))
    else:
        total_book_val = 0.0

    _summary = dis_res.get("summary", {})
    _overlap = dis_res.get("overlap_summary", {})
    fin_exp = (
        _summary.get("headline_potential_order_value_exposure_inr")
        or _overlap.get("combined_unique_headline_potential_value_exposure_inr")
        or dis_res.get("combined_potential_financial_exposure_inr")
        or dis_res.get("potential_financial_exposure_inr")
        or 0
    )
    orders_exp = (
        _summary.get("headline_order_count")
        or _overlap.get("combined_unique_headline_order_count")
        or 0
    )
    n_fac = len(dis_res.get("factories", []))
    n_wh = len(dis_res.get("warehouses", []))

    pct_orders_at_risk = round(100 * orders_exp / max(1, total_orders), 1)
    pct_val_at_risk = round(100 * fin_exp / max(1.0, total_book_val), 1)

    html = f"""<div style='background:linear-gradient(135deg, #101C2C 0%, #172B46 100%);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:16px 20px;color:#FFFFFF;margin-bottom:14px;box-shadow:0 4px 16px rgba(0,0,0,0.12);'>
<div style='display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(255,255,255,0.12);padding-bottom:10px;margin-bottom:14px;flex-wrap:wrap;gap:8px;'>
<div>
<span style='font-size:0.68rem;font-weight:700;color:#38BDF8;text-transform:uppercase;letter-spacing:0.8px;'>Operational Impact Assessment</span>
<div style='font-size:1.1rem;font-weight:800;color:#FFFFFF;'>Disruption Scenario: {', '.join(sim_failed)} ({sim_days} Days)</div>
</div>
<div style='text-align:right;'>
<span style='background:#EF4444;color:#FFFFFF;padding:3px 10px;border-radius:4px;font-size:0.72rem;font-weight:700;text-transform:uppercase;'>High Exposure Active</span>
</div>
</div>
<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(160px, 1fr));gap:12px;'>
<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:10px 12px;'>
<div style='font-size:0.68rem;color:#94A3B8;text-transform:uppercase;'>Financial Backlog at Risk</div>
<div style='font-size:1.25rem;font-weight:800;color:#F87171;'>₹{fin_exp:,.0f}</div>
<div style='font-size:0.70rem;color:#FCA5A5;'>{pct_val_at_risk}% of total order book</div>
</div>
<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:10px 12px;'>
<div style='font-size:0.68rem;color:#94A3B8;text-transform:uppercase;'>Exposed Customer Orders</div>
<div style='font-size:1.25rem;font-weight:800;color:#FBBF24;'>{orders_exp} / {total_orders}</div>
<div style='font-size:0.70rem;color:#FDE68A;'>{pct_orders_at_risk}% fulfillment at risk</div>
</div>
<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:10px 12px;'>
<div style='font-size:0.68rem;color:#94A3B8;text-transform:uppercase;'>Assembly Plants Throttled</div>
<div style='font-size:1.25rem;font-weight:800;color:#38BDF8;'>{n_fac} / {total_fac} Plants</div>
<div style='font-size:0.70rem;color:#BAE6FD;'>Manufacturing impacted</div>
</div>
<div style='background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:10px 12px;'>
<div style='font-size:0.68rem;color:#94A3B8;text-transform:uppercase;'>Regional Warehouses Strained</div>
<div style='font-size:1.25rem;font-weight:800;color:#A78BFA;'>{n_wh} / {total_wh} Hubs</div>
<div style='font-size:0.70rem;color:#DDD6FE;'>Buffer inventory depleted</div>
</div>
</div>
</div>"""
    return clean_html(html)


def render_strategy_tradeoff_html(p_bal: dict, p_cost: dict, p_fast: dict) -> str:
    """
    Render visual strategy trade-off comparison matrix across Balanced, Lowest Cost, and Fastest Recovery.
    All HTML is completely unindented to prevent markdown code-block triggers.
    """
    strategies = [
        {"name": "BALANCED (Recommended)", "icon": "⚖️", "plan": p_bal, "color": "#0A6ED1", "tag": "Multi-Criteria Optimum"},
        {"name": "LOWEST COST", "icon": "💰", "plan": p_cost, "color": "#16A68A", "tag": "Min Total Procurement Cost"},
        {"name": "FASTEST RECOVERY", "icon": "⚡", "plan": p_fast, "color": "#E9A23B", "tag": "Min Delivery Days"},
    ]

    cards_html = ""
    for s in strategies:
        plan = s["plan"] or {}
        allocated = float(plan.get("allocated_quantity", 0) or 0)
        required = float(plan.get("required_quantity", 0) or 0)
        cost = float(plan.get("total_procurement_cost_inr", 0) or 0)
        days = plan.get("effective_delivery_days", "N/A")
        status = plan.get("status", "N/A")
        
        is_feas = status not in ("NO_FEASIBLE_PLAN", "FAILED", None)
        status_bg = "#ECFDF5" if is_feas else "#FEF2F2"
        status_fg = "#065F46" if is_feas else "#991B1B"
        alloc_pct = int(100 * allocated / required) if required > 0 else 0

        selected = plan.get("selected_suppliers", [])
        sup_list_html = "".join([
            f"<div style='font-size:0.74rem;color:#334155;padding:2px 0;'>• <strong>{sup.get('supplier_name', 'Unknown')}</strong> ({sup.get('allocated_quantity', 0):,.0f} units)</div>"
            for sup in selected
        ]) or "<div style='font-size:0.74rem;color:#94A3B8;'>No suppliers allocated</div>"

        cards_html += f"""<div style='background:#FFFFFF;border:1px solid #E2E8F0;border-top:4px solid {s["color"]};border-radius:8px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.03);display:flex;flex-direction:column;justify-content:space-between;'>
<div>
<div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;'>
<div style='font-size:0.92rem;font-weight:800;color:#1E293B;'>{s["icon"]} {s["name"]}</div>
</div>
<div style='font-size:0.68rem;color:#64748B;font-weight:600;margin-bottom:10px;'>{s["tag"]}</div>
<div style='margin-bottom:12px;'>
<span style='background:{status_bg};color:{status_fg};padding:3px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;border:1px solid {status_fg}30;'>{status}</span>
</div>
<div style='background:#F8FAFC;border:1px solid #E2E8F0;border-radius:6px;padding:10px;margin-bottom:12px;'>
<div style='display:flex;justify-content:space-between;padding:3px 0;font-size:0.78rem;'><span style='color:#64748B;'>Allocated Units:</span><strong style='color:#0F172A;'>{allocated:,.0f} / {required:,.0f} ({alloc_pct}%)</strong></div>
<div style='display:flex;justify-content:space-between;padding:3px 0;font-size:0.78rem;'><span style='color:#64748B;'>Procurement Cost:</span><strong style='color:#0A6ED1;'>₹{cost:,.2f}</strong></div>
<div style='display:flex;justify-content:space-between;padding:3px 0;font-size:0.78rem;'><span style='color:#64748B;'>Delivery Lead Time:</span><strong style='color:#10B981;'>{days} Days</strong></div>
</div>
<div style='font-size:0.72rem;font-weight:700;color:#475569;text-transform:uppercase;margin-bottom:4px;'>Selected Allocation:</div>
{sup_list_html}
</div>
</div>"""

    container_html = f"<div style='display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:12px;margin:12px 0 16px;'>{cards_html}</div>"
    return clean_html(container_html)
