"""SQLite-style compatibility layer for PostgreSQL mode."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import text

from db_config import is_sqlite
from db_pg import get_pg_engine


_QUESTION_PARAM_RE = re.compile(r"\?")
_PRAGMA_TABLE_INFO_RE = re.compile(
    r"^\s*PRAGMA\s+table_info\s*\(\s*(?P<table>[^)]+?)\s*\)\s*;?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_SQLITE_MASTER_RE = re.compile(r"\bsqlite_master\b", re.IGNORECASE)


def _strip_identifier_quotes(value: Any) -> str:
    text_v = str(value or "").strip()
    if (text_v.startswith('"') and text_v.endswith('"')) or (text_v.startswith("'") and text_v.endswith("'")):
        return text_v[1:-1]
    return text_v


def _convert_question_placeholders(sql: str) -> tuple[str, list[str]]:
    names: list[str] = []
    out: list[str] = []
    in_single = False
    in_double = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""
        if in_line_comment:
            out.append(ch)
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            out.append(ch)
            if ch == "*" and nxt == "/":
                out.append(nxt)
                i += 2
                in_block_comment = False
            else:
                i += 1
            continue
        if not in_single and not in_double and ch == "-" and nxt == "-":
            out.extend([ch, nxt])
            i += 2
            in_line_comment = True
            continue
        if not in_single and not in_double and ch == "/" and nxt == "*":
            out.extend([ch, nxt])
            i += 2
            in_block_comment = True
            continue
        if ch == "'" and not in_double:
            out.append(ch)
            if in_single and nxt == "'":
                out.append(nxt)
                i += 2
                continue
            in_single = not in_single
            i += 1
            continue
        if ch == '"' and not in_single:
            out.append(ch)
            in_double = not in_double
            i += 1
            continue
        if ch == "?" and not in_single and not in_double:
            name = f"p{len(names)}"
            names.append(name)
            out.append(f":{name}")
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out), names


def _bind_params(params: Any, names: list[str]) -> Any:
    if params is None:
        return {}
    if isinstance(params, Mapping):
        return dict(params)
    if not names:
        return params
    values = list(params if isinstance(params, (list, tuple)) else [params])
    return {name: values[idx] if idx < len(values) else None for idx, name in enumerate(names)}


def _bind_many(seq_of_params: Iterable[Any], names: list[str]) -> list[Any]:
    bound_rows: list[Any] = []
    for row in seq_of_params:
        bound_rows.append(_bind_params(row, names))
    return bound_rows


def _convert_sqlite_functions(sql: str) -> str:
    converted = re.sub(r"\bIFNULL\s*\(", "COALESCE(", sql, flags=re.IGNORECASE)
    converted = re.sub(
        r"strftime\s*\(\s*'%Y-%m-%d %H:%M:%S'\s*,\s*'now'\s*\)",
        "TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS')",
        converted,
        flags=re.IGNORECASE,
    )
    converted = re.sub(
        r"datetime\s*\(\s*'now'\s*\)",
        "CURRENT_TIMESTAMP",
        converted,
        flags=re.IGNORECASE,
    )
    return converted


def _convert_insert_or_replace(sql: str) -> str:
    if not re.search(r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+spot_summary_hidden\b", sql, re.IGNORECASE):
        return sql
    return re.sub(
        r"^\s*INSERT\s+OR\s+REPLACE\s+INTO\s+spot_summary_hidden\s*"
        r"\(\s*group_id\s*,\s*spot_name\s*,\s*hidden_at\s*,\s*hidden_by\s*,\s*note\s*\)\s*"
        r"VALUES\s*\((?P<values>.*?)\)\s*;?\s*$",
        (
            "INSERT INTO spot_summary_hidden(group_id, spot_name, hidden_at, hidden_by, note) "
            "VALUES(\\g<values>) "
            "ON CONFLICT(group_id, spot_name) DO UPDATE SET "
            "hidden_at=excluded.hidden_at, "
            "hidden_by=excluded.hidden_by, "
            "note=excluded.note"
        ),
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _prepare_sql_and_params(sql: str, params: Any = None) -> tuple[str, Any]:
    converted = _convert_insert_or_replace(_convert_sqlite_functions(str(sql)))
    converted, names = _convert_question_placeholders(converted)
    return converted, _bind_params(params, names)


class PostgresCompatResult:
    def __init__(
        self,
        rows: Sequence[Sequence[Any]] | None = None,
        columns: Sequence[str] | None = None,
        rowcount: int = -1,
    ) -> None:
        self._rows = [tuple(row) for row in (rows or [])]
        self._columns = [str(col) for col in (columns or [])]
        self.rowcount = int(rowcount if rowcount is not None else -1)
        self.description = [(col, None, None, None, None, None, None) for col in self._columns]
        self._idx = 0

    def fetchone(self) -> tuple[Any, ...] | None:
        if self._idx >= len(self._rows):
            return None
        row = self._rows[self._idx]
        self._idx += 1
        return row

    def fetchall(self) -> list[tuple[Any, ...]]:
        if self._idx <= 0:
            self._idx = len(self._rows)
            return list(self._rows)
        rows = self._rows[self._idx :]
        self._idx = len(self._rows)
        return list(rows)

    def fetchmany(self, size: int | None = None) -> list[tuple[Any, ...]]:
        n = int(size or 1)
        rows = self._rows[self._idx : self._idx + n]
        self._idx += len(rows)
        return list(rows)


class PostgresCompatCursor:
    def __init__(self, conn: "PostgresCompatConnection") -> None:
        self._conn = conn
        self._result = PostgresCompatResult()
        self.description = self._result.description
        self.rowcount = self._result.rowcount

    def execute(self, sql: str, params: Any = None) -> "PostgresCompatCursor":
        self._result = self._conn.execute(sql, params)
        self.description = self._result.description
        self.rowcount = self._result.rowcount
        return self

    def executemany(self, sql: str, seq_of_params: Iterable[Any]) -> "PostgresCompatCursor":
        self._result = self._conn.executemany(sql, seq_of_params)
        self.description = self._result.description
        self.rowcount = self._result.rowcount
        return self

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._result.fetchone()

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self._result.fetchall()

    def fetchmany(self, size: int | None = None) -> list[tuple[Any, ...]]:
        return self._result.fetchmany(size)

    def close(self) -> None:
        return None


class PostgresCompatConnection:
    backend = "postgres"

    def __init__(self, engine: Any | None = None) -> None:
        self.engine = engine or get_pg_engine()
        self._conn = self.engine.connect()
        self._closed = False
        self._explicit_transaction = False
        self._total_changes = 0

    @property
    def in_transaction(self) -> bool:
        return bool(self._explicit_transaction)

    @property
    def total_changes(self) -> int:
        return int(self._total_changes)

    def cursor(self) -> PostgresCompatCursor:
        return PostgresCompatCursor(self)

    def execute(self, sql: str, params: Any = None) -> PostgresCompatResult:
        sql_text = str(sql or "").strip()
        if not sql_text:
            return PostgresCompatResult()
        special = self._execute_special(sql_text)
        if special is not None:
            return special
        prepared_sql, bound_params = _prepare_sql_and_params(sql_text, params)
        result = self._conn.execute(text(prepared_sql), bound_params)
        return self._wrap_sqlalchemy_result(result)

    def executemany(self, sql: str, seq_of_params: Iterable[Any]) -> PostgresCompatResult:
        sql_text = str(sql or "").strip()
        if not sql_text:
            return PostgresCompatResult()
        prepared_sql = _convert_insert_or_replace(_convert_sqlite_functions(sql_text))
        prepared_sql, names = _convert_question_placeholders(prepared_sql)
        rows = _bind_many(seq_of_params, names)
        if not rows:
            return PostgresCompatResult(rowcount=0)
        result = self._conn.execute(text(prepared_sql), rows)
        return self._wrap_sqlalchemy_result(result)

    def executescript(self, sql_script: str) -> PostgresCompatResult:
        raise RuntimeError("PostgreSQL mode does not execute SQLite executescript blocks.")

    def commit(self) -> None:
        self._conn.commit()
        self._explicit_transaction = False

    def rollback(self) -> None:
        self._conn.rollback()
        self._explicit_transaction = False

    def close(self) -> None:
        if self._closed:
            return
        self._conn.close()
        self._closed = True

    def _execute_special(self, sql_text: str) -> PostgresCompatResult | None:
        upper = sql_text.upper().rstrip(";")
        if upper in {"BEGIN", "BEGIN IMMEDIATE", "BEGIN TRANSACTION", "BEGIN IMMEDIATE TRANSACTION"}:
            if not self._conn.in_transaction():
                self._conn.begin()
            self._explicit_transaction = True
            return PostgresCompatResult(rowcount=-1)
        if upper in {"COMMIT", "END"}:
            self.commit()
            return PostgresCompatResult(rowcount=-1)
        if upper == "ROLLBACK":
            self.rollback()
            return PostgresCompatResult(rowcount=-1)
        if upper.startswith("PRAGMA DATABASE_LIST"):
            return PostgresCompatResult([(0, "main", "")], ["seq", "name", "file"], rowcount=1)
        table_match = _PRAGMA_TABLE_INFO_RE.match(sql_text)
        if table_match:
            return self._pragma_table_info(_strip_identifier_quotes(table_match.group("table")))
        if upper.startswith("PRAGMA "):
            return PostgresCompatResult(rowcount=-1)
        if _SQLITE_MASTER_RE.search(sql_text):
            result = self._conn.execute(
                text(
                    """
                    SELECT table_name AS name
                    FROM information_schema.tables
                    WHERE table_schema = current_schema()
                      AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """
                )
            )
            return self._wrap_sqlalchemy_result(result)
        return None

    def _pragma_table_info(self, table_name: str) -> PostgresCompatResult:
        sql = text(
            """
            WITH pk_cols AS (
                SELECT
                    kcu.column_name,
                    kcu.ordinal_position AS pk_ordinal
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                 AND tc.table_name = kcu.table_name
                WHERE tc.table_schema = current_schema()
                  AND tc.table_name = :table_name
                  AND tc.constraint_type = 'PRIMARY KEY'
            )
            SELECT
                c.ordinal_position - 1 AS cid,
                c.column_name AS name,
                UPPER(c.data_type) AS type,
                CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull,
                c.column_default AS dflt_value,
                COALESCE(pk_cols.pk_ordinal, 0) AS pk
            FROM information_schema.columns c
            LEFT JOIN pk_cols ON pk_cols.column_name = c.column_name
            WHERE c.table_schema = current_schema()
              AND c.table_name = :table_name
            ORDER BY c.ordinal_position
            """
        )
        result = self._conn.execute(sql, {"table_name": table_name})
        return self._wrap_sqlalchemy_result(result)

    def _wrap_sqlalchemy_result(self, result: Any) -> PostgresCompatResult:
        rowcount = int(getattr(result, "rowcount", -1) if getattr(result, "rowcount", -1) is not None else -1)
        if rowcount and rowcount > 0:
            self._total_changes += rowcount
        if not getattr(result, "returns_rows", False):
            return PostgresCompatResult(rowcount=rowcount)
        columns = [str(col) for col in result.keys()]
        rows = [tuple(row) for row in result.fetchall()]
        return PostgresCompatResult(rows, columns, rowcount=(len(rows) if rowcount < 0 else rowcount))


def get_compat_conn(sqlite_factory: Any | None = None) -> Any:
    if is_sqlite():
        if sqlite_factory is None:
            raise RuntimeError("sqlite_factory is required when APP_DB_BACKEND=sqlite.")
        return sqlite_factory()
    return PostgresCompatConnection()


def is_postgres_compat_connection(conn: Any) -> bool:
    return isinstance(conn, PostgresCompatConnection)
