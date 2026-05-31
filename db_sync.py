"""Manual SQLite <-> Neon PostgreSQL synchronization helpers."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from db_pg import get_pg_engine, init_pg_db


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BATCH_SIZE = 500


def quote_ident(name: str) -> str:
    name_s = str(name or "").strip()
    if not IDENTIFIER_RE.fullmatch(name_s):
        raise ValueError(f"非法 SQL 标识符：{name_s!r}")
    return f'"{name_s}"'


def sqlite_type_to_pg(sqlite_type: Any) -> str:
    type_s = str(sqlite_type or "").strip().upper()
    if "INT" in type_s:
        return "INTEGER"
    if any(token in type_s for token in ("REAL", "FLOA", "DOUB")):
        return "DOUBLE PRECISION"
    if "BLOB" in type_s:
        return "BYTEA"
    return "TEXT"


def pg_type_to_sqlite(data_type: str, udt_name: str = "") -> str:
    data_type_s = str(data_type or "").lower()
    udt_name_s = str(udt_name or "").lower()
    if data_type_s in {"smallint", "integer", "bigint", "boolean"}:
        return "INTEGER"
    if data_type_s in {"real", "double precision", "numeric", "decimal"}:
        return "REAL"
    if data_type_s == "bytea" or udt_name_s == "bytea":
        return "BLOB"
    return "TEXT"


def normalize_sqlite_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, memoryview):
        return bytes(value)
    return value


def sqlite_business_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return row is not None


def sqlite_table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall())


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in sqlite_table_info(conn, table)]


def sqlite_pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    info = sqlite_table_info(conn, table)
    return [
        str(row["name"])
        for row in sorted(info, key=lambda item: int(item["pk"] or 0))
        if int(row["pk"] or 0)
    ]


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0])


def pg_business_tables(pg_conn: Any) -> list[str]:
    rows = pg_conn.execute(
        text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """
        )
    ).fetchall()
    return [str(row[0]) for row in rows]


def pg_table_exists(pg_conn: Any, table: str) -> bool:
    row = pg_conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name = :table
            LIMIT 1
            """
        ),
        {"table": table},
    ).fetchone()
    return row is not None


def pg_columns(pg_conn: Any, table: str) -> list[str]:
    rows = pg_conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table
            ORDER BY ordinal_position
            """
        ),
        {"table": table},
    ).fetchall()
    return [str(row[0]) for row in rows]


def pg_column_info(pg_conn: Any, table: str) -> list[dict[str, str]]:
    rows = pg_conn.execute(
        text(
            """
            SELECT column_name, data_type, udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = :table
            ORDER BY ordinal_position
            """
        ),
        {"table": table},
    ).fetchall()
    return [
        {"name": str(row[0]), "data_type": str(row[1] or ""), "udt_name": str(row[2] or "")}
        for row in rows
    ]


