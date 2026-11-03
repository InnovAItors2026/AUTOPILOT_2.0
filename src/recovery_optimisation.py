"""
recovery_optimisation.py
------------------------
AUTOPILOT 2.0 - Member 3: Backup Supplier Intelligence & Recovery Optimisation.

Given a disruption event (one or more failed suppliers) and a material that
must be re-sourced, this module:

  Task 1  - Classifies suppliers: PRIMARY, BACKUP, SECONDARY, EMERGENCY.
  Task 2  - Verifies material compatibility (rejects incompatible suppliers).
  Task 3  - Evaluates stock and capacity feasibility per candidate.
  Task 4  - Collects cost and delivery data; marks missing values UNKNOWN.
  Task 5  - Checks transport reachability via Member 1 graph + routes CSV.
  Task 6  - Checks shared upstream dependency via Member 1 graph.
  Task 7  - Ranks candidates with a transparent, configurable weighted score.
  Task 8  - Allocates demand across multiple suppliers (greedy, MOQ-safe).
  Task 9  - Builds three plan variants: BALANCED, LOWEST_COST, FASTEST.
  Task 10 - Emergency Recovery Mode when normal recovery is insufficient.
  Task 11 - Returns a structured, JSON-serialisable recovery plan dict.
  Task 13 - Accepts Member 2 disruption report directly via wrapper function.
  Task 14 - Validates all inputs; handles missing / bad data gracefully.

Design rules
------------
- UNKNOWN means "exists but could not be determined from the dataset".
- Hard constraints are enforced BEFORE ranking; none are silently relaxed.
- Actual dataset values are always preferred over any default or estimate.
- Missing information is collected in the ``missing_information`` list.
- No circular imports: this module imports FROM supplier_risk and
  disruption_simulation; it is NOT imported by them.

Integration
-----------
Member 4 (Challenger): call optimise_recovery(); inspect returned dict;
  simulate additional failures; call optimise_recovery() again.
Member 5 (Streamlit): call optimise_recovery(); json.dumps(result).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Set, Tuple

import pandas as pd

from src.data_loader import load_all_data
from src.disruption_impact import find_downstream_suppliers  # noqa: F401 (available for callers)
from src.supplier_risk import check_backup_candidate  # noqa: F401 (available for callers)
from src.supply_chain_graph import (
    find_upstream_dependencies,
    get_supply_chain_graph,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Status / label constants
# ---------------------------------------------------------------------------

UNKNOWN = "UNKNOWN"
NOT_COMPUTED = "NOT_COMPUTED"

# Task 1 - Supplier classification
CLASS_PRIMARY = "PRIMARY"
CLASS_BACKUP = "BACKUP"
CLASS_SECONDARY = "SECONDARY"
CLASS_EMERGENCY = "EMERGENCY"

# Task 3 - Feasibility
FEASIBLE = "FEASIBLE"
PARTIALLY_FEASIBLE = "PARTIALLY_FEASIBLE"
INFEASIBLE = "INFEASIBLE"
FEASIBILITY_UNKNOWN = "FEASIBILITY_UNKNOWN"

# Task 5 - Transport
TRANSPORT_AVAILABLE = "AVAILABLE"
TRANSPORT_UNKNOWN = "UNKNOWN"
TRANSPORT_UNAVAILABLE = "UNAVAILABLE"

# Task 6 - Upstream dependency
DEP_INDEPENDENT = "INDEPENDENT"
DEP_SHARED_UPSTREAM = "SHARED_UPSTREAM"
DEP_DIRECTLY_AFFECTED = "DIRECTLY_AFFECTED"
DEP_UNKNOWN = "UNKNOWN"

# Task 9 / 11 - Recovery plan status
STATUS_FEASIBLE = "FEASIBLE"
STATUS_PARTIAL = "PARTIAL_RECOVERY"
STATUS_NO_PLAN = "NO_FEASIBLE_PLAN"
STATUS_EMERGENCY = "EMERGENCY_RECOVERY"

# Task 9 - Optimisation objectives
OBJ_BALANCED = "BALANCED"
OBJ_LOWEST_COST = "LOWEST_COST"
OBJ_FASTEST = "FASTEST"

# Task 7 - Default scoring weights (must sum to 1.0)
# Each weight is documented: what it measures and why it has this value.
DEFAULT_WEIGHTS: Dict[str, float] = {
    "material_ok": 0.30,     # hard gate: incompatible supplier always scores 0
    "feasibility": 0.20,     # stock + capacity: can it actually supply the qty?
    "delivery_time": 0.20,   # shorter lead time = faster recovery
    "unit_cost": 0.15,       # lower cost = less additional procurement spend
    "independence": 0.10,    # no shared upstream = genuinely independent backup
    "transport": 0.05,       # verified route to destination
}


# ---------------------------------------------------------------------------
# Small private cell-level helpers
# ---------------------------------------------------------------------------

def _text(value: Any) -> str:
    """CSV cell -> clean string; None or NaN becomes ''."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _number(value: Any) -> Optional[float]:
    """CSV cell -> float, or None when missing / non-numeric."""
    if value is None:
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
    """Return int when float is whole (600.0 -> 600), else float. None stays None."""
    if n is None:
        return None
    try:
        if n == int(n):
            return int(n)
    except (TypeError, ValueError):
        pass
    return n


def _rows(df: Any) -> List[Dict]:
    """DataFrame or list -> list of row dicts; empty list when None or empty."""
    if df is None:
        return []
    if isinstance(df, pd.DataFrame):
        if df.empty:
            return []
        return df.to_dict("records")
    return list(df)


# ---------------------------------------------------------------------------
# Task 14 - Input validation helpers
# ---------------------------------------------------------------------------

def _validate_supplier_id(
    supplier_id: Any, graph: Any
) -> Tuple[str, Optional[str]]:
    """
    Validate a supplier_id string.
    Returns (cleaned_id, error_message). error_message is None when valid.
    """
    if not isinstance(supplier_id, str) or not supplier_id.strip():
        return "", "supplier_id must be a non-empty string, got: " + repr(supplier_id)
    sid = supplier_id.strip()
    if graph is not None and sid not in graph:
        return sid, "supplier_id not in the supply-chain graph: " + sid
    if graph is not None and graph.nodes[sid].get("node_type") != "supplier":
        return sid, sid + " exists in graph but is not a supplier node"
    return sid, None


def _validate_material_id(
    material_id: Any, material_info: Dict
) -> Tuple[str, Optional[str]]:
    """Validate a material_id. Returns (cleaned_id, error_message)."""
    if not isinstance(material_id, str) or not material_id.strip():
        return "", "material_id must be a non-empty string, got: " + repr(material_id)
    mid = material_id.strip()
    if mid not in material_info:
        return mid, "material_id not found in materials.csv: " + mid
    return mid, None


def _validate_quantity(
    quantity: Any, label: str = "required_quantity"
) -> Tuple[Optional[float], Optional[str]]:
    """Validate a positive quantity. Returns (value, error_message)."""
    num = _number(quantity)
    if num is None:
        return None, label + " must be a positive number, got: " + repr(quantity)
    if num <= 0:
        return None, label + " must be positive, got: " + str(num)
    return num, None


