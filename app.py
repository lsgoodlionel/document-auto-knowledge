from __future__ import annotations

import json
import io
import re
import zipfile
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET
import posixpath


ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "web"
HOST = "127.0.0.1"
PORT = 8000
MAX_UPLOAD_SIZE = 15 * 1024 * 1024
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def json_response(handler: BaseHTTPRequestHandler, status: int, payload: dict[str, Any]) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def binary_response(
    handler: BaseHTTPRequestHandler,
    status: int,
    content_type: str,
    data: bytes,
    filename: str | None = None,
) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(data)))
    if filename:
        handler.send_header("Content-Disposition", f'attachment; filename="{filename}"')
    handler.end_headers()
    handler.wfile.write(data)


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned or "untitled"


@dataclass
class FolderNode:
    name: str
    level: int
    children: list["FolderNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "FolderNode":
        name = sanitize_name(str(payload.get("name", "")).strip())
        level = max(1, int(payload.get("level", 1)))
        children_payload = payload.get("children", [])
        children = []
        if isinstance(children_payload, list):
            children = [cls.from_dict(child) for child in children_payload if isinstance(child, dict)]
        return cls(name=name, level=level, children=children)


class DocxFolderParser:
    def parse(self, content: bytes) -> dict[str, Any]:
        with zipfile.ZipFile(io.BytesIO(content)) as docx:
            document_root = ET.fromstring(docx.read("word/document.xml"))
            styles_root = ET.fromstring(docx.read("word/styles.xml")) if self._has_file(docx, "word/styles.xml") else None

        style_map = self._build_style_map(styles_root) if styles_root is not None else {}
        headings = self._extract_headings(document_root, style_map)
        tree = self._build_tree(headings)
        return {
            "headings": headings,
            "tree": [node.to_dict() for node in tree],
            "bashScript": self._build_bash_script(tree),
            "powershellScript": self._build_powershell_script(tree),
        }

    @staticmethod
    def _has_file(docx: zipfile.ZipFile, filename: str) -> bool:
        try:
            docx.getinfo(filename)
            return True
        except KeyError:
            return False

    def _build_style_map(self, styles_root: ET.Element) -> dict[str, int]:
        mapping: dict[str, int] = {}
        for style in styles_root.findall("w:style", NS):
            style_id = style.attrib.get(f"{{{NS['w']}}}styleId")
            if not style_id:
                continue

            outline = style.find("w:pPr/w:outlineLvl", NS)
            if outline is not None:
                try:
                    mapping[style_id] = int(outline.attrib.get(f"{{{NS['w']}}}val", "0")) + 1
                    continue
                except ValueError:
                    pass

            match = re.search(r"Heading(\d+)$", style_id, re.IGNORECASE)
            if match:
                mapping[style_id] = int(match.group(1))
                continue

            name = style.find("w:name", NS)
            if name is None:
                continue
            style_name = name.attrib.get(f"{{{NS['w']}}}val", "")
            match = re.search(r"heading\s*(\d+)", style_name, re.IGNORECASE)
            if match:
                mapping[style_id] = int(match.group(1))
        return mapping

    def _extract_headings(self, document_root: ET.Element, style_map: dict[str, int]) -> list[dict[str, Any]]:
        headings: list[dict[str, Any]] = []
        for para in document_root.findall(".//w:body/w:p", NS):
            text = "".join(node.text or "" for node in para.findall(".//w:t", NS)).strip()
            if not text:
                continue

            style_id = self._paragraph_style_id(para)
            level, source = self._resolve_level(para, style_id, style_map)
            if level is None:
                continue

            headings.append(
                {
                    "title": text,
                    "folderName": sanitize_name(text),
                    "level": level,
                    "source": source,
                }
            )
        return headings

    def _resolve_level(
        self,
        para: ET.Element,
        style_id: str | None,
        style_map: dict[str, int],
    ) -> tuple[int | None, str | None]:
        direct_outline_level = self._paragraph_outline_level(para)
        if direct_outline_level is not None:
            return direct_outline_level, "outline"

        style_level = style_map.get(style_id)
        if style_level is not None:
            return style_level, "style"

        fallback_level = self._fallback_heading_level(style_id)
        if fallback_level is not None:
            return fallback_level, "style"

        return None, None

    @staticmethod
    def _paragraph_style_id(para: ET.Element) -> str | None:
        node = para.find("w:pPr/w:pStyle", NS)
        if node is None:
            return None
        return node.attrib.get(f"{{{NS['w']}}}val")

    @staticmethod
    def _paragraph_outline_level(para: ET.Element) -> int | None:
        node = para.find("w:pPr/w:outlineLvl", NS)
        if node is None:
            return None

        raw_value = node.attrib.get(f"{{{NS['w']}}}val")
        if raw_value is None:
            return None

        try:
            return int(raw_value) + 1
        except ValueError:
            return None

    @staticmethod
    def _fallback_heading_level(style_id: str | None) -> int | None:
        if not style_id:
            return None
        match = re.search(r"heading\s*(\d+)", style_id, re.IGNORECASE)
        if match:
            return int(match.group(1))
        return None

    def _build_tree(self, headings: list[dict[str, Any]]) -> list[FolderNode]:
        root = FolderNode(name="root", level=0)
        stack: list[FolderNode] = [root]
        for heading in headings:
            level = max(1, int(heading["level"]))
            node = FolderNode(name=heading["folderName"], level=level)

            while stack and stack[-1].level >= level:
                stack.pop()
            if not stack:
                stack = [root]

            stack[-1].children.append(node)
            stack.append(node)
        return root.children

    def _build_bash_script(self, tree: list[FolderNode]) -> str:
        lines = ["#!/usr/bin/env bash", "set -euo pipefail", ""]
        for path in self._iter_paths(tree):
            lines.append(f'mkdir -p "{path}"')
        return "\n".join(lines) + "\n"

    def _build_powershell_script(self, tree: list[FolderNode]) -> str:
        lines = ["$ErrorActionPreference = 'Stop'", ""]
        for path in self._iter_paths(tree):
            escaped = path.replace("'", "''")
            lines.append(f"New-Item -ItemType Directory -Force -Path '{escaped}' | Out-Null")
        return "\n".join(lines) + "\n"

    def _iter_paths(self, tree: list[FolderNode], prefix: str = "") -> list[str]:
        paths: list[str] = []
        for node in tree:
            current = f"{prefix}/{node.name}" if prefix else node.name
            paths.append(current)
            paths.extend(self._iter_paths(node.children, current))
        return paths


class FolderArchiveBuilder:
    def build_zip(self, tree: list[FolderNode]) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in self._iter_directory_entries(tree):
                info = zipfile.ZipInfo(f"{path}/")
                archive.writestr(info, b"")
        return buffer.getvalue()

    def _iter_directory_entries(self, tree: list[FolderNode], prefix: str = "") -> list[str]:
        entries: list[str] = []
        for node in tree:
            current = posixpath.join(prefix, node.name) if prefix else node.name
            entries.append(current)
            entries.extend(self._iter_directory_entries(node.children, current))
        return entries


class AppHandler(BaseHTTPRequestHandler):
    parser = DocxFolderParser()
    archive_builder = FolderArchiveBuilder()

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self._serve_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return

        file_path = (STATIC_DIR / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(STATIC_DIR.resolve())) or not file_path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return

        content_type = self._guess_type(file_path.suffix)
        self._serve_file(file_path, content_type)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/parse":
            self._handle_parse()
            return
        if path == "/api/download-zip":
            self._handle_download_zip()
            return

        self.send_error(HTTPStatus.NOT_FOUND, "API not found")

    def _handle_parse(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "请求体为空。"})
            return
        if length > MAX_UPLOAD_SIZE:
            json_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "文件太大，请控制在 15MB 内。"})
            return

        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "请求格式无效。"})
            return

        filename = payload.get("filename", "")
        file_b64 = payload.get("file")
        if not filename.lower().endswith(".docx") or not isinstance(file_b64, str):
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "请上传 .docx 格式的 Word 文档。"})
            return

        try:
            content = decode_base64(file_b64)
            result = self.parser.parse(content)
        except zipfile.BadZipFile:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "文件不是有效的 .docx 文档。"})
            return
        except KeyError as exc:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": f"文档缺少必要内容：{exc.args[0]}。"})
            return
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"解析失败：{exc}"})
            return

        json_response(self, HTTPStatus.OK, result)

    def _handle_download_zip(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "请求体为空。"})
            return
        if length > MAX_UPLOAD_SIZE:
            json_response(self, HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "目录结构过大，请稍后重试。"})
            return

        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "请求格式无效。"})
            return

        tree_payload = payload.get("tree")
        export_name = sanitize_name(str(payload.get("name", "folder-system")).strip())
        if not isinstance(tree_payload, list) or not tree_payload:
            json_response(self, HTTPStatus.BAD_REQUEST, {"error": "没有可导出的目录结构。"})
            return

        try:
            tree = [FolderNode.from_dict(node) for node in tree_payload if isinstance(node, dict)]
            archive = self.archive_builder.build_zip(tree)
        except Exception as exc:
            json_response(self, HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"压缩包生成失败：{exc}"})
            return

        binary_response(self, HTTPStatus.OK, "application/zip", archive, f"{export_name}.zip")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _serve_file(self, file_path: Path, content_type: str) -> None:
        data = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    @staticmethod
    def _guess_type(suffix: str) -> str:
        return {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
        }.get(suffix, "application/octet-stream")


def decode_base64(data: str) -> bytes:
    import base64

    return base64.b64decode(data.encode("utf-8"), validate=True)


def run() -> None:
    server = ThreadingHTTPServer((HOST, PORT), AppHandler)
    print(f"Server running at http://{HOST}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    run()
