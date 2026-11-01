"""
disruption_simulation.py
------------------------
Member 2: Disruption Impact Analysis, PHASE 1 (one failed supplier).

Main function:
    simulate_supplier_disruption(supplier_id, duration_days=7, data=None, graph=None)
        -> dictionary (the "disruption impact report")

Text version of the report:
    format_disruption_report(report) -> str

Try it:
    python -m src.disruption_simulation SUP-T2-01 7

This file only READS Member 1's data and graph. It never changes them.

=====================================================================
WHAT THIS REPORT IS (AND IS NOT)
=====================================================================
Everything here is POTENTIAL EXPOSURE found by following links in the
dataset. Nothing is confirmed damage, and no money has been "lost".

  DIRECT               materials the failed supplier itself is listed for in
                       supplier_materials.csv
  POTENTIAL_CASCADING  materials listed for suppliers that sit downstream of the
                       failed supplier (found with find_downstream_suppliers).
                       We do NOT assume those suppliers stopped operating.

Missing information is reported as "UNKNOWN" or "NOT COMPUTED". It is never
turned into 0.

=====================================================================
ASSUMPTIONS (S1 to S10)
=====================================================================
S1  The disruption duration is a scenario label only. The dataset has no
    consumption or production rates, so the duration is not used in any
    calculation.

S2  SUPPLIER -> MATERIAL: only supplier_materials.csv decides which materials a
    supplier provides. The material_id column of supplier_dependencies.csv is
    shown as an ANNOTATION only and never decides impact. A supplier with no row
    in supplier_materials.csv has UNKNOWN materials (not "none").

S3  BACKUP STATUS of an exposed material (reuses check_backup_candidate from
    supplier_risk.py, so assumptions A2-A4 there apply):
      exposed suppliers = failed supplier (if it supplies the material) plus
                          downstream suppliers of the material
      candidates        = other suppliers listed for the same material
      MITIGATED    at least one candidate is a genuine independent backup
                   against EVERY exposed supplier of that material
      UNMITIGATED  no genuine backup and no candidate is still undecided
                   (this includes "no other supplier is listed")
      UNKNOWN      no genuine backup, but a candidate could not be judged
                   (independence or capacity data missing)

S4  INVENTORY is recorded per material and location. quantity_on_hand is used
    as "available inventory" (the dataset has no reservations). We compare it
    with reorder_point only. Pooled status reuses supplier_risk's
    _summarise_inventory and _pooled_below_reorder, so if ANY row of a material
    has a missing value the pooled status is UNKNOWN.

S5  FACTORY LINK: the dataset has no bill of materials. A factory is
    "potentially affected" when
      (a) it holds inventory of an exposed material (graph holds_inventory edge),
          evidence INVENTORY_LINK, or
      (b) a route used by the failed/downstream supplier arrives at it
          (graph uses_route / leaves_route edges), evidence ROUTE_LINK_ONLY.

S6  WAREHOUSE LINK: a warehouse is potentially affected when it holds inventory
    of an exposed material (INVENTORY_LINK), or it is fed by a factory that has
    INVENTORY_LINK evidence (graph feeds_warehouse edge, FACTORY_LINK_ONLY).

S7  CUSTOMER ORDERS: an order is exposed through an exposed material M only if
    M is used in the order's product (materials.used_in_product; product names
    compared after collapsing whitespace; the CSVs are not modified).
    Evidence levels, strongest first:
      WAREHOUSE_HOLDS_MATERIAL       order's warehouse holds M      \\  HEADLINE
      LINKED_FACTORY_HOLDS_MATERIAL  a factory feeding the warehouse |  (path
                                     holds M                        /  supported)
      PRODUCT_LINK_ONLY              product uses M, no storage path  -> shown
                                     separately as an UPPER BOUND, never added
                                     to the headline
    Only orders with status "confirmed" or "planned" are included. Each order is
    counted once, at its strongest evidence level.

S8  ORDER VALUE uses order_value_inr exactly as given. It is potential exposure,
    not a loss. Missing values stay UNKNOWN and are not added as 0.

S9  TRANSPORT ROUTES are "potentially affected" when a failed/downstream supplier
    uses them, or they start/end at a potentially affected factory/warehouse.
    Nobody assumes a route has failed. Route cargo text is free text: material
    ids found in it are shown as an annotation only.

S10 DELIVERY DELAY and PRODUCTION DAYS REMAINING are NOT COMPUTED: the dataset
    has no consumption rate, production rate, shipment schedule or replenishment
    plan.
"""

import re
import sys

import pandas as pd

from src.data_loader import load_all_data
from src.disruption_impact import find_downstream_suppliers
from src.supplier_risk import (
    _pooled_below_reorder,
    _summarise_inventory,
    check_backup_candidate,
)
from src.supply_chain_graph import find_upstream_dependencies, get_supply_chain_graph


# ---------------------------------------------------------------------------
# Labels used in the report
# ---------------------------------------------------------------------------

UNKNOWN = "UNKNOWN"
NOT_COMPUTED = "NOT COMPUTED"

DIRECT = "DIRECT"
POTENTIAL_CASCADING = "POTENTIAL_CASCADING"

MITIGATED = "MITIGATED"
UNMITIGATED = "UNMITIGATED"

# Customer-order evidence levels (strongest first).
WAREHOUSE_HOLDS_MATERIAL = "WAREHOUSE_HOLDS_MATERIAL"
LINKED_FACTORY_HOLDS_MATERIAL = "LINKED_FACTORY_HOLDS_MATERIAL"
PRODUCT_LINK_ONLY = "PRODUCT_LINK_ONLY"
HEADLINE_EVIDENCE = (WAREHOUSE_HOLDS_MATERIAL, LINKED_FACTORY_HOLDS_MATERIAL)

