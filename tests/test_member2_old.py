"""Automated tests for AUTOPILOT 2.0 Member 2 (Step 1: downstream supplier lookup)."""

import os
import sys
import unittest

import networkx as nx

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.data_loader import load_all_data
from src.supply_chain_graph import get_supply_chain_graph
from src.disruption_impact import find_downstream_suppliers


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


if __name__ == "__main__":
    unittest.main()
