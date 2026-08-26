"""Bounded, read-only MySQL access for production agents."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import date, datetime, time as datetime_time, timedelta
from decimal import Decimal
from typing import Any

import pymysql
from langchain_core.tools import tool
from pydantic import BaseModel, Field


logger = logging.getLogger(__name__)

DEFAULT_MAX_ROWS = 500
MAX_ALLOWED_ROWS = 5_000
DEFAULT_QUERY_TIMEOUT_MS = 10_000
MAX_QUERY_TIMEOUT_MS = 60_000

_ALLOWED_START = re.compile(r"^\s*(SELECT|SHOW|DESCRIBE|DESC|EXPLAIN)\b", re.I)
_ALLOWED_SHOW = re.compile(
    r"^\s*SHOW\s+(TABLES|COLUMNS|FIELDS|INDEX|INDEXES|KEYS)\b",
    re.I,
)
_FORBIDDEN_TOKENS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|REPLACE|UPSERT|MERGE|CREATE|ALTER|DROP|TRUNCATE|"
    r"RENAME|GRANT|REVOKE|CALL|DO|HANDLER|LOAD|LOCK|UNLOCK|SET|USE|KILL|"
    r"SHUTDOWN|INTO|FOR\s+UPDATE|EXPLAIN\s+ANALYZE|"
    r"LOCK\s+IN\s+SHARE\s+MODE|SLEEP|BENCHMARK|LOAD_FILE|GET_LOCK|"
    r"RELEASE_LOCK|IS_FREE_LOCK|LAST_INSERT_ID|PROCEDURE)\b",
    re.I,
)


class UnsafeSQL(ValueError):
    """Raised when SQL exceeds the read-only policy."""


class SQLQuery(BaseModel):
    sql_query: str = Field(
        min_length=1,
        max_length=20_000,
        description=(
            "一条只读 MySQL 语句。仅允许 SELECT、SHOW、DESCRIBE/DESC 或 EXPLAIN；"
            "不允许注释、多语句、写操作、锁或文件操作。"
        ),
    )


def bounded_env_int(name: str, default: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0 or value > maximum:
        raise RuntimeError(f"{name} must be between 1 and {maximum}")
    return value


def _redact_literals(sql: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    for char in sql:
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            result.append(" ")
        elif char in {"'", '"', "`"}:
            quote = char
            result.append(" ")
        else:
            result.append(char)
    if quote:
        raise UnsafeSQL("SQL contains an unterminated quoted value")
    return "".join(result)


def validate_sql(sql_query: str) -> tuple[str, str]:
    """Validate and normalize one read-only SQL statement."""

    query = sql_query.strip()
    if not query:
        raise UnsafeSQL("SQL query is empty")
    if "--" in query or "#" in query or "/*" in query or "*/" in query:
        raise UnsafeSQL("SQL comments are not allowed")

    redacted = _redact_literals(query)
    if redacted.rstrip().endswith(";"):
        query = query[:-1].rstrip()
        redacted = redacted[:-1].rstrip()
    if ";" in redacted:
        raise UnsafeSQL("Only one SQL statement is allowed")
    if ":=" in redacted:
        raise UnsafeSQL("SQL variable assignment is not allowed")

    match = _ALLOWED_START.match(redacted)
    if not match:
        raise UnsafeSQL(
            "Only SELECT, SHOW, DESCRIBE/DESC and EXPLAIN statements are allowed"
        )
    if _FORBIDDEN_TOKENS.search(redacted):
        raise UnsafeSQL("The SQL statement contains a forbidden operation")

    statement_type = match.group(1).upper()
    if statement_type == "SHOW" and not _ALLOWED_SHOW.match(redacted):
        raise UnsafeSQL("Only schema-inspection SHOW statements are allowed")
    if statement_type == "DESC":
        statement_type = "DESCRIBE"
    return query, statement_type


def connection_kwargs() -> dict[str, Any]:
    values = {
        "MYSQL_HOST": os.getenv("MYSQL_HOST"),
        "MYSQL_USER": os.getenv("MYSQL_USER"),
        "MYSQL_PASSWORD": os.getenv("MYSQL_PASSWORD"),
        "MYSQL_DATABASE": os.getenv("MYSQL_DATABASE"),
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(f"Missing MySQL configuration: {', '.join(missing)}")

    port = bounded_env_int("MYSQL_PORT", 3306, 65_535)
    timeout_ms = bounded_env_int(
        "DATA_AGENT_QUERY_TIMEOUT_MS",
        DEFAULT_QUERY_TIMEOUT_MS,
        MAX_QUERY_TIMEOUT_MS,
    )
    timeout_seconds = max(1, (timeout_ms + 999) // 1000)
    host = values["MYSQL_HOST"]
    is_local = host in {"127.0.0.1", "localhost", "::1"}
    ssl_disabled = os.getenv(
        "MYSQL_SSL_DISABLED", "true" if is_local else "false"
    ).lower() in {"1", "true", "yes", "on"}

    return {
        "host": host,
        "user": values["MYSQL_USER"],
        "password": values["MYSQL_PASSWORD"],
        "database": values["MYSQL_DATABASE"],
        "port": port,
        "charset": "utf8mb4",
        "ssl_disabled": ssl_disabled,
        "connect_timeout": timeout_seconds,
        "read_timeout": timeout_seconds,
        "write_timeout": timeout_seconds,
        "autocommit": True,
    }


def connect():
    """Connect with bounded timeouts; deployments must use a read-only user."""

    return pymysql.connect(**connection_kwargs())


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, datetime_time)):
        return value.isoformat()
    if isinstance(value, timedelta):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


def execute(sql_query: str) -> dict[str, Any]:
    query, statement_type = validate_sql(sql_query)
    max_rows = bounded_env_int(
        "DATA_AGENT_MAX_ROWS", DEFAULT_MAX_ROWS, MAX_ALLOWED_ROWS
    )
    timeout_ms = bounded_env_int(
        "DATA_AGENT_QUERY_TIMEOUT_MS",
        DEFAULT_QUERY_TIMEOUT_MS,
        MAX_QUERY_TIMEOUT_MS,
    )
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    started = time.monotonic()
    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION MAX_EXECUTION_TIME = %s", (timeout_ms,))
            cursor.execute(query)
            rows = list(cursor.fetchmany(max_rows + 1))
            columns = [item[0] for item in cursor.description or ()]
    except Exception:
        logger.exception(
            "data_agent_query_failed",
            extra={"query_hash": query_hash, "statement_type": statement_type},
        )
        raise
    finally:
        connection.close()

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    duration_ms = round((time.monotonic() - started) * 1000, 2)
    logger.info(
        "data_agent_query_completed",
        extra={
            "query_hash": query_hash,
            "statement_type": statement_type,
            "row_count": len(rows),
            "truncated": truncated,
            "duration_ms": duration_ms,
        },
    )
    return {
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "max_rows": max_rows,
        "query_hash": query_hash,
        "duration_ms": duration_ms,
    }


@tool(args_schema=SQLQuery)
def sql_inter(sql_query: str) -> str:
    """Run one bounded read-only query and return structured JSON."""

    try:
        result = execute(sql_query)
    except UnsafeSQL as exc:
        return json.dumps(
            {"error": "unsafe_sql", "message": str(exc)}, ensure_ascii=False
        )
    except Exception:
        return json.dumps(
            {
                "error": "query_failed",
                "message": "只读查询执行失败，请检查语句、权限或数据库连接。",
            },
            ensure_ascii=False,
        )
    return json.dumps(result, ensure_ascii=False, default=_json_default)
