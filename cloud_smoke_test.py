"""Streamlit Cloud smoke test page for Neon PostgreSQL."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from sqlalchemy import text

from db_config import get_db_backend, is_postgres
from db_pg import PG_CORE_TABLES, get_pg_engine, init_pg_db


st.set_page_config(page_title="Neon PostgreSQL 连接测试", layout="wide")
st.title("Neon PostgreSQL 连接测试")

backend = get_db_backend()
st.caption(f"当前 APP_DB_BACKEND：{backend}")

if not is_postgres():
    st.warning('请在 Streamlit Secrets 中设置 APP_DB_BACKEND="postgres"。')
    st.stop()

try:
    init_pg_db(run_optional=False)
    engine = get_pg_engine()
    with engine.connect() as conn:
        server_time = conn.execute(text("SELECT now() AS server_time")).scalar_one()
        rows = []
        for table in PG_CORE_TABLES:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one()
            rows.append({"table": table, "row_count": int(count)})
    st.success("Neon PostgreSQL 连接成功，核心表检查完成。")
    st.metric("server_time", str(server_time))
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
except Exception as exc:
    st.error("Neon PostgreSQL 连接或建表失败，请检查 Streamlit Secrets 中的连接配置。")
    st.caption(f"错误类型：{type(exc).__name__}")
    st.exception(exc)
