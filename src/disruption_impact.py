"""
disruption_impact.py
--------------------
Member 2: Disruption Impact Analysis.

STEP 1 (this file so far): a lookup that finds every supplier that sits
DOWNSTREAM of a given supplier.

How the graph is built (Member 1's design, not changed here):
    Each supplier_dependency edge points
        UPSTREAM supplier  --->  DOWNSTREAM supplier
    (goods flow in the direction of the arrow).

So "who is hurt if supplier X fails?" means: follow the arrows that
START at X, and keep following them. We use graph.successors() for that.

This file only READS the graph. It never changes it.
"""


def find_downstream_suppliers(graph, supplier_id):
    """
    Return all suppliers that depend on `supplier_id`, directly or through
    other suppliers (Tier 3 -> Tier 2 -> Tier 1).

    Rules:
      * Only edges with edge_type == "supplier_dependency" are followed.
      * Only supplier nodes are returned (no materials, factories,
        warehouses, routes or orders).
      * The starting supplier is never included in the result.
      * Each supplier appears once.

    Returns a list of supplier IDs, sorted by tier (Tier 1 first) and then ID.

    Raises ValueError if `supplier_id` is not a supplier in the graph, so a
    typo is noticed instead of silently giving an empty answer.
    """
    # 1. Check the starting point is a real supplier node.
    if supplier_id not in graph or graph.nodes[supplier_id].get("node_type") != "supplier":
        raise ValueError("Not a supplier in the graph: " + str(supplier_id))

    found = []                  # the answer, in the order we discover suppliers
    already_seen = {supplier_id}  # includes the start, so it can never be returned
    to_visit = [supplier_id]    # suppliers whose downstream links we still need to check

    # 2. Keep walking forward until there is nothing new left to visit.
    while to_visit:
        current = to_visit.pop()

        for next_node in graph.successors(current):
            # Only follow supplier-to-supplier dependency links.
            edge = graph.edges[current, next_node]
            if edge.get("edge_type") != "supplier_dependency":
                continue
            if graph.nodes[next_node].get("node_type") != "supplier":
                continue

            # Skip suppliers we have already recorded (avoids duplicates and loops).
            if next_node in already_seen:
                continue

            already_seen.add(next_node)
            found.append(next_node)
            to_visit.append(next_node)

    # 3. Tier 1 first, then by ID, so the output is stable and easy to read.
    found.sort(key=lambda node_id: (graph.nodes[node_id].get("tier", 0), node_id))
    return found
