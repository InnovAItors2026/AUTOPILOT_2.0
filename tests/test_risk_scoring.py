"""
Automated tests for AUTOPILOT 2.0 Member 2, Step 3: src/risk_scoring.py

Most tests use small hand-made risk-factor tables (same columns as
supplier_risk.build_supplier_risk_factors()), so the expected answers can be
checked by hand. The text columns are produced with supplier_risk.py's own
helper functions, so these tests also prove that the scoring module still
understands the wording supplier_risk.py writes.

The last class (RealDatasetCompatibilityTests) runs on the real 35 suppliers.
"""

import copy
import math
import os
import sys
import unittest

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.risk_scoring import (
    CATEGORY_THRESHOLDS,
    FACTOR_WEIGHTS,
    OUTPUT_COLUMNS,
    SCORE_COLUMNS,
    WEIGHT_COLUMNS,
    calculate_capacity_risk,
    calculate_inventory_risk,
    calculate_lead_time_risk,
    calculate_material_dependency_risk,
    calculate_quality_risk,
    calculate_supplier_risk_scores,
    calculate_upstream_dependency_risk,
    check_thresholds,
    check_weights,
    classify_risk,
    combine_factor_scores,
    evaluate_escalation,
    parse_backup_statuses,
    parse_inventory_statuses,
    summarise_scores,
)
from src.supplier_risk import (
    _describe_backup_check,
    _describe_inventory,
    _summarise_inventory,
    check_backup_candidate,
)


# ---------------------------------------------------------------------------
# Helpers that build realistic input tables
# ---------------------------------------------------------------------------

WHOLE_NUMBER_COLUMNS = [
    "number_of_upstream_suppliers", "number_of_downstream_suppliers",
    "number_of_materials_supplied", "number_of_single_source_materials",
    "number_of_genuine_independent_backups", "number_of_materials_without_genuine_backup",
    "inventory_rows_for_supplied_materials", "inventory_rows_below_reorder_point",
    "materials_below_reorder_point_pooled",
]


def inventory_text(material_id, kind):
    """The inventory sentence supplier_risk.py writes: kind = below/above/unknown/none."""
    if kind == "none":
        return _describe_inventory(material_id, None)
    rows = {"below": [(100, 200)], "above": [(500, 200)], "unknown": [(None, 200)]}[kind]
    table = pd.DataFrame(
        [{"material_id": material_id, "quantity_on_hand": q, "reorder_point": r} for q, r in rows]
    )
    return _describe_inventory(material_id, _summarise_inventory(table)[material_id])


def backup_text(material_id, kind):
    """The backup line supplier_risk.py writes: kind = genuine / shared / single."""
    if kind == "single":
        return material_id + ": single source, no other supplier listed"
    upstream_of = {"P": {"X"}, "A": {"Y"}, "S": {"X"}}      # S shares upstream X with P
    rows = {
        ("P", material_id): {"monthly_capacity_units": 1000, "is_backup": 0},
        ("A", material_id): {"monthly_capacity_units": 1500, "is_backup": 1},
        ("S", material_id): {"monthly_capacity_units": 1500, "is_backup": 1},
    }
    info = {name: {"capacity_status": "sufficient"} for name in ("P", "A", "S")}
    candidate = {"genuine": "A", "shared": "S"}[kind]
    return _describe_backup_check(check_backup_candidate("P", candidate, material_id, upstream_of, rows, info))


def make_row(supplier_id="S1", **changes):
    """
    One risk-factor row (a dictionary). Default: one material MAT-01 with a
    genuine backup, stock above reorder point, sufficient capacity.

    Pass materials=[(material_id, backup_kind, inventory_kind), ...] to build
    the material columns consistently, plus any plain column as a keyword.
    """
    materials = changes.pop("materials", [("MAT-01", "genuine", "above")])
    row = {
        "supplier_id": supplier_id,
        "supplier_name": "Supplier " + supplier_id,
        "tier": 2,
        "lead_time_days": 10,
        "quality_score": 0.9,
        "capacity_status": "sufficient",
        "number_of_upstream_suppliers": 1,
        "number_of_downstream_suppliers": 0,
    }
    if materials:
        ids = [m[0] for m in materials]
        without = [m[0] for m in materials if m[1] != "genuine"]
        below = [m[0] for m in materials if m[2] == "below"]
        row.update({
            "has_material_mapping": True,
            "number_of_materials_supplied": len(ids),
            "materials_supplied": "; ".join(ids),
            "number_of_single_source_materials": sum(1 for m in materials if m[1] == "single"),
            "single_source_materials": "; ".join(m[0] for m in materials if m[1] == "single"),
            "number_of_genuine_independent_backups": len(ids) - len(without),
            "number_of_materials_without_genuine_backup": len(without),
            "backup_assessment": " | ".join(backup_text(m[0], m[1]) for m in materials),
            "inventory_rows_for_supplied_materials": len(ids),
            "inventory_rows_below_reorder_point": len(below),
            "materials_below_reorder_point_pooled": len(below),
            "inventory_buffer_detail": " | ".join(inventory_text(m[0], m[2]) for m in materials),
        })
    else:   # no material mapping (supplier_risk.py leaves these empty)
        no_mapping = "No row in supplier_materials.csv, so the materials supplied are unknown"
        row.update({
            "has_material_mapping": False,
            "number_of_materials_supplied": 0,
            "materials_supplied": "",
            "number_of_single_source_materials": None,
            "single_source_materials": "",
            "number_of_genuine_independent_backups": None,
            "number_of_materials_without_genuine_backup": None,
            "backup_assessment": no_mapping,
            "inventory_rows_for_supplied_materials": None,
            "inventory_rows_below_reorder_point": None,
            "materials_below_reorder_point_pooled": None,
            "inventory_buffer_detail": no_mapping,
        })
    row.update(changes)
    return row


