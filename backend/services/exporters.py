from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass
from typing import Any, Callable
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


def build_pdf(project_name: str, tree: list[dict[str, Any]]) -> bytes:
    lines = [project_name, ""] + outline_lines(tree)
    wrapped = wrap_lines(lines, 68)
    page_line_capacity = 45
    pages = [wrapped[index:index + page_line_capacity] for index in range(0, len(wrapped), page_line_capacity)] or [[""]]
    objects: list[bytes] = []

    def add_object(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    font_id = add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
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
    commands = ["BT", "/F1 12 Tf", "50 790 Td", "14 TL"]
    for index, line in enumerate(lines):
        text = escape_pdf_text(line)
        if index == 0:
            commands.append(f"({text}) Tj")
        else:
            commands.append("T*")
            commands.append(f"({text}) Tj")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


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


def escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def build_freemind_mm(project_name: str, tree: list[dict[str, Any]]) -> bytes:
    children = "".join(mm_node(node) for node in tree)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<map version="1.0.1"><node TEXT="{escape(project_name)}">{children}</node></map>'
    )
    return xml.encode("utf-8")


def mm_node(node: dict[str, Any]) -> str:
    title = escape(str(node.get("title") or node.get("name") or "untitled"))
    note = (node.get("note") or "").strip()
    note_xml = ""
    if note:
        note_xml = (
            '<richcontent TYPE="NOTE"><html><body>'
            f"<p>{escape(note).replace(chr(10), '</p><p>')}</p>"
            "</body></html></richcontent>"
        )
    children = "".join(mm_node(child) for child in node.get("children", []))
    return f'<node TEXT="{title}">{note_xml}{children}</node>'


def build_png(project_name: str, tree: list[dict[str, Any]]) -> bytes:
    lines = [project_name] + outline_lines(tree)
    width = 480
    row_height = 10
    height = max(64, min(1200, 24 + len(lines) * row_height))
    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        for x in range(width):
            pixels.extend(png_pixel(x, y, width, height, lines, row_height))

    raw = zlib.compress(bytes(pixels), level=9)
    return b"".join(
        [
            b"\x89PNG\r\n\x1a\n",
            png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
            png_chunk(b"IDAT", raw),
            png_chunk(b"IEND", b""),
        ]
    )


def png_pixel(x: int, y: int, width: int, height: int, lines: list[str], row_height: int) -> bytes:
    if y < 18:
        return bytes((43, 87, 151))
    if y >= height - 14:
        return bytes((26, 34, 48))
    row_index = min(max((y - 24) // row_height, 0), max(len(lines) - 1, 0))
    indent = min(row_index_indent(lines[row_index]) * 24, width - 20)
    if x < indent:
        return bytes((245, 247, 250))
    stripe = row_index % 2
    if stripe == 0:
        return bytes((236, 242, 248))
    return bytes((224, 233, 243))


def row_index_indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + chunk_type
        + data
        + struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    )


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
        current = line
        while len(current) > width:
            wrapped.append(current[:width])
            current = current[width:]
        wrapped.append(current)
    return wrapped


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
