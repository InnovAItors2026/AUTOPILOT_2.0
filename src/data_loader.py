
"""
Loads supply chain data for AUTOPILOT 2.0.

Supports:
1. CSV Baseline
2. SAP OData
3. SAP HANA Cloud

HANA loading includes connection verification before querying tables.
"""

from datetime import datetime, timezone
import os

import pandas as pd

# ---------------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# ---------------------------------------------------------

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ---------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------

DATA_FOLDER = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data")
)

DATA_SOURCE = os.environ.get("DATA_SOURCE", "csv").strip().lower()


# ---------------------------------------------------------
# CSV FILE MAPPING
# ---------------------------------------------------------

CSV_FILES = {
    "suppliers": "suppliers.csv",
    "materials": "materials.csv",
    "factories": "factories.csv",
    "warehouses": "warehouses.csv",
    "transport_routes": "transport_routes.csv",
    "customer_orders": "customer_orders.csv",
    "inventory": "inventory.csv",
    "supplier_dependencies": "supplier_dependencies.csv",
    "supplier_materials": "supplier_materials.csv",
}


# ---------------------------------------------------------
# SAP HANA TABLE MAPPING
# ---------------------------------------------------------

HANA_TABLES = {
    "suppliers": "SUPPLIERS",
    "materials": "MATERIALS",
    "factories": "FACTORIES",
    "warehouses": "WAREHOUSES",
    "transport_routes": "TRANSPORT_ROUTES",
    "customer_orders": "CUSTOMER_ORDERS",
    "inventory": "INVENTORY",
    "supplier_dependencies": "SUPPLIER_DEPENDENCIES",
    "supplier_materials": "SUPPLIER_MATERIALS",
}


# Optional HANA schema.
# Leave empty to use the database user's current schema.
HANA_SCHEMA = os.environ.get("HANA_SCHEMA", "").strip()


# ---------------------------------------------------------
# STATUS HELPER
# ---------------------------------------------------------

def create_source_status(
    connected,
    active_source,
    mode,
    message,
    error=None,
    current_schema=None,
    current_user=None,
    tables_loaded=None,
    total_records=None,
):
    """Create a consistent source-status DataFrame."""

    return pd.DataFrame([{
        "connected": connected,
        "active_source": active_source,
        "mode": mode,
        "message": message,
        "last_sync": (
            datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            )
            if connected else None
        ),
        "error": error,
        "current_schema": current_schema,
        "current_user": current_user,
        "tables_loaded": tables_loaded,
        "total_records": total_records,
    }])


# ---------------------------------------------------------
# CSV LOADER
# ---------------------------------------------------------

def load_csv(file_name):
    """Load an individual CSV file."""

    file_path = os.path.join(DATA_FOLDER, file_name)

    if not os.path.exists(file_path):
        print("CSV not found:", file_path)
        return pd.DataFrame()

    return pd.read_csv(file_path)


def load_from_csv(verbose=True):
    """Load all supply chain tables from local CSV files."""

    data = {}

    for table_name, file_name in CSV_FILES.items():

        data[table_name] = load_csv(file_name)

        if verbose:
            print(
                f"Loaded {table_name}: "
                f"{len(data[table_name])} rows"
            )

    data["_sap_status"] = create_source_status(
        connected=True,
        active_source="CSV Baseline",
        mode="CSV_BASELINE",
        message="Loaded local CSV tables."
    )

    return data


# ---------------------------------------------------------
# SAP ODATA LOADER
# ---------------------------------------------------------

def load_from_sap(verbose=True, client=None):
    """Load supply chain data through SAP OData."""

    try:

        if client is None:
            from src.sap_client import get_sap_client
            client = get_sap_client()

        if verbose:
            print("Querying SAP OData...")

        data = client.fetch_all(fallback_on_error=True)

        if verbose:
            print("SAP OData data retrieval completed.")

        return data

    except Exception as exc:

        if verbose:
            print(
                f"SAP OData load failed: {exc}. "
                "Falling back to CSV."
            )

        fallback = load_from_csv(verbose=verbose)

        fallback["_sap_status"] = create_source_status(
            connected=False,
            active_source="CSV Fallback (SAP OData Offline)",
            mode="CSV_FALLBACK",
            message=str(exc),
            error=str(exc)
        )

        return fallback


# ---------------------------------------------------------
# SAP HANA QUERY BUILDER
# ---------------------------------------------------------

def build_hana_query(table_name):
    """
    Build a SELECT query for a HANA table.

    Uses the current schema unless HANA_SCHEMA is configured.
    """

    if not table_name.replace("_", "").isalnum():
        raise ValueError(
            f"Invalid HANA table name: {table_name}"
        )

    if HANA_SCHEMA:

        if not HANA_SCHEMA.replace("_", "").isalnum():
            raise ValueError("Invalid HANA_SCHEMA value.")

        return (
            f'SELECT * FROM "{HANA_SCHEMA}"."{table_name}"'
        )

    return f'SELECT * FROM "{table_name}"'


