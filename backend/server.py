from __future__ import annotations

import json
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from .config import FRONTEND_DIR, HOST, MAX_UPLOAD_SIZE, PORT
from .db import init_db
from .services import auth, projects
from .services.exporters import ExporterError, export_project_file
from .services.importers import ImporterError


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: Any) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    extra_headers = getattr(handler, "_extra_headers", {})
    for key, value in extra_headers.items():
        handler.send_header(key, value)
    handler._extra_headers = {}
    handler.end_headers()
    handler.wfile.write(data)


def error_response(handler: BaseHTTPRequestHandler, status: int, code: str, message: str) -> None:
    json_response(handler, status, {"error": {"code": code, "message": message}})


def handle_api_error(handler: BaseHTTPRequestHandler, exc: Exception) -> None:
    if isinstance(exc, ApiError):
        error_response(handler, exc.status, exc.code, exc.message)
    elif isinstance(exc, (ImporterError, ExporterError, auth.AuthError)):
        error_response(handler, exc.status, exc.code, exc.message)
    elif isinstance(exc, KeyError):
        error_response(handler, HTTPStatus.NOT_FOUND, "not_found", str(exc).strip("'"))
    elif isinstance(exc, (ValueError, json.JSONDecodeError)):
        error_response(handler, HTTPStatus.BAD_REQUEST, "bad_request", str(exc))
    else:
        error_response(handler, HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "Internal server error")


