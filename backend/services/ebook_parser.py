from __future__ import annotations

import html
import posixpath
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET

from .docx_parser import sanitize_name


CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
OPF_NS = {"opf": "http://www.idpf.org/2007/opf", "dc": "http://purl.org/dc/elements/1.1/"}
NCX_NS = {"ncx": "http://www.daisy.org/z3986/2005/ncx/"}
XHTML_NS = {"xhtml": "http://www.w3.org/1999/xhtml"}


class EpubParserError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class Azw3UnsupportedError:
    code = "azw3_conversion_required"
    message = (
        "AZW3 import needs an external conversion tool. Convert the book to EPUB first, "
        "or install Calibre and expose ebook-convert for a future converter-backed importer."
    )


@dataclass
class ManifestItem:
    id: str
    href: str
    media_type: str
    properties: str = ""


@dataclass
class TocEntry:
    title: str
    href: str
    children: list["TocEntry"] = field(default_factory=list)


class EpubParser:
    def parse(self, content: bytes) -> dict[str, Any]:
        try:
            with zipfile.ZipFile(BytesIO(content)) as epub:
                opf_path = find_opf_path(epub)
                opf_root = ET.fromstring(epub.read(opf_path))
                opf_dir = PurePosixPath(opf_path).parent.as_posix()
                if opf_dir == ".":
                    opf_dir = ""

                title = extract_book_title(opf_root)
                manifest = parse_manifest(opf_root)
                spine_ids = parse_spine_ids(opf_root)
                toc_entries = parse_toc(epub, opf_root, opf_dir, manifest)
                if not toc_entries:
                    toc_entries = toc_from_spine(epub, opf_dir, manifest, spine_ids)

                tree = [
                    entry_to_node(epub, opf_dir, entry, level=1)
                    for entry in toc_entries
                ]
                headings: list[dict[str, Any]] = []
                collect_headings(tree, headings)
        except EpubParserError:
            raise
        except (KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
            raise EpubParserError("invalid_epub", "EPUB import failed: the file is not a readable EPUB package.") from exc

        if not tree:
            raise EpubParserError("epub_chapters_not_found", "EPUB import failed: no chapters were found.")

        return {
            "title": title,
            "tree": tree,
            "headings": headings,
            "warnings": [],
            "metadata": {"chapter_count": len(headings)},
        }


def find_opf_path(epub: zipfile.ZipFile) -> str:
    try:
        container_root = ET.fromstring(epub.read("META-INF/container.xml"))
    except KeyError as exc:
        raise EpubParserError("epub_container_not_found", "EPUB import failed: META-INF/container.xml was not found.") from exc

    rootfile = container_root.find(".//c:rootfile", CONTAINER_NS)
    opf_path = rootfile.attrib.get("full-path", "") if rootfile is not None else ""
    if not opf_path:
        raise EpubParserError("epub_opf_not_found", "EPUB import failed: the package document was not found.")
    return opf_path


def extract_book_title(opf_root: ET.Element) -> str:
    title_node = opf_root.find(".//dc:title", OPF_NS)
    if title_node is not None and title_node.text:
        return sanitize_name(title_node.text)
    return "untitled"


def parse_manifest(opf_root: ET.Element) -> dict[str, ManifestItem]:
    manifest: dict[str, ManifestItem] = {}
    for item in opf_root.findall(".//opf:manifest/opf:item", OPF_NS):
        item_id = item.attrib.get("id", "")
        href = item.attrib.get("href", "")
        if not item_id or not href:
            continue
        manifest[item_id] = ManifestItem(
            id=item_id,
            href=href,
            media_type=item.attrib.get("media-type", ""),
            properties=item.attrib.get("properties", ""),
        )
    return manifest


def parse_spine_ids(opf_root: ET.Element) -> list[str]:
    return [
        itemref.attrib["idref"]
        for itemref in opf_root.findall(".//opf:spine/opf:itemref", OPF_NS)
        if itemref.attrib.get("idref")
    ]


def parse_toc(
    epub: zipfile.ZipFile,
    opf_root: ET.Element,
    opf_dir: str,
    manifest: dict[str, ManifestItem],
) -> list[TocEntry]:
    toc_entries = parse_ncx_toc(epub, opf_root, opf_dir, manifest)
    if toc_entries:
        return toc_entries
    return parse_nav_toc(epub, opf_dir, manifest)


def parse_ncx_toc(
    epub: zipfile.ZipFile,
    opf_root: ET.Element,
    opf_dir: str,
    manifest: dict[str, ManifestItem],
) -> list[TocEntry]:
    spine = opf_root.find(".//opf:spine", OPF_NS)
    toc_id = spine.attrib.get("toc", "") if spine is not None else ""
    toc_item = manifest.get(toc_id) if toc_id else None
    if toc_item is None:
        toc_item = next((item for item in manifest.values() if item.media_type == "application/x-dtbncx+xml"), None)
    if toc_item is None:
        return []

    toc_path = resolve_package_path(opf_dir, toc_item.href)
    root = ET.fromstring(epub.read(toc_path))
    return [parse_nav_point(nav_point) for nav_point in root.findall(".//ncx:navMap/ncx:navPoint", NCX_NS)]


def parse_nav_point(nav_point: ET.Element) -> TocEntry:
    label = nav_point.find("ncx:navLabel/ncx:text", NCX_NS)
    content = nav_point.find("ncx:content", NCX_NS)
    title = sanitize_name((label.text or "").strip() if label is not None else "untitled")
    href = content.attrib.get("src", "") if content is not None else ""
    children = [parse_nav_point(child) for child in nav_point.findall("ncx:navPoint", NCX_NS)]
    return TocEntry(title=title, href=href, children=children)


def parse_nav_toc(epub: zipfile.ZipFile, opf_dir: str, manifest: dict[str, ManifestItem]) -> list[TocEntry]:
    nav_item = next(
        (
            item
            for item in manifest.values()
            if item.media_type in {"application/xhtml+xml", "text/html"} and "nav" in item.properties.split()
        ),
        None,
    )
    if nav_item is None:
        return []

    nav_path = resolve_package_path(opf_dir, nav_item.href)
    root = ET.fromstring(epub.read(nav_path))
    nav = find_toc_nav(root)
    if nav is None:
        return []
    first_ol = nav.find("xhtml:ol", XHTML_NS)
    return parse_nav_ol(first_ol) if first_ol is not None else []


def find_toc_nav(root: ET.Element) -> ET.Element | None:
    for nav in root.findall(".//xhtml:nav", XHTML_NS):
        nav_type = nav.attrib.get("{http://www.idpf.org/2007/ops}type", nav.attrib.get("type", ""))
        if "toc" in nav_type.split():
            return nav
    return None


def parse_nav_ol(ol: ET.Element) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for li in ol.findall("xhtml:li", XHTML_NS):
        anchor = li.find("xhtml:a", XHTML_NS)
        if anchor is None:
            continue
        title = sanitize_name(text_content(anchor))
        child_ol = li.find("xhtml:ol", XHTML_NS)
        children = parse_nav_ol(child_ol) if child_ol is not None else []
        entries.append(TocEntry(title=title, href=anchor.attrib.get("href", ""), children=children))
    return entries


def toc_from_spine(
    epub: zipfile.ZipFile,
    opf_dir: str,
    manifest: dict[str, ManifestItem],
    spine_ids: list[str],
) -> list[TocEntry]:
    entries: list[TocEntry] = []
    for item_id in spine_ids:
        item = manifest.get(item_id)
        if item is None:
            continue
        path = resolve_package_path(opf_dir, item.href)
        title = chapter_title(epub.read(path), PurePosixPath(item.href).stem)
        entries.append(TocEntry(title=title, href=item.href))
    return entries


def entry_to_node(epub: zipfile.ZipFile, opf_dir: str, entry: TocEntry, level: int) -> dict[str, Any]:
    note = ""
    source_path = strip_fragment(entry.href)
    if source_path:
        package_path = resolve_package_path(opf_dir, source_path)
        try:
            note = extract_html_text(epub.read(package_path))
        except KeyError:
            note = ""

    return {
        "title": sanitize_name(entry.title),
        "name": sanitize_name(entry.title),
        "level": level,
        "note": note,
        "metadata": {"href": entry.href},
        "children": [entry_to_node(epub, opf_dir, child, level + 1) for child in entry.children],
    }


def collect_headings(nodes: list[dict[str, Any]], headings: list[dict[str, Any]]) -> None:
    for node in nodes:
        headings.append(
            {
                "title": node["title"],
                "folderName": node["title"],
                "level": node["level"],
                "source": "epub-toc",
                "note": node["note"],
            }
        )
        collect_headings(node["children"], headings)


def resolve_package_path(opf_dir: str, href: str) -> str:
    base = f"{opf_dir}/" if opf_dir else ""
    return posixpath.normpath(base + strip_fragment(href))


def strip_fragment(href: str) -> str:
    return href.split("#", 1)[0]


def chapter_title(content: bytes, fallback: str) -> str:
    text = content.decode("utf-8", errors="ignore")
    for pattern in (r"<h1\b[^>]*>(.*?)</h1>", r"<title\b[^>]*>(.*?)</title>"):
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if match:
            return sanitize_name(clean_html_text(match.group(1)))
    return sanitize_name(fallback)


def extract_html_text(content: bytes) -> str:
    raw = content.decode("utf-8", errors="ignore")
    raw = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)</(p|div|section|article|h[1-6]|li|br)>", "\n", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    lines = []
    for line in html.unescape(raw).splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def text_content(element: ET.Element) -> str:
    return sanitize_name("".join(element.itertext()))


def clean_html_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"(?is)<[^>]+>", " ", value))).strip()
