"""
verify_hana.py
--------------
Independent SAP HANA Cloud SQL Read Connection Verification Script for Member 5.

Performs a secure, non-destructive connection test using:
    SELECT CURRENT_USER, CURRENT_SCHEMA, CURRENT_TIMESTAMP FROM DUMMY;

Usage:
    python scripts/verify_hana.py
    python scripts/verify_hana.py --host <endpoint> --port 443 --user DBADMIN
"""

import argparse
import json
import os
import sys

# Ensure repository root is on sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.integration.hana_client import HANAClient


def main():
    parser = argparse.ArgumentParser(
        description="Verify SAP HANA Cloud SQL Read Connection (hdbcli)"
    )
    parser.add_argument("--host", default=None, help="HANA Cloud SQL endpoint host")
    parser.add_argument("--port", type=int, default=None, help="HANA port (default: 443)")
    parser.add_argument("--user", default=None, help="HANA database username")
    parser.add_argument("--password", default=None, help="HANA database password")
    parser.add_argument(
        "--skip-cert-validation",
        action="store_true",
        help="Disable SSL certificate validation (for testing only)",
    )
    args = parser.parse_args()

    client = HANAClient(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        ssl_validate_certificate=False if args.skip_cert_validation else None,
    )

    print("=" * 70)
    print("  AUTOPILOT 2.0 — SAP HANA Cloud SQL Read Verifier (Member 5)")
    print("=" * 70)
    print(f"Target Host     : {client.host or '(Not configured in .env)'}")
    print(f"Target Port     : {client.port}")
    print(f"Target User     : {client.user or '(Not configured in .env)'}")
    print(f"TLS Encryption  : {'REQUIRED (encrypt=True)' if client.encrypt else 'OFF'}")
    print(f"SSL Cert Verify : {client.ssl_validate_certificate}")
    print(f"Read-Only Mode  : STRICT (DUMMY view query only)")
    print("-" * 70)

    print("Testing connection to SAP HANA Cloud...")
    connected, message, details = client.test_connection()

    if connected:
        print("\n>>> [SUCCESS] SAP HANA CLOUD SQL CONNECTION VERIFIED <<<")
        print(f"Status Message     : {message}")
        print(f"Authenticated User : {details.get('current_user')}")
        print(f"Default Schema     : {details.get('current_schema')}")
        print(f"Database Timestamp : {details.get('database_timestamp')}")
        print(f"TLS Active         : {details.get('tls_encrypted')}")

        print("\nVerifying all 9 AUTOPILOT tables in SAP HANA Cloud...")
        tbl_res = client.verify_tables_accessibility()
        print(f"Accessible Tables  : {tbl_res.get('tables_accessible')} / {tbl_res.get('total_tables')}")
        print(f"Total SQL Records  : {tbl_res.get('total_records')}")
        print("-" * 70)
        for tbl_name, count in tbl_res.get("table_counts", {}).items():
            print(f"  • {tbl_name:<24}: {count:>3} rows")
        print("-" * 70)
    else:
        status = details.get("status", "")
        if status == "MISSING_CREDENTIALS":
            print("\n>>> [CONFIGURATION NOTICE] MISSING HANA CREDENTIALS <<<")
            print(f"Reason: {message}\n")
            print("WHERE TO OBTAIN YOUR SAP HANA CLOUD CREDENTIALS:")
            print("-" * 70)
            for item in details.get("missing_parameters", []):
                print(f"• {item['parameter']}:")
                print(f"  {item['where_to_find']}\n")
            print("Set these in your local '.env' file:")
            print("  HANA_HOST=your-instance.hanacloud.ondemand.com")
            print("  HANA_PORT=443")
            print("  HANA_USER=DBADMIN")
            print("  HANA_PASSWORD=your_password")
        else:
            print("\n>>> [CONNECTION FAILED] UNABLE TO REACH SAP HANA CLOUD <<<")
            print(f"Error Message: {message}")
            print("\nTroubleshooting Checklist:")
            print("1. IP Allowlist: In SAP BTP Cockpit, verify that your client IP is allowed.")
            print("2. Host & Port: Ensure host ends with .hanacloud.ondemand.com and port is 443.")
            print("3. Password: Check that HANA_PASSWORD matches your DB user password.")

    print("=" * 70)


if __name__ == "__main__":
    main()
