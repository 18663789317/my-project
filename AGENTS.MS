# AGENTS.MS

本文件记录对 `D:\biancheng` 项目的快速项目地图和协作约定，供后续编码代理或开发者进入仓库时先读。

## 项目概览

- 这是一个 Windows 本地运行的 Streamlit 场外期权风险管理工作台，README 将项目描述为 `OPTION 管理软件`。
- 核心入口是根目录的 `app.py`，当前约 8.7 万行，是一个单文件主应用；不要把它当成小模块随手大改。
- 默认应用标题为 `CH场外期权结构风险管理监控系统 V8.2`。
- 运行时数据主要落在根目录 SQLite 数据库 `otc_gui.db`，旁边可能出现 `otc_gui.db-wal` / `otc_gui.db-shm`。
- 业务功能覆盖策略组、结构录入、价格录入、现货仓库、期权仓库、监控计算、自助报价/反解 IV、蒙卡系统/策略组综析、回测/3D 估值/Greeks、累计结构精准套保。

## 重要协作约束

- 根目录已有 `CLAUDE.md`，其核心约束是：用户只要求“检测 / 分析 / 看看 / 总结 / review”时只读不写；只有用户明确授权“改 / 修改 / 帮我改 / 帮我写”等，才允许改源码。
- 当前这份 `AGENTS.MS` 是用户明确要求生成的项目说明文件；后续不要因为发现 bug 就擅自修复业务代码，先报告再等授权。
- 工作树可能经常很脏，已有大量未提交或未跟踪文件；不要回滚、覆盖、删除你没有创建的改动。
- 对 `otc_gui.db` 这类真实业务数据保持谨慎。写数据库前先确认任务需要；测试优先用 `sqlite3.connect(":memory:")` 或临时副本。

## 目录地图

- `app.py`: 主应用、业务规则、数据库 schema/migration、计算模型、Streamlit UI 全部集中在这里。
- `launcher.py`: 启动 Streamlit，切到项目根目录，优先从 `127.0.0.1:8501` 起找可用端口，并关闭 Streamlit file watcher。
- `launch_app.cmd` / `启动OTC工作台.cmd`: Windows 双击启动入口。
- `requirements.txt`: 运行/测试依赖，包含 streamlit、pandas、numpy、plotly、akshare、scipy、matplotlib、PyMuPDF、python-docx、pytest 等。
- `.streamlit/config.toml`: Streamlit 配置，headless=true，关闭 CORS 与 XSRF。
- `tests/`: pytest 回归测试，通常通过 importlib 加载根目录 `app.py` 的核心函数。
- `tests/app.py`: 看起来是旧版/快照式大文件；多数测试显式加载 `../app.py`，不要把它误认为当前入口。
- `tools/`: 文档生成、快照备份/恢复、页面性能 profiling、监控/平仓/专项页回归脚本。
- `backups/`: 快照、回滚和取证材料。
- `cache/special_pages/`: 专项页历史数据和结果缓存。
- `output/`, `output_images/`, `artifacts/`: 运行检查、报告预览、截图、渲染样例等生成物。
- `dist/`, `dist_release/`, `build/`: PyInstaller 打包输出或中间产物。

## 运行命令

```powershell
cd D:\biancheng
python -m pip install -r requirements.txt
python launcher.py
```

也可以直接运行：

```powershell
streamlit run app.py
```

Windows 双击路径：

```powershell
.\launch_app.cmd
```

## 测试与验证

常规测试：

```powershell
python -m pytest tests
```

针对单个风险点优先跑相关测试，例如：

```powershell
python -m pytest tests\test_option_warehouse_module_core.py
python -m pytest tests\test_monitor_perf_safety.py
python -m pytest tests\test_volatility_valuation_structures.py
```

有些测试会读取并编译 `app.py` 在 `st.set_page_config(...)` 之前的核心逻辑，以避免启动完整 Streamlit UI。这个模式也被 `tools/profile_page_switch.py` 和多个回归脚本使用。

## 打包发布

- 普通打包：双击或运行 `build_package.bat`，输出 `dist\OTC-Risk-App`。
- 生成 zip：运行 `package_latest_zip.bat`，输出 `dist_release\CH-OTC-Risk-App.zip`。
- `OTC-Risk-App.spec` 使用 PyInstaller，以 `launcher.py` 为入口，并把 `app.py`、可选的 `otc_gui.db`、`manifest.json`、Streamlit/AkShare 资源和元数据打进发行目录。
- 打包环境除 `requirements.txt` 外还需要 `pyinstaller`；脚本会检查 streamlit、pandas、matplotlib、chinese_calendar、akshare、pyarrow、PyInstaller。

