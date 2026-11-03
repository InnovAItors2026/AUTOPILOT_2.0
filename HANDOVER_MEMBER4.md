# HANDOVER_MEMBER4.md
# AUTOPILOT 2.0 — Member 4 Handover
## Cascading Failure Simulation & Recovery Plan Challenger Engine

---

## What Was Built

Member 4 implemented `src/cascading_failure.py`. It answers:

> "Member 3 proposed a recovery plan. If a backup, emergency supplier,
> shared upstream node, or transport route also fails, what is still
> feasible — without writing a second optimiser?"

The module **reads** Member 1's data and graph, **reuses** Member 2
disruption simulation, **invalidates** affected allocations, and
**re-calls** Member 3 `optimise_recovery()` with the original material
ID and required quantity.

It does **not** rank candidates, allocate quantity, or run emergency
recovery. Those remain in `src/recovery_optimisation.py`.

---

## Files Created

| File | Change |
|---|---|
| `src/cascading_failure.py` | Created — Member 4 public API |
| `tests/test_cascading_failure.py` | Created — 31 automated tests |
| `HANDOVER_MEMBER4.md` | Created — this file |

Existing Member 1, 2 and 3 source files, tests, and CSV data were **not**
modified. `src/__init__.py` was **not** changed. Import Member 4 from
`src.cascading_failure`.

---

## Public API

```python
from src.cascading_failure import (
    detect_shared_upstream_dependencies,
    suppliers_using_route,
    simulate_route_failure,
    transport_excluded_suppliers,
    simulate_cascading_supplier_failures,
    invalidate_recovery_allocations,
    challenge_recovery_plan,
)
```

### 1. Shared upstream detection

```python
detect_shared_upstream_dependencies(graph, supplier_ids) -> dict
```

Uses Member 1 `find_upstream_dependencies()` (only `supplier_dependency`
edges). For each id:

| Field | Meaning |
|---|---|
| `in_graph` | Whether the id is a supplier node |
| `upstream_ids` | Ancestor supplier ids, or `UNKNOWN` if not in the graph |
| `depends_on` | Other ids in the same list that sit **upstream** of this one, or `UNKNOWN` |
| `shared_with` | `{other_id: [shared ancestor ids]}` |

A missing supplier is **not** treated as "no parents". `upstream_ids`
is `UNKNOWN`.

### 2. Route lookup and route-failure exposure

```python
suppliers_using_route(graph, route_id) -> list[str]
simulate_route_failure(route_id, data=None, graph=None) -> dict
transport_excluded_suppliers(graph, failed_route_ids) -> dict
```

`suppliers_using_route` follows `uses_route` edges into the route node.
A missing route returns `[]`.

`simulate_route_failure` returns `status="ROUTE_FAILED"` when the route
exists, or `status="UNKNOWN"` when it does not. Exposed suppliers and
origin/destination locations are listed. A failed route is **not** a
supplier shutdown.

`transport_excluded_suppliers` lists suppliers whose **every** graph
`uses_route` target is in the failed set. Suppliers with no `uses_route`
edges are not excluded (transport is UNKNOWN).

### 3. Cascading supplier simulation (Member 2 reuse)

```python
simulate_cascading_supplier_failures(
    supplier_ids, duration_days=7, data=None, graph=None
) -> dict
```

| Valid supplier count | Member 2 function |
|---|---|
| 1 | `simulate_supplier_disruption` |
| 2 or more | `simulate_multiple_supplier_disruption` |
| 0 | Member 2 is not called; `status` is `UNKNOWN` |

Unknown ids are listed in `unknown_supplier_ids` / `data_gaps` and are
never passed to Member 2 (which would raise `ValueError`).

### 4. Allocation invalidation (no re-optimisation)

```python
invalidate_recovery_allocations(
    recovery_plan,
    additional_failed_supplier_ids=None,
    failed_route_ids=None,
    graph=None,
) -> dict
```

Accepts the full `optimise_recovery()` dict or a single plan dict.
Works on a **copy**. An allocation is removed when:

- `supplier_id` is in the additional failed set (`FAILED_SUPPLIER`)
- the supplier depends on a newly failed supplier (`UPSTREAM_FAILURE`)
- every `reachable_routes` entry is a failed route (`ROUTE_FAILURE`)

