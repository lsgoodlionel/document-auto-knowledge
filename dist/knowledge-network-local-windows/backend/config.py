from __future__ import annotations

from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_DIR / "frontend"
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "knowledge_network.sqlite3"
HOST = "127.0.0.1"
PORT = 8000
MAX_UPLOAD_SIZE = 20 * 1024 * 1024
