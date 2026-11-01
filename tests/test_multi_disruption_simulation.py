"""
Automated unit tests for src/multi_disruption_simulation.py (Member 2, Phase 2 - Stage 1).

Covers:
  - Input validation (types, count, whitespace, non-suppliers, duration, error aggregation)
  - Combined downstream supplier identification & overlapping dependencies
  - Direct and potential cascading materials & priority rules (DIRECT beats POTENTIAL_CASCADING)
  - Unmapped supplier handling (KNOWN, PARTIAL, UNKNOWN)
"""

import json
import os
import sys
import unittest
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.data_loader import load_all_data
from src.disruption_simulation import (
    DIRECT,
    FACTORY_LINK_ONLY,
    INVENTORY_LINK,
    LINKED_FACTORY_HOLDS_MATERIAL,
    LOCATION_LINK_ONLY,
    MITIGATED,
    POTENTIAL_CASCADING,
    PRODUCT_LINK_ONLY,
    ROUTE_LINK_ONLY,
    SUPPLIER_ROUTE,
    UNKNOWN,
    UNMITIGATED,
    WAREHOUSE_HOLDS_MATERIAL,
    simulate_supplier_disruption,
)
from src.multi_disruption_simulation import (
    KNOWN,
    PARTIAL,
    format_multi_disruption_report,
    simulate_multiple_supplier_disruption,
)
from src.supply_chain_graph import build_supply_chain_graph, get_supply_chain_graph


# ---------------------------------------------------------------------------
# Synthetic test data builder
# ---------------------------------------------------------------------------

def make_multi_test_data(shared_downstream=False, shared_material=False, nested_failure=False):
    """
    Construct a deterministic synthetic supply chain graph.

    Graph topology:
      S-U1 (Tier 3) ---> S-A (Tier 2) ---> S-C1 (Tier 1)
      S-U2 (Tier 3) ---> S-B (Tier 2) ---> S-C2 (Tier 1)
    """
    suppliers = pd.DataFrame([
        {"supplier_id": "S-U1", "supplier_name": "Upstream 1", "tier": 3, "capacity_status": "sufficient"},
        {"supplier_id": "S-U2", "supplier_name": "Upstream 2", "tier": 3, "capacity_status": "sufficient"},
        {"supplier_id": "S-A", "supplier_name": "Primary A", "tier": 2, "capacity_status": "sufficient"},
        {"supplier_id": "S-B", "supplier_name": "Primary B", "tier": 2, "capacity_status": "sufficient"},
        {"supplier_id": "S-C1", "supplier_name": "Downstream 1", "tier": 1, "capacity_status": "sufficient"},
        {"supplier_id": "S-C2", "supplier_name": "Downstream 2", "tier": 1, "capacity_status": "sufficient"},
    ])

    mat_rows = [
        {"supplier_id": "S-A", "material_id": "M-A", "is_backup": 0, "monthly_capacity_units": 100},
        {"supplier_id": "S-B", "material_id": "M-B", "is_backup": 0, "monthly_capacity_units": 200},
        {"supplier_id": "S-C1", "material_id": "M-C1", "is_backup": 0, "monthly_capacity_units": 150},
        {"supplier_id": "S-C2", "material_id": "M-C2", "is_backup": 0, "monthly_capacity_units": 250},
    ]
    if shared_material:
        # S-B also supplies M-A
        mat_rows.append({"supplier_id": "S-B", "material_id": "M-A", "is_backup": 0, "monthly_capacity_units": 120})

    dependencies = [
        {"dependency_id": "D1", "downstream_supplier_id": "S-A", "upstream_supplier_id": "S-U1", "dependency_type": "direct"},
        {"dependency_id": "D2", "downstream_supplier_id": "S-B", "upstream_supplier_id": "S-U2", "dependency_type": "direct"},
        {"dependency_id": "D3", "downstream_supplier_id": "S-C1", "upstream_supplier_id": "S-A", "dependency_type": "direct"},
        {"dependency_id": "D4", "downstream_supplier_id": "S-C2", "upstream_supplier_id": "S-B", "dependency_type": "direct"},
    ]

    if shared_downstream:
        # S-B also supplies S-C1, so both S-A and S-B reach S-C1
        dependencies.append(
            {"dependency_id": "D5", "downstream_supplier_id": "S-C1", "upstream_supplier_id": "S-B", "dependency_type": "direct"}
        )

    if nested_failure:
        # S-U1 is upstream of S-A
        pass  # already in dependencies: S-U1 -> S-A

    materials = pd.DataFrame([
        {"material_id": "M-A", "material_name": "Part A", "used_in_product": "Prod 1"},
        {"material_id": "M-B", "material_name": "Part B", "used_in_product": "Prod 2"},
        {"material_id": "M-C1", "material_name": "Part C1", "used_in_product": "Prod 1;Prod 3"},
        {"material_id": "M-C2", "material_name": "Part C2", "used_in_product": "Prod 2"},
    ])

    factories = pd.DataFrame([{"factory_id": "F1", "factory_name": "Factory 1", "linked_warehouse_id": "W1"}])
    warehouses = pd.DataFrame([{"warehouse_id": "W1", "warehouse_name": "Warehouse 1", "linked_factory_id": "F1"}])
    inventory = pd.DataFrame([
        {"inventory_id": "I1", "location_id": "F1", "location_type": "factory", "material_id": "M-A", "quantity_on_hand": 100, "reorder_point": 50},
    ])
    customer_orders = pd.DataFrame([
        {"order_id": "O1", "customer_name": "Cust 1", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 10, "order_value_inr": 50000, "status": "confirmed"},
    ])
    transport_routes = pd.DataFrame(columns=["route_id", "origin_id", "destination_id"])

    return {
        "suppliers": suppliers,
        "supplier_materials": pd.DataFrame(mat_rows),
        "supplier_dependencies": pd.DataFrame(dependencies),
        "materials": materials,
        "factories": factories,
        "warehouses": warehouses,
        "inventory": inventory,
        "customer_orders": customer_orders,
        "transport_routes": transport_routes,
    }


# ---------------------------------------------------------------------------
# Test Suite: Stage 1
# ---------------------------------------------------------------------------

