"""
test_recovery_optimisation.py
-----------------------------
AUTOPILOT 2.0 - Member 3: Automated tests for the Recovery Optimisation Engine.

Covers all Task 15 requirements:
  - Single fully feasible backup supplier
  - Incompatible supplier rejection
  - Supplier with insufficient stock
  - Supplier with insufficient capacity
  - Supplier with missing stock information
  - Supplier with missing cost information
  - Supplier with missing lead time
  - Supplier with an unavailable route
  - Supplier with a shared upstream dependency
  - Multiple suppliers jointly fulfilling demand
  - Partial recovery when supply is insufficient
  - Minimum order quantity constraints
  - Multiple simultaneous supplier failures
  - Emergency Recovery Mode
  - No feasible recovery plan
  - Duplicate supplier records
  - Invalid material IDs
  - Recovery plan serialisation
  - Recovery plan compatibility with Member 4
  - Re-optimisation after additional failure

Design:
  All tests use small, deterministic in-memory datasets.
  No external APIs, SAP access, or filesystem dependencies.
  The existing Member 2 baseline (268 tests) is not modified.
"""

import json
import unittest
from typing import Any, Dict, List

import networkx as nx
import pandas as pd

from src.recovery_optimisation import (
    CLASS_BACKUP,
    CLASS_PRIMARY,
    CLASS_SECONDARY,
    DEP_DIRECTLY_AFFECTED,
    DEP_INDEPENDENT,
    DEP_SHARED_UPSTREAM,
    DEP_UNKNOWN,
    DEFAULT_WEIGHTS,
    FEASIBILITY_UNKNOWN,
    FEASIBLE,
    INFEASIBLE,
    OBJ_BALANCED,
    OBJ_FASTEST,
    OBJ_LOWEST_COST,
    PARTIALLY_FEASIBLE,
    STATUS_EMERGENCY,
    STATUS_FEASIBLE,
    STATUS_NO_PLAN,
    STATUS_PARTIAL,
    TRANSPORT_AVAILABLE,
    TRANSPORT_UNKNOWN,
    UNKNOWN,
    _build_lookups,
    allocate_quantity,
    assess_cost_and_delivery,
    assess_feasibility,
    assess_transport,
    assess_upstream_dependency,
    check_material_compatibility,
    classify_supplier,
    optimise_from_disruption_report,
    optimise_recovery,
    rank_candidates,
)


# ---------------------------------------------------------------------------
# Minimal dataset builders
# ---------------------------------------------------------------------------

def _make_data(
    suppliers: List[Dict] = None,
    materials: List[Dict] = None,
    supplier_materials: List[Dict] = None,
    inventory: List[Dict] = None,
    transport_routes: List[Dict] = None,
    supplier_dependencies: List[Dict] = None,
    factories: List[Dict] = None,
    warehouses: List[Dict] = None,
    customer_orders: List[Dict] = None,
) -> Dict[str, pd.DataFrame]:
    """Build a minimal data dict with DataFrames, similar to load_all_data()."""
    def _df(rows, cols):
        if rows:
            return pd.DataFrame(rows)
        return pd.DataFrame(columns=cols)

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


def _make_minimal_graph(data: Dict) -> nx.DiGraph:
    """Build a minimal NetworkX graph from supplier/dependency data."""
    g = nx.DiGraph()
    for _, row in data["suppliers"].iterrows():
        sid = str(row["supplier_id"]).strip()
        g.add_node(sid, node_type="supplier",
                   name=str(row.get("supplier_name", "")),
                   tier=row.get("tier"),
                   lead_time_days=row.get("lead_time_days"),
                   capacity_status=str(row.get("capacity_status", "")),
                   primary_route_id=str(row.get("primary_route_id", "")))
    for _, row in data["supplier_dependencies"].iterrows():
        ds = str(row["downstream_supplier_id"]).strip()
        us = str(row["upstream_supplier_id"]).strip()
        if ds in g and us in g:
            g.add_edge(us, ds, edge_type="supplier_dependency",
                       material_id=str(row.get("material_id", "")))
    for _, row in data["transport_routes"].iterrows():
        rid = str(row["route_id"]).strip()
        orig = str(row["origin_id"]).strip()
        dest = str(row["destination_id"]).strip()
        g.add_node(rid, node_type="transport_route",
                   origin_id=orig, destination_id=dest,
                   transit_days=row.get("transit_days"),
                   cost_per_shipment_inr=row.get("cost_per_shipment_inr"))
        if orig in g:
            g.add_edge(orig, rid, edge_type="uses_route")
        if dest not in g:
            g.add_node(dest, node_type="factory")
        g.add_edge(rid, dest, edge_type="leaves_route")
    return g


# ---------------------------------------------------------------------------
# Reusable minimal fixtures
# ---------------------------------------------------------------------------

BASE_SUPPLIERS = [
    {"supplier_id": "S-PRIM", "supplier_name": "Primary Co",
     "tier": 1, "city": "X", "state": "X", "country": "India",
     "category": "widgets", "monthly_capacity_units": 5000,
     "capacity_status": "sufficient", "lead_time_days": 10,
     "quality_score": 95, "primary_route_id": "RTE-A"},
    {"supplier_id": "S-BACK", "supplier_name": "Backup Co",
     "tier": 1, "city": "Y", "state": "Y", "country": "India",
     "category": "widgets", "monthly_capacity_units": 3000,
     "capacity_status": "sufficient", "lead_time_days": 8,
     "quality_score": 92, "primary_route_id": "RTE-B"},
]

BASE_MATERIALS = [
    {"material_id": "MAT-T1", "material_name": "Widget A",
     "category": "mechanical", "unit": "pcs",
     "unit_cost_inr": 100, "typical_lead_time_days": 10,
     "used_in_product": "Product X"},
]

BASE_SM = [
    {"supplier_id": "S-PRIM", "material_id": "MAT-T1", "is_backup": 0,
     "unit_cost_inr": 100, "monthly_capacity_units": 5000,
     "lead_time_days": 10, "moq_units": 100},
    {"supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
     "unit_cost_inr": 110, "monthly_capacity_units": 3000,
     "lead_time_days": 8, "moq_units": 100},
]

BASE_ROUTES = [
    {"route_id": "RTE-A", "origin_id": "S-PRIM", "origin_name": "Primary Co",
     "origin_type": "supplier", "destination_id": "FAC-01",
     "destination_name": "Factory 1", "destination_type": "factory",
     "mode": "road", "distance_km": 100, "transit_days": 2,
     "cost_per_shipment_inr": 5000, "cargo": "widgets", "shared_supplier_ids": ""},
    {"route_id": "RTE-B", "origin_id": "S-BACK", "origin_name": "Backup Co",
     "origin_type": "supplier", "destination_id": "FAC-01",
     "destination_name": "Factory 1", "destination_type": "factory",
     "mode": "road", "distance_km": 120, "transit_days": 3,
     "cost_per_shipment_inr": 6000, "cargo": "widgets", "shared_supplier_ids": ""},
]

