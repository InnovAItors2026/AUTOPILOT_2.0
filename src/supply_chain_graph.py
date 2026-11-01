"""
supply_chain_graph.py
---------------------
Builds the Supply Chain Digital Twin as a NetworkX graph.

Nodes come from the CSV tables:
suppliers, materials, factories, warehouses, transport routes, and orders.

Edges come from the real links in those tables. This file does not
create extra suppliers, materials, or other records.
"""

import networkx as nx
import pandas as pd


def _rows(table):
    """Turn a pandas DataFrame into a list of dictionaries."""
    if table is None or len(table) == 0:
        return []
    return table.to_dict("records")


def _text(value):
    """Convert a CSV cell to text. Empty cells and NaN become ''."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _number(value, fallback=None):
    """Keep numbers when they exist. Otherwise return fallback."""
    if value is None or pd.isna(value):
        return fallback
    return value


def _add_node(graph, node_id, node_type, attributes):
    """Add a node once. Skip blank IDs."""
    node_id = _text(node_id)
    if not node_id:
        return
    if node_id not in graph:
        graph.add_node(node_id, node_type=node_type, **attributes)


def _add_edge(graph, from_id, to_id, edge_type, attributes=None):
    """Add an edge only when both nodes already exist."""
    from_id = _text(from_id)
    to_id = _text(to_id)
    if not from_id or not to_id:
        return
    if from_id not in graph or to_id not in graph:
        return
    graph.add_edge(from_id, to_id, edge_type=edge_type, **(attributes or {}))


def _add_supplier_nodes(graph, data):
    for row in _rows(data.get("suppliers")):
        city = _text(row.get("city"))
        state = _text(row.get("state"))
        _add_node(
            graph,
            row.get("supplier_id"),
            "supplier",
            {
                "name": _text(row.get("supplier_name")),
                "tier": _number(row.get("tier")),
                "material": _text(row.get("category")),
                "capacity": _number(row.get("monthly_capacity_units")),
                "capacity_status": _text(row.get("capacity_status")),
                "location": city + ", " + state if city and state else city,
                "city": city,
                "state": state,
                "country": _text(row.get("country")),
                "category": _text(row.get("category")),
                "lead_time_days": _number(row.get("lead_time_days")),
                "quality_score": _number(row.get("quality_score")),
                "primary_route_id": _text(row.get("primary_route_id")),
            },
        )


def _add_material_nodes(graph, data):
    for row in _rows(data.get("materials")):
        _add_node(
            graph,
            row.get("material_id"),
            "material",
            {
                "name": _text(row.get("material_name")),
                "material": _text(row.get("material_name")),
                "category": _text(row.get("category")),
                "unit": _text(row.get("unit")),
                "unit_cost_inr": _number(row.get("unit_cost_inr")),
                "lead_time_days": _number(row.get("typical_lead_time_days")),
                "used_in_product": _text(row.get("used_in_product")),
            },
        )


def _add_factory_nodes(graph, data):
    for row in _rows(data.get("factories")):
        city = _text(row.get("city"))
        state = _text(row.get("state"))
        _add_node(
            graph,
            row.get("factory_id"),
            "factory",
            {
                "name": _text(row.get("factory_name")),
                "capacity": _number(row.get("monthly_capacity_units")),
                "location": city + ", " + state if city and state else city,
                "city": city,
                "state": state,
                "country": _text(row.get("country")),
                "product_focus": _text(row.get("product_focus")),
                "linked_warehouse_id": _text(row.get("linked_warehouse_id")),
            },
        )


def _add_warehouse_nodes(graph, data):
    for row in _rows(data.get("warehouses")):
        city = _text(row.get("city"))
        state = _text(row.get("state"))
        _add_node(
            graph,
            row.get("warehouse_id"),
            "warehouse",
            {
                "name": _text(row.get("warehouse_name")),
                "capacity": _number(row.get("capacity_units")),
                "location": city + ", " + state if city and state else city,
                "city": city,
                "state": state,
                "country": _text(row.get("country")),
                "serves_region": _text(row.get("serves_region")),
                "linked_factory_id": _text(row.get("linked_factory_id")),
            },
        )


def _add_route_nodes(graph, data):
    for row in _rows(data.get("transport_routes")):
        _add_node(
            graph,
            row.get("route_id"),
            "transport_route",
            {
                "name": _text(row.get("origin_name")) + " -> " + _text(row.get("destination_name")),
                "origin_id": _text(row.get("origin_id")),
                "destination_id": _text(row.get("destination_id")),
                "mode": _text(row.get("mode")),
                "distance_km": _number(row.get("distance_km")),
                "transit_days": _number(row.get("transit_days")),
                "cost_per_shipment_inr": _number(row.get("cost_per_shipment_inr")),
                "cargo": _text(row.get("cargo")),
                "shared_supplier_ids": _text(row.get("shared_supplier_ids")),
            },
        )


def _add_order_nodes(graph, data):
    for row in _rows(data.get("customer_orders")):
        city = _text(row.get("city"))
        state = _text(row.get("state"))
        _add_node(
            graph,
            row.get("order_id"),
            "customer_order",
            {
                "name": _text(row.get("customer_name")),
                "customer_name": _text(row.get("customer_name")),
                "location": city + ", " + state if city and state else city,
                "city": city,
                "state": state,
                "warehouse_id": _text(row.get("warehouse_id")),
                "product_name": _text(row.get("product_name")),
                "quantity": _number(row.get("quantity")),
                "unit_price_inr": _number(row.get("unit_price_inr")),
                "order_value_inr": _number(row.get("order_value_inr")),
                "status": _text(row.get("status")),
            },
        )


def _add_supplier_dependency_edges(graph, data):
    """Tier 1 / 2 / 3 links: goods flow from upstream supplier to downstream supplier."""
    for row in _rows(data.get("supplier_dependencies")):
        _add_edge(
            graph,
            row.get("upstream_supplier_id"),
            row.get("downstream_supplier_id"),
            "supplier_dependency",
            {
                "dependency_id": _text(row.get("dependency_id")),
                "material_id": _text(row.get("material_id")),
                "dependency_type": _text(row.get("dependency_type")),
                "notes": _text(row.get("notes")),
            },
        )


def _add_supplier_material_edges(graph, data):
    for row in _rows(data.get("supplier_materials")):
        _add_edge(
            graph,
            row.get("supplier_id"),
            row.get("material_id"),
            "supplies",
            {
                "is_backup": _number(row.get("is_backup")),
                "unit_cost_inr": _number(row.get("unit_cost_inr")),
                "monthly_capacity_units": _number(row.get("monthly_capacity_units")),
                "lead_time_days": _number(row.get("lead_time_days")),
                "moq_units": _number(row.get("moq_units")),
            },
        )


def _add_inventory_edges(graph, data):
    for row in _rows(data.get("inventory")):
        _add_edge(
            graph,
            row.get("location_id"),
            row.get("material_id"),
            "holds_inventory",
            {
                "inventory_id": _text(row.get("inventory_id")),
                "quantity_on_hand": _number(row.get("quantity_on_hand")),
                "reorder_point": _number(row.get("reorder_point")),
                "max_stock": _number(row.get("max_stock")),
            },
        )


def _add_factory_warehouse_edges(graph, data):
    for row in _rows(data.get("factories")):
        _add_edge(
            graph,
            row.get("factory_id"),
            row.get("linked_warehouse_id"),
            "feeds_warehouse",
            {},
        )
    for row in _rows(data.get("warehouses")):
        _add_edge(
            graph,
            row.get("linked_factory_id"),
            row.get("warehouse_id"),
            "feeds_warehouse",
            {},
        )


def _add_route_edges(graph, data):
    for row in _rows(data.get("transport_routes")):
        route_id = row.get("route_id")
        _add_edge(graph, row.get("origin_id"), route_id, "enters_route", {})
        _add_edge(graph, route_id, row.get("destination_id"), "leaves_route", {})

        shared = _text(row.get("shared_supplier_ids"))
        if shared:
            for supplier_id in shared.split(";"):
                _add_edge(graph, supplier_id, route_id, "uses_route", {"shared": True})

    for row in _rows(data.get("suppliers")):
        _add_edge(
            graph,
            row.get("supplier_id"),
            row.get("primary_route_id"),
            "uses_route",
            {},
        )


def _add_order_edges(graph, data):
    for row in _rows(data.get("customer_orders")):
        _add_edge(
            graph,
            row.get("warehouse_id"),
            row.get("order_id"),
            "fulfills_order",
            {},
        )

    # Connect materials to orders when the material's product list matches the order.
    product_to_materials = {}
    for row in _rows(data.get("materials")):
        material_id = _text(row.get("material_id"))
        products = _text(row.get("used_in_product"))
        if not material_id or not products:
            continue
        for product_name in products.split(";"):
            product_name = product_name.strip()
            if product_name:
                product_to_materials.setdefault(product_name, []).append(material_id)

    for row in _rows(data.get("customer_orders")):
        product_name = _text(row.get("product_name"))
        for material_id in product_to_materials.get(product_name, []):
            _add_edge(
                graph,
                material_id,
                row.get("order_id"),
                "used_in_order",
                {"product_name": product_name},
            )


def build_supply_chain_graph(data):
    """Build the NetworkX digital twin from already-loaded CSV tables."""
    graph = nx.DiGraph()
    graph.graph["name"] = "AUTOPILOT 2.0 Supply Chain Digital Twin"

    _add_supplier_nodes(graph, data)
    _add_material_nodes(graph, data)
    _add_factory_nodes(graph, data)
    _add_warehouse_nodes(graph, data)
    _add_route_nodes(graph, data)
    _add_order_nodes(graph, data)

    _add_supplier_dependency_edges(graph, data)
    _add_supplier_material_edges(graph, data)
    _add_inventory_edges(graph, data)
    _add_factory_warehouse_edges(graph, data)
    _add_route_edges(graph, data)
    _add_order_edges(graph, data)

    return graph


def get_supply_chain_graph(data=None):
    """
    Return the complete supply-chain graph.

    Pass in data from load_all_data(), or leave it empty to load CSVs here.
    """
    if data is None:
        from src.data_loader import load_all_data
        data = load_all_data()
    return build_supply_chain_graph(data)


def find_upstream_dependencies(graph, supplier_id):
    """
    Find all upstream suppliers for one supplier.

    Example: a Tier 1 pack maker depends on a Tier 2 cell maker,
    who depends on Tier 3 lithium, graphite, and foil suppliers.
    """
    supplier_id = _text(supplier_id)
    if supplier_id not in graph:
        print("Supplier not in graph:", supplier_id)
        return []

    found = []
    seen = set()
    to_visit = [supplier_id]

    while to_visit:
        current = to_visit.pop()
        for previous in graph.predecessors(current):
            edge = graph.edges[previous, current]
            if edge.get("edge_type") != "supplier_dependency":
                continue
            if graph.nodes[previous].get("node_type") != "supplier":
                continue
            if previous in seen:
                continue
            seen.add(previous)
            found.append(previous)
            to_visit.append(previous)

    def tier_of(node_id):
        return graph.nodes[node_id].get("tier", 0)

    found.sort(key=lambda node_id: (tier_of(node_id), node_id), reverse=True)
    return found


def find_suppliers_sharing_upstream(graph, upstream_supplier_id=None):
    """
    Find suppliers that share the same upstream supplier.

    If upstream_supplier_id is given, only that shared parent is returned.
    Otherwise every shared upstream parent is returned.
    """
    groups = {}

    for from_id, to_id, edge in graph.edges(data=True):
        if edge.get("edge_type") != "supplier_dependency":
            continue
        if graph.nodes[from_id].get("node_type") != "supplier":
            continue
        if graph.nodes[to_id].get("node_type") != "supplier":
            continue
        groups.setdefault(from_id, [])
        if to_id not in groups[from_id]:
            groups[from_id].append(to_id)

    shared = {}
    for parent, children in groups.items():
        children = sorted(children)
        if len(children) >= 2:
            shared[parent] = children

    if upstream_supplier_id:
        upstream_supplier_id = _text(upstream_supplier_id)
        if upstream_supplier_id in shared:
            return {upstream_supplier_id: shared[upstream_supplier_id]}
        return {upstream_supplier_id: []}

    return shared


def run_graph_demo(graph):
    """Small test: print node/edge counts and one shared dependency."""
    print("Digital twin nodes:", graph.number_of_nodes())
    print("Digital twin edges:", graph.number_of_edges())

    print("Node types:")
    type_counts = {}
    for node_id in graph.nodes:
        node_type = graph.nodes[node_id].get("node_type", "unknown")
        type_counts[node_type] = type_counts.get(node_type, 0) + 1
    for node_type in sorted(type_counts):
        print(" -", node_type, ":", type_counts[node_type])

    shared_example = find_suppliers_sharing_upstream(graph, "SUP-T2-03")
    print("Shared upstream example: SUP-T2-03 (Nilgiri Cover Glass)")
    print(" Downstream suppliers:", shared_example.get("SUP-T2-03", []))

    upstream_example = find_upstream_dependencies(graph, "SUP-T1-03")
    print("Upstream of SUP-T1-03 (DeccanCell Packs):", upstream_example)


class SupplyChainGraph:
    """Simple digital twin of the supply chain, stored as a NetworkX graph."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes = []
        self.edges = []

    def add_node(self, node_id, node_type, details=None):
        """Add one location, supplier, or other entity to the twin."""
        details = details or {}
        _add_node(self.graph, node_id, node_type, details)
        self.nodes = list(self.graph.nodes)

    def add_edge(self, from_id, to_id, edge_type, details=None):
        """Add a link, such as a transport route or a dependency."""
        _add_edge(self.graph, from_id, to_id, edge_type, details or {})
        self.edges = list(self.graph.edges)

    def build_from_data(self, data):
        """Turn loaded tables into a graph."""
        self.graph = build_supply_chain_graph(data)
        self.nodes = list(self.graph.nodes)
        self.edges = list(self.graph.edges)

    def get_graph(self):
        """Return the complete NetworkX supply-chain graph."""
        return self.graph

    def find_upstream_dependencies(self, supplier_id):
        return find_upstream_dependencies(self.graph, supplier_id)

    def find_suppliers_sharing_upstream(self, upstream_supplier_id=None):
        return find_suppliers_sharing_upstream(self.graph, upstream_supplier_id)

    def summary(self):
        """Print a short count of nodes and edges."""
        print("Digital twin nodes:", self.graph.number_of_nodes())
        print("Digital twin edges:", self.graph.number_of_edges())
