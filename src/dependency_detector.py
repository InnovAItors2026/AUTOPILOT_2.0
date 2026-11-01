"""
dependency_detector.py
----------------------
Finds supplier-to-supplier dependencies in the digital twin.

Example: if Supplier A provides a part that Supplier B needs,
then B depends on A. A delay at A can affect B and later factories.

This module lists dependency links only. Risk scoring, impact analysis,
and cascading-failure simulation belong to other team members.
"""

from src.supply_chain_graph import find_upstream_dependencies, get_supply_chain_graph


def find_direct_dependencies(data):
    """
    Return supplier-to-supplier links from the loaded data.

    Returns the supplier_dependencies DataFrame, or an empty list
    if that table is missing.
    """
    dependencies = data.get("supplier_dependencies")

    if dependencies is None or len(dependencies) == 0:
        print("No supplier dependency data yet.")
        return []

    print("Found", len(dependencies), "direct supplier dependencies.")
    return dependencies


def list_direct_dependencies(data):
    """Return direct supplier links as a list of dictionaries."""
    table = data.get("supplier_dependencies")
    if table is None or len(table) == 0:
        return []
    return table.to_dict("records")


def find_multi_tier_dependencies(graph):
    """
    Return each supplier's upstream chain (one or more hops).

    This is a dependency listing, not a risk score.
    """
    results = {}
    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("node_type") != "supplier":
            continue
        upstream = find_upstream_dependencies(graph, node_id)
        if upstream:
            results[node_id] = upstream
    return results


def find_multi_tier_risks(data):
    """
    Placeholder for later work by other members.

    Member 1 does not score risk. Use find_multi_tier_dependencies()
    for upstream supplier chains.
    """
    print("Multi-tier risk detection is not built yet (out of Member 1 scope).")
    return []


def detect_dependencies(data, graph=None):
    """Run Member 1 dependency checks and return a handover dictionary."""
    direct = find_direct_dependencies(data)
    if graph is None:
        graph = get_supply_chain_graph(data)
    multi_tier = find_multi_tier_dependencies(graph)

    return {
        "direct": direct,
        "direct_records": list_direct_dependencies(data),
        "multi_tier": multi_tier,
        "multi_tier_risks": [],
    }
