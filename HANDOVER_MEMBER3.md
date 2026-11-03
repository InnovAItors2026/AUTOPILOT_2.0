# HANDOVER_MEMBER3.md
# AUTOPILOT 2.0 — Member 3 Handover
## Backup Supplier Intelligence & Recovery Optimisation Engine

---

## What Was Built

Member 3 implemented `src/recovery_optimisation.py` — the core intelligence layer
that answers the question:

> "Our supplier has failed. Who else can supply this material, how much,
>  at what cost, how quickly, and with what risk?"

The module is fully integrated with Member 1's data loaders and graph, and with
Member 2's disruption simulation outputs.

---

## Files Created / Modified

| File | Change | Notes |
|---|---|---|
| `src/recovery_optimisation.py` | **Created** | Member 3's main module (~700 LOC) |
| `tests/test_recovery_optimisation.py` | **Created** | 66 automated tests |
| `src/__init__.py` | **Extended** | Exports Member 3 public API |
| `HANDOVER_MEMBER3.md` | **Created** | This file |

---

## Public API

### Primary entry point

```python
from src.recovery_optimisation import optimise_recovery

plan = optimise_recovery(
    material_id="MAT-02",           # Material to re-source
    required_quantity=1000.0,        # Units needed
    failed_supplier_ids=["SUP-T1-03"],  # From Member 2's disruption report
    destination_ids=["FAC-01"],      # Optional: factories/warehouses to reach
    original_supplier_id="SUP-T1-03",  # Optional: for cost delta calculation
    data=None,   # Optional: dict from load_all_data(); loaded internally if None
    graph=None,  # Optional: graph from get_supply_chain_graph(); built if None
    weights=None # Optional: dict of scoring weights (see DEFAULT_WEIGHTS)
)
```

### Member 2 wrapper

```python
from src.recovery_optimisation import optimise_from_disruption_report

# Accepts output of simulate_supplier_disruption() or
# simulate_multiple_supplier_disruption() directly.
plan = optimise_from_disruption_report(
    disruption_report=member2_report,
    material_id="MAT-02",
    required_quantity=1000.0,
)
```

### Individual component functions (also exported)

| Function | Purpose |
|---|---|
| `classify_supplier(sid, mid, lookups)` | Task 1: PRIMARY/BACKUP/SECONDARY/EMERGENCY |
| `check_material_compatibility(sid, mid, lookups)` | Task 2: hard gate |
| `assess_feasibility(sid, mid, qty, lookups, missing)` | Task 3: stock + capacity |
| `assess_cost_and_delivery(sid, mid, orig_sid, lookups, missing)` | Task 4: cost + lead time |
| `assess_transport(sid, dests, lookups, graph, missing)` | Task 5: route check |
| `assess_upstream_dependency(sid, failed, graph, missing)` | Task 6: shared upstream |
| `rank_candidates(candidates, qty, weights)` | Task 7: weighted scoring |
| `allocate_quantity(ranked, qty)` | Task 8: greedy MOQ-safe allocation |

---

## Return Value Schema (Task 11)

`optimise_recovery()` returns a JSON-serialisable dict:

```json
{
  "material_id": "MAT-02",
  "required_quantity": 1000,
  "failed_supplier_ids": ["SUP-T1-03"],
  "original_supplier_id": "SUP-T1-03",

  "candidate_evaluation": [
    {
      "supplier_id": "SUP-T1-04",
      "supplier_name": "WesternCell Packs",
      "supplier_classification": "BACKUP",
      "tier": 1,
      "material_compatible": true,
      "feasibility_status": "FEASIBLE",
      "quantity_available": 5000,
      "quantity_to_allocate": 1000,
      "moq_units": 200,
      "unit_cost_inr": 645,
      "lead_time_days": 9,
      "additional_cost_per_unit_inr": 25,
      "transport_status": "UNKNOWN",
      "dependency_status": "SHARED_UPSTREAM",
      "shared_upstreams": ["SUP-T2-01"],
      "quality_score": 94,
      "ranking_score": 68.33,
      "rejection_reason": null,
      "dependency_reason": "SUP-T1-04 shares upstream with failed: SUP-T2-01"
    }
  ],

  "recommended_plan": { ... },
  "lowest_cost_plan": { ... },
  "fastest_plan": { ... }
}
```

### Plan schema (each of the three plans)

```json
{
  "material_id": "MAT-02",
  "required_quantity": 1000,
  "allocated_quantity": 1000,
  "unmet_quantity": 0,
  "status": "FEASIBLE",
  "optimization_objective": "BALANCED",
  "selected_suppliers": [
    {
      "supplier_id": "SUP-T1-04",
      "supplier_name": "WesternCell Packs",
      "supplier_classification": "BACKUP",
      "allocated_quantity": 1000,
      "unit_cost_inr": 645,
      "lead_time_days": 9,
      "additional_cost_per_unit_inr": 25,
      "transport_status": "UNKNOWN",
      "dependency_status": "SHARED_UPSTREAM",
      "reachable_routes": [],
      "shared_upstreams": ["SUP-T2-01"],
      "ranking_score": 68.33
    }
  ],
  "total_procurement_cost_inr": 645000,
  "effective_delivery_days": 9,
  "missing_information": [],
  "rejected_candidates": [],
  "warnings": [],
  "selection_explanation": "BALANCED plan: 1 supplier(s), 1000 units fully allocated."
}
```

