"""Backend routing helpers for SQLite and PostgreSQL modes."""

from __future__ import annotations

import importlib
import sys
from typing import Any, Callable

import streamlit as st

from db_compat import get_compat_conn
from db_config import get_db_backend, is_sqlite
from db_pg import init_pg_db


DB_MODE_LABELS = {
    "sqlite": "SQLite 本地数据库",
    "postgres": "PostgreSQL 在线数据库",
}


def get_db_mode_label() -> str:
    return DB_MODE_LABELS[get_db_backend()]


def display_db_mode_sidebar() -> None:
    st.sidebar.caption(f"数据库模式：{get_db_mode_label()}")


def _resolve_app_callable(name: str) -> Callable[..., Any]:
    for module_name in ("__main__", "app"):
        module = sys.modules.get(module_name)
        fn = getattr(module, name, None) if module is not None else None
        if callable(fn):
            return fn
    module = importlib.import_module("app")
    fn = getattr(module, name, None)
    if not callable(fn):
        raise RuntimeError(f"app.py 中未找到可调用函数 {name}。")
    return fn


def get_database_connection(sqlite_get_conn: Callable[[], Any] | None = None) -> Any:
    if is_sqlite():
        factory = sqlite_get_conn or _resolve_app_callable("get_conn")
        return factory()
    return get_compat_conn()


def get_session_database_connection(
    sqlite_get_session_conn: Callable[..., Any] | None = None,
    state: Any | None = None,
) -> Any:
    if is_sqlite():
        factory = sqlite_get_session_conn or _resolve_app_callable("get_session_conn")
        if state is None:
            return factory()
        return factory(state)
    return get_compat_conn()


def _init_pg_db_fast() -> None:
    try:
        init_pg_db(run_optional=False)
    except TypeError as exc:
        if "run_optional" not in str(exc):
            raise
        init_pg_db()


def init_database(
    sqlite_init_db: Callable[[Any], None] | None = None,
    sqlite_conn: Any | None = None,
) -> Any:
    if is_sqlite():
        conn = sqlite_conn if sqlite_conn is not None else get_database_connection()
        init_fn = sqlite_init_db or _resolve_app_callable("init_db")
        init_fn(conn)
        return conn
    _init_pg_db_fast()
    return get_compat_conn()
