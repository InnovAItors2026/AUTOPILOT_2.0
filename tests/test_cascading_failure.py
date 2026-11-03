"""
test_cascading_failure.py
-------------------------
AUTOPILOT 2.0 - Member 4: Cascading Failure Simulation & Recovery Plan Challenger.

Synthetic in-memory datasets only (same style as Members 2 and 3).
Real CSV files are used in one smoke test that checks schema, not answers.
"""

import copy
import json
import os
import sys
import unittest
from typing import Dict, List
from unittest.mock import patch

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.cascading_failure import (
    REASON_FAILED_SUPPLIER,
    REASON_ROUTE_FAILURE,
    REASON_UPSTREAM_FAILURE,
    challenge_recovery_plan,
    detect_shared_upstream_dependencies,
    invalidate_recovery_allocations,
    simulate_cascading_supplier_failures,
    simulate_route_failure,
    suppliers_using_route,
    transport_excluded_suppliers,
)
from src.recovery_optimisation import (
    STATUS_FEASIBLE,
    STATUS_NO_PLAN,
    STATUS_PARTIAL,
    UNKNOWN,
    optimise_recovery,
)
from src.supply_chain_graph import build_supply_chain_graph


# ---------------------------------------------------------------------------
# Synthetic builders
# ---------------------------------------------------------------------------

def _df(rows: List[Dict], cols: List[str]) -> pd.DataFrame:
    if rows:
        return pd.DataFrame(rows)
    return pd.DataFrame(columns=cols)


def make_data(
    suppliers=None,
    materials=None,
    supplier_materials=None,
    inventory=None,
    transport_routes=None,
    supplier_dependencies=None,
    factories=None,
    warehouses=None,
    customer_orders=None,
) -> Dict[str, pd.DataFrame]:
    return {
        "suppliers": _df(suppliers or [], [
            "supplier_id", "supplier_name", "tier", "city", "state", "country",
            "category", "monthly_capacity_units", "capacity_status",
            "lead_time_days", "quality_score", "primary_route_id",
        ]),
        "materials": _df(materials or [], [
            "material_id", "material_name", "category", "unit",
            "unit_cost_inr", "typical_lead_time_days", "used_in_product",
        ]),
        "supplier_materials": _df(supplier_materials or [], [
            "supplier_id", "material_id", "is_backup",
            "unit_cost_inr", "monthly_capacity_units", "lead_time_days", "moq_units",
        ]),
        "inventory": _df(inventory or [], [
            "inventory_id", "location_id", "location_type", "material_id",
            "quantity_on_hand", "reorder_point", "max_stock", "unit_cost_inr",
        ]),
        "transport_routes": _df(transport_routes or [], [
            "route_id", "origin_id", "origin_name", "origin_type",
            "destination_id", "destination_name", "destination_type",
            "mode", "distance_km", "transit_days", "cost_per_shipment_inr",
            "cargo", "shared_supplier_ids",
        ]),
        "supplier_dependencies": _df(supplier_dependencies or [], [
            "dependency_id", "downstream_supplier_id", "upstream_supplier_id",
            "material_id", "dependency_type", "notes",
        ]),
        "factories": _df(factories or [], [
            "factory_id", "factory_name", "city", "state", "country",
            "product_focus", "monthly_capacity_units", "linked_warehouse_id",
        ]),
        "warehouses": _df(warehouses or [], [
            "warehouse_id", "warehouse_name", "city", "state", "country",
            "capacity_units", "serves_region", "linked_factory_id",
        ]),
        "customer_orders": _df(customer_orders or [], [
            "order_id", "customer_name", "city", "state", "warehouse_id",
            "product_name", "quantity", "unit_price_inr", "order_value_inr",
            "order_date", "required_date", "status",
        ]),
    }


def supplier_row(sid, name, tier, route, capacity=5000, lead=8, quality=90, status="sufficient"):
    return {
        "supplier_id": sid, "supplier_name": name, "tier": tier,
        "city": "X", "state": "X", "country": "India", "category": "parts",
        "monthly_capacity_units": capacity, "capacity_status": status,
        "lead_time_days": lead, "quality_score": quality, "primary_route_id": route,
    }