### Status values

| Status | Meaning |
|---|---|
| `FEASIBLE` | 100% of required quantity allocated |
| `PARTIAL_RECOVERY` | Some quantity allocated; `unmet_quantity > 0` |
| `NO_FEASIBLE_PLAN` | No eligible supplier found |
| `EMERGENCY_RECOVERY` | Allocated using shared-upstream candidates |

---

## Task Implementation Map

| Task | Status | Notes |
|---|---|---|
| Task 1: Supplier classification | ✅ Complete | Uses `is_backup` from supplier_materials.csv |
| Task 2: Material compatibility | ✅ Complete | Hard gate; no capacity inference |
| Task 3: Stock & capacity feasibility | ✅ Complete | UNKNOWN ≠ zero; MOQ enforced |
| Task 4: Cost & delivery | ✅ Complete | UNKNOWN when missing; delta vs original |
| Task 5: Transport availability | ✅ Complete | Graph + CSV fallback; UNKNOWN when missing |
| Task 6: Shared upstream check | ✅ Complete | Uses Member 1's find_upstream_dependencies() |
| Task 7: Candidate ranking | ✅ Complete | Configurable weights; re-normalises on missing data |
| Task 8: Multi-supplier allocation | ✅ Complete | Greedy, MOQ-safe, stops at required quantity |
| Task 9: Recovery optimisation | ✅ Complete | Three variants: BALANCED, LOWEST_COST, FASTEST |
| Task 10: Emergency mode | ✅ Complete | Activated when normal recovery is insufficient |
| Task 11: Structured output | ✅ Complete | JSON-serialisable; schema documented above |
| Task 12: (not in scope per brief) | — | — |
| Task 13: Member 2 integration | ✅ Complete | `optimise_from_disruption_report()` wrapper |
| Task 14: Error handling | ✅ Complete | All inputs validated; missing data flagged |
| Task 15: Automated tests | ✅ Complete | 66 tests; 100% pass rate |

---

## Integration Guide

### For Member 4 (Cascading Failure & Recovery Plan Challenger)

```python
from src.recovery_optimisation import optimise_recovery

# 1. Get initial plan from Member 3.
plan = optimise_recovery(
    material_id="MAT-02",
    required_quantity=1000,
    failed_supplier_ids=["SUP-T1-03"],
)

# 2. Inspect the selected suppliers for the recommended plan.
selected = plan["recommended_plan"]["selected_suppliers"]
# → [{"supplier_id": "SUP-T1-04", "allocated_quantity": 1000, ...}]

# 3. Check shared_upstreams to simulate cascading failure.
for s in plan["candidate_evaluation"]:
    if s["dependency_status"] == "SHARED_UPSTREAM":
        print(s["supplier_id"], "shares:", s["shared_upstreams"])

# 4. If challenger finds an additional failure, re-optimise.
updated_plan = optimise_recovery(
    material_id="MAT-02",
    required_quantity=1000,
    failed_supplier_ids=["SUP-T1-03", "SUP-T1-04"],  # both now failed
)
```

### For Member 5 (Streamlit Frontend)

```python
import json
from src.recovery_optimisation import optimise_recovery

plan = optimise_recovery("MAT-02", 1000, ["SUP-T1-03"])

# The result is always JSON-serialisable.
json_str = json.dumps(plan, indent=2)

# Key fields for UI cards:
rec = plan["recommended_plan"]
st.metric("Status", rec["status"])
st.metric("Allocated", rec["allocated_quantity"])
st.metric("Unmet", rec["unmet_quantity"])
st.metric("Cost (INR)", rec["total_procurement_cost_inr"])
st.metric("Delivery (days)", rec["effective_delivery_days"])

# Supplier table:
st.dataframe(rec["selected_suppliers"])

# Candidate evaluation table (all ranked candidates):
st.dataframe(plan["candidate_evaluation"])
```

---

## Scoring Weights (Task 7)

The `DEFAULT_WEIGHTS` dict controls candidate ranking. All weights together
must sum to 1.0. They can be overridden by passing a `weights` argument.

| Weight key | Default | What it measures |
|---|---|---|
| `material_ok` | 0.30 | Hard gate: incompatible supplier = score 0 |
| `feasibility` | 0.20 | Can the supplier supply the required quantity? |
| `delivery_time` | 0.20 | Shorter lead time = higher score |
| `unit_cost` | 0.15 | Lower cost = higher score |
| `independence` | 0.10 | No shared upstream dependency |
| `transport` | 0.05 | Verified route to destination |

