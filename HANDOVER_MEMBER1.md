# AUTOPILOT 2.0 — Member 1 handover for Member 2

**From:** Member 1 (Data Management + Digital Twin)  
**To:** Member 2 (risk and impact analysis)

This file is the working contract for using Member 1's data and graph. Do not read CSV files yourself. Import the functions below from the `AUTOPILOT_2.0` project folder.

Member 1 does **not** score risk, estimate impact, simulate cascading failure, or optimise recovery. Those are Member 2. The network, tables, and dependency lookups are ready for you to build on.

---

## 1. What Member 1 already verified

These results were produced by running `validate_data.py`, `main.py`, and `py -3 -m unittest discover -s tests -v`:

| Check | Result |
|---|---|
| Unit tests | **10/10 passed** |
| Dataset validation | **no warnings, no errors, no unmapped materials** |
| Digital twin | **ran successfully** |
| Graph size | **91 nodes, 528 edges** |
| Master data | **35 suppliers, 18 materials, 3 factories, 4 warehouses, 6 routes, 25 customer orders** |
| Direct supplier dependencies | **31** |
| Suppliers with an upstream chain | **22** |
| Shared upstream example | **SUP-T2-03** connects **SUP-T1-01** and **SUP-T1-02** |

Node types in the live graph: 35 suppliers, 18 materials, 3 factories, 4 warehouses, 6 transport routes, 25 customer orders.

---

## 2. Install and run (from this folder)

```bash
cd C:\Users\bhovi\OneDrive\Desktop\AUTOPILOT_2.0
py -3 -m pip install -r requirements.txt
py -3 validate_data.py
py -3 main.py
py -3 -m unittest discover -s tests -v
```

Dependencies in `requirements.txt`: `pandas`, `networkx`.

Python imports only work if the current working directory is `AUTOPILOT_2.0`.

---

## 3. Dataset files

All files are in `data/`. `load_all_data()` returns them as a dictionary of pandas DataFrames. Dictionary keys are listed in **Key**.

| Key | File | Rows | Purpose |
|---|---|---|---|
| `suppliers` | `data/suppliers.csv` | 35 | Supplier master (tiers 10 / 13 / 12) |
| `materials` | `data/materials.csv` | 18 | Materials used in production |
| `factories` | `data/factories.csv` | 3 | Factories |
| `warehouses` | `data/warehouses.csv` | 4 | Warehouses |
| `transport_routes` | `data/transport_routes.csv` | 6 | Transport routes |
| `customer_orders` | `data/customer_orders.csv` | 25 | Customer orders |
| `inventory` | `data/inventory.csv` | 36 | Stock at factories and warehouses |
| `supplier_dependencies` | `data/supplier_dependencies.csv` | 31 | Direct supplier-to-supplier links |
| `supplier_materials` | `data/supplier_materials.csv` | 28 | Which supplier provides which material |

### Columns

**suppliers.csv**  
`supplier_id`, `supplier_name`, `tier`, `city`, `state`, `country`, `category`, `monthly_capacity_units`, `capacity_status`, `lead_time_days`, `quality_score`, `primary_route_id`

**materials.csv**  
`material_id`, `material_name`, `category`, `unit`, `unit_cost_inr`, `typical_lead_time_days`, `used_in_product`

**factories.csv**  
`factory_id`, `factory_name`, `city`, `state`, `country`, `product_focus`, `monthly_capacity_units`, `linked_warehouse_id`

**warehouses.csv**  
`warehouse_id`, `warehouse_name`, `city`, `state`, `country`, `capacity_units`, `serves_region`, `linked_factory_id`

**transport_routes.csv**  
`route_id`, `origin_id`, `origin_name`, `origin_type`, `destination_id`, `destination_name`, `destination_type`, `mode`, `distance_km`, `transit_days`, `cost_per_shipment_inr`, `cargo`, `shared_supplier_ids`

`shared_supplier_ids` is optional. Blank values on 5 of 6 routes are expected.

**customer_orders.csv**  
`order_id`, `customer_name`, `city`, `state`, `warehouse_id`, `product_name`, `quantity`, `unit_price_inr`, `order_value_inr`, `order_date`, `required_date`, `status`

**inventory.csv**  
`inventory_id`, `location_id`, `location_type`, `material_id`, `quantity_on_hand`, `reorder_point`, `max_stock`, `unit_cost_inr`

**supplier_dependencies.csv**  
`dependency_id`, `downstream_supplier_id`, `upstream_supplier_id`, `material_id`, `dependency_type`, `notes`

Read this as: the **downstream** supplier depends on the **upstream** supplier for that material.

**supplier_materials.csv**  
`supplier_id`, `material_id`, `is_backup`, `unit_cost_inr`, `monthly_capacity_units`, `lead_time_days`, `moq_units`

