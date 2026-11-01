"""
risk_scoring.py
---------------
Member 2: explainable supplier RISK SCORING (Step 3).

Input : the DataFrame returned by supplier_risk.build_supplier_risk_factors()
Output: one row per supplier with six factor scores, an overall 0-100 risk
        score, a risk category, a data-confidence figure, reasons, an
        escalation decision and recommended actions.

Main function:
    calculate_supplier_risk_scores(risk_factors, ...)  ->  pandas DataFrame

This file never changes the input table, Member 1's files or any CSV.
Higher score = higher risk.  RISK SCORE and DATA CONFIDENCE ARE DIFFERENT:
the score says "how risky does the known evidence look", the confidence says
"how much of the evidence do we actually have".

=====================================================================
THE SIX FACTORS (weights are configurable, see FACTOR_WEIGHTS)
=====================================================================
  1 material_dependency   30   share of supplied materials with NO genuine
                               independent backup (each material is 0 or 100,
                               supplier score = mean of assessed materials)
  2 inventory             20   share of supplied materials whose POOLED stock
                               is below the reorder point (BELOW = 100,
                               at/above = 0, pooled status UNKNOWN = skipped)
  3 lead_time             15   min-max of lead_time_days (higher = riskier)
  4 quality               15   min-max of quality_score  (LOWER = riskier)
  5 capacity              15   "sufficient" = 0, "insufficient" = 100
  6 upstream_dependency    5   min-max of number_of_upstream_suppliers

UNKNOWN is never turned into zero.  An unknown factor is left out of the
weighted average, and it lowers the DATA CONFIDENCE:
    overall risk    = sum(score x weight over KNOWN factors) / sum(known weights)
    data confidence = sum(known weights) / sum(all weights) x 100
If no factor is known, the score and the category are "Unknown".

=====================================================================
ASSUMPTIONS AND LIMITATIONS  (please read)
=====================================================================
R1  Min-max scores (lead time, quality, upstream count) are RELATIVE to the
    suppliers in the table you pass in. They are not industry standards. The
    best supplier in the table gets 0 and the worst gets 100 even if all of
    them are objectively fine (or all objectively poor).
R2  EQUAL MIN AND MAX: if every known value is the same there is nothing to
    compare, and dividing by (max - min) would divide by zero. The fallback
    is EQUAL_RANGE_SCORE = 0.0 ("no relative difference"). The same fallback
    applies when only ONE supplier has a value. Change it with the
    equal_range_score argument.
R3  BACKUP: "no genuine independent backup" comes from supplier_risk.py. A
    candidate whose capacity is UNKNOWN is NOT counted as genuine there, so a
    material can score 100 because the capacity data is missing, not because
    capacity is known to be too small. The reasons text shows the evidence.
R4  INVENTORY: comparison of quantity_on_hand with reorder_point is an
    initial proxy. Days of supply cannot be calculated (no consumption data).
    Stock is recorded per material, so every supplier of a material shares
    the same stock figures.
    Supplier level: mean over the materials whose pooled status is known.
    Materials with UNKNOWN pooled status are skipped (and listed in
    data_notes). If NO material is known, the factor is Unknown.
R5  The input table has no per-material inventory/backup columns, only
    counts and readable text. This module reads the per-material status from
    that text and CROSS-CHECKS it against the numeric count columns. If they
    disagree, or the text is not understood, the factor becomes Unknown and
    a data note says so. (Tests tie the parser to supplier_risk.py's wording.)
R6  CAPACITY: only the exact labels "sufficient" and "insufficient" (any
    capital letters) are scored. Any other label, or a missing value, is
    Unknown.
R7  UPSTREAM count is a provisional network-EXPOSURE proxy. It is not a
    measure of disruption probability.
R8  CATEGORIES (provisional): 0-24.99 Low, 25-49.99 Medium, 50-74.99 High,
    75-100 Critical. The score is rounded to 2 decimals first, so the shown
    score and the category can never disagree (24.996 shows as 25.0 and is
    Medium).
R9  ESCALATION is a separate layer. The weighted score is never changed. One
    rule exists (E1, below). It only RAISES a category to Critical and never
    lowers one. A supplier without a backup is NOT automatically Critical.
R10 With these weights and only three data-driven min-max factors, the model
    is a transparent first version. It is not calibrated against real
    disruption outcomes.
"""

