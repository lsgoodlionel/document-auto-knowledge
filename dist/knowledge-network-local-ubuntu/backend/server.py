from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import FRONTEND_DIR, HOST, MAX_UPLOAD_SIZE, PORT
from .db import init_db
from .services import projects


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def binary_response(handler: BaseHTTPRequestHandler, status: int, content_type: str, data: bytes, filename: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(data)


class ApiServer(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/projects":
            json_response(self, HTTPStatus.OK, {"projects": projects.list_projects()})
            return
        if path.startswith("/api/projects/") and path.endswith("/export"):
            self._handle_export_docx(path)
            return
        if path.startswith("/api/projects/"):
            self._handle_get_project(path)
            return
        self._serve_frontend(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/projects/import-docx":
            self._handle_import_docx()
            return
        if path.startswith("/api/projects/") and path.endswith("/nodes"):
            self._handle_create_node(path)
            return
        json_response(self, HTTPStatus.NOT_FOUND, {"error": "API not found"})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/nodes/"):
            self._handle_update_node(path)
            return
        json_response(self, HTTPStatus.NOT_FOUND, {"error": "API not found"})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/nodes/"):
            self._handle_delete_node(path)
            return
        json_response(self, HTTPStatus.NOT_FOUND, {"error": "API not found"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > MAX_UPLOAD_SIZE:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_import_docx(self) -> None:
        try:
            payload = self._read_json()
            project = projects.create_project_from_docx(payload.get("filename", ""), payload.get("file", ""))
        except Exception as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        json_response(self, HTTPStatus.CREATED, {"project": project})

    def _handle_get_project(self, path: str) -> None:
        try:
            project_id = int(path.rstrip("/").split("/")[-1])
            project = projects.get_project(project_id)
        except Exception as exc:
            json_response(self, HTTPStatus.NOT_FOUND, {"error": str(exc)})
            return
        json_response(self, HTTPStatus.OK, {"project": project})

    def _handle_create_node(self, path: str) -> None:
        try:
            project_id = int(path.split("/")[3])
            payload = self._read_json()
            node = projects.create_node(project_id, payload.get("parentId"), payload.get("title", "新节点"), payload.get("note", ""))
        except Exception as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        json_response(self, HTTPStatus.CREATED, {"node": node})

    def _handle_update_node(self, path: str) -> None:
        try:
            node_id = int(path.rstrip("/").split("/")[-1])
            payload = self._read_json()
            node = projects.update_node(node_id, payload.get("title", "untitled"), payload.get("note", ""))
        except Exception as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        json_response(self, HTTPStatus.OK, {"node": node})

    def _handle_delete_node(self, path: str) -> None:
        try:
            node_id = int(path.rstrip("/").split("/")[-1])
            projects.delete_node(node_id)
        except Exception as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        json_response(self, HTTPStatus.OK, {"ok": True})

    def _handle_export_docx(self, path: str) -> None:
        try:
            project_id = int(path.split("/")[3])
            filename, content = projects.export_project_docx(project_id)
        except Exception as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        binary_response(self, HTTPStatus.OK, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", content, filename)

    def _serve_frontend(self, path: str) -> None:
        if path == "/":
            file_path = FRONTEND_DIR / "index.html"
        else:
            file_path = (FRONTEND_DIR / path.lstrip("/")).resolve()

        if not str(file_path).startswith(str(FRONTEND_DIR.resolve())) or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", guess_type(file_path.suffix))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def guess_type(suffix: str) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }.get(suffix, "application/octet-stream")


def run() -> None:
    init_db()
    server = ThreadingHTTPServer((HOST, PORT), ApiServer)
    print(f"Server running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
