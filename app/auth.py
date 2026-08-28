"""PostgreSQL-backed users and opaque browser sessions."""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from pwdlib import PasswordHash

from app.db import connect


password_hash = PasswordHash.recommended()
SESSION_COOKIE = "orchestrador_session"


def auth_enabled() -> bool:
    return os.getenv("AUTH_ENABLED", "true").lower() in {"1", "true", "yes"}


def cookie_secure() -> bool:
    return os.getenv("AUTH_COOKIE_SECURE", "true").lower() in {"1", "true", "yes"}


def _connect():
    return connect()


def init_auth_database() -> None:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_users (
                id BIGSERIAL PRIMARY KEY,
                username VARCHAR(64) UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role VARCHAR(16) NOT NULL DEFAULT 'user'
                    CHECK (role IN ('admin', 'user')),
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_login_at TIMESTAMPTZ
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_sessions (
                token_hash CHAR(64) PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS app_sessions_expires_idx ON app_sessions(expires_at)"
        )
        cursor.execute("DELETE FROM app_sessions WHERE expires_at <= NOW()")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(username: str, password: str) -> dict[str, Any] | None:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "SELECT id, username, password_hash, role, is_active FROM app_users WHERE username = %s",
            (username,),
        )
        user = cursor.fetchone()
        if not user or not user["is_active"]:
            return None
        if not password_hash.verify(password, user["password_hash"]):
            return None
        cursor.execute(
            "UPDATE app_users SET last_login_at = NOW() WHERE id = %s", (user["id"],)
        )
        return {key: user[key] for key in ("id", "username", "role")}


def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=int(os.getenv("AUTH_SESSION_HOURS", "12"))
    )
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO app_sessions(token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (_token_hash(token), user_id, expires_at),
        )
    return token


def session_user(token: str | None) -> dict[str, Any] | None:
    if not token:
        return None
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute("""
            SELECT u.id, u.username, u.role
            FROM app_sessions s
            JOIN app_users u ON u.id = s.user_id
            WHERE s.token_hash = %s AND s.expires_at > NOW() AND u.is_active = TRUE
        """, (_token_hash(token),))
        return cursor.fetchone()


def delete_session(token: str | None) -> None:
    if not token:
        return
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute("DELETE FROM app_sessions WHERE token_hash = %s", (_token_hash(token),))


def list_users() -> list[dict[str, Any]]:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, username, role, is_active, created_at, last_login_at
            FROM app_users ORDER BY id
        """)
        return cursor.fetchall()


def create_user(username: str, password: str, role: str = "user") -> dict[str, Any]:
    if role not in {"admin", "user"}:
        raise ValueError("Invalid role")
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute("""
            INSERT INTO app_users(username, password_hash, role)
            VALUES (%s, %s, %s)
            RETURNING id, username, role, is_active, created_at
        """, (username, password_hash.hash(password), role))
        return cursor.fetchone()


def set_user_active(user_id: int, active: bool) -> None:
    with _connect() as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE app_users SET is_active = %s WHERE id = %s", (active, user_id)
        )
        if not active:
            cursor.execute("DELETE FROM app_sessions WHERE user_id = %s", (user_id,))
