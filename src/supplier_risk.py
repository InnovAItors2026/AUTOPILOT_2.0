"""
supplier_risk.py
----------------
Member 2: Supplier Risk Analysis.

STEP 2 (this file so far): build a RAW risk-factor table with one row per
supplier. There are NO risk scores and NO risk categories here. Those are
designed separately in Step 3.

Main function:
    build_supplier_risk_factors(data=None, graph=None)  ->  pandas DataFrame

This file only READS Member 1's data and graph. It never changes them.

=====================================================================
WHAT IS A REAL DATASET VALUE AND WHAT IS AN ASSUMPTION?
=====================================================================
Every column is labelled in COLUMN_SOURCES (below):

  "dataset value"        copied unchanged from a CSV file
  "counted from dataset" counted or added up from CSV/graph data
                         (no judgement involved)
  "rule-based"           depends on a rule/assumption listed here

ASSUMPTIONS (A1 to A7)
----------------------
A1  SINGLE-SOURCE: a material is "single-source" when supplier_materials.csv
    lists exactly ONE supplier for it. Suppliers missing from that file
    are not known to us.

A2  GENUINE INDEPENDENT BACKUP: for a supplier P and one material M that P
    supplies, another supplier A is a genuine backup only if ALL are true:
      (a) A is listed for the same material M in supplier_materials.csv,
      (b) A is independent of P (see A3), and
      (c) A's capacity is "sufficient" (see A4).
    Being a "second supplier" is NOT enough. The dataset's is_backup flag is
    shown for information but does not decide anything.

A3  INDEPENDENCE: A and P are independent when
      - neither is upstream of the other, and
      - they share NO upstream supplier,
    based on supplier_dependencies.csv (through Member 1's graph).
    NOT checked (no data): same city/region, same transport route, same
    owner, shared utilities.

A4  CAPACITY: the data has capacity numbers but NO current load, utilisation
    or demand, so "AVAILABLE capacity" cannot be known. As a stand-in we
    compare monthly_capacity_units (supplier_materials.csv) of A versus P for
    material M. P's capacity is used as the volume that would have to be
    replaced. This is an ASSUMPTION and is optimistic, because A may already
    be busy. Result values:
      "sufficient"    A's capacity >= P's capacity
      "insufficient"  A's capacity < P's capacity, OR A is marked
                      capacity_status = "insufficient" in suppliers.csv
      "unknown"       a needed capacity number is missing (not the same
                      thing as insufficient!)

A5  INVENTORY: stock is recorded per MATERIAL and location, not per
    supplier, so every supplier of a material shares the same stock figures.
    We only compare quantity_on_hand with reorder_point. NO days-of-cover is
    calculated, because the data has no consumption rates.
    "Pooled" means the quantities of ONE material added up over all its
    locations (never adding different materials together).
    If ANY inventory row of a material has a missing quantity_on_hand or
    reorder_point, the pooled status of that material is UNKNOWN: it is not
    counted as BELOW or ABOVE, and the detail text says why. (Counting only
    the rows that have numbers would give a total that is too small.)

A6  SUPPLIERS WITH NO ROW IN supplier_materials.csv (eight Tier 3 suppliers
    today): we do not know which material they supply. Their material-based
    counts are left empty (<NA>) instead of 0, because 0 would wrongly say
    "we checked and found none".

A7  A supplier that is not in the graph gets empty (<NA>) upstream/downstream
    counts rather than a made-up number.
"""

import pandas as pd

from src.data_loader import load_all_data
from src.disruption_impact import find_downstream_suppliers
from src.supply_chain_graph import find_upstream_dependencies, get_supply_chain_graph


# ---------------------------------------------------------------------------
# The columns of the output table, in order, and where each one comes from
# ---------------------------------------------------------------------------

DATASET = "dataset value"
COUNT = "counted from dataset"
RULE = "rule-based (uses assumptions A1-A7)"

COLUMN_SOURCES = {
    "supplier_id": DATASET,
    "supplier_name": DATASET,
    "tier": DATASET,
    "lead_time_days": DATASET,
    "quality_score": DATASET,
    "capacity_status": DATASET,
    "has_material_mapping": COUNT,
    "number_of_upstream_suppliers": COUNT,
    "number_of_downstream_suppliers": COUNT,
    "number_of_materials_supplied": COUNT,
    "materials_supplied": COUNT,
    "number_of_single_source_materials": RULE,
    "single_source_materials": RULE,
    "number_of_genuine_independent_backups": RULE,
    "number_of_materials_without_genuine_backup": RULE,
    "backup_assessment": RULE,
    "inventory_rows_for_supplied_materials": COUNT,
    "inventory_rows_below_reorder_point": COUNT,
    "materials_below_reorder_point_pooled": COUNT,
    "inventory_buffer_detail": COUNT,
}

