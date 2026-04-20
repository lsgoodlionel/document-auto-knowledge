from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any, Callable

from .docx_parser import DocxFolderParser, sanitize_name
from .ebook_parser import Azw3UnsupportedError, EpubParser, EpubParserError
from .excel_parser import CsvTableParser
from .image_parser import ImageParser, is_supported_image
from .mindmap_parser import FreeMindParser
from .pdf_parser import PdfParser, PdfParserError


@dataclass
class ImportNode:
    title: str
    level: int = 1
    note: str = ""
    children: list["ImportNode"] = field(default_factory=list)
    source_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": sanitize_name(self.title),
            "name": sanitize_name(self.title),
            "level": self.level,
            "note": self.note,
            "children": [child.as_dict() for child in self.children],
            "source_type": self.source_type,
            "metadata": self.metadata,
        }


@dataclass
class ImportResult:
    title: str
    tree: list[ImportNode]
    source_type: str
    headings: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def project_name(self) -> str:
        return self.title

    def tree_as_dicts(self) -> list[dict[str, Any]]:
        return [node.as_dict() for node in self.tree]


@dataclass(frozen=True)
class Importer:
    extension: str
    source_type: str
    parse: Callable[[str, bytes], ImportResult]


class ImporterError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class UnsupportedImportFormat(ImporterError):
    def __init__(self, message: str) -> None:
        super().__init__("unsupported_format", message)


class ImportRegistry:
    def __init__(self) -> None:
        self._by_extension: dict[str, Importer] = {}

    def register(self, importer: Importer) -> None:
        self._by_extension[importer.extension] = importer

    def import_file(self, filename: str, content: bytes) -> ImportResult:
        extension = file_extension(filename)
        importer = self._by_extension.get(extension)
        if importer is None:
            supported = "、".join(self.supported_extensions())
            raise UnsupportedImportFormat(f"暂不支持 {extension or '未知'} 格式导入。当前支持：{supported}。")
        return importer.parse(filename, content)

    def supported_extensions(self) -> list[str]:
        return sorted(self._by_extension)


def import_file(filename: str, content: bytes) -> ImportResult:
    return registry.import_file(filename, content)


def import_uploaded_file(filename: str, file_base64: str) -> ImportResult:
    return import_file(filename, decode_upload(file_base64))


def parse_docx(filename: str, content: bytes) -> ImportResult:
    parsed = DocxFolderParser().parse(content)
    return ImportResult(
        title=title_from_filename(filename, "untitled"),
        tree=nodes_from_dicts(parsed["tree"], "docx", {"source_parser": "DocxFolderParser"}),
        source_type="docx",
        headings=[
            {
                **heading,
                "source_type": "docx",
                "metadata": {
                    "folderName": heading.get("folderName"),
                    "source": heading.get("source"),
                },
            }
            for heading in parsed["headings"]
        ],
        metadata={"extension": ".docx", "filename": filename},
    )


def parse_csv(filename: str, content: bytes) -> ImportResult:
    parsed = CsvTableParser().parse(content, filename)
    return ImportResult(
        title=title_from_filename(filename, "untitled"),
        tree=nodes_from_dicts(parsed["tree"], "csv", parsed.get("summary", {})),
        source_type="csv",
        metadata=parsed.get("summary", {}),
    )


def parse_freemind(filename: str, content: bytes) -> ImportResult:
    parsed = FreeMindParser().parse(content)
    return ImportResult(
        title=title_from_filename(filename, "untitled"),
        tree=nodes_from_dicts(parsed["tree"], "freemind", parsed.get("summary", {})),
        source_type="freemind",
        metadata=parsed.get("summary", {}),
    )


def parse_pdf(filename: str, content: bytes) -> ImportResult:
    try:
        parsed = PdfParser().parse(content)
    except PdfParserError as exc:
        raise ImporterError(exc.code, exc.message) from exc
    metadata = {"extension": ".pdf", "filename": filename, "source_parser": "PdfParser", "pages": parsed.get("pages")}
    return ImportResult(
        title=title_from_filename(filename, "untitled"),
        tree=nodes_from_dicts(parsed["tree"], "pdf", metadata),
        source_type="pdf",
        headings=parsed["headings"],
        metadata=metadata,
        warnings=parsed.get("warnings", []),
    )


