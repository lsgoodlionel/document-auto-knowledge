from __future__ import annotations

import json
import tempfile
import threading
import unittest
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from io import BytesIO
from pathlib import Path

from backend import db
from backend.server import ApiServer, content_disposition
from backend.services.docx_exporter import build_docx
from backend.services.docx_parser import DocxFolderParser
from backend.services import projects


class BackendApiSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "smoke.sqlite3"
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()

    def tearDown(self) -> None:
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def test_project_node_crud_move_and_delete(self) -> None:
        with db.connect() as conn:
            project_id = projects.create_project(conn, "Smoke")
            conn.commit()

        renamed = projects.rename_project(project_id, "Renamed Smoke")
        self.assertEqual(renamed["name"], "Renamed Smoke")

        first = projects.create_node(project_id, None, "First")
        second = projects.create_node(project_id, None, "Second")
        child = projects.create_node(project_id, first["id"], "Child")

        moved = projects.move_node(child["id"], None, 0)
        self.assertIsNone(moved["parentId"])
        self.assertEqual(moved["position"], 0)

        reordered = projects.move_node(second["id"], None, 0)
        self.assertEqual(reordered["position"], 0)

        tree = projects.get_project(project_id)["tree"]
        self.assertEqual([node["title"] for node in tree], ["Second", "Child", "First"])

        updated = projects.update_node(first["id"], "First Updated", "note")
        self.assertEqual(updated["note"], "note")

        projects.delete_node(child["id"])
        tree = projects.get_project(project_id)["tree"]
        self.assertEqual([node["title"] for node in tree], ["Second", "First Updated"])

        projects.delete_project(project_id)
        with self.assertRaises(KeyError):
            projects.get_project(project_id)

    def test_error_payload_shape(self) -> None:
        from backend.server import error_response

        class Handler:
            def __init__(self) -> None:
                self.status = None
                self.headers: dict[str, str] = {}
                self.body = b""
                self.wfile = self

            def send_response(self, status: int) -> None:
                self.status = status

            def send_header(self, key: str, value: str) -> None:
                self.headers[key] = value

            def end_headers(self) -> None:
                pass

            def write(self, data: bytes) -> None:
                self.body += data

        handler = Handler()
        error_response(handler, 400, "bad_request", "Bad request")

        self.assertEqual(handler.status, 400)
        self.assertEqual(
            json.loads(handler.body.decode("utf-8")),
            {"error": {"code": "bad_request", "message": "Bad request"}},
        )

    def test_content_disposition_supports_chinese_filename(self) -> None:
        header = content_disposition("导出测试.docx")

        header.encode("latin-1")
        self.assertIn('filename="download.docx"', header)
        self.assertIn("filename*=UTF-8''", header)
        self.assertIn("%E5%AF%BC%E5%87%BA%E6%B5%8B%E8%AF%95.docx", header)


class HttpApiSmokeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "http-smoke.sqlite3"
        self.original_db_path = db.DB_PATH
        db.DB_PATH = self.db_path
        db.init_db()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ApiServer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        db.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def request(self, method: str, path: str, payload: dict[str, object] | None = None) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        connection.close()
        return response.status, json.loads(data.decode("utf-8"))

    def test_project_and_node_api_smoke(self) -> None:
        with db.connect() as conn:
            project_id = projects.create_project(conn, "HTTP Smoke")
            conn.commit()

        status, payload = self.request("PUT", f"/api/projects/{project_id}", {"name": "HTTP Renamed"})
        self.assertEqual(status, 200)
        self.assertEqual(payload["project"]["name"], "HTTP Renamed")

        status, payload = self.request("POST", f"/api/projects/{project_id}/nodes", {"title": "First"})
        self.assertEqual(status, 201)
        first_id = payload["node"]["id"]

        status, payload = self.request("POST", f"/api/projects/{project_id}/nodes", {"title": "Second"})
        self.assertEqual(status, 201)
        second_id = payload["node"]["id"]

        status, payload = self.request("PUT", f"/api/nodes/{second_id}/move", {"parentId": None, "position": 0})
        self.assertEqual(status, 200)
        self.assertEqual(payload["node"]["position"], 0)

        status, payload = self.request("GET", f"/api/projects/{project_id}")
        self.assertEqual(status, 200)
        self.assertEqual([node["title"] for node in payload["project"]["tree"]], ["Second", "First"])

        status, payload = self.request("DELETE", f"/api/nodes/{first_id}")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})

        status, payload = self.request("DELETE", f"/api/projects/{project_id}")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True})

        status, payload = self.request("GET", f"/api/projects/{project_id}")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "not_found")

        status, payload = self.request("GET", "/api/missing")
        self.assertEqual(status, 404)
        self.assertEqual(payload, {"error": {"code": "not_found", "message": "API not found"}})


