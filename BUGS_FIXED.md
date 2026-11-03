# AUTOPILOT 2.0 — Bugs Fixed & Remediation Code Log

**Audit Role:** Senior Full-Stack Developer & Software Security Auditor  
**Scope:** Root-Cause Fixes, Code Diffs, Regression Verification  
**Total Bugs Fixed:** 5 (100% of Identified Bugs)  
**Regression Test Status:** 375/375 Passing Unit Tests

---

## 1. Fix for BUG-01: AI Explanations Nested Metric Extraction

**Target File:** `src/pipeline.py`  
**Patch Applied:**
```python
# Before:
# financial_exposure = disruption_report.get("combined_potential_financial_exposure_inr", disruption_report.get("potential_financial_exposure_inr", 0))
# affected_orders = disruption_report.get("affected_customer_orders", [])
# order_count = len(affected_orders)

# After (Fixed):
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
double_count_avoided = (
    _overlap.get("order_count_overlap_avoided")
    or disruption_report.get("double_counting_avoided")
    or 0
)
```
**Verification:** Narrative now outputs: `Incident: Disruption at DeccanCell Packs (SUP-T1-03) risking ₹73,418,850.00 across 16 customer orders.`

---

## 2. Fix for BUG-02: Multi-Supplier Disruption Type Sanitization

**Target File:** `src/pipeline.py`  
**Patch Applied:**
```python
# Before:
# for sid in failed_sids:
#     match = risk_scores_df[risk_scores_df["supplier_id"] == sid]

# After (Fixed):
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

# Handled NoneType procurement cost for infeasible recovery plans
cost = rec_plan.get("total_procurement_cost_inr", 0) or 0
allocated_qty = rec_plan.get("allocated_quantity", 0) or 0
req_qty = rec_plan.get("required_quantity", 0) or 0
```
**Verification:** Multi-supplier pipeline `['SUP-T2-01', 'SUP-T2-03']` completes successfully without exceptions.

---

## 3. Fix for BUG-03: Dashboard Tab 3 Impact Metric Extraction

**Target File:** `app.py`  
**Patch Applied:**
```python
# Before:
# fin_exp = dis_res.get("combined_potential_financial_exposure_inr", dis_res.get("potential_financial_exposure_inr", 0))
# orders_exp = dis_res.get("affected_customer_orders", [])
# ... st.metric("Exposed Customer Orders", len(orders_exp))

# After (Fixed):
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

# ...
with mc1:
    st.metric("Potential Financial Exposure", f"₹{float(fin_exp or 0):,.2f}")
with mc2:
    st.metric("Exposed Customer Orders", orders_exp_count)
with mc4:
    st.metric("Double-Counting Avoided", f"{overlap_avoided} orders")
```
**Verification:** Browser automation confirms cards display `₹73,418,850.00` and `16` exposed customer orders.

---

## 4. Fix for BUG-04: SAP HANA Cloud Column Header Normalization

**Target File:** `src/data_loader.py`  
**Patch Applied:**
```python
# Before:
# table_data = client.execute_read_query(query)
# if not isinstance(table_data, pd.DataFrame):
#     table_data = pd.DataFrame(table_data)
# data[key] = table_data

# After (Fixed):
table_data = client.execute_read_query(query)
if not isinstance(table_data, pd.DataFrame):
    table_data = pd.DataFrame(table_data)

# Normalize column names to lowercase snake_case
table_data.columns = [str(c).strip().lower() for c in table_data.columns]
data[key] = table_data
```
**Verification:** Calling `build_supply_chain_graph(data)` with HANA data constructs all **91 nodes and 528 edges**.

---

## 5. Fix for BUG-05: HANAClient Explicit Parameter Disambiguation

**Target File:** `src/integration/hana_client.py`  
**Patch Applied:**
```python
# Before:
# self.host = (host or os.environ.get("HANA_HOST", "")).strip()
# self.user = (user or os.environ.get("HANA_USER", "")).strip()
# self._password = password or os.environ.get("HANA_PASSWORD", "")

# After (Fixed):
self.host = (host if host is not None else os.environ.get("HANA_HOST", "")).strip()
port_val = port if port is not None else os.environ.get("HANA_PORT", "443")
self.user = (user if user is not None else os.environ.get("HANA_USER", "")).strip()
self._password = password if password is not None else os.environ.get("HANA_PASSWORD", "")
```
**Verification:** Running `python -m unittest discover` passes 375/375 tests, including `test_missing_config_reporting`.

