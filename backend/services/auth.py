from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from typing import Any

from ..db import connect


SESSION_COOKIE_NAME = "document_knowledge_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7
DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "admin123"
DEFAULT_DISPLAY_NAME = "本地管理员"


class AuthError(ValueError):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def ensure_default_user(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_USERNAME,)).fetchone()
    if row is not None:
        return
    now = utc_now_iso()
    conn.execute(
        """
        INSERT INTO users(username, password_hash, display_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (DEFAULT_USERNAME, hash_password(DEFAULT_PASSWORD), DEFAULT_DISPLAY_NAME, now, now),
    )


def login(username: str, password: str) -> tuple[dict[str, Any], str]:
    clean_username = username.strip()
    if not clean_username or not password:
        raise AuthError(HTTPStatus.BAD_REQUEST, "missing_credentials", "Username and password are required.")

    with connect() as conn:
        ensure_default_user(conn)
        user = conn.execute("SELECT * FROM users WHERE username = ?", (clean_username,)).fetchone()
        if user is None or not verify_password(password, user["password_hash"]):
            raise AuthError(HTTPStatus.UNAUTHORIZED, "invalid_credentials", "Invalid username or password.")

        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=SESSION_MAX_AGE)).isoformat()
        conn.execute("INSERT INTO sessions(user_id, token, expires_at) VALUES (?, ?, ?)", (user["id"], token, expires_at))
        conn.commit()
        return serialize_user(user), build_session_cookie(token)


def logout(token: str | None) -> str:
    if token:
        with connect() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
    return clear_session_cookie()


def get_user_for_token(token: str | None) -> dict[str, Any]:
    if not token:
        raise AuthError(HTTPStatus.UNAUTHORIZED, "unauthorized", "Not logged in.")

    with connect() as conn:
        ensure_default_user(conn)
        row = conn.execute(
            """
            SELECT users.*
            FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token = ? AND sessions.expires_at > ?
            """,
            (token, utc_now_iso()),
        ).fetchone()
        if row is None:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            raise AuthError(HTTPStatus.UNAUTHORIZED, "unauthorized", "Session expired or invalid.")
        return serialize_user(row)


def get_optional_user_for_token(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    try:
        return get_user_for_token(token)
    except AuthError:
        return None


def session_token_from_cookie(header_value: str | None) -> str | None:
    if not header_value:
        return None
    cookie = SimpleCookie()
    cookie.load(header_value)
    morsel = cookie.get(SESSION_COOKIE_NAME)
    return morsel.value if morsel is not None else None


def build_session_cookie(token: str) -> str:
    return f"{SESSION_COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={SESSION_MAX_AGE}"


def clear_session_cookie() -> str:
    return f"{SESSION_COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
    return hmac.compare_digest(digest, expected)


def serialize_user(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "username": str(row["username"]),
        "displayName": str(row["display_name"] or row["username"]),
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