# ---------------------------------------------------------------------------
# Phase B/C - Build lookup dictionaries from loaded data (called once)
# ---------------------------------------------------------------------------

def _build_lookups(data: Dict) -> Dict:
    """
    Build all fast-lookup dictionaries needed by the recovery engine.
    Called once per optimise_recovery() invocation for consistency.
    """
    supplier_info: Dict[str, Dict] = {}
    for row in _rows(data.get("suppliers")):
        sid = _text(row.get("supplier_id"))
        if sid:
            supplier_info[sid] = row

    material_info: Dict[str, Dict] = {}
    for row in _rows(data.get("materials")):
        mid = _text(row.get("material_id"))
        if mid:
            material_info[mid] = row

    # supplier_materials: (supplier_id, material_id) -> row
    sm_rows: Dict[Tuple[str, str], Dict] = {}
    suppliers_of: Dict[str, Set[str]] = {}   # material_id -> {supplier_id, ...}
    materials_of: Dict[str, Set[str]] = {}   # supplier_id -> {material_id, ...}
    for row in _rows(data.get("supplier_materials")):
        sid = _text(row.get("supplier_id"))
        mid = _text(row.get("material_id"))
        if not sid or not mid:
            continue
        sm_rows[(sid, mid)] = row
        suppliers_of.setdefault(mid, set()).add(sid)
        materials_of.setdefault(sid, set()).add(mid)

    # inventory: material_id -> [rows]
    inventory_by_material: Dict[str, List[Dict]] = {}
    for row in _rows(data.get("inventory")):
        mid = _text(row.get("material_id"))
        if mid:
            inventory_by_material.setdefault(mid, []).append(row)

    # transport_routes: origin_id -> [route rows]; route_id -> row
    routes_from: Dict[str, List[Dict]] = {}
    route_info: Dict[str, Dict] = {}
    for row in _rows(data.get("transport_routes")):
        rid = _text(row.get("route_id"))
        orig = _text(row.get("origin_id"))
        if rid:
            route_info[rid] = row
        if orig:
            routes_from.setdefault(orig, []).append(row)

    return {
        "supplier_info": supplier_info,
        "material_info": material_info,
        "sm_rows": sm_rows,
        "suppliers_of": suppliers_of,
        "materials_of": materials_of,
        "inventory_by_material": inventory_by_material,
        "routes_from": routes_from,
        "route_info": route_info,
    }


# ---------------------------------------------------------------------------
# Task 1 - Supplier classification
# ---------------------------------------------------------------------------

def classify_supplier(
    supplier_id: str,
    material_id: str,
    lookups: Dict,
) -> str:
    """
    Classify a supplier for a specific material.

    PRIMARY   - is_backup == 0 (or missing) AND no other non-backup listed.
    BACKUP    - is_backup == 1 in supplier_materials.csv.
    SECONDARY - listed but not flagged backup; another primary also exists.
    EMERGENCY - not listed for this material in supplier_materials.csv at all.

    The dataset's is_backup column (0 or 1) is the authoritative source.
    Verified backup mappings (from HANDOVER_MEMBER1.md):
      SUP-T1-04 / MAT-02  (WesternCell Packs - battery pack backup)
      SUP-T1-02 / MAT-03  (Coromandel Screens - OLED display backup)
    """
    sm_row = lookups["sm_rows"].get((supplier_id, material_id))
    if sm_row is None:
        return CLASS_EMERGENCY  # not listed for this material

    is_backup_flag = _number(sm_row.get("is_backup"))
    if is_backup_flag == 1:
        return CLASS_BACKUP

    # Count other non-backup suppliers for this material.
    other_primaries = [
        s for s in lookups["suppliers_of"].get(material_id, set())
        if s != supplier_id
        and _number((lookups["sm_rows"].get((s, material_id)) or {}).get("is_backup")) != 1
    ]
    if other_primaries:
        return CLASS_SECONDARY
    return CLASS_PRIMARY


# ---------------------------------------------------------------------------
# Task 2 - Material compatibility
# ---------------------------------------------------------------------------

def check_material_compatibility(
    supplier_id: str,
    material_id: str,
    lookups: Dict,
) -> Tuple[bool, str]:
    """
    Verify that supplier_id lists material_id in supplier_materials.csv.

    Returns (compatible: bool, reason: str).
    A supplier is NEVER considered simply because it has capacity.
    It must be explicitly listed for the required material.
    """
    if material_id not in lookups["material_info"]:
        return False, "Material " + material_id + " does not exist in materials.csv"
    sm_row = lookups["sm_rows"].get((supplier_id, material_id))
    if sm_row is None:
        return False, (
            supplier_id + " has no row in supplier_materials.csv for "
            + material_id + " - material incompatibility, rejected"
        )
    return True, "Compatible: listed in supplier_materials.csv for " + material_id


# ---------------------------------------------------------------------------
# Task 3 - Stock and capacity feasibility
# ---------------------------------------------------------------------------