import math

import pandas as pd


# ---------------------------------------------------------------------------
# Settings you can change
# ---------------------------------------------------------------------------

# Percent weights, in the order the factors appear in the output table.
FACTOR_WEIGHTS = {
    "material_dependency": 30.0,
    "inventory": 20.0,
    "lead_time": 15.0,
    "quality": 15.0,
    "capacity": 15.0,
    "upstream_dependency": 5.0,
}

FACTOR_LABELS = {
    "material_dependency": "material dependency and backup availability",
    "inventory": "inventory shortage",
    "lead_time": "lead time",
    "quality": "quality",
    "capacity": "supplier capacity",
    "upstream_dependency": "upstream dependency",
}

# Lowest score that belongs to each category (Low starts at 0).
CATEGORY_THRESHOLDS = {"Medium": 25.0, "High": 50.0, "Critical": 75.0}

CATEGORY_ORDER = ["Low", "Medium", "High", "Critical"]
UNKNOWN = "Unknown"

# Value used by the min-max factors when max == min (assumption R2).
EQUAL_RANGE_SCORE = 0.0

# A min-max factor is mentioned as a "reason" when its score is at least this.
REASON_MIN_SCORE = 50.0

ESCALATION_RULE_ID = "E1"
ESCALATION_RULE_TEXT = (
    "a supplied material has NO genuine independent backup AND its pooled "
    "inventory is BELOW the reorder point AND the supplier's capacity is "
    "'insufficient'"
)

# Columns the input table must have.
REQUIRED_INPUT_COLUMNS = [
    "supplier_id", "supplier_name", "lead_time_days", "quality_score",
    "capacity_status", "has_material_mapping", "number_of_upstream_suppliers",
    "number_of_materials_supplied", "materials_supplied",
    "number_of_materials_without_genuine_backup", "backup_assessment",
    "materials_below_reorder_point_pooled", "inventory_buffer_detail",
]

SCORE_COLUMNS = [name + "_risk" for name in FACTOR_WEIGHTS]
WEIGHT_COLUMNS = [name + "_weight" for name in FACTOR_WEIGHTS]

OUTPUT_COLUMNS = (
    ["supplier_id", "supplier_name"]
    + SCORE_COLUMNS
    + WEIGHT_COLUMNS
    + [
        "overall_risk_score",
        "original_risk_category",
        "final_risk_category",
        "data_confidence_pct",
        "known_factor_count",
        "unknown_factor_count",
        "known_factors",
        "unknown_factors",
        "risk_reasons",
        "escalation_occurred",
        "escalation_reasons",
        "recommended_actions",
        "data_notes",
    ]
)

# Wording that supplier_risk.py writes into its text columns (assumption R5).
_INVENTORY_BELOW_TEXT = "pooled stock BELOW reorder point"
_INVENTORY_ABOVE_TEXT = "pooled stock at/above reorder point"
_GENUINE_BACKUP_TEXT = " -> GENUINE ("
_TEXT_SEPARATOR = " | "      # between materials / lines in the text columns
_LIST_SEPARATOR = "; "       # between ids in list-like columns

BELOW, ABOVE, INVENTORY_UNKNOWN = "BELOW", "ABOVE", "UNKNOWN"


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _clean_number(value):
    """Cell -> float, or None if missing / not a finite number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _text(value):
    """Cell -> stripped text; missing values become ''."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _truthy(value):
    """True only for a real True value (missing -> False)."""
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(value)


def _split_list(text):
    """'MAT-01; MAT-02' -> ['MAT-01', 'MAT-02'] ('' -> [])."""
    return [part.strip() for part in _text(text).split(";") if part.strip()]


def _fmt(number):
    """3000.0 -> '3000', 0.8125 -> '0.8125'."""
    if number is None:
        return "?"
    if number == int(number):
        return str(int(number))
    return format(number, ".4g")


def _round_or_nan(number):
    """Round a score to 2 decimals; None -> NaN (so the column stays numeric)."""
    return float("nan") if number is None else round(number, 2)


