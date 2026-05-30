# my-project
OPTION 管理软件

## Streamlit Cloud + Neon PostgreSQL 部署说明

本地默认使用 SQLite，数据库文件为项目根目录下的 `otc_gui.db`。如果没有配置
`APP_DB_BACKEND`，系统默认按 `sqlite` 模式运行，旧的本地系统可以继续直接打开。

线上部署到 Streamlit Cloud 时使用 Neon PostgreSQL。通过 `APP_DB_BACKEND` 切换数据库：

- `APP_DB_BACKEND="sqlite"`：使用本地 SQLite / `otc_gui.db`
- `APP_DB_BACKEND="postgres"`：使用 Neon PostgreSQL

本地 SQLite 运行命令（PowerShell）：

```powershell
$env:APP_DB_BACKEND="sqlite"
streamlit run app.py
```

PostgreSQL 连接测试命令（PowerShell）：

```powershell
$env:APP_DB_BACKEND="postgres"
streamlit run db_test.py
```

PostgreSQL 建表命令（PowerShell）：

```powershell
$env:APP_DB_BACKEND="postgres"
python pg_init_test.py
```

SQLite 到 PostgreSQL 迁移命令（PowerShell）：

```powershell
$env:APP_DB_BACKEND="postgres"
python migrate_sqlite_to_postgres.py
```

迁移脚本优先读取环境变量 `DATABASE_URL`。如果没有配置 `DATABASE_URL`，再读取
`.streamlit/secrets.toml` 中的 `[connections.postgres].url`。

Streamlit Cloud Secrets 模板：

```toml
APP_DB_BACKEND = "postgres"

[connections.postgres]
url = "postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```

不要提交以下文件或敏感内容：

- `.streamlit/secrets.toml`
- `otc_gui.db`
- `otc_gui.db-wal`
- `otc_gui.db-shm`
- `.env`

## 我下一步怎么部署

### A. 先让 Codex 提交代码

只提交代码文件，不提交本地数据库和 secrets。以下文件不要提交到 GitHub：

- `.streamlit/secrets.toml`
- `otc_gui.db`
- `otc_gui.db-wal`
- `otc_gui.db-shm`
- `.env`

### B. Streamlit Cloud 先部署测试页

在 Streamlit Cloud 创建或修改 App 时先填写：

- Repository: `18663789317/my-project`
- Branch: `codex/streamlit-cloud-neon-deployment`
- Main file path: `cloud_smoke_test.py`
- Python version: `3.11` 或 `3.12`

如果后续已经把该分支合并到 GitHub 的 `main`，再把 Branch 改成 `main`。

### C. Streamlit Cloud Secrets 填写模板

在 Streamlit Cloud 的 Secrets 页面填写：

```toml
APP_DB_BACKEND = "postgres"

[connections.postgres]
url = "postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```

说明：

- 把 `USER` / `PASSWORD` / `HOST` / `DBNAME` 换成 Neon 里的真实信息。
- 不要把 Secrets 发给 Codex。
- 不要把 Secrets 上传到 GitHub。
- 如果 Neon 给的是 `postgresql://`，要改成 `postgresql+psycopg2://`。

### D. 测试页通过后，再部署主程序

`cloud_smoke_test.py` 显示 Neon 连接成功、核心表行数正常后，再把 Streamlit Cloud 的入口改成：

- Main file path: `app.py`

### E. 上线后检查

上线主程序后检查：

- 侧边栏必须显示 `PostgreSQL / Neon 在线数据库`。
- 能看到策略组。
- 能看到结构。
- 能看到价格。
- 新增一条测试价格。
- 刷新后测试价格还在。
- 重启 App 后测试价格还在。