# Factory / warehouse / route evidence levels.
INVENTORY_LINK = "INVENTORY_LINK"
ROUTE_LINK_ONLY = "ROUTE_LINK_ONLY"
FACTORY_LINK_ONLY = "FACTORY_LINK_ONLY"
LOCATION_LINK_ONLY = "LOCATION_LINK_ONLY"
SUPPLIER_ROUTE = "SUPPLIER_ROUTE"

INCLUDED_ORDER_STATUSES = ("confirmed", "planned")

# Inventory status words.
BELOW = "BELOW_REORDER_POINT"
AT_OR_ABOVE = "AT_OR_ABOVE_REORDER_POINT"
NO_RECORDS = "NO_INVENTORY_RECORDS"


# ---------------------------------------------------------------------------
# Small helpers (local copies, as agreed; supplier_risk's helpers stay private)
# ---------------------------------------------------------------------------

def _rows(table):
    """Turn a DataFrame into a list of dictionaries (empty list if no data)."""
    if table is None or len(table) == 0:
        return []
    return table.to_dict("records")


def _text(value):
    """Cell -> clean text. Missing values become ''."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _number(value):
    """Cell -> float, or None if it is missing or not a number."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(number):
        return None
    return number


def _tidy(number):
    """4000.0 -> 4000 (nicer in a report). None stays None."""
    if number is None:
        return None
    if number == int(number):
        return int(number)
    return number


def _known(value):
    """A number from a cell, or the word UNKNOWN when it is missing."""
    number = _number(value)
    return UNKNOWN if number is None else _tidy(number)


def _normalise_name(value):
    """'Slate  10 Tablet ' -> 'Slate 10 Tablet'. Only whitespace is changed."""
    return " ".join(_text(value).split())


def _split_products(value):
    """'A;B ; C' -> {'A', 'B', 'C'} (whitespace-normalised)."""
    products = set()
    for piece in _text(value).split(";"):
        piece = _normalise_name(piece)
        if piece:
            products.add(piece)
    return products


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _check_supplier_id(graph, supplier_id):
    """Return the cleaned supplier id, or raise ValueError."""
    if not isinstance(supplier_id, str) or not supplier_id.strip():
        raise ValueError("supplier_id must be a non-empty text value, got: " + repr(supplier_id))
    supplier_id = supplier_id.strip()
    if supplier_id not in graph:
        raise ValueError("Unknown supplier id (not in the supply chain graph): " + supplier_id)
    if graph.nodes[supplier_id].get("node_type") != "supplier":
        raise ValueError(
            supplier_id + " exists but is a " + str(graph.nodes[supplier_id].get("node_type"))
            + ", not a supplier"
        )
    return supplier_id


def _check_duration(duration_days):
    """Return the duration as a whole number of days (>= 1), or raise ValueError."""
    if isinstance(duration_days, bool) or not isinstance(duration_days, (int, float)):
        raise ValueError("duration_days must be a whole number of days, got: " + repr(duration_days))
    if isinstance(duration_days, float) and (pd.isna(duration_days) or duration_days != int(duration_days)):
        raise ValueError("duration_days must be a whole number of days, got: " + repr(duration_days))
    duration_days = int(duration_days)
    if duration_days < 1:
        raise ValueError("duration_days must be at least 1, got: " + str(duration_days))
    return duration_days


# ---------------------------------------------------------------------------
# Step helpers: lookups, backup status, inventory
# ---------------------------------------------------------------------------

def _build_lookups(data):
    """Prepare the dictionaries used by every later step (built once)."""
    supplier_info = {_text(r.get("supplier_id")): r for r in _rows(data.get("suppliers"))}
    material_info = {_text(r.get("material_id")): r for r in _rows(data.get("materials"))}

    material_rows = {}       # (supplier_id, material_id) -> supplier_materials row
    suppliers_of = {}        # material_id -> set of supplier ids
    materials_of = {}        # supplier_id -> set of material ids
    for row in _rows(data.get("supplier_materials")):
        sid, mid = _text(row.get("supplier_id")), _text(row.get("material_id"))
        if not sid or not mid:
            continue
        material_rows[(sid, mid)] = row
        suppliers_of.setdefault(mid, set()).add(sid)
        materials_of.setdefault(sid, set()).add(mid)

    products_of = {mid: _split_products(r.get("used_in_product")) for mid, r in material_info.items()}

    inventory_rows = []
    for row in _rows(data.get("inventory")):
        if _text(row.get("material_id")):
            inventory_rows.append(row)

    return {
        "supplier_info": supplier_info,
        "material_info": material_info,
        "material_rows": material_rows,
        "suppliers_of": suppliers_of,
        "materials_of": materials_of,
        "products_of": products_of,
        "inventory_rows": inventory_rows,
    }


