"""
Automated tests for AUTOPILOT 2.0 Member 2.

Step 1: downstream supplier lookup (src/disruption_impact.py)
Step 2: supplier risk-factor table (src/supplier_risk.py)
"""

import copy
import csv
import hashlib
import os
import sys
import unittest
from collections import Counter

import networkx as nx
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.data_loader import CSV_FILES, DATA_FOLDER, load_all_data
from src.supply_chain_graph import get_supply_chain_graph
from src.disruption_impact import find_downstream_suppliers
from src.supplier_risk import (
    COLUMN_SOURCES,
    RISK_FACTOR_COLUMNS,
    _describe_inventory,
    _pooled_below_reorder,
    _summarise_inventory,
    assess_capacity,
    build_supplier_risk_factors,
    check_backup_candidate,
)


class DownstreamSupplierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_all_data(verbose=False)
        cls.graph = get_supply_chain_graph(cls.data)

    # ---- the two cases requested for Step 1 -------------------------------

    def test_cover_glass_supplier_reaches_both_display_makers(self):
        result = find_downstream_suppliers(self.graph, "SUP-T2-03")
        self.assertEqual(result, ["SUP-T1-01", "SUP-T1-02"])

    def test_copper_foil_supplier_reaches_eight_suppliers(self):
        result = find_downstream_suppliers(self.graph, "SUP-T3-04")
        self.assertEqual(len(result), 8)
        expected = {
            "SUP-T1-03", "SUP-T1-04", "SUP-T1-05", "SUP-T1-10",
            "SUP-T2-01", "SUP-T2-02", "SUP-T2-06", "SUP-T2-12",
        }
        self.assertEqual(set(result), expected)

    # ---- the rules from the requirements ----------------------------------

    def test_start_supplier_is_never_included(self):
        for supplier_id in ("SUP-T2-03", "SUP-T3-04", "SUP-T3-05", "SUP-T2-01"):
            self.assertNotIn(supplier_id, find_downstream_suppliers(self.graph, supplier_id))

    def test_no_duplicates(self):
        # SUP-T3-04 reaches SUP-T1-03 by several different paths.
        result = find_downstream_suppliers(self.graph, "SUP-T3-04")
        self.assertEqual(len(result), len(set(result)))

    def test_only_suppliers_are_returned(self):
        result = find_downstream_suppliers(self.graph, "SUP-T3-04")
        for node_id in result:
            self.assertEqual(self.graph.nodes[node_id]["node_type"], "supplier")

    def test_direction_is_downstream_not_upstream(self):
        # SUP-T2-03 is fed BY SUP-T3-09, so SUP-T3-09 must not appear.
        result = find_downstream_suppliers(self.graph, "SUP-T2-03")
        self.assertNotIn("SUP-T3-09", result)

    def test_tier_1_supplier_has_no_downstream_suppliers(self):
        self.assertEqual(find_downstream_suppliers(self.graph, "SUP-T1-07"), [])

    def test_unknown_or_non_supplier_id_raises_error(self):
        with self.assertRaises(ValueError):
            find_downstream_suppliers(self.graph, "SUP-NOPE")
        with self.assertRaises(ValueError):
            find_downstream_suppliers(self.graph, "MAT-04")   # a material, not a supplier

    # ---- cross-check against the raw CSV ----------------------------------

    def test_matches_independent_calculation_from_csv_for_every_supplier(self):
        """Rebuild the answer straight from supplier_dependencies.csv and compare."""
        rows = self.data["supplier_dependencies"]
        children = {}
        for _, row in rows.iterrows():
            children.setdefault(row["upstream_supplier_id"], set()).add(row["downstream_supplier_id"])

        def expected_for(start):
            seen, stack = set(), [start]
            while stack:
                for child in children.get(stack.pop(), ()):
                    if child not in seen:
                        seen.add(child)
                        stack.append(child)
            seen.discard(start)
            return seen

        for supplier_id in self.data["suppliers"]["supplier_id"]:
            self.assertEqual(
                set(find_downstream_suppliers(self.graph, supplier_id)),
                expected_for(supplier_id),
                supplier_id,
            )


