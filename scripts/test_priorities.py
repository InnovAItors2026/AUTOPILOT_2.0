"""
Test script for all 4 priorities:
1. HANA table accessibility & row counts & Ping test
2. Recovery strategy candidate check for MAT-02
3. Financial exposure validation for single and multi supplier disruptions
"""
import sys, os
sys.path.insert(0, '.')

print("=" * 70)
print("  PRIORITY 1: SAP HANA VERIFICATION TEST")
print("=" * 70)
try:
    from src.integration.hana_client import get_hana_client
    hc = get_hana_client()
    connected, msg, details = hc.test_connection()
    print(f"Connection status  : {'CONNECTED' if connected else 'DISCONNECTED'}")
    print(f"Message            : {msg}")
    print(f"Database User      : {details.get('current_user')}")
    print(f"Default Schema     : {details.get('current_schema')}")
    print(f"Database Timestamp : {details.get('database_timestamp')}")
    print(f"TLS Active         : {details.get('tls_encrypted')}")

    print("\nPing HANA Gateway (verify_tables_accessibility):")
    res = hc.verify_tables_accessibility()
    print(f"Tables Accessible  : {res.get('tables_accessible')} / {res.get('total_tables')}")
    print(f"Total Records      : {res.get('total_records')}")
    print("Table row counts:")
    for tbl, cnt in res.get("table_counts", {}).items():
        print(f"  • {tbl:<24}: {cnt:>3} rows")
except Exception as e:
    print(f"HANA test error: {e}")

print("\n" + "=" * 70)
print("  PRIORITY 2: RECOVERY STRATEGY CANDIDATE INSPECTION")
print("=" * 70)
from src.data_loader import load_from_csv
from src.supply_chain_graph import get_supply_chain_graph
from src.recovery_optimisation import optimise_recovery
import pandas as pd

data = load_from_csv(verbose=False)
graph = get_supply_chain_graph(data)

# Test MAT-02 with failed SUP-T1-03
rec = optimise_recovery(
    material_id="MAT-02",
    required_quantity=1000.0,
    failed_supplier_ids=["SUP-T1-03"],
    data=data,
    graph=graph,
)
cands = rec.get("candidate_evaluation", [])
print(f"Total candidates evaluated for MAT-02: {len(cands)}")
for c in cands:
    print(f"  • {c.get('supplier_id')} ({c.get('supplier_name')}): "
          f"feasibility={c.get('feasibility_status')}, "
          f"material_compatible={c.get('material_compatible')}, "
          f"dependency={c.get('dependency_status')}, "
          f"unit_cost={c.get('unit_cost_inr')}, "
          f"lead_time={c.get('lead_time_days')} days")

p_bal = rec.get("recommended_plan", {})
p_cost = rec.get("lowest_cost_plan", {})
p_fast = rec.get("fastest_plan", {})

print(f"\nBALANCED plan  : status={p_bal.get('status')}, suppliers={[s.get('supplier_id') for s in p_bal.get('selected_suppliers', [])]}")
print(f"LOWEST COST    : status={p_cost.get('status')}, suppliers={[s.get('supplier_id') for s in p_cost.get('selected_suppliers', [])]}")
print(f"FASTEST        : status={p_fast.get('status')}, suppliers={[s.get('supplier_id') for s in p_fast.get('selected_suppliers', [])]}")

print("\n" + "=" * 70)
print("  PRIORITY 3: FINANCIAL EXPOSURE VALIDATION")
print("=" * 70)
from src.disruption_simulation import simulate_supplier_disruption
from src.multi_disruption_simulation import simulate_multiple_supplier_disruption

# Single disruption: SUP-T1-03
r_single = simulate_supplier_disruption("SUP-T1-03", 7, data=data, graph=graph)
co_single = r_single.get("customer_orders", {}).get("headline_path_supported", {})
orders_single = co_single.get("orders", [])
order_ids_single = sorted(set(str(o.get("order_id")) for o in orders_single))
val_single = sum(float(o.get("order_value_inr", 0)) for o in orders_single)
reported_single = r_single.get("summary", {}).get("headline_potential_order_value_exposure_inr")

print("Single Disruption: SUP-T1-03")
print(f"  Order count                : {len(orders_single)} (reported: {r_single.get('summary', {}).get('headline_order_count')})")
print(f"  Unique order IDs           : {order_ids_single}")
print(f"  Calculated sum of orders   : INR {val_single:,.2f}")
print(f"  Reported headline exposure : INR {reported_single:,.2f}")
print(f"  Matches exactly            : {val_single == reported_single}")

# Multi disruption: SUP-T1-03 + SUP-T1-04
r_multi = simulate_multiple_supplier_disruption(["SUP-T1-03", "SUP-T1-04"], 7, data=data, graph=graph)
co_multi = r_multi.get("customer_orders", {}).get("headline_path_supported", {})
orders_multi = co_multi.get("orders", [])
order_ids_multi = sorted(set(str(o.get("order_id")) for o in orders_multi))
val_multi = sum(float(o.get("order_value_inr", 0)) for o in orders_multi)
os_multi = r_multi.get("overlap_summary", {})

print("\nMulti Disruption: SUP-T1-03 + SUP-T1-04 (both provide MAT-02)")
print(f"  Sum of individual order counts : {os_multi.get('sum_of_individual_headline_order_counts')}")
print(f"  Sum of individual values       : INR {os_multi.get('sum_of_individual_headline_potential_value_exposure_inr'):,.2f}")
print(f"  Combined unique orders         : {len(orders_multi)} (reported: {os_multi.get('combined_unique_headline_order_count')})")
print(f"  Combined unique order IDs      : {order_ids_multi}")
print(f"  Calculated unique sum          : INR {val_multi:,.2f}")
print(f"  Reported unique exposure       : INR {os_multi.get('combined_unique_headline_potential_value_exposure_inr'):,.2f}")
print(f"  Overlap avoided order count    : {os_multi.get('order_count_overlap_avoided')}")
print(f"  Overlap avoided value          : INR {os_multi.get('value_exposure_overlap_avoided_inr'):,.2f}")
print(f"  Deduplication working correctly: {val_multi == os_multi.get('combined_unique_headline_potential_value_exposure_inr')}")

# Multi disruption: SUP-T1-01 + SUP-T1-03 (different materials)
r_diff = simulate_multiple_supplier_disruption(["SUP-T1-01", "SUP-T1-03"], 7, data=data, graph=graph)
os_diff = r_diff.get("overlap_summary", {})
print("\nMulti Disruption: SUP-T1-01 + SUP-T1-03 (different materials: MAT-03 and MAT-02)")
print(f"  Individual sum value           : INR {os_diff.get('sum_of_individual_headline_potential_value_exposure_inr'):,.2f}")
print(f"  Combined unique value          : INR {os_diff.get('combined_unique_headline_potential_value_exposure_inr'):,.2f}")
print(f"  Overlap avoided value          : INR {os_diff.get('value_exposure_overlap_avoided_inr'):,.2f}")
print(f"  Combined unique order count    : {os_diff.get('combined_unique_headline_order_count')}")

print("\n" + "=" * 70)
print("  VALIDATION COMPLETE")
print("=" * 70)