class TestMultiDisruptionStage1InputValidation(unittest.TestCase):
    """Verify input validation for simulate_multiple_supplier_disruption."""

    @classmethod
    def setUpClass(cls):
        cls.real_data = load_all_data(verbose=False)
        cls.real_graph = get_supply_chain_graph(cls.real_data)

    def test_none_supplier_ids_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption(None, data=self.real_data, graph=self.real_graph)
        self.assertIn("supplier_ids cannot be None", str(ctx.exception))

    def test_bare_string_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption("SUP-T2-01", data=self.real_data, graph=self.real_graph)
        self.assertIn("got string", str(ctx.exception))

    def test_non_collection_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption(12345, data=self.real_data, graph=self.real_graph)
        self.assertIn("supplier_ids must be a collection", str(ctx.exception))

    def test_empty_list_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption([], data=self.real_data, graph=self.real_graph)
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_single_supplier_id_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption(["SUP-T2-01"], data=self.real_data, graph=self.real_graph)
        self.assertIn("requires at least 2 distinct valid supplier IDs", str(ctx.exception))
        self.assertIn("simulate_supplier_disruption", str(ctx.exception))

    def test_duplicate_single_supplier_id_raises_value_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-01"], data=self.real_data, graph=self.real_graph)
        self.assertIn("requires at least 2 distinct valid supplier IDs", str(ctx.exception))

    def test_duplicates_with_multiple_distinct_suppliers_succeeds(self):
        report = simulate_multiple_supplier_disruption(
            ["SUP-T2-01", "SUP-T2-02", "SUP-T2-01"],
            data=self.real_data,
            graph=self.real_graph,
        )
        self.assertEqual(report["scenario"]["failed_supplier_ids"], ["SUP-T2-01", "SUP-T2-02"])
        self.assertEqual(report["scenario"]["failed_supplier_count"], 2)

    def test_whitespace_is_stripped_cleanly(self):
        report = simulate_multiple_supplier_disruption(
            ["  SUP-T2-01  ", " SUP-T2-02 "],
            data=self.real_data,
            graph=self.real_graph,
        )
        self.assertEqual(report["scenario"]["failed_supplier_ids"], ["SUP-T2-01", "SUP-T2-02"])

    def test_unknown_supplier_id_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption(["SUP-T2-01", "NON-EXISTENT-SUPPLIER"], data=self.real_data, graph=self.real_graph)
        self.assertIn("Unknown supplier id", str(ctx.exception))
        self.assertIn("NON-EXISTENT-SUPPLIER", str(ctx.exception))

    def test_non_supplier_node_raises_error(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption(["SUP-T2-01", "FAC-01"], data=self.real_data, graph=self.real_graph)
        self.assertIn("FAC-01 exists but is a factory, not a supplier", str(ctx.exception))

    def test_multiple_invalid_ids_reported_together(self):
        with self.assertRaises(ValueError) as ctx:
            simulate_multiple_supplier_disruption(["INVALID_A", "FAC-01", "INVALID_B"], data=self.real_data, graph=self.real_graph)
        err = str(ctx.exception)
        self.assertIn("INVALID_A", err)
        self.assertIn("FAC-01", err)
        self.assertIn("INVALID_B", err)

    def test_invalid_duration_days_raises_error(self):
        for bad_days in [0, -5, 3.5, "7", True, None]:
            with self.subTest(duration_days=bad_days):
                with self.assertRaises(ValueError):
                    simulate_multiple_supplier_disruption(
                        ["SUP-T2-01", "SUP-T2-02"],
                        duration_days=bad_days,
                        data=self.real_data,
                        graph=self.real_graph,
                    )

    def test_valid_duration_days(self):
        report = simulate_multiple_supplier_disruption(
            ["SUP-T2-01", "SUP-T2-02"],
            duration_days=14,
            data=self.real_data,
            graph=self.real_graph,
        )
        self.assertEqual(report["scenario"]["disruption_duration_days"], 14)


class TestMultiDisruptionStage1DownstreamAndDependencies(unittest.TestCase):
    """Verify combined downstream identification and overlapping dependency handling."""

    def test_independent_suppliers_have_disjoint_downstream_union(self):
        data = make_multi_test_data(shared_downstream=False)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        downstream_ids = [d["supplier_id"] for d in report["downstream_suppliers"]]
        self.assertEqual(downstream_ids, ["S-C1", "S-C2"])
        # Check attribution
        sc1 = next(d for d in report["downstream_suppliers"] if d["supplier_id"] == "S-C1")
        sc2 = next(d for d in report["downstream_suppliers"] if d["supplier_id"] == "S-C2")
        self.assertEqual(sc1["reached_by_failed_suppliers"], ["S-A"])
        self.assertEqual(sc2["reached_by_failed_suppliers"], ["S-B"])

    def test_overlapping_downstream_supplier_is_deduplicated_with_multiple_attributions(self):
        data = make_multi_test_data(shared_downstream=True)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        downstream_ids = [d["supplier_id"] for d in report["downstream_suppliers"]]
        # S-C1 must appear only ONCE
        self.assertEqual(downstream_ids, ["S-C1", "S-C2"])
        sc1 = next(d for d in report["downstream_suppliers"] if d["supplier_id"] == "S-C1")
        self.assertEqual(sc1["reached_by_failed_suppliers"], ["S-A", "S-B"])
        self.assertEqual(sorted(sc1["depends_directly_on_failed_suppliers"]), ["S-A", "S-B"])

    def test_nested_failed_supplier_is_removed_from_downstream_and_annotated(self):
        data = make_multi_test_data(nested_failure=True)
        graph = build_supply_chain_graph(data)
        # S-U1 is upstream of S-A; both fail
        report = simulate_multiple_supplier_disruption(["S-U1", "S-A"], data=data, graph=graph)

        failed_reported = [f["supplier_id"] for f in report["failed_suppliers"]]
        self.assertEqual(failed_reported, ["S-U1", "S-A"])

        # S-A is a failed supplier, so it MUST NOT be in downstream_suppliers
        downstream_ids = [d["supplier_id"] for d in report["downstream_suppliers"]]
        self.assertNotIn("S-A", downstream_ids)
        self.assertIn("S-C1", downstream_ids)

        # S-A should be annotated as downstream of S-U1
        sa_entry = next(f for f in report["failed_suppliers"] if f["supplier_id"] == "S-A")
        self.assertEqual(sa_entry["is_downstream_of_other_failed_suppliers"], ["S-U1"])
        self.assertEqual(report["nested_failed_suppliers"], {"S-A": ["S-U1"]})

    def test_real_dataset_shared_downstream_suppliers(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)
        # In real data, SUP-T3-04 and SUP-T3-05 both reach SUP-T1-05
        report = simulate_multiple_supplier_disruption(
            ["SUP-T3-04", "SUP-T3-05"],
            data=real_data,
            graph=real_graph,
        )
        downstream_ids = [d["supplier_id"] for d in report["downstream_suppliers"]]
        self.assertIn("SUP-T1-05", downstream_ids)
        self.assertEqual(downstream_ids.count("SUP-T1-05"), 1)

        t1_05 = next(d for d in report["downstream_suppliers"] if d["supplier_id"] == "SUP-T1-05")
        self.assertIn("SUP-T3-04", t1_05["reached_by_failed_suppliers"])
        self.assertIn("SUP-T3-05", t1_05["reached_by_failed_suppliers"])


class TestMultiDisruptionStage1DirectAndCascadingMaterials(unittest.TestCase):
    """Verify material identification and DIRECT vs POTENTIAL_CASCADING rules."""

    def test_direct_materials_union_without_duplicates(self):
        data = make_multi_test_data()
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        direct_mats = [m["material_id"] for m in report["direct_materials"]]
        self.assertEqual(direct_mats, ["M-A", "M-B"])
        for m in report["direct_materials"]:
            self.assertEqual(m["impact_type"], DIRECT)

    def test_shared_direct_material_is_deduplicated_and_attributes_both_suppliers(self):
        data = make_multi_test_data(shared_material=True)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        direct_mats = [m["material_id"] for m in report["direct_materials"]]
        self.assertEqual(direct_mats, ["M-A", "M-B"])

        ma_entry = next(m for m in report["direct_materials"] if m["material_id"] == "M-A")
        self.assertEqual(ma_entry["supplied_by_failed_suppliers"], ["S-A", "S-B"])
        self.assertEqual(ma_entry["impact_type"], DIRECT)

    def test_direct_beats_potential_cascading(self):
        data = make_multi_test_data()
        # S-C1 (downstream of S-A) also supplies M-A
        extra_row = pd.DataFrame([{"supplier_id": "S-C1", "material_id": "M-A", "is_backup": 0, "monthly_capacity_units": 100}])
        data["supplier_materials"] = pd.concat([data["supplier_materials"], extra_row], ignore_index=True)
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        # M-A must be DIRECT, NOT in cascading materials
        direct_mats = [m["material_id"] for m in report["direct_materials"]]
        cascading_mats = [m["material_id"] for m in report["potential_cascading_materials"]]
        self.assertIn("M-A", direct_mats)
        self.assertNotIn("M-A", cascading_mats)
        self.assertEqual(report["material_impact"]["M-A"], DIRECT)

    def test_unmapped_supplier_status_handling(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)

        # SUP-T3-02 has no supplier_materials row; SUP-T2-01 has supplier_materials rows
        report_partial = simulate_multiple_supplier_disruption(
            ["SUP-T2-01", "SUP-T3-02"],
            data=real_data,
            graph=real_graph,
        )
        self.assertEqual(report_partial["direct_materials_status"], PARTIAL)
        self.assertTrue(report_partial["exposure_may_be_understated"])
        self.assertIn("has no row in supplier_materials.csv", " ".join(report_partial["data_gaps"]))

        # Both Tier 3 unmapped suppliers (SUP-T3-02 and SUP-T3-03)
        report_unknown = simulate_multiple_supplier_disruption(
            ["SUP-T3-02", "SUP-T3-03"],
            data=real_data,
            graph=real_graph,
        )
        self.assertEqual(report_unknown["direct_materials_status"], UNKNOWN)
        self.assertTrue(report_unknown["exposure_may_be_understated"])

        # Both mapped suppliers
        report_known = simulate_multiple_supplier_disruption(
            ["SUP-T2-01", "SUP-T2-02"],
            data=real_data,
            graph=real_graph,
        )
        self.assertEqual(report_known["direct_materials_status"], KNOWN)
        self.assertFalse(report_known["exposure_may_be_understated"])


# ---------------------------------------------------------------------------
# Stage 2: Backup Reassessment Tests
# ---------------------------------------------------------------------------

def make_backup_test_data(
    candidate_capacity=150,
    primary_a_capacity=100,
    primary_b_capacity=100,
    shared_upstream=False,
    candidate_downstream=False,
    candidate_capacity_status="sufficient",
):
    """
    Synthetic supply chain focused on backup reassessment.
    
    Topology:
      S-A supplies M-A (capacity = primary_a_capacity)
      S-B supplies M-A (capacity = primary_b_capacity)
      S-BK supplies M-A (capacity = candidate_capacity, is_backup=1, capacity_status=candidate_capacity_status)
      S-U (Tier 3) -> S-A
    """
    suppliers = [
        {"supplier_id": "S-U", "supplier_name": "Upstream", "tier": 3, "capacity_status": "sufficient"},
        {"supplier_id": "S-A", "supplier_name": "Primary A", "tier": 2, "capacity_status": "sufficient"},
        {"supplier_id": "S-B", "supplier_name": "Primary B", "tier": 2, "capacity_status": "sufficient"},
        {"supplier_id": "S-BK", "supplier_name": "Backup Candidate", "tier": 2, "capacity_status": candidate_capacity_status},
    ]

    mat_rows = [
        {"supplier_id": "S-A", "material_id": "M-A", "is_backup": 0, "monthly_capacity_units": primary_a_capacity},
        {"supplier_id": "S-B", "material_id": "M-A", "is_backup": 0, "monthly_capacity_units": primary_b_capacity},
        {"supplier_id": "S-BK", "material_id": "M-A", "is_backup": 1, "monthly_capacity_units": candidate_capacity},
    ]

    deps = [
        {"dependency_id": "D1", "downstream_supplier_id": "S-A", "upstream_supplier_id": "S-U", "dependency_type": "direct"},
    ]
    if shared_upstream:
        deps.append({"dependency_id": "D2", "downstream_supplier_id": "S-BK", "upstream_supplier_id": "S-U", "dependency_type": "direct"})
    if candidate_downstream:
        deps.append({"dependency_id": "D3", "downstream_supplier_id": "S-BK", "upstream_supplier_id": "S-A", "dependency_type": "direct"})

    materials = pd.DataFrame([{"material_id": "M-A", "material_name": "Part A", "used_in_product": "Prod 1"}])
    factories = pd.DataFrame([{"factory_id": "F1", "factory_name": "Factory 1", "linked_warehouse_id": "W1"}])
    warehouses = pd.DataFrame([{"warehouse_id": "W1", "warehouse_name": "Warehouse 1", "linked_factory_id": "F1"}])
    inventory = pd.DataFrame([
        {"inventory_id": "I1", "location_id": "F1", "location_type": "factory", "material_id": "M-A", "quantity_on_hand": 100, "reorder_point": 50},
    ])
    customer_orders = pd.DataFrame([
        {"order_id": "O1", "customer_name": "Cust 1", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 10, "order_value_inr": 50000, "status": "confirmed"},
    ])
    transport_routes = pd.DataFrame(columns=["route_id", "origin_id", "destination_id"])

    return {
        "suppliers": pd.DataFrame(suppliers),
        "supplier_materials": pd.DataFrame(mat_rows),
        "supplier_dependencies": pd.DataFrame(deps),
        "materials": materials,
        "factories": factories,
        "warehouses": warehouses,
        "inventory": inventory,
        "customer_orders": customer_orders,
        "transport_routes": transport_routes,
    }


class TestMultiDisruptionStage2BackupReassessment(unittest.TestCase):
    """Verify combined backup reassessment, summed capacity, independence, and UNKNOWN handling."""

    def test_backup_works_individually_but_fails_under_combined_disruption(self):
        # S-A = 100, S-B = 100, S-BK = 150
        # S-BK can replace S-A (150 >= 100) or S-B (150 >= 100) individually
        # But for combined failure: summed required is 200 > 150 -> UNMITIGATED
        data = make_backup_test_data(candidate_capacity=150, primary_a_capacity=100, primary_b_capacity=100)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], UNMITIGATED)
        self.assertEqual(b_ma["summed_exposed_capacity_units"], 200)

        # Verify individual statuses are MITIGATED
        self.assertEqual(b_ma["individual_backup_statuses"], {"S-A": MITIGATED, "S-B": MITIGATED})

        cand = b_ma["candidates"][0]
        self.assertEqual(cand["candidate_id"], "S-BK")
        self.assertEqual(cand["verdict"], "NOT_GENUINE")
        self.assertEqual(cand["capacity_status"], "insufficient")
        self.assertIn("150 vs 200 units/month (75% of summed exposed capacity)", cand["capacity_note"])

    def test_sufficient_summed_capacity_gives_mitigated(self):
        # S-A = 100, S-B = 100, S-BK = 250 (>= 200)
        data = make_backup_test_data(candidate_capacity=250, primary_a_capacity=100, primary_b_capacity=100)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], MITIGATED)
        self.assertEqual(b_ma["summed_exposed_capacity_units"], 200)
        self.assertEqual(b_ma["individual_backup_statuses"], {"S-A": MITIGATED, "S-B": MITIGATED})

        cand = b_ma["candidates"][0]
        self.assertEqual(cand["verdict"], "GENUINE")
        self.assertEqual(cand["capacity_status"], "sufficient")
        self.assertIn("250 vs 200 units/month (125% of summed exposed capacity)", cand["capacity_note"])

    def test_insufficient_summed_capacity_gives_unmitigated(self):
        # S-A = 100, S-B = 100, S-BK = 80 (< 200)
        data = make_backup_test_data(candidate_capacity=80, primary_a_capacity=100, primary_b_capacity=100)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], UNMITIGATED)
        cand = b_ma["candidates"][0]
        self.assertEqual(cand["verdict"], "NOT_GENUINE")
        self.assertEqual(cand["capacity_status"], "insufficient")

    def test_missing_primary_capacity_treated_as_unknown_never_insufficient(self):
        # S-A has None capacity, S-B has 100, S-BK has 150
        data = make_backup_test_data(candidate_capacity=150, primary_a_capacity=None, primary_b_capacity=100)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], UNKNOWN)
        self.assertEqual(b_ma["summed_exposed_capacity_units"], UNKNOWN)

        cand = b_ma["candidates"][0]
        self.assertEqual(cand["verdict"], UNKNOWN)
        self.assertEqual(cand["capacity_status"], "unknown")
        self.assertIn("summed exposed capacity is unknown", cand["capacity_note"])

    def test_missing_candidate_capacity_treated_as_unknown_never_insufficient(self):
        # S-A = 100, S-B = 100, S-BK has None capacity
        data = make_backup_test_data(candidate_capacity=None, primary_a_capacity=100, primary_b_capacity=100)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], UNKNOWN)
        cand = b_ma["candidates"][0]
        self.assertEqual(cand["verdict"], UNKNOWN)
        self.assertEqual(cand["capacity_status"], "unknown")
        self.assertIn("candidate capacity missing", cand["capacity_note"])

    def test_shared_upstream_dependency_fails_independence(self):
        # S-BK has 300 capacity (>= 200), but shares S-U with S-A
        data = make_backup_test_data(candidate_capacity=300, primary_a_capacity=100, primary_b_capacity=100, shared_upstream=True)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], UNMITIGATED)

        cand = b_ma["candidates"][0]
        self.assertEqual(cand["verdict"], "NOT_GENUINE")
        self.assertFalse(cand["independent"])
        self.assertTrue(any("shares upstream supplier(s) with S-A: S-U" in r for r in cand["reasons"]))

    def test_failed_backup_supplier_is_excluded_from_candidates(self):
        # S-BK is a backup, but both S-A and S-BK fail simultaneously
        # S-A = 100, S-BK = 50 -> summed required = 150. S-B has 200 >= 150.
        data = make_backup_test_data(candidate_capacity=50, primary_a_capacity=100, primary_b_capacity=200)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-BK"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], MITIGATED)  # S-B is unaffected and has 200 capacity vs 150 summed
        self.assertEqual(b_ma["summed_exposed_capacity_units"], 150)
        # S-BK is a failed supplier, so it MUST NOT be in candidates!
        candidate_ids = [c["candidate_id"] for c in b_ma["candidates"]]
        self.assertNotIn("S-BK", candidate_ids)
        self.assertIn("S-B", candidate_ids)

    def test_downstream_backup_supplier_is_excluded_from_candidates(self):
        # S-BK is downstream of S-A (S-A -> S-BK)
        data = make_backup_test_data(candidate_capacity=300, primary_a_capacity=100, primary_b_capacity=100, candidate_downstream=True)
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["status"], UNMITIGATED)
        # S-BK is in downstream_suppliers, so it MUST NOT be in candidates
        self.assertEqual(len(b_ma["candidates"]), 0)
        self.assertIn("no unaffected alternative exists", b_ma["explanation"])

    def test_multiple_exposed_suppliers_sharing_one_material_summed(self):
        # 3 suppliers: S-A (100), S-B (150), S-C (50) all supply M-A -> Sum = 300
        data = make_backup_test_data(candidate_capacity=300, primary_a_capacity=100, primary_b_capacity=150)
        extra_supplier = pd.DataFrame([{"supplier_id": "S-C", "supplier_name": "Primary C", "tier": 2, "capacity_status": "sufficient"}])
        extra_mat = pd.DataFrame([{"supplier_id": "S-C", "material_id": "M-A", "is_backup": 0, "monthly_capacity_units": 50}])
        data["suppliers"] = pd.concat([data["suppliers"], extra_supplier], ignore_index=True)
        data["supplier_materials"] = pd.concat([data["supplier_materials"], extra_mat], ignore_index=True)
        graph = build_supply_chain_graph(data)

        # Failure of all three
        report = simulate_multiple_supplier_disruption(["S-A", "S-B", "S-C"], data=data, graph=graph)
        b_ma = next(b for b in report["backup_assessment"] if b["material_id"] == "M-A")
        self.assertEqual(b_ma["summed_exposed_capacity_units"], 300)
        self.assertEqual(b_ma["status"], MITIGATED)  # S-BK has 300 >= 300

    def test_real_dataset_backup_assessment_structure(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)
        report = simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-02"], data=real_data, graph=real_graph)

        self.assertGreater(len(report["backup_assessment"]), 0)
        for b in report["backup_assessment"]:
            self.assertIn("material_id", b)
            self.assertIn("status", b)
            self.assertIn(b["status"], [MITIGATED, UNMITIGATED, UNKNOWN])
            self.assertIn("summed_exposed_capacity_units", b)
            self.assertIn("candidates", b)
            self.assertIn("individual_backup_statuses", b)
            self.assertIn("SUP-T2-01", b["individual_backup_statuses"])
            self.assertIn("SUP-T2-02", b["individual_backup_statuses"])

        # Check summary counts
        summary = report["summary"]
        self.assertEqual(
            summary["backup_mitigated_count"] + summary["backup_unmitigated_count"] + summary["backup_unknown_count"],
            len(report["backup_assessment"]),
        )
        self.assertEqual(len(summary["backup_status_by_material"]), len(report["backup_assessment"]))