`is_backup` is `1` for backup suppliers. Verified backup mappings: `SUP-T1-04` / `MAT-02` and `SUP-T1-02` / `MAT-03`.

---

## 4. Exact imports

Recommended (package exports):

```python
from src import (
    load_all_data,
    get_supply_chain_graph,
    find_upstream_dependencies,
    find_suppliers_sharing_upstream,
    SupplyChainGraph,
    detect_dependencies,
    find_direct_dependencies,
    list_direct_dependencies,
    find_multi_tier_dependencies,
)
```

Equivalent file-level imports:

```python
from src.data_loader import load_all_data
from src.supply_chain_graph import (
    SupplyChainGraph,
    get_supply_chain_graph,
    find_upstream_dependencies,
    find_suppliers_sharing_upstream,
)
from src.dependency_detector import (
    detect_dependencies,
    find_direct_dependencies,
    list_direct_dependencies,
    find_multi_tier_dependencies,
)
```

---

## 5. How to load all datasets

```python
from src import load_all_data

data = load_all_data()                 # prints one line per table
data = load_all_data(verbose=False)    # no print

suppliers = data["suppliers"]          # pandas DataFrame, 35 rows
deps = data["supplier_dependencies"]   # pandas DataFrame, 31 rows
```

**`load_all_data(verbose=True)`**

- Arguments: `verbose` (bool, default `True`)
- Returns: `dict[str, pandas.DataFrame]`
- Keys: `suppliers`, `materials`, `factories`, `warehouses`, `transport_routes`, `customer_orders`, `inventory`, `supplier_dependencies`, `supplier_materials`

Do not parse CSV paths in Member 2 code. If SAP is added later, it will still go through `load_all_data()`.

---

## 6. How to access the NetworkX digital twin

```python
from src import load_all_data, get_supply_chain_graph, SupplyChainGraph

data = load_all_data(verbose=False)
graph = get_supply_chain_graph(data)   # networkx.DiGraph

print(graph.number_of_nodes())         # 91
print(graph.number_of_edges())         # 528
print(graph.nodes["SUP-T2-03"]["node_type"])   # "supplier"
print(graph.nodes["SUP-T2-03"]["tier"])        # 2
```

Using the wrapper class (same graph):

```python
twin = SupplyChainGraph()
twin.build_from_data(data)
graph = twin.get_graph()
```

**`get_supply_chain_graph(data=None)`**

- Arguments: `data` — dict from `load_all_data()`, or `None` to load CSVs inside the function
- Returns: `networkx.DiGraph`

Graph direction for supplier links: **upstream supplier → downstream supplier**.

Each node has `node_type` of one of: `supplier`, `material`, `factory`, `warehouse`, `transport_route`, `customer_order`.

Useful supplier-dependency edge type: `supplier_dependency`. Other edge types in the twin include `supplies`, `holds_inventory`, `feeds_warehouse`, `enters_route`, `leaves_route`, `uses_route`, `fulfills_order`, `used_in_order`.

The graph is a `DiGraph`, not a `MultiDiGraph`. A second edge between the same two nodes overwrites the first.

---

## 7. Direct supplier dependencies

```python
from src import load_all_data, list_direct_dependencies, find_direct_dependencies, detect_dependencies

data = load_all_data(verbose=False)

records = list_direct_dependencies(data)
# list of 31 dicts, each with:
# dependency_id, downstream_supplier_id, upstream_supplier_id,
# material_id, dependency_type, notes

table = find_direct_dependencies(data)
# pandas DataFrame with the same 31 rows (also prints a count)

results = detect_dependencies(data, graph=graph)
# results["direct"]          -> DataFrame (31 rows)
# results["direct_records"]  -> list of 31 dicts
# results["multi_tier"]      -> dict of supplier_id -> upstream id list
# results["multi_tier_risks"]-> []   (always empty; see section 9)
```

Example row meaning: `DEP-08` says downstream `SUP-T1-01` depends on upstream `SUP-T2-03` for `MAT-04`.

---

## 8. Shared upstream suppliers and multi-hop chains

```python
from src import (
    find_suppliers_sharing_upstream,
    find_upstream_dependencies,
    find_multi_tier_dependencies,
)

# Verified demo: who shares Nilgiri Cover Glass
shared = find_suppliers_sharing_upstream(graph, "SUP-T2-03")
# {'SUP-T2-03': ['SUP-T1-01', 'SUP-T1-02']}

# All parents that have two or more downstream suppliers
all_shared = find_suppliers_sharing_upstream(graph)

# All upstream suppliers for one node (direct and indirect)
upstream = find_upstream_dependencies(graph, "SUP-T1-03")
# includes SUP-T2-01 and SUP-T3-01 ... SUP-T3-04

# Every supplier that has at least one upstream hop
chains = find_multi_tier_dependencies(graph)
# dict, 22 keys (verified)
```

