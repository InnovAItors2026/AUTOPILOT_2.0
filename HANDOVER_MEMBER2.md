# AUTOPILOT 2.0
## HANDOVER DOCUMENT – MEMBER 2
### Supplier Risk & Disruption Impact Analysis

**Project:** AUTOPILOT 2.0 – Resilient Supply Chain Prototype  
**Role:** Member 2 – Supplier Risk & Disruption Impact Analysis  
**Implementation Status:** Phase 1 and Phase 2 completed  
**Technology:** Python, Pandas, NetworkX

---

# 1. Introduction

Member 2 is responsible for analysing the impact of supplier disruptions on the supply chain.

The main objective is to identify critical suppliers, analyse supplier failures, determine affected materials and downstream entities, evaluate inventory availability, assess backup suppliers and calculate potential financial exposure.

Two major simulation capabilities have been developed:

1. Single Supplier Disruption Simulation.
2. Multiple Supplier Disruption Simulation.

These modules use Member 1's existing datasets and supply-chain digital twin.

# 2. Completed Responsibilities

The following tasks have been implemented:

1. Supplier risk identification and risk scoring.
2. Supplier disruption input handling.
3. Identification of failed suppliers and affected materials.
4. Identification of downstream suppliers.
5. Identification of affected factories and warehouses.
6. Identification of potentially affected customer orders.
7. Inventory availability and reorder-level analysis.
8. Backup supplier availability and capacity assessment.
9. Potential financial exposure calculation.
10. Multiple simultaneous supplier disruption analysis.
11. Detection of overlapping impacts and duplicate customer orders.
12. Formatted disruption impact reports.
13. JSON serialisation of simulation results.
14. Automated testing and validation.

# 3. Developed Python Modules

All modules are located inside the `src/` directory.

| File | Purpose |
|---|---|
| `disruption_impact.py` | Identifies downstream supplier dependencies and potential disruption impacts. |
| `supplier_risk.py` | Analyses supplier risk, backup availability and inventory pooling. |
| `risk_scoring.py` | Calculates weighted supplier risk scores and risk categories. |
| `disruption_simulation.py` | Performs single supplier disruption simulation. |
| `multi_disruption_simulation.py` | Performs simultaneous multiple supplier disruption simulation. |

Test file:

`tests/test_multi_disruption_simulation.py`

# 4. Phase 1 – Single Supplier Disruption Simulation

**Module:** `src/disruption_simulation.py`

This module analyses the impact of an individual supplier failure.

### Implemented functionality

- Accepts a supplier ID as disruption input.
- Identifies directly affected materials.
- Identifies potential cascading materials.
- Finds downstream suppliers.
- Evaluates backup supplier availability.
- Analyses inventory quantities against reorder levels.
- Identifies potentially affected factories and warehouses.
- Identifies potentially affected transportation routes.
- Finds affected customer orders.
- Calculates potential financial exposure.
- Generates a formatted disruption report.

### Main function

`simulate_supplier_disruption(supplier_id, duration_days=7, data=None, graph=None)`

### Report formatter

`format_disruption_report(report)`

### Example

```python
from src.disruption_simulation import (
    simulate_supplier_disruption,
    format_disruption_report
)

report = simulate_supplier_disruption(
    "SUP-T2-01",
    duration_days=7
)

print(format_disruption_report(report))
```

# 5. Phase 2 – Multiple Supplier Disruption Simulation

**Module:** `src/multi_disruption_simulation.py`

Phase 2 extends the single supplier simulation to handle multiple suppliers failing simultaneously.

### Implemented functionality

1. Accepts multiple failed supplier IDs.
2. Validates supplier IDs and disruption duration.
3. Identifies the union of downstream suppliers.
4. Identifies direct and potential cascading materials.
5. Removes duplicate entities.
6. Evaluates backup suppliers against combined disruption.
7. Checks backup independence from exposed suppliers.
8. Compares backup capacity with combined exposed capacity.
9. Analyses pooled inventory and reorder levels.
10. Identifies affected factories and warehouses.
11. Identifies potentially affected transportation routes.
12. Identifies unique affected customer orders.
13. Calculates combined potential financial exposure.
14. Prevents double-counting of overlapping orders.
15. Attributes impacts to failed suppliers.
16. Generates a formatted report.
17. Supports JSON serialisation.

### Main function

`simulate_multiple_supplier_disruption(supplier_ids, duration_days=7, data=None, graph=None)`

### Report formatter

`format_multi_disruption_report(report)`

### Example

```python
from src.multi_disruption_simulation import (
    simulate_multiple_supplier_disruption,
    format_multi_disruption_report
)

report = simulate_multiple_supplier_disruption(
    ["SUP-T2-01", "SUP-T2-03"],
    duration_days=7
)

print(format_multi_disruption_report(report))
```

### JSON serialisation

```python
import json

json_output = json.dumps(report)

print(json_output)
```

The simulation output is JSON serialisable without requiring a custom JSON encoder.

# 6. Important Feature – Overlapping Disruption Analysis

One of the major features developed in Phase 2 is overlap detection.

When multiple suppliers fail simultaneously, the same customer order may be affected by more than one supplier.

Simply adding individual disruption reports would count these orders multiple times.

The multiple supplier simulation calculates the union of affected orders instead.

### Real dataset demonstration

Failed suppliers:

- SUP-T2-01 – CellTech Hyderabad
- SUP-T2-03 – Nilgiri Cover Glass

| Metric | Result |
|---|---:|
| Individual order counts added together | 27 |
| Combined unique orders | 16 |
| Double-counting avoided | 11 |
| Combined potential financial exposure | ₹7,34,18,850 |
| Potential exposure avoided from double-counting | ₹5,14,84,500 |

