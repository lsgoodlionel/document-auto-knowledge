from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol

from .docx_parser import DocxFolderParser, sanitize_name
from .ebook_parser import Azw3UnsupportedError, EpubParser, EpubParserError
from .excel_parser import CsvTableParser
from .image_parser import ImageParser, is_supported_image
from .mindmap_parser import FreeMindParser
from .pdf_parser import PdfParser, PdfParserError


class ImporterError(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass
class ImportNode:
    title: str
    level: int
    note: str = ""
    children: list["ImportNode"] = field(default_factory=list)
    source_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": sanitize_name(self.title),
            "name": sanitize_name(self.title),
            "level": self.level,
            "note": self.note,
            "children": [child.to_dict() for child in self.children],
            "source_type": self.source_type,
            "metadata": self.metadata,
        }


@dataclass
class ImportResult:
    title: str
    source_type: str
    tree: list[ImportNode]
    headings: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def project_name(self) -> str:
        return self.title

    def tree_as_dicts(self) -> list[dict[str, Any]]:
        return [node.to_dict() for node in self.tree]


class FileImporter(Protocol):
    source_type: str
    extensions: tuple[str, ...]

    def parse(self, filename: str, content: bytes) -> ImportResult:
        ...


class ImporterRegistry:
    def __init__(self) -> None:
        self._importers: dict[str, FileImporter] = {}

    def register(self, importer: FileImporter) -> None:
        for extension in importer.extensions:
            self._importers[normalize_extension(extension)] = importer

    def importer_for_filename(self, filename: str) -> FileImporter:
        extension = normalize_extension(Path(filename or "").suffix)
        if not extension:
            raise ImporterError(HTTPStatus.BAD_REQUEST, "missing_extension", "Uploaded filename must include an extension.")
        try:
            return self._importers[extension]
        except KeyError as exc:
            supported = ", ".join(self.supported_extensions())
            raise ImporterError(
                HTTPStatus.BAD_REQUEST,
                "unsupported_import_type",
                f"Unsupported import format. Please upload one of: {supported}.",
            ) from exc

    def supported_extensions(self) -> tuple[str, ...]:
        return tuple(sorted(self._importers))


class DocxImporter:
    source_type = "docx"
    extensions = (".docx",)

    def parse(self, filename: str, content: bytes) -> ImportResult:
        parsed = DocxFolderParser().parse(content)
        return ImportResult(
            title=project_title_from_filename(filename),
            source_type=self.source_type,
            tree=[self._from_docx_node(node) for node in parsed["tree"]],
            headings=[
                {
                    **heading,
                    "source_type": self.source_type,
                    "metadata": {
                        "folderName": heading.get("folderName"),
                        "source": heading.get("source"),
                    },
                }
                for heading in parsed["headings"]
            ],
            metadata={"filename": filename, "format": self.source_type, "source_parser": "DocxFolderParser"},
        )

    def _from_docx_node(self, node: dict[str, Any]) -> ImportNode:
        title = sanitize_name(node.get("title") or node.get("name") or "untitled")
        return ImportNode(
            title=title,
            level=max(1, int(node.get("level") or 1)),
            note=node.get("note", ""),
            children=[self._from_docx_node(child) for child in node.get("children", [])],
            source_type=self.source_type,
            metadata={
                "original_name": node.get("name") or node.get("title") or "",
                "source_parser": "DocxFolderParser",
            },
        )


class PdfImporter:
    source_type = "pdf"
    extensions = (".pdf",)

    def parse(self, filename: str, content: bytes) -> ImportResult:
        try:
            parsed = PdfParser().parse(content)
        except PdfParserError as exc:
            raise ImporterError(HTTPStatus.BAD_REQUEST, exc.code, exc.message) from exc
        metadata = {"filename": filename, "format": self.source_type, "pages": parsed.get("pages"), "source_parser": "PdfParser"}
        return ImportResult(
            title=project_title_from_filename(filename),
            source_type=self.source_type,
            tree=[node_from_dict(node, self.source_type, metadata) for node in parsed["tree"]],
            headings=[
                {
                    **heading,
                    "source_type": self.source_type,
                    "metadata": {"source": heading.get("source")},
                }
                for heading in parsed["headings"]
            ],
            warnings=parsed.get("warnings", []),
            metadata=metadata,
        )


class ImageImporter:
    source_type = "image"
    extensions = (".jpeg", ".jpg", ".png")

    def __init__(self, parser: ImageParser | None = None) -> None:
        self.parser = parser or ImageParser()

    def parse(self, filename: str, content: bytes) -> ImportResult:
        parsed = self.parser.parse(filename, content)
        metadata = {"filename": filename, "format": self.source_type, "source_parser": "ImageParser", **parsed.get("metadata", {})}
        return ImportResult(
            title=project_title_from_filename(filename),
            source_type=self.source_type,
            tree=[node_from_dict(node, self.source_type, metadata) for node in parsed["tree"]],
            headings=[
                {
                    **heading,
                    "source_type": self.source_type,
                    "metadata": {"source": heading.get("source")},
                }
                for heading in parsed["headings"]
            ],
            warnings=parsed.get("warnings", []),
            metadata=metadata,
        )


class EpubImporter:
    source_type = "epub"
    extensions = (".epub",)

    def parse(self, filename: str, content: bytes) -> ImportResult:
        try:
            parsed = EpubParser().parse(content)
        except EpubParserError as exc:
            raise ImporterError(HTTPStatus.BAD_REQUEST, exc.code, exc.message) from exc
        metadata = dict(parsed.get("metadata", {}))
        metadata.update({"filename": filename, "format": self.source_type, "source_parser": "EpubParser"})
        return ImportResult(
            title=parsed.get("title") or project_title_from_filename(filename),
            source_type=self.source_type,
            tree=[node_from_dict(node, self.source_type, metadata) for node in parsed["tree"]],
            headings=parsed.get("headings", []),
            warnings=parsed.get("warnings", []),
            metadata=metadata,
        )