def _column_range(series):
    """(min, max) of the usable numbers in a column, or (None, None)."""
    numbers = pd.to_numeric(series, errors="coerce").dropna()
    if len(numbers) == 0:
        return None, None
    return float(numbers.min()), float(numbers.max())


def check_weights(weights):
    """Return a clean copy of the weights, or raise ValueError if unusable."""
    if set(weights) != set(FACTOR_WEIGHTS):
        raise ValueError("weights must have exactly these keys: " + ", ".join(FACTOR_WEIGHTS))
    clean = {}
    for name in FACTOR_WEIGHTS:
        value = _clean_number(weights[name])
        if value is None or value < 0:
            raise ValueError("weight for " + name + " must be a number >= 0")
        clean[name] = value
    if sum(clean.values()) <= 0:
        raise ValueError("the weights must add up to more than 0")
    return clean


def check_thresholds(thresholds):
    """Return a clean copy of the category thresholds, or raise ValueError."""
    if set(thresholds) != set(CATEGORY_THRESHOLDS):
        raise ValueError("thresholds must have exactly these keys: " + ", ".join(CATEGORY_THRESHOLDS))
    clean = {name: _clean_number(thresholds[name]) for name in CATEGORY_THRESHOLDS}
    values = [clean["Medium"], clean["High"], clean["Critical"]]
    if None in values or not (0 <= values[0] < values[1] < values[2] <= 100):
        raise ValueError("thresholds must satisfy 0 <= Medium < High < Critical <= 100")
    return clean


# ---------------------------------------------------------------------------
# The six factor calculations
# Each returns a score from 0 to 100, or None when the factor is UNKNOWN.
# ---------------------------------------------------------------------------

def calculate_material_dependency_risk(number_of_materials, number_without_genuine_backup):
    """
    FACTOR 1 (30%): material dependency and backup availability.

    Each supplied material scores 100 if it has NO genuine independent backup
    and 0 if it has one. The supplier score is the MEAN of those material
    scores, which equals 100 x (materials without backup) / (materials).

    Returns None (Unknown) when the supplier has no material mapping
    (0 / missing materials) or the backup count is missing or impossible.
    """
    total = _clean_number(number_of_materials)
    without = _clean_number(number_without_genuine_backup)
    if total is None or without is None or total <= 0:
        return None
    if without < 0 or without > total:
        return None
    return 100.0 * without / total


def calculate_inventory_risk(material_statuses):
    """
    FACTOR 2 (20%): inventory shortage risk (pooled stock vs reorder point).

    material_statuses: one text per supplied material, each one of
      "BELOW"    pooled quantity_on_hand < pooled reorder_point  -> 100
      "ABOVE"    pooled quantity_on_hand >= pooled reorder_point -> 0
      anything else (e.g. "UNKNOWN", from missing values)        -> skipped

    The supplier score is the mean over the assessed materials. Missing
    inventory is never treated as zero risk. Returns None (Unknown) if no
    material could be assessed.
    """
    scores = []
    for status in material_statuses or []:
        if status == BELOW:
            scores.append(100.0)
        elif status == ABOVE:
            scores.append(0.0)
    if not scores:
        return None
    return sum(scores) / len(scores)


def _min_max_risk(value, minimum, maximum, higher_is_riskier, equal_range_score):
    """Shared min-max rule used by factors 3, 4 and 6."""
    number = _clean_number(value)
    low = _clean_number(minimum)
    high = _clean_number(maximum)
    if number is None or low is None or high is None:
        return None
    if high < low:
        raise ValueError("maximum must not be smaller than minimum")
    if high == low:
        return float(equal_range_score)          # avoids division by zero (R2)
    if higher_is_riskier:
        score = (number - low) / (high - low) * 100.0
    else:
        score = (high - number) / (high - low) * 100.0
    return min(100.0, max(0.0, score))           # keep inside 0-100


def calculate_lead_time_risk(lead_time_days, min_lead_time, max_lead_time,
                             equal_range_score=EQUAL_RANGE_SCORE):
    """
    FACTOR 3 (15%): ((lead time - min) / (max - min)) x 100.
    Longer lead time = higher risk. None (Unknown) if the value is missing.
    """
    return _min_max_risk(lead_time_days, min_lead_time, max_lead_time, True, equal_range_score)


