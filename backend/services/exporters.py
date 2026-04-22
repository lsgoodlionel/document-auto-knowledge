from __future__ import annotations

import subprocess
import struct
import tempfile
import zlib
from dataclasses import dataclass
from pathlib import Path
import shutil
from typing import Any, Callable
from unicodedata import east_asian_width
from xml.sax.saxutils import escape

from .docx_exporter import build_docx
from .docx_parser import sanitize_name


@dataclass(frozen=True)
class ExportResult:
    filename: str
    content_type: str
    data: bytes


class ExporterError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass(frozen=True)
class Exporter:
    format_name: str
    extension: str
    content_type: str
    build: Callable[[str, list[dict[str, Any]]], bytes]


class ExportRegistry:
    def __init__(self) -> None:
        self._by_format: dict[str, Exporter] = {}

    def register(self, exporter: Exporter) -> None:
        self._by_format[exporter.format_name] = exporter

    def export(self, project_name: str, tree: list[dict[str, Any]], format_name: str) -> ExportResult:
        normalized = (format_name or "docx").lower()
        exporter = self._by_format.get(normalized)
        if exporter is None:
            supported = ", ".join(self.supported_formats())
            raise ExporterError(
                "unsupported_export_format",
                f"Unsupported export format: {format_name or 'unknown'}. Supported formats: {supported}.",
            )
        filename = f"{sanitize_name(project_name)}.{exporter.extension}"
        return ExportResult(
            filename=filename,
            content_type=exporter.content_type,
            data=exporter.build(project_name, tree),
        )

    def supported_formats(self) -> list[str]:
        return sorted(self._by_format)


def export_project_file(project_name: str, tree: list[dict[str, Any]], format_name: str = "docx") -> ExportResult:
    return registry.export(project_name, tree, format_name)


def png_export_available() -> bool:
    return shutil.which("qlmanage") is not None


def build_pdf(project_name: str, tree: list[dict[str, Any]]) -> bytes:
    lines = [project_name, ""] + outline_lines(tree)
    wrapped = wrap_lines(lines, 40)
    page_line_capacity = 45
    pages = [wrapped[index:index + page_line_capacity] for index in range(0, len(wrapped), page_line_capacity)] or [[""]]
    objects: list[bytes] = []

    def add_object(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    cid_font_id = add_object(
        b"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light "
        b"/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 4 >> /DW 1000 >>"
    )
    font_id = add_object(
        f"<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UCS2-H "
        f"/DescendantFonts [{cid_font_id} 0 R] >>".encode("ascii")
    )
    page_ids: list[int] = []
    content_ids: list[int] = []

    for page_lines in pages:
        stream = pdf_page_stream(page_lines)
        content_id = add_object(
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
        content_ids.append(content_id)
        page_id = add_object(b"")
        page_ids.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    pages_id = add_object(f"<< /Type /Pages /Count {len(page_ids)} /Kids [{kids}] >>".encode("ascii"))
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode("ascii"))

    for index, page_id in enumerate(page_ids):
        content_id = content_ids[index]
        objects[page_id - 1] = (
            f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 595 842] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode("ascii")

    return pdf_document(objects, catalog_id)


def pdf_page_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 12 Tf", "50 790 Td", "16 TL"]
    for index, line in enumerate(lines):
        text = encode_pdf_text(line)
        if index == 0:
            commands.append(f"<{text}> Tj")
        else:
            commands.append("T*")
            commands.append(f"<{text}> Tj")
    commands.append("ET")
    return "\n".join(commands).encode("ascii")


def pdf_document(objects: list[bytes], catalog_id: int) -> bytes:
    buffer = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(buffer))
        buffer.extend(f"{index} 0 obj\n".encode("ascii"))
        buffer.extend(body)
        buffer.extend(b"\nendobj\n")
    xref_offset = len(buffer)
    buffer.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    buffer.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    buffer.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF".encode("ascii")
    )
    return bytes(buffer)


def encode_pdf_text(value: str) -> str:
    if not value:
        return ""
    return value.encode("utf-16-be").hex().upper()


def build_freemind_mm(project_name: str, tree: list[dict[str, Any]]) -> bytes:
    children = "\n".join(mm_node(node, 1) for node in tree)
    xml = "\n".join(
        [
            '<?xml version="1.0" encoding="UTF-8"?>',
            "<map version=\"1.0.1\">",
            f"  <node TEXT=\"{escape(project_name)}\">",
            children,
            "  </node>",
            "</map>",
        ]
    )
    return xml.encode("utf-8")