def sm_row(sid, mid, is_backup, cost, cap, lead, moq=50):
    return {
        "supplier_id": sid, "material_id": mid, "is_backup": is_backup,
        "unit_cost_inr": cost, "monthly_capacity_units": cap,
        "lead_time_days": lead, "moq_units": moq,
    }


def route_row(rid, origin, dest, shared=""):
    return {
        "route_id": rid, "origin_id": origin, "origin_name": origin,
        "origin_type": "supplier", "destination_id": dest,
        "destination_name": dest, "destination_type": "factory",
        "mode": "road", "distance_km": 100, "transit_days": 2,
        "cost_per_shipment_inr": 1000, "cargo": "parts",
        "shared_supplier_ids": shared,
    }


def dep_row(did, downstream, upstream, mid="M1"):
    return {
        "dependency_id": did,
        "downstream_supplier_id": downstream,
        "upstream_supplier_id": upstream,
        "material_id": mid,
        "dependency_type": "direct",
        "notes": "",
    }


def chain_data(shared_upstream=True, second_backup=False):
    """
    S-T3 --> S-T2 --> S-PRIM (primary) and S-BACK (backup) for M1.
    Independent S-ALT also supplies M1 on its own route (optional second source).
    """
    suppliers = [
        supplier_row("S-T3", "Tier3", 3, "RTE-P"),
        supplier_row("S-T2", "Tier2", 2, "RTE-P"),
        supplier_row("S-PRIM", "Primary", 1, "RTE-P", capacity=4000, lead=10),
        supplier_row("S-BACK", "Backup", 1, "RTE-B", capacity=3000, lead=9),
    ]
    sm = [
        sm_row("S-PRIM", "M1", 0, 100, 4000, 10),
        sm_row("S-BACK", "M1", 1, 120, 3000, 9),
    ]
    deps = [
        dep_row("D1", "S-T2", "S-T3"),
        dep_row("D2", "S-PRIM", "S-T2"),
        dep_row("D3", "S-BACK", "S-T2"),
    ]
    if not shared_upstream:
        suppliers = [s for s in suppliers if s["supplier_id"] != "S-T3"]
        deps = [dep_row("D2", "S-PRIM", "S-T2")]

    if second_backup:
        suppliers.append(supplier_row("S-ALT", "Alt", 1, "RTE-A", capacity=5000, lead=12))
        sm.append(sm_row("S-ALT", "M1", 0, 130, 5000, 12))

    routes = [
        route_row("RTE-P", "S-PRIM", "FAC-01"),
        route_row("RTE-B", "S-BACK", "FAC-01"),
    ]
    if second_backup:
        routes.append(route_row("RTE-A", "S-ALT", "FAC-01"))

    return make_data(
        suppliers=suppliers,
        materials=[{
            "material_id": "M1", "material_name": "Part",
            "category": "mech", "unit": "pcs", "unit_cost_inr": 100,
            "typical_lead_time_days": 10, "used_in_product": "Prod",
        }],
        supplier_materials=sm,
        inventory=[{
            "inventory_id": "INV-1", "location_id": "FAC-01",
            "location_type": "factory", "material_id": "M1",
            "quantity_on_hand": 8000, "reorder_point": 100,
            "max_stock": 9000, "unit_cost_inr": 100,
        }],
        transport_routes=routes,
        supplier_dependencies=deps,
        factories=[{
            "factory_id": "FAC-01", "factory_name": "Factory",
            "city": "X", "state": "X", "country": "India",
            "product_focus": "Prod", "monthly_capacity_units": 10000,
            "linked_warehouse_id": "WH-01",
        }],
        warehouses=[{
            "warehouse_id": "WH-01", "warehouse_name": "WH",
            "city": "X", "state": "X", "country": "India",
            "capacity_units": 10000, "serves_region": "X",
            "linked_factory_id": "FAC-01",
        }],
        customer_orders=[{
            "order_id": "ORD-1", "customer_name": "Cust",
            "city": "X", "state": "X", "warehouse_id": "WH-01",
            "product_name": "Prod", "quantity": 10, "unit_price_inr": 50,
            "order_value_inr": 500, "order_date": "2026-01-01",
            "required_date": "2026-02-01", "status": "confirmed",
        }],
    )


def graph_of(data):
    return build_supply_chain_graph(data)


