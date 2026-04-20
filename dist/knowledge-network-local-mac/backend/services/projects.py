from __future__ import annotations

import base64
import sqlite3
from typing import Any

from ..db import connect, row_to_dict
from .docx_exporter import build_docx
from .docx_parser import DocxFolderParser, sanitize_name


def create_project_from_docx(filename: str, file_base64: str) -> dict[str, Any]:
    content = base64.b64decode(file_base64.encode("utf-8"), validate=True)
    parsed = DocxFolderParser().parse(content)
    project_name = sanitize_name(filename.rsplit(".", 1)[0] if filename else "untitled")

    with connect() as conn:
        project_id = create_project(conn, project_name)
        insert_tree(conn, project_id, None, parsed["tree"])
        conn.commit()

    project = get_project(project_id)
    project["headings"] = parsed["headings"]
    return project


def create_project(conn: sqlite3.Connection, name: str) -> int:
    cursor = conn.execute("INSERT INTO projects(name) VALUES (?)", (name,))
    return int(cursor.lastrowid)


def insert_tree(
    conn: sqlite3.Connection,
    project_id: int,
    parent_id: int | None,
    nodes: list[dict[str, Any]],
) -> None:
    for position, node in enumerate(nodes):
        cursor = conn.execute(
            """
            INSERT INTO nodes(project_id, parent_id, title, note, position)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, parent_id, node["name"], node.get("note", ""), position),
        )
        node_id = int(cursor.lastrowid)
        insert_tree(conn, project_id, node_id, node.get("children", []))


def list_projects() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC, id DESC").fetchall()
    return [row_to_dict(row) for row in rows]


def get_project(project_id: int) -> dict[str, Any]:
    with connect() as conn:
        project_row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if project_row is None:
            raise KeyError("project not found")
        node_rows = conn.execute(
            "SELECT * FROM nodes WHERE project_id = ? ORDER BY parent_id IS NOT NULL, parent_id, position, id",
            (project_id,),
        ).fetchall()

    project = row_to_dict(project_row)
    project["tree"] = build_node_tree([row_to_dict(row) for row in node_rows])
    return project


def build_node_tree(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in rows:
        node = {
            "id": row["id"],
            "projectId": row["project_id"],
            "parentId": row["parent_id"],
            "title": row["title"],
            "name": row["title"],
            "note": row["note"],
            "position": row["position"],
            "children": [],
        }
        by_id[node["id"]] = node

    for node in by_id.values():
        parent_id = node["parentId"]
        if parent_id and parent_id in by_id:
            by_id[parent_id]["children"].append(node)
        else:
            roots.append(node)

    sort_tree(roots)
    return roots


def sort_tree(nodes: list[dict[str, Any]]) -> None:
    nodes.sort(key=lambda node: (node["position"], node["id"]))
    for node in nodes:
        sort_tree(node["children"])


def create_node(project_id: int, parent_id: int | None, title: str, note: str = "") -> dict[str, Any]:
    with connect() as conn:
        position = next_position(conn, project_id, parent_id)
        cursor = conn.execute(
            """
            INSERT INTO nodes(project_id, parent_id, title, note, position)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, parent_id, sanitize_name(title), note, position),
        )
        conn.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
        conn.commit()
        node_id = int(cursor.lastrowid)
    return get_node(node_id)


def update_node(node_id: int, title: str, note: str) -> dict[str, Any]:
    with connect() as conn:
        conn.execute(
            "UPDATE nodes SET title = ?, note = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (sanitize_name(title), note, node_id),
        )
        conn.execute(
            "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = (SELECT project_id FROM nodes WHERE id = ?)",
            (node_id,),
        )
        conn.commit()
    return get_node(node_id)


def delete_node(node_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        conn.commit()


def get_node(node_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if row is None:
        raise KeyError("node not found")
    data = row_to_dict(row)
    return {
        "id": data["id"],
        "projectId": data["project_id"],
        "parentId": data["parent_id"],
        "title": data["title"],
        "name": data["title"],
        "note": data["note"],
        "position": data["position"],
        "children": [],
    }


def next_position(conn: sqlite3.Connection, project_id: int, parent_id: int | None) -> int:
    if parent_id is None:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS next_position FROM nodes WHERE project_id = ? AND parent_id IS NULL",
            (project_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 AS next_position FROM nodes WHERE project_id = ? AND parent_id = ?",
            (project_id, parent_id),
        ).fetchone()
    return int(row["next_position"])


def export_project_docx(project_id: int) -> tuple[str, bytes]:
    project = get_project(project_id)
    return f"{sanitize_name(project['name'])}.docx", build_docx(project["name"], project["tree"])
