from __future__ import annotations

import csv
from io import StringIO
from typing import Any

from .docx_parser import sanitize_name


class CsvTableParser:
    def parse(self, content: bytes, filename: str = "") -> dict[str, Any]:
        text = decode_csv(content)
        rows = list(csv.reader(StringIO(text)))
        rows = [row for row in rows if any(cell.strip() for cell in row)]
        if not rows:
            raise ValueError("CSV 文件为空，无法生成目录。")

        headers = [sanitize_name(cell) for cell in rows[0]]
        data_rows = rows[1:]
        if not data_rows:
            raise ValueError("CSV 至少需要一行标题和一行内容。")

        sheet_name = sanitize_name(filename.rsplit(".", 1)[0] if filename else "CSV")
        sheet_node = {"name": sheet_name, "note": "", "children": []}
        for index, row in enumerate(data_rows, start=1):
            padded = row + [""] * max(0, len(headers) - len(row))
            values = dict(zip(headers, [cell.strip() for cell in padded]))
            title = first_non_empty(values) or f"第 {index} 行"
            sheet_node["children"].append(
                {
                    "name": title,
                    "note": build_row_note(values),
                    "children": [],
                }
            )

        return {
            "tree": [sheet_node],
            "summary": {
                "format": "csv",
                "sheets": 1,
                "rows": len(data_rows),
                "columns": len(headers),
            },
        }


def decode_csv(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV 编码无法识别，请使用 UTF-8 或 GB18030。")


def first_non_empty(values: dict[str, str]) -> str:
    for value in values.values():
        if value:
            return sanitize_name(value)
    return ""


def build_row_note(values: dict[str, str]) -> str:
    lines = []
    for key, value in values.items():
        if key or value:
            label = key or "未命名列"
            lines.append(f"{label}: {value}")
    return "\n".join(lines)
