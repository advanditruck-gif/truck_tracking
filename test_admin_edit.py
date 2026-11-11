import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

import app as app_module
import config
import db


class AdminEditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.database_path = db.DB_PATH
        self.database_url = db.DATABASE_URL
        self.original_secret_key = app_module.app.secret_key
        self.original_testing = app_module.app.config["TESTING"]
        self.original_developer_username = config.DEVELOPER_USERNAME
        self.original_developer_password = config.DEVELOPER_PASSWORD
        db.DATABASE_URL = ""
        db.DB_PATH = str(self.db_path)
        app_module.app.secret_key = "test-session-secret"
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.admin_key = "test-admin-key-long-enough-for-the-admin-check"
        self.admin_key_patch = patch.object(config, "ADMIN_KEY", self.admin_key)
        self.admin_key_patch.start()
        config.DEVELOPER_USERNAME = "test-developer"
        config.DEVELOPER_PASSWORD = "test-developer-password-long-enough-to-pass"
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_csrf_token"] = "test-csrf-token"
            session["developer_authenticated"] = True
            session["developer_csrf_token"] = "test-developer-csrf-token"

    def tearDown(self):
        self.admin_key_patch.stop()
        db.DATABASE_URL = self.database_url
        db.DB_PATH = self.database_path
        app_module.app.secret_key = self.original_secret_key
        app_module.app.config["TESTING"] = self.original_testing
        config.DEVELOPER_USERNAME = self.original_developer_username
        config.DEVELOPER_PASSWORD = self.original_developer_password
        self.temp_dir.cleanup()

    def test_edit_route_persists_data_and_preserves_image(self):
        event_id = db.add_event(
            "run-1",
            "location",
            "2026-11-11T08:00:00Z",
            {"location": "Old town", "image_path": "events/location.jpg"},
        )

        response = self.client.post(
            f"/admin/edit/{event_id}",
            data={
                "csrf_token": "test-csrf-token",
                "data_json": json.dumps({"location": "New town"}),
            },
        )

        self.assertEqual(response.status_code, 302)
        event = db.admin_event(event_id)
        self.assertEqual(event["d"]["location"], "New town")
        self.assertEqual(event["d"]["image_path"], "events/location.jpg")
        self.assertEqual(event["t"], "location")
        self.assertEqual(event["run"], "run-1")

    def test_admin_page_has_edit_form_and_save_button(self):
        db.add_event("run-1", "visit", "2026-11-11T08:00:00Z", {"area": ["Old"]})

        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Edit record", response.data)
        self.assertIn(b"Save changes", response.data)
        self.assertIn(b"Open report view", response.data)

    def test_report_view_enables_developer_editing_only_after_developer_login(self):
        response = self.client.get("/report")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'data-edit-enabled="true"', response.data)
        self.assertIn(b'data-csrf-token="test-developer-csrf-token"', response.data)

        anonymous = app_module.app.test_client().get("/report")
        self.assertEqual(anonymous.status_code, 200)
        self.assertIn(b'data-edit-enabled="false"', anonymous.data)
        self.assertIn(b'href="/developer"', anonymous.data)

    def test_report_edit_api_requires_developer_session_and_csrf(self):
        event_id = db.add_event("run-1", "visit", "2026-11-11T08:00:00Z", {"area": ["Old"]})
        payload = {"data": {"area": ["New"]}}

        anonymous = app_module.app.test_client().post(
            f"/api/admin/edit/{event_id}",
            json=payload,
            headers={"X-CSRF-Token": "test-csrf-token"},
        )
        self.assertEqual(anonymous.status_code, 401)

        admin_only = app_module.app.test_client()
        with admin_only.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_csrf_token"] = "test-csrf-token"
        admin_page = admin_only.get("/report")
        self.assertIn(b'data-edit-enabled="false"', admin_page.data)
        admin_edit = admin_only.post(
            f"/api/admin/edit/{event_id}",
            json=payload,
            headers={"X-CSRF-Token": "test-csrf-token"},
        )
        self.assertEqual(admin_edit.status_code, 401)

        invalid_csrf = self.client.post(
            f"/api/admin/edit/{event_id}",
            json=payload,
            headers={"X-CSRF-Token": "wrong"},
        )
        self.assertEqual(invalid_csrf.status_code, 400)
        self.assertEqual(db.admin_event(event_id)["d"]["area"], ["Old"])

    def test_report_edit_api_persists_to_database(self):
        event_id = db.add_event("run-1", "visit", "2026-11-11T08:00:00Z", {"area": ["Old"]})

        response = self.client.post(
            f"/api/admin/edit/{event_id}",
            json={"data": {"area": ["New"]}},
            headers={"X-CSRF-Token": "test-developer-csrf-token"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(db.admin_event(event_id)["d"]["area"], ["New"])

    def test_developer_login_uses_separate_username_and_password(self):
        client = app_module.app.test_client()
        login_page = client.get("/developer")
        self.assertEqual(login_page.status_code, 200)
        self.assertIn(b"Developer sign in", login_page.data)
        with client.session_transaction() as session:
            csrf_token = session["developer_csrf_token"]

        rejected = client.post(
            "/developer/login",
            data={
                "csrf_token": csrf_token,
                "username": "test-developer",
                "password": "wrong-password",
            },
        )
        self.assertEqual(rejected.status_code, 401)
        self.assertIn(b"Invalid developer username or password", rejected.data)

        with client.session_transaction() as session:
            csrf_token = session["developer_csrf_token"]
        accepted = client.post(
            "/developer/login",
            data={
                "csrf_token": csrf_token,
                "username": "test-developer",
                "password": "test-developer-password-long-enough-to-pass",
            },
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(accepted.headers["Location"], "/report")
        self.assertIn(b'data-edit-enabled="true"', client.get("/report").data)

        with client.session_transaction() as session:
            csrf_token = session["developer_csrf_token"]
        signed_out = client.post("/developer/logout", data={"csrf_token": csrf_token})
        self.assertEqual(signed_out.status_code, 302)
        self.assertIn(b'data-edit-enabled="false"', client.get("/report").data)

    def test_edit_route_rejects_invalid_csrf(self):
        event_id = db.add_event("run-1", "visit", "2026-11-11T08:00:00Z", {"area": ["Old"]})

        response = self.client.post(
            f"/admin/edit/{event_id}",
            data={"csrf_token": "wrong", "data_json": '{"area":["New"]}'},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(db.admin_event(event_id)["d"]["area"], ["Old"])

    def test_edit_route_reports_duplicate_fuel_receipt(self):
        db.add_event("run-1", "fuel", "2026-11-11T08:00:00Z", {"receipt_no": "R-123"})
        event_id = db.add_event("run-1", "fuel", "2026-11-11T09:00:00Z", {"receipt_no": "R-456"})

        response = self.client.post(
            f"/admin/edit/{event_id}",
            data={
                "csrf_token": "test-csrf-token",
                "data_json": json.dumps({"receipt_no": "R-123"}),
            },
        )

        self.assertEqual(response.status_code, 302)
        error = parse_qs(urlsplit(response.headers["Location"]).query)["error"][0]
        self.assertIn("already in use", error)
        self.assertEqual(db.admin_event(event_id)["d"]["receipt_no"], "R-456")

    def test_editing_fuel_receipt_updates_receipt_index(self):
        event_id = db.add_event("run-1", "fuel", "2026-11-11T08:00:00Z", {"receipt_no": "R-123"})

        self.client.post(
            f"/admin/edit/{event_id}",
            data={
                "csrf_token": "test-csrf-token",
                "data_json": json.dumps({"receipt_no": "R-789"}),
            },
        )

        self.assertIsNone(db.get_fuel_receipt("R-123"))
        self.assertEqual(db.get_fuel_receipt("R-789")["id"], event_id)


if __name__ == "__main__":
    unittest.main()
