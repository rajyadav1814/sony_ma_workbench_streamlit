"""Small PostgreSQL adapter for the workbench's existing query interface."""

from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().with_name(".env"))
except ModuleNotFoundError:
    pass


# Not preceded by ":" or a word character, so a "::1" cast or a "12:30" literal is not taken for a parameter.
_POSITIONAL_PARAMETER = re.compile(r"(?<![:\w]):([1-9][0-9]*)")
# "CREATE TABLE IF NOT EXISTS x" must not be read as a CREATE OR REPLACE (which drops the table first).
_REPLACE_TABLE_NAME = re.compile(r"CREATE\s+TABLE\s+(?!IF\s+NOT\s+EXISTS\b)([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)", re.IGNORECASE)
_PARSE_JSON_DOLLAR = re.compile(r"PARSE_JSON\(\$\$(.*?)\$\$\)", re.DOTALL | re.IGNORECASE)
_PARSE_JSON_STRING = re.compile(r"PARSE_JSON\(('(?:''|[^'])*')\)", re.IGNORECASE)
_PARSE_JSON_PARAM = re.compile(r"PARSE_JSON\((:[1-9][0-9]*)\)", re.IGNORECASE)


def _translate_sql(sql: str) -> str:
    """Translate legacy warehouse SQL into PostgreSQL-compatible SQL."""
    luminate_database = os.getenv("LUMINATE_DATABASE", "catalogue_valuation")
    luminate_schema = os.getenv("LUMINATE_SCHEMA", "extract_s")
    analytics_database = os.getenv("ANALYTICS_DATABASE", "catalogue_valuation")
    analytics_schema = os.getenv("ANALYTICS_SCHEMA", "lai_app")
    sql = sql.replace(
        f"{luminate_database}.{luminate_schema}.",
        f"{luminate_schema}.",
    )
    sql = sql.replace(
        f"{analytics_database}.{analytics_schema}.",
        f"{analytics_schema}.",
    )
    sql = re.sub(r"\bTIMESTAMP_NTZ\b", "TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bNUMBER\b", "NUMERIC", sql, flags=re.IGNORECASE)
    sql = re.sub(r"CURRENT_TIMESTAMP\(\)", "CURRENT_TIMESTAMP", sql, flags=re.IGNORECASE)
    sql = re.sub(r"UUID_STRING\(\)", "gen_random_uuid()::text", sql, flags=re.IGNORECASE)
    sql = re.sub(r"TO_VARCHAR\(([^)]+)\)", r"CAST(\1 AS TEXT)", sql, flags=re.IGNORECASE)
    sql = re.sub(r"\bVARIANT\b", "JSONB", sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"CREATE\s+OR\s+REPLACE\s+TABLE",
        "CREATE TABLE",
        sql,
        flags=re.IGNORECASE,
    )

    def dollar_json(match: re.Match[str]) -> str:
        value = match.group(1).replace("'", "''")
        return f"'{value}'::jsonb"

    sql = _PARSE_JSON_DOLLAR.sub(dollar_json, sql)
    sql = _PARSE_JSON_STRING.sub(r"\1::jsonb", sql)
    sql = _PARSE_JSON_PARAM.sub(r"\1::jsonb", sql)
    return sql


def _parameters(sql: str, params: list[Any] | tuple[Any, ...] | None) -> tuple[str, list[Any] | None]:
    """Turn ``:1``-style markers into psycopg ``%s`` placeholders.

    psycopg treats ``%`` in the SQL text as a placeholder whenever a parameter list is passed (even an
    empty one), so a literal ``%`` (e.g. ``LIKE '%x%'``) is doubled, or the list is dropped when there
    are no parameters at all.
    """
    if not params:
        return sql, None

    values = list(params)

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        if index >= len(values):
            raise ValueError(f"SQL parameter :{index + 1} has no matching value")
        expanded.append(values[index])
        return "%s"

    expanded: list[Any] = []
    return _POSITIONAL_PARAMETER.sub(replace, sql.replace("%", "%%")), expanded


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?")
_IDLE_PING_SECONDS = 45     # ping a connection that has sat idle this long before trusting it
_schema_ready = False       # CREATE SCHEMA only needs to run once per process


class PostgresResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = [
            {str(key).upper(): value for key, value in row.items()}
            for row in rows
        ]

    def collect(self) -> list[dict[str, Any]]:
        return self._rows