## 数据库与核心表

`init_db(conn)` 在 `app.py` 中创建/迁移 SQLite schema。已识别的核心表包括：

- `strategy_group`: 策略组主数据。
- `structure`: 结构主表，保存累计、雪球、安全气囊、TRS、香草期权等结构参数。
- `price`: 日期/品种收盘或结算价。
- `trading_calendar_override`: 交易日手动覆盖。
- `close_trade`, `close_trade2`: 平仓记录；新逻辑主要围绕 `close_trade2`。
- `snowball_conversion`: 雪球折价转期货记录。
- `structure_position_adjustment`: 结构手动增减仓/回滚。
- `spot_position_lot`, `spot_hedge_match_log`, `spot_summary_hidden`: 现货仓库与对冲匹配。
- `app_kv`: UI 偏好、标题、默认策略组等键值配置。
- `structure_template`: 结构模板。
- `self_quote_multi_value_preset`: 自助报价多值预设。
- `probexp_market_input`, `probexp_calc_log`: 蒙卡/概率期望输入与结果。
- `precise_hedge_calc_log`: 精准套保保存结果。
- `winrate_valuation_surface_cache`: 3D 估值曲面缓存。

数据库连接使用 `get_conn()` / `get_session_conn()`，启用 WAL、foreign_keys、busy_timeout，并有锁错误友好提示。

## 业务结构与页面入口

侧边栏菜单在 `app.py` 的 UI 区域定义，当前页面包括：

- `生成策略组`
- `结构录入`
- `价格录入`
- `现货头寸仓库管理`
- `期权头寸仓库管理`
- `监控计算`
- `专项：自助报价&反解IV`
- `专项：蒙卡系统&策略组综析`
- `专项：回测&3D估值&Greeks扫描`
- `专项：累计结构精准套保`

结构类型/策略代码集中在 `STRATEGY_ALIAS_TO_CODE`、`STRUCTURE_REGISTRY`、`STRATEGY_CODE_TO_CN`、`CN_TO_STRATEGY_CODE` 附近。重点代码包括 `BASIC_RANGE`、`FLOAT_KO`、`NO_KO`、`PREMIUM_SUBSIDY`、`RANGE_SUBSIDY`、`PHOENIX_ACC_CALL_FIXED`、`PHOENIX_ACC_PUT_FIXED`、`SAFETY_AIRBAG`、`SNOWBALL`、`TRS`、`VANILLA_OPTION`。

## 外部数据与缓存

- AkShare 是可选/懒加载依赖；应用里有离线模式和超时保护，页面加载默认尽量避免无控制联网。
- 专项页会用 `cache/special_pages/` 缓存历史价格、主力合约目录、计算状态等。
- 报告图片默认写到 `output_images/report_exports`。
- 文档、报告、预览图和 Playwright 截图多在 `output/` 或 `artifacts/`。

## 常用工具脚本

- `tools/profile_page_switch.py`: profile 慢页面切换数据管线。
- `tools/regression_monitor_pipeline.py`: 监控链路回归检查。
- `tools/regression_close_linkage.py`: 平仓联动回归检查。
- `tools/regression_special_conditioned_reval.py`: 专项页条件重估回归检查。
- `tools/verify_monitor_perf_safety.py`: 验证监控性能优化前后结果一致性。
- `tools/generate_user_manual.py`: 生成用户手册 docx。
- `tools/generate_product_api_doc.py`: 生成产品/API 对接文档 docx。
- `tools/backup_snapshot.ps1`, `tools/restore_snapshot.ps1`, `tools/list_snapshots.ps1`: 快照管理。

## 改动建议

- 优先做小范围修改，并给同一风险点补对应 pytest；不要顺手整理整个 `app.py`。
- 涉及页面性能、缓存、专项页预热、后台计算时，额外跑相关 regression/tool 脚本。
- 涉及数据库 schema 时，同步考虑旧库迁移、`_ensure_column`、外键、唯一约束、已有 WAL 状态和真实数据兼容。
- 涉及结构状态、敲入/敲出、自然到期、平仓或仓位口径时，优先搜索现有测试名和函数名，沿用既有规则。
- UI 变更需要注意紧凑显示、宽表、中文列名、Streamlit rerun/session_state 以及页面切换默认选择逻辑。

