"""
Test complete SAP Live Gateway integration end-to-end.
"""
import sys, os
sys.path.insert(0, r"C:\Users\Spandana B S\Downloads\AUTOPILOT_2.0-main\AUTOPILOT_2.0-main")

from unittest.mock import MagicMock, patch
import pandas as pd
from src.sap_client import SAPClient
from src.supply_chain_graph import get_supply_chain_graph
from src.supplier_risk import build_supplier_risk_factors
from src.risk_scoring import calculate_supplier_risk_scores
from src.disruption_simulation import simulate_supplier_disruption
from src.pipeline import run_full_resilience_pipeline

print("=" * 65)
print("TESTING SAP LIVE GATEWAY INTEGRATION END-TO-END")
print("=" * 65)

# Build 100 sample SAP suppliers (95 active, 5 with various SAP blocks)
results_list = []
for i in range(1, 101):
    rec = {
        "Supplier": str(100000 + i),
        "SupplierName": f"SAP Global Supplier {i}",
        "SupplierFullName": f"SAP Global Supplier {i} GmbH",
        "CityName": "Walldorf" if i % 2 == 0 else "Bengaluru",
        "Country": "DE" if i % 2 == 0 else "IN",
        "SupplierAccountGroup": "SUPL" if i % 3 != 0 else "KRED",
        "PostingIsBlocked": (i == 1),
        "PurchasingIsBlocked": (i == 2 or i == 3),
        "PaymentIsBlockedForSupplier": (i == 4),
        "DeletionIndicator": (i == 5),
    }
    results_list.append(rec)

mock_response = MagicMock()
mock_response.status_code = 200
mock_response.json.return_value = {"d": {"results": results_list}}

client = SAPClient(auth_type="api_key", api_key="test_api_key_sandbox")

with patch.object(client, "test_connection", return_value=(True, "Connected to SAP S/4HANA (HTTP 200)", {})):
    with patch("requests.get", return_value=mock_response):
        data = client.fetch_all(fallback_on_error=False)

# 1. Verify entity status and tables
print("1. DATASET INTEGRITY:")
print(f"   Suppliers loaded: {len(data['suppliers'])}")
print(f"   Mode: {data['_sap_status']['mode'].iloc[0]}")
print(f"   Active Source: {data['_sap_status']['active_source'].iloc[0]}")
assert len(data['suppliers']) == 100, f"Expected 100 suppliers, got {len(data['suppliers'])}"
assert "_sap_entity_status" in data, "Missing _sap_entity_status"
print("   Entity Coverage Matrix:")
for _, row in data["_sap_entity_status"].iterrows():
    print(f"     • {row['entity']:<22} : {row['status']:<22} ({row['records']} records)")

# 2. Verify graph building
graph = get_supply_chain_graph(data)
print("\n2. DIGITAL TWIN GRAPH:")
print(f"   Total Nodes: {graph.number_of_nodes()}")
print(f"   Total Edges: {graph.number_of_edges()}")

# 3. Verify Supplier Risk Radar
rf = build_supplier_risk_factors(data=data, graph=graph)
scores = calculate_supplier_risk_scores(rf)
print("\n3. SUPPLIER RISK SCORING:")
print(f"   Total Scored: {len(scores)}")
cat_counts = scores["final_risk_category"].value_counts().to_dict()
print(f"   Category Distribution: {cat_counts}")
print(f"   Data Confidence: {scores['data_confidence_pct'].unique().tolist()}%")

# Verify that all 5 blocked suppliers are Critical (score = 75.0)
blocked_scores = scores[scores["supplier_id"].isin([f"SUP-SAP-{100000 + i}" for i in range(1, 6)])]
print("   Blocked Suppliers Risk:")
for _, r in blocked_scores.iterrows():
    print(f"     • {r['supplier_id']}: score={r['overall_risk_score']}, category={r['final_risk_category']}, capacity_risk={r['capacity_risk']}")
    assert r["final_risk_category"] == "Critical", f"Expected Critical for {r['supplier_id']}, got {r['final_risk_category']}"

# Verify active suppliers
active_sample = scores[~scores["supplier_id"].isin([f"SUP-SAP-{100000 + i}" for i in range(1, 6)])].iloc[0]
print(f"   Active Supplier Sample ({active_sample['supplier_id']}): score={active_sample['overall_risk_score']}, category={active_sample['final_risk_category']}, confidence={active_sample['data_confidence_pct']}%")
assert active_sample["overall_risk_score"] == 0.0
assert active_sample["data_confidence_pct"] == 20.0

# 4. Verify Disruption Simulator on live SAP supplier
print("\n4. DISRUPTION SIMULATION:")
sim_res = simulate_supplier_disruption("SUP-SAP-100001", duration_days=7, data=data, graph=graph)
fin_exp = sim_res.get("summary", {}).get("headline_potential_order_value_exposure_inr", 0)
orders = sim_res.get("summary", {}).get("headline_order_count", 0)
print(f"   Simulated SUP-SAP-100001: Financial Exposure = INR {fin_exp}, Exposed Orders = {orders}")
assert fin_exp == 0
assert orders == 0

# 5. Verify Resilience Pipeline & Executive Briefing
print("\n5. RESILIENCE PIPELINE & AI BRIEFING:")
pipe_res = run_full_resilience_pipeline(
    failed_supplier_ids=["SUP-SAP-100001"],
    duration_days=7,
    target_material_id="MAT-02",
    required_quantity=1000.0,
    data=data,
    graph=graph,
)
print("   Pipeline execution completed successfully.")
print("   Executive Briefing:")
print("   " + pipe_res["ai_explanations"]["executive_summary"].replace("\u20b9", "INR ").replace("\n", "\n   "))
print("   Disruption Narrative:")
print("   " + pipe_res["ai_explanations"]["disruption_narrative"].replace("\u20b9", "INR "))

print("\n" + "=" * 65)
print("ALL SAP LIVE GATEWAY VERIFICATIONS COMPLETED SUCCESSFULLY!")
print("=" * 65)
