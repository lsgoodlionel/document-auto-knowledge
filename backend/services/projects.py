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
        insert_tree(conn, project_id, None, parsed["tree"], source_project_id=project_id)
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
    *,
    source_project_id: int | None = None,
) -> None:
    for position, node in enumerate(nodes):
        cursor = conn.execute(
            """
            INSERT INTO nodes(project_id, parent_id, title, note, source_project_id, source_node_id, position)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                parent_id,
                sanitize_name(node.get("title") or node.get("name") or "untitled"),
                node.get("note", ""),
                node.get("sourceProjectId", source_project_id),
                node.get("sourceNodeId"),
                position,
            ),
        )
        node_id = int(cursor.lastrowid)
        insert_tree(conn, project_id, node_id, node.get("children", []), source_project_id=source_project_id)


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
        project_names = load_project_names(conn)

    project = row_to_dict(project_row)
    project["tree"] = build_node_tree([row_to_dict(row) for row in node_rows], project_names)
    return project


def rename_project(project_id: int, name: str) -> dict[str, Any]:
    project_name = sanitize_name(name)
    with connect() as conn:
        ensure_project(conn, project_id)
        conn.execute(
            "UPDATE projects SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_name, project_id),
        )
        conn.commit()
    return get_project(project_id)


def delete_project(project_id: int) -> None:
    with connect() as conn:
        ensure_project(conn, project_id)
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        conn.commit()


def build_node_tree(rows: list[dict[str, Any]], project_names: dict[int, str] | None = None) -> list[dict[str, Any]]:
    project_names = project_names or {}
    by_id: dict[int, dict[str, Any]] = {}
    roots: list[dict[str, Any]] = []
    for row in rows:
        source_project_id = row.get("source_project_id")
        node = {
            "id": row["id"],
            "projectId": row["project_id"],
            "parentId": row["parent_id"],
            "title": row["title"],
            "name": row["title"],
            "note": row["note"],
            "sourceProjectId": source_project_id,
            "sourceProjectName": project_names.get(source_project_id) if source_project_id else None,
            "sourceNodeId": row.get("source_node_id"),
            "linkedCopy": bool(source_project_id and source_project_id != row["project_id"]),
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
        ensure_project(conn, project_id)
        if parent_id is not None:
            ensure_node_in_project(conn, parent_id, project_id)
        position = next_position(conn, project_id, parent_id)
        cursor = conn.execute(
            """
            INSERT INTO nodes(project_id, parent_id, title, note, source_project_id, source_node_id, position)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, parent_id, sanitize_name(title), note, project_id, None, position),
        )
        conn.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
        conn.commit()
        node_id = int(cursor.lastrowid)
    return get_node(node_id)


def update_node(node_id: int, title: str, note: str) -> dict[str, Any]:
    with connect() as conn:
        node = ensure_node(conn, node_id)
        conn.execute(
            "UPDATE nodes SET title = ?, note = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (sanitize_name(title), note, node_id),
        )
        conn.execute(
            "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (node["project_id"],),
        )
        conn.commit()
    return get_node(node_id)


def delete_node(node_id: int) -> None:
    with connect() as conn:
        node = ensure_node(conn, node_id)
        conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        normalize_positions(conn, node["project_id"], node["parent_id"])
        conn.execute(
            "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (node["project_id"],),
        )
        conn.commit()