RISK_FACTOR_COLUMNS = list(COLUMN_SOURCES.keys())

# Columns that hold whole numbers and may be empty (<NA>) when unknown.
_WHOLE_NUMBER_COLUMNS = [
    "number_of_upstream_suppliers",
    "number_of_downstream_suppliers",
    "number_of_materials_supplied",
    "number_of_single_source_materials",
    "number_of_genuine_independent_backups",
    "number_of_materials_without_genuine_backup",
    "inventory_rows_for_supplied_materials",
    "inventory_rows_below_reorder_point",
    "materials_below_reorder_point_pooled",
]

NO_MAPPING_TEXT = "No row in supplier_materials.csv, so the materials supplied are unknown"


# ---------------------------------------------------------------------------
# Small helper functions
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


def _show(number):
    """3000.0 -> '3000' (nicer to read in text)."""
    if number is None:
        return "?"
    if number == int(number):
        return str(int(number))
    return str(number)


# ---------------------------------------------------------------------------
# Backup validation (assumptions A2, A3, A4)
# ---------------------------------------------------------------------------

def assess_capacity(primary_capacity, candidate_capacity, candidate_capacity_status):
    """
    Compare a possible backup's capacity with the primary supplier's (A4).

    Returns (status, note) where status is
    "sufficient", "insufficient" or "unknown".
    """
    primary = _number(primary_capacity)
    candidate = _number(candidate_capacity)
    flagged_insufficient = _text(candidate_capacity_status).lower() == "insufficient"

    # Build a readable note from whatever numbers we have.
    if primary is None or candidate is None or primary <= 0:
        note = "capacity figure missing in supplier_materials.csv"
        ratio = None
    else:
        ratio = candidate / primary
        note = (
            _show(candidate) + " vs " + _show(primary)
            + " units/month (" + format(ratio, ".0%") + " of primary)"
        )

    # The dataset's own "insufficient" flag always wins.
    if flagged_insufficient:
        return "insufficient", note + "; supplier marked 'insufficient' in suppliers.csv"
    if ratio is None:
        return "unknown", note
    if ratio >= 1:
        return "sufficient", note
    return "insufficient", note


def check_backup_candidate(primary_id, candidate_id, material_id,
                           upstream_of, material_rows, supplier_info):
    """
    Decide whether `candidate_id` is a GENUINE independent backup for
    `primary_id` on one material (assumption A2).

    Inputs (all plain dictionaries, so this is easy to test):
      upstream_of    {supplier_id: set of that supplier's upstream supplier ids}
      material_rows  {(supplier_id, material_id): row from supplier_materials.csv}
      supplier_info  {supplier_id: row from suppliers.csv}

    Returns a dictionary with the answer to each check and the reasons.
    """
    candidate_row = material_rows.get((candidate_id, material_id))
    primary_row = material_rows.get((primary_id, material_id))

    # Check (a): does the candidate supply the same material?
    same_material = candidate_row is not None

    # Check (b): is the candidate independent of the primary?
    primary_upstream = upstream_of.get(primary_id)
    candidate_upstream = upstream_of.get(candidate_id)
    independence_problems = []
    if primary_upstream is None or candidate_upstream is None:
        independent = None  # unknown: one of them is not in the graph
        independence_problems.append("independence unknown (supplier not in graph)")
    else:
        if candidate_id in primary_upstream:
            independence_problems.append(candidate_id + " is upstream of " + primary_id)
        if primary_id in candidate_upstream:
            independence_problems.append(candidate_id + " depends on " + primary_id)
        shared = sorted(primary_upstream & candidate_upstream)
        if shared:
            independence_problems.append("shares upstream supplier(s) " + ", ".join(shared))
        independent = len(independence_problems) == 0

    # Check (c): does the candidate have enough capacity?
    if not same_material:
        capacity_status, capacity_note = "unknown", "candidate has no row for this material"
    else:
        capacity_status, capacity_note = assess_capacity(
            primary_row.get("monthly_capacity_units") if primary_row else None,
            candidate_row.get("monthly_capacity_units"),
            (supplier_info.get(candidate_id) or {}).get("capacity_status"),
        )

    flagged_backup = bool(candidate_row) and _number(candidate_row.get("is_backup")) == 1

    return {
        "material_id": material_id,
        "candidate_id": candidate_id,
        "same_material": same_material,
        "independent": independent,
        "independence_problems": independence_problems,
        "capacity_status": capacity_status,
        "capacity_note": capacity_note,
        "flagged_backup_in_dataset": flagged_backup,
        "is_genuine": bool(same_material and independent is True and capacity_status == "sufficient"),
    }


