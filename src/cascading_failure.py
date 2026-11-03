"""
cascading_failure.py
--------------------
AUTOPILOT 2.0 - Member 4: Cascading Failure Simulation & Recovery Plan Challenger.

This module stress-tests a Member 3 recovery plan. It does not rank candidates,
allocate quantity, or run emergency recovery. Those stay in
``src/recovery_optimisation.py``.

Responsibilities
----------------
- Detect shared upstream (Tier-2 / Tier-3) dependencies on the Member 1 graph.
- Look up which suppliers use a transport route.
- Report route-failure exposure (potential only; suppliers are not assumed shut).
- Reuse Member 2 for single and multiple supplier disruption simulation.
- Invalidate affected allocations in a recovery plan copy.
- Re-call Member 3 ``optimise_recovery()`` with the same material and quantity.
- Compare the original plan with the revised plan.

Design rules
------------
- UNKNOWN means the dataset/graph could not determine a value. It is never 0.
- The input graph, data dict, and original recovery plan are never mutated.
- Supplier IDs, capacities, costs, and routes always come from existing data.
- Missing route or supplier IDs are reported, not invented.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from src.data_loader import load_all_data
from src.disruption_simulation import simulate_supplier_disruption
from src.multi_disruption_simulation import simulate_multiple_supplier_disruption
from src.recovery_optimisation import (
    DEP_DIRECTLY_AFFECTED,
    DEP_SHARED_UPSTREAM,
    STATUS_FEASIBLE,
    STATUS_NO_PLAN,
    STATUS_PARTIAL,
    UNKNOWN,
    optimise_recovery,
)
from src.supply_chain_graph import (
    find_upstream_dependencies,
    get_supply_chain_graph,
)


# ---------------------------------------------------------------------------
# Cell helpers (same missing-data rules as Members 1-3)
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _number(value: Any) -> Optional[float]:
    if value is None or value == UNKNOWN:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    try:
        if pd.isna(num):
            return None
    except (TypeError, ValueError):
        pass
    return num


def _tidy(n: Any) -> Any:
    if n is None:
        return None
    try:
        if n == int(n):
            return int(n)
    except (TypeError, ValueError):
        pass
    return n


def _sanitize_for_json(obj: Any) -> Any:
    """JSON types only. Mirrors Member 2's sanitiser."""
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_sanitize_for_json(item) for item in obj]
    if isinstance(obj, pd.Series):
        return _sanitize_for_json(obj.to_dict())
    if isinstance(obj, pd.DataFrame):
        return _sanitize_for_json(obj.to_dict(orient="records"))
    if hasattr(obj, "item") and not isinstance(obj, (bytes, str)):
        try:
            return obj.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    return str(obj)


def _unique_ids(values: Optional[List[Any]]) -> List[str]:
    """Strip, drop blanks, keep first-seen order."""
    cleaned: List[str] = []
    seen: Set[str] = set()
    for raw in values or []:
        sid = _text(raw)
        if not sid or sid in seen:
            continue
        seen.add(sid)
        cleaned.append(sid)
    return cleaned


def _is_supplier_node(graph: Any, node_id: str) -> bool:
    return (
        graph is not None
        and node_id in graph
        and graph.nodes[node_id].get("node_type") == "supplier"
    )


def _is_route_node(graph: Any, node_id: str) -> bool:
    return (
        graph is not None
        and node_id in graph
        and graph.nodes[node_id].get("node_type") == "transport_route"
    )


def _ensure_data_graph(
    data: Optional[Dict], graph: Optional[Any]
) -> Tuple[Dict, Any]:
    if data is None:
        data = load_all_data(verbose=False)
    if graph is None:
        graph = get_supply_chain_graph(data)
    return data, graph


# ---------------------------------------------------------------------------
# Task: shared upstream detection
# ---------------------------------------------------------------------------