def calculate_quality_risk(quality_score, min_quality, max_quality,
                           equal_range_score=EQUAL_RANGE_SCORE):
    """
    FACTOR 4 (15%): ((max quality - quality) / (max - min)) x 100.
    Higher quality = LOWER risk. None (Unknown) if the value is missing.
    """
    return _min_max_risk(quality_score, min_quality, max_quality, False, equal_range_score)


def calculate_capacity_risk(capacity_status):
    """
    FACTOR 5 (15%): "sufficient" -> 0, "insufficient" -> 100.
    Any other label or a missing value -> None (Unknown), assumption R6.
    """
    label = _text(capacity_status).lower()
    if label == "sufficient":
        return 0.0
    if label == "insufficient":
        return 100.0
    return None


def calculate_upstream_dependency_risk(upstream_count, min_upstream, max_upstream,
                                       equal_range_score=EQUAL_RANGE_SCORE):
    """
    FACTOR 6 (5%): ((upstream count - min) / (max - min)) x 100.
    A provisional network-EXPOSURE proxy (R7), not a probability of disruption.
    None (Unknown) if the count is missing.
    """
    return _min_max_risk(upstream_count, min_upstream, max_upstream, True, equal_range_score)


# ---------------------------------------------------------------------------
# Combining factors: overall score, data confidence, category
# ---------------------------------------------------------------------------

def combine_factor_scores(factor_scores, weights=None):
    """
    Weighted average of the KNOWN factors only.

    factor_scores: {factor name: score or None}
    Returns a dictionary:
      overall_risk_score   float, or None if no factor is known (or the known
                           factors all have weight 0)
      data_confidence_pct  sum(known weights) / sum(all weights) x 100
      known_factors        list of names
      unknown_factors      list of names
    """
    weights = check_weights(weights or FACTOR_WEIGHTS)
    known = [name for name in FACTOR_WEIGHTS if _clean_number(factor_scores.get(name)) is not None]
    unknown = [name for name in FACTOR_WEIGHTS if name not in known]

    known_weight = sum(weights[name] for name in known)
    total_weight = sum(weights.values())

    overall = None
    if known_weight > 0:
        overall = sum(factor_scores[name] * weights[name] for name in known) / known_weight

    return {
        "overall_risk_score": overall,
        "data_confidence_pct": known_weight / total_weight * 100.0,
        "known_factors": known,
        "unknown_factors": unknown,
    }


def classify_risk(score, thresholds=None):
    """
    Score -> "Low" / "Medium" / "High" / "Critical", or "Unknown".

    The score is rounded to 2 decimals first (assumption R8). A missing score
    gives "Unknown", never a made-up category.
    """
    thresholds = check_thresholds(thresholds or CATEGORY_THRESHOLDS)
    number = _clean_number(score)
    if number is None:
        return UNKNOWN
    number = round(number, 2)
    if number >= thresholds["Critical"]:
        return "Critical"
    if number >= thresholds["High"]:
        return "High"
    if number >= thresholds["Medium"]:
        return "Medium"
    return "Low"


def _category_rank(category):
    """Low=0 ... Critical=3, Unknown=-1 (used to compare categories)."""
    return CATEGORY_ORDER.index(category) if category in CATEGORY_ORDER else -1


# ---------------------------------------------------------------------------
# Reading per-material facts out of supplier_risk.py's text columns (R5)
# ---------------------------------------------------------------------------

def parse_inventory_statuses(inventory_buffer_detail):
    """
    'MAT-01: ... pooled stock BELOW reorder point | MAT-02: ...' ->
    {'MAT-01': 'BELOW', 'MAT-02': 'UNKNOWN', ...}.

    Anything that is not clearly BELOW or at/above is reported as UNKNOWN
    (including "no rows in inventory.csv" and "pooled status UNKNOWN").
    """
    statuses = {}
    for part in _text(inventory_buffer_detail).split(_TEXT_SEPARATOR):
        material, colon, _rest = part.partition(":")
        material = material.strip()
        if not colon or not material:
            continue
        if _INVENTORY_BELOW_TEXT in part:
            statuses[material] = BELOW
        elif _INVENTORY_ABOVE_TEXT in part:
            statuses[material] = ABOVE
        else:
            statuses[material] = INVENTORY_UNKNOWN
    return statuses


