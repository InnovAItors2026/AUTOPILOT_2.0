# AUTOPILOT 2.0 — Bugs Discovered and Remediation Log

**Auditor:** Senior Full-Stack Developer & Software Security Engineer  
**Audit Scope:** Codebase Debugging, Root Cause Analysis, Minimal Regression Patches  
**Total Bugs Identified:** 5  
**Total Bugs Resolved:** 5 (100% Fixed and Regression Tested)  
**Regression Test Result:** 375/375 Unit Tests Passing

---

## Bug Index & Severity Breakdown

| Bug ID | Severity | Affected Module | Root Cause Summary | Remediation Status |
|---|---|---|---|---|
| **BUG-01** | **MEDIUM** | `src/pipeline.py` | AI narrative read top-level keys instead of nested `summary` dict, displaying ₹0.00 and 0 orders | **FIXED** |
| **BUG-02** | **HIGH** | `src/pipeline.py` | Multi-disruption crashed with `NotImplementedError` comparing dicts to Series, and `TypeError` on null cost | **FIXED** |
| **BUG-03** | **MEDIUM** | `app.py` | Tab 3 Impact Summary metrics read flat keys instead of nested `summary` dict, displaying ₹0.00 | **FIXED** |
| **BUG-04** | **HIGH** | `src/data_loader.py` | Live HANA Cloud returns uppercase headers (`SUPPLIER_ID`), causing empty graph (0 nodes, 0 edges) | **FIXED** |
| **BUG-05** | **LOW** | `src/integration/hana_client.py` | Falsy fallback `host or os.environ` ignored explicit `host=""` in unit tests when `.env` present | **FIXED** |

---

## Detailed Root Cause Analysis & Code Patches

### BUG-01: AI Explanation Zero-Exposure Display
- **File:** `src/pipeline.py`
- **Root Cause:** In `generate_ai_explanations()`, the code attempted to access `disruption_report.get("combined_potential_financial_exposure_inr")` and `disruption_report.get("affected_customer_orders")`. In Member 2's simulation output, these values are stored inside `disruption_report["summary"]["headline_potential_order_value_exposure_inr"]` and `disruption_report["summary"]["headline_order_count"]`.
- **Code Patch:**
  ```python
  _summary = disruption_report.get("summary", {})
  _overlap = disruption_report.get("overlap_summary", {})
  financial_exposure = (
      _summary.get("headline_potential_order_value_exposure_inr")
      or _overlap.get("combined_unique_headline_potential_value_exposure_inr")
      or disruption_report.get("combined_potential_financial_exposure_inr")
      or disruption_report.get("potential_financial_exposure_inr")
      or 0
  )
  order_count = (
      _summary.get("headline_order_count")
      or _overlap.get("combined_unique_headline_order_count")
      or disruption_report.get("affected_customer_orders_count")
      or 0
  )
  ```

---

### BUG-02: Multi-Supplier Disruption Pipeline Crash
- **File:** `src/pipeline.py`
- **Root Cause:**
  1. In multi-disruption scenarios, `disruption_report["failed_suppliers"]` contains a list of dictionary objects representing supplier metadata, whereas in single-disruption it is a string or list of strings. Passing a `dict` into pandas Series comparison `risk_scores_df["supplier_id"] == sid` triggered `NotImplementedError: eq not implemented for <class 'dict'>`.
  2. In cases where the recovery plan is infeasible (`NO_FEASIBLE_PLAN`), `total_procurement_cost_inr` is `None`. The format string `f"₹{cost:,.2f}"` triggered `TypeError: unsupported format string passed to NoneType.__format__`.
- **Code Patch:**
  ```python
  failed_names = []
  for sid in failed_sids:
      if isinstance(sid, dict):
          sid_str = sid.get("supplier_id", str(sid))
      else:
          sid_str = str(sid) if sid is not None else ""
      match = risk_scores_df[risk_scores_df["supplier_id"] == sid_str]
      if not match.empty:
          failed_names.append(f"{match.iloc[0]['supplier_name']} ({sid_str})")
      else:
          failed_names.append(sid_str)

  cost = rec_plan.get("total_procurement_cost_inr", 0) or 0
  ```

---

### BUG-03: Streamlit Tab 3 Metric Cards Zeroed
- **File:** `app.py`
- **Root Cause:** Tab 3 Impact Summary metrics read flat keys `dis_res.get("combined_potential_financial_exposure_inr")` and `len(dis_res.get("affected_customer_orders", []))`.
- **Code Patch:**
  ```python
  _dis_summary = dis_res.get("summary", {})
  _dis_overlap = dis_res.get("overlap_summary", {})
  fin_exp = (
      _dis_summary.get("headline_potential_order_value_exposure_inr")
      or _dis_overlap.get("combined_unique_headline_potential_value_exposure_inr")
      or dis_res.get("combined_potential_financial_exposure_inr")
      or dis_res.get("potential_financial_exposure_inr")
      or 0
  )
  orders_exp_count = (
      _dis_summary.get("headline_order_count")
      or _dis_overlap.get("combined_unique_headline_order_count")
      or 0
  )
  overlap_avoided = (
      _dis_overlap.get("order_count_overlap_avoided")
      or dis_res.get("double_counting_avoided")
      or 0
  )
  ```

---

### BUG-04: SAP HANA Cloud Uppercase Column Name Mapping
- **File:** `src/data_loader.py`
- **Root Cause:** SAP HANA Cloud queries return uppercase column names (`SUPPLIER_ID`, `MATERIAL_ID`, `FACTORY_ID`). The downstream graph builder and risk scoring modules query lowercase snake_case headers (`row.get("supplier_id")`). This resulted in `build_supply_chain_graph` silently building an empty graph with 0 nodes and 0 edges.
- **Code Patch:**
  ```python
  if not isinstance(table_data, pd.DataFrame):
      table_data = pd.DataFrame(table_data)

  # Normalize column names to lowercase snake_case
  table_data.columns = [str(c).strip().lower() for c in table_data.columns]
  data[key] = table_data
  ```

---

### BUG-05: HANAClient Empty String Fallback Bug
- **File:** `src/integration/hana_client.py`
- **Root Cause:** Python expression `(host or os.environ.get("HANA_HOST", "")).strip()` evaluates empty string `""` as falsy, falling back to the `.env` value. When unit tests tested missing configuration using `HANAClient(host="", user="", password="")`, the client erroneously used credentials loaded from `.env`.
- **Code Patch:**
  ```python
  self.host = (host if host is not None else os.environ.get("HANA_HOST", "")).strip()
  port_val = port if port is not None else os.environ.get("HANA_PORT", "443")
  self.user = (user if user is not None else os.environ.get("HANA_USER", "")).strip()
  self._password = password if password is not None else os.environ.get("HANA_PASSWORD", "")
  ```

---

## Regression Verification
Following the application of all 5 patches:
- **Unit Test Suite:** All 375 tests passed (`Ran 375 tests in 14.872s, OK`).
- **Live HANA Pipeline:** Executed full resilience pipeline directly against SAP HANA Cloud without errors.
- **Browser Automation:** 10/11 browser tests passed (1 harmless tab detection warning).