Other verified shared-upstream pair useful for backups: `SUP-T1-03` and `SUP-T1-04` share `SUP-T2-01`.

**`find_suppliers_sharing_upstream(graph, upstream_supplier_id=None)`**

- Arguments: NetworkX graph; optional supplier id
- Returns: `dict` mapping upstream id → sorted list of downstream supplier ids
- If you pass an id that is not a shared parent, you get `{that_id: []}`

**`find_upstream_dependencies(graph, supplier_id)`**

- Arguments: NetworkX graph; one supplier id
- Returns: `list` of upstream supplier ids (empty if the id is missing)
- Walks only `supplier_dependency` edges

**`find_multi_tier_dependencies(graph)`**

- Arguments: NetworkX graph
- Returns: `dict` of supplier id → upstream id list
- This is a **chain listing**, not a risk score

The same two lookup methods exist on `SupplyChainGraph`:

```python
twin.find_upstream_dependencies("SUP-T1-03")
twin.find_suppliers_sharing_upstream("SUP-T2-03")
```

---

## 9. What Member 1 did not implement (Member 2 work)

`detect_dependencies()["multi_tier_risks"]` is **always `[]`**.

`find_multi_tier_risks(data)` exists only as a placeholder. It prints that risk detection is not built and returns `[]`.

Member 2 can build risk and impact analysis using:

- `data["suppliers"]` (tier, capacity, lead time, quality, route)
- `data["supplier_dependencies"]` / `list_direct_dependencies(data)`
- `data["supplier_materials"]` (`is_backup`)
- `data["inventory"]` and `data["customer_orders"]`
- `graph` plus `find_upstream_dependencies` / `find_suppliers_sharing_upstream`

Suggested starting points (not implemented here):

1. Score a disruption at `SUP-T2-03` and see both display makers (`SUP-T1-01`, `SUP-T1-02`).
2. Score a disruption at `SUP-T2-01` and see both pack makers (`SUP-T1-03` primary, `SUP-T1-04` backup).
3. Walk `find_upstream_dependencies` / `graph.predecessors` for multi-hop exposure.

---

## 10. Function and class reference

| Name | Module | Arguments | Returns |
|---|---|---|---|
| `load_all_data` | `src.data_loader` | `verbose=True` | dict of DataFrames |
| `get_supply_chain_graph` | `src.supply_chain_graph` | `data=None` | `networkx.DiGraph` |
| `build_supply_chain_graph` | `src.supply_chain_graph` | `data` | `networkx.DiGraph` |
| `find_upstream_dependencies` | `src.supply_chain_graph` | `graph`, `supplier_id` | `list` of ids |
| `find_suppliers_sharing_upstream` | `src.supply_chain_graph` | `graph`, `upstream_supplier_id=None` | `dict` |
| `SupplyChainGraph` | `src.supply_chain_graph` | none for `__init__` | class instance |
| `SupplyChainGraph.build_from_data` | same | `data` | none (fills `self.graph`) |
| `SupplyChainGraph.get_graph` | same | none | `networkx.DiGraph` |
| `list_direct_dependencies` | `src.dependency_detector` | `data` | `list` of dicts |
| `find_direct_dependencies` | `src.dependency_detector` | `data` | DataFrame (or `[]` if missing) |
| `find_multi_tier_dependencies` | `src.dependency_detector` | `graph` | `dict` |
| `detect_dependencies` | `src.dependency_detector` | `data`, `graph=None` | dict with `direct`, `direct_records`, `multi_tier`, `multi_tier_risks` |
| `find_multi_tier_risks` | `src.dependency_detector` | `data` | `[]` (placeholder) |

`SupplyChainGraph.add_node` / `add_edge` / `summary` exist for manual graph edits. Member 2 should normally call `build_from_data` or `get_supply_chain_graph`.

---

## 11. Copy-paste starter for Member 2

```python
from src import (
    load_all_data,
    get_supply_chain_graph,
    find_upstream_dependencies,
    find_suppliers_sharing_upstream,
    list_direct_dependencies,
)

data = load_all_data(verbose=False)
graph = get_supply_chain_graph(data)

assert graph.number_of_nodes() == 91
assert graph.number_of_edges() == 528
assert len(list_direct_dependencies(data)) == 31
assert find_suppliers_sharing_upstream(graph, "SUP-T2-03")["SUP-T2-03"] == [
    "SUP-T1-01",
    "SUP-T1-02",
]

# Member 2 starts here: risk/impact using data + graph
shared = find_suppliers_sharing_upstream(graph)
upstream = find_upstream_dependencies(graph, "SUP-T1-03")
```