def make_table(rows):
    """Rows -> DataFrame with the same column types as build_supplier_risk_factors()."""
    table = pd.DataFrame(rows)
    for column in WHOLE_NUMBER_COLUMNS:
        table[column] = pd.array(table[column].tolist(), dtype="Int64")
    for column in ("lead_time_days", "quality_score"):
        table[column] = pd.to_numeric(table[column], errors="coerce")
    return table


def score_one(**changes):
    """Score a single supplier on its own (its min-max ranges are then all equal)."""
    return calculate_supplier_risk_scores(make_table([make_row(**changes)])).iloc[0]


def three_supplier_table():
    """Three suppliers with spread-out numbers, so min-max scores are 0 / 50 / 100."""
    return make_table([
        make_row("A", lead_time_days=10, quality_score=0.9, number_of_upstream_suppliers=0),
        make_row("B", lead_time_days=20, quality_score=0.8, number_of_upstream_suppliers=2),
        make_row("C", lead_time_days=30, quality_score=0.7, number_of_upstream_suppliers=4),
    ])


# ---------------------------------------------------------------------------
# 1. The six factor calculations
# ---------------------------------------------------------------------------

class FactorCalculationTests(unittest.TestCase):
    # Factor 1
    def test_material_dependency_all_with_backup_is_0(self):
        self.assertEqual(calculate_material_dependency_risk(3, 0), 0.0)

    def test_material_dependency_none_with_backup_is_100(self):
        self.assertEqual(calculate_material_dependency_risk(2, 2), 100.0)

    def test_material_dependency_is_mean_of_material_scores(self):
        # 1 of 4 materials without a backup = mean(100, 0, 0, 0) = 25
        self.assertEqual(calculate_material_dependency_risk(4, 1), 25.0)
        self.assertAlmostEqual(calculate_material_dependency_risk(3, 1), (100 + 0 + 0) / 3)

    def test_material_dependency_unknown_cases(self):
        self.assertIsNone(calculate_material_dependency_risk(0, 0))
        self.assertIsNone(calculate_material_dependency_risk(None, None))
        self.assertIsNone(calculate_material_dependency_risk(2, pd.NA))
        self.assertIsNone(calculate_material_dependency_risk(2, 3))      # impossible
        self.assertIsNone(calculate_material_dependency_risk(float("nan"), 0))

    # Factor 2
    def test_inventory_below_is_100_and_above_is_0(self):
        self.assertEqual(calculate_inventory_risk(["BELOW"]), 100.0)
        self.assertEqual(calculate_inventory_risk(["ABOVE"]), 0.0)

    def test_inventory_mean_of_assessed_materials(self):
        self.assertEqual(calculate_inventory_risk(["BELOW", "ABOVE"]), 50.0)

    def test_inventory_unknown_materials_are_skipped_not_zero(self):
        # If UNKNOWN counted as 0 this would be 33.3, not 50.
        self.assertEqual(calculate_inventory_risk(["BELOW", "ABOVE", "UNKNOWN"]), 50.0)

    def test_inventory_all_unknown_or_empty_is_unknown(self):
        self.assertIsNone(calculate_inventory_risk(["UNKNOWN", "UNKNOWN"]))
        self.assertIsNone(calculate_inventory_risk([]))
        self.assertIsNone(calculate_inventory_risk(None))

    # Factor 3
    def test_lead_time_min_max(self):
        self.assertEqual(calculate_lead_time_risk(10, 10, 30), 0.0)
        self.assertEqual(calculate_lead_time_risk(20, 10, 30), 50.0)
        self.assertEqual(calculate_lead_time_risk(30, 10, 30), 100.0)
        self.assertAlmostEqual(calculate_lead_time_risk(15, 10, 30), 25.0)

    def test_lead_time_missing_is_unknown(self):
        self.assertIsNone(calculate_lead_time_risk(None, 10, 30))
        self.assertIsNone(calculate_lead_time_risk(float("nan"), 10, 30))
        self.assertIsNone(calculate_lead_time_risk(10, None, None))

    # Factor 4
    def test_quality_higher_means_lower_risk(self):
        self.assertEqual(calculate_quality_risk(0.9, 0.7, 0.9), 0.0)     # best quality
        self.assertEqual(calculate_quality_risk(0.7, 0.7, 0.9), 100.0)   # worst quality
        self.assertAlmostEqual(calculate_quality_risk(0.8, 0.7, 0.9), 50.0)

    def test_quality_missing_is_unknown(self):
        self.assertIsNone(calculate_quality_risk(None, 0.7, 0.9))

    # Factor 5
    def test_capacity_values(self):
        self.assertEqual(calculate_capacity_risk("sufficient"), 0.0)
        self.assertEqual(calculate_capacity_risk("insufficient"), 100.0)
        self.assertEqual(calculate_capacity_risk("  Insufficient "), 100.0)   # case / spaces

    def test_capacity_unknown_cases(self):
        for value in (None, "", "unknown", "limited", float("nan"), pd.NA):
            self.assertIsNone(calculate_capacity_risk(value), repr(value))

    # Factor 6
    def test_upstream_min_max(self):
        self.assertEqual(calculate_upstream_dependency_risk(0, 0, 4), 0.0)
        self.assertEqual(calculate_upstream_dependency_risk(2, 0, 4), 50.0)
        self.assertEqual(calculate_upstream_dependency_risk(4, 0, 4), 100.0)

    def test_upstream_missing_is_unknown(self):
        self.assertIsNone(calculate_upstream_dependency_risk(pd.NA, 0, 4))
        self.assertIsNone(calculate_upstream_dependency_risk(None, 0, 4))

    def test_values_outside_the_range_are_kept_inside_0_to_100(self):
        self.assertEqual(calculate_lead_time_risk(99, 10, 30), 100.0)
        self.assertEqual(calculate_lead_time_risk(1, 10, 30), 0.0)


