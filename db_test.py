"""Streamlit page for testing the Neon PostgreSQL connection."""

from __future__ import annotations

import streamlit as st

from db_config import get_db_backend, is_postgres
from db_pg import pg_query
from db_router import display_db_mode_sidebar, get_db_mode_label


st.set_page_config(page_title="PostgreSQL 连接测试", layout="wide")
display_db_mode_sidebar()

st.title("PostgreSQL 连接测试")
st.caption(f"当前数据库模式：{get_db_mode_label()}")

if not is_postgres():
    st.warning(
        f"当前 APP_DB_BACKEND={get_db_backend()!r}，本页面不会访问 Neon PostgreSQL。"
        " 如需测试连接，请切换到 postgres 模式。"
    )
    st.code(
        "$env:APP_DB_BACKEND='postgres'\nstreamlit run db_test.py",
        language="powershell",
    )
    st.stop()

st.info("本页面只测试 Streamlit Secrets 中的 [connections.postgres]，不会访问本地 otc_gui.db。")

try:
    df = pg_query(
        """
        SELECT
            current_database() AS database_name,
            current_user AS user_name,
            now() AS server_time,
            version() AS server_version
        """
    )
    st.success("PostgreSQL 连接成功。")
    st.dataframe(df, use_container_width=True)
except Exception as exc:
    st.error("PostgreSQL 连接失败，请检查 Streamlit Secrets 或环境变量配置。")
    st.exception(exc)
    st.code(
        """
# .streamlit/secrets.toml
APP_DB_BACKEND = "postgres"

[connections.postgres]
url = "postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require"
""".strip(),
        language="toml",
    )
