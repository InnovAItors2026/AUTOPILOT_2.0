"""
test_hana_client.py
-------------------
Unit tests for SAP HANA Cloud SQL integration client (src/integration/hana_client.py).
"""

import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.integration.hana_client import HANAClient, get_hana_client


class HANAClientTests(unittest.TestCase):
    def test_initialization_defaults(self):
        client = HANAClient(
            host="dummy.hanacloud.ondemand.com",
            port=443,
            user="TEST_USER",
            password="SECRET_PASSWORD_123",
        )
        self.assertEqual(client.host, "dummy.hanacloud.ondemand.com")
        self.assertEqual(client.port, 443)
        self.assertEqual(client.user, "TEST_USER")
        self.assertTrue(client.encrypt)
        self.assertTrue(client.ssl_validate_certificate)

    def test_password_never_exposed_in_repr(self):
        client = HANAClient(
            host="dummy.hanacloud.ondemand.com",
            port=443,
            user="TEST_USER",
            password="SUPER_SENSITIVE_PASSWORD",
        )
        repr_str = repr(client)
        self.assertNotIn("SUPER_SENSITIVE_PASSWORD", repr_str)
        self.assertIn("***", repr_str)

    def test_missing_config_reporting(self):
        # Empty client with no environment variables
        client = HANAClient(host="", port=443, user="", password="")
        missing = client.get_missing_config()
        param_names = [m["parameter"] for m in missing]

        self.assertIn("HANA_HOST", param_names)
        self.assertIn("HANA_USER", param_names)
        self.assertIn("HANA_PASSWORD", param_names)

        # Ensure actionable guidance is returned for each missing parameter
        for m in missing:
            self.assertGreater(len(m["where_to_find"]), 20)
            self.assertIn("parameter", m)

        connected, msg, details = client.test_connection()
        self.assertFalse(connected)
        self.assertEqual(details["status"], "MISSING_CREDENTIALS")
        self.assertIn("Missing required", msg)

    def test_read_only_query_enforcement(self):
        client = HANAClient(
            host="dummy.hanacloud.ondemand.com",
            port=443,
            user="TEST_USER",
            password="PWD",
        )
        # Forbidden DDL/DML statements
        forbidden_queries = [
            "INSERT INTO SUPPLIERS VALUES ('S1', 'Name')",
            "UPDATE INVENTORY SET QUANTITY = 0",
            "DELETE FROM MATERIALS WHERE ID = 'M1'",
            "DROP TABLE CUSTOMER_ORDERS",
            "CREATE TABLE HACK_TEST (ID INT)",
            "ALTER TABLE FACTORIES ADD COLUMN TEST VARCHAR(10)",
            "TRUNCATE TABLE ROUTES",
        ]

        for q in forbidden_queries:
            with self.assertRaises(PermissionError):
                client.execute_read_query(q)

    def test_error_sanitization(self):
        # Point to an unreachable port to trigger error handling
        client = HANAClient(
            host="127.0.0.1",
            port=59999,
            user="TEST_USER",
            password="CONFIDENTIAL_KEY_XYZ",
            timeout_ms=500,
        )
        connected, msg, details = client.test_connection()
        self.assertFalse(connected)
        # Verify password is not in the error message
        self.assertNotIn("CONFIDENTIAL_KEY_XYZ", msg)


if __name__ == "__main__":
    unittest.main()