# ---------------------------------------------------------------------------
# Stage 3: Inventory, Factory, Warehouse, Route, and Customer Order Tests
# ---------------------------------------------------------------------------

class TestMultiDisruptionStage3DownstreamEntitiesAndOrders(unittest.TestCase):
    """Verify combined inventory, factories, warehouses, routes, and customer order impact analysis."""

    def test_inventory_identified_and_attributed(self):
        data = make_multi_test_data()
        # Add inventory for M-B
        extra_inv = pd.DataFrame([
            {"inventory_id": "I2", "location_id": "W1", "location_type": "warehouse", "material_id": "M-B",
             "quantity_on_hand": 200, "reorder_point": 100},
        ])
        data["inventory"] = pd.concat([data["inventory"], extra_inv], ignore_index=True)
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        inv_mats = [i["material_id"] for i in report["inventory"]]
        self.assertIn("M-A", inv_mats)
        self.assertIn("M-B", inv_mats)

        ma_inv = next(i for i in report["inventory"] if i["material_id"] == "M-A")
        mb_inv = next(i for i in report["inventory"] if i["material_id"] == "M-B")
        self.assertEqual(ma_inv["caused_by_failed_suppliers"], ["S-A"])
        self.assertEqual(mb_inv["caused_by_failed_suppliers"], ["S-B"])
        self.assertIn("pooled_all_locations", ma_inv)

    def test_inventory_missing_data_preserves_unknown(self):
        data = make_multi_test_data()
        # Missing quantity on hand
        data["inventory"] = pd.DataFrame([
            {"inventory_id": "I1", "location_id": "F1", "location_type": "factory", "material_id": "M-A",
             "quantity_on_hand": None, "reorder_point": 50},
        ])
        graph = build_supply_chain_graph(data)
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        ma_inv = next(i for i in report["inventory"] if i["material_id"] == "M-A")
        self.assertEqual(ma_inv["pooled_all_locations"]["status"], UNKNOWN)
        self.assertEqual(ma_inv["shortage_exposure"], UNKNOWN)

    def test_factories_and_warehouses_direct_beats_cascading(self):
        data = make_multi_test_data(shared_downstream=False)
        # F1 holds M-A (DIRECT from S-A)
        # F2 holds M-C1 (POTENTIAL_CASCADING from downstream S-C1)
        extra_fac = pd.DataFrame([{"factory_id": "F2", "factory_name": "Factory 2", "linked_warehouse_id": "W2"}])
        extra_wh = pd.DataFrame([{"warehouse_id": "W2", "warehouse_name": "Warehouse 2", "linked_factory_id": "F2"}])
        extra_inv = pd.DataFrame([
            {"inventory_id": "I2", "location_id": "F2", "location_type": "factory", "material_id": "M-C1",
             "quantity_on_hand": 100, "reorder_point": 50},
        ])
        data["factories"] = pd.concat([data["factories"], extra_fac], ignore_index=True)
        data["warehouses"] = pd.concat([data["warehouses"], extra_wh], ignore_index=True)
        data["inventory"] = pd.concat([data["inventory"], extra_inv], ignore_index=True)
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)

        f1 = next(f for f in report["factories"] if f["factory_id"] == "F1")
        f2 = next(f for f in report["factories"] if f["factory_id"] == "F2")
        self.assertEqual(f1["impact_type"], DIRECT)
        self.assertEqual(f1["evidence_level"], INVENTORY_LINK)
        self.assertIn("S-A", f1["caused_by_failed_suppliers"])

        self.assertEqual(f2["impact_type"], POTENTIAL_CASCADING)
        self.assertEqual(f2["evidence_level"], INVENTORY_LINK)

        # W1 is fed by F1 (which holds direct inventory) -> DIRECT via FACTORY_LINK_ONLY
        w1 = next(w for w in report["warehouses"] if w["warehouse_id"] == "W1")
        self.assertEqual(w1["impact_type"], DIRECT)
        self.assertEqual(w1["evidence_level"], FACTORY_LINK_ONLY)
        self.assertIn("S-A", w1["caused_by_failed_suppliers"])

    def test_transport_routes_status_and_evidence(self):
        data = make_multi_test_data()
        # Route R1 used by S-A; Route R2 connecting F1 to W1
        routes = pd.DataFrame([
            {"route_id": "R1", "origin_id": "S-A", "destination_id": "F1", "mode": "road", "transit_days": 2, "cargo": "MAT-01", "shared_supplier_ids": "S-A"},
            {"route_id": "R2", "origin_id": "F1", "destination_id": "W1", "mode": "road", "transit_days": 1, "cargo": "Finished Goods"},
        ])
        data["transport_routes"] = routes
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)
        self.assertGreater(len(report["transport_routes"]), 0)

        for r in report["transport_routes"]:
            self.assertEqual(r["status"], "POTENTIALLY_AFFECTED (route not assumed to have failed)")
            self.assertIn(r["evidence_level"], [SUPPLIER_ROUTE, LOCATION_LINK_ONLY])

        r1 = next(r for r in report["transport_routes"] if r["route_id"] == "R1")
        self.assertEqual(r1["evidence_level"], SUPPLIER_ROUTE)
        self.assertIn("S-A", r1["caused_by_failed_suppliers"])

    def test_customer_orders_deduplicated_and_priority_rule(self):
        data = make_multi_test_data()
        # O1 uses Prod 1 (uses M-A: DIRECT, and M-C1: cascading) -> DIRECT beats cascading
        # O2 uses Prod 2 (uses M-B: DIRECT) -> DIRECT
        # O3 has status "cancelled" -> must be EXCLUDED
        # O4 uses Prod 3 (uses M-C1: cascading only) -> POTENTIAL_CASCADING
        orders = pd.DataFrame([
            {"order_id": "O1", "customer_name": "Cust 1", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 10, "order_value_inr": 50000, "status": "confirmed"},
            {"order_id": "O2", "customer_name": "Cust 2", "warehouse_id": "W1", "product_name": "Prod 2", "quantity": 5, "order_value_inr": 30000, "status": "planned"},
            {"order_id": "O3", "customer_name": "Cust 3", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 2, "order_value_inr": 10000, "status": "cancelled"},
            {"order_id": "O4", "customer_name": "Cust 4", "warehouse_id": "W1", "product_name": "Prod 3", "quantity": 1, "order_value_inr": 15000, "status": "confirmed"},
        ])
        # Add warehouse inventory for M-A, M-B and M-C1 so orders are path-supported at warehouse level
        extra_inv = pd.DataFrame([
            {"inventory_id": "I1_w", "location_id": "W1", "location_type": "warehouse", "material_id": "M-A", "quantity_on_hand": 100, "reorder_point": 50},
            {"inventory_id": "I2", "location_id": "W1", "location_type": "warehouse", "material_id": "M-B", "quantity_on_hand": 100, "reorder_point": 50},
            {"inventory_id": "I3", "location_id": "W1", "location_type": "warehouse", "material_id": "M-C1", "quantity_on_hand": 100, "reorder_point": 50},
        ])
        data["customer_orders"] = orders
        data["inventory"] = pd.concat([data["inventory"], extra_inv], ignore_index=True)
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)
        head_orders = report["customer_orders"]["headline_path_supported"]["orders"]
        head_ids = [o["order_id"] for o in head_orders]

        # O1, O2, O4 included; O3 (cancelled) excluded
        self.assertIn("O1", head_ids)
        self.assertIn("O2", head_ids)
        self.assertIn("O4", head_ids)
        self.assertNotIn("O3", head_ids)

        # Check unique order count
        self.assertEqual(len(head_ids), len(set(head_ids)))

        # O1 caused by S-A; O2 caused by S-B
        o1 = next(o for o in head_orders if o["order_id"] == "O1")
        o2 = next(o for o in head_orders if o["order_id"] == "O2")
        o4 = next(o for o in head_orders if o["order_id"] == "O4")
        self.assertEqual(o1["impact_type"], DIRECT)
        self.assertIn("S-A", o1["caused_by_failed_suppliers"])
        self.assertEqual(o2["impact_type"], DIRECT)
        self.assertEqual(o2["caused_by_failed_suppliers"], ["S-B"])
        self.assertEqual(o4["impact_type"], POTENTIAL_CASCADING)

        # Total value exposure: 50,000 + 30,000 + 15,000 = 95,000
        self.assertEqual(report["customer_orders"]["headline_path_supported"]["potential_value_exposure_inr"], 95000)

    def test_financial_exposure_no_double_counting_and_unknown_handling(self):
        data = make_multi_test_data()
        # Order with None value
        orders = pd.DataFrame([
            {"order_id": "O1", "customer_name": "C1", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 1, "order_value_inr": None, "status": "confirmed"},
        ])
        data["customer_orders"] = orders
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)
        head = report["customer_orders"]["headline_path_supported"]
        self.assertEqual(head["potential_value_exposure_inr"], UNKNOWN)
        self.assertFalse(head["value_is_complete"])
        self.assertIn("O1", head["orders_with_unknown_value"])

    def test_real_dataset_multi_disruption_union_invariants(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)

        # Inspect pair SUP-T2-01 and SUP-T2-03
        r1 = simulate_supplier_disruption("SUP-T2-01", data=real_data, graph=real_graph)
        r2 = simulate_supplier_disruption("SUP-T2-03", data=real_data, graph=real_graph)
        combined = simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-03"], data=real_data, graph=real_graph)

        r1_head = r1["customer_orders"]["headline_path_supported"]
        r2_head = r2["customer_orders"]["headline_path_supported"]
        comb_head = combined["customer_orders"]["headline_path_supported"]

        # Combined must be union: 16 orders, INR 73,418,850 (not 27 orders or 124.9M sum!)
        self.assertEqual(comb_head["order_count"], 16)
        self.assertEqual(comb_head["potential_value_exposure_inr"], 73418850)

        # Invariants:
        # 1. max(r1, r2) <= combined <= r1 + r2
        self.assertGreaterEqual(comb_head["order_count"], max(r1_head["order_count"], r2_head["order_count"]))
        self.assertLessEqual(comb_head["order_count"], r1_head["order_count"] + r2_head["order_count"])

        self.assertGreaterEqual(comb_head["potential_value_exposure_inr"], max(r1_head["potential_value_exposure_inr"], r2_head["potential_value_exposure_inr"]))
        self.assertLessEqual(comb_head["potential_value_exposure_inr"], r1_head["potential_value_exposure_inr"] + r2_head["potential_value_exposure_inr"])

        # No duplicate orders
        order_ids = [o["order_id"] for o in comb_head["orders"]]
        self.assertEqual(len(order_ids), len(set(order_ids)))

        # Summary agrees with orders dict
        summary = combined["summary"]
        self.assertEqual(summary["headline_order_count"], comb_head["order_count"])
        self.assertEqual(summary["headline_potential_order_value_exposure_inr"], comb_head["potential_value_exposure_inr"])
        self.assertEqual(summary["factory_count"], len(combined["factories"]))
        self.assertEqual(summary["warehouse_count"], len(combined["warehouses"]))
        self.assertEqual(summary["route_count"], len(combined["transport_routes"]))


