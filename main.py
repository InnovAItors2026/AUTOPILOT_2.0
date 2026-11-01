"""
main.py
-------
Starting point for Member 1: Data Management and Supply Chain Digital Twin.

Run this file to load data, build the graph starter, and run
dependency detection starter code.
"""

from src.data_loader import load_all_data
from src.supply_chain_graph import SupplyChainGraph, run_graph_demo
from src.dependency_detector import detect_dependencies


def main():
    print("AUTOPILOT 2.0 - Member 1")
    print("Data Management and Supply Chain Digital Twin")
    print("-" * 50)

    # 1. Load synthetic CSV data (SAP can be added later in data_loader.py)
    data = load_all_data()

    # 2. Build the NetworkX digital twin from that data
    twin = SupplyChainGraph()
    twin.build_from_data(data)
    run_graph_demo(twin.get_graph())

    # 3. List supplier dependencies (risk scoring is not Member 1)
    results = detect_dependencies(data, graph=twin.get_graph())
    print("Dependency check finished.")
    print("Direct supplier-to-supplier rows:", len(results["direct"]))
    print("Suppliers with an upstream chain:", len(results["multi_tier"]))
    print("Multi-tier risks (other members):", results["multi_tier_risks"])


if __name__ == "__main__":
    main()