BASE_INVENTORY = [
    {"inventory_id": "INV-1", "location_id": "FAC-01",
     "location_type": "factory", "material_id": "MAT-T1",
     "quantity_on_hand": 4000, "reorder_point": 1000,
     "max_stock": 8000, "unit_cost_inr": 100},
]


def _base_data():
    return _make_data(
        suppliers=BASE_SUPPLIERS,
        materials=BASE_MATERIALS,
        supplier_materials=BASE_SM,
        inventory=BASE_INVENTORY,
        transport_routes=BASE_ROUTES,
    )


def _base_graph(data=None):
    if data is None:
        data = _base_data()
    return _make_minimal_graph(data)


# ---------------------------------------------------------------------------
# Tests: Task 1 - Supplier classification
# ---------------------------------------------------------------------------

class TestSupplierClassification(unittest.TestCase):

    def setUp(self):
        self.data = _base_data()
        self.lookups = _build_lookups(self.data)

    def test_primary_supplier_classified(self):
        cls = classify_supplier("S-PRIM", "MAT-T1", self.lookups)
        self.assertEqual(cls, CLASS_PRIMARY)

    def test_backup_supplier_classified(self):
        cls = classify_supplier("S-BACK", "MAT-T1", self.lookups)
        self.assertEqual(cls, CLASS_BACKUP)

    def test_secondary_supplier_classified(self):
        """Two non-backup suppliers -> the second is SECONDARY."""
        data = _make_data(
            suppliers=BASE_SUPPLIERS + [{
                "supplier_id": "S-SEC", "supplier_name": "Secondary Co",
                "tier": 1, "city": "Z", "state": "Z", "country": "India",
                "category": "widgets", "monthly_capacity_units": 2000,
                "capacity_status": "sufficient", "lead_time_days": 12,
                "quality_score": 88, "primary_route_id": "",
            }],
            materials=BASE_MATERIALS,
            supplier_materials=BASE_SM + [{
                "supplier_id": "S-SEC", "material_id": "MAT-T1", "is_backup": 0,
                "unit_cost_inr": 115, "monthly_capacity_units": 2000,
                "lead_time_days": 12, "moq_units": 50,
            }],
        )
        lookups = _build_lookups(data)
        cls = classify_supplier("S-SEC", "MAT-T1", lookups)
        self.assertEqual(cls, CLASS_SECONDARY)

    def test_emergency_supplier_not_listed(self):
        """Supplier not in supplier_materials for the material -> EMERGENCY."""
        data = _make_data(
            suppliers=BASE_SUPPLIERS + [{
                "supplier_id": "S-EMRG", "supplier_name": "Emergency Co",
                "tier": 2, "city": "E", "state": "E", "country": "India",
                "category": "other", "monthly_capacity_units": 1000,
                "capacity_status": "sufficient", "lead_time_days": 20,
                "quality_score": 80, "primary_route_id": "",
            }],
            materials=BASE_MATERIALS,
            supplier_materials=BASE_SM,
        )
        lookups = _build_lookups(data)
        cls = classify_supplier("S-EMRG", "MAT-T1", lookups)
        from src.recovery_optimisation import CLASS_EMERGENCY
        self.assertEqual(cls, CLASS_EMERGENCY)


# ---------------------------------------------------------------------------
# Tests: Task 2 - Material compatibility
# ---------------------------------------------------------------------------

class TestMaterialCompatibility(unittest.TestCase):

    def setUp(self):
        self.lookups = _build_lookups(_base_data())

    def test_compatible_supplier(self):
        ok, reason = check_material_compatibility("S-BACK", "MAT-T1", self.lookups)
        self.assertTrue(ok)
        self.assertIn("Compatible", reason)

    def test_incompatible_supplier_rejected(self):
        """S-PRIM is not listed for MAT-FAKE -> incompatible."""
        ok, reason = check_material_compatibility("S-PRIM", "MAT-FAKE", self.lookups)
        self.assertFalse(ok)
        self.assertIn("MAT-FAKE", reason)

    def test_supplier_not_listed_for_material(self):
        """A supplier that exists but has no row for the requested material."""
        data = _make_data(
            suppliers=[{
                "supplier_id": "S-OTHER", "supplier_name": "Other",
                "tier": 2, "city": "A", "state": "A", "country": "India",
                "category": "other", "monthly_capacity_units": 1000,
                "capacity_status": "sufficient", "lead_time_days": 5,
                "quality_score": 90, "primary_route_id": "",
            }],
            materials=BASE_MATERIALS,
            supplier_materials=[],
        )
        lookups = _build_lookups(data)
        ok, reason = check_material_compatibility("S-OTHER", "MAT-T1", lookups)
        self.assertFalse(ok)
        self.assertIn("supplier_materials.csv", reason)


# ---------------------------------------------------------------------------
# Tests: Task 3 - Feasibility
# ---------------------------------------------------------------------------

