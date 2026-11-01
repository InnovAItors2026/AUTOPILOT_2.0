# AUTOPILOT 2.0 - Member 1

Data Management and Supply Chain Digital Twin.

This module loads the project datasets, builds a NetworkX digital twin of the supplier network, and exposes dependency lookup functions for the rest of the team.

## Scope

Member 1 owns:

1. Dataset creation and management
2. Supplier network construction
3. Supplier dependency graph
4. Shared upstream supplier identification
5. Making the data and graph available to other team members

Member 1 does **not** own risk analysis, impact analysis, recovery optimisation, cascading failure, frontend, or SAP integration.

SAP access is not confirmed yet, so the data source is **synthetic CSV files** in `data/`. `src/data_loader.py` can later add a SAP loader without changing how other modules call `load_all_data()`.

## Setup (beginner)

1. Open a terminal.
2. Go to this project folder:

```bash
cd C:\Users\bhovi\OneDrive\Desktop\AUTOPILOT_2.0
```

3. Install the Python packages:

```bash
py -3 -m pip install -r requirements.txt
```

You only need `pandas` and `networkx`.

## Architecture

```
CSV files in data/
        |
        v
src/data_loader.py          load_all_data() -> dict of DataFrames
        |
        v
src/supply_chain_graph.py   NetworkX DiGraph digital twin
        |
        +-- find_upstream_dependencies()
        +-- find_suppliers_sharing_upstream()
        |
        v
src/dependency_detector.py  lists direct and multi-hop supplier links
        |
        v
Other team members import from src
```

Goods-flow direction in the graph: **upstream supplier -> downstream supplier**.

## Folder structure

```
data/                      Synthetic CSV files
src/
    __init__.py            Package exports for other modules
    data_loader.py         Loads CSV now; SAP API later
    supply_chain_graph.py  Builds the digital twin graph
    dependency_detector.py Lists supplier-to-supplier links
tests/
    test_member1.py        Automated Member 1 tests
main.py                    Program entry point
validate_data.py           Dataset integrity checks
HANDOVER_MEMBER1.md        Instructions for Member 2
requirements.txt           Python packages to install
README.md                  This file
```

## Datasets

Fictional OEM: **Aarohan Electronics** (India).

| File | Rows | Purpose |
|---|---|---|
| `data/suppliers.csv` | 35 | Suppliers in 3 tiers (10 / 13 / 12) |
| `data/materials.csv` | 18 | Materials used in production |
| `data/factories.csv` | 3 | Factories |
| `data/warehouses.csv` | 4 | Warehouses |
| `data/transport_routes.csv` | 6 | Transport routes |
| `data/customer_orders.csv` | 25 | Customer orders |
| `data/inventory.csv` | 36 | Stock at factories and warehouses |
| `data/supplier_dependencies.csv` | 31 | Supplier-to-supplier links |
| `data/supplier_materials.csv` | 28 | Which supplier provides which material |

Blank `shared_supplier_ids` on 5 routes is expected. That column is optional.

## Functions other members can import

```python
from src import (
    load_all_data,
    get_supply_chain_graph,
    find_upstream_dependencies,
    find_suppliers_sharing_upstream,
    SupplyChainGraph,
    detect_dependencies,
    list_direct_dependencies,
    find_multi_tier_dependencies,
)

data = load_all_data()                 # dict of pandas DataFrames
graph = get_supply_chain_graph(data)   # networkx.DiGraph

# Upstream chain for one supplier (Tier 3 then Tier 2, by tier)
find_upstream_dependencies(graph, "SUP-T1-03")

# Who shares one upstream parent
find_suppliers_sharing_upstream(graph, "SUP-T2-03")
# -> {'SUP-T2-03': ['SUP-T1-01', 'SUP-T1-02']}

# All shared upstream parents
find_suppliers_sharing_upstream(graph)
```

`load_all_data()` keys:

`suppliers`, `materials`, `factories`, `warehouses`, `transport_routes`, `customer_orders`, `inventory`, `supplier_dependencies`, `supplier_materials`

You can also import from the original files:

```python
from src.data_loader import load_all_data
from src.supply_chain_graph import get_supply_chain_graph
```

Pass `verbose=False` if you do not want load messages: `load_all_data(verbose=False)`.

## Execution commands

Run these from the `AUTOPILOT_2.0` folder so `from src...` imports work.

```bash
py -3 -m pip install -r requirements.txt
py -3 validate_data.py
py -3 main.py
py -3 -m unittest discover -s tests -v
```

## Actual test results (1 Nov 2026)

### `py -3 -m unittest discover -s tests -v`

```
test_csv_files_exist ... ok
test_dependency_edges_match_dataset ... ok
test_every_dataset_id_is_a_graph_node ... ok
test_foreign_keys_are_valid ... ok
test_graph_node_and_edge_counts ... ok
test_handover_api_and_class_wrapper ... ok
test_no_duplicate_ids ... ok
test_required_ids_have_no_missing_values ... ok
test_shared_upstream_with_real_data ... ok
test_tables_load_with_expected_counts ... ok

Ran 10 tests in 0.140s
OK
```

### `py -3 validate_data.py`

- All 9 CSV files loaded
- Counts match the table above
- Invalid dependency IDs: none
- Self-references: none
- Unmapped materials: none
- Duplicate IDs: none
- Warnings: NONE
- Errors: NONE
- Exit code: 0

### `py -3 main.py`

- Digital twin nodes: **91**
- Digital twin edges: **528**
- Node types: 35 suppliers, 18 materials, 3 factories, 4 warehouses, 6 routes, 25 customer orders
- Shared upstream example: `SUP-T2-03` (Nilgiri Cover Glass) -> `SUP-T1-01`, `SUP-T1-02`
- Upstream of `SUP-T1-03` (DeccanCell Packs): `SUP-T2-01` plus `SUP-T3-01` ... `SUP-T3-04`
- Direct supplier-to-supplier rows: 31
- Suppliers with an upstream chain: 22
- Isolated graph nodes: 0

## Handover notes for other members

Full API, columns, and copy-paste examples for Member 2 are in **`HANDOVER_MEMBER1.md`**.

- Start with `load_all_data()` and `get_supply_chain_graph(data)`. Do not read CSV files yourself.
- Shared-upstream demo ID: **SUP-T2-03**. Backup pack maker pair: **SUP-T1-03** and **SUP-T1-04** share **SUP-T2-01**.
- `detect_dependencies()["multi_tier_risks"]` is always empty. Risk scoring is not implemented here.
- Graph type is `networkx.DiGraph`. Repeat edges between the same two nodes overwrite; counts above are the live totals.

## Out of scope (do not expect these from Member 1)

- Live SAP loading
- Risk / impact / recovery / cascading-failure models
- Frontend
- Retraining any ML models
