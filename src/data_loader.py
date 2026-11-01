"""
data_loader.py
--------------
Loads supply chain data for AUTOPILOT 2.0.

For now we read synthetic CSV files from the data/ folder because
SAP access is not confirmed yet.

Later we can add SAP API loading in this same file without changing
the rest of the project much. Other files should call load_all_data()
instead of reading files themselves.
"""

import os
import pandas as pd


# Folder that stores CSV files (next to the src folder).
DATA_FOLDER = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))

# Expected CSV file names. Create these files when synthetic data is ready.
CSV_FILES = {
    "suppliers": "suppliers.csv",          # 35 suppliers across multiple tiers
    "materials": "materials.csv",          # materials used in production
    "factories": "factories.csv",          # 3 factories
    "warehouses": "warehouses.csv",        # 4 warehouses
    "transport_routes": "transport_routes.csv",  # 6 transport routes
    "customer_orders": "customer_orders.csv",    # 25 customer orders
    "inventory": "inventory.csv",          # inventory levels
    "supplier_dependencies": "supplier_dependencies.csv",  # supplier-to-supplier links
    "supplier_materials": "supplier_materials.csv",  # which supplier provides which material
}

# Switch this later: "csv" now, "sap" when the SAP API is available.
DATA_SOURCE = "csv"


def load_csv(file_name):
    """Read one CSV file from the data folder and return a DataFrame."""
    file_path = os.path.join(DATA_FOLDER, file_name)

    if not os.path.exists(file_path):
        print("CSV not found yet:", file_path)
        return pd.DataFrame()

    return pd.read_csv(file_path)


def load_from_sap():
    """
    Placeholder for future SAP API integration.

    When SAP access is confirmed, put the API calls here and return
    the same dictionary keys as load_from_csv().
    """
    print("SAP loading is not set up yet. Using CSV instead.")
    return load_from_csv()


def load_from_csv(verbose=True):
    """Load all synthetic CSV tables into a dictionary of DataFrames."""
    data = {}

    for table_name, file_name in CSV_FILES.items():
        data[table_name] = load_csv(file_name)
        if verbose:
            print("Loaded", table_name, ":", len(data[table_name]), "rows")

    return data


def load_all_data(verbose=True):
    """
    Main function other modules should use.

    Chooses CSV or SAP based on DATA_SOURCE.
    Returns a dict of pandas DataFrames keyed by table name.
    """
    if DATA_SOURCE == "sap":
        return load_from_sap()

    return load_from_csv(verbose=verbose)