def move_node(node_id: int, parent_id: int | None, position: int | None) -> dict[str, Any]:
    with connect() as conn:
        node = ensure_node(conn, node_id)
        project_id = int(node["project_id"])
        old_parent_id = node["parent_id"]

        if parent_id is not None:
            ensure_node_in_project(conn, parent_id, project_id)
            if parent_id == node_id or is_descendant(conn, parent_id, node_id):
                raise ValueError("node cannot be moved under itself or its descendants")

        sibling_count = count_siblings(conn, project_id, parent_id, exclude_node_id=node_id)
        target_position = clamp_position(position, sibling_count)

        conn.execute("UPDATE nodes SET position = -1 WHERE id = ?", (node_id,))
        normalize_positions(conn, project_id, old_parent_id)
        conn.execute(
            """
            UPDATE nodes
            SET position = position + 1
            WHERE project_id = ?
              AND ((? IS NULL AND parent_id IS NULL) OR parent_id = ?)
              AND position >= ?
              AND id != ?
            """,
            (project_id, parent_id, parent_id, target_position, node_id),
        )
        conn.execute(
            """
            UPDATE nodes
            SET parent_id = ?, position = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (parent_id, target_position, node_id),
        )
        conn.execute(
            "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (project_id,),
        )
        conn.commit()
    return get_node(node_id)


def attach_project_subtree(
    target_project_id: int,
    target_parent_id: int | None,
    source_project_id: int,
    source_root_node_id: int | None = None,
) -> dict[str, Any]:
    with connect() as conn:
        ensure_project(conn, target_project_id)
        ensure_project(conn, source_project_id)
        if target_project_id == source_project_id:
            raise ValueError("cross-project linking requires different source and target projects")
        if target_parent_id is not None:
            ensure_node_in_project(conn, target_parent_id, target_project_id)

        source_rows = conn.execute(
            "SELECT * FROM nodes WHERE project_id = ? ORDER BY parent_id IS NOT NULL, parent_id, position, id",
            (source_project_id,),
        ).fetchall()
        project_names = load_project_names(conn)
        source_tree = build_node_tree([row_to_dict(row) for row in source_rows], project_names)

        if source_root_node_id is None:
            nodes_to_attach = source_tree
        else:
            source_root = find_tree_node(source_root_node_id, source_tree)
            if source_root is None:
                raise KeyError("source node not found")
            if source_root["parentId"] is not None:
                raise ValueError("only source project root nodes can be attached across projects")
            nodes_to_attach = [source_root]

        if not nodes_to_attach:
            raise ValueError("source project has no root nodes to attach")

        cloned_nodes = [clone_as_linked_subtree(node, source_project_id) for node in nodes_to_attach]
        insert_tree(conn, target_project_id, target_parent_id, cloned_nodes, source_project_id=source_project_id)
        conn.execute(
            "UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id IN (?, ?)",
            (target_project_id, source_project_id),
        )
        conn.commit()

    return get_project(target_project_id)


def get_node(node_id: int) -> dict[str, Any]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        project_names = load_project_names(conn)
    if row is None:
        raise KeyError("node not found")
    data = row_to_dict(row)
    source_project_id = data.get("source_project_id")
    return {
        "id": data["id"],
        "projectId": data["project_id"],
        "parentId": data["parent_id"],
        "title": data["title"],
        "name": data["title"],
        "note": data["note"],
        "sourceProjectId": source_project_id,
        "sourceProjectName": project_names.get(source_project_id) if source_project_id else None,
        "sourceNodeId": data.get("source_node_id"),
        "linkedCopy": bool(source_project_id and source_project_id != data["project_id"]),
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


def ensure_project(conn: sqlite3.Connection, project_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise KeyError("project not found")
    return row


def ensure_node(conn: sqlite3.Connection, node_id: int) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if row is None:
        raise KeyError("node not found")
    return row


def ensure_node_in_project(conn: sqlite3.Connection, node_id: int, project_id: int) -> sqlite3.Row:
    row = ensure_node(conn, node_id)
    if int(row["project_id"]) != project_id:
        raise ValueError("parent node belongs to another project")
    return row


def is_descendant(conn: sqlite3.Connection, node_id: int, ancestor_id: int) -> bool:
    current_id: int | None = node_id
    while current_id is not None:
        row = conn.execute("SELECT parent_id FROM nodes WHERE id = ?", (current_id,)).fetchone()
        if row is None:
            return False
        current_id = row["parent_id"]
        if current_id == ancestor_id:
            return True
    return False


def count_siblings(
    conn: sqlite3.Connection,
    project_id: int,
    parent_id: int | None,
    exclude_node_id: int | None = None,
) -> int:
    if parent_id is None:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM nodes
            WHERE project_id = ? AND parent_id IS NULL AND (? IS NULL OR id != ?)
            """,
            (project_id, exclude_node_id, exclude_node_id),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM nodes
            WHERE project_id = ? AND parent_id = ? AND (? IS NULL OR id != ?)
            """,
            (project_id, parent_id, exclude_node_id, exclude_node_id),
        ).fetchone()
    return int(row["count"])


def clamp_position(position: int | None, sibling_count: int) -> int:
    if position is None:
        return sibling_count
    try:
        parsed = int(position)
    except (TypeError, ValueError) as exc:
        raise ValueError("position must be an integer") from exc
    return max(0, min(parsed, sibling_count))


def normalize_positions(conn: sqlite3.Connection, project_id: int, parent_id: int | None) -> None:
    if parent_id is None:
        rows = conn.execute(
            """
            SELECT id FROM nodes
            WHERE project_id = ? AND parent_id IS NULL AND position >= 0
            ORDER BY position, id
            """,
            (project_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id FROM nodes
            WHERE project_id = ? AND parent_id = ? AND position >= 0
            ORDER BY position, id
            """,
            (project_id, parent_id),
        ).fetchall()

    for position, row in enumerate(rows):
        conn.execute("UPDATE nodes SET position = ? WHERE id = ?", (position, row["id"]))


def export_project_docx(project_id: int) -> tuple[str, bytes]:
    project = get_project(project_id)
    return f"{sanitize_name(project['name'])}.docx", build_docx(project["name"], project["tree"])


def load_project_names(conn: sqlite3.Connection) -> dict[int, str]:
    rows = conn.execute("SELECT id, name FROM projects").fetchall()
    return {int(row["id"]): str(row["name"]) for row in rows}


def clone_as_linked_subtree(node: dict[str, Any], source_project_id: int) -> dict[str, Any]:
    origin_project_id = node.get("sourceProjectId") or source_project_id
    origin_node_id = node.get("sourceNodeId") or node["id"]
    return {
        "title": node.get("title") or node.get("name") or "untitled",
        "name": node.get("title") or node.get("name") or "untitled",
        "note": node.get("note", ""),
        "sourceProjectId": origin_project_id,
        "sourceNodeId": origin_node_id,
        "children": [clone_as_linked_subtree(child, source_project_id) for child in node.get("children", [])],
    }


def find_tree_node(node_id: int, nodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for node in nodes:
        if node["id"] == node_id:
            return node
        child = find_tree_node(node_id, node["children"])
        if child is not None:
            return child
    return None
