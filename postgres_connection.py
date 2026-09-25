"""Small PostgreSQL adapter for the workbench's existing query interface."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import pandas as pd
import psycopg
from psycopg.rows import dict_row

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().with_name(".env"))
except ModuleNotFoundError:
    pass


_POSITIONAL_PARAMETER = re.compile(r":([1-9][0-9]*)")
_REPLACE_TABLE_NAME = re.compile(r"CREATE\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?)", re.IGNORECASE)
_PARSE_JSON_DOLLAR = re.compile(r"PARSE_JSON\(\$\$(.*?)\$\$\)", re.DOTALL | re.IGNORECASE)
_PARSE_JSON_STRING = re.compile(r"PARSE_JSON\(('(?:''|[^'])*')\)", re.IGNORECASE)


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
    return sql


def _parameters(sql: str, params: list[Any] | tuple[Any, ...] | None) -> tuple[str, list[Any]]:
    if not params:
        return sql, []

    values = list(params)

    def replace(match: re.Match[str]) -> str:
        index = int(match.group(1)) - 1
        if index >= len(values):
            raise ValueError(f"SQL parameter :{index + 1} has no matching value")
        expanded.append(values[index])
        return "%s"

    expanded: list[Any] = []
    return _POSITIONAL_PARAMETER.sub(replace, sql), expanded


class PostgresResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def collect(self) -> list[dict[str, Any]]:
        return self._rows

    def to_pandas(self) -> pd.DataFrame:
        return pd.DataFrame(self._rows)


class PostgresSession:
    def __init__(self, connection: psycopg.Connection[Any]):
        self._connection = connection

    def sql(self, sql: str, params: list[Any] | tuple[Any, ...] | None = None) -> PostgresResult:
        translated = _translate_sql(sql)
        translated, query_params = _parameters(translated, params)
        try:
            # CREATE OR REPLACE TABLE is translated to CREATE TABLE for local
            # PostgreSQL. Drop the old table first so retries are safe.
            table_match = _REPLACE_TABLE_NAME.match(translated)
            with self._connection.cursor(row_factory=dict_row) as cursor:
                if table_match:
                    cursor.execute(f"DROP TABLE IF EXISTS {table_match.group(1)}")
                cursor.execute(translated, query_params)
                rows = cursor.fetchall() if cursor.description else []
            self._connection.commit()
            return PostgresResult(rows)
        except Exception:
            # psycopg leaves the connection in an aborted transaction after
            # any failed statement unless it is explicitly rolled back.
            self._connection.rollback()
            raise


class PostgresConnection:
    def __init__(self, url: str | None = None):
        self.url = url or os.getenv("DATABASE_URL", "")
        if not self.url:
            raise RuntimeError("DATABASE_URL is required for the PostgreSQL connection")
        self._connection = psycopg.connect(self.url)
        self._configure_application_schema()

    def _configure_application_schema(self) -> None:
        """Ensure runtime tables are created in the configured application schema."""
        schema = os.getenv("APP_SCHEMA", "lai_app")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", schema):
            raise ValueError("APP_SCHEMA must be a valid PostgreSQL schema identifier")
        with self._connection.cursor() as cursor:
            cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            cursor.execute(f'SET search_path TO "{schema}", public')
        self._connection.commit()

    def session(self) -> PostgresSession:
        return PostgresSession(self._connection)

    def query(self, sql: str) -> pd.DataFrame:
        return self.session().sql(sql).to_pandas()
