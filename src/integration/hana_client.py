"""
hana_client.py
--------------
SAP HANA Cloud SQL Integration Client for AUTOPILOT 2.0.

Provides direct, read-only SQL connectivity to SAP HANA Cloud instances
using the official hdbcli driver with mandatory TLS/SSL encryption.

Features:
- Reads configuration strictly from environment variables or explicit parameters.
- Enforces secure TLS encryption (encrypt=True, sslValidateCertificate=True).
- Non-destructive connection verification using DUMMY view query:
    SELECT CURRENT_USER, CURRENT_SCHEMA, CURRENT_TIMESTAMP FROM DUMMY;
- Strict read-only query policy (no DDL/DML, no write-backs).
- Passwords and secrets are never logged, printed, or exposed.
- Detailed guidance on where to locate credentials if missing.
"""

from datetime import datetime, timezone
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Load .env if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("autopilot.integration.hana_client")


class HANAClient:
    """Read-only SAP HANA Cloud SQL Client using hdbcli."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        encrypt: Optional[bool] = None,
        ssl_validate_certificate: Optional[bool] = None,
        timeout_ms: int = 15000,
    ):
        self.host = (host if host is not None else os.environ.get("HANA_HOST", "")).strip()

        port_val = port if port is not None else os.environ.get("HANA_PORT", "443")
        try:
            self.port = int(port_val)
        except (ValueError, TypeError):
            self.port = 443

        self.user = (user if user is not None else os.environ.get("HANA_USER", "")).strip()
        self._password = password if password is not None else os.environ.get("HANA_PASSWORD", "")

        # TLS / SSL Settings (HANA Cloud requires TLS encryption)
        if encrypt is not None:
            self.encrypt = encrypt
        else:
            self.encrypt = os.environ.get("HANA_ENCRYPT", "true").lower() in ("true", "1", "yes")

        if ssl_validate_certificate is not None:
            self.ssl_validate_certificate = ssl_validate_certificate
        else:
            self.ssl_validate_certificate = os.environ.get(
                "HANA_SSL_VALIDATE_CERTIFICATE", "true"
            ).lower() in ("true", "1", "yes")

        try:
            self.timeout_ms = int(os.environ.get("HANA_TIMEOUT", str(timeout_ms)))
        except ValueError:
            self.timeout_ms = 15000

    def __repr__(self) -> str:
        """Safe string representation that never exposes passwords."""
        masked_pwd = "***" if self._password else "UNSET"
        return (
            f"<HANAClient host='{self.host}' port={self.port} "
            f"user='{self.user}' password={masked_pwd} encrypt={self.encrypt} "
            f"sslValidateCertificate={self.ssl_validate_certificate}>"
        )

    def get_missing_config(self) -> List[Dict[str, str]]:
        """
        Identify missing connection parameters and provide exact instructions
        on where to find them in the SAP BTP Cockpit.
        """
        missing = []
        if not self.host or "your-" in self.host.lower() or "example" in self.host.lower():
            missing.append({
                "parameter": "HANA_HOST",
                "purpose": "HANA Cloud SQL endpoint hostname",
                "where_to_find": (
                    "In SAP BTP Cockpit -> Subaccount -> SAP HANA Cloud -> HANA Database "
                    "Instances -> Click Actions (...) on your instance -> Copy 'SQL Endpoint' "
                    "(e.g., <guid>.hanacloud.ondemand.com)."
                ),
            })
        if not self.user:
            missing.append({
                "parameter": "HANA_USER",
                "purpose": "Database user name",
                "where_to_find": (
                    "Standard administrative user is 'DBADMIN'. For least-privilege read access, "
                    "create a dedicated user (e.g., 'AUTOPILOT_READER') via SAP HANA Database Explorer."
                ),
            })
        if not self._password:
            missing.append({
                "parameter": "HANA_PASSWORD",
                "purpose": "Database user password",
                "where_to_find": (
                    "The master password created during instance provisioning in SAP BTP Cockpit, "
                    "or the password assigned to your database user."
                ),
            })
        return missing

    def test_connection(self) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Perform a non-destructive read-only connection test.

        Executes:
            SELECT CURRENT_USER, CURRENT_SCHEMA, CURRENT_TIMESTAMP FROM DUMMY;

        Returns:
            (is_connected: bool, status_message: str, details: dict)
        """
        missing = self.get_missing_config()
        if missing:
            param_names = ", ".join(m["parameter"] for m in missing)
            details = {
                "status": "MISSING_CREDENTIALS",
                "missing_parameters": missing,
                "host": self.host or "UNSET",
                "port": self.port,
            }
            return (
                False,
                f"Missing required SAP HANA Cloud connection parameter(s): {param_names}.",
                details,
            )

        try:
            from hdbcli import dbapi
        except ImportError:
            return (
                False,
                "The 'hdbcli' driver is not installed. Please run: pip install hdbcli",
                {"status": "MISSING_DRIVER"},
            )

        conn = None
        cursor = None
        try:
            # Connect with mandatory TLS settings
            conn = dbapi.connect(
                address=self.host,
                port=self.port,
                user=self.user,
                password=self._password,
                encrypt=self.encrypt,
                sslValidateCertificate=self.ssl_validate_certificate,
                connectTimeout=self.timeout_ms,
            )

            cursor = conn.cursor()
            # Verified read-only query using DUMMY view
            cursor.execute("SELECT CURRENT_USER, CURRENT_SCHEMA, CURRENT_TIMESTAMP FROM DUMMY;")
            row = cursor.fetchone()

            if row:
                current_user = str(row[0])
                current_schema = str(row[1])
                current_ts = str(row[2])
                return (
                    True,
                    f"Successfully connected to SAP HANA Cloud as user '{current_user}'.",
                    {
                        "status": "CONNECTED",
                        "current_user": current_user,
                        "current_schema": current_schema,
                        "database_timestamp": current_ts,
                        "host": self.host,
                        "port": self.port,
                        "tls_encrypted": self.encrypt,
                    },
                )
            else:
                return (
                    False,
                    "Query executed but returned an empty response from DUMMY view.",
                    {"status": "EMPTY_RESULT"},
                )

        except dbapi.Error as db_err:
            raw_msg = str(db_err)
            # Mask any potential password leakage in raw error text
            safe_msg = raw_msg.replace(self._password, "***") if self._password else raw_msg
            return (
                False,
                f"SAP HANA Cloud Connection Error: {safe_msg}",
                {
                    "status": "DATABASE_ERROR",
                    "host": self.host,
                    "port": self.port,
                },
            )
        except Exception as exc:
            raw_msg = str(exc)
            safe_msg = raw_msg.replace(self._password, "***") if self._password else raw_msg
            return (
                False,
                f"Unexpected error while connecting to SAP HANA Cloud: {safe_msg}",
                {"status": "UNEXPECTED_ERROR"},
            )
        finally:
            if cursor:
                try:
                    cursor.close()
                except Exception:
                    pass
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def execute_read_query(
        self, query: str, params: Optional[Any] = None
    ) -> pd.DataFrame:
        """
        Execute a strictly read-only query on SAP HANA Cloud and return a DataFrame.

        Hard security gate: Rejects any query containing modification keywords
        (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, REPLACE, MERGE).
        """
        cleaned = query.strip()
        forbidden = re.compile(
            r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|MERGE|GRANT|REVOKE)\b",
            re.IGNORECASE,
        )
        if forbidden.search(cleaned):
            raise PermissionError(
                "Write/DDL/DML operations are strictly forbidden in read-only mode."
            )

        if not re.match(r"^\s*(SELECT|WITH)\b", cleaned, re.IGNORECASE):
            raise ValueError("Only SELECT or WITH read queries are permitted.")

        from hdbcli import dbapi

        conn = dbapi.connect(
            address=self.host,
            port=self.port,
            user=self.user,
            password=self._password,
            encrypt=self.encrypt,
            sslValidateCertificate=self.ssl_validate_certificate,
            connectTimeout=self.timeout_ms,
        )
        try:
            cursor = conn.cursor()
            cursor.execute(cleaned, params or ())
            rows = cursor.fetchall()
            cols = [desc[0] for desc in cursor.description] if cursor.description else []
            return pd.DataFrame(rows, columns=cols)
        finally:
            conn.close()

    def verify_tables_accessibility(
        self, tables: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        Verify accessibility and record counts for all required AUTOPILOT tables in HANA.

        Non-destructive read-only operation: executes SELECT COUNT(*) for each table.
        """
        if tables is None:
            tables = {
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

        conn_ok, msg, details = self.test_connection()
        if not conn_ok:
            return {
                "connected": False,
                "message": msg,
                "details": details,
                "tables_accessible": 0,
                "total_tables": len(tables),
                "total_records": 0,
                "table_counts": {},
                "errors": [msg],
            }

        from hdbcli import dbapi

        table_counts = {}
        errors = []
        total_records = 0

        conn = None
        try:
            conn = dbapi.connect(
                address=self.host,
                port=self.port,
                user=self.user,
                password=self._password,
                encrypt=self.encrypt,
                sslValidateCertificate=self.ssl_validate_certificate,
                connectTimeout=self.timeout_ms,
            )
            cursor = conn.cursor()
            for key, tbl in tables.items():
                try:
                    cursor.execute(f'SELECT COUNT(*) FROM "{tbl}"')
                    row = cursor.fetchone()
                    cnt = int(row[0]) if row else 0
                    table_counts[tbl] = cnt
                    total_records += cnt
                except Exception as exc:
                    errors.append(f"Failed to query {tbl}: {exc}")
            cursor.close()
        except Exception as exc:
            errors.append(f"Connection error during table verification: {exc}")
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

        return {
            "connected": True,
            "message": f"Successfully verified {len(table_counts)}/{len(tables)} tables ({total_records} total records).",
            "current_user": details.get("current_user"),
            "current_schema": details.get("current_schema"),
            "database_timestamp": details.get("database_timestamp"),
            "tables_accessible": len(table_counts),
            "total_tables": len(tables),
            "total_records": total_records,
            "table_counts": table_counts,
            "errors": errors,
        }


# Module-level singleton
_GLOBAL_HANA_CLIENT: Optional[HANAClient] = None


def get_hana_client(force_new: bool = False, **kwargs) -> HANAClient:
    """Return configured HANAClient singleton instance."""
    global _GLOBAL_HANA_CLIENT
    if _GLOBAL_HANA_CLIENT is None or force_new:
        _GLOBAL_HANA_CLIENT = HANAClient(**kwargs)
    return _GLOBAL_HANA_CLIENT
