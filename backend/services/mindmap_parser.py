from __future__ import annotations

from typing import Any
import xml.etree.ElementTree as ET

from .docx_parser import sanitize_name


class FreeMindParser:
    def parse(self, content: bytes) -> dict[str, Any]:
        try:
            root = ET.fromstring(content)
        except ET.ParseError as exc:
            raise ValueError("FreeMind .mm 文件不是有效 XML。") from exc

        if strip_namespace(root.tag) != "map":
            raise ValueError("FreeMind .mm 文件缺少 map 根节点。")

        root_nodes = [child for child in list(root) if strip_namespace(child.tag) == "node"]
        if not root_nodes:
            raise ValueError("FreeMind .mm 文件没有可导入的 node 节点。")

        return {
            "tree": [parse_freemind_node(node) for node in root_nodes],
            "summary": {
                "format": "freemind",
                "nodes": sum(count_freemind_nodes(node) for node in root_nodes),
            },
        }


def parse_freemind_node(element: ET.Element) -> dict[str, Any]:
    title = element.attrib.get("TEXT") or element.attrib.get("text") or element.text or "未命名节点"
    note = collect_notes(element)
    children = [
        parse_freemind_node(child)
        for child in list(element)
        if strip_namespace(child.tag) == "node"
    ]
    return {
        "name": sanitize_name(title),
        "note": note,
        "children": children,
    }


def collect_notes(element: ET.Element) -> str:
    notes: list[str] = []
    for child in list(element):
        tag = strip_namespace(child.tag)
        if tag == "richcontent" and child.attrib.get("TYPE", "").upper() == "NOTE":
            text = " ".join(part.strip() for part in child.itertext() if part.strip())
            if text:
                notes.append(text)
        elif tag == "hook" and child.attrib.get("NAME") == "accessories/plugins/NodeNote.properties":
            text = " ".join(part.strip() for part in child.itertext() if part.strip())
            if text:
                notes.append(text)
    return "\n".join(notes)


def count_freemind_nodes(element: ET.Element) -> int:
    return 1 + sum(
        count_freemind_nodes(child)
        for child in list(element)
        if strip_namespace(child.tag) == "node"
    )


def strip_namespace(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