class PostgresSession:
    def __init__(self, connection: psycopg.Connection[Any], owner: "PostgresConnection | None" = None):
        self._connection = connection
        self._owner = owner

    def sql(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> PostgresResult:
        translated = _translate_sql(sql)
        translated, query_params = _parameters(translated, params)
        # The connection is in autocommit mode, so a plain statement is one network round-trip
        # (not BEGIN + statement + COMMIT). Only the DROP + CREATE pair below needs a transaction.
        # An error leaves nothing to roll back.
        # CREATE OR REPLACE TABLE is translated to CREATE TABLE for local
        # PostgreSQL. Drop the old table first so retries are safe.
        table_match = _REPLACE_TABLE_NAME.match(translated)
        with self._connection.cursor(row_factory=dict_row) as cursor:
            if table_match:
                with self._connection.transaction():
                    cursor.execute(f"DROP TABLE IF EXISTS {table_match.group(1)}")
                    cursor.execute(translated, query_params)
            else:
                cursor.execute(translated, query_params)
            rows = cursor.fetchall() if cursor.description else []
        if self._owner:
            self._owner.touch()
        return PostgresResult(rows)

    def bulk_insert(self, table: str, columns: list[str], rows: list[tuple[Any, ...]]) -> int:
        """Load ``rows`` with COPY: one round-trip however many rows, and values are never spliced into SQL."""
        if not _IDENTIFIER.fullmatch(table) or not all(_IDENTIFIER.fullmatch(c) for c in columns):
            raise ValueError("bulk_insert needs plain table and column identifiers")
        with self._connection.cursor() as cursor:
            with cursor.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
                for row in rows:
                    copy.write_row(row)
        if self._owner:
            self._owner.touch()
        return len(rows)


class PostgresConnection:
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("DATABASE_URL", "")
        if not self.url:
            raise RuntimeError("DATABASE_URL is required for the PostgreSQL connection")
        self._schema = os.getenv("APP_SCHEMA", "lai_app")
        if not _IDENTIFIER.fullmatch(self._schema) or "." in self._schema:
            raise ValueError("APP_SCHEMA must be a valid PostgreSQL schema identifier")
        # Opening a connection is slow (TLS + auth over the network), so callers keep one per user
        # session (see get_connection) instead of opening one per Streamlit rerun.
        self._connection = psycopg.connect(
            self.url,
            autocommit=True,
            connect_timeout=15,
            keepalives=1,
            keepalives_idle=30,
            keepalives_interval=10,
            keepalives_count=3,
            options=f'-c search_path="{self._schema}",public',
        )
        self._last_used = time.monotonic()
        # Free-form per-connection state for things that live exactly as long as this connection's
        # TEMP tables (e.g. the ISRC upload table and which file it holds).
        self.state: dict[str, Any] = {}
        self._configure_application_schema()

    def _configure_application_schema(self) -> None:
        """Ensure runtime tables are created in the configured application schema."""
        global _schema_ready
        if _schema_ready:
            return
        with self._connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{self._schema}"')
        _schema_ready = True

    @property
    def last_used(self) -> float:
        return self._last_used

    def touch(self) -> None:
        self._last_used = time.monotonic()

    def is_alive(self) -> bool:
        """False once the connection is closed/broken, or an idle one fails a ping (RDS and NATs drop idle sockets)."""
        if self._connection.closed or self._connection.broken:
            return False
        if time.monotonic() - self._last_used < _IDLE_PING_SECONDS:
            return True
        try:
            self._connection.execute("SELECT 1")
            self.touch()
            return True
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._connection.close()
        except Exception:
            pass

    def session(self) -> PostgresSession:
        return PostgresSession(self._connection, self)

    def query(self, sql: str) -> list[dict[str, Any]]:
        return self.session().sql(sql).collect()


class _ConnectionRegistry:
    """Process-wide connections, one per user, kept across Streamlit sessions.

    Every step click in the workbench reloads the browser page, and a reload is a brand-new
    Streamlit session with empty ``st.session_state``. A per-session connection would therefore be
    reopened (seconds) and leaked on every click. Keeping the connection per user in the server
    process means a click reuses it, and the TEMP tables on it (the ISRC upload and the analytics
    working tables) are still there.
    """

    MAX_IDLE_SECONDS = 20 * 60
    MAX_CONNECTIONS = 40

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connections: dict[str, PostgresConnection] = {}

    def get(self, owner: str) -> "PostgresConnection":
        key = (owner or "anonymous").strip().lower()
        with self._lock:
            self._evict_locked(keep=key)
            conn = self._connections.get(key)
            if conn is not None and conn.is_alive():
                return conn
            if conn is not None:
                conn.close()
            conn = PostgresConnection()
            self._connections[key] = conn
            return conn

    def _evict_locked(self, keep: str) -> None:
        now = time.monotonic()
        for key, conn in list(self._connections.items()):
            if key != keep and now - conn.last_used > self.MAX_IDLE_SECONDS:
                conn.close()
                del self._connections[key]
        while len(self._connections) >= self.MAX_CONNECTIONS:
            oldest = min((k for k in self._connections if k != keep), key=lambda k: self._connections[k].last_used, default=None)
            if oldest is None:
                break
            self._connections.pop(oldest).close()


def get_connection(owner: str) -> PostgresConnection:
    """The user's long-lived database connection (reconnecting transparently if it has died)."""
    import streamlit as st

    @st.cache_resource
    def registry() -> _ConnectionRegistry:
        return _ConnectionRegistry()

    return registry().get(owner)