If some routes remain, failed routes are stripped from the copy and the
allocation is kept. Totals are **summed from leftover rows**; Member 3
ranking / greedy allocation is not re-run.

### 5. Main entry: challenge a recovery plan

```python
challenge_recovery_plan(
    original_plan,
    additional_failed_supplier_ids=None,
    failed_route_ids=None,
    data=None,
    graph=None,
    weights=None,
    destination_ids=None,
) -> dict
```

`original_plan` should be the dict returned by `optimise_recovery()`
(preferred) or a single plan with `selected_suppliers`.

`destination_ids` is forwarded to Member 3. If omitted, Member 4 reuses a
`destination_ids` key already present on the original plan. Destinations are
never invented. `weights` and `original_supplier_id` are preserved the same way
(`weights` via the argument; `original_supplier_id` from the original plan).

Steps:

1. Deep-copy the original plan. Do not mutate graph, data, or input plan.
2. Validate extra supplier / route ids. Unknown ids stay `UNKNOWN`.
3. Detect shared upstream links among selected and failed suppliers.
4. Invalidate affected allocations on the copy.
5. Build `combined_failed_supplier_ids` = original failed set + valid extra
   failures + transport-excluded suppliers.
6. Call `optimise_recovery(material_id, required_quantity, combined_failed,
   destination_ids=..., original_supplier_id=..., weights=...)`
   using the **original** material id and required quantity. Quantity is
   never invented from inventory or orders.
7. Compare original recommended plan vs revised recommended plan.

---

## Return value of `challenge_recovery_plan()`

JSON-serialisable dict:

```text
material_id
required_quantity
destination_ids                         # forwarded to Member 3; may be null
original_failed_supplier_ids
additional_failed_supplier_ids          # as requested (may include UNKNOWN ids)
additional_failed_supplier_ids_valid
combined_failed_supplier_ids            # passed to Member 3
failed_route_ids
transport_excluded_supplier_ids
route_failure_reports[]
shared_upstream_dependencies            # detect_shared_upstream_dependencies()
invalidated_allocations[]
invalidated_plan                        # post-filter copy, not a new optimisation
original_plan                           # deep copy of the input
revised_plan                            # full Member 3 result
comparison
member2_disruption                      # status + summary only
dependency_warnings[]
data_gaps[]
```

### `comparison`

| Field | Meaning |
|---|---|
| `original_status` / `revised_status` | Member 3 status strings |
| `original_allocated` / `revised_allocated` | Units |
| `original_unmet` / `revised_unmet` | Units |
| `remaining_demand` | Original required quantity |
| `unmet_quantity` | From the revised recommended plan |
| `feasibility_changed` | `True`/`False`, or `UNKNOWN` |
| `suppliers_removed` / `suppliers_added` | Selected supplier id diffs |
| `revised_plan_available` | `False` if Member 3 was not re-called |

### Invalidation row

```text
supplier_id
allocated_quantity_removed
reason
reason_codes   # FAILED_SUPPLIER | UPSTREAM_FAILURE | ROUTE_FAILURE
```

---

## How Member 4 calls Member 3

```python
from src.recovery_optimisation import optimise_recovery
from src.cascading_failure import challenge_recovery_plan
from src.data_loader import load_all_data
from src.supply_chain_graph import get_supply_chain_graph

data = load_all_data(verbose=False)
graph = get_supply_chain_graph(data)

original = optimise_recovery(
    material_id="MAT-02",
    required_quantity=1000.0,
    failed_supplier_ids=["SUP-T1-03"],
    destination_ids=["FAC-01"],
    data=data,
    graph=graph,
)

challenged = challenge_recovery_plan(
    original_plan=original,
    additional_failed_supplier_ids=["SUP-T2-01"],  # shared upstream of the backup
    failed_route_ids=["RTE-03"],                   # optional
    destination_ids=["FAC-01"],                    # preserve Member 3 destinations
    data=data,
    graph=graph,
)

print(challenged["comparison"]["revised_status"])
print(challenged["comparison"]["unmet_quantity"])
print(challenged["dependency_warnings"])
```

Pass the same `data`, `graph`, optional `weights`, and optional
`destination_ids` that Member 3 used. Member 4 never mutates them.

Transport-excluded suppliers are added to `failed_supplier_ids` **only**
because Member 3 has no `failed_route_ids` argument and does not skip
`TRANSPORT_UNKNOWN` during allocation. Each such exclusion is labelled
`TRANSPORT EXCLUSION (not a confirmed supplier shutdown)`.

