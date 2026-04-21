from __future__ import annotations

import base64
import json
import sqlite3
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
from backend.services import projects
from backend.services.docx_exporter import build_docx
from backend.services.docx_parser import DocxFolderParser
from backend.services.importers import ImporterError, import_file, registry
from backend.services.exporters import ExporterError, export_project_file


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
        self.assertEqual(first["sourceType"], "manual")
        self.assertEqual(first["metadata"], {})

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

    def test_import_docx_uses_registered_importer_and_persists_metadata(self) -> None:
        payload = base64.b64encode(build_test_docx()).decode("ascii")
        project = projects.create_project_from_upload("导入测试.docx", payload)

        self.assertEqual(project["name"], "导入测试")
        self.assertEqual(project["sourceType"], "docx")
        self.assertIn(".docx", registry.supported_extensions())
        self.assertEqual([heading["title"] for heading in project["headings"]], ["第一章", "第一节", "大纲标题"])

        tree = project["tree"]
        self.assertEqual(tree[0]["title"], "第一章")
        self.assertEqual(tree[0]["note"], "第一章正文第一段\n第一章正文第二段")
        self.assertEqual(tree[0]["sourceType"], "docx")
        self.assertEqual(tree[0]["metadata"]["source_parser"], "DocxFolderParser")
        self.assertEqual(tree[0]["children"][0]["title"], "第一节")

        imported = import_file("again.docx", build_test_docx())
        self.assertEqual(imported.source_type, "docx")
        self.assertEqual(imported.tree[0].source_type, "docx")

    def test_pdf_import_builds_tree_from_selectable_text(self) -> None:
        payload = base64.b64encode(build_test_pdf()).decode("ascii")
        project = projects.create_project_from_upload("PDF 导入测试.pdf", payload)

        self.assertEqual(project["name"], "PDF 导入测试")
        self.assertEqual(project["sourceType"], "pdf")
        self.assertEqual(project["metadata"]["source_parser"], "PdfParser")
        self.assertEqual(project["tree"][0]["title"], "1 Project Overview")
        self.assertIn("Project body paragraph", project["tree"][0]["note"])
        self.assertEqual(project["tree"][0]["children"][0]["title"], "1.1 Scope")
        self.assertEqual(project["headings"][0]["source"], "pdf-text")

    def test_image_import_creates_source_node_with_ocr_warning(self) -> None:
        payload = base64.b64encode(MINIMAL_PNG).decode("ascii")
        project = projects.create_project_from_upload("图片导入.png", payload)

        self.assertEqual(project["name"], "图片导入")
        self.assertEqual(project["sourceType"], "image")
        self.assertIn(".png", registry.supported_extensions())
        self.assertEqual(project["tree"][0]["title"], "图片导入")
        self.assertIn("Source image: 图片导入.png", project["tree"][0]["note"])
        self.assertIn("OCR is not configured", project["tree"][0]["note"])
        self.assertEqual(project["importWarnings"][0]["code"], "ocr_unavailable")

    def test_import_epub_builds_chapter_tree_and_notes(self) -> None:
        imported = import_file("电子书样例.epub", build_test_epub())

        self.assertEqual(imported.title, "电子书样例")
        self.assertEqual(imported.source_type, "epub")
        self.assertIn(".epub", registry.supported_extensions())
        self.assertEqual([heading["title"] for heading in imported.headings], ["第一章", "第一节", "第二章"])
        self.assertEqual(imported.tree[0].title, "第一章")
        self.assertIn("第一章正文第一段", imported.tree[0].note)
        self.assertEqual(imported.tree[0].children[0].title, "第一节")
        self.assertIn("第一节正文", imported.tree[0].children[0].note)
        self.assertEqual(imported.tree[1].title, "第二章")

        payload = base64.b64encode(build_test_epub()).decode("ascii")
        project = projects.create_project_from_upload("电子书样例.epub", payload)
        self.assertEqual(project["sourceType"], "epub")
        self.assertEqual(project["tree"][0]["sourceType"], "epub")
        self.assertEqual(project["tree"][0]["metadata"]["source_parser"], "EpubParser")
        self.assertIn("第一章正文第二段", project["tree"][0]["note"])

    def test_import_azw3_reports_conversion_requirement(self) -> None:
        with self.assertRaises(ImporterError) as context:
            import_file("kindle.azw3", b"BOOKMOBI")

        self.assertEqual(context.exception.code, "azw3_conversion_required")
        self.assertIn("Calibre", context.exception.message)

    def test_csv_import_creates_sheet_rows_and_notes(self) -> None:
        csv_content = "标题,负责人,状态\n需求梳理,Alice,进行中\n上线验收,Bob,待开始\n".encode("utf-8")
        payload = base64.b64encode(csv_content).decode("ascii")
        project = projects.create_project_from_upload("计划.csv", payload)

        self.assertEqual(project["sourceType"], "csv")
        self.assertEqual(project["metadata"]["rows"], 2)
        sheet = project["tree"][0]
        self.assertEqual(sheet["title"], "计划")
        self.assertEqual([node["title"] for node in sheet["children"]], ["需求梳理", "上线验收"])
        self.assertEqual(sheet["children"][0]["sourceType"], "csv")
        self.assertIn("负责人: Alice", sheet["children"][0]["note"])
        self.assertIn("状态: 进行中", sheet["children"][0]["note"])

    def test_freemind_mm_import_preserves_hierarchy(self) -> None:
        mm_content = b"""<?xml version="1.0" encoding="UTF-8"?>
<map version="1.0.1">
  <node TEXT="Root">
    <node TEXT="Branch A">
      <node TEXT="Leaf A1"/>
    </node>
    <node TEXT="Branch B">
      <richcontent TYPE="NOTE"><html><body><p>Branch note</p></body></html></richcontent>
    </node>
  </node>
</map>"""
        payload = base64.b64encode(mm_content).decode("ascii")
        project = projects.create_project_from_upload("mind.mm", payload)

        self.assertEqual(project["sourceType"], "freemind")
        self.assertEqual(project["metadata"]["nodes"], 4)
        root = project["tree"][0]
        self.assertEqual(root["title"], "Root")
        self.assertEqual(root["children"][0]["title"], "Branch A")
        self.assertEqual(root["children"][0]["children"][0]["title"], "Leaf A1")
        self.assertEqual(root["children"][1]["note"], "Branch note")

    def test_init_db_adds_import_columns_to_existing_nodes_table(self) -> None:
        legacy_db_path = Path(self.tmpdir.name) / "legacy.sqlite3"
        with sqlite3.connect(legacy_db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE projects (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE nodes (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  project_id INTEGER NOT NULL,
                  parent_id INTEGER,
                  title TEXT NOT NULL,
                  note TEXT NOT NULL DEFAULT '',
                  position INTEGER NOT NULL DEFAULT 0,
                  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

        db.init_db(legacy_db_path)
        with db.connect(legacy_db_path) as conn:
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}

        self.assertIn("note", columns)
        self.assertIn("source_type", columns)
        self.assertIn("metadata", columns)

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
        self.assertIn(b"/BaseFont /STSong-Light", pdf_export.data)
        self.assertIn(b"/Encoding /UniGB-UCS2-H", pdf_export.data)

        mm_export = export_project_file("导出测试", tree, "mm")
        self.assertEqual(mm_export.filename, "导出测试.mm")
        self.assertIn(b"<map", mm_export.data)
        self.assertIn("第一章".encode("utf-8"), mm_export.data)
        self.assertIn(b"\n  <node TEXT=", mm_export.data)

        png_export = export_project_file("导出测试", tree, "png")
        self.assertEqual(png_export.content_type, "image/png")
        self.assertEqual(png_export.data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertGreater(len(png_export.data), 1024)

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

    def test_upload_endpoint_dispatches_by_extension(self) -> None:
        encoded_docx = base64.b64encode(build_test_docx()).decode("ascii")
        encoded_epub = base64.b64encode(build_test_epub()).decode("ascii")

        status, payload = self.request(
            "POST",
            "/api/projects/import",
            {"filename": "接口导入.docx", "file": encoded_docx},
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["project"]["sourceType"], "docx")
        self.assertEqual(payload["project"]["tree"][0]["note"], "第一章正文第一段\n第一章正文第二段")

        status, payload = self.request(
            "POST",
            "/api/projects/import-docx",
            {"filename": "兼容导入.docx", "file": encoded_docx},
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["project"]["tree"][0]["sourceType"], "docx")

        status, payload = self.request(
            "POST",
            "/api/projects/import",
            {"filename": "接口 PDF.pdf", "file": base64.b64encode(build_test_pdf()).decode("ascii")},
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["project"]["sourceType"], "pdf")

        status, payload = self.request(
            "POST",
            "/api/projects/import",
            {"filename": "接口图片.png", "file": base64.b64encode(MINIMAL_PNG).decode("ascii")},
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["project"]["sourceType"], "image")
        self.assertEqual(payload["project"]["importWarnings"][0]["code"], "ocr_unavailable")

        status, payload = self.request(
            "POST",
            "/api/projects/import",
            {"filename": "接口电子书.epub", "file": encoded_epub},
        )
        self.assertEqual(status, 201)
        self.assertEqual(payload["project"]["sourceType"], "epub")
        self.assertIn("第一章正文第一段", payload["project"]["tree"][0]["note"])

        status, payload = self.request(
            "POST",
            "/api/projects/import",
            {"filename": "kindle.azw3", "file": base64.b64encode(b"BOOKMOBI").decode("ascii")},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "azw3_conversion_required")

        status, payload = self.request(
            "POST",
            "/api/projects/import",
            {"filename": "mind.xmind", "file": encoded_docx},
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "unsupported_format")

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
        "word/document.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:pPr><w:pStyle w:val="标题 1"/></w:pPr>
      <w:r><w:t>第一章</w:t></w:r>
    </w:p>
    <w:p><w:r><w:t>第一章正文第一段</w:t></w:r></w:p>
    <w:p><w:r><w:t>第一章正文第二段</w:t></w:r></w:p>
    <w:p>
      <w:pPr><w:pStyle w:val="Heading2"/></w:pPr>
      <w:r><w:t>第一节</w:t></w:r>
    </w:p>
    <w:p><w:r><w:t>第一节正文</w:t></w:r></w:p>
    <w:p>
      <w:pPr><w:outlineLvl w:val="0"/></w:pPr>
      <w:r><w:t>大纲标题</w:t></w:r>
    </w:p>
    <w:p><w:r><w:t>大纲标题正文</w:t></w:r></w:p>
    <w:sectPr/>
  </w:body>
</w:document>""",
        "word/styles.xml": """<?xml version="1.0" encoding="UTF-8"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:styleId="标题 1"><w:name w:val="标题 1"/></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/></w:style>
</w:styles>""",
    }
    return build_zip(files)


def build_test_pdf() -> bytes:
    stream_text = "\n".join(
        [
            "BT",
            "/F1 18 Tf",
            "72 720 Td",
            "(1 Project Overview) Tj",
            "0 -24 Td",
            "(Project body paragraph) Tj",
            "0 -24 Td",
            "(1.1 Scope) Tj",
            "0 -24 Td",
            "(Scope detail line) Tj",
            "ET",
        ]
    ).encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R >>\nendobj\n",
        (
            b"4 0 obj\n<< /Length "
            + str(len(stream_text)).encode("ascii")
            + b" >>\nstream\n"
            + stream_text
            + b"\nendstream\nendobj\n"
        ),
    ]

    pdf = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        (
            "trailer\n"
            f"<< /Size {len(offsets)} /Root 1 0 R >>\n"
            "startxref\n"
            f"{xref_offset}\n"
            "%%EOF\n"
        ).encode("ascii")
    )
    return bytes(pdf)


def build_test_epub() -> bytes:
    files = {
        "mimetype": "application/epub+zip",
        "META-INF/container.xml": """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>""",
        "OEBPS/content.opf": """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="bookid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>电子书样例</dc:title>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="ch1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>""",
        "OEBPS/toc.ncx": """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="navPoint-1" playOrder="1">
      <navLabel><text>第一章</text></navLabel>
      <content src="chapter1.xhtml"/>
      <navPoint id="navPoint-1-1" playOrder="2">
        <navLabel><text>第一节</text></navLabel>
        <content src="chapter1.xhtml#section1"/>
      </navPoint>
    </navPoint>
    <navPoint id="navPoint-2" playOrder="3">
      <navLabel><text>第二章</text></navLabel>
      <content src="chapter2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>""",
        "OEBPS/chapter1.xhtml": """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>第一章</h1>
    <p>第一章正文第一段</p>
    <p>第一章正文第二段</p>
    <h2 id="section1">第一节</h2>
    <p>第一节正文</p>
  </body>
</html>""",
        "OEBPS/chapter2.xhtml": """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <body>
    <h1>第二章</h1>
    <p>第二章正文</p>
  </body>
</html>""",
    }
    return build_zip(files, store_mimetype=True)


MINIMAL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9sX8x7EAAAAASUVORK5CYII="
)


def build_zip(files: dict[str, str], *, store_mimetype: bool = False) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            compression = zipfile.ZIP_STORED if store_mimetype and name == "mimetype" else zipfile.ZIP_DEFLATED
            archive.writestr(name, content, compress_type=compression)
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
