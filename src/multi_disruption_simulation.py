"""
multi_disruption_simulation.py
------------------------------
Member 2: Disruption Impact Analysis, PHASE 2 (multiple failed suppliers).

Main function:
    simulate_multiple_supplier_disruption(supplier_ids, duration_days=7, data=None, graph=None)
        -> dictionary (the "multiple disruption impact report")

Text version of the report:
    format_multi_disruption_report(report) -> str

This file only READS Member 1's data and graph. It never changes them.
It reuses tested Phase 1 logic and helpers from disruption_simulation.py,
supplier_risk.py, and disruption_impact.py.

=====================================================================
CORE PRINCIPLES OF MULTI-SUPPLIER SIMULATION
=====================================================================
1. COMBINED EXPOSURE (UNION, NOT SUM):
   Simulating multiple simultaneous failures is NOT simply adding up individual
   single-supplier reports. Adding individual reports causes severe double-counting:
   - Shared customer orders would be counted multiple times.
   - Overlapping downstream suppliers would be duplicated.
   - Common materials and inventory locations would be inflated.
   Instead, this module computes the true UNION of failures across all exposed
   entities.

2. DIRECT BEATS POTENTIAL CASCADING:
   - If a material or entity is directly exposed by any failed supplier, its
     impact type is DIRECT.
   - It is classified as POTENTIAL_CASCADING only if its exposure occurs solely
     through downstream suppliers.
   - If a supplier in supplier_ids is also downstream of another failed supplier,
     it is a DIRECT failure (failed suppliers are removed from the downstream set).

3. PRESERVE UNKNOWN AND NOT COMPUTED:
   Missing information is never treated as zero. Statuses of UNKNOWN, PARTIAL,
   or NOT COMPUTED are faithfully preserved.
"""

import sys
import pandas as pd

from src.data_loader import load_all_data
from src.disruption_impact import find_downstream_suppliers
from src.disruption_simulation import (
    DIRECT,
    FACTORY_LINK_ONLY,
    INVENTORY_LINK,
    LINKED_FACTORY_HOLDS_MATERIAL,
    LOCATION_LINK_ONLY,
    MITIGATED,
    NOT_COMPUTED,
    POTENTIAL_CASCADING,
    PRODUCT_LINK_ONLY,
    ROUTE_LINK_ONLY,
    SUPPLIER_ROUTE,
    UNKNOWN,
    UNMITIGATED,
    WAREHOUSE_HOLDS_MATERIAL,
    _assess_backup,
    _build_lookups,
    _check_duration,
    _find_factories_and_warehouses,
    _find_orders,
    _find_routes,
    _inventory_for_material,
    _route_destination,
    _supplier_routes,
    simulate_supplier_disruption,
)
from src.supply_chain_graph import find_upstream_dependencies, get_supply_chain_graph

# Status constants
KNOWN = "KNOWN"
PARTIAL = "PARTIAL"


# ---------------------------------------------------------------------------
# Local formatting / cell parsing helpers
# ---------------------------------------------------------------------------

def _rows(df):
    """Return a list of row dictionaries from a DataFrame or list."""
    if df is None:
        return []
    if isinstance(df, pd.DataFrame):
        return df.to_dict(orient="records")
    return list(df)