def parse_backup_statuses(backup_assessment, materials):
    """
    {material: True if at least one GENUINE backup line exists, else False}.
    Every material in `materials` gets an answer.
    """
    has_backup = {material: False for material in materials}
    for line in _text(backup_assessment).split(_TEXT_SEPARATOR):
        material, colon, _rest = line.partition(":")
        material = material.strip()
        if colon and material in has_backup and _GENUINE_BACKUP_TEXT in line:
            has_backup[material] = True
    return has_backup


# ---------------------------------------------------------------------------
# Escalation layer (assumption R9)
# ---------------------------------------------------------------------------

def evaluate_escalation(original_category, capacity_status,
                        materials_without_backup, materials_below_reorder):
    """
    Rule E1: escalate to Critical when, for the SAME material,
      - there is no genuine independent backup, AND
      - the pooled inventory is below the reorder point,
    AND the supplier's capacity_status is "insufficient".

    materials_without_backup / materials_below_reorder are lists of material
    ids, or None when that information could not be established (then the
    rule cannot fire, because we never escalate on guesses).

    The weighted score is NOT changed here, only the category can be raised.
    Returns {"escalated", "final_category", "reasons" (list of text)}.
    """
    result = {"escalated": False, "final_category": original_category, "reasons": []}

    if _category_rank(original_category) >= _category_rank("Critical"):
        return result                      # already Critical, nothing to raise
    if _text(capacity_status).lower() != "insufficient":
        return result
    if materials_without_backup is None or materials_below_reorder is None:
        return result

    both = sorted(set(materials_without_backup) & set(materials_below_reorder))
    if not both:
        return result

    result["escalated"] = True
    result["final_category"] = "Critical"
    result["reasons"].append(
        "Rule " + ESCALATION_RULE_ID + " (" + ESCALATION_RULE_TEXT + ") applies to "
        + ", ".join(both) + "; raised from " + original_category + " to Critical "
        "(the weighted score is unchanged)"
    )
    return result


# ---------------------------------------------------------------------------
# Reasons and recommendations (only from evidence in the table)
# ---------------------------------------------------------------------------

def _build_reasons(ctx, reason_min_score):
    """Plain-language reasons for the factors that actually add risk."""
    reasons = []
    scores = ctx["scores"]
    ranges = ctx["ranges"]

    if scores["material_dependency"]:                       # > 0
        names = ctx["without_backup"]
        reasons.append(
            "Material dependency: " + _fmt(ctx["n_without_backup"]) + " of " + _fmt(ctx["n_materials"])
            + " supplied material(s) have no genuine independent backup"
            + (" (" + ", ".join(names) + ")" if names else "")
        )
    if scores["inventory"]:                                 # > 0
        names = ctx["below_reorder"]
        reasons.append(
            "Inventory: pooled stock is below the reorder point for "
            + (", ".join(names) if names else "at least one supplied material")
        )
    if scores["lead_time"] is not None and scores["lead_time"] >= reason_min_score:
        reasons.append(
            "Lead time of " + _fmt(ctx["lead_time"]) + " days is long compared with the other suppliers ("
            "dataset range " + _fmt(ranges["lead_time"][0]) + " to " + _fmt(ranges["lead_time"][1]) + " days)"
        )
    if scores["quality"] is not None and scores["quality"] >= reason_min_score:
        reasons.append(
            "Quality score of " + _fmt(ctx["quality"]) + " is low compared with the other suppliers ("
            "dataset range " + _fmt(ranges["quality"][0]) + " to " + _fmt(ranges["quality"][1]) + ")"
        )
    if scores["capacity"]:                                  # > 0
        reasons.append("Capacity: capacity_status is 'insufficient'")
    if scores["upstream_dependency"] is not None and scores["upstream_dependency"] >= reason_min_score:
        reasons.append(
            "Upstream dependency: " + _fmt(ctx["upstream"]) + " upstream supplier(s) compared with a dataset range of "
            + _fmt(ranges["upstream"][0]) + " to " + _fmt(ranges["upstream"][1])
            + " (provisional exposure proxy, not a probability of disruption)"
        )

    if not reasons:
        if ctx["known_count"] == 0:
            reasons.append("Risk cannot be assessed: no factor has usable data")
        else:
            reasons.append(
                "No single factor stands out (no backup, inventory or capacity problem found, and no "
                "min-max factor at or above " + _fmt(reason_min_score) + "); any score comes from "
                "moderate values across the known factors"
            )
    return reasons


