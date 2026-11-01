"""
Automated tests for src/disruption_simulation.py (Member 2, Phase 1).

Two groups:
  * SyntheticScenarioTests : tiny hand-made datasets, so every rule can be
                             checked against an answer worked out by hand.
  * RealDatasetTests       : Member 1's actual CSV files.
"""

import copy
import hashlib
import json
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.data_loader import CSV_FILES, DATA_FOLDER, load_all_data
from src.disruption_impact import find_downstream_suppliers
from src.disruption_simulation import (
    BELOW,
    DIRECT,
    LINKED_FACTORY_HOLDS_MATERIAL,
    MITIGATED,
    NOT_COMPUTED,
    POTENTIAL_CASCADING,
    PRODUCT_LINK_ONLY,
    UNKNOWN,
    UNMITIGATED,
    WAREHOUSE_HOLDS_MATERIAL,
    format_disruption_report,
    simulate_supplier_disruption,
)
from src.supply_chain_graph import build_supply_chain_graph, get_supply_chain_graph


# ---------------------------------------------------------------------------
# A tiny hand-made supply chain
#
#   S-U (tier 3)  --->  S-A (tier 2, FAILS)  --->  S-C (tier 1)
#   S-B (tier 2) also supplies M1 (possible backup for S-A)
#   S-C supplies M2.  M1 and M2 are both used in "Prod One"; only M2 in "Prod Two".
#   F1 feeds W1.  W2 has no factory.
# ---------------------------------------------------------------------------

def make_data(shared_upstream=False, backup_capacity=100, extra_inventory=None,
              inventory=None, orders=None):
    suppliers = pd.DataFrame([
        {"supplier_id": "S-U", "supplier_name": "Upstream", "tier": 3, "capacity_status": "sufficient"},
        {"supplier_id": "S-A", "supplier_name": "Failing", "tier": 2, "capacity_status": "sufficient"},
        {"supplier_id": "S-B", "supplier_name": "Backup", "tier": 2, "capacity_status": "sufficient"},
        {"supplier_id": "S-C", "supplier_name": "Downstream", "tier": 1, "capacity_status": "sufficient"},
    ])
    supplier_materials = pd.DataFrame([
        {"supplier_id": "S-A", "material_id": "M1", "is_backup": 0, "monthly_capacity_units": 100},
        {"supplier_id": "S-B", "material_id": "M1", "is_backup": 1, "monthly_capacity_units": backup_capacity},
        {"supplier_id": "S-C", "material_id": "M2", "is_backup": 0, "monthly_capacity_units": 100},
    ])
    dependencies = [
        {"dependency_id": "D1", "downstream_supplier_id": "S-C", "upstream_supplier_id": "S-A",
         "material_id": "M1", "dependency_type": "direct"},
    ]
    if shared_upstream:
        dependencies += [
            {"dependency_id": "D2", "downstream_supplier_id": "S-A", "upstream_supplier_id": "S-U",
             "material_id": "M1", "dependency_type": "direct"},
            {"dependency_id": "D3", "downstream_supplier_id": "S-B", "upstream_supplier_id": "S-U",
             "material_id": "M1", "dependency_type": "direct"},
        ]
    materials = pd.DataFrame([
        {"material_id": "M1", "material_name": "Part One", "used_in_product": "Prod One"},
        {"material_id": "M2", "material_name": "Part Two", "used_in_product": "Prod One;Prod Two"},
    ])
    factories = pd.DataFrame([{"factory_id": "F1", "factory_name": "Factory", "linked_warehouse_id": "W1"}])
    warehouses = pd.DataFrame([
        {"warehouse_id": "W1", "warehouse_name": "Hub 1", "linked_factory_id": "F1"},
        {"warehouse_id": "W2", "warehouse_name": "Hub 2", "linked_factory_id": ""},
    ])
    if inventory is None:
        inventory = [
            {"inventory_id": "I1", "location_id": "F1", "location_type": "factory", "material_id": "M1",
             "quantity_on_hand": 100, "reorder_point": 300, "max_stock": 900},
            {"inventory_id": "I2", "location_id": "W1", "location_type": "warehouse", "material_id": "M1",
             "quantity_on_hand": 500, "reorder_point": 200, "max_stock": 900},
        ]
    if orders is None:
        orders = [
            {"order_id": "O1", "customer_name": "C1", "warehouse_id": "W1", "product_name": "Prod One",
             "quantity": 1, "order_value_inr": 1000, "status": "confirmed"},
        ]
    return {
        "suppliers": suppliers,
        "supplier_materials": supplier_materials,
        "supplier_dependencies": pd.DataFrame(dependencies),
        "materials": materials,
        "factories": factories,
        "warehouses": warehouses,
        "inventory": pd.DataFrame(inventory + (extra_inventory or [])),
        "customer_orders": pd.DataFrame(orders),
        "transport_routes": pd.DataFrame(columns=["route_id", "origin_id", "destination_id"]),
    }


