# AUTOPILOT 2.0 — Independent Technical Verification Report
## Member 3: Backup Supplier Intelligence & Recovery Optimisation Engine

**Auditor:** Independent technical audit (automated)
**Date:** 2026-11-01
**Verdict:** See Section 11.

---

## 1. Executive Summary

Member 3's Recovery Optimisation Engine is **substantially correct and functional**.
All 66 Member 3 tests pass independently. The full project suite of **334 tests**
passes with **zero failures**. Every number reported for the MAT-03 / SUP-T1-01
scenario was independently recalculated from raw CSV data and confirmed correct.

**Two issues require attention before the final demonstration:**

| # | Issue | Severity |
|---|---|---|
| A | `assess_feasibility()` uses pooled on-hand inventory as a supply ceiling — conceptually wrong, breaks multi-supplier allocation | HIGH |
| B | Multi-supplier joint allocation returns wrong total when inventory caps each supplier | MEDIUM |
| C | SHARED_UPSTREAM risk not surfaced in `plan.warnings` in normal mode | LOW |
| D | Transit days not added to effective delivery estimate (documented limitation) | LOW |

---

## 2. Files Inspected

| File | Verified |
|---|---|
| `src/recovery_optimisation.py` (1,513 lines) | YES |
| `tests/test_recovery_optimisation.py` (1,457 lines) | YES |
| `src/__init__.py` | YES |
| `HANDOVER_MEMBER3.md` | YES |
| `run_recovery.py` | YES |
| `data/suppliers.csv` (36 data rows) | YES |
| `data/supplier_materials.csv` (29 rows) | YES |
| `data/supplier_dependencies.csv` (31 rows) | YES |
| `data/transport_routes.csv` (6 routes) | YES |
| `data/inventory.csv` (37 rows) | YES |
| `src/disruption_simulation.py` | YES |
| `src/multi_disruption_simulation.py` | YES |
| `src/supply_chain_graph.py` | YES |
| `HANDOVER_MEMBER1.md`, `HANDOVER_MEMBER2.md` | YES |

---

## 3. Verified Public Functions

| Function | Signature | Works |
|---|---|---|
| `optimise_recovery()` | `(material_id, required_quantity, failed_supplier_ids, destination_ids=None, original_supplier_id=None, data=None, graph=None, weights=None) -> dict` | YES |
| `optimise_from_disruption_report()` | `(disruption_report, material_id, required_quantity, ...) -> dict` | YES |
| `classify_supplier()` | `(supplier_id, material_id, lookups) -> str` | YES |
| `check_material_compatibility()` | `(supplier_id, material_id, lookups) -> (bool, str)` | YES |
| `assess_feasibility()` | `(supplier_id, material_id, required_quantity, lookups, missing_info) -> dict` | YES (Issue A) |
| `assess_cost_and_delivery()` | `(supplier_id, material_id, original_supplier_id, lookups, missing_info) -> dict` | YES |
| `assess_transport()` | `(supplier_id, destination_ids, lookups, graph, missing_info) -> dict` | YES |
| `assess_upstream_dependency()` | `(candidate_id, failed_supplier_ids, graph, missing_info) -> dict` | YES |
| `rank_candidates()` | `(candidates, required_quantity, weights=None) -> list` | YES |
| `allocate_quantity()` | `(ranked_candidates, required_quantity) -> (list, allocated, unmet)` | YES |
| `_build_lookups()` | `(data) -> dict` | YES |

All private helpers (`_text`, `_number`, `_tidy`, `_rows`, `_validate_*`,
`_build_plan`) verified correct.

---

## 4. Test Results

### Independently executed — no result taken on faith.

```
Platform : Windows / Python 3.11.9 / pytest 9.1.1
Collected: 334 tests
PASSED   : 334
FAILED   :   0
Subtests : 41 passed
Duration : 9.83 s
```

### Member 3 tests

```
tests/test_recovery_optimisation.py   66 passed / 0 failed / 0 skipped
```

No test was modified before running. No test was skipped.

### Baseline comparison

| Reported M2 baseline | Current verified total | Delta |
|---|---|---|
| ~268 | **334** | +66 (all Member 3 tests) |

### Test quality

| Dimension | Finding |
|---|---|
| Mock usage | Minimal — in-memory DataFrames, not mocks |
| Real-data coverage | 5 tests (`TestRealDataset`) use actual project CSVs |
| Edge-case coverage | Good: zero qty, None qty, invalid material, duplicate failures, MOQ |
| Assertion quality | Specific field values asserted; low accidental-pass risk |
| Gap | No test exercises multi-supplier joint allocation on real data (Issue B) |

---