def _build_recommendations(ctx, reason_min_score):
    """Actions that each point back to evidence found in this supplier's data."""
    actions = []
    scores = ctx["scores"]
    ranges = ctx["ranges"]

    if scores["material_dependency"]:
        names = ctx["without_backup"]
        actions.append(
            "Identify and qualify an independent alternative supplier"
            + (" for " + ", ".join(names) if names else "")
        )
    if scores["inventory"]:
        names = ctx["below_reorder"]
        actions.append(
            "Prioritise replenishment of "
            + (", ".join(names) if names else "the materials below their reorder point")
        )
    if scores["capacity"]:
        actions.append("Review this supplier's capacity or allocate production elsewhere")
    if scores["lead_time"] is not None and scores["lead_time"] >= reason_min_score:
        actions.append(
            "Investigate faster delivery options or additional safety stock (lead time "
            + _fmt(ctx["lead_time"]) + " days; dataset maximum " + _fmt(ranges["lead_time"][1]) + ")"
        )
    if scores["quality"] is not None and scores["quality"] >= reason_min_score:
        actions.append(
            "Review supplier quality performance (quality score " + _fmt(ctx["quality"])
            + "; dataset maximum " + _fmt(ranges["quality"][1]) + ")"
        )
    if scores["upstream_dependency"] is not None and scores["upstream_dependency"] >= reason_min_score:
        actions.append(
            "Review this supplier's upstream dependencies (" + _fmt(ctx["upstream"]) + " upstream suppliers)"
        )

    # Data gaps: unknown is not safe, so say what is missing.
    if not ctx["mapped"]:
        actions.append(
            "Obtain this supplier's material mapping so that backup and inventory risk can be assessed"
        )
    gaps = [FACTOR_LABELS[name] for name in ctx["unknown_factors"]
            if not (not ctx["mapped"] and name in ("material_dependency", "inventory"))]
    if gaps:
        actions.append("Obtain the missing data for: " + ", ".join(gaps))

    if not actions:
        actions.append("No specific action indicated by the current data")
    return actions


# ---------------------------------------------------------------------------
# Scoring one supplier
# ---------------------------------------------------------------------------