# ---------------------------------------------------------------------------
# 7. Equal minimum and maximum values
# ---------------------------------------------------------------------------

class EqualRangeTests(unittest.TestCase):
    def test_equal_min_and_max_does_not_divide_by_zero(self):
        self.assertEqual(calculate_lead_time_risk(15, 15, 15), 0.0)
        self.assertEqual(calculate_quality_risk(0.8, 0.8, 0.8), 0.0)
        self.assertEqual(calculate_upstream_dependency_risk(3, 3, 3), 0.0)

    def test_fallback_can_be_changed(self):
        self.assertEqual(calculate_lead_time_risk(15, 15, 15, equal_range_score=50.0), 50.0)

    def test_equal_range_with_missing_value_is_still_unknown(self):
        self.assertIsNone(calculate_lead_time_risk(None, 15, 15))

    def test_table_where_every_supplier_has_the_same_values(self):
        table = make_table([make_row("A"), make_row("B"), make_row("C")])
        result = calculate_supplier_risk_scores(table)
        for column in ("lead_time_risk", "quality_risk", "upstream_dependency_risk"):
            self.assertTrue((result[column] == 0.0).all(), column)

    def test_wrong_order_of_min_and_max_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_lead_time_risk(5, 30, 10)


# ---------------------------------------------------------------------------
# 2, 5, 6. Weighted score, data confidence, missing factors, nothing known
# ---------------------------------------------------------------------------