def assess_feasibility(
    supplier_id: str,
    material_id: str,
    required_quantity: float,
    lookups: Dict,
    missing_info: List[str],
) -> Dict:
    """
    Evaluate how much of required_quantity the supplier can realistically supply.

    Data sources:
      monthly_capacity_units  from supplier_materials.csv  (supply ceiling)
      quantity_on_hand        from inventory.csv (all locations, summed)
      moq_units               from supplier_materials.csv  (minimum order)
      capacity_status         from suppliers.csv           (explicit flag)

    Rules:
      - Missing stock is NOT treated as zero or unlimited.
      - Missing capacity is NOT treated as zero or unlimited.
      - quantity_available = min(capacity, stock) using only known values.
      - When BOTH capacity and stock are unknown: FEASIBILITY_UNKNOWN.
      - explicit capacity_status == 'insufficient' -> INFEASIBLE immediately.
    """
    sm_row = lookups["sm_rows"].get((supplier_id, material_id)) or {}
    sup_row = lookups["supplier_info"].get(supplier_id) or {}

    capacity = _number(sm_row.get("monthly_capacity_units"))
    moq = _number(sm_row.get("moq_units"))
    cap_status = _text(sup_row.get("capacity_status")).lower()

    # Explicit insufficient flag wins.
    if cap_status == "insufficient":
        return {
            "feasibility_status": INFEASIBLE,
            "capacity_units": _tidy(capacity),
            "stock_on_hand": UNKNOWN,
            "moq_units": _tidy(moq),
            "quantity_available": 0,
            "quantity_to_allocate": 0,
            "reason": supplier_id + " is marked capacity_status=insufficient in suppliers.csv",
        }

    # Pool stock from inventory.csv across all locations for this material.
    inv_rows = lookups["inventory_by_material"].get(material_id, [])
    stock_total: Optional[float] = None
    stock_missing = False
    for inv_row in inv_rows:
        q = _number(inv_row.get("quantity_on_hand"))
        if q is None:
            stock_missing = True
        else:
            stock_total = (stock_total or 0.0) + q

    if stock_missing and stock_total is None:
        stock_display: Any = UNKNOWN
    elif stock_missing:
        # Partial data: do not show a partial sum as if it were the total.
        stock_display = UNKNOWN
        missing_info.append(
            "inventory.csv has missing quantity_on_hand rows for "
            + material_id + "; pooled stock is UNKNOWN"
        )
    else:
        stock_display = _tidy(stock_total)

    # Determine supply ceiling.
    # FIX (Issue A/B): capacity (monthly_capacity_units) is what the SUPPLIER can
    # produce and deliver.  quantity_on_hand in inventory.csv is existing BUYER-SIDE
    # stock already at factories/warehouses — it has no relationship to what the
    # supplier can ship.  Using min(capacity, stock) would cap every supplier at the
    # shared on-hand inventory figure and break multi-supplier joint allocation.
    #
    # Rule:
    #   - When capacity is known  -> use capacity as the supply ceiling.
    #   - When capacity is unknown -> fall back to pooled inventory as a proxy
    #     (conservative, with a warning so the caller knows it is a proxy).
    #   - When BOTH are unknown   -> FEASIBILITY_UNKNOWN (handled below).
    if capacity is None and stock_total is None:
        missing_info.append(
            supplier_id + " / " + material_id
            + ": no capacity or stock data found; feasibility is UNKNOWN"
        )
        return {
            "feasibility_status": FEASIBILITY_UNKNOWN,
            "capacity_units": UNKNOWN,
            "stock_on_hand": UNKNOWN,
            "moq_units": _tidy(moq),
            "quantity_available": UNKNOWN,
            "quantity_to_allocate": UNKNOWN,
            "reason": "Both capacity and stock unknown for " + supplier_id + "/" + material_id,
        }

    if capacity is not None:
        # Primary path: use the supplier's own production/delivery capacity.
        quantity_available = capacity
    else:
        # Fallback: capacity unknown; use pooled on-hand inventory as a proxy.
        # This may overstate available supply — flag it explicitly.
        quantity_available = stock_total
        missing_info.append(
            supplier_id + "/" + material_id
            + ": monthly_capacity_units unknown; using pooled on-hand inventory ("
            + str(_tidy(stock_total)) + " units) as proxy supply ceiling"
            + " — actual supplier capacity may differ"
        )

    # Enforce MOQ.
    if moq is not None and quantity_available < moq:
        return {
            "feasibility_status": INFEASIBLE,
            "capacity_units": _tidy(capacity),
            "stock_on_hand": stock_display,
            "moq_units": _tidy(moq),
            "quantity_available": _tidy(quantity_available),
            "quantity_to_allocate": 0,
            "reason": (
                "Available " + str(_tidy(quantity_available))
                + " < MOQ " + str(_tidy(moq)) + " for " + supplier_id
            ),
        }

    quantity_to_allocate = min(quantity_available, required_quantity)

    if quantity_to_allocate <= 0:
        status = INFEASIBLE
        reason = "Effective available quantity is zero or negative for " + supplier_id
    elif quantity_to_allocate >= required_quantity:
        status = FEASIBLE
        reason = (
            supplier_id + " can fully satisfy "
            + str(_tidy(required_quantity)) + " units"
        )
    else:
        status = PARTIALLY_FEASIBLE
        reason = (
            supplier_id + " can partially satisfy: "
            + str(_tidy(quantity_to_allocate)) + " of "
            + str(_tidy(required_quantity)) + " required"
        )

    return {
        "feasibility_status": status,
        "capacity_units": _tidy(capacity),
        "stock_on_hand": stock_display,
        "moq_units": _tidy(moq),
        "quantity_available": _tidy(quantity_available),
        "quantity_to_allocate": _tidy(quantity_to_allocate),
        "reason": reason,
    }


# ---------------------------------------------------------------------------
# Task 4 - Cost and delivery evaluation
# ---------------------------------------------------------------------------

def assess_cost_and_delivery(
    supplier_id: str,
    material_id: str,
    original_supplier_id: Optional[str],
    lookups: Dict,
    missing_info: List[str],
) -> Dict:
    """
    Collect unit cost and lead time from the dataset.

    All values come from actual CSV data - nothing is invented.
    Additional procurement cost is calculated ONLY when both the baseline
    (original supplier) and candidate costs are known.
    Missing values are reported as UNKNOWN.
    """
    sm_row = lookups["sm_rows"].get((supplier_id, material_id)) or {}
    sup_row = lookups["supplier_info"].get(supplier_id) or {}

    unit_cost = _number(sm_row.get("unit_cost_inr"))
    # Lead time: try supplier_materials first, then suppliers.csv.
    lead_time = _number(sm_row.get("lead_time_days"))
    if lead_time is None:
        lead_time = _number(sup_row.get("lead_time_days"))

    additional_cost_per_unit: Any = None
    cost_note = "Additional procurement cost not calculated (no original supplier baseline)"

    if original_supplier_id:
        orig_sm = lookups["sm_rows"].get((original_supplier_id, material_id)) or {}
        orig_cost = _number(orig_sm.get("unit_cost_inr"))
        if orig_cost is not None and unit_cost is not None:
            delta = unit_cost - orig_cost
            additional_cost_per_unit = _tidy(delta)
            cost_note = (
                "Additional cost/unit vs " + original_supplier_id + ": "
                + str(_tidy(unit_cost)) + " - " + str(_tidy(orig_cost))
                + " = " + str(_tidy(delta)) + " INR"
            )
        elif orig_cost is None:
            missing_info.append(
                "Original supplier " + original_supplier_id
                + " has no unit_cost_inr for " + material_id
                + "; additional cost comparison not possible"
            )
            cost_note = "Additional cost unknown: original supplier cost missing"
        elif unit_cost is None:
            missing_info.append(
                supplier_id + " unit_cost_inr for " + material_id
                + " missing; additional cost not calculated"
            )
            cost_note = "Additional cost unknown: candidate unit cost missing"

    if unit_cost is None:
        missing_info.append(
            supplier_id + " / " + material_id
            + ": unit_cost_inr missing from supplier_materials.csv"
        )
    if lead_time is None:
        missing_info.append(
            supplier_id + " / " + material_id
            + ": lead_time_days missing from supplier_materials.csv and suppliers.csv"
        )

    return {
        "unit_cost_inr": _tidy(unit_cost) if unit_cost is not None else UNKNOWN,
        "lead_time_days": _tidy(lead_time) if lead_time is not None else UNKNOWN,
        "additional_cost_per_unit_inr": additional_cost_per_unit,
        "cost_note": cost_note,
    }


# ---------------------------------------------------------------------------
# Task 5 - Transportation availability
# ---------------------------------------------------------------------------