# ---------------------------------------------------------------------------
# Stage 4: Overlap Summary, Attribution, JSON Serialisability & Report Tests
# ---------------------------------------------------------------------------

class TestMultiDisruptionStage4FinalReportAndValidation(unittest.TestCase):
    """Verify Stage 4 overlap summary, attribution, JSON serialisability, and report formatter."""

    def test_overlap_summary_calculation_synthetic(self):
        data = make_multi_test_data()
        # S-A provides M-A (used in Prod 1)
        # S-B provides M-B (used in Prod 2 and Prod 1)
        data["materials"] = pd.DataFrame([
            {"material_id": "M-A", "material_name": "Part A", "used_in_product": "Prod 1"},
            {"material_id": "M-B", "material_name": "Part B", "used_in_product": "Prod 1;Prod 2"},
            {"material_id": "M-C1", "material_name": "Part C1", "used_in_product": "Prod 1"},
            {"material_id": "M-C2", "material_name": "Part C2", "used_in_product": "Prod 2"},
        ])
        # Add warehouse inventory for M-A and M-B so orders are path-supported at warehouse
        extra_inv = pd.DataFrame([
            {"inventory_id": "I1_w", "location_id": "W1", "location_type": "warehouse", "material_id": "M-A", "quantity_on_hand": 100, "reorder_point": 50},
            {"inventory_id": "I2_w", "location_id": "W1", "location_type": "warehouse", "material_id": "M-B", "quantity_on_hand": 100, "reorder_point": 50},
        ])
        data["inventory"] = pd.concat([data["inventory"], extra_inv], ignore_index=True)

        # Orders:
        # O1: Prod 1 (requires M-A and M-B) -> affected by BOTH S-A and S-B!
        # O2: Prod 2 (requires M-B) -> affected by S-B only
        orders = pd.DataFrame([
            {"order_id": "O1", "customer_name": "Cust 1", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 10, "order_value_inr": 50000, "status": "confirmed"},
            {"order_id": "O2", "customer_name": "Cust 2", "warehouse_id": "W1", "product_name": "Prod 2", "quantity": 5, "order_value_inr": 30000, "status": "confirmed"},
        ])
        data["customer_orders"] = orders
        graph = build_supply_chain_graph(data)

        # Individual S-A affects O1 (1 order, 50,000 INR)
        # Individual S-B affects O1 and O2 (2 orders, 80,000 INR)
        # Sum of individual = 3 orders, 130,000 INR
        # Combined unique = 2 orders (O1, O2), 80,000 INR
        # Overlap avoided = 1 order, 50,000 INR avoided!
        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)
        ov = report["overlap_summary"]

        self.assertFalse(ov["is_additive"])
        self.assertIn("NOT ADDITIVE", ov["non_additive_note"])
        self.assertEqual(ov["sum_of_individual_headline_order_counts"], 3)
        self.assertEqual(ov["sum_of_individual_headline_potential_value_exposure_inr"], 130000)
        self.assertEqual(ov["combined_unique_headline_order_count"], 2)
        self.assertEqual(ov["combined_unique_headline_potential_value_exposure_inr"], 80000)
        self.assertEqual(ov["order_count_overlap_avoided"], 1)
        self.assertEqual(ov["value_exposure_overlap_avoided_inr"], 50000)

        # Overlapping orders
        self.assertEqual(ov["overlapping_order_count"], 1)
        oo = ov["overlapping_orders"][0]
        self.assertEqual(oo["order_id"], "O1")
        self.assertEqual(oo["order_value_inr"], 50000)
        self.assertEqual(oo["affected_by_failed_suppliers"], ["S-A", "S-B"])

        # Summary sync
        self.assertEqual(report["summary"]["order_count_overlap_avoided"], 1)
        self.assertEqual(report["summary"]["value_exposure_overlap_avoided_inr"], 50000)

    def test_overlap_summary_on_real_dataset(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)
        report = simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-03"], data=real_data, graph=real_graph)
        ov = report["overlap_summary"]

        self.assertFalse(ov["is_additive"])
        self.assertEqual(ov["sum_of_individual_headline_order_counts"], 27)
        self.assertEqual(ov["combined_unique_headline_order_count"], 16)
        self.assertEqual(ov["order_count_overlap_avoided"], 11)

        self.assertEqual(ov["sum_of_individual_headline_potential_value_exposure_inr"], 124903350)
        self.assertEqual(ov["combined_unique_headline_potential_value_exposure_inr"], 73418850)
        self.assertEqual(ov["value_exposure_overlap_avoided_inr"], 51484500)

        self.assertEqual(len(ov["overlapping_orders"]), 11)
        for oo in ov["overlapping_orders"]:
            self.assertGreaterEqual(oo["supplier_count"], 2)
            self.assertIn("SUP-T2-01", oo["affected_by_failed_suppliers"])
            self.assertIn("SUP-T2-03", oo["affected_by_failed_suppliers"])

    def test_attribution_on_all_entities(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)
        report = simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-03"], data=real_data, graph=real_graph)

        # 1. Direct materials
        self.assertGreater(len(report["direct_materials"]), 0)
        for m in report["direct_materials"]:
            self.assertIn("caused_by_failed_suppliers", m)
            self.assertIsInstance(m["caused_by_failed_suppliers"], list)
            self.assertTrue(all(s in ["SUP-T2-01", "SUP-T2-03"] for s in m["caused_by_failed_suppliers"]))

        # 2. Downstream suppliers
        self.assertGreater(len(report["downstream_suppliers"]), 0)
        for d in report["downstream_suppliers"]:
            self.assertIn("caused_by_failed_suppliers", d)
            self.assertIsInstance(d["caused_by_failed_suppliers"], list)

        # 3. Potential cascading materials
        for m in report["potential_cascading_materials"]:
            self.assertIn("caused_by_failed_suppliers", m)
            self.assertIsInstance(m["caused_by_failed_suppliers"], list)

        # 4. Inventory
        self.assertGreater(len(report["inventory"]), 0)
        for inv in report["inventory"]:
            self.assertIn("caused_by_failed_suppliers", inv)
            self.assertIsInstance(inv["caused_by_failed_suppliers"], list)

        # 5. Factories
        self.assertGreater(len(report["factories"]), 0)
        for f in report["factories"]:
            self.assertIn("caused_by_failed_suppliers", f)
            self.assertIsInstance(f["caused_by_failed_suppliers"], list)

        # 6. Warehouses
        self.assertGreater(len(report["warehouses"]), 0)
        for w in report["warehouses"]:
            self.assertIn("caused_by_failed_suppliers", w)
            self.assertIsInstance(w["caused_by_failed_suppliers"], list)

        # 7. Transport routes
        self.assertGreater(len(report["transport_routes"]), 0)
        for r in report["transport_routes"]:
            self.assertIn("caused_by_failed_suppliers", r)
            self.assertIsInstance(r["caused_by_failed_suppliers"], list)

        # 8. Customer orders
        head_orders = report["customer_orders"]["headline_path_supported"]["orders"]
        self.assertGreater(len(head_orders), 0)
        for o in head_orders:
            self.assertIn("caused_by_failed_suppliers", o)
            self.assertIsInstance(o["caused_by_failed_suppliers"], list)

    def test_json_serialisability_synthetic_and_real(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)
        report = simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-03"], data=real_data, graph=real_graph)

        # Ensure json.dumps executes cleanly with default encoder
        dumped = json.dumps(report)
        self.assertIsInstance(dumped, str)
        self.assertGreater(len(dumped), 1000)

        # Ensure json.loads parses it back accurately
        loaded = json.loads(dumped)
        self.assertEqual(loaded["scenario"]["failed_supplier_count"], 2)
        self.assertEqual(loaded["summary"]["headline_order_count"], 16)

    def test_format_multi_disruption_report(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)
        report = simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-03"], data=real_data, graph=real_graph)

        formatted_text = format_multi_disruption_report(report)
        self.assertIsInstance(formatted_text, str)

        required_sections = [
            "MULTIPLE SUPPLIER DISRUPTION IMPACT REPORT",
            "OVERLAP SUMMARY (UNION VS INDIVIDUAL REPORTS)",
            "NOT ADDITIVE",
            "DIRECT MATERIALS",
            "DOWNSTREAM & POTENTIAL CASCADING IMPACTS",
            "COMBINED BACKUP ASSESSMENT",
            "INVENTORY IMPACT",
            "LOCATIONS & TRANSPORT ROUTES",
            "CUSTOMER ORDERS & FINANCIAL EXPOSURE",
            "NOT COMPUTED",
            "ASSUMPTIONS",
            "DATA GAPS",
        ]
        for section in required_sections:
            self.assertIn(section, formatted_text)

    def test_unknown_order_values_in_overlap_summary(self):
        data = make_multi_test_data()
        # Order with None value
        orders = pd.DataFrame([
            {"order_id": "O1", "customer_name": "C1", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 1, "order_value_inr": None, "status": "confirmed"},
        ])
        data["customer_orders"] = orders
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)
        ov = report["overlap_summary"]
        self.assertEqual(ov["sum_of_individual_headline_potential_value_exposure_inr"], UNKNOWN)
        self.assertEqual(ov["combined_unique_headline_potential_value_exposure_inr"], UNKNOWN)
        self.assertEqual(ov["value_exposure_overlap_avoided_inr"], UNKNOWN)

        # Formatter shouldn't crash on UNKNOWN currency
        formatted = format_multi_disruption_report(report)
        self.assertIn("UNKNOWN", formatted)

    def test_disjoint_suppliers_overlap_summary(self):
        data = make_multi_test_data()
        # S-A provides M-A (Prod 1) at W1
        # S-B provides M-B (Prod 2) at W2
        extra_fac = pd.DataFrame([{"factory_id": "F2", "factory_name": "Factory 2", "linked_warehouse_id": "W2"}])
        extra_wh = pd.DataFrame([{"warehouse_id": "W2", "warehouse_name": "Warehouse 2", "linked_factory_id": "F2"}])
        extra_inv = pd.DataFrame([
            {"inventory_id": "I1_w", "location_id": "W1", "location_type": "warehouse", "material_id": "M-A", "quantity_on_hand": 100, "reorder_point": 50},
            {"inventory_id": "I2_w", "location_id": "W2", "location_type": "warehouse", "material_id": "M-B", "quantity_on_hand": 100, "reorder_point": 50},
        ])
        orders = pd.DataFrame([
            {"order_id": "O1", "customer_name": "C1", "warehouse_id": "W1", "product_name": "Prod 1", "quantity": 1, "order_value_inr": 20000, "status": "confirmed"},
            {"order_id": "O2", "customer_name": "C2", "warehouse_id": "W2", "product_name": "Prod 2", "quantity": 1, "order_value_inr": 30000, "status": "confirmed"},
        ])
        data["factories"] = pd.concat([data["factories"], extra_fac], ignore_index=True)
        data["warehouses"] = pd.concat([data["warehouses"], extra_wh], ignore_index=True)
        data["inventory"] = extra_inv
        data["customer_orders"] = orders
        graph = build_supply_chain_graph(data)

        report = simulate_multiple_supplier_disruption(["S-A", "S-B"], data=data, graph=graph)
        ov = report["overlap_summary"]
        self.assertEqual(ov["sum_of_individual_headline_order_counts"], 2)
        self.assertEqual(ov["combined_unique_headline_order_count"], 2)
        self.assertEqual(ov["order_count_overlap_avoided"], 0)
        self.assertEqual(ov["value_exposure_overlap_avoided_inr"], 0)
        self.assertEqual(ov["overlapping_orders"], [])

    def test_three_supplier_real_dataset_disruption(self):
        real_data = load_all_data(verbose=False)
        real_graph = get_supply_chain_graph(real_data)
        report = simulate_multiple_supplier_disruption(["SUP-T2-01", "SUP-T2-02", "SUP-T2-03"], data=real_data, graph=real_graph)

        self.assertEqual(report["scenario"]["failed_supplier_count"], 3)
        ov = report["overlap_summary"]
        self.assertEqual(len(ov["individual_supplier_reports"]), 3)
        self.assertGreater(ov["order_count_overlap_avoided"], 0)
        self.assertGreater(ov["value_exposure_overlap_avoided_inr"], 0)

        # JSON dumps check
        dumped = json.dumps(report)
        self.assertIsInstance(dumped, str)

        # Format report check
        formatted = format_multi_disruption_report(report)
        self.assertIn("SUP-T2-01, SUP-T2-02, SUP-T2-03", formatted)


if __name__ == "__main__":
    unittest.main()



