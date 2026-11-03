"""
test_member5.py
---------------
Automated tests for Member 5: SAP Integration, End-to-End Pipeline,
AI Explanations, Approval Workflow, and Dossier Export.
"""

import json
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.sap_client import SAPClient, get_sap_client
from src.pipeline import (
    run_full_resilience_pipeline,
    approve_recovery_plan,
    reject_recovery_plan,
    get_approval_history,
    generate_dossier_markdown,
    AUDIT_LOG_FILE,
)


class Member5Tests(unittest.TestCase):
    def test_sap_client_unconfigured_fallback(self):
        client = SAPClient(auth_type="api_key", api_key="")
        connected, msg, details = client.test_connection()
        self.assertFalse(connected)
        self.assertIn("missing or unconfigured", msg)

        # Fallback to CSV should succeed smoothly
        data = client.fetch_all(fallback_on_error=True)
        self.assertIn("suppliers", data)
        self.assertEqual(len(data["suppliers"]), 35)
        self.assertIn("_sap_status", data)
        self.assertEqual(data["_sap_status"]["mode"].iloc[0], "CSV_FALLBACK")

    def test_sap_client_mock_mode(self):
        client = SAPClient(auth_type="mock")
        connected, msg, details = client.test_connection()
        self.assertTrue(connected)
        self.assertIn("Mock", msg)

        data = client.fetch_all()
        self.assertIn("suppliers", data)
        self.assertIn("_sap_status", data)
        self.assertEqual(data["_sap_status"]["mode"].iloc[0], "SAP_ODATA_VERIFIED")

    def test_full_resilience_pipeline_execution(self):
        result = run_full_resilience_pipeline(
            failed_supplier_ids=["SUP-T1-03"],
            duration_days=7,
            additional_challenger_suppliers=["SUP-T2-01"],
            failed_routes=["RTE-03"],
            target_material_id="MAT-02",
            required_quantity=1000.0,
        )

        self.assertIn("network_summary", result)
        self.assertEqual(result["network_summary"]["total_nodes"], 91)
        self.assertIn("risk_scores_df", result)
        self.assertEqual(len(result["risk_scores_df"]), 35)

        self.assertIn("disruption_report", result)
        self.assertEqual(result["failed_suppliers"], ["SUP-T1-03"])

        self.assertIn("recovery_plan", result)
        rec = result["recovery_plan"]["recommended_plan"]
        self.assertEqual(rec["status"], "FEASIBLE")
        self.assertEqual(rec["allocated_quantity"], 1000.0)

        self.assertIn("challenger_result", result)
        self.assertIn("ai_explanations", result)
        ai = result["ai_explanations"]
        self.assertIn("executive_summary", ai)
        self.assertIn("disruption_narrative", ai)
        self.assertIn("recovery_narrative", ai)

    def test_approval_workflow_and_audit_trail(self):
        sample_suppliers = [{"supplier_id": "SUP-T1-04", "supplier_name": "WesternCell Packs", "allocated_quantity": 1000, "unit_cost_inr": 645}]
        record = approve_recovery_plan(
            material_id="MAT-02",
            allocated_quantity=1000.0,
            total_cost_inr=645000.0,
            selected_suppliers=sample_suppliers,
            approver_name="Dr. Shreya",
            approver_role="Chief Supply Chain Officer",
            justification="Emergency re-routing authorized for Hackfest 2026 scenario.",
            notes="Testing audit trail persistence",
        )

        self.assertEqual(record["status"], "APPROVED")
        self.assertEqual(record["approver_name"], "Dr. Shreya")

        history = get_approval_history()
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["approval_id"], record["approval_id"])

    def test_dossier_markdown_generation(self):
        result = run_full_resilience_pipeline(
            failed_supplier_ids=["SUP-T1-03"],
            target_material_id="MAT-02",
            required_quantity=500.0,
        )
        dossier = generate_dossier_markdown(result)
        self.assertIn("# AUTOPILOT 2.0 — Disruption Recovery Dossier", dossier)
        self.assertIn("Executive Summary", dossier)
        self.assertIn("Selected Suppliers", dossier)

    def test_rejection_workflow_and_audit_trail(self):
        """Phase 9: Test formal rejection recording and audit trail persistence."""
        sample_suppliers = [{"supplier_id": "SUP-T1-04", "supplier_name": "WesternCell Packs", "allocated_quantity": 1000, "unit_cost_inr": 645}]
        record = reject_recovery_plan(
            material_id="MAT-02",
            allocated_quantity=1000.0,
            total_cost_inr=645000.0,
            selected_suppliers=sample_suppliers,
            approver_name="Dr. Shreya",
            approver_role="Chief Supply Chain Officer",
            rejection_reason="Excessive cost premium and shared upstream dependency risk.",
            notes="Testing rejection audit trail persistence",
        )

        self.assertEqual(record["status"], "REJECTED")
        self.assertEqual(record["approver_name"], "Dr. Shreya")
        self.assertEqual(record["justification"], "Excessive cost premium and shared upstream dependency risk.")
        self.assertTrue(record["approval_id"].startswith("REJ-"))

        history = get_approval_history()
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["approval_id"], record["approval_id"])

    def test_rejection_requires_reason(self):
        """Phase 9: Test that empty rejection reason raises ValueError."""
        with self.assertRaises(ValueError):
            reject_recovery_plan(
                material_id="MAT-02",
                allocated_quantity=100.0,
                total_cost_inr=10000.0,
                selected_suppliers=[],
                approver_name="Manager",
                approver_role="CSCO",
                rejection_reason="   ",
            )

    def test_dossier_markdown_with_infeasible_plan(self):
        """Phase 8 & BUG-08: Test dossier generation when recovery plan is NO_FEASIBLE_PLAN."""
        result = run_full_resilience_pipeline(
            failed_supplier_ids=["SUP-T2-01", "SUP-T2-03"],
            target_material_id="MAT-02",
            required_quantity=1000.0,
        )
        dossier = generate_dossier_markdown(result)
        self.assertIn("# AUTOPILOT 2.0 — Disruption Recovery Dossier", dossier)
        self.assertIn("Executive Summary", dossier)
        self.assertIn("NO_FEASIBLE_PLAN", dossier)

    def test_sap_live_supplier_field_mapping_and_blocks(self):
        """Test SAP Live Gateway field mapping and real blocking indicator logic."""
        from unittest.mock import MagicMock, patch

        client = SAPClient(auth_type="api_key", api_key="test_key_123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "d": {
                "results": [
                    {
                        "Supplier": "100001",
                        "SupplierName": "Active Clean Vendor",
                        "SupplierFullName": "Active Clean Vendor Inc.",
                        "CityName": "Bengaluru",
                        "Country": "IN",
                        "SupplierAccountGroup": "SUPL",
                        "PostingIsBlocked": False,
                        "PurchasingIsBlocked": False,
                        "PaymentIsBlockedForSupplier": False,
                        "DeletionIndicator": False,
                    },
                    {
                        "Supplier": "100002",
                        "SupplierName": "Blocked Purchasing Vendor",
                        "SupplierFullName": "Blocked Purchasing Vendor LLC",
                        "CityName": "Munich",
                        "Country": "DE",
                        "SupplierAccountGroup": "KRED",
                        "PostingIsBlocked": False,
                        "PurchasingIsBlocked": True,
                        "PaymentIsBlockedForSupplier": False,
                        "DeletionIndicator": False,
                    },
                ]
            }
        }

        with patch("requests.get", return_value=mock_response):
            df = client.fetch_suppliers_odata()

        self.assertEqual(len(df), 2)
        # Check active vendor
        active = df.iloc[0]
        self.assertEqual(active["supplier_id"], "SUP-SAP-100001")
        self.assertEqual(active["capacity_status"], "sufficient")
        self.assertIsNone(active["lead_time_days"])
        self.assertIsNone(active["quality_score"])
        self.assertIsNone(active["tier"])

        # Check blocked vendor
        blocked = df.iloc[1]
        self.assertEqual(blocked["supplier_id"], "SUP-SAP-100002")
        self.assertEqual(blocked["capacity_status"], "insufficient")
        self.assertTrue(blocked["sap_purchasing_blocked"])

    def test_sap_live_risk_scoring_confidence_honesty(self):
        """Test that live SAP suppliers produce honest confidence (20%) and correct risk categories."""
        from unittest.mock import MagicMock, patch
        from src.supplier_risk import build_supplier_risk_factors
        from src.risk_scoring import calculate_supplier_risk_scores
        from src.supply_chain_graph import get_supply_chain_graph

        client = SAPClient(auth_type="api_key", api_key="test_key_123")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "d": {
                "results": [
                    {"Supplier": "100", "SupplierName": "Vendor Normal", "PurchasingIsBlocked": False, "PostingIsBlocked": False},
                    {"Supplier": "200", "SupplierName": "Vendor Blocked", "PurchasingIsBlocked": True, "PostingIsBlocked": False},
                ]
            }
        }

        with patch.object(client, "test_connection", return_value=(True, "Connected", {})):
            with patch("requests.get", return_value=mock_response):
                data = client.fetch_all(fallback_on_error=False)

        graph = get_supply_chain_graph(data)
        rf = build_supplier_risk_factors(data=data, graph=graph)
        scores = calculate_supplier_risk_scores(rf)

        self.assertEqual(len(scores), 2)
        normal_row = scores[scores["supplier_id"] == "SUP-SAP-100"].iloc[0]
        blocked_row = scores[scores["supplier_id"] == "SUP-SAP-200"].iloc[0]

        # Normal vendor has 0 score, Low risk, but honest 20% confidence (not fake 50%)
        self.assertEqual(normal_row["overall_risk_score"], 0.0)
        self.assertEqual(normal_row["final_risk_category"], "Low")
        self.assertEqual(normal_row["data_confidence_pct"], 20.0)
        self.assertIn("material_dependency", normal_row["unknown_factors"])
        self.assertIn("lead_time", normal_row["unknown_factors"])

        # Blocked vendor has 75.0 score ((15*100 + 5*0)/20 = 75.0), Critical risk
        self.assertEqual(blocked_row["overall_risk_score"], 75.0)
        self.assertEqual(blocked_row["final_risk_category"], "Critical")

        # Check entity status tracking
        self.assertIn("_sap_entity_status", data)
        status_df = data["_sap_entity_status"]
        self.assertEqual(len(status_df), 9)
        suppliers_row = status_df[status_df["entity"] == "suppliers"].iloc[0]
        self.assertEqual(suppliers_row["status"], "LIVE_VERIFIED")


if __name__ == "__main__":
    unittest.main()