def assess_transport(
    supplier_id: str,
    destination_ids: List[str],
    lookups: Dict,
    graph: Any,
    missing_info: List[str],
) -> Dict:
    """
    Check whether the supplier can reach any destination_id using:
      (a) graph uses_route edges pointing from supplier to transport_route nodes
      (b) transport_routes.csv rows where origin_id == supplier_id

    Missing route information -> TRANSPORT_UNKNOWN (not TRANSPORT_UNAVAILABLE).
    A supplier with no verified route must not be treated as fully feasible.
    """
    sup_row = lookups["supplier_info"].get(supplier_id) or {}
    primary_route_id = _text(sup_row.get("primary_route_id"))

    reachable_routes: List[Dict] = []
    status = TRANSPORT_UNKNOWN
    seen_routes: Set[str] = set()

    # (a) Graph-based lookup.
    if graph is not None and supplier_id in graph:
        for neighbor in graph.successors(supplier_id):
            edge = graph.edges.get((supplier_id, neighbor), {})
            if edge.get("edge_type") != "uses_route":
                continue
            if graph.nodes.get(neighbor, {}).get("node_type") != "transport_route":
                continue
            route_id = neighbor
            if route_id in seen_routes:
                continue
            seen_routes.add(route_id)
            rinfo = lookups["route_info"].get(route_id) or {}
            dest_id = _text(rinfo.get("destination_id"))
            transit_days = _number(rinfo.get("transit_days"))
            cost_per_ship = _number(rinfo.get("cost_per_shipment_inr"))
            reachable_routes.append({
                "route_id": route_id,
                "destination_id": dest_id,
                "transit_days": _tidy(transit_days) if transit_days is not None else UNKNOWN,
                "cost_per_shipment_inr": _tidy(cost_per_ship) if cost_per_ship is not None else UNKNOWN,
                "is_primary_route": (route_id == primary_route_id),
            })
            if not destination_ids or dest_id in destination_ids:
                status = TRANSPORT_AVAILABLE

    # (b) CSV-based fallback.
    for route in lookups["routes_from"].get(supplier_id, []):
        route_id = _text(route.get("route_id"))
        if route_id in seen_routes:
            continue
        seen_routes.add(route_id)
        dest_id = _text(route.get("destination_id"))
        transit_days = _number(route.get("transit_days"))
        cost_per_ship = _number(route.get("cost_per_shipment_inr"))
        reachable_routes.append({
            "route_id": route_id,
            "destination_id": dest_id,
            "transit_days": _tidy(transit_days) if transit_days is not None else UNKNOWN,
            "cost_per_shipment_inr": _tidy(cost_per_ship) if cost_per_ship is not None else UNKNOWN,
            "is_primary_route": (route_id == primary_route_id),
        })
        if not destination_ids or dest_id in destination_ids:
            status = TRANSPORT_AVAILABLE

    if not reachable_routes:
        missing_info.append(
            supplier_id + ": no transport route found in graph or transport_routes.csv;"
            " transport feasibility is UNKNOWN"
        )

    return {
        "transport_status": status,
        "reachable_routes": reachable_routes,
        "primary_route_id": primary_route_id or UNKNOWN,
    }


# ---------------------------------------------------------------------------
# Task 6 - Shared upstream dependency check
# ---------------------------------------------------------------------------

def assess_upstream_dependency(
    candidate_id: str,
    failed_supplier_ids: List[str],
    graph: Any,
    missing_info: List[str],
) -> Dict:
    """
    Determine whether candidate_id shares upstream suppliers with the failed set,
    or is itself directly affected.

    Uses Member 1's find_upstream_dependencies() - no duplication.

    Returns:
      dependency_status   DEP_INDEPENDENT | DEP_SHARED_UPSTREAM
                          | DEP_DIRECTLY_AFFECTED | DEP_UNKNOWN
      shared_upstreams    list of shared upstream supplier IDs
      reason              human-readable explanation
    """
    if graph is None or candidate_id not in graph:
        missing_info.append(
            candidate_id + ": not in graph; upstream dependency is UNKNOWN"
        )
        return {
            "dependency_status": DEP_UNKNOWN,
            "shared_upstreams": [],
            "reason": "Supplier not in graph; cannot determine upstream dependencies",
        }

    # Is the candidate itself in the failed set?
    if candidate_id in failed_supplier_ids:
        return {
            "dependency_status": DEP_DIRECTLY_AFFECTED,
            "shared_upstreams": [],
            "reason": candidate_id + " is one of the failed suppliers",
        }

    candidate_upstream: Set[str] = set(find_upstream_dependencies(graph, candidate_id))

    # Is any failed supplier upstream of the candidate?
    directly_exposed = [f for f in failed_supplier_ids if f in candidate_upstream]
    if directly_exposed:
        return {
            "dependency_status": DEP_DIRECTLY_AFFECTED,
            "shared_upstreams": directly_exposed,
            "reason": (
                candidate_id + " depends on failed supplier(s): "
                + ", ".join(sorted(directly_exposed))
            ),
        }

    # Do the candidate and any failed supplier share a common upstream?
    shared: Set[str] = set()
    for failed_id in failed_supplier_ids:
        if failed_id not in graph:
            continue
        failed_upstream: Set[str] = set(find_upstream_dependencies(graph, failed_id))
        shared |= (candidate_upstream & failed_upstream)

    if shared:
        return {
            "dependency_status": DEP_SHARED_UPSTREAM,
            "shared_upstreams": sorted(shared),
            "reason": (
                candidate_id + " shares upstream supplier(s) with failed set: "
                + ", ".join(sorted(shared))
                + ". A failure at those nodes could affect this candidate too."
            ),
        }

    return {
        "dependency_status": DEP_INDEPENDENT,
        "shared_upstreams": [],
        "reason": candidate_id + " is independent of all failed suppliers",
    }


# ---------------------------------------------------------------------------
# Task 7 - Candidate ranking
# ---------------------------------------------------------------------------