# ---------------------------------------------------------------------------
# Shared upstream
# ---------------------------------------------------------------------------

class TestSharedUpstreamDetection(unittest.TestCase):
    def test_shared_tier2_and_tier3(self):
        data = chain_data()
        g = graph_of(data)
        result = detect_shared_upstream_dependencies(g, ["S-PRIM", "S-BACK"])
        self.assertTrue(result["S-PRIM"]["in_graph"])
        self.assertIn("S-T2", result["S-PRIM"]["upstream_ids"])
        self.assertIn("S-T3", result["S-PRIM"]["upstream_ids"])
        self.assertEqual(result["S-PRIM"]["shared_with"]["S-BACK"], ["S-T2", "S-T3"])
        self.assertEqual(result["S-BACK"]["shared_with"]["S-PRIM"], ["S-T2", "S-T3"])

    def test_shared_tier2_dependency(self):
        data = chain_data()
        g = graph_of(data)
        result = detect_shared_upstream_dependencies(g, ["S-PRIM", "S-BACK"])
        self.assertIn("S-T2", result["S-PRIM"]["shared_with"]["S-BACK"])
        self.assertIn("S-T2", result["S-BACK"]["shared_with"]["S-PRIM"])

    def test_shared_tier3_dependency(self):
        data = chain_data()
        g = graph_of(data)
        result = detect_shared_upstream_dependencies(g, ["S-PRIM", "S-BACK"])
        self.assertIn("S-T3", result["S-PRIM"]["shared_with"]["S-BACK"])
        self.assertIn("S-T3", result["S-BACK"]["shared_with"]["S-PRIM"])
        self.assertIn("S-T3", result["S-PRIM"]["upstream_ids"])
        self.assertIn("S-T3", result["S-BACK"]["upstream_ids"])

    def test_direct_depends_on(self):
        data = chain_data()
        g = graph_of(data)
        result = detect_shared_upstream_dependencies(g, ["S-BACK", "S-T2"])
        self.assertIn("S-T2", result["S-BACK"]["depends_on"])

    def test_unknown_supplier_is_unknown_not_empty(self):
        data = chain_data()
        g = graph_of(data)
        result = detect_shared_upstream_dependencies(g, ["S-PRIM", "NO-SUCH"])
        self.assertEqual(result["NO-SUCH"]["upstream_ids"], UNKNOWN)
        self.assertFalse(result["NO-SUCH"]["in_graph"])
        self.assertEqual(result["NO-SUCH"]["depends_on"], UNKNOWN)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

class TestRouteFailure(unittest.TestCase):
    def test_suppliers_using_route(self):
        data = chain_data()
        g = graph_of(data)
        users = suppliers_using_route(g, "RTE-B")
        self.assertIn("S-BACK", users)
        self.assertNotIn("S-PRIM", users)

    def test_unknown_route(self):
        data = chain_data()
        g = graph_of(data)
        self.assertEqual(suppliers_using_route(g, "RTE-MISSING"), [])
        report = simulate_route_failure("RTE-MISSING", data=data, graph=g)
        self.assertEqual(report["status"], UNKNOWN)
        self.assertEqual(report["exposed_suppliers"], [])

    def test_empty_route_id(self):
        data = chain_data()
        g = graph_of(data)
        report = simulate_route_failure("", data=data, graph=g)
        self.assertEqual(report["status"], UNKNOWN)

    def test_route_failure_exposes_users_not_shutdown(self):
        data = chain_data()
        g = graph_of(data)
        report = simulate_route_failure("RTE-B", data=data, graph=g)
        self.assertEqual(report["status"], "ROUTE_FAILED")
        self.assertIn("S-BACK", report["exposed_suppliers"])
        self.assertIn("supplier", report["meaning_of_results"].lower())

    def test_transport_excluded_only_when_all_routes_failed(self):
        data = chain_data()
        g = graph_of(data)
        only_b = transport_excluded_suppliers(g, ["RTE-B"])
        self.assertIn("S-BACK", only_b["excluded_supplier_ids"])
        self.assertNotIn("S-PRIM", only_b["excluded_supplier_ids"])
        unknown = transport_excluded_suppliers(g, ["RTE-MISSING"])
        self.assertEqual(unknown["excluded_supplier_ids"], [])
        self.assertIn("RTE-MISSING", unknown["unknown_route_ids"])


