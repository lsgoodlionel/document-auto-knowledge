from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any
import xml.etree.ElementTree as ET


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def sanitize_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]', " ", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(".")
    return cleaned or "untitled"


@dataclass
class FolderNode:
    name: str
    level: int
    note: str = ""
    children: list["FolderNode"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "level": self.level,
            "note": self.note,
            "children": [child.to_dict() for child in self.children],
        }


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

            name = style.find("w:name", NS)
            style_name = name.attrib.get(f"{{{NS['w']}}}val", "") if name is not None else ""
            fallback_level = self._fallback_heading_level(style_id) or self._fallback_heading_level(style_name)
            if fallback_level is not None:
                mapping[style_id] = fallback_level
        return mapping

    def _extract_headings(self, document_root: ET.Element, style_map: dict[str, int]) -> list[dict[str, Any]]:
        headings: list[dict[str, Any]] = []
        current_heading: dict[str, Any] | None = None
        pending_body: list[str] = []
        for para in document_root.findall(".//w:body/w:p", NS):
            text = self._paragraph_text(para)
            if not text:
                continue

            style_id = self._paragraph_style_id(para)
            level, source = self._resolve_level(para, style_id, style_map)
            if level is None:
                if current_heading is not None:
                    pending_body.append(text)
                    current_heading["note"] = "\n".join(pending_body)
                continue

            pending_body = []
            current_heading = {
                "title": text,
                "folderName": sanitize_name(text),
                "level": level,
                "source": source,
                "note": "",
            }
            headings.append(current_heading)
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
        return node.attrib.get(f"{{{NS['w']}}}val") if node is not None else None

    @staticmethod
    def _paragraph_outline_level(para: ET.Element) -> int | None:
        node = para.find("w:pPr/w:outlineLvl", NS)
        if node is None:
            return None
        try:
            return int(node.attrib.get(f"{{{NS['w']}}}val", "")) + 1
        except ValueError:
            return None

    @staticmethod
    def _fallback_heading_level(style_id: str | None) -> int | None:
        if not style_id:
            return None
        match = re.search(r"(?:heading|标题)\s*(\d+)", style_id, re.IGNORECASE)
        return int(match.group(1)) if match else None

    @staticmethod
    def _paragraph_text(para: ET.Element) -> str:
        parts: list[str] = []
        for node in para.iter():
            if node.tag == f"{{{NS['w']}}}t":
                parts.append(node.text or "")
            elif node.tag == f"{{{NS['w']}}}tab":
                parts.append("\t")
            elif node.tag == f"{{{NS['w']}}}br":
                parts.append("\n")
        return "".join(parts).strip()

    def _build_tree(self, headings: list[dict[str, Any]]) -> list[FolderNode]:
        root = FolderNode(name="root", level=0)
        stack: list[FolderNode] = [root]
        for heading in headings:
            level = max(1, int(heading["level"]))
            node = FolderNode(name=heading["folderName"], level=level, note=heading.get("note", ""))

            while stack and stack[-1].level >= level:
                stack.pop()
            if not stack:
                stack = [root]

            stack[-1].children.append(node)
            stack.append(node)
        return root.children