def _candidate_score(
    candidate: Dict,
    required_quantity: float,
    weights: Dict[str, float],
    all_costs: List[Optional[float]],
    all_lead_times: List[Optional[float]],
) -> float:
    """
    Compute a 0-100 ranking score. Higher = better candidate.

    Missing dimensions are skipped and remaining weights re-normalised.
    Hard gates (incompatible, infeasible) return 0 immediately.
    The formula is documented here; weights are in DEFAULT_WEIGHTS.
    """
    if not candidate.get("material_compatible", False):
        return 0.0
    feas = candidate.get("feasibility_status", INFEASIBLE)
    if feas == INFEASIBLE:
        return 0.0

    components: Dict[str, Optional[float]] = {}

    # material_ok gate (already passed)
    components["material_ok"] = 100.0

    # feasibility
    if feas == FEASIBLE:
        components["feasibility"] = 100.0
    elif feas == PARTIALLY_FEASIBLE:
        qty = _number(candidate.get("quantity_available"))
        if qty is not None:
            components["feasibility"] = 50.0 + 50.0 * min(qty / required_quantity, 1.0)
        else:
            components["feasibility"] = 50.0
    else:
        components["feasibility"] = None  # FEASIBILITY_UNKNOWN: skip

    # delivery_time: lower is better (min-max normalised, inverted)
    lead = _number(candidate.get("lead_time_days"))
    known_times = [t for t in all_lead_times if t is not None]
    if lead is not None and known_times:
        t_min, t_max = min(known_times), max(known_times)
        components["delivery_time"] = (
            100.0 * (t_max - lead) / (t_max - t_min) if t_max > t_min else 100.0
        )
    else:
        components["delivery_time"] = None

    # unit_cost: lower is better (min-max normalised, inverted)
    cost = _number(candidate.get("unit_cost_inr"))
    known_costs = [c for c in all_costs if c is not None]
    if cost is not None and known_costs:
        c_min, c_max = min(known_costs), max(known_costs)
        components["unit_cost"] = (
            100.0 * (c_max - cost) / (c_max - c_min) if c_max > c_min else 100.0
        )
    else:
        components["unit_cost"] = None

    # independence
    dep = candidate.get("dependency_status", DEP_UNKNOWN)
    if dep == DEP_INDEPENDENT:
        components["independence"] = 100.0
    elif dep == DEP_SHARED_UPSTREAM:
        components["independence"] = 30.0
    elif dep == DEP_DIRECTLY_AFFECTED:
        components["independence"] = 0.0
    else:
        components["independence"] = None  # DEP_UNKNOWN: skip

    # transport
    t_stat = candidate.get("transport_status", TRANSPORT_UNKNOWN)
    if t_stat == TRANSPORT_AVAILABLE:
        components["transport"] = 100.0
    elif t_stat == TRANSPORT_UNAVAILABLE:
        components["transport"] = 0.0
    else:
        components["transport"] = None  # unknown: skip

    # Weighted average over known components only (re-normalise missing weights).
    total_w = 0.0
    weighted_sum = 0.0
    for key, val in components.items():
        w = weights.get(key, 0.0)
        if val is not None:
            weighted_sum += w * val
            total_w += w

    return weighted_sum / total_w if total_w > 0.0 else 0.0