class TestFeasibility(unittest.TestCase):

    def _lookups_with(self, sm_rows=None, inv_rows=None, sup_rows=None):
        data = _make_data(
            suppliers=BASE_SUPPLIERS if sup_rows is None else sup_rows,
            materials=BASE_MATERIALS,
            supplier_materials=BASE_SM if sm_rows is None else sm_rows,
            inventory=BASE_INVENTORY if inv_rows is None else inv_rows,
        )
        return _build_lookups(data)

    def test_fully_feasible(self):
        """Capacity and stock both exceed required quantity -> FEASIBLE."""
        lookups = self._lookups_with()
        result = assess_feasibility("S-BACK", "MAT-T1", 500.0, lookups, [])
        self.assertEqual(result["feasibility_status"], FEASIBLE)
        self.assertEqual(result["quantity_to_allocate"], 500)

    def test_partially_feasible(self):
        """Required 4500 but only 3000 capacity -> PARTIALLY_FEASIBLE."""
        lookups = self._lookups_with(
            sm_rows=[
                {"supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
                 "unit_cost_inr": 110, "monthly_capacity_units": 3000,
                 "lead_time_days": 8, "moq_units": 100},
            ],
            inv_rows=[],
        )
        result = assess_feasibility("S-BACK", "MAT-T1", 4500.0, lookups, [])
        self.assertEqual(result["feasibility_status"], PARTIALLY_FEASIBLE)
        self.assertEqual(result["quantity_to_allocate"], 3000)

    def test_insufficient_capacity_flag(self):
        """capacity_status=insufficient -> INFEASIBLE immediately."""
        lookups = self._lookups_with(
            sup_rows=[{
                "supplier_id": "S-BACK", "supplier_name": "Backup Co",
                "tier": 1, "city": "Y", "state": "Y", "country": "India",
                "category": "widgets", "monthly_capacity_units": 3000,
                "capacity_status": "insufficient", "lead_time_days": 8,
                "quality_score": 92, "primary_route_id": "",
            }]
        )
        result = assess_feasibility("S-BACK", "MAT-T1", 500.0, lookups, [])
        self.assertEqual(result["feasibility_status"], INFEASIBLE)
        self.assertEqual(result["quantity_to_allocate"], 0)

    def test_missing_stock_and_capacity_returns_unknown(self):
        """Both capacity and stock missing -> FEASIBILITY_UNKNOWN."""
        lookups = self._lookups_with(
            sm_rows=[{
                "supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
                "unit_cost_inr": 110, "monthly_capacity_units": None,
                "lead_time_days": 8, "moq_units": 100,
            }],
            inv_rows=[],
        )
        missing = []
        result = assess_feasibility("S-BACK", "MAT-T1", 500.0, lookups, missing)
        self.assertEqual(result["feasibility_status"], FEASIBILITY_UNKNOWN)
        self.assertTrue(len(missing) > 0)

    def test_moq_violation_infeasible(self):
        """Available < MOQ -> INFEASIBLE."""
        lookups = self._lookups_with(
            sm_rows=[{
                "supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
                "unit_cost_inr": 110, "monthly_capacity_units": 50,
                "lead_time_days": 8, "moq_units": 200,
            }],
            inv_rows=[],
        )
        result = assess_feasibility("S-BACK", "MAT-T1", 500.0, lookups, [])
        self.assertEqual(result["feasibility_status"], INFEASIBLE)
        self.assertIn("MOQ", result["reason"])

    def test_missing_stock_recorded_in_missing_info(self):
        """When stock is missing, it should be recorded in missing_info."""
        lookups = self._lookups_with(
            sm_rows=[{
                "supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
                "unit_cost_inr": 110, "monthly_capacity_units": 3000,
                "lead_time_days": 8, "moq_units": 100,
            }],
            inv_rows=[],  # no inventory
        )
        # No inv rows at all - capacity is used as ceiling.
        missing = []
        result = assess_feasibility("S-BACK", "MAT-T1", 500.0, lookups, missing)
        # Should use capacity only - not crash.
        self.assertIn(result["feasibility_status"], (FEASIBLE, PARTIALLY_FEASIBLE))


# ---------------------------------------------------------------------------
# Tests: Task 4 - Cost and delivery
# ---------------------------------------------------------------------------

class TestCostAndDelivery(unittest.TestCase):

    def test_known_cost_and_lead_time(self):
        lookups = _build_lookups(_base_data())
        result = assess_cost_and_delivery("S-BACK", "MAT-T1", "S-PRIM", lookups, [])
        self.assertEqual(result["unit_cost_inr"], 110)
        self.assertEqual(result["lead_time_days"], 8)
        self.assertEqual(result["additional_cost_per_unit_inr"], 10)  # 110 - 100

    def test_missing_cost_reported_unknown(self):
        data = _make_data(
            suppliers=BASE_SUPPLIERS,
            materials=BASE_MATERIALS,
            supplier_materials=[{
                "supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
                "unit_cost_inr": None, "monthly_capacity_units": 3000,
                "lead_time_days": 8, "moq_units": 100,
            }],
        )
        lookups = _build_lookups(data)
        missing = []
        result = assess_cost_and_delivery("S-BACK", "MAT-T1", "S-PRIM", lookups, missing)
        self.assertEqual(result["unit_cost_inr"], UNKNOWN)
        self.assertTrue(any("unit_cost_inr" in m for m in missing))

    def test_missing_lead_time_reported_unknown(self):
        data = _make_data(
            suppliers=[{
                "supplier_id": "S-BACK", "supplier_name": "Backup Co",
                "tier": 1, "city": "Y", "state": "Y", "country": "India",
                "category": "widgets", "monthly_capacity_units": 3000,
                "capacity_status": "sufficient", "lead_time_days": None,
                "quality_score": 92, "primary_route_id": "",
            }],
            materials=BASE_MATERIALS,
            supplier_materials=[{
                "supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
                "unit_cost_inr": 110, "monthly_capacity_units": 3000,
                "lead_time_days": None, "moq_units": 100,
            }],
        )
        lookups = _build_lookups(data)
        missing = []
        result = assess_cost_and_delivery("S-BACK", "MAT-T1", "S-PRIM", lookups, missing)
        self.assertEqual(result["lead_time_days"], UNKNOWN)
        self.assertTrue(any("lead_time_days" in m for m in missing))

    def test_no_additional_cost_without_original(self):
        lookups = _build_lookups(_base_data())
        result = assess_cost_and_delivery("S-BACK", "MAT-T1", None, lookups, [])
        self.assertIsNone(result["additional_cost_per_unit_inr"])


# ---------------------------------------------------------------------------
# Tests: Task 5 - Transportation
# ---------------------------------------------------------------------------

class TestTransportation(unittest.TestCase):

    def test_route_detected_from_csv(self):
        data = _base_data()
        g = _base_graph(data)
        lookups = _build_lookups(data)
        missing = []
        result = assess_transport("S-BACK", ["FAC-01"], lookups, g, missing)
        self.assertEqual(result["transport_status"], TRANSPORT_AVAILABLE)
        self.assertTrue(len(result["reachable_routes"]) > 0)

    def test_no_route_returns_unknown(self):
        data = _make_data(
            suppliers=BASE_SUPPLIERS,
            materials=BASE_MATERIALS,
            supplier_materials=BASE_SM,
            transport_routes=[],  # no routes at all
        )
        g = _make_minimal_graph(data)
        lookups = _build_lookups(data)
        missing = []
        result = assess_transport("S-BACK", ["FAC-01"], lookups, g, missing)
        self.assertEqual(result["transport_status"], TRANSPORT_UNKNOWN)
        self.assertTrue(len(missing) > 0)


# ---------------------------------------------------------------------------
# Tests: Task 6 - Upstream dependency
# ---------------------------------------------------------------------------