def _assess_backup(material_id, exposed, impact_type, lookups, upstream_of):
    """
    Backup status (S3) of ONE exposed material.

    `exposed` = suppliers of this material that are the failed supplier or
    downstream of it. Every other supplier of the material is a candidate.
    """
    candidates = sorted(lookups["suppliers_of"].get(material_id, set()) - set(exposed))
    candidate_reports = []
    any_genuine = False
    any_undecided = False

    for candidate_id in candidates:
        checks = [
            check_backup_candidate(
                primary_id, candidate_id, material_id,
                upstream_of, lookups["material_rows"], lookups["supplier_info"],
            )
            for primary_id in sorted(exposed)
        ]
        # Definitely NOT a backup: any check found a dependency or too little capacity.
        definitely_not = any(
            (not c["same_material"]) or c["independent"] is False or c["capacity_status"] == "insufficient"
            for c in checks
        )
        genuine = (not definitely_not) and all(c["is_genuine"] for c in checks)
        undecided = (not definitely_not) and not genuine

        reasons = []
        for c in checks:
            reasons.extend(c["independence_problems"])
            if c["capacity_status"] != "sufficient":
                reasons.append("capacity " + c["capacity_status"] + ": " + c["capacity_note"])
        candidate_reports.append({
            "candidate_id": candidate_id,
            "verdict": "GENUINE" if genuine else (UNKNOWN if undecided else "NOT_GENUINE"),
            "reasons": sorted(set(reasons)),
        })
        any_genuine = any_genuine or genuine
        any_undecided = any_undecided or undecided

    if any_genuine:
        status = MITIGATED
        explanation = "At least one other supplier is a genuine independent backup."
    elif any_undecided:
        status = UNKNOWN
        explanation = "No confirmed genuine backup, and at least one candidate could not be judged (data missing)."
    elif not candidates:
        status = UNMITIGATED
        explanation = ("Every supplier listed for this material in supplier_materials.csv is the failed "
                       "supplier or downstream of it, so no unaffected alternative exists.")
    else:
        status = UNMITIGATED
        explanation = "Other suppliers are listed, but none is a genuine independent backup."

    return {
        "material_id": material_id,
        "material_name": _text((lookups["material_info"].get(material_id) or {}).get("material_name")),
        "impact_type": impact_type,
        "status": status,
        "exposed_suppliers": sorted(exposed),
        "candidates": candidate_reports,
        "explanation": explanation,
    }


def _pooled_view(rows, material_id):
    """
    Pooled inventory status for one material over the given rows.

    Reuses _summarise_inventory and _pooled_below_reorder (supplier_risk.py).
    Totals are only shown when the status is known, so partial sums are never
    mistaken for real totals.
    """
    if not rows:
        return {"status": NO_RECORDS, "locations": 0, "on_hand": UNKNOWN, "reorder_point": UNKNOWN,
                "locations_below_reorder_point": UNKNOWN}
    entry = _summarise_inventory(pd.DataFrame(rows)).get(material_id)
    below = _pooled_below_reorder(entry)
    if below is None:
        return {"status": UNKNOWN, "locations": entry["rows"], "on_hand": UNKNOWN, "reorder_point": UNKNOWN,
                "locations_below_reorder_point": entry["below_rows"],
                "note": str(entry["missing_rows"]) + " of " + str(entry["rows"])
                        + " row(s) have a missing quantity_on_hand or reorder_point"}
    return {"status": BELOW if below else AT_OR_ABOVE, "locations": entry["rows"],
            "on_hand": _tidy(entry["on_hand"]), "reorder_point": _tidy(entry["reorder"]),
            "locations_below_reorder_point": entry["below_rows"]}


def _inventory_for_material(material_id, impact_type, lookups, graph, gaps):
    """Per-location rows plus pooled views for one exposed material."""
    rows = [r for r in lookups["inventory_rows"] if _text(r.get("material_id")) == material_id]
    locations = []
    for row in rows:
        on_hand, reorder = _number(row.get("quantity_on_hand")), _number(row.get("reorder_point"))
        location_id = _text(row.get("location_id"))
        graph_kind = graph.nodes[location_id].get("node_type") if location_id in graph else None
        stated_kind = _text(row.get("location_type"))
        kind = graph_kind or stated_kind or UNKNOWN
        if graph_kind and stated_kind and graph_kind != stated_kind:
            gaps.append("inventory " + _text(row.get("inventory_id")) + ": location_type '" + stated_kind
                        + "' differs from graph node type '" + graph_kind + "' for " + location_id)
        if location_id not in graph:
            gaps.append("inventory " + _text(row.get("inventory_id")) + ": location " + (location_id or "(blank)")
                        + " is not in the graph")
        if on_hand is None or reorder is None:
            status, shortfall = UNKNOWN, UNKNOWN
        elif on_hand < reorder:
            status, shortfall = BELOW, _tidy(reorder - on_hand)
        else:
            status, shortfall = AT_OR_ABOVE, None
        locations.append({
            "inventory_id": _text(row.get("inventory_id")),
            "location_id": location_id,
            "location_kind": kind,
            "quantity_on_hand": _known(row.get("quantity_on_hand")),
            "reorder_point": _known(row.get("reorder_point")),
            "max_stock": _known(row.get("max_stock")),
            "status": status,
            "shortfall_to_reorder_point": shortfall,
        })

    factory_rows = [r for r, loc in zip(rows, locations) if loc["location_kind"] == "factory"]
    warehouse_rows = [r for r, loc in zip(rows, locations) if loc["location_kind"] == "warehouse"]
    pooled = _pooled_view(rows, material_id)

    if not rows:
        shortage = UNKNOWN
        gaps.append(material_id + ": no rows in inventory.csv, so inventory is UNKNOWN (not zero)")
    elif pooled["status"] == UNKNOWN:
        shortage = UNKNOWN
    elif pooled["status"] == BELOW:
        shortage = "POOLED_BELOW_REORDER_POINT"
    elif any(loc["status"] == BELOW for loc in locations):
        shortage = "SOME_LOCATIONS_BELOW_REORDER_POINT"
    else:
        shortage = "NO_LOCATION_BELOW_REORDER_POINT"

    return {
        "material_id": material_id,
        "material_name": _text((lookups["material_info"].get(material_id) or {}).get("material_name")),
        "impact_type": impact_type,
        "locations": locations,
        "pooled_all_locations": pooled,
        "pooled_factories": _pooled_view(factory_rows, material_id),
        "pooled_warehouses": _pooled_view(warehouse_rows, material_id),
        "shortage_exposure": shortage,
    }


