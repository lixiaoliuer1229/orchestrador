import json

import pytest

from app.graphs import data as data_graph
from app.tools import sql as sql_tool


@pytest.mark.parametrize(
    ("query", "statement_type"),
    [
        ("SELECT id, name FROM instruments", "SELECT"),
        ("SHOW TABLES", "SHOW"),
        ("SHOW COLUMNS FROM instruments", "SHOW"),
        ("DESCRIBE instruments", "DESCRIBE"),
        ("DESC instruments", "DESCRIBE"),
        ("EXPLAIN SELECT * FROM instruments", "EXPLAIN"),
        ("SELECT 'delete is text' AS note", "SELECT"),
    ],
)
def test_readonly_sql_is_accepted(query: str, statement_type: str) -> None:
    normalized, actual_type = sql_tool.validate_sql(query)

    assert normalized == query
    assert actual_type == statement_type


@pytest.mark.parametrize(
    "query",
    [
        "INSERT INTO instruments VALUES (1)",
        "UPDATE instruments SET name = 'x'",
        "DELETE FROM instruments",
        "DROP TABLE instruments",
        "SELECT * FROM instruments FOR UPDATE",
        "SELECT SLEEP(10)",
        "SELECT LOAD_FILE('/etc/passwd')",
        "SELECT * FROM instruments INTO OUTFILE '/tmp/export'",
        "SELECT 1; DELETE FROM instruments",
        "SELECT 1 -- bypass",
        "WITH rows AS (SELECT 1) SELECT * FROM rows",
        "SHOW PROCESSLIST",
        "SHOW VARIABLES",
        "SHOW CREATE TABLE instruments",
        "EXPLAIN ANALYZE SELECT * FROM instruments",
        "SELECT @row := @row + 1 FROM instruments",
        "SELECT id INTO @selected_id FROM instruments",
        "SELECT GET_LOCK('agent-lock', 10)",
        "SELECT LAST_INSERT_ID(42)",
    ],
)
def test_unsafe_sql_is_rejected(query: str) -> None:
    with pytest.raises(sql_tool.UnsafeSQL):
        sql_tool.validate_sql(query)


def test_trailing_semicolon_is_normalized() -> None:
    normalized, statement_type = sql_tool.validate_sql("SELECT 1;")

    assert normalized == "SELECT 1"
    assert statement_type == "SELECT"


def test_semicolon_inside_literal_is_not_treated_as_second_statement() -> None:
    normalized, statement_type = sql_tool.validate_sql(
        "SELECT ';' AS punctuation"
    )

    assert normalized == "SELECT ';' AS punctuation"
    assert statement_type == "SELECT"


def test_agent_exposes_only_readonly_sql_tool() -> None:
    assert [registered.name for registered in data_graph.TOOLS] == ["sql_inter"]


def test_sql_tool_rejects_unsafe_query_without_connecting(monkeypatch) -> None:
    def unexpected_connection():
        raise AssertionError("unsafe SQL must be rejected before connecting")

    monkeypatch.setattr(sql_tool, "connect", unexpected_connection)

    result = json.loads(sql_tool.sql_inter.invoke({"sql_query": "DROP TABLE x"}))

    assert result["error"] == "unsafe_sql"


def test_query_results_are_bounded_and_connection_is_closed(monkeypatch) -> None:
    class FakeCursor:
        description = (("id",), ("name",))

        def __init__(self):
            self.calls = []

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, query, params=None):
            self.calls.append((query, params))

        def fetchmany(self, size):
            assert size == 3
            return [(1, "one"), (2, "two"), (3, "three")]

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FakeCursor()
            self.closed = False

        def cursor(self):
            return self.cursor_instance

        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(sql_tool, "connect", lambda: connection)
    monkeypatch.setenv("DATA_AGENT_MAX_ROWS", "2")
    monkeypatch.setenv("DATA_AGENT_QUERY_TIMEOUT_MS", "2500")

    result = sql_tool.execute("SELECT id, name FROM instruments")

    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [(1, "one"), (2, "two")]
    assert result["row_count"] == 2
    assert result["truncated"] is True
    assert connection.closed is True
    assert connection.cursor_instance.calls == [
        ("SET SESSION MAX_EXECUTION_TIME = %s", (2500,)),
        ("SELECT id, name FROM instruments", None),
    ]


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATA_AGENT_MAX_ROWS", "0"),
        ("DATA_AGENT_MAX_ROWS", "5001"),
        ("DATA_AGENT_QUERY_TIMEOUT_MS", "60001"),
        ("MYSQL_PORT", "not-a-number"),
    ],
)
def test_invalid_safety_configuration_is_rejected(monkeypatch, name, value) -> None:
    monkeypatch.setenv(name, value)

    if name == "MYSQL_PORT":
        monkeypatch.setenv("MYSQL_HOST", "localhost")
        monkeypatch.setenv("MYSQL_USER", "readonly")
        monkeypatch.setenv("MYSQL_PASSWORD", "secret")
        monkeypatch.setenv("MYSQL_DATABASE", "analytics")
        with pytest.raises(RuntimeError):
            sql_tool.connection_kwargs()
    else:
        maximum = (
            sql_tool.MAX_ALLOWED_ROWS
            if name == "DATA_AGENT_MAX_ROWS"
            else sql_tool.MAX_QUERY_TIMEOUT_MS
        )
        with pytest.raises(RuntimeError):
            sql_tool.bounded_env_int(name, 1, maximum)