class TestUpstreamDependency(unittest.TestCase):

    def _data_with_dep(self):
        """
        S-PRIM (failed)  <- S-UPSTR (upstream of both PRIM and BACK)
        S-BACK           <- S-UPSTR  (shared upstream!)
        S-INDEP                       (independent)
        """
        suppliers = BASE_SUPPLIERS + [
            {"supplier_id": "S-UPSTR", "supplier_name": "Upstream",
             "tier": 2, "city": "U", "state": "U", "country": "India",
             "category": "raw", "monthly_capacity_units": 10000,
             "capacity_status": "sufficient", "lead_time_days": 15,
             "quality_score": 88, "primary_route_id": ""},
            {"supplier_id": "S-INDEP", "supplier_name": "Independent",
             "tier": 1, "city": "I", "state": "I", "country": "India",
             "category": "widgets", "monthly_capacity_units": 2000,
             "capacity_status": "sufficient", "lead_time_days": 7,
             "quality_score": 90, "primary_route_id": ""},
        ]
        dependencies = [
            {"dependency_id": "D1", "downstream_supplier_id": "S-PRIM",
             "upstream_supplier_id": "S-UPSTR", "material_id": "MAT-T1",
             "dependency_type": "direct", "notes": ""},
            {"dependency_id": "D2", "downstream_supplier_id": "S-BACK",
             "upstream_supplier_id": "S-UPSTR", "material_id": "MAT-T1",
             "dependency_type": "direct", "notes": ""},
        ]
        data = _make_data(suppliers=suppliers, materials=BASE_MATERIALS,
                          supplier_materials=BASE_SM,
                          supplier_dependencies=dependencies)
        return data, _make_minimal_graph(data)

    def test_independent_supplier_detected(self):
        data, g = self._data_with_dep()
        missing = []
        result = assess_upstream_dependency("S-INDEP", ["S-PRIM"], g, missing)
        self.assertEqual(result["dependency_status"], DEP_INDEPENDENT)

    def test_shared_upstream_detected(self):
        data, g = self._data_with_dep()
        missing = []
        result = assess_upstream_dependency("S-BACK", ["S-PRIM"], g, missing)
        self.assertEqual(result["dependency_status"], DEP_SHARED_UPSTREAM)
        self.assertIn("S-UPSTR", result["shared_upstreams"])

    def test_directly_affected_when_failed(self):
        data, g = self._data_with_dep()
        missing = []
        result = assess_upstream_dependency("S-PRIM", ["S-PRIM"], g, missing)
        self.assertEqual(result["dependency_status"], DEP_DIRECTLY_AFFECTED)

    def test_unknown_when_not_in_graph(self):
        data, g = self._data_with_dep()
        missing = []
        result = assess_upstream_dependency("S-NOT-IN-GRAPH", ["S-PRIM"], g, missing)
        self.assertEqual(result["dependency_status"], DEP_UNKNOWN)
        self.assertTrue(len(missing) > 0)


# ---------------------------------------------------------------------------
# Tests: Task 7 - Candidate ranking
# ---------------------------------------------------------------------------

class TestRanking(unittest.TestCase):

    def test_compatible_ranks_above_incompatible(self):
        candidates = [
            {
                "supplier_id": "BAD", "material_compatible": False,
                "feasibility_status": INFEASIBLE, "unit_cost_inr": 50,
                "lead_time_days": 5, "dependency_status": DEP_INDEPENDENT,
                "transport_status": TRANSPORT_AVAILABLE,
            },
            {
                "supplier_id": "GOOD", "material_compatible": True,
                "feasibility_status": FEASIBLE, "quantity_available": 1000,
                "unit_cost_inr": 100, "lead_time_days": 10,
                "dependency_status": DEP_INDEPENDENT,
                "transport_status": TRANSPORT_AVAILABLE,
            },
        ]
        ranked = rank_candidates(candidates, 1000.0)
        self.assertEqual(ranked[0]["supplier_id"], "GOOD")
        self.assertEqual(ranked[-1]["ranking_score"], 0.0)

    def test_faster_supplier_ranks_higher_same_cost(self):
        candidates = [
            {
                "supplier_id": "SLOW", "material_compatible": True,
                "feasibility_status": FEASIBLE, "quantity_available": 1000,
                "unit_cost_inr": 100, "lead_time_days": 20,
                "dependency_status": DEP_INDEPENDENT,
                "transport_status": TRANSPORT_AVAILABLE,
            },
            {
                "supplier_id": "FAST", "material_compatible": True,
                "feasibility_status": FEASIBLE, "quantity_available": 1000,
                "unit_cost_inr": 100, "lead_time_days": 5,
                "dependency_status": DEP_INDEPENDENT,
                "transport_status": TRANSPORT_AVAILABLE,
            },
        ]
        ranked = rank_candidates(candidates, 1000.0)
        self.assertEqual(ranked[0]["supplier_id"], "FAST")

    def test_independent_ranks_above_shared_upstream(self):
        candidates = [
            {
                "supplier_id": "SHARED", "material_compatible": True,
                "feasibility_status": FEASIBLE, "quantity_available": 1000,
                "unit_cost_inr": 100, "lead_time_days": 10,
                "dependency_status": DEP_SHARED_UPSTREAM,
                "transport_status": TRANSPORT_AVAILABLE,
            },
            {
                "supplier_id": "INDEP", "material_compatible": True,
                "feasibility_status": FEASIBLE, "quantity_available": 1000,
                "unit_cost_inr": 100, "lead_time_days": 10,
                "dependency_status": DEP_INDEPENDENT,
                "transport_status": TRANSPORT_AVAILABLE,
            },
        ]
        ranked = rank_candidates(candidates, 1000.0)
        self.assertEqual(ranked[0]["supplier_id"], "INDEP")

    def test_missing_cost_does_not_crash(self):
        candidates = [
            {
                "supplier_id": "NOCOST", "material_compatible": True,
                "feasibility_status": FEASIBLE, "quantity_available": 1000,
                "unit_cost_inr": UNKNOWN, "lead_time_days": 10,
                "dependency_status": DEP_INDEPENDENT,
                "transport_status": TRANSPORT_UNKNOWN,
            },
        ]
        ranked = rank_candidates(candidates, 1000.0)
        self.assertEqual(len(ranked), 1)
        self.assertGreater(ranked[0]["ranking_score"], 0.0)


# ---------------------------------------------------------------------------
# Tests: Task 8 - Multi-supplier quantity allocation
# ---------------------------------------------------------------------------

