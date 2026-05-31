"""Streamlit Cloud data migration and backup tools for Neon PostgreSQL."""

from __future__ import annotations

import contextlib
import io
import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from db_config import get_db_backend
from db_pg import init_pg_db
from migrate_sqlite_to_postgres import migrate
from postgres_to_sqlite_backup import backup_postgres_to_sqlite


st.set_page_config(page_title="Neon Data Tools", layout="wide")
st.title("Neon 数据迁移工具")

backend = get_db_backend()
st.caption(f"当前 APP_DB_BACKEND: {backend}")
st.info("本页面不会显示 Neon 连接串或密码。导入会使用 Streamlit Cloud Secrets 中已保存的连接配置。")

if backend != "postgres":
    st.error('当前不是 PostgreSQL 模式。请先在 Streamlit Secrets 中设置 APP_DB_BACKEND = "postgres"。')
    st.stop()

try:
    init_pg_db(run_optional=False)
except Exception as exc:
    st.error("PostgreSQL 初始化失败。请检查 Streamlit Secrets 中的连接配置。")
    st.caption(f"错误类型：{type(exc).__name__}")
    st.stop()

tab_import, tab_export = st.tabs(["本地 SQLite 导入 Neon", "Neon 导出 SQLite"])

with tab_import:
    st.subheader("上传本地 otc_gui.db 并导入 Neon")
    st.write("适用于把电脑本地旧系统的数据迁移到线上 Neon。重复导入时，主键冲突的数据会跳过。")
    uploaded = st.file_uploader(
        "选择本地 SQLite 数据库文件",
        type=["db", "sqlite", "sqlite3"],
        help="通常选择你电脑上的 otc_gui.db。",
    )
    if uploaded is not None:
        st.write(f"已选择：`{uploaded.name}`，大小：{uploaded.size:,} bytes")
        st.warning("导入前建议确认线上没有正在编辑的数据。导入不会删除 Neon 中已有数据。")
        if st.button("开始导入到 Neon", type="primary"):
            log_buffer = io.StringIO()
            with tempfile.TemporaryDirectory() as tmpdir:
                sqlite_path = Path(tmpdir) / "uploaded_otc_gui.db"
                sqlite_path.write_bytes(uploaded.getvalue())
                with st.spinner("正在导入，请不要关闭页面..."):
                    with contextlib.redirect_stdout(log_buffer):
                        code = migrate(sqlite_path)
            log_text = log_buffer.getvalue().strip()
            if log_text:
                st.code(log_text)
            if code == 0:
                st.success("导入完成。现在可以切回 app.py 查看线上数据。")
            else:
                st.error("导入未完全成功，请查看上面的日志。")

with tab_export:
    st.subheader("从 Neon 生成 SQLite 备份")
    st.write("适用于把线上 Neon 当前数据下载到本地，作为 SQLite 备份或后续本地使用。")
    if st.button("生成并下载 SQLite 备份", type="primary"):
        filename = f"neon_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sqlite3"
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                backup_path = Path(tmpdir) / filename
                with st.spinner("正在从 Neon 导出 SQLite 备份..."):
                    summary = backup_postgres_to_sqlite(backup_path)
                data = backup_path.read_bytes()
            st.success(f"导出完成，共 {len(summary['tables'])} 张表，{summary['total_rows']} 行。")
            table_rows = [{"table": table, "rows": rows} for table, rows in summary["tables"].items()]
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
            st.download_button(
                "下载 SQLite 备份文件",
                data=data,
                file_name=filename,
                mime="application/octet-stream",
            )
        except Exception as exc:
            st.error("导出失败，请查看错误类型并联系维护。")
            st.caption(f"错误类型：{type(exc).__name__}")