def run(data, supplier_id="S-A", days=7):
    return simulate_supplier_disruption(supplier_id, days, data=data, graph=build_supply_chain_graph(data))


def backup_status(report, material_id):
    return next(b["status"] for b in report["backup_assessment"] if b["material_id"] == material_id)


def order(order_id, warehouse, product="Prod One", value=1000, status="confirmed"):
    return {"order_id": order_id, "customer_name": "C", "warehouse_id": warehouse, "product_name": product,
            "quantity": 1, "order_value_inr": value, "status": status}


class SyntheticScenarioTests(unittest.TestCase):

    # ---- direct / cascading -----------------------------------------------

    def test_direct_and_cascading_are_separate(self):
        report = run(make_data())
        self.assertEqual([m["material_id"] for m in report["direct_materials"]], ["M1"])
        self.assertEqual([m["material_id"] for m in report["potential_cascading_materials"]], ["M2"])
        self.assertEqual(report["direct_materials"][0]["impact_type"], DIRECT)
        self.assertEqual(report["potential_cascading_materials"][0]["impact_type"], POTENTIAL_CASCADING)
        self.assertEqual([d["supplier_id"] for d in report["downstream_suppliers"]], ["S-C"])
        self.assertIn("not assumed to have stopped", report["downstream_suppliers"][0]["status"])

    def test_material_both_direct_and_downstream_stays_direct(self):
        data = make_data()
        data["supplier_materials"] = pd.concat([data["supplier_materials"], pd.DataFrame([
            {"supplier_id": "S-C", "material_id": "M1", "is_backup": 0, "monthly_capacity_units": 100}])],
            ignore_index=True)
        report = run(data)
        self.assertEqual([m["material_id"] for m in report["direct_materials"]], ["M1"])
        self.assertNotIn("M1", [m["material_id"] for m in report["potential_cascading_materials"]])

    def test_dependency_material_id_is_annotation_only(self):
        base = run(make_data())
        data = make_data()
        data["supplier_dependencies"].loc[:, "material_id"] = "M2"   # change the annotation only
        changed = run(data)
        for key in ("direct_materials", "potential_cascading_materials", "factories", "warehouses"):
            self.assertEqual(
                [list(x.values())[0] for x in base[key]], [list(x.values())[0] for x in changed[key]], key)
        self.assertEqual(base["summary"]["headline_order_count"], changed["summary"]["headline_order_count"])
        link = changed["downstream_suppliers"][0]["dependency_links"][0]
        self.assertEqual(link["dependency_material_id_annotation"], "M2")

    # ---- backup status ----------------------------------------------------

    def test_genuine_independent_backup_is_mitigated(self):
        self.assertEqual(backup_status(run(make_data()), "M1"), MITIGATED)

    def test_shared_upstream_backup_is_unmitigated(self):
        report = run(make_data(shared_upstream=True))
        self.assertEqual(backup_status(report, "M1"), UNMITIGATED)
        candidate = report["backup_assessment"][0]["candidates"][0]
        self.assertEqual(candidate["verdict"], "NOT_GENUINE")
        self.assertTrue(any("shares upstream" in r for r in candidate["reasons"]))

    def test_insufficient_capacity_backup_is_unmitigated(self):
        self.assertEqual(backup_status(run(make_data(backup_capacity=50)), "M1"), UNMITIGATED)

    def test_missing_capacity_backup_is_unknown_not_unmitigated(self):
        report = run(make_data(backup_capacity=None))
        self.assertEqual(backup_status(report, "M1"), UNKNOWN)
        self.assertEqual(report["backup_assessment"][0]["candidates"][0]["verdict"], UNKNOWN)

    def test_material_with_only_exposed_suppliers_is_unmitigated(self):
        report = run(make_data())
        self.assertEqual(backup_status(report, "M2"), UNMITIGATED)   # only S-C (downstream) supplies M2
        self.assertEqual(report["backup_assessment"][1]["candidates"], [])

    def test_failed_supplier_with_no_material_mapping_is_unknown(self):
        report = run(make_data(shared_upstream=True), supplier_id="S-U")
        self.assertEqual(report["direct_materials_status"], UNKNOWN)
        self.assertEqual(report["direct_materials"], [])
        self.assertEqual(report["summary"]["direct_material_count"], UNKNOWN)
        self.assertTrue(any("S-U has no row in supplier_materials.csv" in g for g in report["data_gaps"]))
        # Downstream materials are still reported, but only as potential.
        self.assertTrue(all(m["impact_type"] == POTENTIAL_CASCADING
                            for m in report["potential_cascading_materials"]))

    # ---- inventory --------------------------------------------------------

    def test_inventory_values_and_pooled_status(self):
        inv = run(make_data())["inventory"][0]
        self.assertEqual(inv["material_id"], "M1")
        self.assertEqual([(l["location_id"], l["location_kind"], l["quantity_on_hand"], l["status"])
                          for l in inv["locations"]],
                         [("F1", "factory", 100, BELOW), ("W1", "warehouse", 500, "AT_OR_ABOVE_REORDER_POINT")])
        self.assertEqual(inv["locations"][0]["shortfall_to_reorder_point"], 200)
        self.assertEqual(inv["pooled_all_locations"]["on_hand"], 600)
        self.assertEqual(inv["pooled_all_locations"]["reorder_point"], 500)
        self.assertEqual(inv["pooled_all_locations"]["status"], "AT_OR_ABOVE_REORDER_POINT")
        self.assertEqual(inv["pooled_factories"]["status"], BELOW)
        self.assertEqual(inv["shortage_exposure"], "SOME_LOCATIONS_BELOW_REORDER_POINT")

    def test_missing_quantity_makes_pooled_status_unknown_not_zero(self):
        inventory = [
            {"inventory_id": "I1", "location_id": "F1", "location_type": "factory", "material_id": "M1",
             "quantity_on_hand": None, "reorder_point": 300, "max_stock": 900},
            {"inventory_id": "I2", "location_id": "W1", "location_type": "warehouse", "material_id": "M1",
             "quantity_on_hand": 500, "reorder_point": 200, "max_stock": 900},
        ]
        inv = run(make_data(inventory=inventory))["inventory"][0]
        self.assertEqual(inv["pooled_all_locations"]["status"], UNKNOWN)
        self.assertEqual(inv["pooled_all_locations"]["on_hand"], UNKNOWN)
        self.assertEqual(inv["locations"][0]["quantity_on_hand"], UNKNOWN)
        self.assertEqual(inv["locations"][0]["status"], UNKNOWN)
        self.assertEqual(inv["shortage_exposure"], UNKNOWN)

    def test_missing_reorder_point_makes_pooled_status_unknown(self):
        inventory = [
            {"inventory_id": "I1", "location_id": "F1", "location_type": "factory", "material_id": "M1",
             "quantity_on_hand": 100, "reorder_point": None, "max_stock": 900},
            {"inventory_id": "I2", "location_id": "W1", "location_type": "warehouse", "material_id": "M1",
             "quantity_on_hand": 500, "reorder_point": 200, "max_stock": 900},
        ]
        inv = run(make_data(inventory=inventory))["inventory"][0]
        self.assertEqual(inv["pooled_all_locations"]["status"], UNKNOWN)
        self.assertEqual(inv["pooled_all_locations"]["reorder_point"], UNKNOWN)

    def test_no_inventory_rows_is_unknown_not_zero(self):
        data = make_data(inventory=[{"inventory_id": "I9", "location_id": "F1", "location_type": "factory",
                                     "material_id": "M2", "quantity_on_hand": 5, "reorder_point": 1,
                                     "max_stock": 9}])
        m1 = next(i for i in run(data)["inventory"] if i["material_id"] == "M1")
        self.assertEqual(m1["locations"], [])
        self.assertEqual(m1["pooled_all_locations"]["status"], "NO_INVENTORY_RECORDS")
        self.assertEqual(m1["pooled_all_locations"]["on_hand"], UNKNOWN)
        self.assertEqual(m1["shortage_exposure"], UNKNOWN)

    # ---- factories / warehouses -------------------------------------------

    def test_factory_and_warehouse_found_through_inventory(self):
        report = run(make_data())
        self.assertEqual([(f["factory_id"], f["evidence_level"], f["impact_type"]) for f in report["factories"]],
                         [("F1", "INVENTORY_LINK", DIRECT)])
        self.assertEqual([(w["warehouse_id"], w["evidence_level"]) for w in report["warehouses"]],
                         [("W1", "INVENTORY_LINK")])

    def test_warehouse_fed_by_affected_factory_is_link_only(self):
        inventory = [{"inventory_id": "I1", "location_id": "F1", "location_type": "factory",
                      "material_id": "M1", "quantity_on_hand": 100, "reorder_point": 300, "max_stock": 900}]
        report = run(make_data(inventory=inventory))
        self.assertEqual([(w["warehouse_id"], w["evidence_level"]) for w in report["warehouses"]],
                         [("W1", "FACTORY_LINK_ONLY")])

    # ---- customer orders --------------------------------------------------

    def test_order_found_through_warehouse_holding_material(self):
        head = run(make_data())["customer_orders"]["headline_path_supported"]
        self.assertEqual(head["order_count"], 1)
        self.assertEqual(head["orders"][0]["evidence_level"], WAREHOUSE_HOLDS_MATERIAL)
        self.assertEqual(head["potential_value_exposure_inr"], 1000)

    def test_order_found_through_linked_factory(self):
        inventory = [{"inventory_id": "I1", "location_id": "F1", "location_type": "factory",
                      "material_id": "M1", "quantity_on_hand": 100, "reorder_point": 300, "max_stock": 900}]
        head = run(make_data(inventory=inventory))["customer_orders"]["headline_path_supported"]
        self.assertEqual(head["orders"][0]["evidence_level"], LINKED_FACTORY_HOLDS_MATERIAL)
        self.assertEqual(head["orders"][0]["supporting_materials"][0]["via_location"], "F1")

    def test_product_link_only_is_separate_and_not_in_headline(self):
        data = make_data(orders=[order("O1", "W1", value=1000), order("O2", "W2", value=5000)])
        orders = run(data)["customer_orders"]
        self.assertEqual([o["order_id"] for o in orders["headline_path_supported"]["orders"]], ["O1"])
        self.assertEqual(orders["headline_path_supported"]["potential_value_exposure_inr"], 1000)
        extra = orders["additional_product_link_only"]
        self.assertEqual([o["order_id"] for o in extra["orders"]], ["O2"])
        self.assertEqual(extra["orders"][0]["evidence_level"], PRODUCT_LINK_ONLY)
        self.assertEqual(extra["potential_value_exposure_inr"], 5000)
        self.assertEqual(orders["upper_bound_including_product_link_only_inr"], 6000)

    def test_order_with_two_supporting_materials_is_counted_once(self):
        # "Prod One" uses both M1 (direct) and M2 (cascading). W1 holds both.
        inventory = [
            {"inventory_id": "I1", "location_id": "W1", "location_type": "warehouse", "material_id": "M1",
             "quantity_on_hand": 500, "reorder_point": 200, "max_stock": 900},
            {"inventory_id": "I2", "location_id": "W1", "location_type": "warehouse", "material_id": "M2",
             "quantity_on_hand": 500, "reorder_point": 200, "max_stock": 900},
        ]
        head = run(make_data(inventory=inventory))["customer_orders"]["headline_path_supported"]
        self.assertEqual(head["order_count"], 1)
        self.assertEqual(head["potential_value_exposure_inr"], 1000)
        self.assertEqual(len(head["orders"][0]["supporting_materials"]), 2)
        self.assertEqual(head["orders"][0]["impact_type"], DIRECT)

    def test_cascading_only_order_is_labelled_cascading(self):
        # "Prod Two" uses only M2 (cascading). W1 holds M2.
        inventory = [{"inventory_id": "I2", "location_id": "W1", "location_type": "warehouse",
                      "material_id": "M2", "quantity_on_hand": 5, "reorder_point": 2, "max_stock": 9}]
        head = run(make_data(inventory=inventory, orders=[order("O1", "W1", "Prod Two")]))[
            "customer_orders"]["headline_path_supported"]
        self.assertEqual(head["orders"][0]["impact_type"], POTENTIAL_CASCADING)
        self.assertEqual(head["direct_order_count"], 0)
        self.assertEqual(head["potential_cascading_order_count"], 1)
        self.assertEqual(head["potential_value_direct_inr"], 0)
        self.assertEqual(head["potential_value_cascading_only_inr"], 1000)

    def test_product_name_whitespace_is_normalised_without_changing_data(self):
        data = make_data(orders=[order("O1", "W1", "  Prod   One ")])
        before = data["customer_orders"].copy(deep=True)
        head = run(data)["customer_orders"]["headline_path_supported"]
        self.assertEqual([o["order_id"] for o in head["orders"]], ["O1"])
        self.assertEqual(head["orders"][0]["product_name"], "Prod One")
        pd.testing.assert_frame_equal(data["customer_orders"], before)

    def test_only_confirmed_and_planned_orders_are_included(self):
        data = make_data(orders=[order("O1", "W1", status="confirmed"), order("O2", "W1", status="planned"),
                                 order("O3", "W1", status="cancelled"), order("O4", "W1", status="")])
        report = run(data)
        ids = [o["order_id"] for o in report["customer_orders"]["headline_path_supported"]["orders"]]
        self.assertEqual(ids, ["O1", "O2"])
        self.assertTrue(any("O3" in g and "O4" in g for g in report["data_gaps"]))

    def test_missing_order_value_is_unknown_and_never_zero(self):
        data = make_data(orders=[order("O1", "W1", value=1000), order("O2", "W1", value=None)])
        head = run(data)["customer_orders"]["headline_path_supported"]
        o2 = next(o for o in head["orders"] if o["order_id"] == "O2")
        self.assertEqual(o2["order_value_inr"], UNKNOWN)
        self.assertEqual(head["potential_value_exposure_inr"], 1000)   # known values only
        self.assertFalse(head["value_is_complete"])
        self.assertEqual(head["orders_with_unknown_value"], ["O2"])

    def test_all_order_values_missing_gives_unknown_total(self):
        data = make_data(orders=[order("O1", "W1", value=None)])
        orders = run(data)["customer_orders"]
        self.assertEqual(orders["headline_path_supported"]["potential_value_exposure_inr"], UNKNOWN)
        self.assertEqual(orders["upper_bound_including_product_link_only_inr"], UNKNOWN)

    def test_order_for_unrelated_product_is_not_exposed(self):
        data = make_data(orders=[order("O1", "W1", "Prod Three")])
        report = run(data)
        self.assertEqual(report["summary"]["headline_order_count"], 0)
        self.assertTrue(any("O1" in g for g in report["data_gaps"]))   # product matched nothing

    def test_no_orders_gives_zero_orders_and_zero_value(self):
        data = make_data()
        data["customer_orders"] = pd.DataFrame(columns=list(order("x", "W1").keys()))
        head = run(data)["customer_orders"]["headline_path_supported"]
        self.assertEqual(head["order_count"], 0)
        self.assertEqual(head["potential_value_exposure_inr"], 0)

    # ---- routes -----------------------------------------------------------

    def test_routes_used_by_failed_supplier_and_touching_affected_locations(self):
        data = make_data()
        data["suppliers"]["primary_route_id"] = ["", "R1", "", ""]
        data["transport_routes"] = pd.DataFrame([
            {"route_id": "R1", "origin_id": "S-A", "destination_id": "F1", "mode": "road",
             "transit_days": 2, "cargo": "Part One (M1)", "shared_supplier_ids": ""},
            {"route_id": "R2", "origin_id": "F1", "destination_id": "W1", "mode": "road",
             "transit_days": 1, "cargo": "Goods", "shared_supplier_ids": ""},
            {"route_id": "R3", "origin_id": "W2", "destination_id": "W2", "mode": "road",
             "transit_days": 1, "cargo": "x", "shared_supplier_ids": ""},
        ])
        routes = {r["route_id"]: r for r in run(data)["transport_routes"]}
        self.assertEqual(set(routes), {"R1", "R2"})
        self.assertEqual(routes["R1"]["evidence_level"], "SUPPLIER_ROUTE")
        self.assertEqual(routes["R2"]["evidence_level"], "LOCATION_LINK_ONLY")
        self.assertEqual(routes["R1"]["cargo_text_material_ids_annotation"], [])   # only MAT-nn ids are parsed
        self.assertIn("not assumed to have failed", routes["R1"]["status"])

    # ---- NOT COMPUTED / validation / immutability ----------------------------

    def test_delivery_delay_and_production_days_are_not_computed(self):
        report = run(make_data())
        self.assertEqual(report["delivery_delay"]["status"], NOT_COMPUTED)
        self.assertEqual(report["production_days_remaining"]["status"], NOT_COMPUTED)
        self.assertTrue(report["delivery_delay"]["reason"])
        self.assertTrue(report["production_days_remaining"]["reason"])

    def test_inputs_are_not_modified(self):
        data = make_data(shared_upstream=True)
        graph = build_supply_chain_graph(data)
        data_before = {k: v.copy(deep=True) for k, v in data.items()}
        nodes_before, edges_before = copy.deepcopy(dict(graph.nodes(data=True))), copy.deepcopy(list(graph.edges(data=True)))
        simulate_supplier_disruption("S-A", 7, data=data, graph=graph)
        for name, table in data_before.items():
            pd.testing.assert_frame_equal(data[name], table)
        self.assertEqual(dict(graph.nodes(data=True)), nodes_before)
        self.assertEqual(list(graph.edges(data=True)), edges_before)


class ValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = make_data()
        cls.graph = build_supply_chain_graph(cls.data)

    def sim(self, supplier_id="S-A", days=7):
        return simulate_supplier_disruption(supplier_id, days, data=self.data, graph=self.graph)

    def test_unknown_supplier_is_rejected(self):
        with self.assertRaises(ValueError):
            self.sim("S-NOPE")

    def test_non_supplier_node_is_rejected(self):
        for node in ("M1", "F1", "W1"):
            with self.assertRaises(ValueError, msg=node):
                self.sim(node)

    def test_bad_supplier_id_values_are_rejected(self):
        for bad in (None, "", "   ", 5, ["S-A"]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.sim(bad)

    def test_supplier_id_whitespace_is_trimmed(self):
        self.assertEqual(self.sim("  S-A ")["scenario"]["failed_supplier_id"], "S-A")

    def test_bad_durations_are_rejected(self):
        for bad in (0, -3, 2.5, True, False, "7", None, float("nan")):
            with self.assertRaises(ValueError, msg=repr(bad)):
                self.sim(days=bad)

    def test_default_and_custom_duration(self):
        default = simulate_supplier_disruption("S-A", data=self.data, graph=self.graph)
        self.assertEqual(default["scenario"]["disruption_duration_days"], 7)
        self.assertEqual(self.sim(days=30)["scenario"]["disruption_duration_days"], 30)
        self.assertEqual(self.sim(days=14.0)["scenario"]["disruption_duration_days"], 14)

    def test_duration_does_not_change_the_findings(self):
        a, b = self.sim(days=1), self.sim(days=365)
        for report in (a, b):
            report["scenario"].pop("disruption_duration_days")
        a["assumptions"], b["assumptions"] = [], []
        self.assertEqual(a, b)


class RealDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_all_data(verbose=False)
        cls.graph = get_supply_chain_graph(cls.data)
        cls.report = simulate_supplier_disruption("SUP-T2-01", 7, data=cls.data, graph=cls.graph)

    # ---- SUP-T2-01, the 7-day scenario -------------------------------------

    def test_scenario(self):
        self.assertEqual(self.report["scenario"]["disruption_duration_days"], 7)
        self.assertEqual(self.report["failed_supplier"]["supplier_name"], "CellTech Hyderabad")

    def test_direct_and_cascading_materials(self):
        self.assertEqual([m["material_id"] for m in self.report["direct_materials"]], ["MAT-01"])
        self.assertEqual([m["material_id"] for m in self.report["potential_cascading_materials"]], ["MAT-02"])

    def test_downstream_suppliers_match_existing_function(self):
        expected = find_downstream_suppliers(self.graph, "SUP-T2-01")
        self.assertEqual([d["supplier_id"] for d in self.report["downstream_suppliers"]], expected)
        self.assertEqual(expected, ["SUP-T1-03", "SUP-T1-04"])

    def test_backup_status(self):
        statuses = self.report["summary"]["backup_status_by_material"]
        # SUP-T3-01 also lists MAT-01 but is UPSTREAM of SUP-T2-01, so it is not independent.
        self.assertEqual(statuses, {"MAT-01": UNMITIGATED, "MAT-02": UNMITIGATED})
        reasons = self.report["backup_assessment"][0]["candidates"][0]["reasons"]
        self.assertTrue(any("upstream of SUP-T2-01" in r for r in reasons))

    def test_inventory_matches_csv(self):
        inventory = self.data["inventory"]
        for item in self.report["inventory"]:
            rows = inventory[inventory["material_id"] == item["material_id"]]
            self.assertEqual(len(item["locations"]), len(rows))
            self.assertEqual(item["pooled_all_locations"]["on_hand"], int(rows["quantity_on_hand"].sum()))
            self.assertEqual(item["pooled_all_locations"]["reorder_point"], int(rows["reorder_point"].sum()))
        mat01 = self.report["inventory"][0]
        self.assertEqual(mat01["pooled_all_locations"]["on_hand"], 3000)
        self.assertEqual(mat01["pooled_all_locations"]["reorder_point"], 7000)
        self.assertEqual(mat01["pooled_all_locations"]["status"], BELOW)
        self.assertEqual(mat01["pooled_factories"]["on_hand"], 2100)
        self.assertEqual(mat01["pooled_warehouses"]["on_hand"], 900)

    def test_factories_and_warehouses(self):
        self.assertEqual({f["factory_id"]: f["impact_type"] for f in self.report["factories"]},
                         {"FAC-01": POTENTIAL_CASCADING, "FAC-03": DIRECT})
        self.assertEqual({w["warehouse_id"]: w["evidence_level"] for w in self.report["warehouses"]},
                         {"WH-01": "INVENTORY_LINK", "WH-03": "INVENTORY_LINK", "WH-04": "FACTORY_LINK_ONLY"})

    def test_routes(self):
        routes = {r["route_id"]: r for r in self.report["transport_routes"]}
        self.assertEqual(set(routes), {"RTE-01", "RTE-02", "RTE-03", "RTE-04", "RTE-05"})
        self.assertEqual(routes["RTE-03"]["evidence_level"], "SUPPLIER_ROUTE")
        self.assertEqual(routes["RTE-03"]["cargo_text_material_ids_annotation"], ["MAT-02"])
        self.assertNotIn("RTE-06", routes)

    def test_orders_headline_matches_independent_calculation(self):
        orders = self.data["customer_orders"]
        exposed_products = ["Nova X Smartphone", "Slate 10 Tablet"]       # products using MAT-01 / MAT-02
        in_scope = orders[orders["product_name"].isin(exposed_products) & orders["status"].isin(["confirmed", "planned"])]
        headline_expected = in_scope[in_scope["warehouse_id"].isin(["WH-01", "WH-03", "WH-04"])]
        extra_expected = in_scope[in_scope["warehouse_id"] == "WH-02"]

        head = self.report["customer_orders"]["headline_path_supported"]
        extra = self.report["customer_orders"]["additional_product_link_only"]
        self.assertEqual({o["order_id"] for o in head["orders"]}, set(headline_expected["order_id"]))
        self.assertEqual({o["order_id"] for o in extra["orders"]}, set(extra_expected["order_id"]))
        self.assertEqual(head["order_count"], 16)
        self.assertEqual(extra["order_count"], 3)
        self.assertEqual(head["potential_value_exposure_inr"], int(headline_expected["order_value_inr"].sum()))
        self.assertEqual(extra["potential_value_exposure_inr"], int(extra_expected["order_value_inr"].sum()))
        self.assertEqual(head["potential_value_exposure_inr"], 73418850)
        self.assertEqual(self.report["customer_orders"]["upper_bound_including_product_link_only_inr"],
                         int(in_scope["order_value_inr"].sum()))

    def test_orders_are_never_double_counted(self):
        orders = self.report["customer_orders"]
        head_ids = [o["order_id"] for o in orders["headline_path_supported"]["orders"]]
        extra_ids = [o["order_id"] for o in orders["additional_product_link_only"]["orders"]]
        self.assertEqual(len(head_ids), len(set(head_ids)))
        self.assertFalse(set(head_ids) & set(extra_ids))
        self.assertEqual(self.report["summary"]["headline_potential_order_value_exposure_inr"],
                         orders["headline_path_supported"]["potential_value_exposure_inr"])

    def test_headline_split_into_direct_and_cascading(self):
        head = self.report["customer_orders"]["headline_path_supported"]
        self.assertEqual(head["direct_order_count"], 5)                    # WH-03 holds MAT-01
        self.assertEqual(head["potential_cascading_order_count"], 11)
        self.assertEqual(head["potential_value_direct_inr"] + head["potential_value_cascading_only_inr"],
                         head["potential_value_exposure_inr"])

    def test_pulse_buds_orders_are_not_exposed(self):
        pulse = set(self.data["customer_orders"].query("product_name == 'Pulse Buds'")["order_id"])
        reported = {o["order_id"] for key in ("headline_path_supported", "additional_product_link_only")
                    for o in self.report["customer_orders"][key]["orders"]}
        self.assertFalse(pulse & reported)

    def test_order_links_agree_with_graph_used_in_order_edges(self):
        exposed = {"MAT-01", "MAT-02"}
        graph_orders = {o for m in exposed for o in self.graph.successors(m)
                        if self.graph.edges[m, o].get("edge_type") == "used_in_order"}
        reported = {o["order_id"] for key in ("headline_path_supported", "additional_product_link_only")
                    for o in self.report["customer_orders"][key]["orders"]}
        # Reported = graph product-link orders, minus the planned/confirmed filter (all are included here).
        self.assertEqual(reported, graph_orders)

    def test_not_computed_items_and_documentation(self):
        self.assertEqual(self.report["delivery_delay"]["status"], NOT_COMPUTED)
        self.assertEqual(self.report["production_days_remaining"]["status"], NOT_COMPUTED)
        self.assertTrue(self.report["assumptions"])
        self.assertTrue(self.report["data_gaps"])
        self.assertTrue(self.report["evidence_levels"])
        self.assertIn("not assumed to have stopped", self.report["downstream_suppliers"][0]["status"])

    def test_report_is_json_serialisable_and_text_report_works(self):
        json.dumps(self.report)
        text = format_disruption_report(self.report)
        for phrase in ("SUP-T2-01", "NOT an actual loss", "NOT COMPUTED", "PRODUCT_LINK_ONLY", "Data gaps"):
            self.assertIn(phrase, text)

    # ---- other real suppliers ----------------------------------------------

    def test_supplier_without_material_mapping(self):
        report = simulate_supplier_disruption("SUP-T3-04", data=self.data, graph=self.graph)
        self.assertEqual(report["direct_materials_status"], UNKNOWN)
        self.assertEqual(report["direct_materials"], [])
        self.assertEqual(len(report["downstream_suppliers"]), 8)
        self.assertTrue(any("SUP-T3-04 has no row" in g for g in report["data_gaps"]))

    def test_supplier_with_no_downstream_suppliers(self):
        report = simulate_supplier_disruption("SUP-T1-09", data=self.data, graph=self.graph)
        self.assertEqual(report["downstream_suppliers"], [])
        self.assertEqual(report["potential_cascading_materials"], [])
        self.assertEqual([m["material_id"] for m in report["direct_materials"]], ["MAT-17"])
        # SUP-T3-11 also lists MAT-17, but it is UPSTREAM of SUP-T1-09 (DEP-26), so it is not independent.
        self.assertEqual(backup_status(report, "MAT-17"), UNMITIGATED)
        reasons = report["backup_assessment"][0]["candidates"][0]["reasons"]
        self.assertTrue(any("upstream of SUP-T1-09" in r for r in reasons))

    def test_every_supplier_runs_on_the_real_dataset(self):
        for supplier_id in self.data["suppliers"]["supplier_id"]:
            with self.subTest(supplier=supplier_id):
                report = simulate_supplier_disruption(supplier_id, data=self.data, graph=self.graph)
                self.assertEqual(report["delivery_delay"]["status"], NOT_COMPUTED)
                self.assertEqual(report["production_days_remaining"]["status"], NOT_COMPUTED)
                self.assertEqual([d["supplier_id"] for d in report["downstream_suppliers"]],
                                 find_downstream_suppliers(self.graph, supplier_id))
                direct = {m["material_id"] for m in report["direct_materials"]}
                cascading = {m["material_id"] for m in report["potential_cascading_materials"]}
                self.assertFalse(direct & cascading)
                head = report["customer_orders"]["headline_path_supported"]["orders"]
                self.assertEqual(len({o["order_id"] for o in head}), len(head))
                json.dumps(report)

    def test_loads_data_and_graph_itself_when_not_given(self):
        report = simulate_supplier_disruption("SUP-T2-01")
        self.assertEqual(report["summary"]["headline_order_count"], 16)

    # ---- Member 1's data and graph stay untouched ---------------------------

    def test_real_data_and_graph_are_not_modified(self):
        def file_hashes():
            hashes = {}
            for name, file_name in CSV_FILES.items():
                with open(os.path.join(DATA_FOLDER, file_name), "rb") as handle:
                    hashes[name] = hashlib.sha256(handle.read()).hexdigest()
            return hashes

        data = load_all_data(verbose=False)
        graph = get_supply_chain_graph(data)
        hashes_before = file_hashes()
        data_before = {k: v.copy(deep=True) for k, v in data.items()}
        nodes_before = copy.deepcopy(dict(graph.nodes(data=True)))
        edges_before = copy.deepcopy(list(graph.edges(data=True)))
        for supplier_id in ("SUP-T2-01", "SUP-T3-04", "SUP-T2-03"):
            simulate_supplier_disruption(supplier_id, 7, data=data, graph=graph)
        self.assertEqual(file_hashes(), hashes_before)
        for name, table in data_before.items():
            pd.testing.assert_frame_equal(data[name], table)
        self.assertEqual(dict(graph.nodes(data=True)), nodes_before)
        self.assertEqual(list(graph.edges(data=True)), edges_before)


if __name__ == "__main__":
    unittest.main()