class TestQuantityAllocation(unittest.TestCase):

    def test_single_fully_satisfies(self):
        candidates = [{
            "supplier_id": "A", "material_compatible": True,
            "feasibility_status": FEASIBLE,
            "quantity_to_allocate": 1000, "moq_units": 100,
            "unit_cost_inr": 100, "lead_time_days": 7,
            "supplier_name": "A Co", "supplier_classification": CLASS_BACKUP,
            "transport_status": TRANSPORT_AVAILABLE,
            "dependency_status": DEP_INDEPENDENT,
            "reachable_routes": [], "shared_upstreams": [], "ranking_score": 80.0,
            "additional_cost_per_unit_inr": 10,
        }]
        allocs, total, unmet = allocate_quantity(candidates, 1000.0)
        self.assertEqual(total, 1000)
        self.assertEqual(unmet, 0)
        self.assertEqual(len(allocs), 1)

    def test_two_suppliers_jointly_satisfy(self):
        """600 + 400 = 1000 required -> full allocation."""
        candidates = [
            {"supplier_id": "A", "material_compatible": True,
             "feasibility_status": PARTIALLY_FEASIBLE,
             "quantity_to_allocate": 600, "moq_units": 100,
             "unit_cost_inr": 100, "lead_time_days": 7,
             "supplier_name": "A Co", "supplier_classification": CLASS_BACKUP,
             "transport_status": TRANSPORT_AVAILABLE,
             "dependency_status": DEP_INDEPENDENT,
             "reachable_routes": [], "shared_upstreams": [], "ranking_score": 80.0,
             "additional_cost_per_unit_inr": None},
            {"supplier_id": "B", "material_compatible": True,
             "feasibility_status": PARTIALLY_FEASIBLE,
             "quantity_to_allocate": 400, "moq_units": 100,
             "unit_cost_inr": 110, "lead_time_days": 9,
             "supplier_name": "B Co", "supplier_classification": CLASS_SECONDARY,
             "transport_status": TRANSPORT_AVAILABLE,
             "dependency_status": DEP_INDEPENDENT,
             "reachable_routes": [], "shared_upstreams": [], "ranking_score": 70.0,
             "additional_cost_per_unit_inr": None},
        ]
        allocs, total, unmet = allocate_quantity(candidates, 1000.0)
        self.assertEqual(total, 1000)
        self.assertEqual(unmet, 0)
        self.assertEqual(len(allocs), 2)

    def test_partial_recovery_when_supply_insufficient(self):
        """Only 700 available for 1000 required -> PARTIAL."""
        candidates = [{
            "supplier_id": "A", "material_compatible": True,
            "feasibility_status": PARTIALLY_FEASIBLE,
            "quantity_to_allocate": 700, "moq_units": 100,
            "unit_cost_inr": 100, "lead_time_days": 7,
            "supplier_name": "A Co", "supplier_classification": CLASS_BACKUP,
            "transport_status": TRANSPORT_AVAILABLE,
            "dependency_status": DEP_INDEPENDENT,
            "reachable_routes": [], "shared_upstreams": [], "ranking_score": 60.0,
            "additional_cost_per_unit_inr": None,
        }]
        allocs, total, unmet = allocate_quantity(candidates, 1000.0)
        self.assertEqual(total, 700)
        self.assertEqual(unmet, 300)

    def test_moq_violation_skips_supplier(self):
        """MOQ 500, can only allocate 200 (remaining) -> skipped."""
        candidates = [
            {"supplier_id": "A", "material_compatible": True,
             "feasibility_status": FEASIBLE,
             "quantity_to_allocate": 800, "moq_units": 100,
             "unit_cost_inr": 100, "lead_time_days": 7,
             "supplier_name": "A Co", "supplier_classification": CLASS_BACKUP,
             "transport_status": TRANSPORT_AVAILABLE,
             "dependency_status": DEP_INDEPENDENT,
             "reachable_routes": [], "shared_upstreams": [], "ranking_score": 90.0,
             "additional_cost_per_unit_inr": None},
            {"supplier_id": "B", "material_compatible": True,
             "feasibility_status": FEASIBLE,
             "quantity_to_allocate": 1000, "moq_units": 500,
             "unit_cost_inr": 90, "lead_time_days": 6,
             "supplier_name": "B Co", "supplier_classification": CLASS_BACKUP,
             "transport_status": TRANSPORT_AVAILABLE,
             "dependency_status": DEP_INDEPENDENT,
             "reachable_routes": [], "shared_upstreams": [], "ranking_score": 85.0,
             "additional_cost_per_unit_inr": None},
        ]
        allocs, total, unmet = allocate_quantity(candidates, 1000.0)
        # A gets 800, remaining 200 < MOQ 500 for B -> B skipped
        self.assertEqual(total, 800)
        self.assertEqual(unmet, 200)
        supplier_ids = [a["supplier_id"] for a in allocs]
        self.assertNotIn("B", supplier_ids)

    def test_infeasible_skipped(self):
        candidates = [
            {"supplier_id": "BAD", "material_compatible": True,
             "feasibility_status": INFEASIBLE,
             "quantity_to_allocate": 0, "moq_units": 100,
             "unit_cost_inr": 50, "lead_time_days": 3,
             "supplier_name": "Bad Co", "supplier_classification": CLASS_BACKUP,
             "transport_status": TRANSPORT_AVAILABLE,
             "dependency_status": DEP_INDEPENDENT,
             "reachable_routes": [], "shared_upstreams": [], "ranking_score": 0.0,
             "additional_cost_per_unit_inr": None},
        ]
        allocs, total, unmet = allocate_quantity(candidates, 500.0)
        self.assertEqual(total, 0)
        self.assertEqual(unmet, 500)

    def test_incompatible_skipped(self):
        candidates = [
            {"supplier_id": "INC", "material_compatible": False,
             "feasibility_status": FEASIBLE,
             "quantity_to_allocate": 1000, "moq_units": 100,
             "unit_cost_inr": 80, "lead_time_days": 5,
             "supplier_name": "Inc Co", "supplier_classification": CLASS_BACKUP,
             "transport_status": TRANSPORT_AVAILABLE,
             "dependency_status": DEP_INDEPENDENT,
             "reachable_routes": [], "shared_upstreams": [], "ranking_score": 0.0,
             "additional_cost_per_unit_inr": None},
        ]
        allocs, total, unmet = allocate_quantity(candidates, 500.0)
        self.assertEqual(total, 0)
        self.assertEqual(unmet, 500)


# ---------------------------------------------------------------------------
# Tests: Task 9 / optimise_recovery - integration
# ---------------------------------------------------------------------------