# ---------------------------------------------------------------------------
# Step helpers: factories, warehouses, routes, orders
# ---------------------------------------------------------------------------

def _best_impact(impact_types):
    """DIRECT beats POTENTIAL_CASCADING."""
    return DIRECT if DIRECT in impact_types else POTENTIAL_CASCADING


def _supplier_routes(graph, supplier_id):
    """Routes a supplier uses (graph uses_route edges) -> [(route_id, 'PRIMARY'|'SHARED')]."""
    primary = graph.nodes[supplier_id].get("primary_route_id")
    found = []
    for node in graph.successors(supplier_id):
        if graph.edges[supplier_id, node].get("edge_type") != "uses_route":
            continue
        if graph.nodes[node].get("node_type") != "transport_route":
            continue
        found.append((node, "PRIMARY_ROUTE" if node == primary else "SHARED_ROUTE"))
    return sorted(found)


def _route_destination(graph, route_id):
    """Where a route ends (graph leaves_route edge), or None."""
    for node in graph.successors(route_id):
        if graph.edges[route_id, node].get("edge_type") == "leaves_route":
            return node
    return None


def _find_factories_and_warehouses(graph, holders, supplier_impact):
    """
    Factories and warehouses that are potentially affected (S5, S6).

    holders         {(location_id, material_id): impact_type of that material}
    supplier_impact {supplier_id: DIRECT (failed one) or POTENTIAL_CASCADING}
    """
    factories, warehouses = {}, {}

    def add(table, node_id, reason, evidence, impact):
        entry = table.setdefault(node_id, {"reasons": [], "evidence": [], "impact": []})
        entry["reasons"].append(reason)
        entry["evidence"].append(evidence)
        entry["impact"].append(impact)

    for (location_id, material_id), impact in sorted(holders.items()):
        if location_id not in graph:
            continue
        kind = graph.nodes[location_id].get("node_type")
        reason = "holds inventory of " + material_id + " (" + impact + ")"
        if kind == "factory":
            add(factories, location_id, reason, INVENTORY_LINK, impact)
        elif kind == "warehouse":
            add(warehouses, location_id, reason, INVENTORY_LINK, impact)

    # Routes used by the failed / downstream suppliers that arrive at a factory.
    for supplier_id, impact in sorted(supplier_impact.items()):
        for route_id, label in _supplier_routes(graph, supplier_id):
            destination = _route_destination(graph, route_id)
            if destination in graph and graph.nodes[destination].get("node_type") == "factory":
                add(factories, destination,
                    "route " + route_id + " (" + label.lower().replace("_", " ") + " of " + supplier_id
                    + ") arrives here", ROUTE_LINK_ONLY, impact)

    # Warehouses fed by a factory that has inventory-link evidence.
    for factory_id, entry in sorted(factories.items()):
        if INVENTORY_LINK not in entry["evidence"]:
            continue
        for node in graph.successors(factory_id):
            if (graph.edges[factory_id, node].get("edge_type") == "feeds_warehouse"
                    and graph.nodes[node].get("node_type") == "warehouse"):
                inventory_impacts = [i for e, i in zip(entry["evidence"], entry["impact"]) if e == INVENTORY_LINK]
                add(warehouses, node, "is fed by " + factory_id + " (which holds exposed inventory)",
                    FACTORY_LINK_ONLY, _best_impact(inventory_impacts))

    def finish(table, node_type):
        report = []
        for node_id in sorted(table):
            entry = table[node_id]
            # The impact type comes from the STRONGEST evidence only, so a weak
            # route link cannot turn a cascading location into a DIRECT one.
            strongest = next(e for e in (INVENTORY_LINK, FACTORY_LINK_ONLY, ROUTE_LINK_ONLY)
                             if e in entry["evidence"])
            at_strongest = [i for e, i in zip(entry["evidence"], entry["impact"]) if e == strongest]
            report.append({
                node_type + "_id": node_id,
                "name": graph.nodes[node_id].get("name", ""),
                "impact_type": _best_impact(at_strongest),
                "evidence_level": strongest,
                "reasons": entry["reasons"],
            })
        return report

    return finish(factories, "factory"), finish(warehouses, "warehouse")


def _find_routes(graph, supplier_impact, location_impact):
    """Potentially affected transport routes (S9). Nothing is assumed to have failed."""
    found = {}

    def add(route_id, reason, evidence, impact):
        entry = found.setdefault(route_id, {"reasons": [], "evidence": [], "impact": []})
        entry["reasons"].append(reason)
        entry["evidence"].append(evidence)
        entry["impact"].append(impact)

    for supplier_id, impact in sorted(supplier_impact.items()):
        for route_id, label in _supplier_routes(graph, supplier_id):
            add(route_id, "used by " + supplier_id + " (" + label.lower().replace("_", " ") + ")",
                SUPPLIER_ROUTE, impact)

    for route_id, attrs in graph.nodes(data=True):
        if attrs.get("node_type") != "transport_route":
            continue
        for end in (attrs.get("origin_id"), attrs.get("destination_id")):
            if end in location_impact:
                add(route_id, "starts/ends at potentially affected location " + end,
                    LOCATION_LINK_ONLY, location_impact[end])

    report = []
    for route_id in sorted(found, key=lambda r: (SUPPLIER_ROUTE not in found[r]["evidence"], r)):
        attrs, entry = graph.nodes[route_id], found[route_id]
        report.append({
            "route_id": route_id,
            "origin_id": attrs.get("origin_id"),
            "destination_id": attrs.get("destination_id"),
            "mode": attrs.get("mode"),
            "transit_days": _known(attrs.get("transit_days")),
            "cargo_text": attrs.get("cargo", ""),
            "cargo_text_material_ids_annotation": sorted(set(re.findall(r"MAT-\d+", attrs.get("cargo", "")))),
            "impact_type": _best_impact(entry["impact"]),
            "evidence_level": SUPPLIER_ROUTE if SUPPLIER_ROUTE in entry["evidence"] else LOCATION_LINK_ONLY,
            "reasons": entry["reasons"],
            "status": "POTENTIALLY_AFFECTED (route not assumed to have failed)",
        })
    return report


