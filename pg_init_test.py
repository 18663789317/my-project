"""Initialize and inspect PostgreSQL schema for the OTC app."""

from __future__ import annotations

from sqlalchemy import text

from db_config import get_db_backend
from db_pg import PG_CORE_TABLES, get_pg_engine, init_pg_db


def main() -> int:
    backend = get_db_backend()
    if backend != "postgres":
        print(f"当前 APP_DB_BACKEND={backend!r}，不会访问 PostgreSQL。请设置 APP_DB_BACKEND=postgres。")
        return 2

    print("初始化 PostgreSQL 表结构...")
    try:
        init_pg_db()
    except Exception as exc:
        print("PostgreSQL 初始化失败。请检查 DATABASE_URL 或 .streamlit/secrets.toml 中的连接配置。")
        print(f"错误类型：{type(exc).__name__}")
        return 1

    try:
        engine = get_pg_engine()
    except Exception as exc:
        print("PostgreSQL 连接失败。请检查 DATABASE_URL 或 .streamlit/secrets.toml 中的连接配置。")
        print(f"错误类型：{type(exc).__name__}")
        return 1
    with engine.connect() as conn:
        tables = conn.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
            )
        ).scalars().all()

        print("\n当前 PostgreSQL 业务表：")
        for table in tables:
            print(f"- {table}")

        print("\n核心表行数：")
        for table in PG_CORE_TABLES:
            if table not in tables:
                print(f"- {table}: 不存在")
                continue
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            print(f"- {table}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