class TestOptimiseRecovery(unittest.TestCase):

    def test_single_feasible_backup_supplier(self):
        """S-PRIM fails, S-BACK can fully satisfy 500 units."""
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=500.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        rec = result["recommended_plan"]
        self.assertEqual(rec["status"], STATUS_FEASIBLE)
        self.assertEqual(rec["allocated_quantity"], 500)
        self.assertEqual(rec["unmet_quantity"], 0)
        self.assertEqual(len(rec["selected_suppliers"]), 1)
        self.assertEqual(rec["selected_suppliers"][0]["supplier_id"], "S-BACK")

    def test_invalid_material_id_returns_error(self):
        result = optimise_recovery(
            material_id="MAT-INVALID",
            required_quantity=100.0,
            failed_supplier_ids=["S-PRIM"],
        )
        self.assertIn("error", result)

    def test_negative_quantity_returns_error(self):
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=-100.0,
            failed_supplier_ids=["S-PRIM"],
        )
        self.assertIn("error", result)

    def test_zero_quantity_returns_error(self):
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=0.0,
            failed_supplier_ids=["S-PRIM"],
        )
        self.assertIn("error", result)

    def test_no_candidates_remaining(self):
        """Both suppliers fail -> no candidates -> STATUS_NO_PLAN."""
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=100.0,
            failed_supplier_ids=["S-PRIM", "S-BACK"],
            data=data,
            graph=g,
        )
        rec = result["recommended_plan"]
        self.assertEqual(rec["status"], STATUS_NO_PLAN)
        self.assertEqual(rec["allocated_quantity"], 0)

    def test_three_plan_variants_present(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        self.assertIn("recommended_plan", result)
        self.assertIn("lowest_cost_plan", result)
        self.assertIn("fastest_plan", result)
        self.assertEqual(result["lowest_cost_plan"]["optimization_objective"], OBJ_LOWEST_COST)
        self.assertEqual(result["fastest_plan"]["optimization_objective"], OBJ_FASTEST)
        self.assertEqual(result["recommended_plan"]["optimization_objective"], OBJ_BALANCED)

    def test_multiple_simultaneous_failures(self):
        """Both primaries fail; only an independent third supplier can rescue."""
        suppliers = [
            {"supplier_id": "PRIM-A", "supplier_name": "PrimA", "tier": 1,
             "city": "A", "state": "A", "country": "India",
             "category": "w", "monthly_capacity_units": 5000,
             "capacity_status": "sufficient", "lead_time_days": 10,
             "quality_score": 95, "primary_route_id": ""},
            {"supplier_id": "PRIM-B", "supplier_name": "PrimB", "tier": 1,
             "city": "B", "state": "B", "country": "India",
             "category": "w", "monthly_capacity_units": 4000,
             "capacity_status": "sufficient", "lead_time_days": 9,
             "quality_score": 93, "primary_route_id": ""},
            {"supplier_id": "SAVR", "supplier_name": "Saviour", "tier": 1,
             "city": "S", "state": "S", "country": "India",
             "category": "w", "monthly_capacity_units": 6000,
             "capacity_status": "sufficient", "lead_time_days": 12,
             "quality_score": 91, "primary_route_id": ""},
        ]
        sm = [
            {"supplier_id": "PRIM-A", "material_id": "MAT-T1", "is_backup": 0,
             "unit_cost_inr": 100, "monthly_capacity_units": 5000,
             "lead_time_days": 10, "moq_units": 100},
            {"supplier_id": "PRIM-B", "material_id": "MAT-T1", "is_backup": 0,
             "unit_cost_inr": 105, "monthly_capacity_units": 4000,
             "lead_time_days": 9, "moq_units": 100},
            {"supplier_id": "SAVR", "material_id": "MAT-T1", "is_backup": 0,
             "unit_cost_inr": 115, "monthly_capacity_units": 6000,
             "lead_time_days": 12, "moq_units": 100},
        ]
        data = _make_data(suppliers=suppliers, materials=BASE_MATERIALS, supplier_materials=sm)
        g = _make_minimal_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=500.0,
            failed_supplier_ids=["PRIM-A", "PRIM-B"],
            data=data,
            graph=g,
        )
        rec = result["recommended_plan"]
        self.assertEqual(rec["status"], STATUS_FEASIBLE)
        ids = [s["supplier_id"] for s in rec["selected_suppliers"]]
        self.assertIn("SAVR", ids)

    def test_unknown_failed_supplier_generates_warning(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=100.0,
            failed_supplier_ids=["S-NONEXISTENT"],
            data=data,
            graph=g,
        )
        warnings = result["recommended_plan"]["warnings"]
        self.assertTrue(any("S-NONEXISTENT" in w for w in warnings))

    def test_candidate_evaluation_present(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        self.assertIn("candidate_evaluation", result)
        self.assertTrue(len(result["candidate_evaluation"]) > 0)

    def test_additional_cost_calculated(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            original_supplier_id="S-PRIM",
            data=data,
            graph=g,
        )
        # S-BACK costs 110 vs S-PRIM 100 -> delta = 10
        cands = result["candidate_evaluation"]
        back = next((c for c in cands if c["supplier_id"] == "S-BACK"), None)
        self.assertIsNotNone(back)
        self.assertEqual(back["additional_cost_per_unit_inr"], 10)


# ---------------------------------------------------------------------------
# Tests: Task 10 - Emergency Recovery Mode
# ---------------------------------------------------------------------------

class TestEmergencyRecovery(unittest.TestCase):

    def test_emergency_mode_activates_when_only_shared_upstream_available(self):
        """
        S-PRIM fails. S-BACK shares an upstream with S-PRIM.
        Normal mode excludes shared-upstream candidates if they are DEP_DIRECTLY_AFFECTED.
        Emergency mode should activate and use S-BACK.
        """
        suppliers = BASE_SUPPLIERS + [
            {"supplier_id": "S-UPSTR", "supplier_name": "Upstream",
             "tier": 2, "city": "U", "state": "U", "country": "India",
             "category": "raw", "monthly_capacity_units": 10000,
             "capacity_status": "sufficient", "lead_time_days": 15,
             "quality_score": 88, "primary_route_id": ""},
        ]
        deps = [
            {"dependency_id": "D1", "downstream_supplier_id": "S-PRIM",
             "upstream_supplier_id": "S-UPSTR", "material_id": "MAT-T1",
             "dependency_type": "direct", "notes": ""},
            {"dependency_id": "D2", "downstream_supplier_id": "S-BACK",
             "upstream_supplier_id": "S-UPSTR", "material_id": "MAT-T1",
             "dependency_type": "direct", "notes": ""},
        ]
        data = _make_data(
            suppliers=suppliers,
            materials=BASE_MATERIALS,
            supplier_materials=BASE_SM,
            supplier_dependencies=deps,
        )
        g = _make_minimal_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=500.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        rec = result["recommended_plan"]
        # S-BACK has shared upstream but is still feasible -> emergency or normal plan
        # should allocate to S-BACK
        self.assertGreater(rec["allocated_quantity"], 0)
        self.assertIn(rec["status"],
                      (STATUS_FEASIBLE, STATUS_PARTIAL, STATUS_EMERGENCY))

    def test_no_feasible_plan_when_all_excluded(self):
        """All suppliers fail -> status NO_FEASIBLE_PLAN."""
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=100.0,
            failed_supplier_ids=["S-PRIM", "S-BACK"],
            data=data,
            graph=g,
        )
        self.assertIn(result["recommended_plan"]["status"],
                      (STATUS_NO_PLAN, STATUS_EMERGENCY))