class WeightedScoreTests(unittest.TestCase):
    def test_weights_are_the_requested_ones_and_add_up_to_100(self):
        self.assertEqual(
            FACTOR_WEIGHTS,
            {"material_dependency": 30, "inventory": 20, "lead_time": 15,
             "quality": 15, "capacity": 15, "upstream_dependency": 5},
        )
        self.assertEqual(sum(FACTOR_WEIGHTS.values()), 100)

    def test_all_six_factors_known(self):
        scores = {"material_dependency": 100, "inventory": 0, "lead_time": 50,
                  "quality": 20, "capacity": 100, "upstream_dependency": 40}
        # 100*30 + 0*20 + 50*15 + 20*15 + 100*15 + 40*5 = 3000+0+750+300+1500+200 = 5750
        result = combine_factor_scores(scores)
        self.assertAlmostEqual(result["overall_risk_score"], 57.5)
        self.assertEqual(result["data_confidence_pct"], 100.0)
        self.assertEqual(result["unknown_factors"], [])

    def test_unknown_factors_are_left_out_not_counted_as_zero(self):
        scores = {"material_dependency": 100, "inventory": None, "lead_time": 0,
                  "quality": None, "capacity": 100, "upstream_dependency": None}
        # known: 30 + 15 + 15 = 60 -> (100*30 + 0*15 + 100*15) / 60 = 75
        result = combine_factor_scores(scores)
        self.assertAlmostEqual(result["overall_risk_score"], 75.0)
        self.assertAlmostEqual(result["data_confidence_pct"], 60.0)
        self.assertEqual(result["known_factors"], ["material_dependency", "lead_time", "capacity"])
        self.assertEqual(result["unknown_factors"], ["inventory", "quality", "upstream_dependency"])

    def test_risk_score_and_data_confidence_are_independent(self):
        # Only the 5% factor is known: score can be 100 while confidence is 5.
        scores = {name: None for name in FACTOR_WEIGHTS}
        scores["upstream_dependency"] = 100
        result = combine_factor_scores(scores)
        self.assertEqual(result["overall_risk_score"], 100.0)
        self.assertEqual(result["data_confidence_pct"], 5.0)

    def test_all_factors_missing_gives_no_score(self):
        result = combine_factor_scores({name: None for name in FACTOR_WEIGHTS})
        self.assertIsNone(result["overall_risk_score"])
        self.assertEqual(result["data_confidence_pct"], 0.0)
        self.assertEqual(len(result["unknown_factors"]), 6)

    def test_custom_weights_are_used(self):
        scores = {name: 0 for name in FACTOR_WEIGHTS}
        scores["lead_time"] = 100
        weights = dict(FACTOR_WEIGHTS, lead_time=50.0, material_dependency=0.0)
        # total weight = 0 + 20 + 50 + 15 + 15 + 5 = 105; only lead_time scores 100 -> 100*50 / 105 = 47.62
        self.assertEqual(sum(weights.values()), 105)
        self.assertAlmostEqual(combine_factor_scores(scores, weights)["overall_risk_score"], 100 * 50 / 105)
        # confidence is also relative to the custom total
        self.assertEqual(combine_factor_scores(scores, weights)["data_confidence_pct"], 100.0)

    def test_bad_weights_and_thresholds_are_rejected(self):
        with self.assertRaises(ValueError):
            check_weights({"lead_time": 100})
        with self.assertRaises(ValueError):
            check_weights(dict(FACTOR_WEIGHTS, quality=-1))
        with self.assertRaises(ValueError):
            check_weights({name: 0 for name in FACTOR_WEIGHTS})
        with self.assertRaises(ValueError):
            check_thresholds({"Medium": 50, "High": 25, "Critical": 75})

    def test_table_overall_score_matches_hand_calculation(self):
        # Supplier C of the three-supplier table: lead 100, quality 100, upstream 100,
        # capacity 0, material 0 (has backup), inventory 0 (above) -> (15+15+5)*100/100 = 35
        result = calculate_supplier_risk_scores(three_supplier_table()).set_index("supplier_id")
        self.assertAlmostEqual(result.loc["C", "overall_risk_score"], 35.0)
        # Supplier B: lead 50, quality 50, upstream 50, rest 0 -> 35 * 0.5 = 17.5
        self.assertAlmostEqual(result.loc["B", "overall_risk_score"], 17.5)
        self.assertAlmostEqual(result.loc["A", "overall_risk_score"], 0.0)


class TableLevelMissingDataTests(unittest.TestCase):
    # 3. missing material mapping
    def test_missing_material_mapping_stays_unknown(self):
        row = score_one(materials=[])
        self.assertTrue(math.isnan(row["material_dependency_risk"]))
        self.assertTrue(math.isnan(row["inventory_risk"]))
        self.assertIn("material_dependency", row["unknown_factors"])
        self.assertIn("inventory", row["unknown_factors"])
        self.assertIn("no material mapping", row["data_notes"])
        # 30 + 20 of 100 weight are unknown -> 50% confidence
        self.assertEqual(row["data_confidence_pct"], 50.0)
        self.assertEqual(row["known_factor_count"], 4)
        self.assertEqual(row["unknown_factor_count"], 2)
        # ...and the other four factors still give a real score.
        self.assertFalse(math.isnan(row["overall_risk_score"]))

    def test_missing_mapping_recommends_getting_the_mapping(self):
        row = score_one(materials=[])
        self.assertIn("material mapping", row["recommended_actions"])

    # 4. missing inventory information
    def test_missing_inventory_is_unknown_not_zero(self):
        row = score_one(materials=[("MAT-01", "genuine", "unknown")])
        self.assertTrue(math.isnan(row["inventory_risk"]))
        self.assertIn("inventory", row["unknown_factors"])
        self.assertEqual(row["data_confidence_pct"], 80.0)
        self.assertIn("pooled inventory status unknown", row["data_notes"])

    def test_partly_missing_inventory_uses_only_assessed_materials(self):
        row = score_one(materials=[("MAT-01", "genuine", "below"), ("MAT-02", "genuine", "unknown")])
        self.assertEqual(row["inventory_risk"], 100.0)
        self.assertIn("1 of 2 materials", row["data_notes"])
        self.assertIn("MAT-02", row["data_notes"])

    def test_material_with_no_inventory_rows_is_unknown(self):
        row = score_one(materials=[("MAT-01", "genuine", "none")])
        self.assertTrue(math.isnan(row["inventory_risk"]))

    def test_missing_lead_time_quality_capacity_upstream(self):
        row = score_one(lead_time_days=None, quality_score=None, capacity_status=None,
                        number_of_upstream_suppliers=None)
        for column in ("lead_time_risk", "quality_risk", "capacity_risk", "upstream_dependency_risk"):
            self.assertTrue(math.isnan(row[column]), column)
        # only material (30) + inventory (20) known
        self.assertEqual(row["data_confidence_pct"], 50.0)
        self.assertEqual(row["known_factors"], "material_dependency; inventory")
        self.assertEqual(row["unknown_factors"], "lead_time; quality; capacity; upstream_dependency")

    # 6. all factors missing
    def test_all_factors_missing_gives_unknown_score_and_category(self):
        row = score_one(materials=[], lead_time_days=None, quality_score=None,
                        capacity_status=None, number_of_upstream_suppliers=None)
        self.assertTrue(math.isnan(row["overall_risk_score"]))
        self.assertEqual(row["original_risk_category"], "Unknown")
        self.assertEqual(row["final_risk_category"], "Unknown")
        self.assertEqual(row["data_confidence_pct"], 0.0)
        self.assertEqual(row["known_factor_count"], 0)
        self.assertEqual(row["unknown_factor_count"], 6)
        self.assertFalse(row["escalation_occurred"])
        self.assertIn("cannot be assessed", row["risk_reasons"])

    def test_text_that_disagrees_with_the_counts_becomes_unknown_not_a_guess(self):
        # The number says 1 material is below reorder point; the text says none are.
        row = score_one(materials=[("MAT-01", "genuine", "above")], materials_below_reorder_point_pooled=1)
        self.assertTrue(math.isnan(row["inventory_risk"]))
        self.assertIn("does not match", row["data_notes"])