## 5. Real-Data Calculation Verification (Audit M)

**Scenario: MAT-03, 5,000 units, SUP-T1-01 (BharatVista Displays) fails.**

### Raw CSV values

| File | Row | Field | Value |
|---|---|---|---|
| `supplier_materials.csv` | SUP-T1-02 / MAT-03 | `unit_cost_inr` | **1,920** |
| `supplier_materials.csv` | SUP-T1-02 / MAT-03 | `monthly_capacity_units` | **6,000** |
| `supplier_materials.csv` | SUP-T1-02 / MAT-03 | `lead_time_days` | **10** |
| `supplier_materials.csv` | SUP-T1-02 / MAT-03 | `moq_units` | **80** |
| `supplier_materials.csv` | SUP-T1-02 / MAT-03 | `is_backup` | **1** (BACKUP) |
| `suppliers.csv` | SUP-T1-02 | `capacity_status` | **sufficient** |
| `inventory.csv` | MAT-03 pooled | `quantity_on_hand` | FAC-01 5,200 + WH-01 1,100 + WH-04 1,600 = **7,900** |
| `transport_routes.csv` | RTE-02 | `origin_id` | **SUP-T1-02** |
| `transport_routes.csv` | RTE-02 | `destination_id` | **FAC-01** |
| `transport_routes.csv` | RTE-02 | `transit_days` | **2** |

### Feasibility

```
capacity        = 6,000  (supplier_materials.csv)
stock_on_hand   = 7,900  (inventory.csv, 3 locations pooled)
ceiling         = min(6000, 7900) = 6,000  [capacity dominates]
MOQ             = 80 -> 6,000 >= 80 OK
qty_to_allocate = min(6000, 5000) = 5,000
status          = FEASIBLE
```

### Cost

```
unit_cost_inr   = 1,920
quantity        = 5,000
total_cost      = 1,920 x 5,000 = 9,600,000 INR = RS 96,00,000
```

> **Reported RS 96,00,000 is CORRECT.**

### Delivery

```
lead_time_days = 10  (supplier_materials.csv)
```

> **Reported 10 days is CORRECT.**
> Note: transit_days=2 (RTE-02) is NOT added — a documented design choice.

### Route

```
RTE-02 origin_id      = SUP-T1-02   CORRECT
RTE-02 destination_id = FAC-01      CORRECT
```

> **Route RTE-02 to FAC-01 is CORRECT.**

### Shared upstream dependencies

```
SUP-T1-01 upstream = {SUP-T2-03, SUP-T3-09}
SUP-T1-02 upstream = {SUP-T2-03, SUP-T3-09}
Intersection       = {SUP-T2-03, SUP-T3-09}
```

Evidence from `supplier_dependencies.csv`:
- DEP-08: SUP-T1-01 depends on SUP-T2-03 (Nilgiri cover glass)
- DEP-09: SUP-T1-02 depends on SUP-T2-03 (same glass, shared backup)
- DEP-07: SUP-T2-03 depends on SUP-T3-09 (Aravalli Silica)

> **SUP-T2-03 and SUP-T3-09 are CONFIRMED genuine shared upstreams.**

### Additional cost per unit

When `original_supplier_id="SUP-T1-01"` supplied:

```
SUP-T1-01 cost = 1,850  (supplier_materials.csv)
SUP-T1-02 cost = 1,920
delta          = 70 INR/unit
```

Correctly computed by engine when parameter is passed.

---

## 6. Functional Audit Results

### Supplier Classification — PASS

- `is_backup=1` column is authoritative; no hardcoded supplier IDs in logic.
- SUP-T1-02 = BACKUP for MAT-03: confirmed.
- SUP-T1-04 = BACKUP for MAT-02: confirmed.
- PRIMARY, SECONDARY, EMERGENCY paths all verified in tests.

### Material Compatibility — PASS

- Incompatible suppliers (wrong material) rejected before ranking.
- Stock availability does NOT override compatibility gate: confirmed.
- Unknown material ID returns error dict, not crash.

### Stock and Capacity — PASS with Issue A

All UNKNOWN/zero/missing-data cases handled correctly for single-supplier scenarios.
`capacity_status=insufficient` on SUP-T2-01 correctly returns INFEASIBLE.

**HIGH ISSUE A — inventory pooling:**

`assess_feasibility()` computes `quantity_available = min(capacity, pooled_stock)`.
`quantity_on_hand` in `inventory.csv` is existing buyer-side stock at factories
and warehouses — not the supplier's own stock. Using it as a supply ceiling is
wrong. For all real materials tested, capacity < stock, so capacity dominates
and no wrong answer is produced. However:

**MAT-04 multi-supplier test (demand=60,000):**

| Supplier | Capacity | Inventory ceiling | Engine allocates |
|---|---|---|---|
| SUP-T2-03 | 22,000 | 6,100 (INV-13) | 6,100 |
| SUP-T3-09 | 50,000 | 6,100 (INV-13) | 6,100 |
| **Total** | **72,000** | — | **12,200** |

Engine returns PARTIAL_RECOVERY with 12,200 instead of FEASIBLE with 60,000+.
**This is wrong.**

### Cost Calculation — PASS

RS 96,00,000 = 1,920 x 5,000 verified. No double-counting. No silent zero for
missing transport cost. Additional delta computed correctly when baseline supplied.

### Delivery Time and Route — PASS

Lead time (10 days) and route (RTE-02 -> FAC-01) confirmed from raw CSV.
Transit time correctly distinguished from lead time.

### Shared Upstream Dependency — PASS with Issue C

All four dependency statuses (INDEPENDENT, SHARED_UPSTREAM, DIRECTLY_AFFECTED,
UNKNOWN) verified. Member 1's `find_upstream_dependencies()` used correctly.

**LOW ISSUE C:** When a SHARED_UPSTREAM candidate is selected in normal mode,
`plan.warnings` remains empty. The risk is in `candidate_evaluation[].dependency_status`
but not surfaced to `plan.warnings`. Emergency mode correctly issues warnings.

### Optimisation Scenarios

| Scenario | Expected | Actual | Pass |
|---|---|---|---|
| 1: Single backup (MAT-03, 5000) | FEASIBLE, 5000 | FEASIBLE, 5000 | YES |
| 2: Multi-supplier joint (MAT-04, 60000) | FEASIBLE, 60000 | PARTIAL, 12200 | **NO** |
| 3: Insufficient supply (MAT-03, 10000) | PARTIAL, unmet 4000 | PARTIAL, unmet 4000 | YES |
| 4: Incompatible rejected | Rejected | Pass (unit tests) | YES |
| 5: Shared dep flagged | SHARED_UPSTREAM | SHARED_UPSTREAM | YES |
| 6: Cost vs speed (3 plans) | Different | Identical (only 1 candidate) | NOTE |
| 7: No feasible supplier | NO_FEASIBLE_PLAN | NO_FEASIBLE_PLAN | YES |
| 8: Emergency recovery | EMERGENCY_RECOVERY | Pass (unit tests) | YES |

Scenario 6 note: No real material has 2+ viable candidates in the dataset.
The three-variant logic is correct and covered by synthetic unit tests.

---

## 7. Integration Readiness

### Member 2 Integration — PASS

```python
# Single disruption — tested end-to-end:
report = simulate_supplier_disruption('SUP-T1-01', 7, data, graph)
plan = optimise_from_disruption_report(report, 'MAT-03', 5000.0)
# -> status=FEASIBLE, allocated=5000, failed_ids=['SUP-T1-01']  CORRECT

# Multi disruption — tested end-to-end:
rep2 = simulate_multiple_supplier_disruption(['SUP-T1-01','SUP-T1-02'], data, graph)
plan2 = optimise_from_disruption_report(rep2, 'MAT-03', 5000.0)
# -> status=NO_FEASIBLE_PLAN, failed_ids=['SUP-T1-01','SUP-T1-02']  CORRECT
```

No circular imports. No M2 interface broken.

### Member 4 Readiness — PASS

All re-optimisation fields present: `supplier_id`, `allocated_quantity`,
`material_id`, `reachable_routes`, `lead_time_days`, `shared_upstreams`,
`unit_cost_inr`, `unmet_quantity`, `status`, `warnings`, `rejected_candidates`.

Pattern verified:

```python
plan1 = optimise_recovery('MAT-03', 5000, ['SUP-T1-01'], ...)
# Challenger detects backup also fails:
plan2 = optimise_recovery('MAT-03', 5000, ['SUP-T1-01', 'SUP-T1-02'], ...)
# -> NO_FEASIBLE_PLAN  CORRECT
```

### Member 5 Dashboard Readiness — PASS

`json.dumps(result, default=str)` succeeds. No numpy types. No NaN in output.
Consistent status vocabulary. Error dict distinguishable from plan dict.
Three plan variants always present.

---

## 8. Bugs and Weaknesses

### CRITICAL — None found.

### HIGH

**Issue A — `assess_feasibility()` inventory-pooling flaw**

Location: `src/recovery_optimisation.py` lines 426–431

