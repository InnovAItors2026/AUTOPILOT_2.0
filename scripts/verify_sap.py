"""
verify_sap.py
-------------
Independent SAP Read Connection Verification Script for Member 5.

Run this script to verify your SAP connection status before running
the Streamlit dashboard or starting the final demonstration.

Usage:
    python scripts/verify_sap.py
    python scripts/verify_sap.py --mode mock
"""

import argparse
import json
import os
import sys

# Ensure project root is in sys.path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.sap_client import SAPClient, get_sap_client


def main():
    parser = argparse.ArgumentParser(description="Verify SAP OData Read Connection")
    parser.add_argument("--mode", choices=["live", "mock"], default=None, help="Force live or mock mode")
    parser.add_argument("--url", default=None, help="Override SAP base URL")
    parser.add_argument("--key", default=None, help="Override SAP API Key")
    args = parser.parse_args()

    auth_type = "mock" if args.mode == "mock" else None
    client = SAPClient(
        base_url=args.url,
        auth_type=auth_type,
        api_key=args.key,
    )

    print("=" * 65)
    print("  AUTOPILOT 2.0 — SAP Read Connection Verifier (Member 5)")
    print("=" * 65)
    print(f"Target Base URL : {client.base_url}")
    print(f"Auth Protocol   : {client.auth_type.upper()}")
    print(f"Read-Only Mode  : STRICT (no records will be modified)")
    print("-" * 65)

    print("Pinging SAP Endpoint for non-destructive read...")
    connected, message, details = client.test_connection()

    if connected:
        print("\n>>> [SUCCESS] SAP READ CONNECTION VERIFIED <<<")
        print(f"Status Message : {message}")
        print("Details:")
        print(json.dumps(details, indent=2))
        print("\nLoading dataset snapshot via SAP Client adapter...")
        data = client.fetch_all(fallback_on_error=True)
        print(f"Verified Suppliers Count : {len(data['suppliers'])}")
        print(f"Verified Materials Count : {len(data['materials'])}")
        print(f"Data Source Mode         : {data['_sap_status']['mode'].iloc[0]}")
    else:
        print("\n>>> [NOTICE] SAP API NOT DIRECTLY REACHABLE <<<")
        print(f"Reason: {message}")
        print("\nFallback Strategy:")
        print("AUTOPILOT 2.0 will automatically operate on the validated baseline datasets.")
        print("To connect to a live SAP system, provide your credentials in .env or via environment variables.")
        print("Run with '--mode mock' to test the full SAP OData integration workflow offline.")

    print("=" * 65)


if __name__ == "__main__":
    main()