# ---------------------------------------------------------------------------
# 8. Classification boundaries
# ---------------------------------------------------------------------------

class ClassificationTests(unittest.TestCase):
    def test_boundaries(self):
        expected = [
            (0, "Low"), (24.99, "Low"), (25, "Medium"), (49.99, "Medium"),
            (50, "High"), (74.99, "High"), (75, "Critical"), (100, "Critical"),
        ]
        for score, category in expected:
            self.assertEqual(classify_risk(score), category, score)

    def test_score_is_rounded_before_classifying(self):
        self.assertEqual(classify_risk(24.999), "Medium")    # shows as 25.0
        self.assertEqual(classify_risk(24.991), "Low")       # shows as 24.99

    def test_unknown_score_gives_unknown_category(self):
        self.assertEqual(classify_risk(None), "Unknown")
        self.assertEqual(classify_risk(float("nan")), "Unknown")
        self.assertEqual(classify_risk(pd.NA), "Unknown")

    def test_custom_thresholds(self):
        thresholds = {"Medium": 10, "High": 20, "Critical": 30}
        self.assertEqual(classify_risk(15, thresholds), "Medium")
        self.assertEqual(classify_risk(30, thresholds), "Critical")

    def test_default_thresholds_are_the_requested_ones(self):
        self.assertEqual(CATEGORY_THRESHOLDS, {"Medium": 25.0, "High": 50.0, "Critical": 75.0})

    def test_table_categories_follow_scores(self):
        result = calculate_supplier_risk_scores(three_supplier_table())
        for _, row in result.iterrows():
            self.assertEqual(row["original_risk_category"], classify_risk(row["overall_risk_score"]))


# ---------------------------------------------------------------------------
# 9. Critical escalation
# ---------------------------------------------------------------------------