def mm_node(node: dict[str, Any], depth: int) -> str:
    indent = "  " * (depth + 1)
    title = escape(str(node.get("title") or node.get("name") or "untitled"))
    note = (node.get("note") or "").strip()
    parts = [f'{indent}<node TEXT="{title}">']
    if note:
        note_html = "".join(f"<p>{escape(line)}</p>" for line in note.splitlines() if line.strip()) or "<p></p>"
        parts.append(
            f"{indent}  <richcontent TYPE=\"NOTE\"><html><body>{note_html}</body></html></richcontent>"
        )
    for child in node.get("children", []):
        parts.append(mm_node(child, depth + 1))
    parts.append(f"{indent}</node>")
    return "\n".join(parts)


def build_png(project_name: str, tree: list[dict[str, Any]]) -> bytes:
    if not png_export_available():
        raise ExporterError("png_export_unavailable", "PNG export is not available on this platform.")
    html = build_outline_html(project_name, tree)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        html_path = tmp_path / "outline.html"
        html_path.write_text(html, encoding="utf-8")
        command = ["qlmanage", "-t", "-s", "2400", "-o", tmpdir, str(html_path)]
        try:
            subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, subprocess.CalledProcessError) as exc:
            raise ExporterError("png_export_unavailable", "PNG export is not available on this platform.") from exc
        png_path = tmp_path / "outline.html.png"
        if not png_path.exists():
            raise ExporterError("png_export_unavailable", "PNG export did not produce an output file.")
        return png_path.read_bytes()


def outline_lines(nodes: list[dict[str, Any]], depth: int = 0) -> list[str]:
    lines: list[str] = []
    for node in nodes:
        title = str(node.get("title") or node.get("name") or "untitled")
        lines.append(f"{'  ' * depth}- {title}")
        note = (node.get("note") or "").strip()
        if note:
            for line in note.splitlines():
                if line.strip():
                    lines.append(f"{'  ' * (depth + 1)}{line.strip()}")
        lines.extend(outline_lines(node.get("children", []), depth + 1))
    return lines


def wrap_lines(lines: list[str], width: int) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if not line:
            wrapped.append("")
            continue
        current = ""
        current_width = 0
        for char in line:
            char_width = display_width(char)
            if current and current_width + char_width > width:
                wrapped.append(current)
                current = char
                current_width = char_width
            else:
                current += char
                current_width += char_width
        wrapped.append(current)
    return wrapped


def display_width(value: str) -> int:
    return 2 if east_asian_width(value) in {"W", "F"} else 1


def build_outline_html(project_name: str, tree: list[dict[str, Any]]) -> str:
    body = build_outline_html_nodes(tree)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <title>{escape(project_name)}</title>
    <style>
      body {{
        margin: 0;
        padding: 40px 48px;
        font-family: "Hiragino Sans GB", "PingFang SC", "Microsoft YaHei", sans-serif;
        color: #1c2430;
        background: linear-gradient(180deg, #fbf8f2 0%, #f1efe8 100%);
      }}
      h1 {{
        margin: 0 0 20px;
        font-size: 34px;
      }}
      .tree {{
        display: grid;
        gap: 10px;
        font-size: 16px;
        line-height: 1.6;
      }}
      .node {{
        background: rgba(255,255,255,0.9);
        border: 1px solid rgba(30, 46, 74, 0.12);
        border-radius: 14px;
        padding: 10px 14px;
        margin-left: calc(var(--depth) * 24px);
        box-shadow: 0 10px 24px rgba(28, 36, 48, 0.06);
      }}
      .title {{
        font-weight: 700;
      }}
      .note {{
        margin-top: 6px;
        color: #4a5565;
        white-space: pre-wrap;
      }}
    </style>
  </head>
  <body>
    <h1>{escape(project_name)}</h1>
    <div class="tree">{body}</div>
  </body>
</html>"""


def build_outline_html_nodes(nodes: list[dict[str, Any]], depth: int = 0) -> str:
    parts: list[str] = []
    for node in nodes:
        title = escape(str(node.get("title") or node.get("name") or "untitled"))
        note = escape(str(node.get("note") or "").strip())
        parts.append(f'<section class="node" style="--depth:{depth}"><div class="title">{title}</div>')
        if note:
            parts.append(f'<div class="note">{note}</div>')
        parts.append("</section>")
        if node.get("children"):
            parts.append(build_outline_html_nodes(node["children"], depth + 1))
    return "".join(parts)


registry = ExportRegistry()
registry.register(
    Exporter(
        format_name="docx",
        extension="docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        build=build_docx,
    )
)
registry.register(Exporter(format_name="pdf", extension="pdf", content_type="application/pdf", build=build_pdf))
registry.register(Exporter(format_name="mm", extension="mm", content_type="application/x-freemind", build=build_freemind_mm))
registry.register(Exporter(format_name="png", extension="png", content_type="image/png", build=build_png))