# ---------------------------------------------------------------------------
# Member 2 dispatch
# ---------------------------------------------------------------------------

class TestCascadingSupplierSimulation(unittest.TestCase):
    def test_single_dispatches_to_phase1(self):
        data = chain_data()
        g = graph_of(data)
        result = simulate_cascading_supplier_failures(["S-T2"], data=data, graph=g)
        self.assertEqual(result["status"], "SIMULATED")
        self.assertEqual(result["valid_supplier_ids"], ["S-T2"])
        report = result["member2_report"]
        self.assertEqual(report["scenario"]["failed_supplier_id"], "S-T2")
        self.assertIn("S-PRIM", [r["supplier_id"] for r in report["downstream_suppliers"]])

    def test_multiple_dispatches_to_phase2(self):
        data = chain_data()
        g = graph_of(data)
        result = simulate_cascading_supplier_failures(
            ["S-T2", "S-T3"], data=data, graph=g
        )
        self.assertEqual(result["status"], "SIMULATED")
        report = result["member2_report"]
        self.assertEqual(report["scenario"]["failed_supplier_ids"], ["S-T2", "S-T3"])

    def test_unknown_supplier_not_sent_to_member2(self):
        data = chain_data()
        g = graph_of(data)
        result = simulate_cascading_supplier_failures(
            ["NOPE"], data=data, graph=g
        )
        self.assertEqual(result["status"], UNKNOWN)
        self.assertIsNone(result["member2_report"])
        self.assertEqual(result["unknown_supplier_ids"], ["NOPE"])

    def test_mix_valid_and_unknown(self):
        data = chain_data()
        g = graph_of(data)
        result = simulate_cascading_supplier_failures(
            ["S-PRIM", "GHOST"], data=data, graph=g
        )
        self.assertEqual(result["valid_supplier_ids"], ["S-PRIM"])
        self.assertEqual(result["unknown_supplier_ids"], ["GHOST"])
        self.assertEqual(
            result["member2_report"]["scenario"]["failed_supplier_id"], "S-PRIM"
        )


# ---------------------------------------------------------------------------
# Allocation invalidation
# ---------------------------------------------------------------------------

def _mini_plan(selected, required=1000, allocated=None, status=STATUS_FEASIBLE, mid="M1"):
    if allocated is None:
        allocated = sum(s.get("allocated_quantity", 0) for s in selected)
    unmet = UNKNOWN
    if isinstance(required, (int, float)) and isinstance(allocated, (int, float)):
        unmet = max(required - allocated, 0)
    return {
        "material_id": mid,
        "required_quantity": required,
        "allocated_quantity": allocated,
        "unmet_quantity": unmet,
        "status": status,
        "selected_suppliers": selected,
    }