def detect_shared_upstream_dependencies(
    graph: Any,
    supplier_ids: Optional[List[str]],
) -> Dict[str, Dict[str, Any]]:
    """
    For each supplier, list all upstream suppliers and which other ids in
    ``supplier_ids`` share those ancestors.

    Uses Member 1 ``find_upstream_dependencies`` (supplier_dependency edges only).

    A supplier missing from the graph is not skipped: ``upstream_ids`` is
    UNKNOWN so callers do not treat "not found" as "no parents".
    """
    result: Dict[str, Dict[str, Any]] = {}
    ids = _unique_ids(supplier_ids)
    upstream_map: Dict[str, Optional[Set[str]]] = {}

    for sid in ids:
        if not _is_supplier_node(graph, sid):
            upstream_map[sid] = None
        else:
            upstream_map[sid] = set(find_upstream_dependencies(graph, sid))

    for sid in ids:
        upstream = upstream_map[sid]
        if upstream is None:
            result[sid] = {
                "supplier_id": sid,
                "in_graph": False,
                "upstream_ids": UNKNOWN,
                "depends_on": UNKNOWN,
                "shared_with": {},
            }
            continue

        shared_with: Dict[str, List[str]] = {}
        depends_on = [other for other in ids if other != sid and other in upstream]
        for other in ids:
            if other == sid:
                continue
            other_up = upstream_map[other]
            if other_up is None:
                continue
            shared = sorted(upstream & other_up)
            if shared:
                shared_with[other] = shared

        result[sid] = {
            "supplier_id": sid,
            "in_graph": True,
            "upstream_ids": sorted(upstream),
            "depends_on": sorted(depends_on),
            "shared_with": shared_with,
        }

    return result


# ---------------------------------------------------------------------------
# Task: route lookup and route-failure exposure
# ---------------------------------------------------------------------------

def suppliers_using_route(graph: Any, route_id: str) -> List[str]:
    """
    Return supplier IDs with a ``uses_route`` edge into ``route_id``.

    Missing / non-route ids return []. Callers that need UNKNOWN should use
    ``simulate_route_failure``.
    """
    rid = _text(route_id)
    if not _is_route_node(graph, rid):
        return []

    found: List[str] = []
    for pred in graph.predecessors(rid):
        edge = graph.edges[pred, rid]
        if edge.get("edge_type") != "uses_route":
            continue
        if graph.nodes[pred].get("node_type") != "supplier":
            continue
        if pred not in found:
            found.append(pred)
    found.sort()
    return found


def _routes_used_by_supplier(graph: Any, supplier_id: str) -> List[str]:
    if not _is_supplier_node(graph, supplier_id):
        return []
    routes: List[str] = []
    for neigh in graph.successors(supplier_id):
        edge = graph.edges[supplier_id, neigh]
        if edge.get("edge_type") != "uses_route":
            continue
        if graph.nodes[neigh].get("node_type") != "transport_route":
            continue
        if neigh not in routes:
            routes.append(neigh)
    return sorted(routes)