def _describe_backup_check(result):
    """One readable line for the backup_assessment column."""
    start = result["material_id"] + ": " + result["candidate_id"] + " -> "
    flag = " [dataset flags it as a backup]" if result["flagged_backup_in_dataset"] else ""

    if result["is_genuine"]:
        return start + "GENUINE (independent; capacity sufficient: " + result["capacity_note"] + ")" + flag

    problems = []
    if not result["same_material"]:
        problems.append("does not supply this material")
    problems.extend(result["independence_problems"])
    if result["capacity_status"] == "insufficient":
        problems.append("capacity insufficient: " + result["capacity_note"])
    elif result["capacity_status"] == "unknown":
        problems.append("capacity unknown: " + result["capacity_note"])
    return start + "NOT genuine (" + "; ".join(problems) + ")" + flag


# ---------------------------------------------------------------------------
# Inventory (assumption A5)
# ---------------------------------------------------------------------------

def _summarise_inventory(inventory_table):
    """
    Add up inventory.csv per material.

    Returns {material_id: {"rows", "below_rows", "on_hand", "reorder", "missing_rows"}}.
    "below_rows" = locations where quantity_on_hand < reorder_point.
    """
    summary = {}
    for row in _rows(inventory_table):
        material_id = _text(row.get("material_id"))
        if not material_id:
            continue
        entry = summary.setdefault(
            material_id,
            {"rows": 0, "below_rows": 0, "on_hand": 0.0, "reorder": 0.0, "missing_rows": 0},
        )
        entry["rows"] += 1

        on_hand = _number(row.get("quantity_on_hand"))
        reorder = _number(row.get("reorder_point"))
        if on_hand is None or reorder is None:
            entry["missing_rows"] += 1  # cannot compare this row
            continue

        entry["on_hand"] += on_hand
        entry["reorder"] += reorder
        if on_hand < reorder:
            entry["below_rows"] += 1
    return summary


def _pooled_below_reorder(entry):
    """
    Is the POOLED stock of one material below its pooled reorder point?

    Returns
      True   pooled quantity_on_hand < pooled reorder_point
      False  pooled quantity_on_hand >= pooled reorder_point
      None   UNKNOWN

    UNKNOWN (None) is returned when there is nothing to compare, OR when ANY
    row of this material has a missing quantity_on_hand or reorder_point.
    Adding up only the rows that happen to have numbers would give a total
    that is too small, and could wrongly say BELOW or ABOVE. So we never
    classify partly-available data.
    """
    if entry is None or entry["rows"] == 0:
        return None
    if entry["missing_rows"] > 0:
        return None
    return entry["on_hand"] < entry["reorder"]


def _describe_inventory(material_id, entry):
    """One readable sentence about one material's stock."""
    if entry is None:
        return material_id + ": no rows in inventory.csv"

    text = material_id + ": " + str(entry["rows"]) + " location(s)"
    compared = entry["rows"] - entry["missing_rows"]

    # Some values are missing -> the pooled status cannot be determined.
    # We do NOT print partial totals, because they would look like real
    # pooled numbers. Per-location facts that ARE known are still shown.
    if _pooled_below_reorder(entry) is None:
        text += (
            ", pooled status UNKNOWN: " + str(entry["missing_rows"]) + " of "
            + str(entry["rows"]) + " location(s) have a missing quantity_on_hand or"
            " reorder_point, so pooled stock cannot be determined"
        )
        if compared > 0:
            text += (
                "; of the " + str(compared) + " location(s) with complete values, "
                + str(entry["below_rows"]) + " are below reorder point"
            )
        return text

    # All values present: same wording as before.
    text += (
        ", on hand " + _show(entry["on_hand"]) + " vs reorder point " + _show(entry["reorder"])
        + " (" + str(entry["below_rows"]) + " of " + str(compared) + " location(s) below reorder point)"
    )
    if _pooled_below_reorder(entry):
        text += ", pooled stock BELOW reorder point"
    else:
        text += ", pooled stock at/above reorder point"
    return text


# ---------------------------------------------------------------------------
# The main function
# ---------------------------------------------------------------------------