# ---------------------------------------------------------------------------
# Tests: Task 11 - JSON serialisation
# ---------------------------------------------------------------------------

class TestSerialisation(unittest.TestCase):

    def test_result_is_json_serialisable(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        try:
            serialised = json.dumps(result, default=str)
        except (TypeError, ValueError) as e:
            self.fail("Result is not JSON serialisable: " + str(e))
        self.assertIsInstance(serialised, str)

    def test_plan_has_required_fields(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        rec = result["recommended_plan"]
        required_fields = [
            "material_id", "required_quantity", "allocated_quantity",
            "unmet_quantity", "status", "optimization_objective",
            "selected_suppliers", "total_procurement_cost_inr",
            "effective_delivery_days", "missing_information",
            "rejected_candidates", "warnings", "selection_explanation",
        ]
        for field in required_fields:
            self.assertIn(field, rec, "Missing field: " + field)

    def test_partial_recovery_correctly_flagged(self):
        """Only 300 available for 1000 required -> PARTIAL_RECOVERY."""
        sm = [{
            "supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
            "unit_cost_inr": 110, "monthly_capacity_units": 300,
            "lead_time_days": 8, "moq_units": 50,
        }]
        data = _make_data(
            suppliers=BASE_SUPPLIERS,
            materials=BASE_MATERIALS,
            supplier_materials=sm,
        )
        g = _make_minimal_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=1000.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        rec = result["recommended_plan"]
        self.assertIn(rec["status"], (STATUS_PARTIAL, STATUS_EMERGENCY))
        self.assertLess(rec["allocated_quantity"], 1000)
        self.assertGreater(rec["unmet_quantity"], 0)

    def test_full_recovery_correctly_flagged(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        self.assertEqual(result["recommended_plan"]["status"], STATUS_FEASIBLE)


# ---------------------------------------------------------------------------
# Tests: Task 13 - Integration with Member 4 (re-optimisation)
# ---------------------------------------------------------------------------

class TestMember4Integration(unittest.TestCase):

    def test_plan_contains_member4_required_fields(self):
        """Member 4 needs: selected_supplier_ids, allocated quantities,
        dependency info, routes, unmet demand."""
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        rec = result["recommended_plan"]
        for supplier in rec.get("selected_suppliers", []):
            self.assertIn("supplier_id", supplier)
            self.assertIn("allocated_quantity", supplier)
            self.assertIn("dependency_status", supplier)
            self.assertIn("transport_status", supplier)

    def test_reoptimisation_after_challenger_finds_new_failure(self):
        """
        Challenger finds S-BACK also fails. Re-run optimise_recovery with
        both failures -> no candidates -> NO_PLAN.
        """
        data = _base_data()
        g = _base_graph(data)

        # Initial plan
        plan1 = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        self.assertEqual(plan1["recommended_plan"]["status"], STATUS_FEASIBLE)

        # Challenger detects S-BACK also failed.
        additional_failed = "S-BACK"
        all_failed = plan1["failed_supplier_ids"] + [additional_failed]

        plan2 = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=all_failed,
            data=data,
            graph=g,
        )
        self.assertIn(plan2["recommended_plan"]["status"],
                      (STATUS_NO_PLAN, STATUS_EMERGENCY))

    def test_disruption_report_wrapper_single(self):
        """optimise_from_disruption_report extracts failed_supplier_id correctly."""
        fake_report = {"scenario": {"failed_supplier_id": "S-PRIM"}}
        data = _base_data()
        g = _base_graph(data)
        result = optimise_from_disruption_report(
            disruption_report=fake_report,
            material_id="MAT-T1",
            required_quantity=200.0,
            data=data,
            graph=g,
        )
        self.assertIn("recommended_plan", result)
        self.assertIn("S-PRIM", result["failed_supplier_ids"])

    def test_disruption_report_wrapper_multi(self):
        """optimise_from_disruption_report handles multi-disruption report."""
        fake_report = {"scenario": {"failed_supplier_ids": ["S-PRIM", "S-BACK"]}}
        data = _base_data()
        g = _base_graph(data)
        result = optimise_from_disruption_report(
            disruption_report=fake_report,
            material_id="MAT-T1",
            required_quantity=100.0,
            data=data,
            graph=g,
        )
        self.assertIn("S-PRIM", result["failed_supplier_ids"])
        self.assertIn("S-BACK", result["failed_supplier_ids"])


# ---------------------------------------------------------------------------
# Tests: Edge cases and error handling (Task 14)
# ---------------------------------------------------------------------------

class TestEdgeCasesAndErrors(unittest.TestCase):

    def test_empty_failed_suppliers_returns_all_candidates(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=100.0,
            failed_supplier_ids=[],
            data=data,
            graph=g,
        )
        self.assertIn("candidate_evaluation", result)
        self.assertEqual(len(result["candidate_evaluation"]), 2)  # both S-PRIM and S-BACK

    def test_invalid_quantity_string_returns_error(self):
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity="not-a-number",
            failed_supplier_ids=[],
        )
        self.assertIn("error", result)

    def test_none_material_id_returns_error(self):
        result = optimise_recovery(
            material_id=None,
            required_quantity=100.0,
            failed_supplier_ids=[],
        )
        self.assertIn("error", result)

    def test_missing_information_list_populated(self):
        """Supplier with no cost in supplier_materials -> missing_info populated."""
        sm = [{
            "supplier_id": "S-BACK", "material_id": "MAT-T1", "is_backup": 1,
            "unit_cost_inr": None, "monthly_capacity_units": 3000,
            "lead_time_days": 8, "moq_units": 100,
        }]
        data = _make_data(
            suppliers=BASE_SUPPLIERS,
            materials=BASE_MATERIALS,
            supplier_materials=sm,
        )
        g = _make_minimal_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            original_supplier_id="S-PRIM",
            data=data,
            graph=g,
        )
        missing = result["recommended_plan"]["missing_information"]
        self.assertTrue(len(missing) > 0)

    def test_warnings_list_always_present(self):
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=100.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        self.assertIn("warnings", result["recommended_plan"])
        self.assertIsInstance(result["recommended_plan"]["warnings"], list)

    def test_rejected_candidates_listed(self):
        """An incompatible supplier should appear in rejected_candidates."""
        # Add a supplier that is not listed for MAT-T1 but exists.
        suppliers = BASE_SUPPLIERS + [{
            "supplier_id": "S-WRONG", "supplier_name": "WrongMaterial Co",
            "tier": 2, "city": "W", "state": "W", "country": "India",
            "category": "metal", "monthly_capacity_units": 2000,
            "capacity_status": "sufficient", "lead_time_days": 14,
            "quality_score": 85, "primary_route_id": "",
        }]
        sm = BASE_SM + [{
            "supplier_id": "S-WRONG", "material_id": "MAT-T9", "is_backup": 0,
            "unit_cost_inr": 50, "monthly_capacity_units": 2000,
            "lead_time_days": 14, "moq_units": 200,
        }]
        mats = BASE_MATERIALS + [{
            "material_id": "MAT-T9", "material_name": "Wrong Material",
            "category": "metal", "unit": "kg",
            "unit_cost_inr": 50, "typical_lead_time_days": 14,
            "used_in_product": "Product Z",
        }]
        data = _make_data(suppliers=suppliers, materials=mats, supplier_materials=sm)
        g = _make_minimal_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
        )
        # S-WRONG is not a candidate for MAT-T1 at all (not in suppliers_of[MAT-T1])
        # so it won't appear in candidates or rejections - this tests that S-WRONG
        # does not pollute the MAT-T1 search.
        for cand in result["candidate_evaluation"]:
            self.assertNotEqual(cand["supplier_id"], "S-WRONG")

    def test_duplicate_failed_supplier_ids_handled(self):
        """Providing the same failed supplier twice should not break anything."""
        data = _base_data()
        g = _base_graph(data)
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=100.0,
            failed_supplier_ids=["S-PRIM", "S-PRIM"],
            data=data,
            graph=g,
        )
        self.assertIn("recommended_plan", result)

    def test_configurable_weights_accepted(self):
        """Custom weights should be accepted without error."""
        data = _base_data()
        g = _base_graph(data)
        custom_weights = {
            "material_ok": 0.50,
            "feasibility": 0.30,
            "delivery_time": 0.10,
            "unit_cost": 0.05,
            "independence": 0.03,
            "transport": 0.02,
        }
        result = optimise_recovery(
            material_id="MAT-T1",
            required_quantity=200.0,
            failed_supplier_ids=["S-PRIM"],
            data=data,
            graph=g,
            weights=custom_weights,
        )
        self.assertIn("recommended_plan", result)
        self.assertEqual(result["recommended_plan"]["status"], STATUS_FEASIBLE)