class SmallToyGraphTests(unittest.TestCase):
    """Tiny hand-made graphs to prove the edge-type and loop rules."""

    def _supplier(self, graph, node_id, tier):
        graph.add_node(node_id, node_type="supplier", tier=tier)

    def test_ignores_edges_that_are_not_supplier_dependency(self):
        g = nx.DiGraph()
        self._supplier(g, "A", 3)
        self._supplier(g, "B", 2)
        self._supplier(g, "C", 1)
        g.add_node("MAT-X", node_type="material")
        g.add_edge("A", "B", edge_type="supplier_dependency")
        g.add_edge("A", "C", edge_type="uses_route")        # decoy: wrong edge type
        g.add_edge("A", "MAT-X", edge_type="supplies")      # decoy: not a supplier
        self.assertEqual(find_downstream_suppliers(g, "A"), ["B"])

    def test_does_not_loop_forever_and_excludes_start_in_a_cycle(self):
        g = nx.DiGraph()
        self._supplier(g, "A", 2)
        self._supplier(g, "B", 1)
        g.add_edge("A", "B", edge_type="supplier_dependency")
        g.add_edge("B", "A", edge_type="supplier_dependency")  # makes a loop
        self.assertEqual(find_downstream_suppliers(g, "A"), ["B"])

    def test_does_not_change_the_graph(self):
        g = nx.DiGraph()
        self._supplier(g, "A", 2)
        self._supplier(g, "B", 1)
        g.add_edge("A", "B", edge_type="supplier_dependency")
        nodes_before, edges_before = list(g.nodes(data=True)), list(g.edges(data=True))
        find_downstream_suppliers(g, "A")
        self.assertEqual(list(g.nodes(data=True)), nodes_before)
        self.assertEqual(list(g.edges(data=True)), edges_before)


# ===========================================================================
# STEP 2: supplier risk-factor table
# ===========================================================================

REQUIRED_COLUMNS = [
    "supplier_id",
    "supplier_name",
    "tier",
    "lead_time_days",
    "quality_score",
    "capacity_status",
    "number_of_upstream_suppliers",
    "number_of_downstream_suppliers",
    "number_of_single_source_materials",
    "number_of_genuine_independent_backups",
    # inventory buffer information
    "inventory_rows_for_supplied_materials",
    "inventory_rows_below_reorder_point",
    "materials_below_reorder_point_pooled",
    "inventory_buffer_detail",
]