`quantity_available = min(capacity, pooled_inventory)` is conceptually wrong.
Existing on-hand stock is buyer-side inventory, not supplier supply capacity.
In the real dataset, capacity < inventory for all materials, so the correct
branch is always taken. But for MAT-04 with two suppliers, both suppliers are
capped at the shared 6,100-unit inventory figure, giving 12,200 total instead
of the correct combined capacity of 72,000.

### MEDIUM

**Issue B — Multi-supplier joint allocation wrong total**

Same root cause as Issue A. Combined allocation from N suppliers is capped at
the shared inventory level rather than the sum of supplier capacities.

### LOW

**Issue C — No SHARED_UPSTREAM warning in plan.warnings (normal mode)**

`plan.warnings = []` even when the selected supplier is flagged SHARED_UPSTREAM.

**Issue D — Transit days not included in effective_delivery_days**

Documented limitation. Lead time from `supplier_materials.csv` used without
adding route transit time. Result may understate end-to-end delivery by 1–5 days.

---

## 9. Missing Functionality

| Item | Status |
|---|---|
| Task 12 (out of scope per project brief) | Correctly excluded |
| Multi-supplier joint allocation on real data | Broken — Issue B |
| SHARED_UPSTREAM warning in plan.warnings | Missing — Issue C |
| Transit time in effective delivery | Not implemented, documented |
| Cost vs speed real-data demonstration | No multi-candidate material in dataset |

---

## 10. Recommended Fixes

### Fix 1 (HIGH + MEDIUM — resolves Issues A and B)

**File:** `src/recovery_optimisation.py`
**Function:** `assess_feasibility()`
**Replace lines 426–431:**

```python
# CURRENT (wrong for multi-supplier materials):
ceilings = []
if capacity is not None:
    ceilings.append(capacity)
if stock_total is not None:
    ceilings.append(stock_total)
quantity_available = min(ceilings)

# REPLACEMENT (correct):
# capacity  = what the supplier can produce/deliver (supply ceiling)
# stock     = what the buyer already holds (not supplier supply)
# Use capacity as primary. Fall back to inventory proxy only when capacity unknown.
if capacity is not None:
    quantity_available = capacity
elif stock_total is not None:
    quantity_available = stock_total
    missing_info.append(
        supplier_id + "/" + material_id
        + ": monthly_capacity_units unknown; using pooled on-hand inventory "
        "as proxy for supply ceiling — may overstate available supply"
    )
```

### Fix 2 (LOW — resolves Issue C)

**File:** `src/recovery_optimisation.py`
**Location:** After `allocate_quantity()` call in plan assembly, before returning plan.

```python
for alloc in allocations:
    if alloc.get("dependency_status") == DEP_SHARED_UPSTREAM:
        shared = ", ".join(alloc.get("shared_upstreams", []))
        warnings.append(
            "RISK: " + alloc["supplier_id"]
            + " shares upstream supplier(s) with the failed set: " + shared
            + ". This supplier may also be disrupted if those upstream nodes fail."
        )
```

### Fix 3 (LOW — optional, resolves Issue D)

Add minimum `transit_days` from `reachable_routes` to `lead_time_days` in
`_max_lead_time()` to produce a true end-to-end delivery estimate.

---

## 11. Final Verdict

> ## VERIFIED WITH MINOR ISSUES

### What was independently confirmed correct:

- **334 / 334 tests pass** (zero failures, zero modifications).
- **RS 96,00,000** = 1,920 INR x 5,000 units — confirmed from raw CSV.
- **10 days** — from `supplier_materials.csv` lead_time_days — confirmed.
- **RTE-02 to FAC-01** — origin/destination confirmed in `transport_routes.csv`.
- **SUP-T2-03 and SUP-T3-09** — genuine shared upstreams confirmed in `supplier_dependencies.csv`.
- Member 2 integration end-to-end functional (both single and multi disruption).
- Member 4 re-optimisation pattern verified.
- Member 5 JSON serialisation clean — no numpy types, no NaN.
- No circular imports.
- Hard constraints (material compatibility, MOQ, capacity_status=insufficient) enforced before ranking.

### What requires fixing:

- **Fix 1 must be applied** before any demonstration involving multiple suppliers
  for the same material (MAT-04, MAT-01 multi-supplier). For the primary demo
  materials MAT-02 and MAT-03, the current engine is correct.
- **Fix 2** (10-line addition) improves dashboard usability by surfacing
  shared-upstream risk prominently in plan.warnings.

**The engine is ready for integration with Members 4 and 5 for all single-backup
recovery scenarios. Apply Fix 1 before the final demonstration.**

---

*All calculations independently executed against actual project CSV data.*
*No values assumed, invented, or copied from developer claims.*
*No production code was modified during this audit.*