def binary_response(handler: BaseHTTPRequestHandler, status: int, content_type: str, data: bytes, filename: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Content-Disposition", content_disposition(filename))
    handler.end_headers()
    handler.wfile.write(data)


def content_disposition(filename: str) -> str:
    fallback = ascii_filename_fallback(filename)
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{encoded}"


def ascii_filename_fallback(filename: str) -> str:
    fallback = filename.encode("ascii", "ignore").decode("ascii")
    fallback = re.sub(r'[\r\n"\\;]', "_", fallback)
    fallback = re.sub(r"\s+", " ", fallback).strip()
    extension = filename.rsplit(".", 1)[-1].encode("ascii", "ignore").decode("ascii") if "." in filename else ""
    if not fallback or fallback.startswith("."):
        fallback = f"download.{extension}" if extension else "download"
    if "." not in fallback and extension:
        if extension:
            fallback = f"{fallback}.{extension}"
    return fallback


class ApiServer(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/api/auth/me":
            self._handle_auth_me()
            return
        if path == "/api/projects":
            json_response(self, HTTPStatus.OK, {"projects": projects.list_projects()})
            return
        if path.startswith("/api/projects/") and path.endswith("/export"):
            self._handle_export(path, parsed_url.query)
            return
        if path.startswith("/api/projects/"):
            self._handle_get_project(path)
            return
        if path.startswith("/api/"):
            error_response(self, HTTPStatus.NOT_FOUND, "not_found", "API not found")
            return
        self._serve_frontend(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/auth/login":
            self._handle_auth_login()
            return
        if path == "/api/auth/logout":
            self._handle_auth_logout()
            return
        if path == "/api/projects/import":
            self._handle_import()
            return
        if path == "/api/projects/import-docx":
            self._handle_import()
            return
        if path.startswith("/api/projects/") and path.endswith("/attachments"):
            self._handle_attach_project_subtree(path)
            return
        if path.startswith("/api/projects/") and path.endswith("/nodes"):
            self._handle_create_node(path)
            return
        if path.startswith("/api/nodes/") and path.endswith("/move"):
            self._handle_move_node(path)
            return
        error_response(self, HTTPStatus.NOT_FOUND, "not_found", "API not found")

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/projects/"):
            self._handle_rename_project(path)
            return
        if path.startswith("/api/nodes/") and path.endswith("/move"):
            self._handle_move_node(path)
            return
        if path.startswith("/api/nodes/"):
            self._handle_update_node(path)
            return
        error_response(self, HTTPStatus.NOT_FOUND, "not_found", "API not found")

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/api/projects/"):
            self._handle_delete_project(path)
            return
        if path.startswith("/api/nodes/"):
            self._handle_delete_node(path)
            return
        error_response(self, HTTPStatus.NOT_FOUND, "not_found", "API not found")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        if length > MAX_UPLOAD_SIZE:
            raise ValueError("request too large")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _handle_import(self) -> None:
        try:
            payload = self._read_json()
            user = auth.get_optional_user_for_token(self._session_token())
            project = projects.create_project_from_upload(
                payload.get("filename", ""),
                payload.get("file", ""),
                owner_user_id=user["id"] if user else None,
            )
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.CREATED, {"project": project})

    def _handle_auth_login(self) -> None:
        try:
            payload = self._read_json()
            user, cookie_header = auth.login(payload.get("username", ""), payload.get("password", ""))
            self._extra_headers = {"Set-Cookie": cookie_header}
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"user": user})

    def _handle_auth_logout(self) -> None:
        try:
            self._extra_headers = {"Set-Cookie": auth.logout(self._session_token())}
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"ok": True})

    def _handle_auth_me(self) -> None:
        try:
            user = auth.get_user_for_token(self._session_token())
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"user": user})

    def _handle_get_project(self, path: str) -> None:
        try:
            project_id = parse_id(path.rstrip("/").split("/")[-1], "project id")
            project = projects.get_project(project_id)
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"project": project})

    def _handle_rename_project(self, path: str) -> None:
        try:
            project_id = parse_id(path.rstrip("/").split("/")[-1], "project id")
            payload = self._read_json()
            project = projects.rename_project(project_id, payload.get("name", "untitled"))
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"project": project})

    def _handle_delete_project(self, path: str) -> None:
        try:
            project_id = parse_id(path.rstrip("/").split("/")[-1], "project id")
            projects.delete_project(project_id)
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"ok": True})

    def _handle_create_node(self, path: str) -> None:
        try:
            project_id = parse_id(path.split("/")[3], "project id")
            payload = self._read_json()
            node = projects.create_node(project_id, payload.get("parentId"), payload.get("title", "新节点"), payload.get("note", ""))
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.CREATED, {"node": node})

    def _handle_attach_project_subtree(self, path: str) -> None:
        try:
            project_id = parse_id(path.split("/")[3], "project id")
            payload = self._read_json()
            source_root_node_id = payload.get("sourceRootNodeId")
            target_parent_id = payload.get("targetParentId")
            project = projects.attach_project_subtree(
                project_id,
                parse_id(str(target_parent_id), "target parent id") if target_parent_id is not None else None,
                parse_id(str(payload.get("sourceProjectId")), "source project id"),
                parse_id(str(source_root_node_id), "source root node id") if source_root_node_id is not None else None,
            )
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"project": project})

    def _handle_update_node(self, path: str) -> None:
        try:
            node_id = parse_id(path.rstrip("/").split("/")[-1], "node id")
            payload = self._read_json()
            node = projects.update_node(node_id, payload.get("title", "untitled"), payload.get("note", ""))
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"node": node})

    def _handle_delete_node(self, path: str) -> None:
        try:
            node_id = parse_id(path.rstrip("/").split("/")[-1], "node id")
            projects.delete_node(node_id)
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"ok": True})

    def _handle_move_node(self, path: str) -> None:
        try:
            node_id = parse_id(path.rstrip("/").split("/")[-2], "node id")
            payload = self._read_json()
            node = projects.move_node(node_id, payload.get("parentId"), payload.get("position"))
        except Exception as exc:
            handle_api_error(self, exc)
            return
        json_response(self, HTTPStatus.OK, {"node": node})

    def _handle_export(self, path: str, query: str) -> None:
        try:
            project_id = parse_id(path.split("/")[3], "project id")
            format_name = parse_qs(query).get("format", ["docx"])[0] or "docx"
            project = projects.get_project(project_id)

            exported = export_project_file(project["name"], project["tree"], format_name)
            filename, content_type, content = exported.filename, exported.content_type, exported.data
        except Exception as exc:
            handle_api_error(self, exc)
            return
        binary_response(self, HTTPStatus.OK, content_type, content, filename)

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

    def _session_token(self) -> str | None:
        return auth.session_token_from_cookie(self.headers.get("Cookie"))


def guess_type(suffix: str) -> str:
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }.get(suffix, "application/octet-stream")


def parse_id(value: str, label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ApiError(HTTPStatus.BAD_REQUEST, "bad_request", f"Invalid {label}") from exc


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