class WordImportExportSmokeTest(unittest.TestCase):
    def test_import_notes_and_export_heading_styles(self) -> None:
        parsed = DocxFolderParser().parse(build_test_docx())
        tree = parsed["tree"]

        self.assertEqual([heading["title"] for heading in parsed["headings"]], ["第一章", "第一节", "大纲标题"])
        self.assertEqual(tree[0]["name"], "第一章")
        self.assertEqual(tree[0]["note"], "第一章正文第一段\n第一章正文第二段")
        self.assertEqual(tree[0]["children"][0]["name"], "第一节")
        self.assertEqual(tree[0]["children"][0]["note"], "第一节正文")
        self.assertEqual(tree[1]["name"], "大纲标题")
        self.assertEqual(tree[1]["note"], "大纲标题正文")

        export_tree = [
            {
                "title": tree[0]["name"],
                "note": tree[0]["note"],
                "children": [
                    {
                        "title": tree[0]["children"][0]["name"],
                        "note": tree[0]["children"][0]["note"],
                        "children": [],
                    }
                ],
            }
        ]
        exported = build_docx("导出测试", export_tree)
        with zipfile.ZipFile(BytesIO(exported)) as docx:
            document_xml = docx.read("word/document.xml").decode("utf-8")
            styles_xml = docx.read("word/styles.xml").decode("utf-8")

        self.assertIn("第一章正文第一段", document_xml)
        self.assertIn('w:pStyle w:val="Heading1"', document_xml)
        self.assertIn('w:outlineLvl w:val="0"', document_xml)
        self.assertIn('w:pStyle w:val="Heading2"', document_xml)
        self.assertIn('w:outlineLvl w:val="1"', document_xml)
        self.assertIn('w:spacing w:before="240" w:after="120"', document_xml)
        self.assertIn('w:eastAsia="Microsoft YaHei"', styles_xml)
        self.assertIn('w:spacing w:after="160" w:line="360"', styles_xml)

        round_trip = DocxFolderParser().parse(exported)["tree"]
        self.assertEqual(round_trip[0]["name"], "第一章")
        self.assertEqual(round_trip[0]["note"], "第一章正文第一段\n第一章正文第二段")
        self.assertEqual(round_trip[0]["children"][0]["name"], "第一节")
        self.assertEqual(round_trip[0]["children"][0]["note"], "第一节正文")

    def test_export_keeps_note_under_matching_heading(self) -> None:
        export_tree = [
            {
                "title": "一级节点",
                "note": "一级正文第一段\n一级正文第二段",
                "children": [
                    {
                        "title": "二级节点",
                        "note": "二级正文",
                        "children": [],
                    }
                ],
            },
            {
                "title": "另一个一级节点",
                "note": "另一个正文",
                "children": [],
            },
        ]

        round_trip = DocxFolderParser().parse(build_docx("导出正文测试", export_tree))["tree"]

        self.assertEqual(round_trip[0]["name"], "一级节点")
        self.assertEqual(round_trip[0]["note"], "一级正文第一段\n一级正文第二段")
        self.assertEqual(round_trip[0]["children"][0]["name"], "二级节点")
        self.assertEqual(round_trip[0]["children"][0]["note"], "二级正文")
        self.assertEqual(round_trip[1]["name"], "另一个一级节点")
        self.assertEqual(round_trip[1]["note"], "另一个正文")

    def test_node_note_update_survives_project_reload_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            original_db_path = db.DB_PATH
            db.DB_PATH = Path(tmpdir) / "note-export.sqlite3"
            try:
                db.init_db()
                with db.connect() as conn:
                    project_id = projects.create_project(conn, "正文回写")
                    conn.commit()

                node = projects.create_node(project_id, None, "章节")
                projects.update_node(node["id"], "章节", "保存后的正文\n第二段正文")

                reloaded = projects.get_project(project_id)
                self.assertEqual(reloaded["tree"][0]["note"], "保存后的正文\n第二段正文")

                _, exported = projects.export_project_docx(project_id)
                round_trip = DocxFolderParser().parse(exported)["tree"]
                self.assertEqual(round_trip[0]["name"], "章节")
                self.assertEqual(round_trip[0]["note"], "保存后的正文\n第二段正文")
            finally:
                db.DB_PATH = original_db_path


def build_test_docx() -> bytes:
    files = {
        "[Content_Types].xml": """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>""",
        "_rels/.rels": """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
        "word/styles.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="cnHeading1"><w:name w:val="标题 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="cnHeading2"><w:name w:val="标题 2"/></w:style>
</w:styles>""",
        "word/document.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="cnHeading1"/></w:pPr><w:r><w:t>第一章</w:t></w:r></w:p>
    <w:p><w:r><w:t>第一章正文第一段</w:t></w:r></w:p>
    <w:p><w:r><w:t>第一章正文第二段</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="cnHeading2"/></w:pPr><w:r><w:t>第一节</w:t></w:r></w:p>
    <w:p><w:r><w:t>第一节正文</w:t></w:r></w:p>
    <w:p><w:pPr><w:outlineLvl w:val="0"/></w:pPr><w:r><w:t>大纲标题</w:t></w:r></w:p>
    <w:p><w:r><w:t>大纲标题正文</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>""",
    }
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        for path, content in files.items():
            docx.writestr(path, content)
    return buffer.getvalue()


if __name__ == "__main__":
    unittest.main()