def simulate_route_failure(
    route_id: str,
    data: Optional[Dict] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Report potential exposure if one transport route cannot be used.

    This does not call Member 3 and does not mark supplier companies as failed.
    """
    data, graph = _ensure_data_graph(data, graph)
    rid = _text(route_id)

    if not rid:
        return _sanitize_for_json({
            "route_id": route_id,
            "status": UNKNOWN,
            "reason": "route_id must be a non-empty string",
            "exposed_suppliers": [],
            "exposed_locations": [],
            "meaning_of_results": (
                "POTENTIAL exposure. A failed route is not a supplier shutdown."
            ),
        })

    if not _is_route_node(graph, rid):
        reason = "route_id not in the supply-chain graph as a transport_route node: " + rid
        if graph is not None and rid in graph:
            reason = (
                rid + " exists in the graph but node_type is "
                + str(graph.nodes[rid].get("node_type"))
                + ", not transport_route"
            )
        return _sanitize_for_json({
            "route_id": rid,
            "status": UNKNOWN,
            "reason": reason,
            "exposed_suppliers": [],
            "exposed_locations": [],
            "meaning_of_results": (
                "POTENTIAL exposure. A failed route is not a supplier shutdown."
            ),
        })

    attrs = graph.nodes[rid]
    origin_id = _text(attrs.get("origin_id"))
    destination_id = _text(attrs.get("destination_id"))
    exposed_suppliers = suppliers_using_route(graph, rid)
    exposed_locations = []
    for loc in (origin_id, destination_id):
        if loc and loc not in exposed_locations:
            exposed_locations.append(loc)

    return _sanitize_for_json({
        "route_id": rid,
        "status": "ROUTE_FAILED",
        "reason": "Route " + rid + " is treated as unavailable in this scenario.",
        "origin_id": origin_id or UNKNOWN,
        "destination_id": destination_id or UNKNOWN,
        "mode": _text(attrs.get("mode")) or UNKNOWN,
        "transit_days": attrs.get("transit_days") if attrs.get("transit_days") is not None else UNKNOWN,
        "exposed_suppliers": exposed_suppliers,
        "exposed_locations": exposed_locations,
        "meaning_of_results": (
            "POTENTIAL exposure found from uses_route / origin / destination links. "
            "Supplier companies are not assumed to have stopped operating."
        ),
    })


def transport_excluded_suppliers(
    graph: Any,
    failed_route_ids: Optional[List[str]],
) -> Dict[str, Any]:
    """
    Suppliers whose every graph ``uses_route`` target is in ``failed_route_ids``.

    Suppliers with no uses_route edges are not excluded (transport is UNKNOWN).
    """
    failed = _unique_ids(failed_route_ids)
    unknown_routes = [rid for rid in failed if not _is_route_node(graph, rid)]
    known_failed = [rid for rid in failed if _is_route_node(graph, rid)]
    known_failed_set = set(known_failed)
    excluded: List[str] = []
    details: List[Dict[str, Any]] = []

    if graph is None or not known_failed_set:
        return {
            "excluded_supplier_ids": [],
            "unknown_route_ids": unknown_routes,
            "details": details,
        }

    for node_id, attrs in graph.nodes(data=True):
        if attrs.get("node_type") != "supplier":
            continue
        routes = _routes_used_by_supplier(graph, node_id)
        if not routes:
            continue
        if all(r in known_failed_set for r in routes):
            excluded.append(node_id)
            details.append({
                "supplier_id": node_id,
                "failed_routes": list(routes),
                "reason": (
                    node_id + " has no remaining uses_route edge outside the failed route set"
                ),
            })

    excluded.sort()
    return {
        "excluded_supplier_ids": excluded,
        "unknown_route_ids": unknown_routes,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Task: reuse Member 2 disruption simulation
# ---------------------------------------------------------------------------

def simulate_cascading_supplier_failures(
    supplier_ids: Optional[List[str]],
    duration_days: int = 7,
    data: Optional[Dict] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Dispatch to Member 2.

    * 1 valid supplier  -> ``simulate_supplier_disruption``
    * 2+ valid suppliers -> ``simulate_multiple_supplier_disruption``

    Unknown ids are not passed to Member 2 (which would raise). They are
    listed as UNKNOWN in ``data_gaps``.
    """
    data, graph = _ensure_data_graph(data, graph)
    requested = _unique_ids(supplier_ids)
    valid: List[str] = []
    unknown: List[str] = []
    gaps: List[str] = []

    if not requested:
        return _sanitize_for_json({
            "status": UNKNOWN,
            "valid_supplier_ids": [],
            "unknown_supplier_ids": [],
            "member2_report": None,
            "data_gaps": ["No supplier_ids were provided."],
        })

    for sid in requested:
        if _is_supplier_node(graph, sid):
            valid.append(sid)
        else:
            unknown.append(sid)
            gaps.append("Unknown or non-supplier id (not simulated): " + sid)

    member2_report = None
    status = "SIMULATED"
    if len(valid) == 1:
        member2_report = simulate_supplier_disruption(
            valid[0], duration_days=duration_days, data=data, graph=graph
        )
    elif len(valid) >= 2:
        member2_report = simulate_multiple_supplier_disruption(
            valid, duration_days=duration_days, data=data, graph=graph
        )
    else:
        status = UNKNOWN
        gaps.append("No valid supplier ids remain; Member 2 simulation was not run.")

    return _sanitize_for_json({
        "status": status,
        "requested_supplier_ids": requested,
        "valid_supplier_ids": valid,
        "unknown_supplier_ids": unknown,
        "member2_report": member2_report,
        "data_gaps": gaps,
    })


# ---------------------------------------------------------------------------
# Task: invalidate allocations without re-optimising
# ---------------------------------------------------------------------------

REASON_FAILED_SUPPLIER = "FAILED_SUPPLIER"
REASON_UPSTREAM_FAILURE = "UPSTREAM_FAILURE"
REASON_ROUTE_FAILURE = "ROUTE_FAILURE"


def _unwrap_recovery_result(original_plan: Dict) -> Tuple[Dict, Dict, bool]:
    """
    Accept either the full ``optimise_recovery()`` dict or a single plan dict.

    Returns (bundle_or_empty, recommended_or_plan, is_full_bundle).
    """
    if not isinstance(original_plan, dict):
        return {}, {}, False
    if isinstance(original_plan.get("recommended_plan"), dict):
        return original_plan, original_plan["recommended_plan"], True
    return {}, original_plan, False


def _allocation_routes(alloc: Dict) -> List[str]:
    routes = []
    for row in alloc.get("reachable_routes") or []:
        if isinstance(row, dict):
            rid = _text(row.get("route_id"))
        else:
            rid = _text(row)
        if rid and rid not in routes:
            routes.append(rid)
    return routes


def _recompute_invalidated_plan(plan: Dict) -> None:
    """Update allocated / unmet / status from remaining selected_suppliers."""
    required = _number(plan.get("required_quantity"))
    total = 0.0
    any_missing = False
    remaining = plan.get("selected_suppliers") or []
    if not remaining:
        plan["allocated_quantity"] = 0
        if required is None:
            plan["unmet_quantity"] = UNKNOWN
            plan["status"] = UNKNOWN
        else:
            plan["unmet_quantity"] = _tidy(required)
            plan["status"] = STATUS_NO_PLAN
        return

    for alloc in remaining:
        qty = _number(alloc.get("allocated_quantity"))
        if qty is None:
            any_missing = True
        else:
            total += qty

    if any_missing:
        plan["allocated_quantity"] = UNKNOWN
        plan["unmet_quantity"] = UNKNOWN
        plan["status"] = UNKNOWN
        return

    plan["allocated_quantity"] = _tidy(total)
    if required is None:
        plan["unmet_quantity"] = UNKNOWN
        plan["status"] = UNKNOWN
        return

    unmet = max(required - total, 0.0)
    plan["unmet_quantity"] = _tidy(unmet)
    if total >= required:
        plan["status"] = STATUS_FEASIBLE
    elif total > 0:
        plan["status"] = STATUS_PARTIAL
    else:
        plan["status"] = STATUS_NO_PLAN


def invalidate_recovery_allocations(
    recovery_plan: Dict,
    additional_failed_supplier_ids: Optional[List[str]] = None,
    failed_route_ids: Optional[List[str]] = None,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Return a copy of the recovery plan with affected allocations removed.

    An allocation is removed when:
      * its supplier_id is in the additional failed set, or
      * it depends on an additional failed supplier (graph upstream walk), or
      * every listed reachable_route is in failed_route_ids.

    Remaining reachable_routes that match a failed route are dropped from the
    copy. Totals are recomputed by summing leftover allocations only.
    """
    if not isinstance(recovery_plan, dict):
        return _sanitize_for_json({
            "status": UNKNOWN,
            "reason": "recovery_plan must be a dict",
            "plan": {},
            "invalidated_allocations": [],
            "warnings": [],
        })

    bundle, plan_in, is_bundle = _unwrap_recovery_result(recovery_plan)
    plan = copy.deepcopy(plan_in)
    failed_suppliers = set(_unique_ids(additional_failed_supplier_ids))
    failed_routes = set(_unique_ids(failed_route_ids))
    warnings: List[str] = []
    invalidated: List[Dict[str, Any]] = []

    original_failed = []
    if is_bundle:
        original_failed = _unique_ids(bundle.get("failed_supplier_ids"))
    all_failed_for_dep = failed_suppliers | set(original_failed)

    kept: List[Dict[str, Any]] = []
    for alloc in copy.deepcopy(plan.get("selected_suppliers") or []):
        sid = _text(alloc.get("supplier_id"))
        reasons: List[str] = []
        codes: List[str] = []

        if not sid:
            warnings.append("Allocation is missing supplier_id; left in place.")
            kept.append(alloc)
            continue

        if sid in failed_suppliers:
            reasons.append(sid + " is in the additional failed supplier set")
            codes.append(REASON_FAILED_SUPPLIER)

        upstream: Optional[Set[str]] = None
        if graph is not None:
            if not _is_supplier_node(graph, sid):
                warnings.append(
                    sid + ": not a supplier node in the graph; upstream impact is UNKNOWN"
                )
            else:
                upstream = set(find_upstream_dependencies(graph, sid))
                hits = sorted(all_failed_for_dep & upstream)
                extra_hits = [h for h in hits if h in failed_suppliers]
                if extra_hits:
                    reasons.append(
                        sid + " depends on newly failed supplier(s): " + ", ".join(extra_hits)
                    )
                    codes.append(REASON_UPSTREAM_FAILURE)

        listed_shared = alloc.get("shared_upstreams") or []
        shared_hits = [
            _text(u) for u in listed_shared
            if _text(u) in failed_suppliers
        ]
        if shared_hits and REASON_UPSTREAM_FAILURE not in codes:
            # Plan already recorded a shared ancestor that has now failed.
            reasons.append(
                sid + " shares now-failed upstream supplier(s): " + ", ".join(shared_hits)
            )
            codes.append(REASON_UPSTREAM_FAILURE)

        alloc_routes = _allocation_routes(alloc)
        if failed_routes and alloc_routes:
            remaining_routes = [
                row for row in (alloc.get("reachable_routes") or [])
                if _text(row.get("route_id") if isinstance(row, dict) else row) not in failed_routes
            ]
            dropped = [r for r in alloc_routes if r in failed_routes]
            alloc["reachable_routes"] = remaining_routes
            if dropped and not remaining_routes:
                reasons.append(
                    sid + " has no remaining reachable_routes after route failure(s): "
                    + ", ".join(dropped)
                )
                codes.append(REASON_ROUTE_FAILURE)
            elif dropped:
                warnings.append(
                    sid + ": dropped failed route(s) " + ", ".join(dropped)
                    + " but other reachable_routes remain"
                )
        elif failed_routes and not alloc_routes:
            warnings.append(
                sid + ": no reachable_routes on the allocation; route impact is UNKNOWN"
            )

        if codes:
            invalidated.append({
                "supplier_id": sid,
                "allocated_quantity_removed": alloc.get("allocated_quantity", UNKNOWN),
                "reason": "; ".join(reasons),
                "reason_codes": codes,
            })
        else:
            kept.append(alloc)

    plan["selected_suppliers"] = kept
    _recompute_invalidated_plan(plan)

    return _sanitize_for_json({
        "plan": plan,
        "invalidated_allocations": invalidated,
        "warnings": warnings,
        "additional_failed_supplier_ids": sorted(failed_suppliers),
        "failed_route_ids": sorted(failed_routes),
    })


# ---------------------------------------------------------------------------
# Task: challenge Member 3 plan and re-optimise
# ---------------------------------------------------------------------------

def _selected_ids(plan: Dict) -> List[str]:
    ids = []
    for alloc in plan.get("selected_suppliers") or []:
        sid = _text(alloc.get("supplier_id"))
        if sid and sid not in ids:
            ids.append(sid)
    return ids


def _dependency_warnings(
    graph: Any,
    selected_ids: List[str],
    failed_ids: List[str],
    shared_map: Dict[str, Dict[str, Any]],
) -> List[str]:
    warnings: List[str] = []
    failed_set = set(failed_ids)
    for sid in selected_ids:
        info = shared_map.get(sid) or {}
        if info.get("upstream_ids") == UNKNOWN:
            warnings.append(
                sid + ": upstream dependency is UNKNOWN (supplier not in graph)"
            )
            continue
        depends = [
            u for u in (info.get("depends_on") or []) if u in failed_set
        ]
        if depends:
            warnings.append(
                sid + " is directly exposed to failed supplier(s): " + ", ".join(depends)
            )
        for other, shared in (info.get("shared_with") or {}).items():
            if other in failed_set or other in selected_ids:
                warnings.append(
                    sid + " shares upstream supplier(s) " + ", ".join(shared)
                    + " with " + other
                )
        if _is_supplier_node(graph, sid):
            upstream = set(info.get("upstream_ids") or [])
            failed_ancestors = sorted(upstream & failed_set)
            if failed_ancestors:
                warnings.append(
                    sid + " has failed ancestor(s): " + ", ".join(failed_ancestors)
                )
    return warnings


def _compare_plans(
    original_plan: Dict,
    revised_bundle: Optional[Dict],
    required_quantity: Any,
) -> Dict[str, Any]:
    orig_status = original_plan.get("status", UNKNOWN)
    orig_alloc = original_plan.get("allocated_quantity", UNKNOWN)
    orig_unmet = original_plan.get("unmet_quantity", UNKNOWN)
    orig_ids = _selected_ids(original_plan)

    if not isinstance(revised_bundle, dict) or "recommended_plan" not in revised_bundle:
        return {
            "original_status": orig_status,
            "revised_status": UNKNOWN,
            "original_allocated": orig_alloc,
            "revised_allocated": UNKNOWN,
            "original_unmet": orig_unmet,
            "revised_unmet": UNKNOWN,
            "remaining_demand": required_quantity if required_quantity is not None else UNKNOWN,
            "unmet_quantity": UNKNOWN,
            "feasibility_changed": UNKNOWN,
            "suppliers_removed": orig_ids,
            "suppliers_added": [],
            "revised_plan_available": False,
        }

    revised_plan = revised_bundle["recommended_plan"]
    new_ids = _selected_ids(revised_plan)
    orig_set, new_set = set(orig_ids), set(new_ids)
    revised_status = revised_plan.get("status", UNKNOWN)

    feasibility_changed: Any = UNKNOWN
    if orig_status != UNKNOWN and revised_status != UNKNOWN:
        feasibility_changed = orig_status != revised_status

    remaining = required_quantity if required_quantity is not None else original_plan.get(
        "required_quantity", UNKNOWN
    )

    return {
        "original_status": orig_status,
        "revised_status": revised_status,
        "original_allocated": orig_alloc,
        "revised_allocated": revised_plan.get("allocated_quantity", UNKNOWN),
        "original_unmet": orig_unmet,
        "revised_unmet": revised_plan.get("unmet_quantity", UNKNOWN),
        "remaining_demand": remaining if remaining is not None else UNKNOWN,
        "unmet_quantity": revised_plan.get("unmet_quantity", UNKNOWN),
        "feasibility_changed": feasibility_changed,
        "suppliers_removed": [s for s in orig_ids if s not in new_set],
        "suppliers_added": [s for s in new_ids if s not in orig_set],
        "revised_plan_available": True,
    }


def _resolve_destination_ids(
    destination_ids: Optional[List[str]],
    bundle: Dict,
    rec_plan: Dict,
    is_bundle: bool,
) -> Optional[List[str]]:
    """
    Preserve destinations for the Member 3 re-call. Never invent locations.

    Explicit argument wins. Otherwise use a key already present on the original
    bundle or plan. Member 3 does not currently echo destination_ids, so the
    caller should pass them when they were used on the first optimisation.
    """
    if destination_ids is not None:
        return list(destination_ids)
    if is_bundle and "destination_ids" in bundle:
        stored = bundle.get("destination_ids")
        return list(stored) if stored is not None else None
    if "destination_ids" in rec_plan:
        stored = rec_plan.get("destination_ids")
        return list(stored) if stored is not None else None
    return None


def challenge_recovery_plan(
    original_plan: Dict,
    additional_failed_supplier_ids: Optional[List[str]] = None,
    failed_route_ids: Optional[List[str]] = None,
    data: Optional[Dict] = None,
    graph: Optional[Any] = None,
    weights: Optional[Dict[str, float]] = None,
    destination_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Challenge a Member 3 recovery plan and re-run ``optimise_recovery``.

    Parameters
    ----------
    original_plan
        Full dict from ``optimise_recovery()`` (preferred) or a single plan
        dict with ``selected_suppliers``.
    additional_failed_supplier_ids
        Extra supplier failures (backup, emergency, upstream, simultaneous).
    failed_route_ids
        Transport routes treated as unavailable in this challenge.
    data, graph, weights
        Same objects Member 3 used. Graph and data are only read.
    destination_ids
        Optional factory/warehouse ids passed through to Member 3. If omitted,
        any ``destination_ids`` already on the original plan are reused.

    Material id and required quantity always come from the original plan.
    They are never invented from inventory or orders.
    """
    data, graph = _ensure_data_graph(data, graph)
    original_copy = copy.deepcopy(original_plan) if isinstance(original_plan, dict) else {}
    bundle, rec_plan, is_bundle = _unwrap_recovery_result(
        original_copy if original_copy else {}
    )
    gaps: List[str] = []
    warnings: List[str] = []

    if not rec_plan:
        return _sanitize_for_json({
            "error": "Invalid original_plan",
            "input_errors": ["original_plan must be a Member 3 recovery result or plan dict"],
            "original_plan": original_copy,
            "revised_plan": None,
            "data_gaps": gaps,
        })

    material_id = _text(
        (bundle.get("material_id") if is_bundle else None) or rec_plan.get("material_id")
    )
    required_quantity = _number(
        (bundle.get("required_quantity") if is_bundle else None)
        or rec_plan.get("required_quantity")
    )
    original_failed = _unique_ids(
        (bundle.get("failed_supplier_ids") if is_bundle else None)
        or rec_plan.get("failed_supplier_ids")
    )
    original_supplier_id = (
        (bundle.get("original_supplier_id") if is_bundle else None)
        or rec_plan.get("original_supplier_id")
    )
    resolved_destinations = _resolve_destination_ids(
        destination_ids, bundle, rec_plan, is_bundle
    )

    extra_requested = _unique_ids(additional_failed_supplier_ids)
    extra_valid = [s for s in extra_requested if _is_supplier_node(graph, s)]
    extra_unknown = [s for s in extra_requested if s not in extra_valid]
    for sid in extra_unknown:
        gaps.append("Additional failed supplier is UNKNOWN (not a supplier node): " + sid)

    route_ids = _unique_ids(failed_route_ids)
    route_reports = [simulate_route_failure(rid, data=data, graph=graph) for rid in route_ids]
    for report in route_reports:
        if report.get("status") == UNKNOWN:
            gaps.append("Failed route is UNKNOWN: " + str(report.get("route_id")))

    transport = transport_excluded_suppliers(graph, route_ids)
    for rid in transport.get("unknown_route_ids") or []:
        if "Failed route is UNKNOWN: " + rid not in gaps:
            gaps.append("Failed route is UNKNOWN: " + rid)

    transport_excluded = transport.get("excluded_supplier_ids") or []
    if transport_excluded:
        warnings.append(
            "TRANSPORT EXCLUSION (not a confirmed supplier shutdown): "
            + ", ".join(transport_excluded)
            + " have no remaining uses_route edges outside the failed route set. "
            "They are passed to Member 3 as failed_supplier_ids so they are not re-selected."
        )

    # Combined failed set for Member 3: original + extra valid + transport exclusions.
    combined_failed = _unique_ids(original_failed + extra_valid + transport_excluded)

    inspect_ids = _unique_ids(
        _selected_ids(rec_plan) + combined_failed + extra_requested
    )
    shared_map = detect_shared_upstream_dependencies(graph, inspect_ids)
    warnings.extend(
        _dependency_warnings(graph, _selected_ids(rec_plan), combined_failed, shared_map)
    )
    # Keep first-seen wording; duplicate ancestor/shared lines are not useful.
    warnings = list(dict.fromkeys(warnings))

    invalidation = invalidate_recovery_allocations(
        original_copy if is_bundle else rec_plan,
        additional_failed_supplier_ids=extra_valid,
        failed_route_ids=[
            rid for rid in route_ids if _is_route_node(graph, rid)
        ],
        graph=graph,
    )
    warnings.extend(invalidation.get("warnings") or [])

    revised_plan = None
    if not material_id:
        gaps.append("original_plan has no material_id; Member 3 was not re-called.")
    elif required_quantity is None:
        gaps.append(
            "original_plan has no numeric required_quantity; Member 3 was not re-called."
        )
    else:
        revised_plan = optimise_recovery(
            material_id=material_id,
            required_quantity=required_quantity,
            failed_supplier_ids=combined_failed,
            destination_ids=resolved_destinations,
            original_supplier_id=original_supplier_id,
            data=data,
            graph=graph,
            weights=weights,
        )

    comparison = _compare_plans(
        rec_plan,
        revised_plan if isinstance(revised_plan, dict) else None,
        _tidy(required_quantity) if required_quantity is not None else rec_plan.get("required_quantity"),
    )

    disruption = simulate_cascading_supplier_failures(
        combined_failed if len(combined_failed) >= 1 else extra_requested,
        data=data,
        graph=graph,
    )

    return _sanitize_for_json({
        "material_id": material_id or UNKNOWN,
        "required_quantity": (
            _tidy(required_quantity) if required_quantity is not None else UNKNOWN
        ),
        "destination_ids": resolved_destinations,
        "original_failed_supplier_ids": original_failed,
        "additional_failed_supplier_ids": extra_requested,
        "additional_failed_supplier_ids_valid": extra_valid,
        "combined_failed_supplier_ids": combined_failed,
        "failed_route_ids": route_ids,
        "transport_excluded_supplier_ids": transport_excluded,
        "route_failure_reports": route_reports,
        "shared_upstream_dependencies": shared_map,
        "invalidated_allocations": invalidation.get("invalidated_allocations") or [],
        "invalidated_plan": invalidation.get("plan") or {},
        "original_plan": original_copy,
        "revised_plan": revised_plan,
        "comparison": comparison,
        "member2_disruption": {
            "status": disruption.get("status"),
            "valid_supplier_ids": disruption.get("valid_supplier_ids"),
            "unknown_supplier_ids": disruption.get("unknown_supplier_ids"),
            "summary": (disruption.get("member2_report") or {}).get("summary"),
        },
        "dependency_warnings": warnings,
        "data_gaps": gaps + list(disruption.get("data_gaps") or []),
    })


# ---------------------------------------------------------------------------
# CLI smoke test (synthetic-safe defaults still go through load_all_data)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import os
    import sys

    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    _mid = sys.argv[1] if len(sys.argv) > 1 else "MAT-02"
    _qty = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    _failed = sys.argv[3:] if len(sys.argv) > 3 else ["SUP-T1-03"]

    _data = load_all_data(verbose=False)
    _graph = get_supply_chain_graph(_data)
    _original = optimise_recovery(
        material_id=_mid,
        required_quantity=_qty,
        failed_supplier_ids=_failed,
        data=_data,
        graph=_graph,
    )
    _extra = []
    rec = _original.get("recommended_plan") or {}
    for row in rec.get("selected_suppliers") or []:
        if row.get("dependency_status") in (DEP_SHARED_UPSTREAM, DEP_DIRECTLY_AFFECTED):
            _extra.extend(row.get("shared_upstreams") or [])
    result = challenge_recovery_plan(
        original_plan=_original,
        additional_failed_supplier_ids=_extra,
        data=_data,
        graph=_graph,
    )
    print(json.dumps(result, indent=2, default=str))