class EscalationTests(unittest.TestCase):
    TRIPLE = dict(materials=[("MAT-01", "shared", "below")], capacity_status="insufficient")

    def test_rule_unit_escalates_when_all_three_conditions_hold_for_one_material(self):
        result = evaluate_escalation("Medium", "insufficient", ["MAT-01"], ["MAT-01"])
        self.assertTrue(result["escalated"])
        self.assertEqual(result["final_category"], "Critical")
        self.assertIn("MAT-01", result["reasons"][0])
        self.assertIn("from Medium to Critical", result["reasons"][0])

    def test_rule_unit_each_missing_condition_blocks_escalation(self):
        self.assertFalse(evaluate_escalation("Medium", "sufficient", ["MAT-01"], ["MAT-01"])["escalated"])
        self.assertFalse(evaluate_escalation("Medium", None, ["MAT-01"], ["MAT-01"])["escalated"])
        self.assertFalse(evaluate_escalation("Medium", "insufficient", [], ["MAT-01"])["escalated"])
        self.assertFalse(evaluate_escalation("Medium", "insufficient", ["MAT-01"], [])["escalated"])
        # unknown evidence (None) never escalates
        self.assertFalse(evaluate_escalation("Medium", "insufficient", None, ["MAT-01"])["escalated"])
        self.assertFalse(evaluate_escalation("Medium", "insufficient", ["MAT-01"], None)["escalated"])

    def test_conditions_must_hold_for_the_same_material(self):
        # MAT-01 lacks a backup, MAT-02 is below reorder point: not the same material.
        result = evaluate_escalation("Low", "insufficient", ["MAT-01"], ["MAT-02"])
        self.assertFalse(result["escalated"])

    def test_already_critical_is_not_reported_as_escalated(self):
        result = evaluate_escalation("Critical", "insufficient", ["MAT-01"], ["MAT-01"])
        self.assertFalse(result["escalated"])
        self.assertEqual(result["final_category"], "Critical")

    def test_escalated_supplier_in_table_keeps_its_score_and_original_category(self):
        row = score_one(**self.TRIPLE)
        # material 100*30 + inventory 100*20 + capacity 100*15 + others 0 -> 6500/100 = 65 (High)
        self.assertAlmostEqual(row["overall_risk_score"], 65.0)
        self.assertEqual(row["original_risk_category"], "High")
        self.assertEqual(row["final_risk_category"], "Critical")
        self.assertTrue(row["escalation_occurred"])
        self.assertIn("Rule E1", row["escalation_reasons"])
        self.assertIn("MAT-01", row["escalation_reasons"])
        self.assertIn("score is unchanged", row["escalation_reasons"])

    def test_no_backup_alone_is_not_escalated(self):
        row = score_one(materials=[("MAT-01", "single", "above")])
        self.assertEqual(row["final_risk_category"], row["original_risk_category"])
        self.assertFalse(row["escalation_occurred"])
        self.assertEqual(row["escalation_reasons"], "")

    def test_two_of_three_conditions_is_not_escalated(self):
        row = score_one(materials=[("MAT-01", "single", "below")], capacity_status="sufficient")
        self.assertFalse(row["escalation_occurred"])
        row = score_one(materials=[("MAT-01", "genuine", "below")], capacity_status="insufficient")
        self.assertFalse(row["escalation_occurred"])

    def test_unknown_inventory_blocks_escalation(self):
        row = score_one(materials=[("MAT-01", "single", "unknown")], capacity_status="insufficient")
        self.assertFalse(row["escalation_occurred"])

    def test_escalation_can_be_switched_off(self):
        result = calculate_supplier_risk_scores(make_table([make_row(**self.TRIPLE)]), enable_escalation=False)
        self.assertEqual(result.iloc[0]["final_risk_category"], "High")
        self.assertFalse(result.iloc[0]["escalation_occurred"])

    def test_final_category_is_never_lower_than_original(self):
        table = make_table([make_row("A", **self.TRIPLE), make_row("B"), make_row("C", capacity_status=None)])
        result = calculate_supplier_risk_scores(table)
        order = ["Unknown", "Low", "Medium", "High", "Critical"]
        for _, row in result.iterrows():
            self.assertGreaterEqual(order.index(row["final_risk_category"]),
                                    order.index(row["original_risk_category"]))


# ---------------------------------------------------------------------------
# 10. Explanations and recommendations
# ---------------------------------------------------------------------------

class ExplanationTests(unittest.TestCase):
    def setUp(self):
        self.result = calculate_supplier_risk_scores(three_supplier_table()).set_index("supplier_id")

    def test_every_requested_output_column_exists(self):
        for column in ("supplier_id", "supplier_name", "overall_risk_score", "original_risk_category",
                       "final_risk_category", "data_confidence_pct", "known_factors", "unknown_factors",
                       "risk_reasons", "escalation_occurred", "escalation_reasons", "recommended_actions"):
            self.assertIn(column, OUTPUT_COLUMNS)
        self.assertEqual(len(SCORE_COLUMNS), 6)
        self.assertEqual(len(WEIGHT_COLUMNS), 6)
        self.assertEqual(list(self.result.reset_index().columns), OUTPUT_COLUMNS)

    def test_weights_are_reported_per_factor(self):
        row = self.result.loc["A"]
        for name, weight in FACTOR_WEIGHTS.items():
            self.assertEqual(row[name + "_weight"], weight)

    def test_no_backup_gives_reason_and_alternative_supplier_action(self):
        row = score_one(materials=[("MAT-01", "single", "above"), ("MAT-02", "genuine", "above")])
        self.assertIn("1 of 2", row["risk_reasons"])
        self.assertIn("MAT-01", row["risk_reasons"])
        self.assertIn("independent alternative supplier for MAT-01", row["recommended_actions"])

    def test_shared_upstream_alternative_still_means_no_genuine_backup(self):
        row = score_one(materials=[("MAT-01", "shared", "above")])
        self.assertEqual(row["material_dependency_risk"], 100.0)
        self.assertIn("independent alternative supplier for MAT-01", row["recommended_actions"])

    def test_inventory_below_reorder_gives_replenishment_action(self):
        row = score_one(materials=[("MAT-01", "genuine", "below")])
        self.assertIn("pooled stock is below the reorder point for MAT-01", row["risk_reasons"])
        self.assertIn("Prioritise replenishment of MAT-01", row["recommended_actions"])

    def test_insufficient_capacity_gives_capacity_action(self):
        row = score_one(capacity_status="insufficient")
        self.assertIn("insufficient", row["risk_reasons"])
        self.assertIn("capacity or allocate production elsewhere", row["recommended_actions"])

    def test_long_lead_time_gives_lead_time_action_with_the_actual_number(self):
        row = self.result.loc["C"]
        self.assertIn("Lead time of 30 days", row["risk_reasons"])
        self.assertIn("safety stock", row["recommended_actions"])
        self.assertIn("lead time 30 days", row["recommended_actions"])

    def test_low_quality_gives_quality_action_with_the_actual_number(self):
        row = self.result.loc["C"]
        self.assertIn("Quality score of 0.7", row["risk_reasons"])
        self.assertIn("quality performance", row["recommended_actions"])

    def test_best_supplier_gets_no_unsupported_recommendations(self):
        row = self.result.loc["A"]
        self.assertEqual(row["recommended_actions"], "No specific action indicated by the current data")
        self.assertIn("No single factor stands out", row["risk_reasons"])
        for word in ("alternative", "replenishment", "capacity", "safety stock", "quality", "upstream"):
            self.assertNotIn(word, row["recommended_actions"])

    def test_no_recommendation_without_its_evidence(self):
        # Healthy supplier with a middle-of-the-range lead time (score 50 is shown, 49 is not).
        row = self.result.loc["B"]
        self.assertIn("Lead time", row["risk_reasons"])          # 50 >= 50
        table = make_table([
            make_row("A", lead_time_days=10), make_row("B", lead_time_days=29), make_row("C", lead_time_days=60),
        ])
        quiet = calculate_supplier_risk_scores(table).set_index("supplier_id").loc["B"]
        self.assertNotIn("Lead time", quiet["risk_reasons"])      # (29-10)/50 = 38
        self.assertNotIn("safety stock", quiet["recommended_actions"])

    def test_missing_data_recommends_obtaining_it(self):
        row = score_one(capacity_status=None)
        self.assertIn("Obtain the missing data for: supplier capacity", row["recommended_actions"])

    def test_upstream_reason_says_it_is_only_a_proxy(self):
        row = self.result.loc["C"]
        self.assertIn("provisional exposure proxy", row["risk_reasons"])