def _text(value):
    """Cell -> clean text string. Missing values become empty string."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _number(value):
    """Cell -> float, or None if missing / non-numeric."""
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(num):
        return None
    return num


def _tidy(number):
    """Format whole floats nicely (e.g. 500.0 -> 500). None stays None."""
    if number is None:
        return None
    if number == int(number):
        return int(number)
    return number


def _known(value):
    """Return a clean number or the string 'UNKNOWN'."""
    num = _number(value)
    return UNKNOWN if num is None else _tidy(num)


# ---------------------------------------------------------------------------
# Input validation (Stage 1)
# ---------------------------------------------------------------------------

def _validate_supplier_ids(graph, supplier_ids):
    """
    Validate that supplier_ids is a valid collection of at least two distinct supplier IDs.

    Rules:
      * Must be an iterable (list, tuple, set, etc.), not None, not a string, and not a dict.
      * Each ID must be a non-empty string. Leading/trailing whitespace is stripped.
      * Each ID must exist in graph and have node_type == 'supplier'.
      * All validation errors across all IDs are collected and reported together in a single ValueError.
      * Duplicate IDs are collapsed while preserving order of first appearance (no double-counting).
      * Must yield at least 2 distinct valid supplier IDs; otherwise raises ValueError.

    Returns:
      list of cleaned, distinct supplier IDs in order of first appearance.
    """
    if supplier_ids is None:
        raise ValueError("supplier_ids cannot be None. Expected a collection of at least two supplier IDs.")

    if isinstance(supplier_ids, (str, bytes)):
        raise ValueError(
            f"supplier_ids must be a collection of supplier IDs (e.g. list or tuple), got string: {repr(supplier_ids)}"
        )

    if isinstance(supplier_ids, dict) or not hasattr(supplier_ids, "__iter__"):
        raise ValueError(
            f"supplier_ids must be a collection of supplier IDs, got: {type(supplier_ids).__name__}"
        )

    items = list(supplier_ids)
    if not items:
        raise ValueError("supplier_ids cannot be empty. At least two distinct supplier IDs are required.")

    cleaned_ids = []
    seen = set()
    errors = []

    for idx, raw_id in enumerate(items):
        if not isinstance(raw_id, str) or not raw_id.strip():
            errors.append(f"Item at index {idx} is not a valid non-empty string: {repr(raw_id)}")
            continue
        clean_id = raw_id.strip()
        if clean_id not in graph:
            errors.append(f"Unknown supplier id (not in the supply chain graph): {clean_id}")
            continue
        node_type = graph.nodes[clean_id].get("node_type")
        if node_type != "supplier":
            errors.append(f"{clean_id} exists but is a {node_type}, not a supplier")
            continue
        if clean_id not in seen:
            seen.add(clean_id)
            cleaned_ids.append(clean_id)

    if errors:
        raise ValueError("Validation failed for supplier_ids:\n  - " + "\n  - ".join(errors))

    if len(cleaned_ids) < 2:
        raise ValueError(
            f"simulate_multiple_supplier_disruption requires at least 2 distinct valid supplier IDs, got {len(cleaned_ids)}: "
            f"{cleaned_ids}. For single-supplier disruption, use simulate_supplier_disruption()."
        )

    return cleaned_ids


# ---------------------------------------------------------------------------
# Backup Reassessment Helper (Stage 2)
# ---------------------------------------------------------------------------

def _show(number):
    """3000.0 -> '3000' (nicer to read in text). None -> '?'."""
    if number is None:
        return "?"
    if number == int(number):
        return str(int(number))
    return str(number)


def _assess_backup_combined(material_id, exposed, impact_type, lookups, upstream_of, failed_ids, graph):
    """
    Reassess backup suppliers for ONE exposed material under combined disruption (Stage 2).

    Rules:
      * exposed: suppliers of this material in the affected chain (failed + pure downstream).
      * candidates: suppliers of this material NOT in the affected chain.
      * Independence: candidate must be independent of EVERY exposed supplier of this material.
      * Summed capacity: candidate's monthly_capacity_units is compared against the SUM of
        monthly_capacity_units across all exposed suppliers of this material.
      * If any exposed supplier or candidate has missing capacity, capacity_status is UNKNOWN
        (never insufficient, unless flagged 'insufficient' in suppliers.csv).
      * Preserves MITIGATED, UNMITIGATED, and UNKNOWN verdicts.
      * Records individual single-supplier backup statuses for comparison.
    """
    candidates = sorted(lookups["suppliers_of"].get(material_id, set()) - set(exposed))

    # Calculate summed capacity required from exposed suppliers
    exposed_caps = []
    any_exposed_cap_missing = False
    for pid in sorted(exposed):
        p_row = lookups["material_rows"].get((pid, material_id))
        cap = _number(p_row.get("monthly_capacity_units")) if p_row else None
        if cap is None:
            any_exposed_cap_missing = True
        else:
            exposed_caps.append(cap)

    if any_exposed_cap_missing or not exposed:
        summed_exposed_capacity = UNKNOWN if any_exposed_cap_missing else 0
    else:
        summed_exposed_capacity = _tidy(sum(exposed_caps))

    candidate_reports = []
    any_genuine = False
    any_undecided = False

    for candidate_id in candidates:
        candidate_row = lookups["material_rows"].get((candidate_id, material_id))
        candidate_cap = _number(candidate_row.get("monthly_capacity_units")) if candidate_row else None
        candidate_status_flag = _text((lookups["supplier_info"].get(candidate_id) or {}).get("capacity_status")).lower()
        flagged_insufficient = (candidate_status_flag == "insufficient")

        # 1. Independence against ALL exposed suppliers of this material
        candidate_upstream = upstream_of.get(candidate_id)
        independence_problems = []
        definite_dependency = False
        supplier_not_in_graph = False

        for pid in sorted(exposed):
            primary_upstream = upstream_of.get(pid)
            if candidate_upstream is None or primary_upstream is None:
                supplier_not_in_graph = True
                independence_problems.append(f"independence unknown ({candidate_id} or {pid} not in graph)")
            else:
                if candidate_id in primary_upstream:
                    definite_dependency = True
                    independence_problems.append(f"{candidate_id} is upstream of exposed supplier {pid}")
                if pid in candidate_upstream:
                    definite_dependency = True
                    independence_problems.append(f"{candidate_id} depends on exposed supplier {pid}")
                shared = sorted(primary_upstream & candidate_upstream)
                if shared:
                    definite_dependency = True
                    independence_problems.append(f"shares upstream supplier(s) with {pid}: {', '.join(shared)}")

        if definite_dependency:
            is_independent = False
        elif supplier_not_in_graph:
            is_independent = None
        else:
            is_independent = True

        # 2. Capacity assessment against summed exposed capacity
        if flagged_insufficient:
            capacity_status = "insufficient"
            capacity_note = "supplier marked 'insufficient' in suppliers.csv"
        elif candidate_cap is None:
            capacity_status = "unknown"
            capacity_note = "candidate capacity missing in supplier_materials.csv"
        elif summed_exposed_capacity == UNKNOWN:
            capacity_status = "unknown"
            capacity_note = "summed exposed capacity is unknown (capacity missing for some exposed suppliers)"
        elif summed_exposed_capacity <= 0:
            capacity_status = "sufficient"
            capacity_note = f"{_show(candidate_cap)} units/month available"
        else:
            ratio = candidate_cap / summed_exposed_capacity
            capacity_note = (
                f"{_show(candidate_cap)} vs {_show(summed_exposed_capacity)} units/month "
                f"({format(ratio, '.0%')} of summed exposed capacity)"
            )
            if candidate_cap >= summed_exposed_capacity:
                capacity_status = "sufficient"
            else:
                capacity_status = "insufficient"

        # 3. Verdict for candidate
        if is_independent is False or capacity_status == "insufficient":
            verdict = "NOT_GENUINE"
        elif is_independent is True and capacity_status == "sufficient":
            verdict = "GENUINE"
        else:
            verdict = UNKNOWN  # undecided due to missing independence or capacity data

        reasons = list(independence_problems)
        if capacity_status != "sufficient":
            reasons.append(f"capacity {capacity_status}: {capacity_note}")

        candidate_reports.append({
            "candidate_id": candidate_id,
            "verdict": verdict,
            "independent": is_independent,
            "capacity_status": capacity_status,
            "candidate_capacity_units": candidate_cap,
            "capacity_note": capacity_note,
            "reasons": sorted(set(reasons)),
        })

        if verdict == "GENUINE":
            any_genuine = True
        elif verdict == UNKNOWN:
            any_undecided = True

    # Combined material backup status
    if any_genuine:
        status = MITIGATED
        explanation = "At least one other supplier is a genuine independent backup with sufficient capacity for the combined failure."
    elif any_undecided:
        status = UNKNOWN
        explanation = "No confirmed genuine backup, and at least one candidate could not be judged (data missing)."
    elif not candidates:
        status = UNMITIGATED
        explanation = (
            "Every supplier listed for this material in supplier_materials.csv is part of the affected chain, "
            "so no unaffected alternative exists."
        )
    else:
        status = UNMITIGATED
        explanation = "Other suppliers are listed, but none is a genuine independent backup with sufficient combined capacity."

    # 4. Individual single-supplier backup statuses for comparison
    individual_statuses = {}
    for fid in failed_ids:
        down_fid = set(find_downstream_suppliers(graph, fid))
        chain_fid = {fid} | down_fid
        exposed_fid = [s for s in lookups["suppliers_of"].get(material_id, set()) if s in chain_fid]
        if not exposed_fid:
            individual_statuses[fid] = "NOT_EXPOSED"
        else:
            ind_report = _assess_backup(material_id, exposed_fid, impact_type, lookups, upstream_of)
            individual_statuses[fid] = ind_report["status"]

    return {
        "material_id": material_id,
        "material_name": _text((lookups["material_info"].get(material_id) or {}).get("material_name")),
        "impact_type": impact_type,
        "status": status,
        "exposed_suppliers": sorted(exposed),
        "summed_exposed_capacity_units": summed_exposed_capacity,
        "candidates": candidate_reports,
        "individual_backup_statuses": individual_statuses,
        "explanation": explanation,
    }


# ---------------------------------------------------------------------------
# Main function: simulate_multiple_supplier_disruption
# ---------------------------------------------------------------------------

def simulate_multiple_supplier_disruption(supplier_ids, duration_days=7, data=None, graph=None):
    """
    Simulate the simultaneous failure of two or more suppliers and return an explainable report.

    Parameters:
      supplier_ids   collection of supplier IDs failing simultaneously, e.g. ['SUP-T2-01', 'SUP-T2-02']
      duration_days  scenario duration in days (default: 7); scenario label only
      data, graph    from load_all_data() / get_supply_chain_graph(); loaded if None

    Returns:
      dictionary (the multi-supplier disruption impact report)
    """
    if data is None:
        data = load_all_data(verbose=False)
    if graph is None:
        graph = get_supply_chain_graph(data)

    # 1. Input validation (Stage 1)
    failed_ids = _validate_supplier_ids(graph, supplier_ids)
    duration_days = _check_duration(duration_days)
    failed_set = set(failed_ids)

    lookups = _build_lookups(data)
    gaps = []

    # 2. Failed suppliers info & mapping check (Stage 1)
    failed_suppliers_report = []
    unmapped_failed = []
    for sid in failed_ids:
        attrs = graph.nodes[sid]
        materials = sorted(lookups["materials_of"].get(sid, set()))
        mat_known = bool(materials)
        if not mat_known:
            unmapped_failed.append(sid)
            gaps.append(
                f"{sid} (failed) has no row in supplier_materials.csv: its DIRECT materials are UNKNOWN (not none)"
            )
        failed_suppliers_report.append({
            "supplier_id": sid,
            "supplier_name": attrs.get("name", ""),
            "tier": _known(attrs.get("tier")),
            "capacity_status": attrs.get("capacity_status") or UNKNOWN,
            "lead_time_days": _known(attrs.get("lead_time_days")),
            "materials_known": mat_known,
            "direct_material_count": len(materials) if mat_known else UNKNOWN,
            "direct_materials": materials,
        })

    if not unmapped_failed:
        direct_materials_status = KNOWN
        exposure_may_be_understated = False
    elif len(unmapped_failed) < len(failed_ids):
        direct_materials_status = PARTIAL
        exposure_may_be_understated = True
    else:
        direct_materials_status = UNKNOWN
        exposure_may_be_understated = True

    # 3. Downstream suppliers & overlapping dependency handling (Stage 1)
    downstream_by_failed = {}
    reached_by = {}       # downstream_sid -> list of failed_ids that reach it
    nested_failed = {}    # failed_sid -> list of other failed_ids upstream of it

    for fid in failed_ids:
        down = find_downstream_suppliers(graph, fid)
        downstream_by_failed[fid] = down
        for dsid in down:
            if dsid in failed_set:
                # Failed supplier sits downstream of another failed supplier
                nested_failed.setdefault(dsid, []).append(fid)
            else:
                reached_by.setdefault(dsid, []).append(fid)

    # Annotate nested failed suppliers in failed_suppliers_report
    for entry in failed_suppliers_report:
        fid = entry["supplier_id"]
        entry["is_downstream_of_other_failed_suppliers"] = sorted(nested_failed.get(fid, []))

    # Pure downstream suppliers are those in reached_by (failed suppliers excluded)
    pure_downstream_ids = sorted(
        reached_by.keys(),
        key=lambda node_id: (graph.nodes[node_id].get("tier", 0), node_id)
    )
    pure_downstream_set = set(pure_downstream_ids)
    affected_chain = failed_set | pure_downstream_set

    downstream_report = []
    cascading_source = {}  # material_id -> list of downstream suppliers that provide it

    for sid in pure_downstream_ids:
        materials = sorted(lookups["materials_of"].get(sid, set()))
        if not materials:
            gaps.append(f"{sid} (downstream) has no row in supplier_materials.csv: its materials are UNKNOWN")
        for mid in materials:
            cascading_source.setdefault(mid, []).append(sid)

        # Dependency links within the combined affected chain
        links = []
        for upstream in sorted(graph.predecessors(sid)):
            edge = graph.edges[upstream, sid]
            if edge.get("edge_type") == "supplier_dependency" and upstream in affected_chain:
                links.append({
                    "upstream_supplier_id": upstream,
                    "upstream_is_failed_supplier": upstream in failed_set,
                    "dependency_id": edge.get("dependency_id", ""),
                    "dependency_material_id_annotation": edge.get("material_id", ""),
                })

        downstream_report.append({
            "supplier_id": sid,
            "supplier_name": graph.nodes[sid].get("name", ""),
            "tier": _known(graph.nodes[sid].get("tier")),
            "reached_by_failed_suppliers": sorted(reached_by[sid]),
            "caused_by_failed_suppliers": sorted(reached_by[sid]),
            "depends_directly_on_failed_suppliers": sorted(
                l["upstream_supplier_id"] for l in links if l["upstream_is_failed_supplier"]
            ),
            "materials_supplied": materials if materials else UNKNOWN,
            "dependency_links": links,
            "status": "POTENTIALLY_AFFECTED (not assumed to have stopped operating)",
        })

    # 4. Direct and potential cascading materials (Stage 1)
    direct_materials_map = {}  # mid -> list of failed suppliers providing it
    for sid in failed_ids:
        for mid in lookups["materials_of"].get(sid, set()):
            direct_materials_map.setdefault(mid, []).append(sid)

    direct_ids = sorted(direct_materials_map.keys())

    # Material impact mapping: DIRECT beats POTENTIAL_CASCADING
    material_impact = {mid: DIRECT for mid in direct_ids}
    for mid in cascading_source:
        material_impact.setdefault(mid, POTENTIAL_CASCADING)

    # Attribution map: material_id -> list of failed suppliers causing it
    material_causes = {}
    for mid in material_impact:
        causes = set(direct_materials_map.get(mid, []))
        for dsid in cascading_source.get(mid, []):
            causes.update(reached_by.get(dsid, []))
        material_causes[mid] = sorted(causes)

    def material_entry(mid):
        info = lookups["material_info"].get(mid) or {}
        direct_suppliers = sorted(direct_materials_map.get(mid, []))
        downstream_suppliers = sorted(set(cascading_source.get(mid, [])))
        all_exposed = sorted(set(direct_suppliers) | set(downstream_suppliers))
        return {
            "material_id": mid,
            "material_name": _text(info.get("material_name")) or UNKNOWN,
            "impact_type": material_impact[mid],
            "supplied_by_failed_suppliers": direct_suppliers,
            "supplied_by_downstream_suppliers": downstream_suppliers,
            "all_exposed_suppliers": all_exposed,
            "caused_by_failed_suppliers": material_causes.get(mid, []),
            "products": sorted(lookups["products_of"].get(mid, set())),
        }

    direct_materials = [material_entry(m) for m in direct_ids]
    cascading_materials = [
        material_entry(m) for m in sorted(material_impact)
        if material_impact[m] == POTENTIAL_CASCADING
    ]

    for mid in material_impact:
        if mid not in lookups["material_info"]:
            gaps.append(f"{mid} is in supplier_materials.csv but not in materials.csv")

    # 5. Combined backup reassessment (Stage 2)
    upstream_of = {
        sid: set(find_upstream_dependencies(graph, sid))
        for sid in lookups["supplier_info"] if sid in graph
    }
    backup_assessments = []
    for mid in sorted(material_impact):
        exposed = [s for s in lookups["suppliers_of"].get(mid, set()) if s in affected_chain]
        backup_assessments.append(
            _assess_backup_combined(
                material_id=mid,
                exposed=exposed,
                impact_type=material_impact[mid],
                lookups=lookups,
                upstream_of=upstream_of,
                failed_ids=failed_ids,
                graph=graph,
            )
        )

    # 6. Combined inventory analysis (Stage 3)
    inventory = [
        _inventory_for_material(mid, material_impact[mid], lookups, graph, gaps)
        for mid in sorted(material_impact)
    ]
    for inv_entry in inventory:
        inv_entry["caused_by_failed_suppliers"] = material_causes.get(inv_entry["material_id"], [])

    holders = {}
    for row in lookups["inventory_rows"]:
        loc_id = _text(row.get("location_id"))
        mat_id = _text(row.get("material_id"))
        if mat_id in material_impact:
            key = (loc_id, mat_id)
            current = holders.get(key)
            new_impact = material_impact[mat_id]
            if current == DIRECT or new_impact == DIRECT:
                holders[key] = DIRECT
            else:
                holders[key] = POTENTIAL_CASCADING

    # 7. Factories, warehouses, and transport routes (Stage 3)
    supplier_impact = {sid: DIRECT for sid in failed_ids}
    supplier_impact.update({sid: POTENTIAL_CASCADING for sid in pure_downstream_ids})

    factories, warehouses = _find_factories_and_warehouses(graph, holders, supplier_impact)
    location_impact = {f["factory_id"]: f["impact_type"] for f in factories}
    location_impact.update({w["warehouse_id"]: w["impact_type"] for w in warehouses})

    routes = _find_routes(graph, supplier_impact, location_impact)

    def feeding_factories(warehouse_id):
        if warehouse_id not in graph:
            return []
        return sorted(
            p for p in graph.predecessors(warehouse_id)
            if graph.edges[p, warehouse_id].get("edge_type") == "feeds_warehouse"
            and graph.nodes[p].get("node_type") == "factory"
        )

    # Attribution for factories
    factory_causes = {}
    for fac in factories:
        fid = fac["factory_id"]
        causes = set()
        for mid in material_impact:
            if (fid, mid) in holders:
                causes.update(material_causes.get(mid, []))
        for sid in failed_ids:
            for rid, _ in _supplier_routes(graph, sid):
                if _route_destination(graph, rid) == fid:
                    causes.add(sid)
        fac["caused_by_failed_suppliers"] = sorted(causes)
        factory_causes[fid] = causes

    # Attribution for warehouses
    warehouse_causes = {}
    for wh in warehouses:
        wid = wh["warehouse_id"]
        causes = set()
        for mid in material_impact:
            if (wid, mid) in holders:
                causes.update(material_causes.get(mid, []))
        for f in feeding_factories(wid):
            causes.update(factory_causes.get(f, set()))
        wh["caused_by_failed_suppliers"] = sorted(causes)
        warehouse_causes[wid] = causes

    # Attribution for transport routes
    for route in routes:
        rid = route["route_id"]
        causes = set()
        for sid in failed_ids:
            for r, _ in _supplier_routes(graph, sid):
                if r == rid:
                    causes.add(sid)
        for loc in (route.get("origin_id"), route.get("destination_id")):
            if loc in factory_causes:
                causes.update(factory_causes[loc])
            if loc in warehouse_causes:
                causes.update(warehouse_causes[loc])
        route["caused_by_failed_suppliers"] = sorted(causes)

    # 8. Customer orders (Stage 3)
    orders = _find_orders(data, graph, holders, material_impact, lookups, gaps)

    for o in orders["headline_path_supported"]["orders"]:
        order_causes = set()
        for s in o.get("supporting_materials", []):
            mid = s.get("material_id")
            order_causes.update(material_causes.get(mid, []))
        o["caused_by_failed_suppliers"] = sorted(order_causes)

    for o in orders["additional_product_link_only"]["orders"]:
        order_causes = set()
        for s in o.get("supporting_materials", []):
            mid = s.get("material_id")
            order_causes.update(material_causes.get(mid, []))
        o["caused_by_failed_suppliers"] = sorted(order_causes)

    # 9. Fixed gaps and assumptions
    gaps.extend([
        "No consumption or production-rate data: production days remaining cannot be computed.",
        "No shipment schedule, replenishment plan or production plan: delivery delay cannot be estimated.",
        "No bill of materials: factory links rely on inventory rows and supplier routes.",
        "Capacity check evaluates summed capacity of exposed suppliers; current load data is not available.",
        "One candidate backing several materials cannot be checked for shared capacity across materials (no multi-material load data).",
    ])

    assumptions = [
        f"M1  Duration ({duration_days} days) is a scenario label only; not used in calculations.",
        "M2  Simultaneous failure of all listed suppliers; downstream suppliers are potentially affected only.",
        "M3  DIRECT impact beats POTENTIAL_CASCADING if a material or entity is reached both ways.",
        "M4  Exposure is calculated on the union of failures; individual supplier reports are not summed.",
        "M5  Missing information is reported as UNKNOWN or NOT COMPUTED, never zero.",
        "M6  Backup candidates must be independent of ALL exposed suppliers of that material.",
        "M7  Backup capacity is compared against the summed monthly_capacity_units of all exposed suppliers supplying that material.",
        "M8  Missing capacity is treated as UNKNOWN, never as insufficient.",
        "M9  Factory and warehouse links: inventory holding (INVENTORY_LINK) or route arrival (ROUTE_LINK_ONLY/FACTORY_LINK_ONLY); production is not assumed stopped.",
        "M10 Routes are potentially affected; no route is assumed to have failed.",
        "M11 Customer orders: confirmed and planned only; path-supported orders form headline exposure; each order counted once at strongest evidence level.",
        "M12 order_value_inr represents unique potential financial exposure, not actual financial loss.",
    ]

    evidence_levels = {
        "DIRECT": "Supplier is listed for the material in supplier_materials.csv.",
        "POTENTIAL_CASCADING": "Supplier is downstream of a failed supplier; not assumed to have stopped.",
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
    extra = orders["additional_product_link_only"]

    # 10. Overlap Summary (Stage 4)
    individual_reports = []
    for sid in failed_ids:
        ind_rep = simulate_supplier_disruption(sid, duration_days=duration_days, data=data, graph=graph)
        s_info = ind_rep["failed_supplier"]
        h_ind = ind_rep["customer_orders"]["headline_path_supported"]
        individual_reports.append({
            "supplier_id": sid,
            "supplier_name": s_info.get("supplier_name", sid),
            "tier": s_info.get("tier"),
            "direct_material_count": len(ind_rep["direct_materials"]),
            "direct_materials": [m["material_id"] for m in ind_rep["direct_materials"]],
            "headline_order_count": h_ind["order_count"],
            "headline_potential_order_value_exposure_inr": h_ind["potential_value_exposure_inr"],
            "headline_orders": [
                {
                    "order_id": o["order_id"],
                    "order_value_inr": o.get("order_value_inr"),
                    "impact_type": o.get("impact_type"),
                }
                for o in h_ind.get("orders", [])
            ],
        })

    sum_orders = sum(
        r["headline_order_count"] for r in individual_reports
        if isinstance(r["headline_order_count"], (int, float))
    )
    if any(r["headline_potential_order_value_exposure_inr"] == UNKNOWN for r in individual_reports):
        sum_val = UNKNOWN
    else:
        sum_val = sum(
            r["headline_potential_order_value_exposure_inr"] for r in individual_reports
            if isinstance(r["headline_potential_order_value_exposure_inr"], (int, float))
        )

    comb_orders = head["order_count"]
    comb_val = head["potential_value_exposure_inr"]

    order_overlap_count = (sum_orders - comb_orders) if isinstance(comb_orders, (int, float)) else UNKNOWN
    if sum_val != UNKNOWN and comb_val != UNKNOWN:
        val_overlap = sum_val - comb_val
    else:
        val_overlap = UNKNOWN

    order_exposure_map = {}
    for r in individual_reports:
        sid = r["supplier_id"]
        for o in r["headline_orders"]:
            oid = o["order_id"]
            if oid not in order_exposure_map:
                order_exposure_map[oid] = {
                    "order_id": oid,
                    "order_value_inr": o.get("order_value_inr"),
                    "affected_by_failed_suppliers": [],
                }
            order_exposure_map[oid]["affected_by_failed_suppliers"].append(sid)

    overlapping_orders = [
        {
            "order_id": info["order_id"],
            "order_value_inr": info["order_value_inr"],
            "affected_by_failed_suppliers": sorted(info["affected_by_failed_suppliers"]),
            "supplier_count": len(info["affected_by_failed_suppliers"]),
        }
        for info in order_exposure_map.values()
        if len(info["affected_by_failed_suppliers"]) > 1
    ]
    overlapping_orders.sort(key=lambda x: x["order_id"])

    shared_direct_materials = []
    for mid in sorted(direct_materials_map):
        sids = direct_materials_map[mid]
        if len(sids) > 1:
            mat_name = _text(lookups["material_info"].get(mid, {}).get("material_name")) or UNKNOWN
            shared_direct_materials.append({
                "material_id": mid,
                "material_name": mat_name,
                "shared_by_failed_suppliers": sorted(sids),
                "supplier_count": len(sids),
            })

    overlap_summary = {
        "is_additive": False,
        "non_additive_note": (
            "Individual supplier order counts and value exposures are NOT ADDITIVE because multiple "
            "failed suppliers impact shared customer orders and common inventory paths. Simple addition "
            "double-counts orders and financial exposure. Combined unique exposure reflects the true union."
        ),
        "individual_supplier_reports": individual_reports,
        "sum_of_individual_headline_order_counts": sum_orders,
        "sum_of_individual_headline_potential_value_exposure_inr": sum_val,
        "combined_unique_headline_order_count": comb_orders,
        "combined_unique_headline_potential_value_exposure_inr": comb_val,
        "order_count_overlap_avoided": order_overlap_count,
        "value_exposure_overlap_avoided_inr": val_overlap,
        "overlapping_order_count": len(overlapping_orders),
        "overlapping_orders": overlapping_orders,
        "shared_direct_material_count": len(shared_direct_materials),
        "shared_direct_materials": shared_direct_materials,
    }

    report = {
        "scenario": {
            "failed_supplier_ids": failed_ids,
            "failed_supplier_count": len(failed_ids),
            "disruption_duration_days": duration_days,
            "duration_note": "scenario label only; not used in any calculation because there is no consumption data",
            "meaning_of_results": "POTENTIAL exposure found by following dataset links. Not confirmed damage.",
        },
        "failed_suppliers": failed_suppliers_report,
        "nested_failed_suppliers": {k: sorted(v) for k, v in nested_failed.items()},
        "direct_materials_status": direct_materials_status,
        "exposure_may_be_understated": exposure_may_be_understated,
        "direct_materials": direct_materials,
        "downstream_suppliers": downstream_report,
        "potential_cascading_materials": cascading_materials,
        "material_impact": material_impact,
        "backup_assessment": backup_assessments,
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
        "overlap_summary": overlap_summary,
        "summary": {
            "failed_supplier_count": len(failed_ids),
            "direct_material_count": len(direct_materials) if direct_materials_status == KNOWN else (
                f"{len(direct_materials)} (partial)" if direct_materials_status == PARTIAL else UNKNOWN
            ),
            "downstream_supplier_count": len(downstream_report),
            "potential_cascading_material_count": len(cascading_materials),
            "total_exposed_material_count": len(material_impact),
            "backup_mitigated_count": sum(1 for b in backup_assessments if b["status"] == MITIGATED),
            "backup_unmitigated_count": sum(1 for b in backup_assessments if b["status"] == UNMITIGATED),
            "backup_unknown_count": sum(1 for b in backup_assessments if b["status"] == UNKNOWN),
            "backup_status_by_material": {b["material_id"]: b["status"] for b in backup_assessments},
            "factory_count": len(factories),
            "warehouse_count": len(warehouses),
            "route_count": len(routes),
            "headline_order_count": head["order_count"],
            "headline_potential_order_value_exposure_inr": head["potential_value_exposure_inr"],
            "additional_product_link_only_order_count": extra["order_count"],
            "upper_bound_potential_order_value_exposure_inr": orders["upper_bound_including_product_link_only_inr"],
            "sum_of_individual_headline_order_counts": sum_orders,
            "sum_of_individual_headline_potential_value_exposure_inr": sum_val,
            "order_count_overlap_avoided": order_overlap_count,
            "value_exposure_overlap_avoided_inr": val_overlap,
        },
        "evidence_levels": evidence_levels,
        "assumptions": assumptions,
        "data_gaps": gaps,
    }

    return _sanitize_for_json(report)


# ---------------------------------------------------------------------------
# Stage 4: JSON Sanitizer, Currency Formatter, and Plain Text Report Formatter
# ---------------------------------------------------------------------------

def _sanitize_for_json(obj):
    """
    Ensure the object and all nested structures contain only standard JSON types
    (dict, list, str, int, float, bool, None).
    Converts sets/tuples to lists, NumPy types to standard Python primitives.
    """
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_json(item) for item in obj]
    elif isinstance(obj, pd.Series):
        return _sanitize_for_json(obj.to_dict())
    elif isinstance(obj, pd.DataFrame):
        return _sanitize_for_json(obj.to_dict(orient="records"))
    elif hasattr(obj, "item"):
        return obj.item()
    elif isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    else:
        return str(obj)


def _money(value):
    """Format numeric values as INR currency string, preserving UNKNOWN."""
    if value == UNKNOWN or value is None:
        return UNKNOWN
    try:
        val = int(value) if value == int(value) else value
        return "INR {:,}".format(val)
    except (TypeError, ValueError):
        return str(value)


def format_multi_disruption_report(report):
    """
    Produce a comprehensive, readable plain text summary of the multiple
    supplier disruption report.
    Presents scenarios, overlap analysis, direct/cascading exposure, backups,
    locations, routes, orders, financial exposure, assumptions, and data gaps.
    Preserves UNKNOWN and NOT COMPUTED cleanly.
    """
    s = report["scenario"]
    lines = [
        "=" * 74,
        "MULTIPLE SUPPLIER DISRUPTION IMPACT REPORT (POTENTIAL EXPOSURE)",
        "=" * 74,
        "Failed Suppliers : " + ", ".join(s["failed_supplier_ids"]) + f" ({s['failed_supplier_count']} suppliers)",
        f"Duration         : {s['disruption_duration_days']} days ({s['duration_note']})",
        f"Assessment Scope : {s['meaning_of_results']}",
        "",
    ]

    # Failed suppliers detail
    lines.append("FAILED SUPPLIERS DETAIL:")
    for fs in report.get("failed_suppliers", []):
        mat_count = fs.get("direct_material_count")
        lines.append(f"  - {fs['supplier_id']}: {fs['supplier_name']} (tier {fs['tier']}) -> {mat_count} direct material(s)")
    lines.append("")

    # Overlap summary
    ov = report.get("overlap_summary", {})
    if ov:
        lines += [
            "-" * 74,
            "OVERLAP SUMMARY (UNION VS INDIVIDUAL REPORTS)",
            "-" * 74,
            f"  NOTE: {ov.get('non_additive_note', '')}",
            "",
            "  Individual Supplier Reports (Phase 1 Baseline):",
        ]
        for ind in ov.get("individual_supplier_reports", []):
            lines.append(
                f"    - {ind['supplier_id']} ({ind['supplier_name']}): "
                f"{ind['headline_order_count']} headline orders | "
                f"Potential Exposure: {_money(ind['headline_potential_order_value_exposure_inr'])}"
            )
        lines += [
            "",
            "  Comparison:",
            f"    - Sum of Individual Headline Orders : {ov.get('sum_of_individual_headline_order_counts')} orders (naive sum - double counted!)",
            f"    - Sum of Individual Value Exposure  : {_money(ov.get('sum_of_individual_headline_potential_value_exposure_inr'))} (naive sum - double counted!)",
            f"    - Combined Unique Headline Orders   : {ov.get('combined_unique_headline_order_count')} orders (true union)",
            f"    - Combined Unique Value Exposure    : {_money(ov.get('combined_unique_headline_potential_value_exposure_inr'))} (true union, NOT actual loss)",
            f"    - Overlap Prevented (Double-Count)  : {ov.get('order_count_overlap_avoided')} orders | "
            f"{_money(ov.get('value_exposure_overlap_avoided_inr'))} avoided",
            "",
        ]
        shared_mats = ov.get("shared_direct_materials", [])
        if shared_mats:
            lines.append("  Shared Direct Materials (supplied by >= 2 failed suppliers):")
            for sm in shared_mats:
                lines.append(f"    - {sm['material_id']} {sm['material_name']} (shared by: {', '.join(sm['shared_by_failed_suppliers'])})")
            lines.append("")
        else:
            lines.append("  Shared Direct Materials: none")
            lines.append("")

        overlap_orders = ov.get("overlapping_orders", [])
        if overlap_orders:
            lines.append(f"  Overlapping Headline Orders ({len(overlap_orders)} orders affected by >= 2 failed suppliers):")
            for oo in overlap_orders[:10]:
                lines.append(f"    - {oo['order_id']} ({_money(oo['order_value_inr'])}) -> affected by: {', '.join(oo['affected_by_failed_suppliers'])}")
            if len(overlap_orders) > 10:
                lines.append(f"    ... and {len(overlap_orders) - 10} more overlapping orders")
            lines.append("")

    # Direct materials
    lines += [
        "-" * 74,
        f"DIRECT MATERIALS ({report['direct_materials_status']}, {len(report['direct_materials'])} materials)",
        "-" * 74,
    ]
    for m in report.get("direct_materials", []):
        supplied_by = ", ".join(m.get("supplied_by_failed_suppliers", []))
        lines.append(f"  - {m['material_id']} {m['material_name']} (supplied by failed: {supplied_by})")
    if not report.get("direct_materials"):
        lines.append("  (none)")
    lines.append("")

    # Downstream suppliers & potential cascading materials
    downstream = report.get("downstream_suppliers", [])
    cascading = report.get("potential_cascading_materials", [])
    lines += [
        "-" * 74,
        f"DOWNSTREAM & POTENTIAL CASCADING IMPACTS",
        "-" * 74,
        f"Downstream Suppliers ({len(downstream)} suppliers potentially affected, not assumed stopped):",
    ]
    for d in downstream:
        reached = ", ".join(d.get("reached_by_failed_suppliers", []))
        dep_failed = ", ".join(d.get("depends_directly_on_failed_suppliers", []))
        detail = f"reached by failed: {reached}"
        if dep_failed:
            detail += f"; directly depends on: {dep_failed}"
        lines.append(f"  - {d['supplier_id']} {d['supplier_name']} (tier {d['tier']}) -> {detail}")
    if not downstream:
        lines.append("  (none)")

    lines.append("")
    lines.append(f"Potential Cascading Materials ({len(cascading)} materials):")
    for m in cascading:
        via = ", ".join(m.get("supplied_by_downstream_suppliers", []))
        caused = ", ".join(m.get("caused_by_failed_suppliers", []))
        lines.append(f"  - {m['material_id']} {m['material_name']} (via downstream: {via}; caused by failed: {caused})")
    if not cascading:
        lines.append("  (none)")
    lines.append("")

    # Combined backup assessment
    backups = report.get("backup_assessment", [])
    lines += [
        "-" * 74,
        f"COMBINED BACKUP ASSESSMENT ({len(backups)} materials evaluated)",
        "-" * 74,
        "  NOTE: Evaluates candidate capacity against SUMMED capacity of all exposed suppliers,",
        "        and requires genuine independence from all exposed suppliers.",
    ]
    for b in backups:
        ind_str = ", ".join(f"{k}: {v}" for k, v in b.get("individual_backup_statuses", {}).items())
        lines.append(f"  - {b['material_id']} [{b['impact_type']}]: {b['status']} - {b['explanation']}")
        lines.append(f"      summed exposed capacity: {b.get('summed_exposed_capacity_units')} units/month | individual: {ind_str}")
        for c in b.get("candidates", []):
            reasons_str = f" ({'; '.join(c['reasons'])})" if c.get("reasons") else ""
            lines.append(f"      candidate {c['candidate_id']}: {c['verdict']}{reasons_str}")
    lines.append("")

    # Inventory
    inv_list = report.get("inventory", [])
    lines += [
        "-" * 74,
        f"INVENTORY IMPACT ({len(inv_list)} materials, pooled on hand vs reorder point)",
        "-" * 74,
    ]
    for inv in inv_list:
        p = inv["pooled_all_locations"]
        caused = ", ".join(inv.get("caused_by_failed_suppliers", []))
        lines.append(
            f"  - {inv['material_id']} {inv['material_name']} [{inv['impact_type']}]: pooled {p['status']} "
            f"(on hand {p['on_hand']} vs reorder {p['reorder_point']}); shortage exposure: {inv['shortage_exposure']} "
            f"(caused by: {caused})"
        )
        for loc in inv.get("locations", []):
            lines.append(
                f"      {loc['location_id']} ({loc['location_kind']}): "
                f"{loc['quantity_on_hand']} vs {loc['reorder_point']} -> {loc['status']}"
            )
    lines.append("")

    # Factories, warehouses, transport routes
    factories = report.get("factories", [])
    warehouses = report.get("warehouses", [])
    routes = report.get("transport_routes", [])
    lines += [
        "-" * 74,
        "LOCATIONS & TRANSPORT ROUTES (Potentially affected, not assumed stopped/failed)",
        "-" * 74,
        f"Factories ({len(factories)}):",
    ]
    for f in factories:
        caused = ", ".join(f.get("caused_by_failed_suppliers", []))
        lines.append(f"  - {f['factory_id']} {f['name']} [{f['impact_type']}, {f['evidence_level']}] (caused by: {caused})")
    if not factories:
        lines.append("  (none)")

    lines.append(f"Warehouses ({len(warehouses)}):")
    for w in warehouses:
        caused = ", ".join(w.get("caused_by_failed_suppliers", []))
        lines.append(f"  - {w['warehouse_id']} {w['name']} [{w['impact_type']}, {w['evidence_level']}] (caused by: {caused})")
    if not warehouses:
        lines.append("  (none)")

    lines.append(f"Transport Routes ({len(routes)}):")
    for r in routes:
        caused = ", ".join(r.get("caused_by_failed_suppliers", []))
        lines.append(
            f"  - {r['route_id']} {r['origin_id']} -> {r['destination_id']} "
            f"[{r['evidence_level']}] (caused by: {caused})"
        )
    if not routes:
        lines.append("  (none)")
    lines.append("")

    # Customer orders
    o = report.get("customer_orders", {})
    h = o.get("headline_path_supported", {})
    a = o.get("additional_product_link_only", {})
    lines += [
        "-" * 74,
        "CUSTOMER ORDERS & FINANCIAL EXPOSURE (Confirmed + planned, each counted once)",
        "-" * 74,
        f"  HEADLINE (Path Supported Exposure): {h.get('order_count', 0)} orders, "
        f"potential value exposure {_money(h.get('potential_value_exposure_inr'))} (NOT an actual loss)",
        f"     of which DIRECT: {h.get('direct_order_count', 0)} / POTENTIAL_CASCADING-only: {h.get('potential_cascading_order_count', 0)}",
        f"     Orders: {', '.join(x['order_id'] for x in h.get('orders', [])) or '(none)'}",
        f"  ADDITIONAL, PRODUCT_LINK_ONLY (Upper bound, not in headline): {a.get('order_count', 0)} orders, "
        f"{_money(a.get('potential_value_exposure_inr'))}",
        f"     Orders: {', '.join(x['order_id'] for x in a.get('orders', [])) or '(none)'}",
        f"  Upper bound incl. product-link-only: {_money(o.get('upper_bound_including_product_link_only_inr'))}",
        "",
    ]

    # Operational impact
    lines += [
        "-" * 74,
        "OPERATIONAL DELAYS & PRODUCTION IMPACT",
        "-" * 74,
        f"  Delivery delay           : {report['delivery_delay']['status']} - {report['delivery_delay']['reason']}",
        f"  Production days remaining: {report['production_days_remaining']['status']} - {report['production_days_remaining']['reason']}",
        "",
        "ASSUMPTIONS:",
    ]
    for asm in report.get("assumptions", []):
        lines.append(f"  {asm}")
    lines.append("")
    lines.append("DATA GAPS:")
    for g in report.get("data_gaps", []):
        lines.append(f"  - {g}")
    lines.append("=" * 74)

    return "\n".join(lines)


if __name__ == "__main__":
    # Example: python -m src.multi_disruption_simulation SUP-T2-01 SUP-T2-03
    chosen_suppliers = sys.argv[1:] if len(sys.argv) > 1 else ["SUP-T2-01", "SUP-T2-03"]
    rep = simulate_multiple_supplier_disruption(chosen_suppliers)
    print(format_multi_disruption_report(rep))

