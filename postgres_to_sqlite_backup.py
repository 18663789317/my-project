"""Export Neon PostgreSQL business tables into a local SQLite backup file."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import text

from db_config import get_db_backend
from db_pg import get_pg_engine


PROJECT_ROOT = Path(__file__).resolve().parent
BATCH_SIZE = 500


def quote_ident(name: str) -> str:
    return '"' + str(name).replace('"', '""') + '"'


def sqlite_type_for_pg(data_type: str, udt_name: str = "") -> str:
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
    return value


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


def pg_columns(pg_conn: Any, table: str) -> list[dict[str, str]]:
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
        {
            "name": str(row[0]),
            "data_type": str(row[1] or ""),
            "udt_name": str(row[2] or ""),
        }
        for row in rows
    ]


def create_sqlite_table(sqlite_conn: sqlite3.Connection, table: str, columns: list[dict[str, str]]) -> None:
    column_defs = [
        f"{quote_ident(col['name'])} {sqlite_type_for_pg(col['data_type'], col['udt_name'])}"
        for col in columns
    ]
    ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} (\n    " + ",\n    ".join(column_defs) + "\n)"
    sqlite_conn.execute(ddl)


def export_table(pg_conn: Any, sqlite_conn: sqlite3.Connection, table: str) -> int:
    columns = pg_columns(pg_conn, table)
    if not columns:
        return 0
    create_sqlite_table(sqlite_conn, table, columns)
    column_names = [col["name"] for col in columns]
    quoted_columns = ", ".join(quote_ident(col) for col in column_names)
    placeholders = ", ".join("?" for _ in column_names)
    insert_sql = f"INSERT INTO {quote_ident(table)} ({quoted_columns}) VALUES ({placeholders})"
    select_sql = text(f"SELECT {quoted_columns} FROM {quote_ident(table)}")
    result = pg_conn.execute(select_sql)
    total = 0
    while True:
        batch = result.fetchmany(BATCH_SIZE)
        if not batch:
            break
        values = [tuple(normalize_sqlite_value(value) for value in row) for row in batch]
        sqlite_conn.executemany(insert_sql, values)
        total += len(values)
    return total


def backup_postgres_to_sqlite(
    output_path: str | Path,
    *,
    require_postgres_backend: bool = True,
) -> dict[str, Any]:
    if require_postgres_backend and get_db_backend() != "postgres":
        raise RuntimeError("Current backend is not postgres; export stopped.")
    output = Path(output_path)
    if output.exists():
        raise FileExistsError(f"Backup file already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    engine = get_pg_engine(require_postgres_backend=require_postgres_backend)
    table_counts: dict[str, int] = {}
    with engine.connect() as pg_conn, sqlite3.connect(str(output)) as sqlite_conn:
        tables = pg_business_tables(pg_conn)
        for table in tables:
            table_counts[table] = export_table(pg_conn, sqlite_conn, table)
        sqlite_conn.commit()
    return {
        "path": str(output),
        "tables": table_counts,
        "total_rows": sum(table_counts.values()),
    }


def default_backup_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / f"postgres_backup_{stamp}.sqlite3"


def main() -> int:
    try:
        summary = backup_postgres_to_sqlite(default_backup_path())
    except Exception as exc:
        print(f"PostgreSQL export failed: {type(exc).__name__}: {exc}")
        return 1
    print(f"SQLite backup file: {summary['path']}")
    print(f"Exported tables: {len(summary['tables'])}")
    print(f"Exported rows: {summary['total_rows']}")
    for table, count in summary["tables"].items():
        print(f"- {table}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
