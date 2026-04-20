from __future__ import annotations

import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

from backend import db
from backend.server import ApiServer
from backend.services import projects


class BackendApiSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "smoke.sqlite3"
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

    def tearDown(self) -> None:
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def test_project_node_crud_move_and_delete(self) -> None:
        with db.connect() as conn:
            project_id = projects.create_project(conn, "Smoke")
            conn.commit()

        renamed = projects.rename_project(project_id, "Renamed Smoke")
        self.assertEqual(renamed["name"], "Renamed Smoke")

        first = projects.create_node(project_id, None, "First")
        second = projects.create_node(project_id, None, "Second")
        child = projects.create_node(project_id, first["id"], "Child")

        moved = projects.move_node(child["id"], None, 0)
        self.assertIsNone(moved["parentId"])
        self.assertEqual(moved["position"], 0)

        reordered = projects.move_node(second["id"], None, 0)
        self.assertEqual(reordered["position"], 0)

        tree = projects.get_project(project_id)["tree"]
        self.assertEqual([node["title"] for node in tree], ["Second", "Child", "First"])

        updated = projects.update_node(first["id"], "First Updated", "note")
        self.assertEqual(updated["note"], "note")

        projects.delete_node(child["id"])
        tree = projects.get_project(project_id)["tree"]
        self.assertEqual([node["title"] for node in tree], ["Second", "First Updated"])

        projects.delete_project(project_id)
        with self.assertRaises(KeyError):
            projects.get_project(project_id)

    def test_error_payload_shape(self) -> None:
        from backend.server import error_response

        class Handler:
            def __init__(self) -> None:
                self.status = None
                self.headers: dict[str, str] = {}
                self.body = b""
                self.wfile = self

            def send_response(self, status: int) -> None:
                self.status = status

            def send_header(self, key: str, value: str) -> None:
                self.headers[key] = value

            def end_headers(self) -> None:
                pass

            def write(self, data: bytes) -> None:
                self.body += data

        handler = Handler()
        error_response(handler, 400, "bad_request", "Bad request")

        self.assertEqual(handler.status, 400)
        self.assertEqual(
            json.loads(handler.body.decode("utf-8")),
            {"error": {"code": "bad_request", "message": "Bad request"}},
        )


class HttpApiSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "http-smoke.sqlite3"
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ApiServer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def request(self, method: str, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, json.loads(data.decode("utf-8"))

    def test_project_and_node_api_smoke(self) -> None:
        with db.connect() as conn:
            project_id = projects.create_project(conn, "HTTP Smoke")
            conn.commit()

        status, payload = self.request("PUT", f"/api/projects/{project_id}", {"name": "HTTP Renamed"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["project"]["name"], "HTTP Renamed")

        status, payload = self.request("POST", f"/api/projects/{project_id}/nodes", {"title": "First"})
        self.assertEqual(status, 201)
        first_id = payload["node"]["id"]

        status, payload = self.request("POST", f"/api/projects/{project_id}/nodes", {"title": "Second"})
        self.assertEqual(status, 201)
        second_id = payload["node"]["id"]

        status, payload = self.request("PUT", f"/api/nodes/{second_id}/move", {"parentId": None, "position": 0})
        self.assertEqual(status, 200)
        self.assertEqual(payload["node"]["position"], 0)

        status, payload = self.request("GET", f"/api/projects/{project_id}")
        self.assertEqual(status, 200)
        self.assertEqual([node["title"] for node in payload["project"]["tree"]], ["Second", "First"])

        status, payload = self.request("DELETE", f"/api/nodes/{first_id}")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})

        status, payload = self.request("DELETE", f"/api/projects/{project_id}")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})

        status, payload = self.request("GET", f"/api/projects/{project_id}")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

        status, payload = self.request("GET", "/api/missing")
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": {"code": "not_found", "message": "API not found"}})


if __name__ == "__main__":
    unittest.main()
