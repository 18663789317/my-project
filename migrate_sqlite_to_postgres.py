"""Migrate local SQLite business tables into Neon PostgreSQL."""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import text

from db_config import get_db_backend
from db_pg import get_pg_engine, init_pg_db


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_SQLITE_DB = PROJECT_ROOT / "otc_gui.db"
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


def sqlite_table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall())


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0])


def pg_table_exists(pg_conn: Any, table: str) -> bool:
    exists = pg_conn.execute(
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
    return exists is not None


def pg_table_columns(pg_conn: Any, table: str) -> list[str]:
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


def pg_count(pg_conn: Any, table: str) -> int:
    return int(pg_conn.execute(text(f"SELECT COUNT(*) FROM {quote_ident(table)}")).scalar_one())


def create_pg_table_from_sqlite(pg_conn: Any, sqlite_conn: sqlite3.Connection, table: str) -> None:
    info = sqlite_table_info(sqlite_conn, table)
    if not info:
        raise RuntimeError(f"SQLite 表 {table!r} 没有字段信息，无法创建 PostgreSQL 表。")

    pk_cols = [str(row["name"]) for row in sorted(info, key=lambda item: int(item["pk"] or 0)) if int(row["pk"] or 0)]
    column_lines: list[str] = []
    for row in info:
        col = str(row["name"])
        pg_type = sqlite_type_to_pg(row["type"])
        constraints: list[str] = [quote_ident(col), pg_type]
        if int(row["notnull"] or 0) and col not in pk_cols:
            constraints.append("NOT NULL")
        column_lines.append(" ".join(constraints))
    if pk_cols:
        column_lines.append("PRIMARY KEY (" + ", ".join(quote_ident(col) for col in pk_cols) + ")")

    ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} (\n    " + ",\n    ".join(column_lines) + "\n)"
    pg_conn.execute(text(ddl))
    print(f"PostgreSQL 中不存在表 {table}，已按 SQLite 字段保守创建。")


def ensure_pg_columns_for_sqlite_table(pg_conn: Any, sqlite_conn: sqlite3.Connection, table: str) -> list[str]:
    if not pg_table_exists(pg_conn, table):
        create_pg_table_from_sqlite(pg_conn, sqlite_conn, table)
    pg_columns = set(pg_table_columns(pg_conn, table))
    added: list[str] = []
    for row in sqlite_table_info(sqlite_conn, table):
        col = str(row["name"])
        if col in pg_columns:
            continue
        pg_type = sqlite_type_to_pg(row["type"])
        pg_conn.execute(
            text(
                f"ALTER TABLE {quote_ident(table)} "
                f"ADD COLUMN IF NOT EXISTS {quote_ident(col)} {pg_type}"
            )
        )
        added.append(col)
    return added


def insert_table_rows(
    sqlite_conn: sqlite3.Connection,
    pg_conn: Any,
    table: str,
    columns: list[str],
) -> int:
    quoted_columns = ", ".join(quote_ident(col) for col in columns)
    value_params = ", ".join(f":{col}" for col in columns)
    insert_sql = text(
        f"INSERT INTO {quote_ident(table)} ({quoted_columns}) "
        f"VALUES ({value_params}) ON CONFLICT DO NOTHING"
    )
    cursor = sqlite_conn.execute(
        f"SELECT {quoted_columns} FROM {quote_ident(table)}"
    )
    sent_rows = 0
    while True:
        batch = cursor.fetchmany(BATCH_SIZE)
        if not batch:
            break
        pg_conn.execute(insert_sql, [dict(row) for row in batch])
        sent_rows += len(batch)
    return sent_rows


def migrate(sqlite_db_path: Path = DEFAULT_SQLITE_DB) -> int:
    backend = get_db_backend()
    if backend != "postgres":
        print(f"当前 APP_DB_BACKEND={backend!r}，迁移已停止。请先设置 APP_DB_BACKEND=postgres。")
        return 2
    if not sqlite_db_path.exists():
        print(f"未找到 SQLite 数据库：{sqlite_db_path}")
        return 2

    print("初始化 PostgreSQL 表结构...")
    try:
        init_pg_db()
    except Exception as exc:
        print("PostgreSQL 初始化失败。请检查 DATABASE_URL 或 .streamlit/secrets.toml 中的连接配置。")
        print(f"错误类型：{type(exc).__name__}")
        return 1

    sqlite_conn = sqlite3.connect(str(sqlite_db_path))
    sqlite_conn.row_factory = sqlite3.Row
    try:
        engine = get_pg_engine()
    except Exception as exc:
        print("PostgreSQL 连接失败。请检查 DATABASE_URL 或 .streamlit/secrets.toml 中的连接配置。")
        print(f"错误类型：{type(exc).__name__}")
        sqlite_conn.close()
        return 1

    success_tables: list[str] = []
    skipped_tables: list[str] = []
    failed_tables: list[str] = []
    total_inserted = 0

    try:
        tables = sqlite_business_tables(sqlite_conn)
        print(f"发现 SQLite 业务表 {len(tables)} 张。")
        for table in tables:
            source_count = sqlite_count(sqlite_conn, table)
            print(f"\n表 {table}: SQLite 行数 {source_count}")
            if source_count <= 0:
                print(f"表 {table}: 跳过空表")
                skipped_tables.append(table)
                continue
            try:
                with engine.begin() as pg_conn:
                    before_count = pg_count(pg_conn, table) if pg_table_exists(pg_conn, table) else 0
                    added_columns = ensure_pg_columns_for_sqlite_table(pg_conn, sqlite_conn, table)
                    if added_columns:
                        print(f"表 {table}: PostgreSQL 补充字段 {', '.join(added_columns)}")
                    pg_columns = set(pg_table_columns(pg_conn, table))
                    sqlite_columns = [str(row["name"]) for row in sqlite_table_info(sqlite_conn, table)]
                    columns = [col for col in sqlite_columns if col in pg_columns]
                    if not columns:
                        raise RuntimeError("SQLite/PostgreSQL 没有可迁移的共同字段。")
                    sent_rows = insert_table_rows(sqlite_conn, pg_conn, table, columns)
                    after_count = pg_count(pg_conn, table)
                inserted = max(after_count - before_count, 0)
                total_inserted += inserted
                success_tables.append(table)
                print(
                    f"表 {table}: 已发送 {sent_rows} 行，新增 {inserted} 行，"
                    f"PostgreSQL 当前行数 {after_count}"
                )
            except Exception as exc:
                failed_tables.append(table)
                print(f"表 {table}: 迁移失败：{exc}")
    finally:
        sqlite_conn.close()

    print("\n迁移汇总")
    print(f"成功表：{len(success_tables)} {success_tables}")
    print(f"跳过表：{len(skipped_tables)} {skipped_tables}")
    print(f"失败表：{len(failed_tables)} {failed_tables}")
    print(f"总新增行数：{total_inserted}")
    return 1 if failed_tables else 0


def main() -> int:
    return migrate()


if __name__ == "__main__":
    raise SystemExit(main())