def _find_orders(data, graph, holders, material_impact, lookups, gaps):
    """
    Customer orders exposed through the affected materials (S7, S8).

    holders          {(location_id, material_id): impact_type}
    material_impact  {material_id: impact_type} for every exposed material
    """
    # Which factories feed each warehouse (graph feeds_warehouse edges).
    def feeding_factories(warehouse_id):
        if warehouse_id not in graph:
            return []
        return sorted(
            p for p in graph.predecessors(warehouse_id)
            if graph.edges[p, warehouse_id].get("edge_type") == "feeds_warehouse"
            and graph.nodes[p].get("node_type") == "factory"
        )

    # Which exposed materials go into which (whitespace-normalised) product.
    materials_for_product = {}
    for material_id in material_impact:
        for product in lookups["products_of"].get(material_id, set()):
            materials_for_product.setdefault(product, []).append(material_id)
    all_known_products = set().union(*lookups["products_of"].values()) if lookups["products_of"] else set()

    included, excluded_status, unmatched_product = {}, [], []
    for row in _rows(data.get("customer_orders")):
        order_id = _text(row.get("order_id"))
        if not order_id:
            continue
        status = _text(row.get("status")).lower()
        if status not in INCLUDED_ORDER_STATUSES:
            excluded_status.append(order_id)
            continue
        product = _normalise_name(row.get("product_name"))
        if product not in all_known_products:
            unmatched_product.append(order_id)
            continue
        material_ids = sorted(materials_for_product.get(product, []))
        if not material_ids:
            continue   # product does not use any exposed material: not exposed

        warehouse_id = _text(row.get("warehouse_id"))
        factories = feeding_factories(warehouse_id)
        support = []
        for material_id in material_ids:
            if (warehouse_id, material_id) in holders:
                level, via = WAREHOUSE_HOLDS_MATERIAL, warehouse_id
            else:
                via = next((f for f in factories if (f, material_id) in holders), None)
                level = LINKED_FACTORY_HOLDS_MATERIAL if via else PRODUCT_LINK_ONLY
                via = via or ""
            support.append({"material_id": material_id, "impact_type": material_impact[material_id],
                            "evidence_level": level, "via_location": via})

        # Each order is counted once, at its strongest evidence level.
        for level in (WAREHOUSE_HOLDS_MATERIAL, LINKED_FACTORY_HOLDS_MATERIAL, PRODUCT_LINK_ONLY):
            at_level = [s for s in support if s["evidence_level"] == level]
            if at_level:
                break
        included[order_id] = {
            "order_id": order_id,
            "customer_name": _text(row.get("customer_name")),
            "warehouse_id": warehouse_id,
            "product_name": product,
            "quantity": _known(row.get("quantity")),
            "order_value_inr": _known(row.get("order_value_inr")),
            "status": status,
            "required_date": _text(row.get("required_date")) or UNKNOWN,
            "evidence_level": level,
            "impact_type": _best_impact([s["impact_type"] for s in at_level]),
            "supporting_materials": support,
        }

    if excluded_status:
        gaps.append("orders excluded because status is not confirmed/planned: " + ", ".join(sorted(excluded_status)))
    if unmatched_product:
        gaps.append("orders whose product matches no materials.used_in_product entry (cannot be linked): "
                    + ", ".join(sorted(unmatched_product)))

    def summarise(orders):
        orders = sorted(orders, key=lambda o: o["order_id"])
        known = [o["order_value_inr"] for o in orders if o["order_value_inr"] != UNKNOWN]
        unknown_ids = [o["order_id"] for o in orders if o["order_value_inr"] == UNKNOWN]
        if orders and not known:
            total = UNKNOWN
        else:
            total = _tidy(float(sum(known)))
        return {
            "order_count": len(orders),
            "potential_value_exposure_inr": total,
            "value_is_complete": not unknown_ids,
            "orders_with_unknown_value": unknown_ids,
            "direct_order_count": sum(1 for o in orders if o["impact_type"] == DIRECT),
            "potential_cascading_order_count": sum(1 for o in orders if o["impact_type"] == POTENTIAL_CASCADING),
            "potential_value_direct_inr": _sum_if_any([o for o in orders if o["impact_type"] == DIRECT]),
            "potential_value_cascading_only_inr": _sum_if_any(
                [o for o in orders if o["impact_type"] == POTENTIAL_CASCADING]),
            "orders": orders,
        }

    headline = [o for o in included.values() if o["evidence_level"] in HEADLINE_EVIDENCE]
    extra = [o for o in included.values() if o["evidence_level"] == PRODUCT_LINK_ONLY]
    headline_summary, extra_summary = summarise(headline), summarise(extra)

    upper = UNKNOWN
    if headline_summary["potential_value_exposure_inr"] != UNKNOWN or not headline:
        if extra_summary["potential_value_exposure_inr"] != UNKNOWN or not extra:
            upper = _tidy(float(
                _zero_if_none(headline_summary["potential_value_exposure_inr"])
                + _zero_if_none(extra_summary["potential_value_exposure_inr"])
            ))
    return {
        "note": "POTENTIAL exposure only: not confirmed delays, cancellations or financial loss.",
        "included_statuses": list(INCLUDED_ORDER_STATUSES),
        "headline_path_supported": headline_summary,
        "additional_product_link_only": dict(extra_summary, note=(
            "Product uses an exposed material but no warehouse/factory storage path was found. "
            "Upper-bound extra exposure; NOT part of the headline.")),
        "upper_bound_including_product_link_only_inr": upper,
    }


