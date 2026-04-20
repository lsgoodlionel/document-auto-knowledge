from __future__ import annotations

import zipfile
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape


def build_docx(project_name: str, tree: list[dict[str, Any]]) -> bytes:
    files = {
        "[Content_Types].xml": content_types_xml(),
        "_rels/.rels": root_rels_xml(),
        "word/document.xml": document_xml(tree),
        "word/styles.xml": styles_xml(),
        "docProps/app.xml": app_xml(),
        "docProps/core.xml": core_xml(project_name),
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        for path, content in files.items():
            docx.writestr(path, content)
    return buffer.getvalue()


def flatten_nodes(nodes: list[dict[str, Any]], level: int = 1) -> list[dict[str, Any]]:
    paragraphs: list[dict[str, Any]] = []
    for node in nodes:
        paragraphs.append({"type": "heading", "level": min(level, 9), "text": node["title"]})
        note = (node.get("note") or "").strip()
        if note:
            for line in note.splitlines():
                if line.strip():
                    paragraphs.append({"type": "text", "text": line.strip()})
        paragraphs.extend(flatten_nodes(node.get("children", []), level + 1))
    return paragraphs


def document_xml(tree: list[dict[str, Any]]) -> str:
    paragraphs = []
    for item in flatten_nodes(tree):
        text = escape(item["text"])
        if item["type"] == "heading":
            outline_level = item["level"] - 1
            paragraphs.append(
                f'<w:p><w:pPr><w:pStyle w:val="Heading{item["level"]}"/>'
                f'<w:outlineLvl w:val="{outline_level}"/>'
                f'<w:spacing w:before="240" w:after="120"/><w:keepNext/></w:pPr>'
                f'<w:r><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/>'
                f'</w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
            )
        else:
            paragraphs.append(
                '<w:p><w:pPr><w:spacing w:before="0" w:after="160" w:line="360" w:lineRule="auto"/></w:pPr>'
                '<w:r><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/>'
                f'<w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
            )

    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {''.join(paragraphs)}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>"""


def styles_xml() -> str:
    headings = []
    for level in range(1, 10):
        size = max(22, 36 - (level - 1) * 2)
        before = max(120, 360 - (level - 1) * 24)
        headings.append(
            f'<w:style w:type="paragraph" w:styleId="Heading{level}">'
            f'<w:name w:val="heading {level}"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/>'
            f'<w:pPr><w:keepNext/><w:keepLines/><w:spacing w:before="{before}" w:after="120"/>'
            f'<w:outlineLvl w:val="{level - 1}"/></w:pPr>'
            f'<w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/>'
            f'<w:b/><w:bCs/><w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr></w:style>'
        )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/><w:qFormat/>
    <w:pPr><w:spacing w:after="160" w:line="360" w:lineRule="auto"/></w:pPr>
    <w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:hAnsi="Microsoft YaHei"/><w:sz w:val="21"/><w:szCs w:val="21"/></w:rPr>
  </w:style>
  {''.join(headings)}
</w:styles>"""


def content_types_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
</Types>"""


def root_rels_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""


def app_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Codex</Application></Properties>"""


def core_xml(project_name: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/">
  <dc:title>{escape(project_name)}</dc:title>
  <dc:creator>Codex</dc:creator>
</cp:coreProperties>"""
