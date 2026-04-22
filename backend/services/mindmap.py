from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..db import connect, row_to_dict
from . import projects
from .docx_parser import sanitize_name


MINDMAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS mindmap_edges (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  from_node_id INTEGER NOT NULL,
  to_node_id INTEGER NOT NULL,
  relation TEXT NOT NULL DEFAULT 'related',
  label TEXT NOT NULL DEFAULT '',
  metadata TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(from_node_id) REFERENCES nodes(id) ON DELETE CASCADE,
  FOREIGN KEY(to_node_id) REFERENCES nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_mindmap_edges_project
ON mindmap_edges(project_id, from_node_id, to_node_id);
CREATE TABLE IF NOT EXISTS mindmap_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  payload TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_mindmap_snapshots_project
ON mindmap_snapshots(project_id, id DESC);
"""


def get_project_mindmap(project_id: int) -> dict[str, Any]:
    project = projects.get_project(project_id)
    with connect() as conn:
        ensure_mindmap_schema(conn)
        edges = list_edges(conn, project_id)
        snapshot_info = latest_snapshot_info(conn, project_id)
    return build_mindmap_payload(project, edges, snapshot_info)


def save_project_mindmap(project_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    tree = payload.get("tree")
    if not isinstance(tree, list):
        raise ValueError("mindmap tree must be a list")
    edge_payloads = payload.get("edges", [])
    if not isinstance(edge_payloads, list):
        raise ValueError("mindmap edges must be a list")

    with connect() as conn:
        ensure_mindmap_schema(conn)
        projects.ensure_project(conn, project_id)
        existing_rows = conn.execute("SELECT * FROM nodes WHERE project_id = ?", (project_id,)).fetchall()
        existing_by_id = {int(row["id"]): row_to_dict(row) for row in existing_rows}
        seen_node_ids: set[int] = set()
        client_id_map: dict[str, int] = {}

        upsert_tree_nodes(
            conn,
            project_id,
            None,
            tree,
            existing_by_id,
            seen_node_ids,
            client_id_map,
        )

        delete_missing_nodes(conn, project_id, set(existing_by_id), seen_node_ids)
        replace_edges(conn, project_id, edge_payloads, existing_by_id, seen_node_ids, client_id_map)
        write_snapshot(conn, project_id, tree, edge_payloads)
        conn.execute("UPDATE projects SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (project_id,))
        conn.commit()

    return get_project_mindmap(project_id)


def build_mindmap_payload(
    project: dict[str, Any],
    edges: list[dict[str, Any]],
    snapshot_info: dict[str, Any],
) -> dict[str, Any]:
    return {
        "project": project,
        "nodes": flatten_tree_with_mindmap(project["tree"]),
        "edges": edges,
        "snapshot": snapshot_info,
    }


def ensure_mindmap_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(MINDMAP_SCHEMA)


def flatten_tree_with_mindmap(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for node in nodes:
        metadata = node.get("metadata") or {}
        mindmap_meta = metadata.get("mindmap") if isinstance(metadata, dict) else {}
        if not isinstance(mindmap_meta, dict):
            mindmap_meta = {}
        flattened.append(
            {
                "id": node["id"],
                "projectId": node["projectId"],
                "parentId": node["parentId"],
                "title": node["title"],
                "note": node.get("note", ""),
                "position": node["position"],
                "x": coerce_number(mindmap_meta.get("x"), 0.0),
                "y": coerce_number(mindmap_meta.get("y"), 0.0),
                "collapsed": bool(mindmap_meta.get("collapsed", False)),
                "style": normalize_style(mindmap_meta.get("style")),
                "sourceProjectId": node.get("sourceProjectId"),
                "sourceNodeId": node.get("sourceNodeId"),
            }
        )
        flattened.extend(flatten_tree_with_mindmap(node.get("children", [])))
    return flattened


def upsert_tree_nodes(
    conn: sqlite3.Connection,
    project_id: int,
    parent_id: int | None,
    nodes: list[dict[str, Any]],
    existing_by_id: dict[int, dict[str, Any]],
    seen_node_ids: set[int],
    client_id_map: dict[str, int],
) -> None:
    for position, raw_node in enumerate(nodes):
        if not isinstance(raw_node, dict):
            raise ValueError("each mindmap node must be an object")
        node_id = resolve_or_create_node(conn, project_id, raw_node, existing_by_id, client_id_map)
        metadata = build_node_metadata(existing_by_id.get(node_id, {}), raw_node)
        conn.execute(
            """
            UPDATE nodes
            SET parent_id = ?, title = ?, note = ?, metadata = ?, position = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND project_id = ?
            """,
            (
                parent_id,
                sanitize_name(str(raw_node.get("title") or "untitled")),
                str(raw_node.get("note") or ""),
                projects.encode_metadata(metadata),
                position,
                node_id,
                project_id,
            ),
        )
        seen_node_ids.add(node_id)
        updated = dict(existing_by_id.get(node_id, {}))
        updated.update(
            {
                "id": node_id,
                "project_id": project_id,
                "parent_id": parent_id,
                "title": sanitize_name(str(raw_node.get("title") or "untitled")),
                "note": str(raw_node.get("note") or ""),
                "metadata": projects.encode_metadata(metadata),
                "position": position,
            }
        )
        existing_by_id[node_id] = updated
        upsert_tree_nodes(
            conn,
            project_id,
            node_id,
            raw_node.get("children", []),
            existing_by_id,
            seen_node_ids,
            client_id_map,
        )


def resolve_or_create_node(
    conn: sqlite3.Connection,
    project_id: int,
    raw_node: dict[str, Any],
    existing_by_id: dict[int, dict[str, Any]],
    client_id_map: dict[str, int],
) -> int:
    node_id = raw_node.get("id")
    if node_id is not None:
        parsed = int(node_id)
        existing = existing_by_id.get(parsed)
        if existing is None or int(existing["project_id"]) != project_id:
            raise ValueError("mindmap node id does not belong to the target project")
        if client_id(raw_node):
            client_id_map[client_id(raw_node)] = parsed
        return parsed

    cursor = conn.execute(
        """
        INSERT INTO nodes(project_id, parent_id, title, note, source_type, metadata, source_project_id, source_node_id, position)
        VALUES (?, NULL, ?, '', 'manual', '{}', ?, NULL, 0)
        """,
        (project_id, sanitize_name(str(raw_node.get("title") or "untitled")), project_id),
    )
    new_id = int(cursor.lastrowid)
    if client_id(raw_node):
        client_id_map[client_id(raw_node)] = new_id
    return new_id


def delete_missing_nodes(
    conn: sqlite3.Connection,
    project_id: int,
    existing_ids: set[int],
    seen_node_ids: set[int],
) -> None:
    missing = sorted(existing_ids - seen_node_ids)
    for node_id in missing:
        conn.execute("DELETE FROM nodes WHERE id = ? AND project_id = ?", (node_id, project_id))


def replace_edges(
    conn: sqlite3.Connection,
    project_id: int,
    edges: list[dict[str, Any]],
    existing_by_id: dict[int, dict[str, Any]],
    seen_node_ids: set[int],
    client_id_map: dict[str, int],
) -> None:
    conn.execute("DELETE FROM mindmap_edges WHERE project_id = ?", (project_id,))
    valid_ids = seen_node_ids | set(existing_by_id)
    for edge in edges:
        if not isinstance(edge, dict):
            raise ValueError("each mindmap edge must be an object")
        from_node_id = resolve_edge_node(edge.get("fromNodeId"), edge.get("fromClientId"), client_id_map, valid_ids)
        to_node_id = resolve_edge_node(edge.get("toNodeId"), edge.get("toClientId"), client_id_map, valid_ids)
        if from_node_id == to_node_id:
            raise ValueError("mindmap edge cannot connect a node to itself")
        conn.execute(
            """
            INSERT INTO mindmap_edges(project_id, from_node_id, to_node_id, relation, label, metadata)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                from_node_id,
                to_node_id,
                str(edge.get("relation") or "related"),
                str(edge.get("label") or ""),
                projects.encode_metadata(edge.get("metadata", {})),
            ),
        )