def build_supplier_risk_factors(data=None, graph=None):
    """
    Build the raw supplier risk-factor table (one row per supplier).

    data   dict from load_all_data(); loaded here if not given
    graph  digital twin from get_supply_chain_graph(); built here if not given

    Returns a pandas DataFrame with the columns in RISK_FACTOR_COLUMNS.
    No scores, no categories. See COLUMN_SOURCES for what each column is.
    """
    # 1. Use Member 1's functions to get the data and the graph if needed.
    if data is None:
        data = load_all_data(verbose=False)
    if graph is None:
        graph = get_supply_chain_graph(data)

    supplier_rows = _rows(data.get("suppliers"))
    if not supplier_rows:
        return pd.DataFrame(columns=RISK_FACTOR_COLUMNS)

    # 2. Prepare quick lookups (built once, used for every supplier).
    supplier_info = {_text(row.get("supplier_id")): row for row in supplier_rows}

    material_rows = {}          # (supplier_id, material_id) -> row
    suppliers_of = {}           # material_id -> set of supplier ids listed for it
    materials_of = {}           # supplier_id -> sorted list of material ids
    for row in _rows(data.get("supplier_materials")):
        supplier_id = _text(row.get("supplier_id"))
        material_id = _text(row.get("material_id"))
        if not supplier_id or not material_id:
            continue
        material_rows[(supplier_id, material_id)] = row
        suppliers_of.setdefault(material_id, set()).add(supplier_id)
        materials_of.setdefault(supplier_id, set()).add(material_id)
    materials_of = {sid: sorted(mats) for sid, mats in materials_of.items()}

    inventory_by_material = _summarise_inventory(data.get("inventory"))

    # Member 1's upstream lookup, once per supplier that exists in the graph.
    upstream_of = {}
    for supplier_id in supplier_info:
        if supplier_id in graph:
            upstream_of[supplier_id] = set(find_upstream_dependencies(graph, supplier_id))

    # 3. Build one record per supplier.
    records = []
    for supplier_id, row in supplier_info.items():
        # --- values straight from suppliers.csv ---
        record = {
            "supplier_id": supplier_id,
            "supplier_name": _text(row.get("supplier_name")),
            "tier": row.get("tier"),
            "lead_time_days": row.get("lead_time_days"),
            "quality_score": row.get("quality_score"),
            "capacity_status": _text(row.get("capacity_status")) or None,
        }

        # --- position in the supplier network (Member 1's graph) ---
        if supplier_id in graph:
            record["number_of_upstream_suppliers"] = len(upstream_of[supplier_id])
            record["number_of_downstream_suppliers"] = len(find_downstream_suppliers(graph, supplier_id))
        else:
            record["number_of_upstream_suppliers"] = None
            record["number_of_downstream_suppliers"] = None

        # --- materials, single sourcing and backups ---
        materials = materials_of.get(supplier_id, [])
        record["has_material_mapping"] = len(materials) > 0
        record["number_of_materials_supplied"] = len(materials)
        record["materials_supplied"] = "; ".join(materials)

        if not materials:
            # Unknown, not zero (assumption A6).
            record["number_of_single_source_materials"] = None
            record["single_source_materials"] = ""
            record["number_of_genuine_independent_backups"] = None
            record["number_of_materials_without_genuine_backup"] = None
            record["backup_assessment"] = NO_MAPPING_TEXT
            record["inventory_rows_for_supplied_materials"] = None
            record["inventory_rows_below_reorder_point"] = None
            record["materials_below_reorder_point_pooled"] = None
            record["inventory_buffer_detail"] = NO_MAPPING_TEXT
            records.append(record)
            continue

        single_source = [m for m in materials if len(suppliers_of[m]) == 1]
        record["number_of_single_source_materials"] = len(single_source)
        record["single_source_materials"] = "; ".join(single_source)

        genuine_total = 0
        materials_without_backup = 0
        backup_lines = []
        for material_id in materials:
            candidates = sorted(s for s in suppliers_of[material_id] if s != supplier_id)
            if not candidates:
                backup_lines.append(material_id + ": single source, no other supplier listed")
                materials_without_backup += 1
                continue

            genuine_for_material = 0
            for candidate_id in candidates:
                result = check_backup_candidate(
                    supplier_id, candidate_id, material_id,
                    upstream_of, material_rows, supplier_info,
                )
                backup_lines.append(_describe_backup_check(result))
                if result["is_genuine"]:
                    genuine_for_material += 1
            genuine_total += genuine_for_material
            if genuine_for_material == 0:
                materials_without_backup += 1

        record["number_of_genuine_independent_backups"] = genuine_total
        record["number_of_materials_without_genuine_backup"] = materials_without_backup
        record["backup_assessment"] = " | ".join(backup_lines)

        # --- inventory buffer for the materials this supplier provides ---
        entries = [inventory_by_material.get(m) for m in materials]
        record["inventory_rows_for_supplied_materials"] = sum(e["rows"] for e in entries if e)
        record["inventory_rows_below_reorder_point"] = sum(e["below_rows"] for e in entries if e)
        record["materials_below_reorder_point_pooled"] = sum(
            1 for e in entries if _pooled_below_reorder(e) is True
        )
        record["inventory_buffer_detail"] = " | ".join(
            _describe_inventory(m, inventory_by_material.get(m)) for m in materials
        )

        records.append(record)

    # 4. Make the DataFrame and tidy the column types.
    table = pd.DataFrame(records, columns=RISK_FACTOR_COLUMNS)
    for column in ("tier", "lead_time_days", "quality_score"):
        table[column] = pd.to_numeric(table[column], errors="coerce")
    for column in _WHOLE_NUMBER_COLUMNS:
        table[column] = pd.array(table[column].tolist(), dtype="Int64")
    return table
