

import os
import re
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from hdbcli import dbapi

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"

TABLES = {
    "suppliers": "SUPPLIERS",
    "materials": "MATERIALS",
    "factories": "FACTORIES",
    "warehouses": "WAREHOUSES",
    "inventory": "INVENTORY",
    "customer_orders": "CUSTOMER_ORDERS",
    "supplier_dependencies": "SUPPLIER_DEPENDENCIES",
    "supplier_materials": "SUPPLIER_MATERIALS",
    "transport_routes": "TRANSPORT_ROUTES",
}


def quote_identifier(name):
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return '"' + name.upper() + '"'


def sql_type(series):
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_float_dtype(series):
        return "DOUBLE"
    return "NVARCHAR(5000)"


def main():
    host = os.getenv("HANA_HOST")
    user = os.getenv("HANA_USER")
    password = os.getenv("HANA_PASSWORD")
    port = int(os.getenv("HANA_PORT", "443"))

    if not all([host, user, password]):
        raise RuntimeError("Missing HANA connection configuration in .env")

    print("Connecting to SAP HANA Cloud...")

    conn = dbapi.connect(
        address=host,
        port=port,
        user=user,
        password=password,
        encrypt=True,
        sslValidateCertificate=True,
    )

    cursor = conn.cursor()

    try:
        cursor.execute("SELECT CURRENT_USER, CURRENT_SCHEMA FROM DUMMY")
        current_user, schema = cursor.fetchone()

        print(f"Connected as: {current_user}")
        print(f"Target schema: {schema}")

        # Explicit confirmation before modifying the database.
        print("\nThis operation creates/replaces the nine AUTOPILOT tables.")
        confirmation = input("Type LOAD AUTOPILOT DATA to continue: ")

        if confirmation != "LOAD AUTOPILOT DATA":
            print("Cancelled. No database changes made.")
            return

        for csv_name, table_name in TABLES.items():
            csv_path = DATA_DIR / f"{csv_name}.csv"

            if not csv_path.exists():
                raise FileNotFoundError(f"Missing file: {csv_path}")

            df = pd.read_csv(csv_path)
            df.columns = [str(c).upper() for c in df.columns]

            if df.empty:
                raise ValueError(f"{csv_name}.csv contains no rows")

            columns = list(df.columns)
            definitions = [
                f"{quote_identifier(col)} {sql_type(df[col])}"
                for col in columns
            ]

            table = quote_identifier(table_name)

            # Drop and recreate only these explicitly named project tables.
            cursor.execute(f"DROP TABLE {table}") if False else None

            try:
                cursor.execute(f"DROP TABLE {table}")
            except Exception as exc:
                if "259" not in str(exc) and "not found" not in str(exc).lower():
                    raise

            create_sql = (
                f"CREATE COLUMN TABLE {table} "
                f"({', '.join(definitions)})"
            )
            cursor.execute(create_sql)

            insert_sql = (
                f"INSERT INTO {table} "
                f"({', '.join(quote_identifier(c) for c in columns)}) "
                f"VALUES ({', '.join(['?'] * len(columns))})"
            )

            rows = [
                tuple(None if pd.isna(v) else (
                    bool(v) if isinstance(v, (bool,))
                    else v.item() if hasattr(v, "item")
                    else v
                ) for v in row)
                for row in df.itertuples(index=False, name=None)
            ]

            cursor.executemany(insert_sql, rows)
            conn.commit()

            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]

            print(f"SUCCESS: {table_name}: {count} rows loaded")

        print("\n========================================")
        print("AUTOPILOT HANA DATA IMPORT COMPLETE")
        print("All nine project tables processed.")
        print("========================================")

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nIMPORT FAILED: {error}")
        sys.exit(1)