def resolve_edge_node(
    node_id: Any,
    client_ref: Any,
    client_id_map: dict[str, int],
    valid_ids: set[int],
) -> int:
    if node_id is not None:
        parsed = int(node_id)
        if parsed not in valid_ids:
            raise ValueError("mindmap edge references a node outside the project")
        return parsed
    if client_ref is not None and str(client_ref) in client_id_map:
        return client_id_map[str(client_ref)]
    raise ValueError("mindmap edge is missing a valid node reference")


def build_node_metadata(existing_row: dict[str, Any], raw_node: dict[str, Any]) -> dict[str, Any]:
    existing_value = existing_row.get("metadata", {})
    existing_metadata = (
        projects.decode_metadata(existing_value)
        if not isinstance(existing_value, dict)
        else dict(existing_value)
    )
    metadata = dict(existing_metadata)
    if isinstance(raw_node.get("metadata"), dict):
        metadata.update(raw_node["metadata"])
    metadata["mindmap"] = {
        "x": coerce_number(raw_node.get("x"), 0.0),
        "y": coerce_number(raw_node.get("y"), 0.0),
        "collapsed": bool(raw_node.get("collapsed", False)),
        "style": normalize_style(raw_node.get("style")),
    }
    return metadata


def list_edges(conn: sqlite3.Connection, project_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM mindmap_edges WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    return [
        {
            "id": row["id"],
            "projectId": row["project_id"],
            "fromNodeId": row["from_node_id"],
            "toNodeId": row["to_node_id"],
            "relation": row["relation"],
            "label": row["label"],
            "metadata": projects.decode_metadata(row["metadata"]),
        }
        for row in rows
    ]


def write_snapshot(
    conn: sqlite3.Connection,
    project_id: int,
    tree: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    payload = {"nodeCount": count_nodes(tree), "edgeCount": len(edges)}
    conn.execute(
        "INSERT INTO mindmap_snapshots(project_id, payload) VALUES (?, ?)",
        (project_id, json.dumps(payload, ensure_ascii=False, sort_keys=True)),
    )


def latest_snapshot_info(conn: sqlite3.Connection, project_id: int) -> dict[str, Any]:
    row = conn.execute(
        "SELECT id, payload, created_at FROM mindmap_snapshots WHERE project_id = ? ORDER BY id DESC LIMIT 1",
        (project_id,),
    ).fetchone()
    count_row = conn.execute(
        "SELECT COUNT(*) AS total FROM mindmap_snapshots WHERE project_id = ?",
        (project_id,),
    ).fetchone()
    if row is None:
        return {"count": int(count_row["total"]), "latest": None}
    return {
        "count": int(count_row["total"]),
        "latest": {
            "id": row["id"],
            "createdAt": row["created_at"],
            "payload": projects.decode_metadata(row["payload"]),
        },
    }


def count_nodes(nodes: list[dict[str, Any]]) -> int:
    return sum(1 + count_nodes(node.get("children", [])) for node in nodes if isinstance(node, dict))


def coerce_number(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def normalize_style(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def client_id(raw_node: dict[str, Any]) -> str | None:
    value = raw_node.get("clientId")
    if value is None:
        return None
    return str(value)