# ---------------------------------------------------------------------------
# The text parsers are tied to supplier_risk.py's real wording
# ---------------------------------------------------------------------------

class ParserContractTests(unittest.TestCase):
    def test_inventory_wording_from_supplier_risk_is_understood(self):
        for kind, expected in (("below", "BELOW"), ("above", "ABOVE"), ("unknown", "UNKNOWN"), ("none", "UNKNOWN")):
            parsed = parse_inventory_statuses(inventory_text("MAT-07", kind))
            self.assertEqual(parsed, {"MAT-07": expected}, kind)

    def test_several_materials_in_one_detail_text(self):
        text = " | ".join([inventory_text("MAT-01", "below"), inventory_text("MAT-02", "above"),
                           inventory_text("MAT-03", "unknown")])
        self.assertEqual(parse_inventory_statuses(text),
                         {"MAT-01": "BELOW", "MAT-02": "ABOVE", "MAT-03": "UNKNOWN"})

    def test_backup_wording_from_supplier_risk_is_understood(self):
        self.assertEqual(parse_backup_statuses(backup_text("MAT-01", "genuine"), ["MAT-01"]), {"MAT-01": True})
        self.assertEqual(parse_backup_statuses(backup_text("MAT-01", "shared"), ["MAT-01"]), {"MAT-01": False})
        self.assertEqual(parse_backup_statuses(backup_text("MAT-01", "single"), ["MAT-01"]), {"MAT-01": False})

    def test_one_genuine_line_is_enough_for_a_material(self):
        text = backup_text("MAT-01", "shared") + " | " + backup_text("MAT-01", "genuine")
        self.assertEqual(parse_backup_statuses(text, ["MAT-01"]), {"MAT-01": True})

    def test_text_with_no_known_material_gives_unknown_defaults(self):
        self.assertEqual(parse_inventory_statuses("nonsense"), {})
        self.assertEqual(parse_backup_statuses("nonsense", ["MAT-01"]), {"MAT-01": False})


# ---------------------------------------------------------------------------
# 11. Input is not modified
# ---------------------------------------------------------------------------

class InputUnchangedTests(unittest.TestCase):
    def test_input_dataframe_is_not_modified(self):
        table = make_table([make_row("A", lead_time_days=5), make_row("B", lead_time_days=50,
                            materials=[("MAT-01", "single", "below")], capacity_status="insufficient"),
                            make_row("C", materials=[])])
        before = table.copy(deep=True)
        columns_before = list(table.columns)
        calculate_supplier_risk_scores(table)
        self.assertEqual(list(table.columns), columns_before)
        self.assertTrue(table.equals(before))
        pd.testing.assert_frame_equal(table, before)

    def test_settings_dictionaries_are_not_modified(self):
        weights_before = copy.deepcopy(FACTOR_WEIGHTS)
        thresholds_before = copy.deepcopy(CATEGORY_THRESHOLDS)
        calculate_supplier_risk_scores(three_supplier_table())
        self.assertEqual(FACTOR_WEIGHTS, weights_before)
        self.assertEqual(CATEGORY_THRESHOLDS, thresholds_before)

    def test_same_input_gives_same_output(self):
        table = three_supplier_table()
        pd.testing.assert_frame_equal(calculate_supplier_risk_scores(table), calculate_supplier_risk_scores(table))

    def test_output_has_one_row_per_input_row_in_the_same_order(self):
        table = three_supplier_table()
        result = calculate_supplier_risk_scores(table)
        self.assertEqual(result["supplier_id"].tolist(), table["supplier_id"].tolist())

    def test_missing_required_column_raises_clear_error(self):
        table = three_supplier_table().drop(columns=["quality_score"])
        with self.assertRaises(ValueError) as caught:
            calculate_supplier_risk_scores(table)
        self.assertIn("quality_score", str(caught.exception))

    def test_empty_table_gives_empty_result_with_columns(self):
        empty = three_supplier_table().iloc[0:0]
        result = calculate_supplier_risk_scores(empty)
        self.assertEqual(len(result), 0)
        self.assertEqual(list(result.columns), OUTPUT_COLUMNS)

    def test_summary_helper(self):
        table = make_table([make_row("A"), make_row("B", materials=[("MAT-01", "shared", "below")],
                            capacity_status="insufficient"), make_row("C", materials=[], capacity_status=None)])
        summary = summarise_scores(calculate_supplier_risk_scores(table))
        self.assertEqual(sum(summary["distribution"].values()), 3)
        self.assertEqual(summary["escalated"], ["B"])
        self.assertEqual(summary["low_confidence"]["supplier_id"].tolist(), ["C"])


