"""Automated tests for AUTOPILOT 2.0 Member 1 (data + digital twin)."""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src import (
    SupplyChainGraph,
    detect_dependencies,
    find_multi_tier_dependencies,
    find_suppliers_sharing_upstream,
    find_upstream_dependencies,
    get_supply_chain_graph,
    list_direct_dependencies,
    load_all_data,
)
from src.data_loader import CSV_FILES, DATA_FOLDER


EXPECTED_COUNTS = {
    "suppliers": 35,
    "materials": 18,
    "factories": 3,
    "warehouses": 4,
    "transport_routes": 6,
    "customer_orders": 25,
    "inventory": 36,
    "supplier_dependencies": 31,
    "supplier_materials": 28,
}

NODE_TOTAL = (
    EXPECTED_COUNTS["suppliers"]
    + EXPECTED_COUNTS["materials"]
    + EXPECTED_COUNTS["factories"]
    + EXPECTED_COUNTS["warehouses"]
    + EXPECTED_COUNTS["transport_routes"]
    + EXPECTED_COUNTS["customer_orders"]
)


class Member1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_all_data(verbose=False)
        cls.graph = get_supply_chain_graph(cls.data)

    def test_csv_files_exist(self):
        for table_name, file_name in CSV_FILES.items():
            path = os.path.join(DATA_FOLDER, file_name)
            self.assertTrue(os.path.isfile(path), "missing %s (%s)" % (file_name, table_name))

    def test_tables_load_with_expected_counts(self):
        for name, expected in EXPECTED_COUNTS.items():
            self.assertIn(name, self.data)
            self.assertEqual(len(self.data[name]), expected, name)

    def test_required_ids_have_no_missing_values(self):
        checks = [
            ("suppliers", "supplier_id"),
            ("materials", "material_id"),
            ("factories", "factory_id"),
            ("warehouses", "warehouse_id"),
            ("transport_routes", "route_id"),
            ("customer_orders", "order_id"),
            ("inventory", "inventory_id"),
            ("supplier_dependencies", "dependency_id"),
        ]
        for table_name, column in checks:
            series = self.data[table_name][column]
            self.assertFalse(series.isna().any(), table_name)
            self.assertFalse((series.astype(str).str.strip() == "").any(), table_name)

    def test_no_duplicate_ids(self):
        unique_checks = [
            ("suppliers", "supplier_id"),
            ("materials", "material_id"),
            ("factories", "factory_id"),
            ("warehouses", "warehouse_id"),
            ("transport_routes", "route_id"),
            ("customer_orders", "order_id"),
            ("inventory", "inventory_id"),
            ("supplier_dependencies", "dependency_id"),
        ]
        for table_name, column in unique_checks:
            series = self.data[table_name][column]
            self.assertEqual(series.nunique(), len(series), table_name)

        maps = self.data["supplier_materials"]
        pair_count = maps.duplicated(["supplier_id", "material_id"]).sum()
        self.assertEqual(int(pair_count), 0)

    def test_foreign_keys_are_valid(self):
        suppliers = set(self.data["suppliers"]["supplier_id"].astype(str))
        materials = set(self.data["materials"]["material_id"].astype(str))
        factories = set(self.data["factories"]["factory_id"].astype(str))
        warehouses = set(self.data["warehouses"]["warehouse_id"].astype(str))
        routes = set(self.data["transport_routes"]["route_id"].astype(str))

        for supplier_id in self.data["suppliers"]["primary_route_id"].astype(str):
            self.assertIn(supplier_id, routes)
        for warehouse_id in self.data["factories"]["linked_warehouse_id"].astype(str):
            self.assertIn(warehouse_id, warehouses)
        for factory_id in self.data["warehouses"]["linked_factory_id"].astype(str):
            self.assertIn(factory_id, factories)
        for warehouse_id in self.data["customer_orders"]["warehouse_id"].astype(str):
            self.assertIn(warehouse_id, warehouses)
        for material_id in self.data["inventory"]["material_id"].astype(str):
            self.assertIn(material_id, materials)
        for location_id, location_type in zip(
            self.data["inventory"]["location_id"].astype(str),
            self.data["inventory"]["location_type"].astype(str),
        ):
            if location_type == "factory":
                self.assertIn(location_id, factories)
            else:
                self.assertIn(location_id, warehouses)

        deps = self.data["supplier_dependencies"]
        for down_id, up_id, material_id in zip(
            deps["downstream_supplier_id"].astype(str),
            deps["upstream_supplier_id"].astype(str),
            deps["material_id"].astype(str),
        ):
            self.assertIn(down_id, suppliers)
            self.assertIn(up_id, suppliers)
            self.assertIn(material_id, materials)
            self.assertNotEqual(down_id, up_id)

        maps = self.data["supplier_materials"]
        for supplier_id, material_id in zip(
            maps["supplier_id"].astype(str),
            maps["material_id"].astype(str),
        ):
            self.assertIn(supplier_id, suppliers)
            self.assertIn(material_id, materials)

        mapped_materials = set(maps["material_id"].astype(str))
        self.assertEqual(materials, mapped_materials)

    def test_graph_node_and_edge_counts(self):
        self.assertEqual(self.graph.number_of_nodes(), NODE_TOTAL)
        self.assertEqual(NODE_TOTAL, 91)
        self.assertEqual(self.graph.number_of_edges(), 528)

        type_counts = {}
        for node_id in self.graph.nodes:
            node_type = self.graph.nodes[node_id].get("node_type", "unknown")
            type_counts[node_type] = type_counts.get(node_type, 0) + 1

        self.assertEqual(type_counts["supplier"], 35)
        self.assertEqual(type_counts["material"], 18)
        self.assertEqual(type_counts["factory"], 3)
        self.assertEqual(type_counts["warehouse"], 4)
        self.assertEqual(type_counts["transport_route"], 6)
        self.assertEqual(type_counts["customer_order"], 25)
        self.assertEqual(sum(1 for _, degree in self.graph.degree() if degree == 0), 0)

    def test_every_dataset_id_is_a_graph_node(self):
        for supplier_id in self.data["suppliers"]["supplier_id"].astype(str):
            self.assertIn(supplier_id, self.graph)
        for material_id in self.data["materials"]["material_id"].astype(str):
            self.assertIn(material_id, self.graph)
        for factory_id in self.data["factories"]["factory_id"].astype(str):
            self.assertIn(factory_id, self.graph)
        for warehouse_id in self.data["warehouses"]["warehouse_id"].astype(str):
            self.assertIn(warehouse_id, self.graph)
        for route_id in self.data["transport_routes"]["route_id"].astype(str):
            self.assertIn(route_id, self.graph)
        for order_id in self.data["customer_orders"]["order_id"].astype(str):
            self.assertIn(order_id, self.graph)

    def test_dependency_edges_match_dataset(self):
        for row in self.data["supplier_dependencies"].to_dict("records"):
            upstream = str(row["upstream_supplier_id"])
            downstream = str(row["downstream_supplier_id"])
            self.assertTrue(self.graph.has_edge(upstream, downstream), (upstream, downstream))
            self.assertEqual(
                self.graph.edges[upstream, downstream]["edge_type"],
                "supplier_dependency",
            )

    def test_shared_upstream_with_real_data(self):
        shared = find_suppliers_sharing_upstream(self.graph, "SUP-T2-03")
        self.assertEqual(shared["SUP-T2-03"], ["SUP-T1-01", "SUP-T1-02"])

        all_shared = find_suppliers_sharing_upstream(self.graph)
        self.assertIn("SUP-T2-01", all_shared)
        self.assertEqual(all_shared["SUP-T2-01"], ["SUP-T1-03", "SUP-T1-04"])

        upstream = find_upstream_dependencies(self.graph, "SUP-T1-03")
        self.assertEqual(
            set(upstream),
            {"SUP-T2-01", "SUP-T3-01", "SUP-T3-02", "SUP-T3-03", "SUP-T3-04"},
        )

    def test_handover_api_and_class_wrapper(self):
        records = list_direct_dependencies(self.data)
        self.assertEqual(len(records), 31)
        self.assertIn("upstream_supplier_id", records[0])

        twin = SupplyChainGraph()
        twin.build_from_data(self.data)
        self.assertEqual(twin.get_graph().number_of_nodes(), 91)
        self.assertEqual(twin.find_suppliers_sharing_upstream("SUP-T2-03")["SUP-T2-03"], ["SUP-T1-01", "SUP-T1-02"])

        chains = find_multi_tier_dependencies(self.graph)
        self.assertIn("SUP-T1-03", chains)
        self.assertGreaterEqual(len(chains), 1)

        results = detect_dependencies(self.data, graph=self.graph)
        self.assertEqual(len(results["direct"]), 31)
        self.assertEqual(results["multi_tier_risks"], [])
        self.assertEqual(results["multi_tier"]["SUP-T1-03"], chains["SUP-T1-03"])


if __name__ == "__main__":
    unittest.main()
