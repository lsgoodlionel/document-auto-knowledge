from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol

from .docx_parser import DocxFolderParser, sanitize_name


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
            "title": self.title,
            "name": self.title,
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
    metadata: dict[str, Any] = field(default_factory=dict)

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
            metadata={"filename": filename, "format": self.source_type},
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


def import_file(filename: str, content: bytes) -> ImportResult:
    return registry.importer_for_filename(filename).parse(filename, content)


def import_uploaded_file(filename: str, file_base64: str) -> ImportResult:
    return import_file(filename, decode_upload(file_base64))