def _score_one_supplier(row, ranges, weights, thresholds, equal_range_score,
                        reason_min_score, enable_escalation):
    """Everything for one supplier (row = dictionary of the input columns)."""
    notes = []

    # --- material facts -----------------------------------------------------
    materials = _split_list(row.get("materials_supplied"))
    n_materials = _clean_number(row.get("number_of_materials_supplied"))
    n_without = _clean_number(row.get("number_of_materials_without_genuine_backup"))
    mapped = _truthy(row.get("has_material_mapping")) and bool(materials)

    without_backup = None      # names of materials with no genuine backup
    below_reorder = None       # names of materials whose pooled stock is BELOW
    inventory_statuses = []

    if mapped:
        # Backup names: cross-check the text against the numeric count (R5).
        has_backup = parse_backup_statuses(row.get("backup_assessment"), materials)
        names = [m for m in materials if not has_backup[m]]
        if n_without is not None and len(names) == int(n_without):
            without_backup = names
        else:
            notes.append("backup text does not match number_of_materials_without_genuine_backup; "
                         "material names not listed")

        # Inventory statuses: cross-check text against the numeric count (R5).
        parsed = parse_inventory_statuses(row.get("inventory_buffer_detail"))
        below_count = _clean_number(row.get("materials_below_reorder_point_pooled"))
        listed = [m for m in materials if m in parsed]
        parsed_below = [m for m in materials if parsed.get(m) == BELOW]
        consistent = (
            len(listed) == len(materials)
            and below_count is not None
            and len(parsed_below) == int(below_count)
        )
        if consistent:
            inventory_statuses = [parsed[m] for m in materials]
            below_reorder = parsed_below
            unknown_materials = [m for m in materials if parsed[m] == INVENTORY_UNKNOWN]
            if unknown_materials and len(unknown_materials) < len(materials):
                notes.append(
                    "inventory risk is based on " + str(len(materials) - len(unknown_materials)) + " of "
                    + str(len(materials)) + " materials; pooled status unknown for "
                    + ", ".join(unknown_materials)
                )
            elif unknown_materials:
                notes.append("pooled inventory status unknown for all supplied materials ("
                             + ", ".join(unknown_materials) + ")")
        else:
            notes.append("inventory text does not match materials_below_reorder_point_pooled; "
                         "inventory risk set to Unknown")
    else:
        notes.append("no material mapping: material dependency and inventory risk are Unknown")

    # --- the six factor scores ---------------------------------------------
    scores = {
        "material_dependency": calculate_material_dependency_risk(
            n_materials if mapped else None, n_without),
        "inventory": calculate_inventory_risk(inventory_statuses),
        "lead_time": calculate_lead_time_risk(
            row.get("lead_time_days"), *ranges["lead_time"], equal_range_score=equal_range_score),
        "quality": calculate_quality_risk(
            row.get("quality_score"), *ranges["quality"], equal_range_score=equal_range_score),
        "capacity": calculate_capacity_risk(row.get("capacity_status")),
        "upstream_dependency": calculate_upstream_dependency_risk(
            row.get("number_of_upstream_suppliers"), *ranges["upstream"],
            equal_range_score=equal_range_score),
    }
    if scores["capacity"] is None:
        notes.append("capacity_status is missing or not 'sufficient'/'insufficient'")

    # --- overall score, confidence, category --------------------------------
    combined = combine_factor_scores(scores, weights)
    overall = combined["overall_risk_score"]
    overall_rounded = None if overall is None else round(overall, 2)
    original_category = classify_risk(overall_rounded, thresholds)

    # --- escalation (does not touch the score) ------------------------------
    if enable_escalation:
        escalation = evaluate_escalation(
            original_category, row.get("capacity_status"), without_backup, below_reorder)
    else:
        escalation = {"escalated": False, "final_category": original_category, "reasons": []}

    # --- explanations -------------------------------------------------------
    context = {
        "scores": scores, "ranges": ranges, "mapped": mapped,
        "n_materials": n_materials, "n_without_backup": n_without,
        "without_backup": without_backup, "below_reorder": below_reorder,
        "lead_time": _clean_number(row.get("lead_time_days")),
        "quality": _clean_number(row.get("quality_score")),
        "upstream": _clean_number(row.get("number_of_upstream_suppliers")),
        "known_count": len(combined["known_factors"]),
        "unknown_factors": combined["unknown_factors"],
    }

    record = {
        "supplier_id": _text(row.get("supplier_id")),
        "supplier_name": _text(row.get("supplier_name")),
    }
    for name in FACTOR_WEIGHTS:
        record[name + "_risk"] = _round_or_nan(scores[name])
        record[name + "_weight"] = weights[name]
    record.update({
        "overall_risk_score": _round_or_nan(overall),
        "original_risk_category": original_category,
        "final_risk_category": escalation["final_category"],
        "data_confidence_pct": round(combined["data_confidence_pct"], 2),
        "known_factor_count": len(combined["known_factors"]),
        "unknown_factor_count": len(combined["unknown_factors"]),
        "known_factors": _LIST_SEPARATOR.join(combined["known_factors"]),
        "unknown_factors": _LIST_SEPARATOR.join(combined["unknown_factors"]),
        "risk_reasons": _TEXT_SEPARATOR.join(_build_reasons(context, reason_min_score)),
        "escalation_occurred": escalation["escalated"],
        "escalation_reasons": _TEXT_SEPARATOR.join(escalation["reasons"]),
        "recommended_actions": _TEXT_SEPARATOR.join(_build_recommendations(context, reason_min_score)),
        "data_notes": _TEXT_SEPARATOR.join(notes),
    })
    return record


# ---------------------------------------------------------------------------
# The main function
# ---------------------------------------------------------------------------

