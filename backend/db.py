from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .config import DATA_DIR, DB_PATH


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS projects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  owner_user_id INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(owner_user_id) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  token TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS nodes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL,
  parent_id INTEGER,
  title TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  source_type TEXT NOT NULL DEFAULT '',
  metadata TEXT NOT NULL DEFAULT '{}',
  source_project_id INTEGER,
  source_node_id INTEGER,
  position INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
  FOREIGN KEY(parent_id) REFERENCES nodes(id) ON DELETE CASCADE,
  FOREIGN KEY(source_project_id) REFERENCES projects(id) ON DELETE SET NULL,
  FOREIGN KEY(source_node_id) REFERENCES nodes(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_nodes_project_parent
ON nodes(project_id, parent_id, position);
CREATE INDEX IF NOT EXISTS idx_sessions_user
ON sessions(user_id, expires_at);
"""


def init_db(db_path: Path | None = None) -> None:
    db_path = db_path or DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        from .services import auth

        conn.executescript(SCHEMA)
        ensure_column(conn, "projects", "owner_user_id", "INTEGER REFERENCES users(id) ON DELETE SET NULL")
        ensure_column(conn, "nodes", "source_type", "TEXT NOT NULL DEFAULT ''")
        ensure_column(conn, "nodes", "metadata", "TEXT NOT NULL DEFAULT '{}'")
        ensure_column(conn, "nodes", "source_project_id", "INTEGER REFERENCES projects(id) ON DELETE SET NULL")
        ensure_column(conn, "nodes", "source_node_id", "INTEGER REFERENCES nodes(id) ON DELETE SET NULL")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_source_project ON nodes(source_project_id)")
        conn.execute("UPDATE nodes SET source_project_id = project_id WHERE source_project_id IS NULL")
        auth.ensure_default_user(conn)
        conn.commit()


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    db_path = db_path or DB_PATH
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
