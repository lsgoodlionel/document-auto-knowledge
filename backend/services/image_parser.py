from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from .docx_parser import sanitize_name


SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg"}
OCR_UNAVAILABLE_MESSAGE = "OCR is not configured. The image was imported as a source node; install an OCR provider to extract text."


class OcrProvider(Protocol):
    name: str

    def extract_text(self, content: bytes, filename: str) -> str:
        ...


class ImageParser:
    def __init__(self, ocr_provider: OcrProvider | None = None) -> None:
        self.ocr_provider = ocr_provider

    def parse(self, filename: str, content: bytes) -> dict[str, Any]:
        image_name = sanitize_name(Path(filename or "image").stem or "image")
        note_lines = [
            f"Source image: {filename or 'unnamed image'}",
            f"Size: {len(content)} bytes",
        ]
        warnings: list[dict[str, str]] = []

        if self.ocr_provider is None:
            note_lines.append(OCR_UNAVAILABLE_MESSAGE)
            warnings.append({"code": "ocr_unavailable", "message": OCR_UNAVAILABLE_MESSAGE})
        else:
            extracted = self.ocr_provider.extract_text(content, filename)
            if extracted.strip():
                note_lines.append("OCR text:")
                note_lines.append(extracted.strip())

        return {
            "headings": [
                {
                    "title": image_name,
                    "folderName": image_name,
                    "level": 1,
                    "source": "image",
                    "note": "\n".join(note_lines),
                }
            ],
            "tree": [
                {
                    "name": image_name,
                    "level": 1,
                    "note": "\n".join(note_lines),
                    "children": [],
                }
            ],
            "warnings": warnings,
            "metadata": {"ocr": self.ocr_provider.name if self.ocr_provider else None},
        }


def is_supported_image(suffix: str) -> bool:
    return suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