This demonstrates why combined disruption analysis is more reliable than simply adding individual supplier impacts.

**Important:** Financial exposure represents potential order-value exposure, not confirmed financial loss.

# 7. Backup Supplier Assessment

The simulation evaluates whether an alternative supplier can mitigate a disruption.

Backup assessment considers:

- Supplier independence.
- Shared upstream dependencies.
- Whether the candidate is part of the affected chain.
- Monthly supplier capacity.
- Combined capacity requirements.
- Missing supplier capacity information.

Backup statuses:

- MITIGATED
- UNMITIGATED
- UNKNOWN
- NOT_EXPOSED

Phase 2 also checks whether a backup that works for an individual disruption remains sufficient when multiple suppliers fail simultaneously.

This is a backup feasibility assessment, not the complete recovery optimisation engine assigned to Member 3.

# 8. Inventory and Operational Impact

The modules analyse available inventory against reorder levels.

The analysis includes:

- Material-level inventory.
- Factory inventory.
- Warehouse inventory.
- Pooled inventory quantities.
- Inventory below reorder point.
- Potential shortage exposure.
- Attribution to failed suppliers.

Factories, warehouses and transportation routes are identified as potentially affected based on available dataset relationships.

They are not automatically assumed to have stopped operating or failed.

# 9. Data Limitations and Pending Dependencies

Some calculations cannot currently be completed because the existing dataset does not contain the required information.

### Production days remaining

**Status: NOT COMPUTED**

Required information:
- Daily material consumption.
- Production rates.
- Material usage per production unit.

### Delivery delay estimation

**Status: NOT COMPUTED**

Required information:
- Shipment schedules.
- Replenishment plans.
- Transit information.
- Expected delivery dates.

### Financial impact

**Status: PARTIALLY IMPLEMENTED**

Potential customer-order value exposure is calculated.

However, actual financial loss, penalties and recovery costs are not calculated.

### Frontend disruption alerts

**Status: BACKEND REPORT IMPLEMENTED; DASHBOARD INTEGRATION PENDING**

Member 2 generates formatted disruption reports and structured simulation results.

Member 5 is responsible for displaying these results through the Streamlit dashboard.

### Important rule

Missing information must be represented as UNKNOWN, PARTIAL or NOT COMPUTED where appropriate. Missing values must not be treated as zero.

# 10. Testing and Validation

Automated tests were executed for the completed implementation.

| Test category | Passed |
|---|---:|
| Original Phase 1 tests | 222 |
| Phase 2 tests | 46 |
| **Total** | **268** |

Final result:

**268 tests passed – 0 failures.**

### Commands to run tests

Run the Phase 2 tests:

```powershell
python -m unittest tests/test_multi_disruption_simulation.py -v
```

Run the complete project test suite:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Run the multiple supplier disruption simulation:

```powershell
python -m src.multi_disruption_simulation SUP-T2-01 SUP-T2-03
```

# 11. Integration Instructions for Other Members

### Member 1 – Data Management

Member 2 uses the existing data-loading and graph modules.

The commonly used functions are:

- `load_all_data()`
- `get_supply_chain_graph(data)`

The data and supplier IDs must remain consistent across all modules.

If production rates, material consumption and shipment schedules become available, Member 2 can extend the corresponding calculations.

### Member 3 – Backup Supplier Intelligence & Recovery Optimisation

Member 3 can use Member 2's disruption output to understand:

- Failed suppliers.
- Directly affected materials.
- Cascading materials.
- Inventory availability.
- Backup status.
- Combined capacity requirements.
- Affected factories and warehouses.
- Potentially affected orders.

Member 3 should implement the actual alternative supplier selection and recovery optimisation logic.

### Member 4 – Cascading Failure & Recovery Plan Challenger

Member 4 can use Member 2's multiple supplier disruption simulation to understand:

- Multiple failed suppliers.
- Downstream supplier dependencies.
- Direct and cascading materials.
- Potentially affected locations.
- Transport route exposure.
- Customer order exposure.

Member 4 should independently implement recovery plan stress-testing and the Recovery Plan Challenger.

### Member 5 – Frontend & Integration

Member 5 can integrate the following functions:

- `simulate_supplier_disruption()`
- `format_disruption_report()`
- `simulate_multiple_supplier_disruption()`
- `format_multi_disruption_report()`

The dashboard should display:

- Supplier risk levels.
- Disruption alerts.
- Affected materials.
- Inventory status.
- Backup supplier status.
- Affected factories and warehouses.
- Customer orders.
- Potential financial exposure.
- Combined disruption reports.

# 12. Important Implementation Rules

1. Reuse Member 1's existing dataset and digital twin.
2. Use the same supplier IDs across all modules.
3. Do not modify Member 1's original datasets unnecessarily.
4. Do not assume downstream suppliers have stopped operating.
5. Do not treat potential financial exposure as actual loss.
6. Do not invent production days or delivery delays.
7. Preserve UNKNOWN and NOT COMPUTED statuses.
8. Keep the existing Phase 1 and Phase 2 implementations compatible with other modules.
9. Do not duplicate customer orders when calculating combined exposure.

# 13. Final Deliverable

Member 2 has completed the core Supplier Risk & Disruption Impact Analysis engine.

The implementation includes supplier risk scoring, single supplier disruption analysis, multiple supplier disruption analysis, backup feasibility assessment, inventory impact analysis, cascading dependency identification, financial exposure calculation, overlap detection and formatted reports.

**Validation:** 268 automated tests passed.

**Pending:** Additional operational data for production and delivery estimates, and integration of disruption alerts into the Streamlit frontend.

---

**Member 2 – Supplier Risk & Disruption Impact Analysis**

**AUTOPILOT 2.0 – Resilient Supply Chain Prototype**