class TestInvalidateAllocations(unittest.TestCase):
    def test_drops_failed_supplier_and_recomputes_unmet(self):
        plan = _mini_plan([
            {"supplier_id": "S-BACK", "allocated_quantity": 1000, "reachable_routes": []},
        ])
        original = copy.deepcopy(plan)
        out = invalidate_recovery_allocations(
            plan, additional_failed_supplier_ids=["S-BACK"]
        )
        self.assertEqual(plan, original)
        self.assertEqual(out["plan"]["selected_suppliers"], [])
        self.assertEqual(out["plan"]["allocated_quantity"], 0)
        self.assertEqual(out["plan"]["unmet_quantity"], 1000)
        self.assertEqual(out["plan"]["status"], STATUS_NO_PLAN)
        self.assertEqual(out["invalidated_allocations"][0]["reason_codes"], [REASON_FAILED_SUPPLIER])

    def test_drops_allocation_when_upstream_fails(self):
        data = chain_data()
        g = graph_of(data)
        plan = _mini_plan([
            {
                "supplier_id": "S-BACK",
                "allocated_quantity": 1000,
                "shared_upstreams": ["S-T2"],
                "reachable_routes": [{"route_id": "RTE-B"}],
            },
        ])
        out = invalidate_recovery_allocations(
            plan, additional_failed_supplier_ids=["S-T2"], graph=g
        )
        self.assertEqual(out["plan"]["selected_suppliers"], [])
        self.assertIn(REASON_UPSTREAM_FAILURE, out["invalidated_allocations"][0]["reason_codes"])

    def test_route_failure_all_routes_gone(self):
        plan = _mini_plan([
            {
                "supplier_id": "S-BACK",
                "allocated_quantity": 400,
                "reachable_routes": [{"route_id": "RTE-B"}],
            },
            {
                "supplier_id": "S-ALT",
                "allocated_quantity": 600,
                "reachable_routes": [{"route_id": "RTE-A"}],
            },
        ])
        out = invalidate_recovery_allocations(
            plan, failed_route_ids=["RTE-B"]
        )
        kept = [s["supplier_id"] for s in out["plan"]["selected_suppliers"]]
        self.assertEqual(kept, ["S-ALT"])
        self.assertEqual(out["plan"]["allocated_quantity"], 600)
        self.assertEqual(out["plan"]["unmet_quantity"], 400)
        self.assertEqual(out["plan"]["status"], STATUS_PARTIAL)
        self.assertIn(REASON_ROUTE_FAILURE, out["invalidated_allocations"][0]["reason_codes"])

    def test_keeps_allocation_if_another_route_remains(self):
        plan = _mini_plan([
            {
                "supplier_id": "S-BACK",
                "allocated_quantity": 1000,
                "reachable_routes": [
                    {"route_id": "RTE-B"},
                    {"route_id": "RTE-X"},
                ],
            },
        ])
        out = invalidate_recovery_allocations(plan, failed_route_ids=["RTE-B"])
        self.assertEqual(len(out["plan"]["selected_suppliers"]), 1)
        remaining = [
            r["route_id"] for r in out["plan"]["selected_suppliers"][0]["reachable_routes"]
        ]
        self.assertEqual(remaining, ["RTE-X"])
        self.assertEqual(out["invalidated_allocations"], [])

    def test_unknown_allocation_quantity_stays_unknown(self):
        plan = _mini_plan([
            {"supplier_id": "S-KEEP", "allocated_quantity": UNKNOWN, "reachable_routes": []},
        ], allocated=UNKNOWN, status=UNKNOWN)
        out = invalidate_recovery_allocations(plan)
        self.assertEqual(out["plan"]["allocated_quantity"], UNKNOWN)
        self.assertEqual(out["plan"]["unmet_quantity"], UNKNOWN)


# ---------------------------------------------------------------------------
# Full challenger + re-optimisation
# ---------------------------------------------------------------------------