def rank_candidates(
    candidates: List[Dict],
    required_quantity: float,
    weights: Optional[Dict[str, float]] = None,
) -> List[Dict]:
    """
    Add ``ranking_score`` to every candidate and sort descending (best first).
    Weights are configurable; DEFAULT_WEIGHTS used when not supplied.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    all_costs = [_number(c.get("unit_cost_inr")) for c in candidates]
    all_lead_times = [_number(c.get("lead_time_days")) for c in candidates]

    for cand in candidates:
        cand["ranking_score"] = round(
            _candidate_score(cand, required_quantity, weights, all_costs, all_lead_times),
            2,
        )

    candidates.sort(key=lambda c: c["ranking_score"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Task 8 - Multi-supplier quantity allocation
# ---------------------------------------------------------------------------

def allocate_quantity(
    ranked_candidates: List[Dict],
    required_quantity: float,
) -> Tuple[List[Dict], Any, Any]:
    """
    Greedily allocate required_quantity across ranked (best-first) candidates.

    Hard rules enforced:
      - Total allocated <= required_quantity.
      - Each supplier's share <= its quantity_to_allocate.
      - MOQ respected: a supplier is skipped if we cannot meet its MOQ.
      - Incompatible and INFEASIBLE/FEASIBILITY_UNKNOWN suppliers are skipped.

    Returns (allocations, allocated_total, unmet_quantity).
    """
    remaining = required_quantity
    allocations: List[Dict] = []

    for cand in ranked_candidates:
        if remaining <= 0:
            break
        if not cand.get("material_compatible", False):
            continue
        feas = cand.get("feasibility_status", INFEASIBLE)
        if feas in (INFEASIBLE, FEASIBILITY_UNKNOWN):
            continue

        qty_avail = _number(cand.get("quantity_to_allocate"))
        if qty_avail is None or qty_avail <= 0:
            continue

        moq = _number(cand.get("moq_units"))
        allocate = min(qty_avail, remaining)

        if moq is not None and allocate < moq:
            continue  # cannot meet MOQ - skip

        remaining -= allocate
        allocations.append({
            "supplier_id": cand["supplier_id"],
            "supplier_name": cand.get("supplier_name", ""),
            "supplier_classification": cand.get("supplier_classification", UNKNOWN),
            "allocated_quantity": _tidy(allocate),
            "unit_cost_inr": cand.get("unit_cost_inr"),
            "lead_time_days": cand.get("lead_time_days"),
            "additional_cost_per_unit_inr": cand.get("additional_cost_per_unit_inr"),
            "transport_status": cand.get("transport_status", TRANSPORT_UNKNOWN),
            "dependency_status": cand.get("dependency_status", DEP_UNKNOWN),
            "reachable_routes": cand.get("reachable_routes", []),
            "shared_upstreams": cand.get("shared_upstreams", []),
            "ranking_score": cand.get("ranking_score", 0.0),
        })

    allocated_total = required_quantity - max(remaining, 0.0)
    unmet = max(remaining, 0.0)
    return allocations, _tidy(allocated_total), _tidy(unmet)


# ---------------------------------------------------------------------------
# Task 9 helpers - cost, delivery, plan assembly
# ---------------------------------------------------------------------------

def _total_cost(allocations: List[Dict]) -> Any:
    """Total procurement cost; UNKNOWN if any allocation lacks unit_cost_inr."""
    total = 0.0
    for alloc in allocations:
        unit_cost = _number(alloc.get("unit_cost_inr"))
        qty = _number(alloc.get("allocated_quantity"))
        if unit_cost is None or qty is None:
            return UNKNOWN
        total += unit_cost * qty
    return _tidy(total)


def _max_lead_time(allocations: List[Dict]) -> Any:
    """Bottleneck delivery time = max(lead_time + min_transit) across allocations.

    FIX (Issue D): adds the minimum transit_days from the supplier's reachable
    routes to the manufacturing lead time, giving a true end-to-end estimate.
    Returns UNKNOWN if any lead_time is missing.
    """
    times = []
    for alloc in allocations:
        t = _number(alloc.get("lead_time_days"))
        if t is None:
            return UNKNOWN
        # Add minimum route transit time if any routes are known.
        routes = alloc.get("reachable_routes", [])
        transits = [
            _number(r.get("transit_days"))
            for r in routes
            if _number(r.get("transit_days")) is not None
        ]
        transit = min(transits) if transits else 0
        times.append(t + transit)
    return _tidy(max(times)) if times else UNKNOWN


def _build_plan(
    objective: str,
    allocations: List[Dict],
    allocated_total: Any,
    unmet_quantity: Any,
    required_quantity: float,
    material_id: str,
    missing_info: List[str],
    warnings: List[str],
    rejected_candidates: List[Dict],
    explanation: str,
) -> Dict:
    """Assemble one recovery plan dict in the standardised Task 11 format."""
    if isinstance(allocated_total, (int, float)) and allocated_total >= required_quantity:
        status = STATUS_FEASIBLE
    elif allocations:
        status = STATUS_PARTIAL
    else:
        status = STATUS_NO_PLAN

    return {
        "material_id": material_id,
        "required_quantity": _tidy(required_quantity),
        "allocated_quantity": (
            _tidy(allocated_total)
            if isinstance(allocated_total, (int, float))
            else 0
        ),
        "unmet_quantity": (
            _tidy(unmet_quantity)
            if isinstance(unmet_quantity, (int, float))
            else _tidy(required_quantity)
        ),
        "status": status,
        "optimization_objective": objective,
        "selected_suppliers": allocations,
        "total_procurement_cost_inr": _total_cost(allocations) if allocations else None,
        "effective_delivery_days": _max_lead_time(allocations) if allocations else UNKNOWN,
        "missing_information": list(missing_info),
        "rejected_candidates": list(rejected_candidates),
        "warnings": list(warnings),
        "selection_explanation": explanation,
    }


def _sort_for_cost(candidates: List[Dict]) -> List[Dict]:
    """Sort by unit_cost_inr ascending; unknown costs last."""
    return sorted(
        candidates,
        key=lambda c: (_number(c.get("unit_cost_inr")) is None,
                       _number(c.get("unit_cost_inr")) or 0.0),
    )


def _sort_for_speed(candidates: List[Dict]) -> List[Dict]:
    """Sort by lead_time_days ascending; unknown times last."""
    return sorted(
        candidates,
        key=lambda c: (_number(c.get("lead_time_days")) is None,
                       _number(c.get("lead_time_days")) or 0.0),
    )


def _sort_balanced(candidates: List[Dict]) -> List[Dict]:
    """Sort by ranking_score descending (already computed)."""
    return sorted(candidates, key=lambda c: c.get("ranking_score", 0.0), reverse=True)


# ---------------------------------------------------------------------------
# Task 10 - Emergency Recovery Mode
# ---------------------------------------------------------------------------

def emergency_recovery(
    all_evaluated_candidates: List[Dict],
    required_quantity: float,
    failed_supplier_ids: List[str],
    material_id: str,
    missing_info: List[str],
    warnings: List[str],
    rejected_candidates: List[Dict],
) -> Dict:
    """
    Emergency Recovery Mode - activated when normal recovery is insufficient.

    Relaxes the shared-upstream exclusion to include DEP_SHARED_UPSTREAM
    candidates. Clearly labels every trade-off.

    Hard constraints NEVER relaxed:
      - Material compatibility
      - MOQ
      - INFEASIBLE / FEASIBILITY_UNKNOWN feasibility
      - DEP_DIRECTLY_AFFECTED (candidate depends on the failed supplier)
    """
    warnings.append(
        "EMERGENCY RECOVERY MODE ACTIVATED: normal recovery could not satisfy "
        + str(_tidy(required_quantity)) + " units of " + material_id
        + ". Evaluating shared-upstream candidates."
    )

    emergency_eligible = [
        c for c in all_evaluated_candidates
        if c.get("material_compatible", False)
        and c.get("feasibility_status") not in (INFEASIBLE, FEASIBILITY_UNKNOWN)
        and c.get("dependency_status") != DEP_DIRECTLY_AFFECTED
    ]

    if not emergency_eligible:
        warnings.append(
            "EMERGENCY RECOVERY: no eligible candidate found for "
            + material_id + ". Plan is NO_FEASIBLE_PLAN."
        )
        plan = _build_plan(
            objective=OBJ_BALANCED,
            allocations=[],
            allocated_total=0,
            unmet_quantity=required_quantity,
            required_quantity=required_quantity,
            material_id=material_id,
            missing_info=missing_info,
            warnings=warnings,
            rejected_candidates=rejected_candidates,
            explanation=(
                "No feasible supplier for " + material_id
                + " exists after excluding failed and directly-affected alternatives."
            ),
        )
        plan["status"] = STATUS_NO_PLAN
        return plan

    sorted_em = _sort_balanced(emergency_eligible)
    allocations, allocated_total, unmet = allocate_quantity(sorted_em, required_quantity)

    for alloc in allocations:
        alloc["emergency_mode"] = True
        if alloc.get("dependency_status") == DEP_SHARED_UPSTREAM:
            warnings.append(
                "EMERGENCY: " + alloc["supplier_id"]
                + " shares upstream dependencies with failed suppliers - elevated risk."
            )

    explanation = (
        "Emergency Recovery: " + str(len(allocations)) + " supplier(s) selected. "
        + "Allocated " + str(allocated_total) + " of "
        + str(_tidy(required_quantity)) + " units. "
        + "Shared-upstream candidates included under emergency rules. "
        + "Unmet: " + str(unmet) + " units."
    )

    plan = _build_plan(
        objective=OBJ_BALANCED,
        allocations=allocations,
        allocated_total=allocated_total,
        unmet_quantity=unmet,
        required_quantity=required_quantity,
        material_id=material_id,
        missing_info=missing_info,
        warnings=warnings,
        rejected_candidates=rejected_candidates,
        explanation=explanation,
    )
    plan["status"] = STATUS_EMERGENCY
    return plan


# ---------------------------------------------------------------------------
# Task 9 / Main engine - optimise_recovery
# ---------------------------------------------------------------------------

def optimise_recovery(
    material_id: str,
    required_quantity: float,
    failed_supplier_ids: List[str],
    destination_ids: Optional[List[str]] = None,
    original_supplier_id: Optional[str] = None,
    data: Optional[Dict] = None,
    graph: Optional[Any] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Main public function: find the best recovery plan for a disrupted material.

    Parameters
    ----------
    material_id : str
        Material that must be re-sourced (must exist in materials.csv).
    required_quantity : float
        Quantity to replace (must be > 0).
    failed_supplier_ids : list[str]
        Supplier IDs that have failed (from Member 2's disruption report).
    destination_ids : list[str], optional
        Factory / warehouse IDs the material must reach. Used for transport
        reachability check. Pass [] or None to check reachability generally.
    original_supplier_id : str, optional
        The primary supplier that failed; used to compute additional cost delta.
    data : dict, optional
        Output of load_all_data(). Loaded internally if None.
    graph : networkx.DiGraph, optional
        Output of get_supply_chain_graph(data). Built internally if None.
    weights : dict, optional
        Scoring weights (keys match DEFAULT_WEIGHTS). Defaults used if None.

    Returns
    -------
    dict  (JSON-serialisable)
        Keys:
          material_id, required_quantity, failed_supplier_ids,
          candidate_evaluation  - list of all evaluated suppliers with scores,
          recommended_plan      - BALANCED objective plan,
          lowest_cost_plan      - LOWEST_COST objective plan,
          fastest_plan          - FASTEST objective plan.
        Each plan follows the Task 11 schema.

    Member 4 integration
    --------------------
    After receiving the plan, Member 4 can:
      1. Inspect recommended_plan["selected_suppliers"].
      2. Simulate additional failures.
      3. Call optimise_recovery() again with updated failed_supplier_ids.
    """
    # --- 0. Setup -----------------------------------------------------------
    if data is None:
        data = load_all_data(verbose=False)
    if graph is None:
        graph = get_supply_chain_graph(data)
    if weights is None:
        weights = DEFAULT_WEIGHTS
    if destination_ids is None:
        destination_ids = []

    missing_info: List[str] = []
    warnings: List[str] = []
    rejected_candidates: List[Dict] = []
    input_errors: List[str] = []

    # --- 1. Validate inputs (Task 14) ---------------------------------------
    lookups = _build_lookups(data)

    mid_clean, mid_err = _validate_material_id(material_id, lookups["material_info"])
    if mid_err:
        return {
            "error": "Invalid input",
            "input_errors": [mid_err],
            "material_id": material_id,
            "required_quantity": required_quantity,
        }

    qty_clean, qty_err = _validate_quantity(required_quantity)
    if qty_err:
        return {
            "error": "Invalid input",
            "input_errors": [qty_err],
            "material_id": mid_clean,
            "required_quantity": required_quantity,
        }

    clean_failed: List[str] = []
    for fsid in (failed_supplier_ids or []):
        sid, err = _validate_supplier_id(fsid, graph)
        if err:
            warnings.append("Failed supplier warning: " + err)
        else:
            clean_failed.append(sid)

    if failed_supplier_ids and not clean_failed:
        warnings.append(
            "None of the provided failed_supplier_ids are valid graph nodes; "
            "proceeding without excluding any supplier."
        )

    # --- 2. Candidate identification ----------------------------------------
    all_for_material = list(lookups["suppliers_of"].get(mid_clean, set()))
    candidate_ids = [s for s in all_for_material if s not in clean_failed]

    if not candidate_ids:
        msg = (
            "No candidate suppliers remain for " + mid_clean
            + " after excluding failed suppliers " + str(clean_failed)
        )
        warnings.append(msg)
        no_plan = _build_plan(
            objective=OBJ_BALANCED,
            allocations=[],
            allocated_total=0,
            unmet_quantity=_tidy(qty_clean),
            required_quantity=qty_clean,
            material_id=mid_clean,
            missing_info=missing_info,
            warnings=warnings,
            rejected_candidates=rejected_candidates,
            explanation=msg,
        )
        return {
            "material_id": mid_clean,
            "required_quantity": _tidy(qty_clean),
            "failed_supplier_ids": clean_failed,
            "original_supplier_id": original_supplier_id,
            "candidate_evaluation": [],
            "recommended_plan": no_plan,
            "lowest_cost_plan": no_plan,
            "fastest_plan": no_plan,
        }

    # --- 3. Evaluate each candidate (Tasks 2-7) -----------------------------
    evaluated: List[Dict] = []

    for sid in candidate_ids:
        sup_row = lookups["supplier_info"].get(sid) or {}
        cand: Dict[str, Any] = {
            "supplier_id": sid,
            "supplier_name": _text(sup_row.get("supplier_name")),
            "tier": _number(sup_row.get("tier")),
            "quality_score": _number(sup_row.get("quality_score")),
        }

        # Task 1
        cand["supplier_classification"] = classify_supplier(sid, mid_clean, lookups)

        # Task 2 - material compatibility (hard gate)
        compatible, compat_reason = check_material_compatibility(sid, mid_clean, lookups)
        cand["material_compatible"] = compatible
        cand["compatibility_reason"] = compat_reason

        if not compatible:
            cand["feasibility_status"] = INFEASIBLE
            cand["rejection_reason"] = compat_reason
            rejected_candidates.append({
                "supplier_id": sid,
                "reason": compat_reason,
                "stage": "material_compatibility",
            })
            evaluated.append(cand)
            continue

        # Task 3 - feasibility
        feas = assess_feasibility(sid, mid_clean, qty_clean, lookups, missing_info)
        cand.update(feas)

        # Task 4 - cost & delivery
        cost_del = assess_cost_and_delivery(
            sid, mid_clean, original_supplier_id, lookups, missing_info
        )
        cand["unit_cost_inr"] = cost_del["unit_cost_inr"]
        cand["lead_time_days"] = cost_del["lead_time_days"]
        cand["additional_cost_per_unit_inr"] = cost_del["additional_cost_per_unit_inr"]
        cand["cost_note"] = cost_del["cost_note"]

        # Task 5 - transport
        transport = assess_transport(sid, destination_ids, lookups, graph, missing_info)
        cand["transport_status"] = transport["transport_status"]
        cand["reachable_routes"] = transport["reachable_routes"]
        cand["primary_route_id"] = transport["primary_route_id"]

        # Task 6 - upstream dependency
        dep = assess_upstream_dependency(sid, clean_failed, graph, missing_info)
        cand["dependency_status"] = dep["dependency_status"]
        cand["shared_upstreams"] = dep["shared_upstreams"]
        cand["dependency_reason"] = dep["reason"]

        evaluated.append(cand)

    # Task 7 - rank all evaluated candidates
    ranked = rank_candidates(list(evaluated), qty_clean, weights)

    # Record feasibility rejections for the output.
    for cand in ranked:
        if (
            cand.get("feasibility_status") == INFEASIBLE
            and cand.get("material_compatible", True)
            and not any(r["supplier_id"] == cand["supplier_id"] for r in rejected_candidates)
        ):
            rejected_candidates.append({
                "supplier_id": cand["supplier_id"],
                "reason": cand.get("reason", "Infeasible"),
                "stage": "feasibility",
            })

    # --- 4. Task 8 / 9 - Three plan variants --------------------------------
    # Normal-mode: exclude DIRECTLY_AFFECTED; include SHARED_UPSTREAM with warning.
    eligible = [
        c for c in ranked
        if c.get("material_compatible", False)
        and c.get("feasibility_status") not in (INFEASIBLE, FEASIBILITY_UNKNOWN)
        and c.get("dependency_status") != DEP_DIRECTLY_AFFECTED
    ]

    def _make_plan(sorted_cands: List[Dict], obj: str) -> Dict:
        allocs, alloc_total, unmet = allocate_quantity(sorted_cands, qty_clean)
        if alloc_total >= qty_clean:
            exp = (
                obj + " plan: " + str(len(allocs)) + " supplier(s), "
                + str(alloc_total) + " units fully allocated."
            )
        elif allocs:
            exp = (
                obj + " PARTIAL plan: " + str(len(allocs)) + " supplier(s), "
                + str(alloc_total) + " of " + str(_tidy(qty_clean))
                + " units. Unmet: " + str(unmet) + " units."
            )
        else:
            exp = obj + " plan: no eligible suppliers for " + mid_clean + "."

        # FIX (Issue C): Surface shared-upstream risk in plan.warnings so that
        # Member 5's dashboard shows it prominently without requiring drill-down
        # into candidate_evaluation.
        plan_warnings = list(warnings)
        for alloc in allocs:
            if alloc.get("dependency_status") == DEP_SHARED_UPSTREAM:
                shared = ", ".join(alloc.get("shared_upstreams", []))
                plan_warnings.append(
                    "RISK: " + alloc["supplier_id"]
                    + " shares upstream supplier(s) with the failed set: "
                    + shared
                    + ". A further failure at those upstream nodes could affect"
                    + " this supplier too."
                )

        return _build_plan(
            objective=obj,
            allocations=allocs,
            allocated_total=alloc_total,
            unmet_quantity=unmet,
            required_quantity=qty_clean,
            material_id=mid_clean,
            missing_info=missing_info,
            warnings=plan_warnings,
            rejected_candidates=list(rejected_candidates),
            explanation=exp,
        )

    if eligible:
        lowest_cost_plan = _make_plan(_sort_for_cost(list(eligible)), OBJ_LOWEST_COST)
        fastest_plan = _make_plan(_sort_for_speed(list(eligible)), OBJ_FASTEST)
        recommended_plan = _make_plan(_sort_balanced(list(eligible)), OBJ_BALANCED)
    else:
        # Task 10 - emergency mode
        em_plan = emergency_recovery(
            all_evaluated_candidates=ranked,
            required_quantity=qty_clean,
            failed_supplier_ids=clean_failed,
            material_id=mid_clean,
            missing_info=missing_info,
            warnings=warnings,
            rejected_candidates=rejected_candidates,
        )
        lowest_cost_plan = em_plan
        fastest_plan = em_plan
        recommended_plan = em_plan

    # Escalate to emergency if the recommended plan is still partial/no-plan
    # and there are additional shared-upstream candidates not yet used.
    if recommended_plan["status"] in (STATUS_PARTIAL, STATUS_NO_PLAN):
        already_selected = {
            a["supplier_id"] for a in recommended_plan.get("selected_suppliers", [])
        }
        extra = [
            c for c in ranked
            if c.get("material_compatible", False)
            and c.get("feasibility_status") not in (INFEASIBLE, FEASIBILITY_UNKNOWN)
            and c.get("dependency_status") == DEP_SHARED_UPSTREAM
            and c["supplier_id"] not in already_selected
        ]
        if extra:
            em_plan2 = emergency_recovery(
                all_evaluated_candidates=ranked,
                required_quantity=qty_clean,
                failed_supplier_ids=clean_failed,
                material_id=mid_clean,
                missing_info=list(missing_info),
                warnings=list(warnings),
                rejected_candidates=list(rejected_candidates),
            )
            if em_plan2["allocated_quantity"] > recommended_plan["allocated_quantity"]:
                recommended_plan = em_plan2

    # --- 5. Build Task 11 candidate summary for Member 4 / Member 5 --------
    candidate_summary = []
    for cand in ranked:
        candidate_summary.append({
            "supplier_id": cand["supplier_id"],
            "supplier_name": cand.get("supplier_name", ""),
            "supplier_classification": cand.get("supplier_classification", UNKNOWN),
            "tier": cand.get("tier"),
            "material_compatible": cand.get("material_compatible", False),
            "feasibility_status": cand.get("feasibility_status", FEASIBILITY_UNKNOWN),
            "quantity_available": cand.get("quantity_available", UNKNOWN),
            "quantity_to_allocate": cand.get("quantity_to_allocate", UNKNOWN),
            "moq_units": cand.get("moq_units"),
            "unit_cost_inr": cand.get("unit_cost_inr", UNKNOWN),
            "lead_time_days": cand.get("lead_time_days", UNKNOWN),
            "additional_cost_per_unit_inr": cand.get("additional_cost_per_unit_inr"),
            "transport_status": cand.get("transport_status", TRANSPORT_UNKNOWN),
            "primary_route_id": cand.get("primary_route_id", UNKNOWN),
            "dependency_status": cand.get("dependency_status", DEP_UNKNOWN),
            "shared_upstreams": cand.get("shared_upstreams", []),
            "quality_score": cand.get("quality_score"),
            "ranking_score": cand.get("ranking_score", 0.0),
            "rejection_reason": cand.get("rejection_reason"),
            "dependency_reason": cand.get("dependency_reason", ""),
            "compatibility_reason": cand.get("compatibility_reason", ""),
        })

    return {
        "material_id": mid_clean,
        "required_quantity": _tidy(qty_clean),
        "failed_supplier_ids": clean_failed,
        "original_supplier_id": original_supplier_id,
        "candidate_evaluation": candidate_summary,
        "recommended_plan": recommended_plan,
        "lowest_cost_plan": lowest_cost_plan,
        "fastest_plan": fastest_plan,
    }