---

## Integration instructions for Member 5

1. Import from `src.cascading_failure`, not from `src`.
2. Always run Member 3 first, then pass that dict into
   `challenge_recovery_plan`.
3. Dashboard fields:
   - `comparison.original_status` vs `comparison.revised_status`
   - `comparison.unmet_quantity` and `comparison.remaining_demand`
   - `invalidated_allocations` (why the first plan broke)
   - `dependency_warnings` and `data_gaps`
   - `revised_plan["recommended_plan"]["selected_suppliers"]`
4. `json.dumps(challenged)` is safe for the UI.
5. Do not treat `member2_disruption.summary` financial figures as confirmed
   loss. Member 2 documents them as potential exposure.
6. Do not treat `transport_excluded_supplier_ids` as company failures.

CLI smoke (from the project root, uses live CSVs):

```powershell
python -m src.cascading_failure MAT-02 1000 SUP-T1-03
```

This builds an original plan, then challenges shared-upstream ancestors of
the selected suppliers if Member 3 reported any.

---

## Testing

```powershell
python -m pytest tests/test_cascading_failure.py -q
python -m pytest -q
```

| Test class | What it covers |
|---|---|
| `TestSharedUpstreamDetection` | Shared T2, shared T3, combined T2/T3, direct depends-on, unknown supplier |
| `TestRouteFailure` | uses_route lookup, unknown/empty route, exposure, transport exclusion |
| `TestCascadingSupplierSimulation` | 1 vs 2+ Member 2 dispatch, unknown ids |
| `TestInvalidateAllocations` | Failed supplier, upstream failure, route filter, UNKNOWN qty |
| `TestChallengeRecoveryPlan` | Re-opt to alternative, shared upstream, simultaneous extras, route exclusion, unknown extra id, JSON, single-plan dict, real `optimise_recovery` call, destination_ids forwarding |
| `TestImmutability` | Original plan, graph nodes/edges, and suppliers table unchanged |
| `TestRealDatasetSmoke` | Schema keys only; no hardcoded CSV answers |

Verified: **31 Member 4 tests passed**. Full project suite: **365 passed**
(baseline before Member 4: 334 passed, 41 subtests).

Synthetic graphs use `build_supply_chain_graph()` so `uses_route` edges match
production.

---

## Limitations

1. **Member 3 has no route-failure parameter.** Route challenges are mapped
   to `failed_supplier_ids` only for suppliers whose *entire* graph route
   set failed. A supplier with a remaining `uses_route` edge can still be
   selected even if one of its routes failed. Member 3 also does not echo
   `destination_ids` in its return dict; pass them into
   `challenge_recovery_plan(destination_ids=...)` to preserve transport
   reachability on the re-call.
2. **`primary_route_id` is a coarse logistics model.** Many live suppliers
   share factory routes. Failing one route can exclude several suppliers.
   That is route exposure, not proof they have shut down.
3. **Emergency mode can re-select `SHARED_UPSTREAM` candidates.** If the
   challenger did not add that shared ancestor to the failed set, Member 3
   may still use it. Pass the ancestor in `additional_failed_supplier_ids`
   to force `DEP_DIRECTLY_AFFECTED`.
4. **Required quantity is never inferred.** If the original plan has no
   numeric `required_quantity`, Member 3 is not re-called (`data_gaps`).
5. **Eight live Tier-3 suppliers have no `supplier_materials` row.** Member 2
   reports their materials as UNKNOWN. Member 4 preserves that.
6. **Duration is still a Member 2 scenario label.** Production days remaining
   and delivery delay stay NOT COMPUTED.
7. **The shared graph is a `DiGraph`.** Member 4 does not add edges. A second
   edge between the same nodes would overwrite the first if anyone else did.

---

## Design rules followed

- Do not duplicate Member 3 ranking, allocation, or emergency logic.
- Do not invent supplier IDs, capacities, costs, or routes.
- Do not hardcode dataset-specific answers in tests.
- Do not modify other members' production code or CSV data.
- Missing values stay `UNKNOWN`, never zero.

---

*Handover completed by Member 4.*
*AUTOPILOT 2.0 — Cascading Failure Simulation & Recovery Plan Challenger.*