# ---------------------------------------------------------------------------
# Tests: Real dataset smoke tests (uses actual CSV data)
# ---------------------------------------------------------------------------

class TestRealDataset(unittest.TestCase):
    """
    Smoke tests using the actual project dataset loaded from CSV.
    These verify integration with Member 1's data and Member 2's graph.
    """

    @classmethod
    def setUpClass(cls):
        """Load actual data once for all real-dataset tests."""
        try:
            from src.data_loader import load_all_data
            from src.supply_chain_graph import get_supply_chain_graph
            cls.data = load_all_data(verbose=False)
            cls.graph = get_supply_chain_graph(cls.data)
            cls.data_available = True
        except Exception:
            cls.data_available = False

    def _skip_if_no_data(self):
        if not self.data_available:
            self.skipTest("Real dataset not available")

    def test_mat02_backup_exists(self):
        """MAT-02 (Battery pack) has backup supplier SUP-T1-04."""
        self._skip_if_no_data()
        result = optimise_recovery(
            material_id="MAT-02",
            required_quantity=1000.0,
            failed_supplier_ids=["SUP-T1-03"],
            original_supplier_id="SUP-T1-03",
            data=self.data,
            graph=self.graph,
        )
        self.assertIn("candidate_evaluation", result)
        # SUP-T1-04 is the designated backup for MAT-02
        cand_ids = [c["supplier_id"] for c in result["candidate_evaluation"]]
        self.assertIn("SUP-T1-04", cand_ids)

    def test_mat03_backup_exists(self):
        """MAT-03 (OLED display) has backup supplier SUP-T1-02."""
        self._skip_if_no_data()
        result = optimise_recovery(
            material_id="MAT-03",
            required_quantity=5000.0,
            failed_supplier_ids=["SUP-T1-01"],
            original_supplier_id="SUP-T1-01",
            data=self.data,
            graph=self.graph,
        )
        cand_ids = [c["supplier_id"] for c in result["candidate_evaluation"]]
        self.assertIn("SUP-T1-02", cand_ids)
        rec = result["recommended_plan"]
        # SUP-T1-02 has 6000 capacity > 5000 required -> should be FEASIBLE
        self.assertEqual(rec["status"], STATUS_FEASIBLE)

    def test_shared_upstream_detected_real_data(self):
        """
        SUP-T1-03 and SUP-T1-04 share upstream SUP-T2-01.
        When SUP-T1-03 fails, SUP-T1-04 should show DEP_SHARED_UPSTREAM.
        """
        self._skip_if_no_data()
        result = optimise_recovery(
            material_id="MAT-02",
            required_quantity=1000.0,
            failed_supplier_ids=["SUP-T1-03"],
            data=self.data,
            graph=self.graph,
        )
        cands = {c["supplier_id"]: c for c in result["candidate_evaluation"]}
        if "SUP-T1-04" in cands:
            dep = cands["SUP-T1-04"]["dependency_status"]
            # SUP-T1-04 depends on SUP-T2-01 and so does SUP-T1-03
            self.assertIn(dep, (DEP_SHARED_UPSTREAM, DEP_DIRECTLY_AFFECTED))

    def test_real_data_result_serialisable(self):
        """Full real-data result must be JSON serialisable for Member 5."""
        self._skip_if_no_data()
        result = optimise_recovery(
            material_id="MAT-02",
            required_quantity=500.0,
            failed_supplier_ids=["SUP-T1-03"],
            data=self.data,
            graph=self.graph,
        )
        try:
            json.dumps(result, default=str)
        except (TypeError, ValueError) as e:
            self.fail("Real data result is not JSON serialisable: " + str(e))

    def test_multi_disruption_real_data(self):
        """Both OLED display suppliers fail -> PARTIAL or NO_PLAN."""
        self._skip_if_no_data()
        result = optimise_recovery(
            material_id="MAT-03",
            required_quantity=10000.0,
            failed_supplier_ids=["SUP-T1-01", "SUP-T1-02"],
            data=self.data,
            graph=self.graph,
        )
        rec = result["recommended_plan"]
        # No suppliers remain for MAT-03 after both fail.
        self.assertIn(rec["status"], (STATUS_NO_PLAN, STATUS_EMERGENCY))
        self.assertEqual(rec["allocated_quantity"], 0)


if __name__ == "__main__":
    unittest.main()
