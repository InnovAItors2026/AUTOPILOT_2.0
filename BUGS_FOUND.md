# AUTOPILOT 2.0 — Bugs Found During Independent Audit

**Audit Role:** Senior QA Engineer, Full-Stack Developer & Software Security Auditor  
**Scope:** Automated Cold Testing, Live SAP HANA Integration, Browser Interaction Auditing  
**Total Bugs Identified:** 5

---

## 1. BUG-01: AI Explanations Displayed ₹0.00 Financial Exposure and 0 Affected Orders
- **Severity:** MEDIUM
- **Affected File:** `src/pipeline.py` (lines 207–213)
- **Component:** Member 5 Pipeline Orchestration / AI Briefing Generator
- **Reproduction Steps:**
  1. Call `run_full_resilience_pipeline(failed_supplier_ids=['SUP-T1-03'])`.
  2. Inspect returned `ai_explanations['executive_summary']` or `disruption_narrative`.
  3. Observe that text states: `Incident: Disruption at ... risking ₹0.00 across 0 customer orders.`
- **Root Cause:** `generate_ai_explanations()` attempted to extract exposure metrics from flat dictionary keys (`combined_potential_financial_exposure_inr`, `potential_financial_exposure_inr`, `affected_customer_orders`). In Member 2's simulation output, these metrics are nested inside `disruption_report["summary"]["headline_potential_order_value_exposure_inr"]` and `disruption_report["summary"]["headline_order_count"]`.

---

## 2. BUG-02: Pipeline Crash on Multi-Supplier Disruption
- **Severity:** HIGH
- **Affected File:** `src/pipeline.py` (lines 198–202 and line 270)
- **Component:** Member 5 Pipeline Orchestration / Multi-Supplier Failure Path
- **Reproduction Steps:**
  1. Call `run_full_resilience_pipeline(failed_supplier_ids=['SUP-T2-01', 'SUP-T2-03'])`.
  2. Observe crash: `NotImplementedError: eq not implemented for <class 'dict'>`.
  3. If sid is handled, observe secondary crash: `TypeError: unsupported format string passed to NoneType.__format__`.
- **Root Cause:**
  1. In multi-disruption reports, `failed_suppliers` is a list of dictionary metadata objects, not a list of string IDs. The loop passed dict objects into `risk_scores_df["supplier_id"] == sid`, causing pyarrow / pandas Series comparison to raise `NotImplementedError`.
  2. In cases where the recovery plan is infeasible (`NO_FEASIBLE_PLAN`), `total_procurement_cost_inr` is `None`. The format expression `f"₹{cost:,.2f}"` raised `TypeError`.

---

## 3. BUG-03: Streamlit Tab 3 UI Metric Cards Displayed ₹0.00 and 0 Orders
- **Severity:** MEDIUM
- **Affected File:** `app.py` (lines 1445–1489)
- **Component:** Streamlit Dashboard Tab 3 (Disruption Impact Simulator UI)
- **Reproduction Steps:**
  1. Open AUTOPILOT 2.0 dashboard at `http://localhost:8501`.
  2. Navigate to Tab 3 (Disruption Impact Simulator).
  3. Click `🚀 Run Disruption Simulation`.
  4. Observe that the top metric cards showed `₹0.00` Potential Financial Exposure and `0` Exposed Customer Orders, even though the tables below showed disrupted entities.
- **Root Cause:** Tab 3 read flat keys `dis_res.get("combined_potential_financial_exposure_inr")` and `len(dis_res.get("affected_customer_orders", []))`, which do not exist at the top level of the disruption report.

---

## 4. BUG-04: SAP HANA Cloud Uppercase Column Headers Generated Empty Graph
- **Severity:** HIGH
- **Affected File:** `src/data_loader.py` (lines 285–295)
- **Component:** Member 1 Data Management / SAP HANA Cloud Integration
- **Reproduction Steps:**
  1. Set `DATA_SOURCE=hana` in `.env`.
  2. Call `data = load_all_data(source='hana')`.
  3. Call `graph = build_supply_chain_graph(data)`.
  4. Observe: `graph.number_of_nodes() == 0` and `graph.number_of_edges() == 0`.
- **Root Cause:** `hdbcli` returns table column names in uppercase (`SUPPLIER_ID`, `MATERIAL_ID`, `TIER`). The graph builder expects lowercase snake_case (`row.get("supplier_id")`). Because all lookups returned `None`, no nodes or edges were added.

---

## 5. BUG-05: HANAClient Falsy Fallback Blocked Explicit Empty Parameter Unit Tests
- **Severity:** LOW
- **Affected File:** `src/integration/hana_client.py` (lines 50–60)
- **Component:** SAP HANA Client Parameter Initialization
- **Reproduction Steps:**
  1. Create `.env` file with real `HANA_HOST` and `HANA_USER`.
  2. Run `test_hana_client.py::test_missing_config_reporting`.
  3. Observe failure: `AssertionError: 'HANA_HOST' not found in []`.
- **Root Cause:** `self.host = (host or os.environ.get("HANA_HOST", "")).strip()` evaluates `host=""` as falsy, falling back to the `.env` value instead of honoring the explicitly passed empty string.