class Azw3Importer:
    source_type = "azw3"
    extensions = (".azw3",)

    def parse(self, filename: str, content: bytes) -> ImportResult:
        raise ImporterError(HTTPStatus.BAD_REQUEST, Azw3UnsupportedError.code, Azw3UnsupportedError.message)


class CsvImporter:
    source_type = "csv"
    extensions = (".csv",)

    def __init__(self, parser: CsvTableParser | None = None) -> None:
        self.parser = parser or CsvTableParser()

    def parse(self, filename: str, content: bytes) -> ImportResult:
        try:
            parsed = self.parser.parse(content, filename)
        except ValueError as exc:
            raise ImporterError(HTTPStatus.BAD_REQUEST, "invalid_csv", str(exc)) from exc
        metadata = {"filename": filename, **parsed.get("summary", {}), "source_parser": "CsvTableParser"}
        return ImportResult(
            title=project_title_from_filename(filename),
            source_type=self.source_type,
            tree=[node_from_dict(node, self.source_type, metadata) for node in parsed["tree"]],
            headings=build_headings_from_tree(parsed["tree"], "csv"),
            metadata=metadata,
        )


class FreeMindImporter:
    source_type = "freemind"
    extensions = (".mm",)

    def __init__(self, parser: FreeMindParser | None = None) -> None:
        self.parser = parser or FreeMindParser()

    def parse(self, filename: str, content: bytes) -> ImportResult:
        try:
            parsed = self.parser.parse(content)
        except ValueError as exc:
            raise ImporterError(HTTPStatus.BAD_REQUEST, "invalid_freemind", str(exc)) from exc
        metadata = {"filename": filename, **parsed.get("summary", {}), "source_parser": "FreeMindParser"}
        return ImportResult(
            title=project_title_from_filename(filename),
            source_type=self.source_type,
            tree=[node_from_dict(node, self.source_type, metadata) for node in parsed["tree"]],
            headings=build_headings_from_tree(parsed["tree"], "freemind"),
            metadata=metadata,
        )


class XmindImporter:
    source_type = "xmind"
    extensions = (".xmind",)

    def parse(self, filename: str, content: bytes) -> ImportResult:
        raise ImporterError(
            HTTPStatus.BAD_REQUEST,
            "unsupported_format",
            "已识别 XMind 导入入口，但当前版本尚未实现 .xmind 完整解析。请先导出为 FreeMind .mm 或 CSV 后导入。",
        )


class ExcelPlaceholderImporter:
    source_type = "excel"
    extensions = (".xls", ".xlsx")

    def parse(self, filename: str, content: bytes) -> ImportResult:
        extension = normalize_extension(Path(filename or "").suffix) or "excel"
        raise ImporterError(
            HTTPStatus.BAD_REQUEST,
            "unsupported_format",
            f"已识别 {extension} 导入入口，但当前版本先支持 .csv；请将 Excel 另存为 CSV 后导入。",
        )


def node_from_dict(node: dict[str, Any], source_type: str, default_metadata: dict[str, Any]) -> ImportNode:
    metadata = dict(default_metadata)
    metadata.update(node.get("metadata", {}))
    return ImportNode(
        title=node.get("title") or node.get("name") or "untitled",
        level=max(1, int(node.get("level") or 1)),
        note=node.get("note", ""),
        children=[node_from_dict(child, source_type, default_metadata) for child in node.get("children", [])],
        source_type=node.get("source_type", source_type),
        metadata=metadata,
    )


def build_headings_from_tree(nodes: list[dict[str, Any]], source: str, level: int = 1) -> list[dict[str, Any]]:
    headings: list[dict[str, Any]] = []
    for node in nodes:
        title = sanitize_name(node.get("title") or node.get("name") or "untitled")
        headings.append(
            {
                "title": title,
                "folderName": title,
                "level": level,
                "source": source,
                "note": node.get("note", ""),
            }
        )
        headings.extend(build_headings_from_tree(node.get("children", []), source, level + 1))
    return headings


def normalize_extension(extension: str) -> str:
    if not extension:
        return ""
    normalized = extension.lower()
    return normalized if normalized.startswith(".") else f".{normalized}"


def decode_upload(file_base64: str) -> bytes:
    if not file_base64:
        raise ImporterError(HTTPStatus.BAD_REQUEST, "missing_file", "Missing uploaded file content.")
    try:
        return base64.b64decode(file_base64.encode("utf-8"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ImporterError(HTTPStatus.BAD_REQUEST, "invalid_file_encoding", "Uploaded file is not valid base64.") from exc


def project_title_from_filename(filename: str) -> str:
    stem = Path(filename or "untitled").stem or "untitled"
    return sanitize_name(stem)


registry = ImporterRegistry()
registry.register(DocxImporter())
registry.register(PdfImporter())
registry.register(EpubImporter())
registry.register(Azw3Importer())
registry.register(CsvImporter())
registry.register(FreeMindImporter())
registry.register(XmindImporter())
registry.register(ExcelPlaceholderImporter())
for image_extension in ImageImporter.extensions:
    if is_supported_image(image_extension):
        registry.register(ImageImporter())


def import_file(filename: str, content: bytes) -> ImportResult:
    return registry.importer_for_filename(filename).parse(filename, content)


def import_uploaded_file(filename: str, file_base64: str) -> ImportResult:
    return import_file(filename, decode_upload(file_base64))