# ---------------------------------------------------------------------------
# 12. The real 35-supplier dataset (needs the whole project)
# ---------------------------------------------------------------------------

class RealDatasetCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from src.data_loader import load_all_data
        from src.supply_chain_graph import get_supply_chain_graph
        from src.supplier_risk import build_supplier_risk_factors

        cls.data = load_all_data(verbose=False)
        cls.graph = get_supply_chain_graph(cls.data)
        cls.factors = build_supplier_risk_factors(cls.data, cls.graph)
        cls.before = cls.factors.copy(deep=True)
        cls.scores = calculate_supplier_risk_scores(cls.factors)

    def test_all_35_suppliers_are_scored_once(self):
        self.assertEqual(len(self.scores), 35)
        self.assertEqual(self.scores["supplier_id"].nunique(), 35)
        self.assertEqual(sorted(self.scores["supplier_id"]), sorted(self.factors["supplier_id"]))

    def test_columns_and_value_ranges(self):
        self.assertEqual(list(self.scores.columns), OUTPUT_COLUMNS)
        for column in SCORE_COLUMNS + ["overall_risk_score"]:
            values = self.scores[column].dropna()
            self.assertTrue(((values >= 0) & (values <= 100)).all(), column)
        confidence = self.scores["data_confidence_pct"]
        self.assertTrue(((confidence >= 0) & (confidence <= 100)).all())

    def test_categories_are_valid_and_consistent(self):
        allowed = {"Low", "Medium", "High", "Critical", "Unknown"}
        self.assertTrue(set(self.scores["original_risk_category"]) <= allowed)
        self.assertTrue(set(self.scores["final_risk_category"]) <= allowed)
        for _, row in self.scores.iterrows():
            self.assertEqual(row["original_risk_category"], classify_risk(row["overall_risk_score"]))
            self.assertEqual(row["escalation_occurred"],
                             row["final_risk_category"] != row["original_risk_category"])

    def test_known_plus_unknown_is_six_and_confidence_matches(self):
        self.assertTrue((self.scores["known_factor_count"] + self.scores["unknown_factor_count"] == 6).all())
        for _, row in self.scores.iterrows():
            known = [n for n in row["known_factors"].split("; ") if n]
            expected = sum(FACTOR_WEIGHTS[n] for n in known)
            self.assertAlmostEqual(row["data_confidence_pct"], expected)

    def test_text_columns_agree_with_numeric_columns_for_every_supplier(self):
        # If supplier_risk.py's wording ever drifts, this notices it.
        self.assertFalse(self.scores["data_notes"].str.contains("does not match").any())

    def test_suppliers_without_material_mapping_keep_unknown_factors(self):
        unmapped = self.factors.loc[~self.factors["has_material_mapping"], "supplier_id"]
        result = self.scores.set_index("supplier_id")
        for supplier_id in unmapped:
            self.assertTrue(math.isnan(result.loc[supplier_id, "material_dependency_risk"]), supplier_id)
            self.assertTrue(math.isnan(result.loc[supplier_id, "inventory_risk"]), supplier_id)

    def test_weighted_score_can_be_recomputed_from_the_factor_columns(self):
        for _, row in self.scores.iterrows():
            known = [(row[n + "_risk"], FACTOR_WEIGHTS[n]) for n in FACTOR_WEIGHTS
                     if not math.isnan(row[n + "_risk"])]
            if not known:
                self.assertTrue(math.isnan(row["overall_risk_score"]))
                continue
            expected = sum(s * w for s, w in known) / sum(w for _, w in known)
            self.assertAlmostEqual(row["overall_risk_score"], expected, delta=0.06)  # factors shown rounded

    def test_input_table_is_unchanged(self):
        pd.testing.assert_frame_equal(self.factors, self.before)


if __name__ == "__main__":
    unittest.main()