def parse_image(filename: str, content: bytes) -> ImportResult:
    parsed = ImageParser().parse(filename, content)
    metadata = {"extension": file_extension(filename), "filename": filename, "source_parser": "ImageParser", **parsed["metadata"]}
    return ImportResult(
        title=title_from_filename(filename, "untitled"),
        tree=nodes_from_dicts(parsed["tree"], "image", metadata),
        source_type="image",
        headings=parsed["headings"],
        metadata=metadata,
        warnings=parsed["warnings"],
    )


def parse_epub(filename: str, content: bytes) -> ImportResult:
    try:
        parsed = EpubParser().parse(content)
    except EpubParserError as exc:
        raise ImporterError(exc.code, exc.message) from exc
    metadata = dict(parsed.get("metadata", {}))
    metadata["source_parser"] = "EpubParser"
    return ImportResult(
        title=parsed.get("title") or title_from_filename(filename, "untitled"),
        tree=nodes_from_dicts(parsed["tree"], "epub", metadata),
        source_type="epub",
        headings=parsed.get("headings", []),
        metadata=parsed.get("metadata", {}),
        warnings=parsed.get("warnings", []),
    )


def parse_azw3(filename: str, content: bytes) -> ImportResult:
    raise ImporterError(Azw3UnsupportedError.code, Azw3UnsupportedError.message)


def parse_xmind(filename: str, content: bytes) -> ImportResult:
    raise UnsupportedImportFormat("已识别 XMind 导入入口，但当前版本尚未实现 .xmind 完整解析。请先导出为 FreeMind .mm 或 CSV 后导入。")


def parse_excel_placeholder(filename: str, content: bytes) -> ImportResult:
    extension = file_extension(filename)
    raise UnsupportedImportFormat(f"已识别 {extension} 导入入口，但当前版本先支持 .csv；请将 Excel 另存为 CSV 后导入。")


def nodes_from_dicts(
    nodes: list[dict[str, Any]],
    source_type: str,
    default_metadata: dict[str, Any],
) -> list[ImportNode]:
    result = []
    for index, node in enumerate(nodes, start=1):
        metadata = dict(default_metadata)
        metadata.update(node.get("metadata", {}))
        metadata.setdefault("position", index)
        result.append(
            ImportNode(
                title=node.get("title") or node.get("name") or "untitled",
                level=max(1, int(node.get("level") or 1)),
                note=node.get("note", ""),
                children=nodes_from_dicts(node.get("children", []), source_type, default_metadata),
                source_type=node.get("source_type", source_type),
                metadata=metadata,
            )
        )
    return result


def decode_upload(file_base64: str) -> bytes:
    if not file_base64:
        raise ImporterError("missing_file", "Missing uploaded file content.")
    try:
        return base64.b64decode(file_base64.encode("utf-8"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ImporterError("invalid_file_encoding", "Uploaded file is not valid base64.") from exc


def title_from_filename(filename: str, fallback: str) -> str:
    if not filename:
        return fallback
    return sanitize_name(filename.rsplit(".", 1)[0])


def file_extension(filename: str) -> str:
    if "." not in filename:
        return ""
    return "." + filename.rsplit(".", 1)[-1].lower()


registry = ImportRegistry()
registry.register(Importer(".docx", "docx", parse_docx))
registry.register(Importer(".pdf", "pdf", parse_pdf))
for image_extension in (".png", ".jpg", ".jpeg"):
    if is_supported_image(image_extension):
        registry.register(Importer(image_extension, "image", parse_image))
registry.register(Importer(".epub", "epub", parse_epub))
registry.register(Importer(".azw3", "azw3", parse_azw3))
registry.register(Importer(".csv", "csv", parse_csv))
registry.register(Importer(".mm", "freemind", parse_freemind))
registry.register(Importer(".xmind", "xmind", parse_xmind))
registry.register(Importer(".xlsx", "excel", parse_excel_placeholder))
registry.register(Importer(".xls", "excel", parse_excel_placeholder))