# ---------------------------------------------------------------------------
# Task 13 - Wrapper accepting Member 2 disruption report directly
# ---------------------------------------------------------------------------

def optimise_from_disruption_report(
    disruption_report: Dict,
    material_id: str,
    required_quantity: float,
    destination_ids: Optional[List[str]] = None,
    data: Optional[Dict] = None,
    graph: Optional[Any] = None,
    weights: Optional[Dict[str, float]] = None,
) -> Dict:
    """
    Convenience wrapper that accepts Member 2's disruption report dict and
    extracts failed_supplier_ids and original_supplier_id before calling
    optimise_recovery().

    Accepts output from:
      simulate_supplier_disruption()           (single supplier)
      simulate_multiple_supplier_disruption()  (multiple suppliers)

    Parameters
    ----------
    disruption_report : dict
        The dict returned by a Member 2 simulation function.
    material_id : str
        The material that needs re-sourcing.
    required_quantity : float
        How many units must be replaced.
    destination_ids, data, graph, weights : optional
        Same as optimise_recovery().
    """
    failed_ids: List[str] = []
    original: Optional[str] = None

    scenario = disruption_report.get("scenario", {})

    # Single-disruption report
    single_id = _text(scenario.get("failed_supplier_id"))
    if single_id:
        failed_ids.append(single_id)
        original = single_id

    # Multi-disruption report
    for fsid in (scenario.get("failed_supplier_ids") or []):
        sid = _text(fsid)
        if sid and sid not in failed_ids:
            failed_ids.append(sid)
    if not original and failed_ids:
        original = failed_ids[0]

    return optimise_recovery(
        material_id=material_id,
        required_quantity=required_quantity,
        failed_supplier_ids=failed_ids,
        destination_ids=destination_ids,
        original_supplier_id=original,
        data=data,
        graph=graph,
        weights=weights,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    import os
    import sys

    # When run directly (python src/recovery_optimisation.py), the project
    # root is not on sys.path.  Insert it so that `from src.xxx import ...`
    # at the top of this file works regardless of invocation style.
    _project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _project_root not in sys.path:
        sys.path.insert(0, _project_root)

    _mat = sys.argv[1] if len(sys.argv) > 1 else "MAT-02"
    _qty = float(sys.argv[2]) if len(sys.argv) > 2 else 1000.0
    _failed = sys.argv[3:] if len(sys.argv) > 3 else ["SUP-T1-03"]

    result = optimise_recovery(
        material_id=_mat,
        required_quantity=_qty,
        failed_supplier_ids=_failed,
    )
    print(json.dumps(result, indent=2, default=str))
