from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any, Protocol

from .docx_parser import DocxFolderParser, sanitize_name
from .image_parser import ImageParser, is_supported_image
from .pdf_parser import PdfParser, PdfParserError


class ImporterError(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


@dataclass
class ImportResult:
    project_name: str
    tree: list[dict[str, Any]]
    headings: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class FileImporter(Protocol):
    def parse(self, filename: str, content: bytes) -> ImportResult:
        ...


class DocxImporter:
    def parse(self, filename: str, content: bytes) -> ImportResult:
        parsed = DocxFolderParser().parse(content)
        return ImportResult(
            project_name=project_name_from_filename(filename),
            tree=parsed["tree"],
            headings=parsed["headings"],
            metadata={"format": "docx"},
        )


class PdfImporter:
    def parse(self, filename: str, content: bytes) -> ImportResult:
        try:
            parsed = PdfParser().parse(content)
        except PdfParserError as exc:
            raise ImporterError(HTTPStatus.BAD_REQUEST, exc.code, exc.message) from exc
        return ImportResult(
            project_name=project_name_from_filename(filename),
            tree=parsed["tree"],
            headings=parsed["headings"],
            warnings=parsed.get("warnings", []),
            metadata={"format": "pdf", "pages": parsed.get("pages")},
        )


class ImageImporter:
    def parse(self, filename: str, content: bytes) -> ImportResult:
        parsed = ImageParser().parse(filename, content)
        return ImportResult(
            project_name=project_name_from_filename(filename),
            tree=parsed["tree"],
            headings=parsed["headings"],
            warnings=parsed["warnings"],
            metadata={"format": "image", **parsed["metadata"]},
        )


def import_uploaded_file(filename: str, file_base64: str) -> ImportResult:
    importer = importer_for_filename(filename)
    return importer.parse(filename, decode_upload(file_base64))


def importer_for_filename(filename: str) -> FileImporter:
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".docx":
        return DocxImporter()
    if suffix == ".pdf":
        return PdfImporter()
    if is_supported_image(suffix):
        return ImageImporter()
    raise ImporterError(
        HTTPStatus.BAD_REQUEST,
        "unsupported_import_type",
        "Unsupported import format. Please upload .docx, .pdf, .png, .jpg, or .jpeg.",
    )


def decode_upload(file_base64: str) -> bytes:
    if not file_base64:
        raise ImporterError(HTTPStatus.BAD_REQUEST, "missing_file", "Missing uploaded file content.")
    try:
        return base64.b64decode(file_base64.encode("utf-8"), validate=True)
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise ImporterError(HTTPStatus.BAD_REQUEST, "invalid_file_encoding", "Uploaded file is not valid base64.") from exc


def project_name_from_filename(filename: str) -> str:
    stem = Path(filename or "untitled").stem or "untitled"
    return sanitize_name(stem)
