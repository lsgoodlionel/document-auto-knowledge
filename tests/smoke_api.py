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
from backend.services.exporters import ExporterError, export_project_file
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

    def test_attach_root_node_from_another_project_preserves_source_identity(self) -> None:
        with db.connect() as conn:
            target_project_id = projects.create_project(conn, "中图法")
            source_project_id = projects.create_project(conn, "囚徒的困境")
            conn.commit()

        social = projects.create_node(target_project_id, None, "社会科学")
        target_parent = projects.create_node(target_project_id, social["id"], "博弈论")
        source_root = projects.create_node(source_project_id, None, "囚徒的困境", "冲突与合作")
        source_child = projects.create_node(source_project_id, source_root["id"], "重复博弈", "长期关系")

        attached_project = projects.attach_project_subtree(
            target_project_id,
            target_parent["id"],
            source_project_id,
            source_root["id"],
        )

        attached_root = attached_project["tree"][0]["children"][0]["children"][0]
        self.assertEqual(attached_root["title"], "囚徒的困境")
        self.assertEqual(attached_root["note"], "冲突与合作")
        self.assertEqual(attached_root["sourceProjectId"], source_project_id)
        self.assertEqual(attached_root["sourceProjectName"], "囚徒的困境")
        self.assertEqual(attached_root["sourceNodeId"], source_root["id"])
        self.assertTrue(attached_root["linkedCopy"])
        self.assertEqual(attached_root["children"][0]["title"], "重复博弈")
        self.assertEqual(attached_root["children"][0]["sourceNodeId"], source_child["id"])

        source_project = projects.get_project(source_project_id)
        self.assertEqual(source_project["tree"][0]["title"], "囚徒的困境")
        self.assertEqual(source_project["tree"][0]["children"][0]["title"], "重复博弈")

    def test_attach_whole_project_adds_all_source_roots(self) -> None:
        with db.connect() as conn:
            target_project_id = projects.create_project(conn, "中图法")
            source_project_id = projects.create_project(conn, "社会科学案例")
            conn.commit()

        target_parent = projects.create_node(target_project_id, None, "社会科学")
        first_root = projects.create_node(source_project_id, None, "囚徒的困境")
        second_root = projects.create_node(source_project_id, None, "公共选择")

        attached_project = projects.attach_project_subtree(target_project_id, target_parent["id"], source_project_id)
        attached_titles = [node["title"] for node in attached_project["tree"][0]["children"]]
        self.assertEqual(attached_titles, ["囚徒的困境", "公共选择"])
        self.assertEqual(attached_project["tree"][0]["children"][0]["sourceNodeId"], first_root["id"])
        self.assertEqual(attached_project["tree"][0]["children"][1]["sourceNodeId"], second_root["id"])

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

    def test_multi_export_framework_outputs_expected_formats(self) -> None:
        tree = sample_tree()

        docx_export = export_project_file("导出测试", tree, "docx")
        self.assertEqual(docx_export.filename, "导出测试.docx")
        self.assertTrue(docx_export.data.startswith(b"PK"))

        pdf_export = export_project_file("导出测试", tree, "pdf")
        self.assertEqual(pdf_export.content_type, "application/pdf")
        self.assertTrue(pdf_export.data.startswith(b"%PDF-1.4"))

        mm_export = export_project_file("导出测试", tree, "mm")
        self.assertEqual(mm_export.filename, "导出测试.mm")
        self.assertIn(b"<map", mm_export.data)
        self.assertIn("第一章".encode("utf-8"), mm_export.data)

        png_export = export_project_file("导出测试", tree, "png")
        self.assertEqual(png_export.content_type, "image/png")
        self.assertEqual(png_export.data[:8], b"\x89PNG\r\n\x1a\n")

    def test_multi_export_framework_rejects_unsupported_format(self) -> None:
        with self.assertRaises(ExporterError) as context:
            export_project_file("导出测试", sample_tree(), "svg")

        self.assertEqual(context.exception.code, "unsupported_export_format")
        self.assertIn("svg", context.exception.message)


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

    def request_binary(
        self,
        method: str,
        path: str,
        payload: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, str], bytes]:
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = response.read()
        response_headers = {key: value for key, value in response.getheaders()}
        connection.close()
        return response.status, response_headers, data

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

    def test_cross_project_attachment_api(self) -> None:
        with db.connect() as conn:
            target_project_id = projects.create_project(conn, "中图法")
            source_project_id = projects.create_project(conn, "囚徒的困境")
            conn.commit()

        target_parent = projects.create_node(target_project_id, None, "社会科学")
        source_root = projects.create_node(source_project_id, None, "囚徒的困境", "合作困境")
        projects.create_node(source_project_id, source_root["id"], "纳什均衡", "均衡说明")

        status, payload = self.request(
            "POST",
            f"/api/projects/{target_project_id}/attachments",
            {
                "targetParentId": target_parent["id"],
                "sourceProjectId": source_project_id,
                "sourceRootNodeId": source_root["id"],
            },
        )
        self.assertEqual(status, 200)
        attached_root = payload["project"]["tree"][0]["children"][0]
        self.assertEqual(attached_root["title"], "囚徒的困境")
        self.assertEqual(attached_root["sourceProjectId"], source_project_id)
        self.assertEqual(attached_root["sourceProjectName"], "囚徒的困境")
        self.assertTrue(attached_root["linkedCopy"])

        status, payload = self.request(
            "POST",
            f"/api/projects/{target_project_id}/attachments",
            {
                "targetParentId": target_parent["id"],
                "sourceProjectId": target_project_id,
            },
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "bad_request")

    def test_export_endpoint_supports_multiple_formats(self) -> None:
        with db.connect() as conn:
            project_id = projects.create_project(conn, "导出接口")
            projects.insert_tree(conn, project_id, None, sample_tree())
            conn.commit()

        status, headers, data = self.request_binary("GET", f"/api/projects/{project_id}/export")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        self.assertTrue(data.startswith(b"PK"))
        self.assertIn("download.docx", headers["Content-Disposition"])

        status, headers, data = self.request_binary("GET", f"/api/projects/{project_id}/export?format=pdf")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/pdf")
        self.assertTrue(data.startswith(b"%PDF-1.4"))

        status, headers, data = self.request_binary("GET", f"/api/projects/{project_id}/export?format=mm")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/x-freemind")
        self.assertIn(b"<map", data)

        status, headers, data = self.request_binary("GET", f"/api/projects/{project_id}/export?format=png")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "image/png")
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

        status, payload = self.request("GET", f"/api/projects/{project_id}/export?format=svg")
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "unsupported_export_format")


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


def sample_tree() -> list[dict[str, object]]:
    return [
        {
            "title": "第一章",
            "note": "第一章正文第一段\n第一章正文第二段",
            "children": [
                {
                    "title": "第一节",
                    "note": "第一节正文",
                    "children": [],
                }
            ],
        },
        {
            "title": "第二章",
            "note": "第二章正文",
            "children": [],
        },
    ]


if __name__ == "__main__":
    unittest.main()