def calculate_supplier_risk_scores(risk_factors, weights=None, thresholds=None,
                                   equal_range_score=EQUAL_RANGE_SCORE,
                                   reason_min_score=REASON_MIN_SCORE,
                                   enable_escalation=True):
    """
    Score every supplier in the risk-factor table (0-100, higher = riskier).

    risk_factors        DataFrame from supplier_risk.build_supplier_risk_factors()
    weights             optional {factor: percent weight}; default FACTOR_WEIGHTS
    thresholds          optional {"Medium", "High", "Critical": lowest score};
                        default CATEGORY_THRESHOLDS
    equal_range_score   score used when min == max (assumption R2)
    reason_min_score    min-max factors are mentioned as reasons from this score
    enable_escalation   set False to switch off the escalation layer

    Min-max ranges are taken from the suppliers in `risk_factors` (R1).
    The input DataFrame is not modified. Returns a new DataFrame with the
    columns in OUTPUT_COLUMNS, one row per input row, same order.
    """
    missing = [c for c in REQUIRED_INPUT_COLUMNS if c not in risk_factors.columns]
    if missing:
        raise ValueError("risk_factors is missing required column(s): " + ", ".join(missing))

    weights = check_weights(weights or FACTOR_WEIGHTS)
    thresholds = check_thresholds(thresholds or CATEGORY_THRESHOLDS)

    if len(risk_factors) == 0:
        return pd.DataFrame(columns=OUTPUT_COLUMNS)

    # Ranges for the three min-max factors, from the table being scored.
    ranges = {
        "lead_time": _column_range(risk_factors["lead_time_days"]),
        "quality": _column_range(risk_factors["quality_score"]),
        "upstream": _column_range(risk_factors["number_of_upstream_suppliers"]),
    }

    records = [
        _score_one_supplier(row, ranges, weights, thresholds, equal_range_score,
                            reason_min_score, enable_escalation)
        for row in risk_factors.to_dict("records")   # to_dict builds new objects
    ]
    return pd.DataFrame(records, columns=OUTPUT_COLUMNS)


# ---------------------------------------------------------------------------
# Reporting helper and command-line report
# ---------------------------------------------------------------------------

def summarise_scores(scores, low_confidence_below=70.0):
    """
    Small summary of a scoring table.

    Returns a dictionary:
      distribution          {"Low", "Medium", "High", "Critical", "Unknown": count}
                            (based on the FINAL category)
      original_distribution same, based on the weighted-score category
      escalated             list of supplier ids that were escalated
      low_confidence        DataFrame of suppliers with data confidence
                            below `low_confidence_below` percent
    """
    labels = CATEGORY_ORDER + [UNKNOWN]
    final = scores["final_risk_category"].value_counts()
    original = scores["original_risk_category"].value_counts()
    return {
        "distribution": {label: int(final.get(label, 0)) for label in labels},
        "original_distribution": {label: int(original.get(label, 0)) for label in labels},
        "escalated": scores.loc[scores["escalation_occurred"], "supplier_id"].tolist(),
        "low_confidence": scores.loc[
            scores["data_confidence_pct"] < low_confidence_below,
            ["supplier_id", "supplier_name", "data_confidence_pct", "unknown_factors"],
        ],
    }


if __name__ == "__main__":
    # Run from the project folder:  python -m src.risk_scoring
    # (imported here so the scoring functions above need no project data)
    from src.data_loader import load_all_data
    from src.supply_chain_graph import get_supply_chain_graph
    from src.supplier_risk import build_supplier_risk_factors

    project_data = load_all_data(verbose=False)
    project_graph = get_supply_chain_graph(project_data)
    factor_table = build_supplier_risk_factors(project_data, project_graph)
    result = calculate_supplier_risk_scores(factor_table)
    summary = summarise_scores(result)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", 30)
    print("Final category distribution :", summary["distribution"])
    print("Weighted-score distribution :", summary["original_distribution"])
    print("Escalated suppliers         :", summary["escalated"])
    print()
    print(result[["supplier_id", "overall_risk_score", "original_risk_category",
                  "final_risk_category", "data_confidence_pct",
                  "unknown_factors"]].to_string(index=False))
    print()
    print("Data confidence below 70%:")
    print(summary["low_confidence"].to_string(index=False))
