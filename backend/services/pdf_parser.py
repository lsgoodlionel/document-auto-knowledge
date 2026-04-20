from __future__ import annotations

import re
import zlib
from dataclasses import dataclass, field
from typing import Any

from .docx_parser import FolderNode, sanitize_name


class PdfParserError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PdfHeading:
    title: str
    level: int
    note_lines: list[str] = field(default_factory=list)


class PdfParser:
    def parse(self, content: bytes) -> dict[str, Any]:
        if not content.startswith(b"%PDF-"):
            raise PdfParserError("invalid_pdf", "PDF import failed: the file does not look like a PDF document.")

        lines = normalize_lines(self.extract_text(content))
        if not lines:
            raise PdfParserError(
                "pdf_text_not_found",
                "PDF import failed: no selectable text was found. Scanned PDFs need an OCR plugin.",
            )

        headings = build_headings(lines)
        return {
            "headings": [
                {
                    "title": heading.title,
                    "folderName": sanitize_name(heading.title),
                    "level": heading.level,
                    "source": "pdf-text",
                    "note": "\n".join(heading.note_lines),
                }
                for heading in headings
            ],
            "tree": build_tree(headings),
            "warnings": [],
            "pages": max(1, content.count(b"/Type /Page")),
        }

    def extract_text(self, content: bytes) -> str:
        chunks: list[str] = []
        for stream in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", content, re.DOTALL):
            raw = stream.group(1).strip(b"\r\n")
            for data in stream_variants(raw):
                chunks.extend(extract_text_strings(data))
        return "\n".join(chunks)


def stream_variants(raw: bytes) -> list[bytes]:
    variants = [raw]
    try:
        variants.append(zlib.decompress(raw))
    except zlib.error:
        pass
    return variants


def extract_text_strings(data: bytes) -> list[str]:
    text = data.decode("latin-1", errors="ignore")
    found: list[str] = []

    for array_match in re.finditer(r"\[(.*?)\]\s*TJ", text, re.DOTALL):
        parts = [decode_pdf_string(match.group(1)) for match in re.finditer(r"\(((?:\\.|[^\\()])*)\)", array_match.group(1))]
        joined = "".join(part for part in parts if part)
        if joined:
            found.append(joined)

    for match in re.finditer(r"\((?:\\.|[^\\()])*\)\s*Tj", text):
        decoded = decode_pdf_string(match.group(0).rsplit(")", 1)[0][1:])
        if decoded:
            found.append(decoded)

    return found


def decode_pdf_string(value: str) -> str:
    output: list[str] = []
    i = 0
    while i < len(value):
        char = value[i]
        if char != "\\":
            output.append(char)
            i += 1
            continue

        i += 1
        if i >= len(value):
            break
        escaped = value[i]
        if escaped in "nr":
            output.append("\n")
        elif escaped == "t":
            output.append("\t")
        elif escaped in "\\()":
            output.append(escaped)
        elif escaped in "\n\r":
            pass
        elif escaped.isdigit():
            octal = escaped
            for _ in range(2):
                if i + 1 < len(value) and value[i + 1].isdigit():
                    i += 1
                    octal += value[i]
                else:
                    break
            try:
                output.append(chr(int(octal, 8)))
            except ValueError:
                pass
        else:
            output.append(escaped)
        i += 1
    return "".join(output).strip()


def normalize_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def build_headings(lines: list[str]) -> list[PdfHeading]:
    headings: list[PdfHeading] = []
    current: PdfHeading | None = None
    for line in lines:
        level = infer_heading_level(line)
        if level is None:
            if current is not None:
                current.note_lines.append(line)
            continue
        current = PdfHeading(title=line, level=level)
        headings.append(current)

    if not headings:
        headings.append(PdfHeading(title=lines[0], level=1, note_lines=lines[1:]))
    return headings


def infer_heading_level(line: str) -> int | None:
    if len(line) > 120:
        return None
    numbered = re.match(r"^(\d+(?:\.\d+){0,5})[\s、.)-]+", line)
    if numbered:
        return min(numbered.group(1).count(".") + 1, 6)
    if re.match(r"^(chapter|section|part)\s+\w+", line, re.IGNORECASE):
        return 1
    if re.match(r"^第[一二三四五六七八九十百千万0-9]+[章节部分篇]", line):
        return 1
    if len(line) <= 48 and " " not in line and not line.endswith(("。", ".", "，", ",")):
        return 1
    if len(line) <= 48 and re.search(r"[\u4e00-\u9fff]", line) and not line.endswith(("。", "，")):
        return 1
    return None


def build_tree(headings: list[PdfHeading]) -> list[dict[str, Any]]:
    root = FolderNode(name="root", level=0)
    stack: list[FolderNode] = [root]
    for heading in headings:
        level = max(1, heading.level)
        node = FolderNode(name=sanitize_name(heading.title), level=level, note="\n".join(heading.note_lines))
        while stack and stack[-1].level >= level:
            stack.pop()
        if not stack:
            stack = [root]
        stack[-1].children.append(node)
        stack.append(node)
    return [node.to_dict() for node in root.children]
