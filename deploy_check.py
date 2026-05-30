"""Deployment readiness check for Streamlit Cloud + Neon."""

from __future__ import annotations

from pathlib import Path

from db_config import get_db_backend
from db_pg import get_pg_database_url


REQUIRED_DEPENDENCIES = {
    "streamlit",
    "sqlalchemy",
    "psycopg2-binary",
    "pandas",
    "numpy",
}

REQUIRED_FILES = {
    "app.py",
    "db_config.py",
    "db_pg.py",
    "db_router.py",
    "db_compat.py",
    "db_test.py",
    "pg_init_test.py",
    "migrate_sqlite_to_postgres.py",
}


def _requirements_entries() -> set[str]:
    path = Path("requirements.txt")
    if not path.exists():
        return set()
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        name = clean.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].split("~=", 1)[0].strip()
        entries.add(name.lower())
    return entries


def _postgres_config_detected() -> bool:
    try:
        return bool(get_pg_database_url())
    except Exception:
        return False


def main() -> int:
    backend = get_db_backend()
    print(f"APP_DB_BACKEND: {backend}")

    requirements = _requirements_entries()
    missing_deps = sorted(dep for dep in REQUIRED_DEPENDENCIES if dep.lower() not in requirements)
    missing_files = sorted(path for path in REQUIRED_FILES if not Path(path).exists())

    if missing_deps:
        print("缺少依赖：")
        for dep in missing_deps:
            print(f"- {dep}")
    else:
        print("依赖检查：通过")

    if missing_files:
        print("缺少关键文件：")
        for path in missing_files:
            print(f"- {path}")
    else:
        print("关键文件检查：通过")

    if missing_deps or missing_files:
        print("NOT READY: missing dependency/file")
        return 1

    if backend == "sqlite":
        print("当前为本地 SQLite 模式，不要求连接 Neon。")
        print("READY: sqlite local mode")
        return 0

    if backend == "postgres":
        if _postgres_config_detected():
            print("PostgreSQL 连接配置：已检测到连接配置")
            print("READY: postgres config detected")
            return 0
        print("PostgreSQL 连接配置：未检测到连接配置")
        print("NOT READY: missing postgres config")
        return 1

    print("NOT READY: invalid backend")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