def read_csv_file(table_name):
    """Read an original CSV straight from disk (not through Member 1's loader)."""
    path = os.path.join(DATA_FOLDER, CSV_FILES[table_name])
    with open(path, newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def hash_all_csv_files():
    """Fingerprint of every CSV file, to prove the files are not changed."""
    fingerprints = {}
    for table_name, file_name in CSV_FILES.items():
        with open(os.path.join(DATA_FOLDER, file_name), "rb") as handle:
            fingerprints[table_name] = hashlib.sha256(handle.read()).hexdigest()
    return fingerprints


def reachable(links, start):
    """All nodes reachable from `start` by following links {node: set(next nodes)}."""
    seen, stack = set(), [start]
    while stack:
        for nxt in links.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    seen.discard(start)
    return seen


class RiskFactorTableTests(unittest.TestCase):
    """Checks the real table against numbers recomputed straight from the CSV files."""

    @classmethod
    def setUpClass(cls):
        cls.data = load_all_data(verbose=False)
        cls.graph = get_supply_chain_graph(cls.data)
        cls.table = build_supplier_risk_factors(cls.data, cls.graph)
        cls.by_id = cls.table.set_index("supplier_id")

        cls.csv_suppliers = read_csv_file("suppliers")
        cls.csv_materials_of = {}   # supplier_id -> sorted material ids
        cls.csv_suppliers_of = {}   # material_id -> set of supplier ids
        for row in read_csv_file("supplier_materials"):
            cls.csv_materials_of.setdefault(row["supplier_id"], set()).add(row["material_id"])
            cls.csv_suppliers_of.setdefault(row["material_id"], set()).add(row["supplier_id"])

    # ---- shape and columns ------------------------------------------------

    def test_exactly_35_suppliers_one_row_each(self):
        self.assertEqual(len(self.table), 35)
        csv_ids = [row["supplier_id"] for row in self.csv_suppliers]
        self.assertEqual(sorted(self.table["supplier_id"]), sorted(csv_ids))

    def test_no_duplicate_supplier_ids(self):
        self.assertEqual(self.table["supplier_id"].nunique(), len(self.table))

    def test_all_required_columns_are_present(self):
        for column in REQUIRED_COLUMNS:
            self.assertIn(column, self.table.columns, column)
        self.assertEqual(list(self.table.columns), RISK_FACTOR_COLUMNS)

    def test_every_column_is_labelled_dataset_count_or_rule(self):
        self.assertEqual(set(COLUMN_SOURCES), set(self.table.columns))
        for label in COLUMN_SOURCES.values():
            self.assertTrue(
                label.startswith(("dataset value", "counted from dataset", "rule-based")), label
            )

    def test_no_scores_or_risk_categories_exist_yet(self):
        forbidden = {
            "risk_score", "risk_category", "risk_level", "risk_rating",
            "vulnerability_score", "criticality_score", "overall_risk_score",
        }
        self.assertTrue(forbidden.isdisjoint(self.table.columns))

    # ---- values copied from suppliers.csv ----------------------------------

    def test_lead_time_and_quality_match_original_csv(self):
        for row in self.csv_suppliers:
            ours = self.by_id.loc[row["supplier_id"]]
            self.assertEqual(int(ours["lead_time_days"]), int(row["lead_time_days"]), row["supplier_id"])
            self.assertEqual(int(ours["quality_score"]), int(row["quality_score"]), row["supplier_id"])

    def test_name_tier_and_capacity_status_match_original_csv(self):
        for row in self.csv_suppliers:
            ours = self.by_id.loc[row["supplier_id"]]
            self.assertEqual(ours["supplier_name"], row["supplier_name"])
            self.assertEqual(int(ours["tier"]), int(row["tier"]))
            self.assertEqual(ours["capacity_status"], row["capacity_status"])

    # ---- upstream / downstream counts -------------------------------------

    def test_upstream_and_downstream_counts_match_csv_for_every_supplier(self):
        parents, children = {}, {}
        for row in read_csv_file("supplier_dependencies"):
            parents.setdefault(row["downstream_supplier_id"], set()).add(row["upstream_supplier_id"])
            children.setdefault(row["upstream_supplier_id"], set()).add(row["downstream_supplier_id"])

        for supplier_id in self.by_id.index:
            ours = self.by_id.loc[supplier_id]
            self.assertEqual(
                int(ours["number_of_upstream_suppliers"]),
                len(reachable(parents, supplier_id)),
                supplier_id + " upstream",
            )
            self.assertEqual(
                int(ours["number_of_downstream_suppliers"]),
                len(reachable(children, supplier_id)),
                supplier_id + " downstream",
            )

    def test_known_upstream_and_downstream_examples(self):
        self.assertEqual(self.by_id.loc["SUP-T1-03", "number_of_upstream_suppliers"], 5)
        self.assertEqual(self.by_id.loc["SUP-T3-04", "number_of_downstream_suppliers"], 8)
        self.assertEqual(self.by_id.loc["SUP-T2-03", "number_of_downstream_suppliers"], 2)
        self.assertEqual(self.by_id.loc["SUP-T1-07", "number_of_downstream_suppliers"], 0)

    # ---- single-source materials ------------------------------------------

    def test_single_source_counts_match_csv_for_every_mapped_supplier(self):
        for supplier_id, materials in self.csv_materials_of.items():
            expected = sorted(m for m in materials if len(self.csv_suppliers_of[m]) == 1)
            ours = self.by_id.loc[supplier_id]
            self.assertEqual(int(ours["number_of_single_source_materials"]), len(expected), supplier_id)
            listed = [m for m in ours["single_source_materials"].split("; ") if m]
            self.assertEqual(listed, expected, supplier_id)

    def test_the_eight_single_source_materials_are_found(self):
        found = set()
        for text in self.table["single_source_materials"]:
            found.update(m for m in text.split("; ") if m)
        self.assertEqual(
            found,
            {"MAT-06", "MAT-07", "MAT-08", "MAT-09", "MAT-10", "MAT-14", "MAT-16", "MAT-18"},
        )

    def test_a_flagged_backup_pair_is_not_single_source(self):
        # MAT-02 is listed for SUP-T1-03 and SUP-T1-04, so neither is single-source for it.
        self.assertEqual(self.by_id.loc["SUP-T1-03", "number_of_single_source_materials"], 0)
        self.assertEqual(self.by_id.loc["SUP-T1-04", "number_of_single_source_materials"], 0)

    def test_suppliers_without_material_mapping_are_included_with_empty_not_zero(self):
        unmapped = sorted(set(self.by_id.index) - set(self.csv_materials_of))
        self.assertEqual(len(unmapped), 8)
        for supplier_id in unmapped:
            ours = self.by_id.loc[supplier_id]
            self.assertFalse(ours["has_material_mapping"])
            self.assertTrue(pd.isna(ours["number_of_single_source_materials"]), supplier_id)
            self.assertTrue(pd.isna(ours["number_of_genuine_independent_backups"]), supplier_id)
            self.assertTrue(pd.isna(ours["inventory_rows_for_supplied_materials"]), supplier_id)
            self.assertEqual(int(ours["number_of_materials_supplied"]), 0)

    # ---- genuine backups (real data) --------------------------------------

    def test_shared_upstream_alternatives_are_not_counted_as_independent(self):
        # SUP-T1-03 / SUP-T1-04 (MAT-02) and SUP-T1-01 / SUP-T1-02 (MAT-03) share upstream suppliers.
        for supplier_id in ("SUP-T1-03", "SUP-T1-04", "SUP-T1-01", "SUP-T1-02"):
            self.assertEqual(self.by_id.loc[supplier_id, "number_of_genuine_independent_backups"], 0)
        text = self.by_id.loc["SUP-T1-04", "backup_assessment"]
        self.assertIn("NOT genuine", text)
        self.assertIn("shares upstream supplier(s) SUP-T2-01", text)
        self.assertIn("[dataset flags it as a backup]", self.by_id.loc["SUP-T1-03", "backup_assessment"])

    def test_parent_child_alternatives_are_not_counted_as_independent(self):
        # SUP-T1-06 buys from SUP-T2-07, so it cannot back SUP-T2-07 up.
        text = self.by_id.loc["SUP-T2-07", "backup_assessment"]
        self.assertIn("SUP-T1-06 depends on SUP-T2-07", text)
        self.assertEqual(self.by_id.loc["SUP-T2-07", "number_of_genuine_independent_backups"], 0)

    def test_capacity_problem_is_reported_for_a_smaller_alternative(self):
        text = self.by_id.loc["SUP-T1-03", "backup_assessment"]
        self.assertIn("capacity insufficient: 5000 vs 9000", text)

    def test_current_dataset_has_no_genuine_independent_backups(self):
        # A finding about TODAY's data (all 10 two-supplier materials fail independence).
        # If Member 1 later adds a truly independent backup, update this test on purpose.
        mapped = self.table[self.table["has_material_mapping"]]
        self.assertTrue((mapped["number_of_genuine_independent_backups"] == 0).all())
        self.assertTrue(
            (mapped["number_of_materials_without_genuine_backup"] == mapped["number_of_materials_supplied"]).all()
        )

    # ---- inventory ---------------------------------------------------------

    def test_inventory_columns_match_inventory_csv_for_every_mapped_supplier(self):
        per_material = {}
        for row in read_csv_file("inventory"):
            entry = per_material.setdefault(
                row["material_id"], {"rows": 0, "below": 0, "on_hand": 0, "reorder": 0}
            )
            entry["rows"] += 1
            entry["on_hand"] += int(row["quantity_on_hand"])
            entry["reorder"] += int(row["reorder_point"])
            if int(row["quantity_on_hand"]) < int(row["reorder_point"]):
                entry["below"] += 1

        for supplier_id, materials in self.csv_materials_of.items():
            ours = self.by_id.loc[supplier_id]
            self.assertEqual(
                int(ours["inventory_rows_for_supplied_materials"]),
                sum(per_material[m]["rows"] for m in materials), supplier_id)
            self.assertEqual(
                int(ours["inventory_rows_below_reorder_point"]),
                sum(per_material[m]["below"] for m in materials), supplier_id)
            self.assertEqual(
                int(ours["materials_below_reorder_point_pooled"]),
                sum(1 for m in materials if per_material[m]["on_hand"] < per_material[m]["reorder"]),
                supplier_id)
            # The exact numbers also appear in the readable text.
            for material_id in materials:
                self.assertIn(
                    "on hand " + str(per_material[material_id]["on_hand"])
                    + " vs reorder point " + str(per_material[material_id]["reorder"]),
                    ours["inventory_buffer_detail"], supplier_id + " " + material_id)

    def test_known_inventory_examples(self):
        row = self.by_id.loc["SUP-T2-01"]          # supplies MAT-01
        self.assertEqual(row["inventory_rows_for_supplied_materials"], 2)
        self.assertEqual(row["inventory_rows_below_reorder_point"], 2)
        self.assertIn("MAT-01: 2 location(s), on hand 3000 vs reorder point 7000", row["inventory_buffer_detail"])
        self.assertEqual(self.by_id.loc["SUP-T2-03", "inventory_rows_below_reorder_point"], 0)  # MAT-04

    def test_no_days_of_cover_columns_exist(self):
        for column in self.table.columns:
            self.assertNotIn("days", column.replace("lead_time_days", ""))

    # ---- calling the function in different ways ----------------------------

    def test_loads_data_and_graph_itself_when_not_given(self):
        again = build_supplier_risk_factors()
        pd.testing.assert_frame_equal(again, self.table)

    def test_empty_supplier_table_gives_empty_table_with_columns(self):
        empty = build_supplier_risk_factors({"suppliers": pd.DataFrame()}, nx.DiGraph())
        self.assertEqual(len(empty), 0)
        self.assertEqual(list(empty.columns), RISK_FACTOR_COLUMNS)

    def test_supplier_missing_from_graph_still_gets_a_row_with_empty_counts(self):
        graph = self.graph.copy()
        graph.remove_node("SUP-T2-11")
        table = build_supplier_risk_factors(self.data, graph)
        self.assertEqual(len(table), 35)
        row = table.set_index("supplier_id").loc["SUP-T2-11"]
        self.assertTrue(pd.isna(row["number_of_upstream_suppliers"]))
        self.assertTrue(pd.isna(row["number_of_downstream_suppliers"]))
        self.assertEqual(int(row["lead_time_days"]), 7)   # dataset values still present

    # ---- Member 1's data and graph must stay unchanged ---------------------

    def test_member1_data_graph_and_csv_files_are_unchanged(self):
        data = load_all_data(verbose=False)
        graph = get_supply_chain_graph(data)

        tables_before = {name: frame.copy(deep=True) for name, frame in data.items()}
        nodes_before = copy.deepcopy(list(graph.nodes(data=True)))
        edges_before = copy.deepcopy(list(graph.edges(data=True)))
        files_before = hash_all_csv_files()

        build_supplier_risk_factors(data, graph)

        for name, frame in data.items():
            self.assertTrue(frame.equals(tables_before[name]), name + " table changed")
        self.assertEqual(list(graph.nodes(data=True)), nodes_before)
        self.assertEqual(list(graph.edges(data=True)), edges_before)
        self.assertEqual(hash_all_csv_files(), files_before)


class BackupLogicUnitTests(unittest.TestCase):
    """The backup rules, tested directly on tiny hand-made inputs."""

    def setUp(self):
        # P and A are independent; S shares an upstream supplier with P.
        self.upstream_of = {"P": {"X"}, "A": {"Y"}, "S": {"X"}, "KID": {"P"}, "PARENT": set()}
        self.rows = {
            ("P", "M"): {"monthly_capacity_units": 1000, "is_backup": 0},
            ("A", "M"): {"monthly_capacity_units": 1500, "is_backup": 1},
            ("S", "M"): {"monthly_capacity_units": 1500, "is_backup": 0},
            ("KID", "M"): {"monthly_capacity_units": 1500, "is_backup": 0},
            ("PARENT", "M"): {"monthly_capacity_units": 1500, "is_backup": 0},
        }
        self.info = {name: {"capacity_status": "sufficient"} for name in ("P", "A", "S", "KID", "PARENT")}

    def check(self, candidate):
        return check_backup_candidate("P", candidate, "M", self.upstream_of, self.rows, self.info)

    def test_independent_same_material_with_enough_capacity_is_genuine(self):
        self.assertTrue(self.check("A")["is_genuine"])

    def test_shared_upstream_supplier_is_not_genuine(self):
        result = self.check("S")
        self.assertFalse(result["independent"])
        self.assertFalse(result["is_genuine"])

    def test_candidate_that_depends_on_the_primary_is_not_genuine(self):
        self.assertFalse(self.check("KID")["is_genuine"])

    def test_candidate_that_feeds_the_primary_is_not_genuine(self):
        self.upstream_of["P"] = {"X", "PARENT"}
        self.assertFalse(self.check("PARENT")["is_genuine"])

    def test_candidate_that_does_not_supply_the_material_is_not_genuine(self):
        del self.rows[("A", "M")]
        result = self.check("A")
        self.assertFalse(result["same_material"])
        self.assertFalse(result["is_genuine"])

    def test_unknown_independence_is_not_genuine(self):
        del self.upstream_of["A"]
        result = self.check("A")
        self.assertIsNone(result["independent"])
        self.assertFalse(result["is_genuine"])

    def test_capacity_unknown_is_different_from_capacity_insufficient(self):
        self.assertEqual(assess_capacity(1000, 1500, "sufficient")[0], "sufficient")
        self.assertEqual(assess_capacity(1000, 400, "sufficient")[0], "insufficient")
        self.assertEqual(assess_capacity(1000, None, "sufficient")[0], "unknown")
        self.assertEqual(assess_capacity(1000, float("nan"), "sufficient")[0], "unknown")
        self.assertEqual(assess_capacity(None, 1500, "sufficient")[0], "unknown")
        self.assertEqual(assess_capacity(1000, 1500, "insufficient")[0], "insufficient")

    def test_capacity_unknown_blocks_a_genuine_backup(self):
        self.rows[("A", "M")]["monthly_capacity_units"] = None
        result = self.check("A")
        self.assertEqual(result["capacity_status"], "unknown")
        self.assertFalse(result["is_genuine"])


class BackupLogicWithModifiedDataTests(unittest.TestCase):
    """
    Full-table check on COPIES of the data, where we add one extra supplier
    row for MAT-14. SUP-T2-11 normally is the only MAT-14 supplier
    (capacity 35000, upstream SUP-T3-07). The original data is never touched.
    """

    @classmethod
    def setUpClass(cls):
        cls.original = load_all_data(verbose=False)

    def table_with_extra_mat14_supplier(self, extra_supplier_id, capacity, supplier_changes=None):
        data = {name: frame.copy(deep=True) for name, frame in self.original.items()}
        extra_row = pd.DataFrame([{
            "supplier_id": extra_supplier_id, "material_id": "MAT-14", "is_backup": 1,
            "unit_cost_inr": 12, "monthly_capacity_units": capacity,
            "lead_time_days": 6, "moq_units": 100,
        }])
        data["supplier_materials"] = pd.concat([data["supplier_materials"], extra_row], ignore_index=True)
        if supplier_changes:
            suppliers = data["suppliers"]
            for column, value in supplier_changes.items():
                suppliers.loc[suppliers["supplier_id"] == extra_supplier_id, column] = value
        graph = get_supply_chain_graph(data)
        return build_supplier_risk_factors(data, graph).set_index("supplier_id")

    def test_independent_alternative_with_enough_capacity_counts(self):
        # SUP-T2-13 uses SUP-T3-12 (different upstream) and has 40000 >= 35000.
        row = self.table_with_extra_mat14_supplier("SUP-T2-13", 40000).loc["SUP-T2-11"]
        self.assertEqual(row["number_of_genuine_independent_backups"], 1)
        self.assertEqual(row["number_of_single_source_materials"], 0)
        self.assertEqual(row["number_of_materials_without_genuine_backup"], 0)
        self.assertIn("GENUINE", row["backup_assessment"])

    def test_independent_alternative_with_too_little_capacity_does_not_count(self):
        row = self.table_with_extra_mat14_supplier("SUP-T2-13", 10000).loc["SUP-T2-11"]
        self.assertEqual(row["number_of_genuine_independent_backups"], 0)
        self.assertIn("capacity insufficient: 10000 vs 35000", row["backup_assessment"])

    def test_independent_alternative_with_missing_capacity_is_unknown_not_insufficient(self):
        row = self.table_with_extra_mat14_supplier("SUP-T2-13", float("nan")).loc["SUP-T2-11"]
        self.assertEqual(row["number_of_genuine_independent_backups"], 0)
        self.assertIn("capacity unknown", row["backup_assessment"])
        self.assertNotIn("capacity insufficient", row["backup_assessment"])

    def test_alternative_marked_insufficient_in_suppliers_csv_does_not_count(self):
        table = self.table_with_extra_mat14_supplier(
            "SUP-T2-13", 40000, supplier_changes={"capacity_status": "insufficient"})
        row = table.loc["SUP-T2-11"]
        self.assertEqual(row["number_of_genuine_independent_backups"], 0)
        self.assertIn("marked 'insufficient' in suppliers.csv", row["backup_assessment"])

    def test_alternative_sharing_an_upstream_supplier_does_not_count(self):
        # SUP-T2-07 and SUP-T2-11 both depend on SUP-T3-07, even with plenty of capacity.
        row = self.table_with_extra_mat14_supplier("SUP-T2-07", 99999).loc["SUP-T2-11"]
        self.assertEqual(row["number_of_genuine_independent_backups"], 0)
        self.assertIn("shares upstream supplier(s) SUP-T3-07", row["backup_assessment"])
        # ...but it is no longer a single-source material on paper.
        self.assertEqual(row["number_of_single_source_materials"], 0)

    def test_original_data_is_untouched_by_these_experiments(self):
        files_before = hash_all_csv_files()
        self.table_with_extra_mat14_supplier("SUP-T2-13", 40000)
        self.assertEqual(hash_all_csv_files(), files_before)
        self.assertEqual(len(self.original["supplier_materials"]), 28)


class InventoryMissingValueTests(unittest.TestCase):
    """
    Pooled inventory status when some inventory values are missing.

    Rule: if ANY row of a material has a missing quantity_on_hand or
    reorder_point, the pooled status is UNKNOWN (never BELOW or ABOVE).
    These tests use tiny hand-made inventory tables for one material, MAT-X.
    The numbers are chosen so that adding up only the rows WITH values would
    give a clear (but wrong) BELOW or ABOVE answer.
    """

    def analyse(self, rows):
        """rows = list of (quantity_on_hand, reorder_point). Returns what the three helpers say."""
        inventory = pd.DataFrame(
            [{"material_id": "MAT-X", "quantity_on_hand": q, "reorder_point": r} for q, r in rows]
        )
        entry = _summarise_inventory(inventory)["MAT-X"]
        return entry, _pooled_below_reorder(entry), _describe_inventory("MAT-X", entry)

    def assert_unknown(self, entry, pooled, text):
        """The three things every UNKNOWN result must show."""
        self.assertIsNone(pooled)
        self.assertIn("pooled status UNKNOWN", text)
        self.assertIn("pooled stock cannot be determined", text)
        # It must not be classified either way, and no pooled totals shown.
        self.assertNotIn("pooled stock BELOW", text)
        self.assertNotIn("at/above reorder point", text)
        self.assertNotIn("on hand", text)

    # ---- 1. all rows valid ----------------------------------------------------

    def test_all_rows_valid_pooled_above(self):
        # One location is below its own reorder point, but pooled 600 >= 500.
        entry, pooled, text = self.analyse([(100, 200), (500, 300)])
        self.assertIs(pooled, False)
        self.assertEqual(entry["missing_rows"], 0)
        self.assertIn("on hand 600 vs reorder point 500", text)
        self.assertIn("1 of 2 location(s) below reorder point", text)
        self.assertIn("pooled stock at/above reorder point", text)
        self.assertNotIn("UNKNOWN", text)

    def test_all_rows_valid_pooled_below(self):
        entry, pooled, text = self.analyse([(100, 200), (100, 300)])
        self.assertIs(pooled, True)
        self.assertIn("on hand 200 vs reorder point 500", text)
        self.assertIn("pooled stock BELOW reorder point", text)
        self.assertNotIn("UNKNOWN", text)

    # ---- 2. one row has a missing quantity -----------------------------------

    def test_one_missing_quantity_makes_pooled_status_unknown(self):
        # Valid rows alone would say BELOW (200 < 500). Must be UNKNOWN instead.
        entry, pooled, text = self.analyse([(100, 200), (None, 300), (100, 300)])
        self.assertEqual(entry["missing_rows"], 1)
        self.assert_unknown(entry, pooled, text)
        self.assertIn("1 of 3 location(s)", text)

    # ---- 3. one row has a missing reorder point -------------------------------

    def test_one_missing_reorder_point_makes_pooled_status_unknown(self):
        # Valid rows alone would say ABOVE (1000 >= 300). Must be UNKNOWN instead.
        entry, pooled, text = self.analyse([(100, 200), (500, None), (900, 100)])
        self.assertEqual(entry["missing_rows"], 1)
        self.assert_unknown(entry, pooled, text)
        self.assertIn("1 of 3 location(s)", text)

    def test_non_numeric_text_counts_as_missing(self):
        entry, pooled, text = self.analyse([(100, 200), ("n/a", 300), (900, 100)])
        self.assertEqual(entry["missing_rows"], 1)
        self.assert_unknown(entry, pooled, text)

    # ---- 4. all rows missing --------------------------------------------------

    def test_all_rows_missing_makes_pooled_status_unknown(self):
        entry, pooled, text = self.analyse([(None, 200), (100, None), (None, None)])
        self.assertEqual(entry["missing_rows"], 3)
        self.assert_unknown(entry, pooled, text)
        self.assertIn("3 of 3 location(s)", text)

    # ---- extra safety checks --------------------------------------------------

    def test_no_inventory_rows_at_all_is_unknown(self):
        self.assertIsNone(_pooled_below_reorder(None))
        self.assertIn("no rows in inventory.csv", _describe_inventory("MAT-X", None))

    def test_known_per_location_facts_are_still_reported_when_unknown(self):
        # The two complete rows are both below their own reorder points; that
        # row-level fact is still true, so it stays in the explanation.
        entry, pooled, text = self.analyse([(100, 200), (None, 300), (100, 300)])
        self.assertEqual(entry["below_rows"], 2)
        self.assertIn("of the 2 location(s) with complete values, 2 are below reorder point", text)

    def test_one_materials_missing_data_does_not_affect_another_material(self):
        inventory = pd.DataFrame([
            {"material_id": "MAT-A", "quantity_on_hand": None, "reorder_point": 100},
            {"material_id": "MAT-B", "quantity_on_hand": 50, "reorder_point": 100},
        ])
        summary = _summarise_inventory(inventory)
        self.assertIsNone(_pooled_below_reorder(summary["MAT-A"]))
        self.assertIs(_pooled_below_reorder(summary["MAT-B"]), True)


if __name__ == "__main__":
    unittest.main()