def _sum_if_any(orders):
    """Sum of known order values; 'UNKNOWN' only if there are orders and none has a value."""
    if not orders:
        return 0
    known = [o["order_value_inr"] for o in orders if o["order_value_inr"] != UNKNOWN]
    return _tidy(float(sum(known))) if known else UNKNOWN


def _zero_if_none(value):
    """For adding two totals when one group is empty (empty group = nothing to add)."""
    return 0 if value in (None, UNKNOWN) else value


# ---------------------------------------------------------------------------
# The main function
# ---------------------------------------------------------------------------

def simulate_supplier_disruption(supplier_id, duration_days=7, data=None, graph=None):
    """
    Simulate the failure of ONE supplier and return an explainable report.

    supplier_id    id of the supplier that fails, e.g. "SUP-T2-01"
    duration_days  scenario length in days (default 7); a label only (see S1)
    data, graph    from load_all_data() / get_supply_chain_graph(); loaded here if None

    Raises ValueError for an unknown supplier id, an id that is not a supplier,
    or an invalid duration.
    """
    if data is None:
        data = load_all_data(verbose=False)
    if graph is None:
        graph = get_supply_chain_graph(data)

    supplier_id = _check_supplier_id(graph, supplier_id)
    duration_days = _check_duration(duration_days)

    lookups = _build_lookups(data)
    gaps = []

    # --- 1. The failed supplier --------------------------------------------
    attrs = graph.nodes[supplier_id]
    direct_ids = sorted(lookups["materials_of"].get(supplier_id, set()))
    direct_known = bool(direct_ids)
    if not direct_known:
        gaps.append(supplier_id + " has no row in supplier_materials.csv: its DIRECT materials are UNKNOWN (not none)")

    # --- 2. Downstream suppliers (existing function) ------------------------
    downstream_ids = find_downstream_suppliers(graph, supplier_id)
    downstream_set = set(downstream_ids)
    chain = {supplier_id} | downstream_set

    downstream_report = []
    cascading_source = {}   # material_id -> downstream suppliers that list it
    for sid in downstream_ids:
        materials = sorted(lookups["materials_of"].get(sid, set()))
        if not materials:
            gaps.append(sid + " (downstream) has no row in supplier_materials.csv: its materials are UNKNOWN")
        for mid in materials:
            cascading_source.setdefault(mid, []).append(sid)
        links = []   # dependency links inside the affected chain (material_id = annotation only)
        for upstream in sorted(graph.predecessors(sid)):
            edge = graph.edges[upstream, sid]
            if edge.get("edge_type") == "supplier_dependency" and upstream in chain:
                links.append({"upstream_supplier_id": upstream, "dependency_id": edge.get("dependency_id", ""),
                              "dependency_material_id_annotation": edge.get("material_id", "")})
        downstream_report.append({
            "supplier_id": sid,
            "supplier_name": graph.nodes[sid].get("name", ""),
            "tier": _known(graph.nodes[sid].get("tier")),
            "depends_directly_on_failed_supplier": any(l["upstream_supplier_id"] == supplier_id for l in links),
            "materials_supplied": materials if materials else UNKNOWN,
            "dependency_links": links,
            "status": "POTENTIALLY_AFFECTED (not assumed to have stopped operating)",
        })

    # --- 3. Direct and potential cascading materials ------------------------
    material_impact = {mid: DIRECT for mid in direct_ids}
    for mid in cascading_source:
        material_impact.setdefault(mid, POTENTIAL_CASCADING)

    def material_entry(mid):
        info = lookups["material_info"].get(mid) or {}
        supplied_by = sorted(
            ([supplier_id] if mid in direct_ids else []) + cascading_source.get(mid, []))
        return {
            "material_id": mid,
            "material_name": _text(info.get("material_name")) or UNKNOWN,
            "impact_type": material_impact[mid],
            "exposed_through_suppliers": supplied_by,
            "products": sorted(lookups["products_of"].get(mid, set())),
        }

    direct_materials = [material_entry(m) for m in direct_ids]
    cascading_materials = [material_entry(m) for m in sorted(material_impact) if material_impact[m] == POTENTIAL_CASCADING]
    for mid in material_impact:
        if mid not in lookups["material_info"]:
            gaps.append(mid + " is in supplier_materials.csv but not in materials.csv")

    # --- 4. Backup status (reuses check_backup_candidate) -------------------
    upstream_of = {sid: set(find_upstream_dependencies(graph, sid))
                   for sid in lookups["supplier_info"] if sid in graph}
    backups = []
    for mid in sorted(material_impact):
        exposed = [s for s in lookups["suppliers_of"].get(mid, set()) if s in chain]
        backups.append(_assess_backup(mid, exposed, material_impact[mid], lookups, upstream_of))

    # --- 5. Inventory --------------------------------------------------------
    inventory = [_inventory_for_material(mid, material_impact[mid], lookups, graph, gaps)
                 for mid in sorted(material_impact)]
    holders = {}
    for row in lookups["inventory_rows"]:
        key = (_text(row.get("location_id")), _text(row.get("material_id")))
        if key[1] in material_impact:
            holders[key] = material_impact[key[1]]

    # --- 6. Factories, warehouses, routes ------------------------------------
    supplier_impact = {supplier_id: DIRECT}
    supplier_impact.update({sid: POTENTIAL_CASCADING for sid in downstream_ids})
    factories, warehouses = _find_factories_and_warehouses(graph, holders, supplier_impact)
    location_impact = {f["factory_id"]: f["impact_type"] for f in factories}
    location_impact.update({w["warehouse_id"]: w["impact_type"] for w in warehouses})
    routes = _find_routes(graph, supplier_impact, location_impact)

    # --- 7. Customer orders --------------------------------------------------
    orders = _find_orders(data, graph, holders, material_impact, lookups, gaps)

    # --- 8. Fixed gaps and assumptions ---------------------------------------
    gaps.extend([
        "No consumption or production-rate data: production days remaining cannot be computed.",
        "No shipment schedule, replenishment plan or production plan: delivery delay cannot be estimated.",
        "No bill of materials: factory links rely on inventory rows and supplier routes, not on a proven "
        "'material is consumed at this factory' relationship.",
        "supplier_dependencies.csv material_id is shown as an annotation only and is never used to decide impact.",
        "Capacity of a possible backup is compared with the exposed supplier's monthly_capacity_units; "
        "current load is not in the data, so 'sufficient' is optimistic.",
    ])
    assumptions = [
        "S1  Duration (" + str(duration_days) + " days) is a scenario label only; it is not used in any calculation.",
        "S2  Supplier-to-material links come only from supplier_materials.csv.",
        "S3  Backup status reuses check_backup_candidate (same material, independent, sufficient capacity).",
        "S4  quantity_on_hand is treated as available inventory and compared with reorder_point only.",
        "S5  Factory links: inventory rows (INVENTORY_LINK) or arrival of an affected supplier's route (ROUTE_LINK_ONLY).",
        "S6  Warehouse links: inventory rows, or being fed by a factory with inventory-link evidence.",
        "S7  Orders: confirmed and planned only; each order counted once at its strongest evidence level; "
        "product names compared after whitespace normalisation.",
        "S8  order_value_inr is potential exposure, not an actual loss.",
        "S9  Routes are potentially affected, not assumed to have failed.",
        "S10 Delivery delay and production days remaining are NOT COMPUTED.",
    ]

    evidence_levels = {
        "DIRECT": "Supplier is listed for the material in supplier_materials.csv.",
        "POTENTIAL_CASCADING": "Supplier is downstream of the failed supplier; not assumed to have stopped.",
        WAREHOUSE_HOLDS_MATERIAL: "Order's warehouse holds inventory of an exposed material (headline).",
        LINKED_FACTORY_HOLDS_MATERIAL: "A factory feeding the order's warehouse holds an exposed material (headline).",
        PRODUCT_LINK_ONLY: "Only the product-material link exists (upper bound, not in headline).",
        INVENTORY_LINK: "Location holds inventory of an exposed material.",
        ROUTE_LINK_ONLY: "A route used by an affected supplier arrives here; nothing else supports the link.",
        FACTORY_LINK_ONLY: "Warehouse is fed by a factory with inventory-link evidence.",
        SUPPLIER_ROUTE: "Route is used by the failed or a downstream supplier.",
        LOCATION_LINK_ONLY: "Route starts or ends at a potentially affected location.",
    }

    head = orders["headline_path_supported"]
    return {
        "scenario": {
            "failed_supplier_id": supplier_id,
            "disruption_duration_days": duration_days,
            "duration_note": "scenario label only; not used in any calculation because there is no consumption data",
            "meaning_of_results": "POTENTIAL exposure found by following dataset links. Not confirmed damage.",
        },
        "failed_supplier": {
            "supplier_id": supplier_id,
            "supplier_name": attrs.get("name", ""),
            "tier": _known(attrs.get("tier")),
            "capacity_status": attrs.get("capacity_status") or UNKNOWN,
            "lead_time_days": _known(attrs.get("lead_time_days")),
            "materials_known": direct_known,
        },
        "direct_materials_status": "KNOWN" if direct_known else UNKNOWN,
        "direct_materials": direct_materials,
        "downstream_suppliers": downstream_report,
        "potential_cascading_materials": cascading_materials,
        "backup_assessment": backups,
        "factories": factories,
        "warehouses": warehouses,
        "inventory": inventory,
        "transport_routes": routes,
        "customer_orders": orders,
        "delivery_delay": {
            "status": NOT_COMPUTED,
            "reason": "No shipment schedule, replenishment plan or consumption data in the dataset.",
        },
        "production_days_remaining": {
            "status": NOT_COMPUTED,
            "reason": "No material consumption or production-rate data in the dataset.",
        },
        "summary": {
            "direct_material_count": len(direct_materials) if direct_known else UNKNOWN,
            "downstream_supplier_count": len(downstream_report),
            "potential_cascading_material_count": len(cascading_materials),
            "factory_count": len(factories),
            "warehouse_count": len(warehouses),
            "route_count": len(routes),
            "headline_order_count": head["order_count"],
            "headline_potential_order_value_exposure_inr": head["potential_value_exposure_inr"],
            "additional_product_link_only_order_count": orders["additional_product_link_only"]["order_count"],
            "backup_status_by_material": {b["material_id"]: b["status"] for b in backups},
        },
        "evidence_levels": evidence_levels,
        "assumptions": assumptions,
        "data_gaps": gaps,
    }