# ---------------------------------------------------------
# SAP HANA CLOUD LOADER
# ---------------------------------------------------------

def load_from_hana(verbose=True):
    """
    Connect to SAP HANA Cloud.

    1. Establish connection.
    2. Verify credentials using DUMMY.
    3. Identify the current database schema.
    4. Load all nine supply chain tables.
    5. Return the data and connection status.
    """

    from src.integration.hana_client import get_hana_client

    if verbose:
        print("=" * 55)
        print("CONNECTING TO SAP HANA CLOUD")
        print("=" * 55)

    # Step 1: Get HANA client
    client = get_hana_client()

    # Step 2: Verify database connection
    connected, message, details = client.test_connection()

    if not connected:

        if verbose:
            print("HANA connection verification failed.")
            print(message)

            if details.get("missing_parameters"):
                for item in details["missing_parameters"]:
                    print(
                        f"Missing: {item['parameter']} - "
                        f"{item['purpose']}"
                    )

        raise ConnectionError(
            f"HANA connection test failed: {message}"
        )

    current_user = details.get("current_user", "Unknown")
    current_schema = details.get("current_schema", "Unknown")

    if verbose:
        print("HANA connection successful!")
        print("Database user:", current_user)
        print("Current schema:", current_schema)
        print("TLS encryption:", details.get("tls_encrypted"))
        print("-" * 55)

    # Step 3: Load all nine tables
    data = {}

    for key, table in HANA_TABLES.items():

        query = build_hana_query(table)

        try:

            if verbose:
                print(f"Loading HANA table: {table}")

            table_data = client.execute_read_query(query)

            if not isinstance(table_data, pd.DataFrame):
                table_data = pd.DataFrame(table_data)

            # Normalize column names to lowercase to ensure consistency with graph & risk models
            table_data.columns = [str(c).strip().lower() for c in table_data.columns]

            data[key] = table_data

            if verbose:
                print(
                    f"Successfully loaded {key}: "
                    f"{len(table_data)} rows, "
                    f"{len(table_data.columns)} columns"
                )

        except Exception as exc:

            if verbose:
                print(
                    f"FAILED to load HANA table '{table}': {exc}"
                )

            raise RuntimeError(
                f"Failed to load HANA table '{table}': {exc}"
            ) from exc

    # Step 4: Verify that all tables were loaded
    if len(data) != len(HANA_TABLES):
        raise RuntimeError(
            "Not all required HANA tables were loaded."
        )

    # Step 5: Record successful connection
    total_records = sum(len(data[k]) for k in HANA_TABLES.keys() if k in data)
    data["_sap_status"] = create_source_status(
        connected=True,
        active_source="SAP HANA Cloud",
        mode="HANA_LIVE",
        message=(
            "Successfully connected to SAP HANA Cloud. "
            "All nine AUTOPILOT tables were loaded."
        ),
        current_schema=current_schema,
        current_user=current_user,
        tables_loaded=len(HANA_TABLES),
        total_records=total_records,
    )

    if verbose:
        print("-" * 55)
        print("ALL NINE HANA TABLES LOADED SUCCESSFULLY.")
        print("=" * 55)

    return data


# ---------------------------------------------------------
# MAIN DATA LOADER
# ---------------------------------------------------------

def load_all_data(verbose=True, source=None, sap_client=None):
    """
    Load supply chain data from the selected source.

    Supported sources:
        csv
        hana
        hana_live
        sap
        sap_live
        sap_mock

    HANA/OData failures fall back to CSV with an explicit
    disconnected status.
    """

    actual_source = (
        source or DATA_SOURCE
    ).strip().lower()

    if verbose:
        print("\nAUTOPILOT 2.0 DATA LOADER")
        print("Selected source:", actual_source)
        print("-" * 55)

    # -----------------------------------------------------
    # SAP HANA CLOUD
    # -----------------------------------------------------

    if actual_source in ("hana", "hana_live"):

        try:
            return load_from_hana(verbose=verbose)

        except Exception as exc:

            if verbose:
                print("\nSAP HANA CLOUD LOADING FAILED")
                print("Reason:", str(exc))
                print("Switching to local CSV fallback.")

            fallback = load_from_csv(verbose=verbose)

            fallback["_sap_status"] = create_source_status(
                connected=False,
                active_source="CSV Fallback (HANA Offline)",
                mode="CSV_FALLBACK",
                message=str(exc),
                error=str(exc)
            )

            return fallback

    # -----------------------------------------------------
    # SAP ODATA
    # -----------------------------------------------------

    if actual_source in ("sap", "sap_live", "sap_mock"):

        return load_from_sap(
            verbose=verbose,
            client=sap_client
        )

    # -----------------------------------------------------
    # CSV BASELINE
    # -----------------------------------------------------

    if actual_source == "csv":

        return load_from_csv(verbose=verbose)

    # -----------------------------------------------------
    # INVALID SOURCE
    # -----------------------------------------------------

    raise ValueError(
        f"Unsupported DATA_SOURCE: '{actual_source}'. "
        "Choose csv, hana, sap, or sap_mock."
    )