class TestChallengeRecoveryPlan(unittest.TestCase):
    def test_backup_failure_reoptimises_to_alternative(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        rec = original["recommended_plan"]
        self.assertEqual(rec["status"], STATUS_FEASIBLE)
        selected = [s["supplier_id"] for s in rec["selected_suppliers"]]
        self.assertIn("S-BACK", selected)

        snapshot = copy.deepcopy(original)
        node_count = g.number_of_nodes()
        edge_count = g.number_of_edges()

        challenged = challenge_recovery_plan(
            original_plan=original,
            additional_failed_supplier_ids=["S-BACK"],
            data=data,
            graph=g,
        )

        self.assertEqual(original, snapshot)
        self.assertEqual(g.number_of_nodes(), node_count)
        self.assertEqual(g.number_of_edges(), edge_count)

        revised = challenged["revised_plan"]["recommended_plan"]
        new_ids = [s["supplier_id"] for s in revised["selected_suppliers"]]
        self.assertNotIn("S-BACK", new_ids)
        self.assertIn("S-ALT", new_ids)
        self.assertEqual(revised["status"], STATUS_FEASIBLE)
        self.assertEqual(challenged["comparison"]["suppliers_removed"], ["S-BACK"])
        self.assertIn("S-ALT", challenged["comparison"]["suppliers_added"])
        self.assertIn("S-BACK", challenged["combined_failed_supplier_ids"])
        self.assertIn("S-PRIM", challenged["combined_failed_supplier_ids"])

    def test_shared_upstream_failure_invalidates_backup(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        challenged = challenge_recovery_plan(
            original_plan=original,
            additional_failed_supplier_ids=["S-T2"],
            data=data,
            graph=g,
        )
        self.assertIn("S-T2", challenged["shared_upstream_dependencies"]["S-BACK"]["depends_on"])
        invalidated_ids = [
            row["supplier_id"] for row in challenged["invalidated_allocations"]
        ]
        self.assertIn("S-BACK", invalidated_ids)
        revised_ids = [
            s["supplier_id"]
            for s in challenged["revised_plan"]["recommended_plan"]["selected_suppliers"]
        ]
        self.assertNotIn("S-BACK", revised_ids)
        self.assertIn("S-ALT", revised_ids)

    def test_simultaneous_extra_failures_leave_no_plan(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        challenged = challenge_recovery_plan(
            original_plan=original,
            additional_failed_supplier_ids=["S-BACK", "S-ALT"],
            data=data,
            graph=g,
        )
        self.assertIn(
            challenged["revised_plan"]["recommended_plan"]["status"],
            (STATUS_NO_PLAN, STATUS_PARTIAL),
        )
        self.assertEqual(
            challenged["revised_plan"]["recommended_plan"]["allocated_quantity"], 0
        )
        self.assertEqual(challenged["comparison"]["unmet_quantity"], 1000)
        self.assertEqual(challenged["comparison"]["remaining_demand"], 1000)

    def test_route_failure_excludes_backup_transport(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        challenged = challenge_recovery_plan(
            original_plan=original,
            failed_route_ids=["RTE-B"],
            data=data,
            graph=g,
        )
        self.assertIn("S-BACK", challenged["transport_excluded_supplier_ids"])
        revised_ids = [
            s["supplier_id"]
            for s in challenged["revised_plan"]["recommended_plan"]["selected_suppliers"]
        ]
        self.assertNotIn("S-BACK", revised_ids)
        self.assertTrue(
            any("TRANSPORT EXCLUSION" in w for w in challenged["dependency_warnings"])
        )

    def test_unknown_additional_supplier_does_not_crash(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        challenged = challenge_recovery_plan(
            original_plan=original,
            additional_failed_supplier_ids=["NOT-A-SUPPLIER"],
            data=data,
            graph=g,
        )
        self.assertTrue(any("UNKNOWN" in gap for gap in challenged["data_gaps"]))
        self.assertNotIn("NOT-A-SUPPLIER", challenged["combined_failed_supplier_ids"])
        self.assertEqual(
            challenged["revised_plan"]["recommended_plan"]["status"],
            original["recommended_plan"]["status"],
        )

    def test_result_is_json_serialisable(self):
        data = chain_data()
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=500,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        challenged = challenge_recovery_plan(
            original_plan=original,
            additional_failed_supplier_ids=["S-T2"],
            data=data,
            graph=g,
        )
        dumped = json.dumps(challenged)
        self.assertIsInstance(dumped, str)
        loaded = json.loads(dumped)
        self.assertIn("comparison", loaded)
        self.assertIn("revised_plan", loaded)

    def test_accepts_single_plan_dict(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            original_supplier_id="S-PRIM",
            data=data,
            graph=g,
        )
        plan_only = copy.deepcopy(original["recommended_plan"])
        plan_only["failed_supplier_ids"] = original["failed_supplier_ids"]
        plan_only["original_supplier_id"] = original["original_supplier_id"]
        challenged = challenge_recovery_plan(
            original_plan=plan_only,
            additional_failed_supplier_ids=["S-BACK"],
            data=data,
            graph=g,
        )
        self.assertIn("recommended_plan", challenged["revised_plan"])

    def test_invalid_original_plan(self):
        data = chain_data()
        g = graph_of(data)
        result = challenge_recovery_plan(
            original_plan=None, data=data, graph=g
        )
        self.assertEqual(result.get("error"), "Invalid original_plan")

    def test_reoptimisation_calls_member3_real_optimiser(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            original_supplier_id="S-PRIM",
            destination_ids=["FAC-01"],
            data=data,
            graph=g,
        )
        custom_weights = {
            "material_ok": 0.30,
            "feasibility": 0.20,
            "delivery_time": 0.20,
            "unit_cost": 0.15,
            "independence": 0.10,
            "transport": 0.05,
        }

        with patch(
            "src.cascading_failure.optimise_recovery",
            wraps=optimise_recovery,
        ) as mocked:
            challenged = challenge_recovery_plan(
                original_plan=original,
                additional_failed_supplier_ids=["S-BACK"],
                data=data,
                graph=g,
                weights=custom_weights,
                destination_ids=["FAC-01"],
            )

        mocked.assert_called_once()
        kwargs = mocked.call_args.kwargs
        self.assertEqual(kwargs["material_id"], "M1")
        self.assertEqual(kwargs["required_quantity"], 1000)
        self.assertEqual(set(kwargs["failed_supplier_ids"]), {"S-PRIM", "S-BACK"})
        self.assertEqual(kwargs["original_supplier_id"], "S-PRIM")
        self.assertEqual(kwargs["destination_ids"], ["FAC-01"])
        self.assertEqual(kwargs["weights"], custom_weights)
        self.assertIs(kwargs["data"], data)
        self.assertIs(kwargs["graph"], g)
        self.assertIn("S-ALT", [
            s["supplier_id"]
            for s in challenged["revised_plan"]["recommended_plan"]["selected_suppliers"]
        ])

    def test_destination_ids_forwarded_from_original_plan(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        original["destination_ids"] = ["FAC-01"]

        with patch(
            "src.cascading_failure.optimise_recovery",
            wraps=optimise_recovery,
        ) as mocked:
            challenged = challenge_recovery_plan(
                original_plan=original,
                additional_failed_supplier_ids=["S-BACK"],
                data=data,
                graph=g,
            )

        self.assertEqual(mocked.call_args.kwargs["destination_ids"], ["FAC-01"])
        self.assertEqual(challenged["destination_ids"], ["FAC-01"])


class TestImmutability(unittest.TestCase):
    def test_original_plan_and_graph_unchanged(self):
        data = chain_data(second_backup=True)
        g = graph_of(data)
        original = optimise_recovery(
            material_id="M1",
            required_quantity=1000,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        plan_snapshot = copy.deepcopy(original)
        nodes_before = set(g.nodes)
        edges_before = set(g.edges)
        supplier_rows = data["suppliers"].copy(deep=True)

        challenge_recovery_plan(
            original_plan=original,
            additional_failed_supplier_ids=["S-BACK"],
            failed_route_ids=["RTE-B"],
            data=data,
            graph=g,
        )

        self.assertEqual(original, plan_snapshot)
        self.assertEqual(set(g.nodes), nodes_before)
        self.assertEqual(set(g.edges), edges_before)
        pd.testing.assert_frame_equal(data["suppliers"], supplier_rows)


class TestRealDatasetSmoke(unittest.TestCase):
    """Schema-only: do not assert dataset-specific supplier or quantity answers."""

    def test_challenge_output_keys_on_loaded_data(self):
        from src.data_loader import load_all_data
        from src.supply_chain_graph import get_supply_chain_graph

        data = load_all_data(verbose=False)
        graph = get_supply_chain_graph(data)
        materials = list(data["supplier_materials"]["material_id"].dropna().unique())
        self.assertTrue(materials)
        material_id = str(materials[0])
        listed = data["supplier_materials"]
        listed = listed[listed["material_id"].astype(str) == material_id]
        failed = [str(listed.iloc[0]["supplier_id"])]
        original = optimise_recovery(
            material_id=material_id,
            required_quantity=100.0,
            failed_supplier_ids=failed,
            data=data,
            graph=graph,
        )
        extra = []
        rec = original.get("recommended_plan") or {}
        for row in rec.get("selected_suppliers") or []:
            extra.extend(row.get("shared_upstreams") or [])
        challenged = challenge_recovery_plan(
            original_plan=original,
            additional_failed_supplier_ids=extra[:1],
            data=data,
            graph=graph,
        )
        for key in (
            "original_plan",
            "revised_plan",
            "comparison",
            "invalidated_allocations",
            "combined_failed_supplier_ids",
            "dependency_warnings",
            "data_gaps",
        ):
            self.assertIn(key, challenged)
        json.dumps(challenged)
        cmp_ = challenged["comparison"]
        for key in (
            "original_status", "revised_status",
            "remaining_demand", "unmet_quantity", "feasibility_changed",
        ):
            self.assertIn(key, cmp_)


if __name__ == "__main__":
    unittest.main()