def pg_pk_columns(pg_conn: Any, table: str) -> list[str]:
    rows = pg_conn.execute(
        text(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = current_schema()
              AND tc.table_name = :table
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """
        ),
        {"table": table},
    ).fetchall()
    return [str(row[0]) for row in rows]


def pg_count(pg_conn: Any, table: str) -> int:
    return int(pg_conn.execute(text(f"SELECT COUNT(*) FROM {quote_ident(table)}")).scalar_one())


def create_pg_table_from_sqlite(pg_conn: Any, sqlite_conn: sqlite3.Connection, table: str) -> None:
    info = sqlite_table_info(sqlite_conn, table)
    if not info:
        raise RuntimeError(f"SQLite 表 {table!r} 没有字段信息。")
    pk_cols = sqlite_pk_columns(sqlite_conn, table)
    column_lines: list[str] = []
    for row in info:
        col = str(row["name"])
        constraints = [quote_ident(col), sqlite_type_to_pg(row["type"])]
        if int(row["notnull"] or 0) and col not in pk_cols:
            constraints.append("NOT NULL")
        column_lines.append(" ".join(constraints))
    if pk_cols:
        column_lines.append("PRIMARY KEY (" + ", ".join(quote_ident(col) for col in pk_cols) + ")")
    ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} (\n    " + ",\n    ".join(column_lines) + "\n)"
    pg_conn.execute(text(ddl))


def ensure_pg_table_for_sqlite(pg_conn: Any, sqlite_conn: sqlite3.Connection, table: str) -> list[str]:
    if not pg_table_exists(pg_conn, table):
        create_pg_table_from_sqlite(pg_conn, sqlite_conn, table)
    existing = set(pg_columns(pg_conn, table))
    added: list[str] = []
    for row in sqlite_table_info(sqlite_conn, table):
        col = str(row["name"])
        if col in existing:
            continue
        pg_conn.execute(
            text(
                f"ALTER TABLE {quote_ident(table)} "
                f"ADD COLUMN IF NOT EXISTS {quote_ident(col)} {sqlite_type_to_pg(row['type'])}"
            )
        )
        added.append(col)
    return added


def create_sqlite_table_from_pg(sqlite_conn: sqlite3.Connection, pg_conn: Any, table: str) -> None:
    columns = pg_column_info(pg_conn, table)
    if not columns:
        raise RuntimeError(f"PostgreSQL 表 {table!r} 没有字段信息。")
    pk_cols = pg_pk_columns(pg_conn, table)
    column_lines = [
        f"{quote_ident(col['name'])} {pg_type_to_sqlite(col['data_type'], col['udt_name'])}"
        for col in columns
    ]
    if pk_cols:
        column_lines.append("PRIMARY KEY (" + ", ".join(quote_ident(col) for col in pk_cols) + ")")
    ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} (\n    " + ",\n    ".join(column_lines) + "\n)"
    sqlite_conn.execute(ddl)


def ensure_sqlite_table_for_pg(sqlite_conn: sqlite3.Connection, pg_conn: Any, table: str) -> list[str]:
    if not sqlite_table_exists(sqlite_conn, table):
        create_sqlite_table_from_pg(sqlite_conn, pg_conn, table)
    existing = set(sqlite_columns(sqlite_conn, table))
    added: list[str] = []
    for col in pg_column_info(pg_conn, table):
        name = str(col["name"])
        if name in existing:
            continue
        sqlite_conn.execute(
            f"ALTER TABLE {quote_ident(table)} "
            f"ADD COLUMN {quote_ident(name)} {pg_type_to_sqlite(col['data_type'], col['udt_name'])}"
        )
        added.append(name)
    return added


def sqlite_backup_path(sqlite_db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return sqlite_db_path.with_name(f"{sqlite_db_path.stem}.before_cloud_sync_{stamp}{sqlite_db_path.suffix}")


def backup_sqlite_database(sqlite_conn: sqlite3.Connection, sqlite_db_path: Path) -> Path:
    backup_path = sqlite_backup_path(sqlite_db_path)
    with sqlite3.connect(str(backup_path)) as backup_conn:
        sqlite_conn.backup(backup_conn)
    return backup_path


def _pg_insert_sql(table: str, columns: list[str], pk_cols: list[str], conflict_action: str, pg_pk_cols: list[str]) -> str:
    quoted_columns = ", ".join(quote_ident(col) for col in columns)
    params = ", ".join(f":p{idx}" for idx, _ in enumerate(columns))
    base = f"INSERT INTO {quote_ident(table)} ({quoted_columns}) VALUES ({params})"
    if conflict_action == "update" and pk_cols and [col for col in pk_cols] == [col for col in pg_pk_cols]:
        update_cols = [col for col in columns if col not in set(pk_cols)]
        if update_cols:
            assignments = ", ".join(f"{quote_ident(col)} = EXCLUDED.{quote_ident(col)}" for col in update_cols)
            target = ", ".join(quote_ident(col) for col in pk_cols)
            return f"{base} ON CONFLICT ({target}) DO UPDATE SET {assignments}"
    return f"{base} ON CONFLICT DO NOTHING"


def _sqlite_insert_sql(table: str, columns: list[str], pk_cols: list[str], conflict_action: str) -> str:
    quoted_columns = ", ".join(quote_ident(col) for col in columns)
    placeholders = ", ".join("?" for _ in columns)
    base = f"INSERT INTO {quote_ident(table)} ({quoted_columns}) VALUES ({placeholders})"
    if not pk_cols:
        return base
    target = ", ".join(quote_ident(col) for col in pk_cols)
    if conflict_action == "update":
        update_cols = [col for col in columns if col not in set(pk_cols)]
        if update_cols:
            assignments = ", ".join(f"{quote_ident(col)} = excluded.{quote_ident(col)}" for col in update_cols)
            return f"{base} ON CONFLICT ({target}) DO UPDATE SET {assignments}"
    return f"{base} ON CONFLICT ({target}) DO NOTHING"


def sync_sqlite_to_postgres(
    sqlite_db_path: str | Path,
    *,
    conflict_action: str = "update",
    require_postgres_backend: bool = False,
) -> dict[str, Any]:
    sqlite_path = Path(sqlite_db_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"未找到 SQLite 数据库：{sqlite_path}")
    if conflict_action not in {"update", "skip"}:
        raise ValueError("conflict_action 只能是 update 或 skip")

    init_pg_db(require_postgres_backend=require_postgres_backend)
    engine = get_pg_engine(require_postgres_backend=require_postgres_backend)
    table_results: list[dict[str, Any]] = []
    with sqlite3.connect(str(sqlite_path)) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        tables = sqlite_business_tables(sqlite_conn)
        for table in tables:
            result: dict[str, Any] = {
                "table": table,
                "source_rows": 0,
                "processed_rows": 0,
                "target_before": 0,
                "target_after": 0,
                "status": "ok",
                "note": "",
            }
            try:
                source_count = sqlite_count(sqlite_conn, table)
                result["source_rows"] = source_count
                if source_count <= 0:
                    result["status"] = "skipped"
                    result["note"] = "空表跳过"
                    table_results.append(result)
                    continue
                with engine.begin() as pg_conn:
                    target_before = pg_count(pg_conn, table) if pg_table_exists(pg_conn, table) else 0
                    result["target_before"] = target_before
                    added = ensure_pg_table_for_sqlite(pg_conn, sqlite_conn, table)
                    if added:
                        result["note"] = f"补充字段：{', '.join(added)}"
                    pg_cols = set(pg_columns(pg_conn, table))
                    columns = [col for col in sqlite_columns(sqlite_conn, table) if col in pg_cols]
                    if not columns:
                        raise RuntimeError("SQLite/PostgreSQL 没有共同字段。")
                    pk_cols = [col for col in sqlite_pk_columns(sqlite_conn, table) if col in columns]
                    pg_pk_cols = [col for col in pg_pk_columns(pg_conn, table) if col in columns]
                    if not pk_cols and target_before > 0:
                        result["status"] = "skipped"
                        result["note"] = "来源表没有主键且云端表已有数据，为避免重复已跳过。"
                        result["target_after"] = target_before
                        table_results.append(result)
                        continue
                    insert_sql = text(_pg_insert_sql(table, columns, pk_cols, conflict_action, pg_pk_cols))
                    cursor = sqlite_conn.execute(
                        f"SELECT {', '.join(quote_ident(col) for col in columns)} FROM {quote_ident(table)}"
                    )
                    processed = 0
                    while True:
                        batch = cursor.fetchmany(BATCH_SIZE)
                        if not batch:
                            break
                        rows = [
                            {f"p{idx}": row[col] for idx, col in enumerate(columns)}
                            for row in batch
                        ]
                        pg_conn.execute(insert_sql, rows)
                        processed += len(rows)
                    result["processed_rows"] = processed
                    result["target_after"] = pg_count(pg_conn, table)
                    if conflict_action == "update" and pk_cols != pg_pk_cols:
                        result["note"] = (str(result.get("note") or "") + " 主键不一致，重复记录已跳过。").strip()
            except Exception as exc:
                result["status"] = "failed"
                result["note"] = f"{type(exc).__name__}: {exc}"
            table_results.append(result)
    return {
        "direction": "sqlite_to_postgres",
        "conflict_action": conflict_action,
        "tables": table_results,
        "failed_tables": [row["table"] for row in table_results if row["status"] == "failed"],
        "processed_rows": sum(int(row.get("processed_rows") or 0) for row in table_results),
    }


def sync_postgres_to_sqlite(
    sqlite_db_path: str | Path,
    *,
    conflict_action: str = "update",
    require_postgres_backend: bool = False,
    create_backup: bool = True,
) -> dict[str, Any]:
    sqlite_path = Path(sqlite_db_path)
    if conflict_action not in {"update", "skip"}:
        raise ValueError("conflict_action 只能是 update 或 skip")
    init_pg_db(require_postgres_backend=require_postgres_backend)
    engine = get_pg_engine(require_postgres_backend=require_postgres_backend)
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    table_results: list[dict[str, Any]] = []
    backup_path: Path | None = None
    had_sqlite_file = sqlite_path.exists()
    with sqlite3.connect(str(sqlite_path)) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        if create_backup and had_sqlite_file:
            backup_path = backup_sqlite_database(sqlite_conn, sqlite_path)
        with engine.connect() as pg_conn:
            tables = pg_business_tables(pg_conn)
            for table in tables:
                result: dict[str, Any] = {
                    "table": table,
                    "source_rows": 0,
                    "processed_rows": 0,
                    "target_before": 0,
                    "target_after": 0,
                    "status": "ok",
                    "note": "",
                }
                try:
                    source_count = pg_count(pg_conn, table)
                    result["source_rows"] = source_count
                    if source_count <= 0:
                        result["status"] = "skipped"
                        result["note"] = "空表跳过"
                        table_results.append(result)
                        continue
                    target_before = sqlite_count(sqlite_conn, table) if sqlite_table_exists(sqlite_conn, table) else 0
                    result["target_before"] = target_before
                    added = ensure_sqlite_table_for_pg(sqlite_conn, pg_conn, table)
                    if added:
                        result["note"] = f"补充字段：{', '.join(added)}"
                    sqlite_cols = set(sqlite_columns(sqlite_conn, table))
                    columns = [col for col in pg_columns(pg_conn, table) if col in sqlite_cols]
                    if not columns:
                        raise RuntimeError("PostgreSQL/SQLite 没有共同字段。")
                    pk_cols = [col for col in sqlite_pk_columns(sqlite_conn, table) if col in columns]
                    if not pk_cols and target_before > 0:
                        result["status"] = "skipped"
                        result["note"] = "本地表没有主键且已有数据，为避免重复已跳过。"
                        table_results.append(result)
                        continue
                    insert_sql = _sqlite_insert_sql(table, columns, pk_cols, conflict_action)
                    select_sql = text(
                        f"SELECT {', '.join(quote_ident(col) for col in columns)} FROM {quote_ident(table)}"
                    )
                    query_result = pg_conn.execute(select_sql)
                    processed = 0
                    while True:
                        batch = query_result.fetchmany(BATCH_SIZE)
                        if not batch:
                            break
                        values = [
                            tuple(normalize_sqlite_value(value) for value in row)
                            for row in batch
                        ]
                        sqlite_conn.executemany(insert_sql, values)
                        processed += len(values)
                    result["processed_rows"] = processed
                    result["target_after"] = sqlite_count(sqlite_conn, table)
                except Exception as exc:
                    result["status"] = "failed"
                    result["note"] = f"{type(exc).__name__}: {exc}"
                table_results.append(result)
        sqlite_conn.commit()
    return {
        "direction": "postgres_to_sqlite",
        "conflict_action": conflict_action,
        "backup_path": str(backup_path) if backup_path is not None else "",
        "tables": table_results,
        "failed_tables": [row["table"] for row in table_results if row["status"] == "failed"],
        "processed_rows": sum(int(row.get("processed_rows") or 0) for row in table_results),
    }