# ---------------------------------------------------------------------------
# Readable text version
# ---------------------------------------------------------------------------

def _money(value):
    return value if value == UNKNOWN else "INR {:,}".format(value)


def format_disruption_report(report):
    """Turn the report dictionary into plain text for printing."""
    s, f = report["scenario"], report["failed_supplier"]
    lines = [
        "=" * 72,
        "DISRUPTION IMPACT REPORT (potential exposure, not confirmed damage)",
        "=" * 72,
        "Failed supplier : " + f["supplier_id"] + " - " + f["supplier_name"] + " (tier " + str(f["tier"]) + ")",
        "Duration        : " + str(s["disruption_duration_days"]) + " days (" + s["duration_note"] + ")",
        "",
        "DIRECT materials (" + report["direct_materials_status"] + ")",
    ]
    for m in report["direct_materials"]:
        lines.append("  - " + m["material_id"] + " " + m["material_name"])
    lines.append("")
    lines.append("Downstream suppliers (potentially affected, not assumed stopped): "
                 + (", ".join(d["supplier_id"] for d in report["downstream_suppliers"]) or "none"))
    lines.append("POTENTIAL_CASCADING materials:")
    for m in report["potential_cascading_materials"] or []:
        lines.append("  - " + m["material_id"] + " " + m["material_name"]
                     + " (via " + ", ".join(m["exposed_through_suppliers"]) + ")")
    if not report["potential_cascading_materials"]:
        lines.append("  (none)")

    lines += ["", "Backup status"]
    for b in report["backup_assessment"]:
        lines.append("  - " + b["material_id"] + " [" + b["impact_type"] + "]: " + b["status"] + " - " + b["explanation"])
        for c in b["candidates"]:
            lines.append("      candidate " + c["candidate_id"] + ": " + c["verdict"]
                         + (" (" + "; ".join(c["reasons"]) + ")" if c["reasons"] else ""))

    lines += ["", "Inventory (quantity_on_hand vs reorder_point; no days of cover)"]
    for inv in report["inventory"]:
        p = inv["pooled_all_locations"]
        lines.append("  - " + inv["material_id"] + " " + inv["material_name"] + " [" + inv["impact_type"] + "]: pooled "
                     + p["status"] + " (on hand " + str(p["on_hand"]) + " vs reorder " + str(p["reorder_point"])
                     + "); shortage exposure: " + inv["shortage_exposure"])
        for loc in inv["locations"]:
            lines.append("      " + loc["location_id"] + " (" + loc["location_kind"] + "): "
                         + str(loc["quantity_on_hand"]) + " vs " + str(loc["reorder_point"]) + " -> " + loc["status"])

    lines += ["", "Potentially affected factories"]
    for x in report["factories"]:
        lines.append("  - " + x["factory_id"] + " " + x["name"] + " [" + x["impact_type"] + ", "
                     + x["evidence_level"] + "]")
    lines.append("Potentially affected warehouses")
    for x in report["warehouses"]:
        lines.append("  - " + x["warehouse_id"] + " " + x["name"] + " [" + x["impact_type"] + ", "
                     + x["evidence_level"] + "]")
    lines.append("Potentially affected transport routes (not assumed failed)")
    for x in report["transport_routes"]:
        lines.append("  - " + x["route_id"] + " " + str(x["origin_id"]) + " -> " + str(x["destination_id"])
                     + " [" + x["evidence_level"] + "]")

    o = report["customer_orders"]
    h, a = o["headline_path_supported"], o["additional_product_link_only"]
    lines += [
        "", "Customer orders (confirmed + planned, each counted once)",
        "  HEADLINE (path supported): " + str(h["order_count"]) + " orders, potential value exposure "
        + _money(h["potential_value_exposure_inr"]) + " (NOT an actual loss)",
        "     of which DIRECT " + str(h["direct_order_count"]) + " / POTENTIAL_CASCADING-only "
        + str(h["potential_cascading_order_count"]),
        "     " + ", ".join(x["order_id"] for x in h["orders"]),
        "  ADDITIONAL, PRODUCT_LINK_ONLY (upper bound, not in headline): " + str(a["order_count"]) + " orders, "
        + _money(a["potential_value_exposure_inr"]),
        "     " + ", ".join(x["order_id"] for x in a["orders"]),
        "  Upper bound incl. product-link-only: " + _money(o["upper_bound_including_product_link_only_inr"]),
        "",
        "Delivery delay          : " + report["delivery_delay"]["status"] + " - " + report["delivery_delay"]["reason"],
        "Production days remaining: " + report["production_days_remaining"]["status"] + " - "
        + report["production_days_remaining"]["reason"],
        "", "Assumptions",
    ]
    lines += ["  " + a_ for a_ in report["assumptions"]]
    lines.append("Data gaps")
    lines += ["  - " + g for g in report["data_gaps"]]
    return "\n".join(lines)


if __name__ == "__main__":
    # Example: python -m src.disruption_simulation SUP-T2-01 7
    chosen_supplier = sys.argv[1] if len(sys.argv) > 1 else "SUP-T2-01"
    chosen_days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    print(format_disruption_report(simulate_supplier_disruption(chosen_supplier, chosen_days)))