---

## Design Decisions and Constraints

### Missing data is never treated as zero or unlimited
Following the principle established by Members 1 and 2: when a value is absent
from the dataset, it is reported as `UNKNOWN`. Feasibility with unknown capacity
and stock is `FEASIBILITY_UNKNOWN`. Unknown cost/lead time is excluded from the
weighted score (remaining weights re-normalise). An unknown transport route does
not give `TRANSPORT_UNAVAILABLE` — it gives `TRANSPORT_UNKNOWN`.

### Hard constraints before ranking
Material compatibility (Task 2), MOQ, and explicit `capacity_status=insufficient`
are all enforced as hard gates before any scoring. A supplier that violates these
constraints gets `ranking_score = 0.0` and is excluded from allocation.

### Emergency mode (Task 10) rules
- Only activates when normal-mode produces a `PARTIAL_RECOVERY` or `NO_FEASIBLE_PLAN`.
- Relaxes the shared-upstream exclusion (includes `DEP_SHARED_UPSTREAM` candidates).
- Never relaxes: material compatibility, MOQ, `INFEASIBLE` feasibility,
  `DEP_DIRECTLY_AFFECTED` dependency.
- Tags every emergency allocation with `emergency_mode: true` in the output.
- Issues explicit `EMERGENCY:` warnings for each shared-upstream candidate used.

### No circular imports
This module imports FROM `supplier_risk`, `disruption_impact`, and
`supply_chain_graph`. These modules must NOT import from `recovery_optimisation`
to avoid circular dependency.

---

## Known Limitations

1. **Transport routes are supplier-node-based only.** The graph currently has
   `uses_route` edges from supplier nodes. Suppliers whose routes are only
   listed in `transport_routes.csv` by city/state (not by supplier_id as
   origin_id) will return `TRANSPORT_UNKNOWN`, not `TRANSPORT_AVAILABLE`.

2. **Stock pooling is global (all locations).** Inventory is summed across all
   factories and warehouses for a material. Per-location stock is not broken
   down per supplier assignment. This is the same approach used by Member 2.

3. **No real-time capacity updates.** Monthly capacity from `supplier_materials.csv`
   does not account for orders already placed with the same supplier. If the
   same supplier is serving multiple disruptions simultaneously, capacity could
   be over-counted.

4. **MOQ enforcement is partial-allocation aware.** When a supplier can only
   provide a fraction of the remaining demand and that fraction is below MOQ,
   the supplier is skipped. This may leave small unmet residuals even when
   total capacity exceeds demand.

---

## Testing

```powershell
# Run Member 3 tests only
python -m pytest tests/test_recovery_optimisation.py -v

# Run all tests (Members 1, 2, 3)
python -m pytest tests/ -v

# Quick CLI smoke test with real data
python -m src.recovery_optimisation MAT-02 1000 SUP-T1-03
```

Test coverage breakdown:

| Test Class | Tests | Coverage |
|---|---|---|
| `TestSupplierClassification` | 4 | Task 1 |
| `TestMaterialCompatibility` | 3 | Task 2 |
| `TestFeasibility` | 6 | Task 3 |
| `TestCostAndDelivery` | 4 | Task 4 |
| `TestTransportation` | 2 | Task 5 |
| `TestUpstreamDependency` | 4 | Task 6 |
| `TestRanking` | 4 | Task 7 |
| `TestQuantityAllocation` | 6 | Task 8 |
| `TestOptimiseRecovery` | 10 | Task 9 (integration) |
| `TestEmergencyRecovery` | 2 | Task 10 |
| `TestSerialisation` | 4 | Task 11 |
| `TestMember4Integration` | 4 | Task 13 |
| `TestEdgeCasesAndErrors` | 8 | Task 14 |
| `TestRealDataset` | 5 | Real-data smoke tests |
| **Total** | **66** | **All tasks** |

---

## Verified Real-Data Behaviour

Verified against the actual project dataset (`data/*.csv`):

| Scenario | Result |
|---|---|
| MAT-02 (Battery pack): SUP-T1-03 fails | SUP-T1-04 selected as BACKUP, FEASIBLE |
| MAT-03 (OLED display): SUP-T1-01 fails | SUP-T1-02 selected as BACKUP, FEASIBLE (6000 cap > 5000 req) |
| MAT-03: Both OLED suppliers fail | NO_FEASIBLE_PLAN (no candidates remain) |
| SUP-T1-04 when SUP-T1-03 fails | SHARED_UPSTREAM via SUP-T2-01 correctly detected |
| Result serialisation | 100% JSON-serialisable (no numpy types, no NaN in output) |

---

*Handover completed by Member 3.*
*AUTOPILOT 2.0 — "Predict the failure. Challenge the backup. Prepare for the next disruption."*
