"""Manual SQLite <-> Neon PostgreSQL synchronization helpers."""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from sqlalchemy import text

from db_pg import get_pg_engine, init_pg_db


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
BATCH_SIZE = 500
KEY_SELECT_BATCH_SIZE = 100
ProgressCallback = Callable[[dict[str, Any]], None]
PG_SYNC_STATEMENT_TIMEOUT = "30s"
PG_SYNC_LOCK_TIMEOUT = "3s"
DIFF_EXAMPLE_LIMIT = 5

TABLE_BUSINESS_NAMES = {
    "strategy_group": "策略组",
    "structure": "结构",
    "price": "价格",
    "close_trade": "旧版平仓记录",
    "close_trade2": "平仓记录",
    "app_kv": "系统设置",
    "risk_credit_limit": "授信额度",
    "structure_template": "结构模板",
    "spot_position_lot": "现货持仓批次",
    "spot_hedge_match_log": "现货对冲匹配记录",
    "trading_calendar_override": "交易日历调整",
    "spot_summary_hidden": "现货汇总隐藏项",
    "structure_position_adjustment": "结构持仓调整",
    "snowball_conversion": "雪球转换记录",
    "probexp_market_input": "概率分析市场输入",
    "probexp_calc_log": "概率分析计算记录",
    "precise_hedge_calc_log": "精准对冲计算记录",
    "winrate_valuation_surface_cache": "胜率估值缓存",
    "self_quote_multi_value_preset": "自报价预设",
    "close_revert_log": "平仓回退记录",
}

COLUMN_BUSINESS_NAMES = {
    "group_id": "策略组ID",
    "group_name": "策略组名称",
    "structure_id": "结构ID",
    "structure_code": "结构编号",
    "name": "名称",
    "underlying": "标的",
    "kind": "结构类型",
    "strategy": "策略",
    "dt": "日期",
    "settle": "结算价",
    "source": "来源",
    "updated_at": "更新时间",
    "close_id": "平仓ID",
    "side": "方向",
    "qty": "数量",
    "close_price": "平仓价",
    "pnl": "盈亏",
    "k": "配置项",
    "risk_party": "风险承担方",
    "credit_limit_wan": "授信额度",
    "template_name": "模板名称",
    "spot_name": "现货名称",
    "buy_dt": "买入日期",
    "buy_price": "买入价格",
    "match_dt": "匹配日期",
    "matched_qty": "匹配数量",
    "total_pnl": "合计盈亏",
}

TABLE_LABEL_COLUMNS = {
    "strategy_group": ["group_name", "underlying", "group_id"],
    "structure": ["name", "structure_code", "underlying", "kind", "start_date", "end_date", "structure_id"],
    "price": ["dt", "underlying", "settle"],
    "close_trade": ["dt", "group_id", "underlying", "side", "qty"],
    "close_trade2": ["dt", "structure_id", "underlying", "side", "qty", "close_price", "pnl"],
    "app_kv": ["k", "updated_at"],
    "risk_credit_limit": ["risk_party", "credit_limit_wan"],
    "structure_template": ["template_name", "underlying", "kind", "template_id"],
    "spot_position_lot": ["spot_name", "buy_dt", "qty", "buy_price", "lot_id"],
    "spot_hedge_match_log": ["match_dt", "spot_name", "matched_qty", "total_pnl", "match_id"],
}


def _emit_progress(progress_callback: ProgressCallback | None, **event: Any) -> None:
    if progress_callback is None:
        return
    try:
        progress_callback(dict(event))
    except Exception:
        return


def _set_pg_transaction_timeouts(pg_conn: Any) -> None:
    pg_conn.execute(text(f"SET LOCAL statement_timeout = '{PG_SYNC_STATEMENT_TIMEOUT}'"))
    pg_conn.execute(text(f"SET LOCAL lock_timeout = '{PG_SYNC_LOCK_TIMEOUT}'"))


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


def pg_type_to_sqlite(data_type: str, udt_name: str = "") -> str:
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
    if isinstance(value, memoryview):
        return bytes(value)
    return value


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


def sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        LIMIT 1
        """,
        (table,),
    ).fetchone()
    return row is not None


def sqlite_table_info(conn: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    return list(conn.execute(f"PRAGMA table_info({quote_ident(table)})").fetchall())


def sqlite_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row["name"]) for row in sqlite_table_info(conn, table)]


def sqlite_pk_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    info = sqlite_table_info(conn, table)
    return [
        str(row["name"])
        for row in sorted(info, key=lambda item: int(item["pk"] or 0))
        if int(row["pk"] or 0)
    ]


def sqlite_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {quote_ident(table)}").fetchone()[0])


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


def pg_table_exists(pg_conn: Any, table: str) -> bool:
    row = pg_conn.execute(
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
    return row is not None


def pg_columns(pg_conn: Any, table: str) -> list[str]:
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


def pg_column_info(pg_conn: Any, table: str) -> list[dict[str, str]]:
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
        {"name": str(row[0]), "data_type": str(row[1] or ""), "udt_name": str(row[2] or "")}
        for row in rows
    ]


def pg_pk_columns(pg_conn: Any, table: str) -> list[str]:
    rows = pg_conn.execute(
        text(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
             AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = current_schema()
              AND tc.table_name = :table
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
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
        raise RuntimeError(f"SQLite 表 {table!r} 没有字段信息。")
    pk_cols = sqlite_pk_columns(sqlite_conn, table)
    column_lines: list[str] = []
    for row in info:
        col = str(row["name"])
        constraints = [quote_ident(col), sqlite_type_to_pg(row["type"])]
        if int(row["notnull"] or 0) and col not in pk_cols:
            constraints.append("NOT NULL")
        column_lines.append(" ".join(constraints))
    if pk_cols:
        column_lines.append("PRIMARY KEY (" + ", ".join(quote_ident(col) for col in pk_cols) + ")")
    ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} (\n    " + ",\n    ".join(column_lines) + "\n)"
    pg_conn.execute(text(ddl))


def ensure_pg_table_for_sqlite(pg_conn: Any, sqlite_conn: sqlite3.Connection, table: str) -> list[str]:
    if not pg_table_exists(pg_conn, table):
        create_pg_table_from_sqlite(pg_conn, sqlite_conn, table)
    existing = set(pg_columns(pg_conn, table))
    added: list[str] = []
    for row in sqlite_table_info(sqlite_conn, table):
        col = str(row["name"])
        if col in existing:
            continue
        pg_conn.execute(
            text(
                f"ALTER TABLE {quote_ident(table)} "
                f"ADD COLUMN IF NOT EXISTS {quote_ident(col)} {sqlite_type_to_pg(row['type'])}"
            )
        )
        added.append(col)
    return added


def create_sqlite_table_from_pg(sqlite_conn: sqlite3.Connection, pg_conn: Any, table: str) -> None:
    columns = pg_column_info(pg_conn, table)
    if not columns:
        raise RuntimeError(f"PostgreSQL 表 {table!r} 没有字段信息。")
    pk_cols = pg_pk_columns(pg_conn, table)
    column_lines = [
        f"{quote_ident(col['name'])} {pg_type_to_sqlite(col['data_type'], col['udt_name'])}"
        for col in columns
    ]
    if pk_cols:
        column_lines.append("PRIMARY KEY (" + ", ".join(quote_ident(col) for col in pk_cols) + ")")
    ddl = f"CREATE TABLE IF NOT EXISTS {quote_ident(table)} (\n    " + ",\n    ".join(column_lines) + "\n)"
    sqlite_conn.execute(ddl)


def ensure_sqlite_table_for_pg(sqlite_conn: sqlite3.Connection, pg_conn: Any, table: str) -> list[str]:
    if not sqlite_table_exists(sqlite_conn, table):
        create_sqlite_table_from_pg(sqlite_conn, pg_conn, table)
    existing = set(sqlite_columns(sqlite_conn, table))
    added: list[str] = []
    for col in pg_column_info(pg_conn, table):
        name = str(col["name"])
        if name in existing:
            continue
        sqlite_conn.execute(
            f"ALTER TABLE {quote_ident(table)} "
            f"ADD COLUMN {quote_ident(name)} {pg_type_to_sqlite(col['data_type'], col['udt_name'])}"
        )
        added.append(name)
    return added


def sqlite_backup_path(sqlite_db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return sqlite_db_path.with_name(f"{sqlite_db_path.stem}.before_cloud_sync_{stamp}{sqlite_db_path.suffix}")


def backup_sqlite_database(sqlite_conn: sqlite3.Connection, sqlite_db_path: Path) -> Path:
    backup_path = sqlite_backup_path(sqlite_db_path)
    with sqlite3.connect(str(backup_path)) as backup_conn:
        sqlite_conn.backup(backup_conn)
    return backup_path


def _pg_insert_sql(table: str, columns: list[str], pk_cols: list[str], conflict_action: str, pg_pk_cols: list[str]) -> str:
    quoted_columns = ", ".join(quote_ident(col) for col in columns)
    params = ", ".join(f":p{idx}" for idx, _ in enumerate(columns))
    base = f"INSERT INTO {quote_ident(table)} ({quoted_columns}) VALUES ({params})"
    if conflict_action == "update" and pk_cols and [col for col in pk_cols] == [col for col in pg_pk_cols]:
        update_cols = [col for col in columns if col not in set(pk_cols)]
        if update_cols:
            assignments = ", ".join(f"{quote_ident(col)} = EXCLUDED.{quote_ident(col)}" for col in update_cols)
            target = ", ".join(quote_ident(col) for col in pk_cols)
            return f"{base} ON CONFLICT ({target}) DO UPDATE SET {assignments}"
    return f"{base} ON CONFLICT DO NOTHING"


def _sqlite_insert_sql(table: str, columns: list[str], pk_cols: list[str], conflict_action: str) -> str:
    quoted_columns = ", ".join(quote_ident(col) for col in columns)
    placeholders = ", ".join("?" for _ in columns)
    base = f"INSERT INTO {quote_ident(table)} ({quoted_columns}) VALUES ({placeholders})"
    if not pk_cols:
        return base
    target = ", ".join(quote_ident(col) for col in pk_cols)
    if conflict_action == "update":
        update_cols = [col for col in columns if col not in set(pk_cols)]
        if update_cols:
            assignments = ", ".join(f"{quote_ident(col)} = excluded.{quote_ident(col)}" for col in update_cols)
            return f"{base} ON CONFLICT ({target}) DO UPDATE SET {assignments}"
    return f"{base} ON CONFLICT ({target}) DO NOTHING"


def business_table_name(table: str) -> str:
    return TABLE_BUSINESS_NAMES.get(str(table), str(table))


def business_column_name(column: str) -> str:
    return COLUMN_BUSINESS_NAMES.get(str(column), str(column))


def _normalize_compare_value(value: Any) -> Any:
    value = normalize_sqlite_value(value)
    if isinstance(value, float) and value != value:
        return None
    return value


def _short_value(value: Any, max_len: int = 48) -> str:
    if value is None:
        return "空"
    text = str(value)
    if len(text) > max_len:
        return text[: max_len - 1] + "..."
    return text


def _row_mapping(row: Any, columns: list[str]) -> dict[str, Any]:
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return {col: mapping.get(col) for col in columns}
    if isinstance(row, sqlite3.Row):
        return {col: row[col] for col in columns}
    if isinstance(row, dict):
        return {col: row.get(col) for col in columns}
    return {col: row[idx] for idx, col in enumerate(columns)}


def _record_key(row: dict[str, Any], pk_cols: list[str]) -> tuple[Any, ...]:
    return tuple(_normalize_compare_value(row.get(col)) for col in pk_cols)


def _compare_row_values(source_row: dict[str, Any], target_row: dict[str, Any], columns: list[str]) -> list[str]:
    changed: list[str] = []
    for col in columns:
        if _normalize_compare_value(source_row.get(col)) != _normalize_compare_value(target_row.get(col)):
            changed.append(col)
    return changed


def _record_label(table: str, row: dict[str, Any], pk_cols: list[str], columns: list[str]) -> str:
    preferred = TABLE_LABEL_COLUMNS.get(table, []) + pk_cols + columns[:4]
    seen: set[str] = set()
    parts: list[str] = []
    for col in preferred:
        if col in seen or col not in row:
            continue
        seen.add(col)
        value = row.get(col)
        if value is None or value == "":
            continue
        parts.append(f"{business_column_name(col)}={_short_value(value)}")
        if len(parts) >= 4:
            break
    if parts:
        return "，".join(parts)
    if pk_cols:
        return "主键=" + "/".join(_short_value(row.get(col)) for col in pk_cols)
    return "无法生成业务标识"


def _sqlite_rows_by_key(
    sqlite_conn: sqlite3.Connection,
    table: str,
    columns: list[str],
    pk_cols: list[str],
) -> dict[tuple[Any, ...], dict[str, Any]]:
    select_sql = f"SELECT {', '.join(quote_ident(col) for col in columns)} FROM {quote_ident(table)}"
    rows = sqlite_conn.execute(select_sql).fetchall()
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        row_map = _row_mapping(row, columns)
        result[_record_key(row_map, pk_cols)] = row_map
    return result


def _pg_rows_by_key(
    pg_conn: Any,
    table: str,
    columns: list[str],
    pk_cols: list[str],
) -> dict[tuple[Any, ...], dict[str, Any]]:
    select_sql = text(f"SELECT {', '.join(quote_ident(col) for col in columns)} FROM {quote_ident(table)}")
    rows = pg_conn.execute(select_sql).fetchall()
    result: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        row_map = _row_mapping(row, columns)
        result[_record_key(row_map, pk_cols)] = row_map
    return result


def _empty_table_diff(
    table: str,
    source_rows: int = 0,
    target_rows: int = 0,
    status: str = "ok",
    note: str = "",
) -> dict[str, Any]:
    return {
        "table": table,
        "business_name": business_table_name(table),
        "source_rows": int(source_rows),
        "target_rows": int(target_rows),
        "new_rows": 0,
        "changed_rows": 0,
        "target_only_rows": 0,
        "same_rows": 0,
        "status": status,
        "note": note,
        "pk_cols": [],
        "columns": [],
        "new_keys": [],
        "changed_keys": [],
        "new_examples": [],
        "changed_examples": [],
        "target_only_examples": [],
    }


def _compare_pk_table(
    *,
    table: str,
    columns: list[str],
    pk_cols: list[str],
    source_rows: dict[tuple[Any, ...], dict[str, Any]],
    target_rows: dict[tuple[Any, ...], dict[str, Any]],
) -> dict[str, Any]:
    source_keys = set(source_rows)
    target_keys = set(target_rows)
    new_keys = sorted(source_keys - target_keys, key=lambda item: tuple(str(part) for part in item))
    target_only_keys = sorted(target_keys - source_keys, key=lambda item: tuple(str(part) for part in item))
    common_keys = sorted(source_keys & target_keys, key=lambda item: tuple(str(part) for part in item))
    compare_columns = [col for col in columns if col not in set(pk_cols)]
    changed_examples: list[dict[str, Any]] = []
    changed_keys: list[tuple[Any, ...]] = []
    changed_rows = 0
    same_rows = 0
    for key in common_keys:
        changed_cols = _compare_row_values(source_rows[key], target_rows[key], compare_columns)
        if changed_cols:
            changed_rows += 1
            changed_keys.append(key)
            if len(changed_examples) < DIFF_EXAMPLE_LIMIT:
                changed_examples.append(
                    {
                        "record": _record_label(table, source_rows[key], pk_cols, columns),
                        "changed_fields": "、".join(business_column_name(col) for col in changed_cols[:8]),
                    }
                )
        else:
            same_rows += 1
    return {
        "table": table,
        "business_name": business_table_name(table),
        "source_rows": len(source_rows),
        "target_rows": len(target_rows),
        "new_rows": len(new_keys),
        "changed_rows": changed_rows,
        "target_only_rows": len(target_only_keys),
        "same_rows": same_rows,
        "status": "ok",
        "note": "",
        "pk_cols": list(pk_cols),
        "columns": list(columns),
        "new_keys": [list(key) for key in new_keys],
        "changed_keys": [list(key) for key in changed_keys],
        "new_examples": [
            {"record": _record_label(table, source_rows[key], pk_cols, columns)}
            for key in new_keys[:DIFF_EXAMPLE_LIMIT]
        ],
        "changed_examples": changed_examples,
        "target_only_examples": [
            {"record": _record_label(table, target_rows[key], pk_cols, columns)}
            for key in target_only_keys[:DIFF_EXAMPLE_LIMIT]
        ],
    }


def _chunked(items: list[Any], size: int) -> list[list[Any]]:
    if size <= 0:
        size = 1
    return [items[idx : idx + size] for idx in range(0, len(items), size)]


def _normalize_key_tuple(raw_key: Any) -> tuple[Any, ...]:
    if isinstance(raw_key, tuple):
        return tuple(_normalize_compare_value(value) for value in raw_key)
    if isinstance(raw_key, list):
        return tuple(_normalize_compare_value(value) for value in raw_key)
    return (_normalize_compare_value(raw_key),)


def _diff_tables_by_name(diff_report: Mapping[str, Any] | None, direction: str) -> dict[str, Mapping[str, Any]] | None:
    if diff_report is None:
        return None
    if str(diff_report.get("direction") or "") != direction:
        raise ValueError("差异报告方向与当前同步方向不一致，请重新检测差异。")
    tables = {}
    for row in list(diff_report.get("tables") or []):
        table = str(row.get("table") or "")
        if table:
            tables[table] = row
    return tables


def _planned_keys_from_diff(table_diff: Mapping[str, Any] | None, conflict_action: str) -> list[tuple[Any, ...]] | None:
    if table_diff is None:
        return None
    keys = [_normalize_key_tuple(key) for key in list(table_diff.get("new_keys") or [])]
    if conflict_action == "update":
        keys.extend(_normalize_key_tuple(key) for key in list(table_diff.get("changed_keys") or []))
    return keys


def _diff_table_needs_sync(table_diff: Mapping[str, Any], conflict_action: str) -> bool:
    if table_diff.get("status") == "failed":
        return False
    keys = _planned_keys_from_diff(table_diff, conflict_action)
    if keys:
        return True
    return int(table_diff.get("new_rows") or 0) > 0 and int(table_diff.get("target_rows") or 0) <= 0


def _sqlite_rows_for_keys(
    sqlite_conn: sqlite3.Connection,
    table: str,
    columns: list[str],
    pk_cols: list[str],
    keys: list[tuple[Any, ...]],
) -> list[sqlite3.Row]:
    if not keys:
        return []
    clauses: list[str] = []
    params: list[Any] = []
    for key in keys:
        parts: list[str] = []
        for col, value in zip(pk_cols, key):
            if value is None:
                parts.append(f"{quote_ident(col)} IS NULL")
            else:
                parts.append(f"{quote_ident(col)} = ?")
                params.append(normalize_sqlite_value(value))
        clauses.append("(" + " AND ".join(parts) + ")")
    sql = (
        f"SELECT {', '.join(quote_ident(col) for col in columns)} "
        f"FROM {quote_ident(table)} WHERE " + " OR ".join(clauses)
    )
    return list(sqlite_conn.execute(sql, params).fetchall())


def _pg_rows_for_keys(
    pg_conn: Any,
    table: str,
    columns: list[str],
    pk_cols: list[str],
    keys: list[tuple[Any, ...]],
) -> list[Any]:
    if not keys:
        return []
    clauses: list[str] = []
    params: dict[str, Any] = {}
    for key_idx, key in enumerate(keys):
        parts: list[str] = []
        for col_idx, (col, value) in enumerate(zip(pk_cols, key)):
            if value is None:
                parts.append(f"{quote_ident(col)} IS NULL")
            else:
                param_name = f"k{key_idx}_{col_idx}"
                parts.append(f"{quote_ident(col)} = :{param_name}")
                params[param_name] = normalize_sqlite_value(value)
        clauses.append("(" + " AND ".join(parts) + ")")
    sql = (
        f"SELECT {', '.join(quote_ident(col) for col in columns)} "
        f"FROM {quote_ident(table)} WHERE " + " OR ".join(clauses)
    )
    return list(pg_conn.execute(text(sql), params).fetchall())


def preview_sync_diff(
    sqlite_db_path: str | Path,
    *,
    direction: str,
    require_postgres_backend: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    if direction not in {"sqlite_to_postgres", "postgres_to_sqlite"}:
        raise ValueError("direction 只能是 sqlite_to_postgres 或 postgres_to_sqlite")
    sqlite_path = Path(sqlite_db_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"未找到 SQLite 数据库：{sqlite_path}")

    _emit_progress(progress_callback, phase="connect", message="正在连接 Neon PostgreSQL")
    engine = get_pg_engine(require_postgres_backend=require_postgres_backend)
    table_results: list[dict[str, Any]] = []
    source_name = "本地 SQLite" if direction == "sqlite_to_postgres" else "Neon 云端"
    target_name = "Neon 云端" if direction == "sqlite_to_postgres" else "本地 SQLite"

    with sqlite3.connect(str(sqlite_path)) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        with engine.connect() as pg_conn:
            sqlite_tables = set(sqlite_business_tables(sqlite_conn))
            pg_tables = set(pg_business_tables(pg_conn))
            tables = sorted(sqlite_tables if direction == "sqlite_to_postgres" else pg_tables)
            total_tables = len(tables)
            _emit_progress(
                progress_callback,
                phase="tables",
                message=f"正在检测 {total_tables} 张业务表差异",
                total_tables=total_tables,
            )
            for table_index, table in enumerate(tables, start=1):
                _emit_progress(
                    progress_callback,
                    phase="table_start",
                    table=table,
                    table_index=table_index,
                    total_tables=total_tables,
                    message=f"正在检测差异 {table_index}/{total_tables}: {table}",
                )
                try:
                    sqlite_exists = table in sqlite_tables
                    pg_exists = table in pg_tables
                    sqlite_row_count = sqlite_count(sqlite_conn, table) if sqlite_exists else 0
                    pg_row_count = pg_count(pg_conn, table) if pg_exists else 0
                    source_count = sqlite_row_count if direction == "sqlite_to_postgres" else pg_row_count
                    target_count = pg_row_count if direction == "sqlite_to_postgres" else sqlite_row_count
                    if source_count <= 0:
                        result = _empty_table_diff(table, source_count, target_count, status="skipped", note="来源为空，不会同步。")
                        table_results.append(result)
                        continue
                    if direction == "sqlite_to_postgres" and not pg_exists:
                        result = _empty_table_diff(table, source_count, 0, note="云端还没有这张表，同步时会先建表再新增。")
                        result["new_rows"] = source_count
                        table_results.append(result)
                        continue
                    if direction == "postgres_to_sqlite" and not sqlite_exists:
                        result = _empty_table_diff(table, source_count, 0, note="本地还没有这张表，同步时会先建表再新增。")
                        result["new_rows"] = source_count
                        table_results.append(result)
                        continue

                    sqlite_cols = sqlite_columns(sqlite_conn, table)
                    pg_cols = pg_columns(pg_conn, table)
                    if direction == "sqlite_to_postgres":
                        columns = [col for col in sqlite_cols if col in set(pg_cols)]
                        pk_cols = [col for col in sqlite_pk_columns(sqlite_conn, table) if col in columns]
                        source_pk = pk_cols
                        target_pk = [col for col in pg_pk_columns(pg_conn, table) if col in columns]
                    else:
                        columns = [col for col in pg_cols if col in set(sqlite_cols)]
                        pk_cols = [col for col in sqlite_pk_columns(sqlite_conn, table) if col in columns]
                        source_pk = [col for col in pg_pk_columns(pg_conn, table) if col in columns]
                        target_pk = pk_cols
                    if not columns:
                        table_results.append(
                            _empty_table_diff(
                                table,
                                source_count,
                                target_count,
                                status="failed",
                                note="两边没有共同字段，无法判断差异。",
                            )
                        )
                        continue
                    if not pk_cols or source_pk != target_pk:
                        result = _empty_table_diff(
                            table,
                            source_count,
                            target_count,
                            status="limited",
                            note="主键缺失或两边主键不一致，无法逐条判断差异；目标已有数据时同步会跳过，避免重复。",
                        )
                        if target_count <= 0:
                            result["new_rows"] = source_count
                            result["note"] = "目标为空，虽然无法逐条比较，但同步时会按来源新增。"
                        table_results.append(result)
                        continue
                    source_rows = (
                        _sqlite_rows_by_key(sqlite_conn, table, columns, pk_cols)
                        if direction == "sqlite_to_postgres"
                        else _pg_rows_by_key(pg_conn, table, columns, pk_cols)
                    )
                    target_rows = (
                        _pg_rows_by_key(pg_conn, table, columns, pk_cols)
                        if direction == "sqlite_to_postgres"
                        else _sqlite_rows_by_key(sqlite_conn, table, columns, pk_cols)
                    )
                    result = _compare_pk_table(
                        table=table,
                        columns=columns,
                        pk_cols=pk_cols,
                        source_rows=source_rows,
                        target_rows=target_rows,
                    )
                    table_results.append(result)
                except Exception as exc:
                    table_results.append(
                        _empty_table_diff(
                            table,
                            0,
                            0,
                            status="failed",
                            note=f"{type(exc).__name__}: {exc}",
                        )
                    )
                _emit_progress(
                    progress_callback,
                    phase="table_done",
                    table=table,
                    table_index=table_index,
                    total_tables=total_tables,
                    message=f"差异检测完成：{table}",
                )
    totals = {
        "new_rows": sum(int(row.get("new_rows") or 0) for row in table_results),
        "changed_rows": sum(int(row.get("changed_rows") or 0) for row in table_results),
        "target_only_rows": sum(int(row.get("target_only_rows") or 0) for row in table_results),
        "failed_tables": [row["table"] for row in table_results if row.get("status") == "failed"],
        "limited_tables": [row["table"] for row in table_results if row.get("status") == "limited"],
    }
    _emit_progress(progress_callback, phase="done", message="差异检测完成", total_tables=len(table_results))
    return {
        "direction": direction,
        "source_name": source_name,
        "target_name": target_name,
        "tables": table_results,
        "totals": totals,
    }


def sync_sqlite_to_postgres(
    sqlite_db_path: str | Path,
    *,
    conflict_action: str = "update",
    require_postgres_backend: bool = False,
    diff_report: Mapping[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    sqlite_path = Path(sqlite_db_path)
    if not sqlite_path.exists():
        raise FileNotFoundError(f"未找到 SQLite 数据库：{sqlite_path}")
    if conflict_action not in {"update", "skip"}:
        raise ValueError("conflict_action 只能是 update 或 skip")

    _emit_progress(progress_callback, phase="init", message="正在初始化 PostgreSQL 表结构")
    init_pg_db(require_postgres_backend=require_postgres_backend, run_optional=False)
    _emit_progress(progress_callback, phase="connect", message="正在连接 Neon PostgreSQL")
    engine = get_pg_engine(require_postgres_backend=require_postgres_backend)
    diff_tables = _diff_tables_by_name(diff_report, "sqlite_to_postgres")
    table_results: list[dict[str, Any]] = []
    with sqlite3.connect(str(sqlite_path)) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        tables = sqlite_business_tables(sqlite_conn)
        if diff_tables is not None:
            tables = [
                table for table in tables
                if table in diff_tables and _diff_table_needs_sync(diff_tables[table], conflict_action)
            ]
        total_tables = len(tables)
        _emit_progress(progress_callback, phase="tables", message=f"发现 {total_tables} 张 SQLite 业务表", total_tables=total_tables)
        for table_index, table in enumerate(tables, start=1):
            result: dict[str, Any] = {
                "table": table,
                "source_rows": 0,
                "processed_rows": 0,
                "target_before": 0,
                "target_after": 0,
                "status": "ok",
                "note": "",
            }
            try:
                table_diff = diff_tables.get(table) if diff_tables is not None else None
                _emit_progress(
                    progress_callback,
                    phase="table_start",
                    direction="sqlite_to_postgres",
                    table=table,
                    table_index=table_index,
                    total_tables=total_tables,
                    message=f"正在处理表 {table_index}/{total_tables}: {table}",
                )
                source_count = sqlite_count(sqlite_conn, table)
                result["source_rows"] = source_count
                _emit_progress(
                    progress_callback,
                    phase="table_count",
                    direction="sqlite_to_postgres",
                    table=table,
                    table_index=table_index,
                    total_tables=total_tables,
                    source_rows=source_count,
                    processed_rows=0,
                    message=f"表 {table}: SQLite 行数 {source_count}",
                )
                if source_count <= 0:
                    result["status"] = "skipped"
                    result["note"] = "空表跳过"
                    table_results.append(result)
                    _emit_progress(
                        progress_callback,
                        phase="table_done",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=0,
                        status="skipped",
                        message=f"表 {table} 是空表，已跳过",
                    )
                    continue
                with engine.begin() as pg_conn:
                    _set_pg_transaction_timeouts(pg_conn)
                    _emit_progress(
                        progress_callback,
                        phase="target_count",
                        direction="sqlite_to_postgres",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=0,
                        message=f"表 {table}: 正在检查 Neon 目标表",
                    )
                    target_before = pg_count(pg_conn, table) if pg_table_exists(pg_conn, table) else 0
                    result["target_before"] = target_before
                    _emit_progress(
                        progress_callback,
                        phase="schema",
                        direction="sqlite_to_postgres",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=0,
                        message=f"表 {table}: 正在对齐字段结构",
                    )
                    added = ensure_pg_table_for_sqlite(pg_conn, sqlite_conn, table)
                    if added:
                        result["note"] = f"补充字段：{', '.join(added)}"
                    pg_cols = set(pg_columns(pg_conn, table))
                    columns = [col for col in sqlite_columns(sqlite_conn, table) if col in pg_cols]
                    if not columns:
                        raise RuntimeError("SQLite/PostgreSQL 没有共同字段。")
                    pk_cols = [col for col in sqlite_pk_columns(sqlite_conn, table) if col in columns]
                    pg_pk_cols = [col for col in pg_pk_columns(pg_conn, table) if col in columns]
                    planned_keys = _planned_keys_from_diff(table_diff, conflict_action)
                    if diff_tables is not None:
                        if table_diff is None:
                            result["status"] = "skipped"
                            result["note"] = "差异报告中没有这张表，已跳过。"
                            result["target_after"] = target_before
                            table_results.append(result)
                            continue
                        if table_diff.get("status") == "failed":
                            result["status"] = "failed"
                            result["note"] = "差异检测失败，已阻止同步。"
                            result["target_after"] = target_before
                            table_results.append(result)
                            continue
                        if planned_keys is not None and not planned_keys:
                            if int(table_diff.get("new_rows") or 0) > 0 and target_before <= 0:
                                planned_keys = None
                            else:
                                result["status"] = "skipped"
                                result["note"] = "差异检测未发现需要写入云端的新增或变更记录。"
                                result["target_after"] = target_before
                                table_results.append(result)
                                _emit_progress(
                                    progress_callback,
                                    phase="table_done",
                                    table=table,
                                    table_index=table_index,
                                    total_tables=total_tables,
                                    source_rows=0,
                                    processed_rows=0,
                                    status="skipped",
                                    message=f"表 {table} 没有需要写入云端的差异，已跳过",
                                )
                                continue
                        if planned_keys is not None:
                            result["source_total_rows"] = source_count
                            source_count = len(planned_keys)
                            result["source_rows"] = source_count
                    if not pk_cols and target_before > 0:
                        result["status"] = "skipped"
                        result["note"] = "来源表没有主键且云端表已有数据，为避免重复已跳过。"
                        result["target_after"] = target_before
                        table_results.append(result)
                        _emit_progress(
                            progress_callback,
                            phase="table_done",
                            table=table,
                            table_index=table_index,
                            total_tables=total_tables,
                            source_rows=source_count,
                            processed_rows=0,
                            status="skipped",
                            message=f"表 {table} 无主键且目标已有数据，已跳过",
                        )
                        continue
                    insert_sql = text(_pg_insert_sql(table, columns, pk_cols, conflict_action, pg_pk_cols))
                    processed = 0
                    _emit_progress(
                        progress_callback,
                        phase="write",
                        direction="sqlite_to_postgres",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=processed,
                        message=f"表 {table}: 开始写入 Neon",
                    )
                    if planned_keys is None:
                        cursor = sqlite_conn.execute(
                            f"SELECT {', '.join(quote_ident(col) for col in columns)} FROM {quote_ident(table)}"
                        )
                        batch_iter = iter(lambda: cursor.fetchmany(BATCH_SIZE), [])
                    else:
                        key_batches = _chunked(planned_keys, KEY_SELECT_BATCH_SIZE)
                        batch_iter = (
                            _sqlite_rows_for_keys(sqlite_conn, table, columns, pk_cols, key_batch)
                            for key_batch in key_batches
                        )
                    for batch in batch_iter:
                        if not batch:
                            continue
                        rows = [
                            {f"p{idx}": row[col] for idx, col in enumerate(columns)}
                            for row in batch
                        ]
                        pg_conn.execute(insert_sql, rows)
                        processed += len(rows)
                        _emit_progress(
                            progress_callback,
                            phase="batch",
                            direction="sqlite_to_postgres",
                            table=table,
                            table_index=table_index,
                            total_tables=total_tables,
                            source_rows=source_count,
                            processed_rows=processed,
                            message=f"表 {table}: 已处理 {processed}/{source_count} 行",
                        )
                    result["processed_rows"] = processed
                    result["target_after"] = pg_count(pg_conn, table)
                    if conflict_action == "update" and pk_cols != pg_pk_cols:
                        result["note"] = (str(result.get("note") or "") + " 主键不一致，重复记录已跳过。").strip()
            except Exception as exc:
                result["status"] = "failed"
                result["note"] = f"{type(exc).__name__}: {exc}"
                _emit_progress(
                    progress_callback,
                    phase="table_failed",
                    table=table,
                    table_index=table_index,
                    total_tables=total_tables,
                    source_rows=result.get("source_rows"),
                    processed_rows=result.get("processed_rows"),
                    status="failed",
                    message=f"表 {table} 同步失败：{type(exc).__name__}",
                )
            table_results.append(result)
            if result.get("status") != "failed":
                _emit_progress(
                    progress_callback,
                    phase="table_done",
                    table=table,
                    table_index=table_index,
                    total_tables=total_tables,
                    source_rows=result.get("source_rows"),
                    processed_rows=result.get("processed_rows"),
                    status=result.get("status"),
                    message=f"表 {table} 处理完成",
                )
    _emit_progress(progress_callback, phase="done", message="SQLite 到 Neon 同步完成", total_tables=len(table_results))
    return {
        "direction": "sqlite_to_postgres",
        "conflict_action": conflict_action,
        "tables": table_results,
        "failed_tables": [row["table"] for row in table_results if row["status"] == "failed"],
        "processed_rows": sum(int(row.get("processed_rows") or 0) for row in table_results),
    }


def sync_postgres_to_sqlite(
    sqlite_db_path: str | Path,
    *,
    conflict_action: str = "update",
    require_postgres_backend: bool = False,
    create_backup: bool = True,
    diff_report: Mapping[str, Any] | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, Any]:
    sqlite_path = Path(sqlite_db_path)
    if conflict_action not in {"update", "skip"}:
        raise ValueError("conflict_action 只能是 update 或 skip")
    _emit_progress(progress_callback, phase="init", message="正在初始化 PostgreSQL 表结构")
    init_pg_db(require_postgres_backend=require_postgres_backend, run_optional=False)
    _emit_progress(progress_callback, phase="connect", message="正在连接 Neon PostgreSQL")
    engine = get_pg_engine(require_postgres_backend=require_postgres_backend)
    diff_tables = _diff_tables_by_name(diff_report, "postgres_to_sqlite")
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    table_results: list[dict[str, Any]] = []
    backup_path: Path | None = None
    had_sqlite_file = sqlite_path.exists()
    with sqlite3.connect(str(sqlite_path)) as sqlite_conn:
        sqlite_conn.row_factory = sqlite3.Row
        if create_backup and had_sqlite_file:
            _emit_progress(progress_callback, phase="backup", message="正在生成本地 SQLite 同步前备份")
            backup_path = backup_sqlite_database(sqlite_conn, sqlite_path)
        with engine.connect() as pg_conn:
            tables = pg_business_tables(pg_conn)
            if diff_tables is not None:
                tables = [
                    table for table in tables
                    if table in diff_tables and _diff_table_needs_sync(diff_tables[table], conflict_action)
                ]
            total_tables = len(tables)
            _emit_progress(progress_callback, phase="tables", message=f"发现 {total_tables} 张 PostgreSQL 业务表", total_tables=total_tables)
            for table_index, table in enumerate(tables, start=1):
                result: dict[str, Any] = {
                    "table": table,
                    "source_rows": 0,
                    "processed_rows": 0,
                    "target_before": 0,
                    "target_after": 0,
                    "status": "ok",
                    "note": "",
                }
                try:
                    table_diff = diff_tables.get(table) if diff_tables is not None else None
                    _emit_progress(
                        progress_callback,
                        phase="table_start",
                        direction="postgres_to_sqlite",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        message=f"正在处理表 {table_index}/{total_tables}: {table}",
                    )
                    source_count = pg_count(pg_conn, table)
                    result["source_rows"] = source_count
                    _emit_progress(
                        progress_callback,
                        phase="table_count",
                        direction="postgres_to_sqlite",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=0,
                        message=f"表 {table}: Neon 行数 {source_count}",
                    )
                    if source_count <= 0:
                        result["status"] = "skipped"
                        result["note"] = "空表跳过"
                        table_results.append(result)
                        _emit_progress(
                            progress_callback,
                            phase="table_done",
                            table=table,
                            table_index=table_index,
                            total_tables=total_tables,
                            source_rows=source_count,
                            processed_rows=0,
                            status="skipped",
                            message=f"表 {table} 是空表，已跳过",
                        )
                        continue
                    _emit_progress(
                        progress_callback,
                        phase="target_count",
                        direction="postgres_to_sqlite",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=0,
                        message=f"表 {table}: 正在检查本地 SQLite 目标表",
                    )
                    target_before = sqlite_count(sqlite_conn, table) if sqlite_table_exists(sqlite_conn, table) else 0
                    result["target_before"] = target_before
                    _emit_progress(
                        progress_callback,
                        phase="schema",
                        direction="postgres_to_sqlite",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=0,
                        message=f"表 {table}: 正在对齐字段结构",
                    )
                    added = ensure_sqlite_table_for_pg(sqlite_conn, pg_conn, table)
                    if added:
                        result["note"] = f"补充字段：{', '.join(added)}"
                    sqlite_cols = set(sqlite_columns(sqlite_conn, table))
                    columns = [col for col in pg_columns(pg_conn, table) if col in sqlite_cols]
                    if not columns:
                        raise RuntimeError("PostgreSQL/SQLite 没有共同字段。")
                    pk_cols = [col for col in sqlite_pk_columns(sqlite_conn, table) if col in columns]
                    planned_keys = _planned_keys_from_diff(table_diff, conflict_action)
                    if diff_tables is not None:
                        if table_diff is None:
                            result["status"] = "skipped"
                            result["note"] = "差异报告中没有这张表，已跳过。"
                            result["target_after"] = target_before
                            table_results.append(result)
                            continue
                        if table_diff.get("status") == "failed":
                            result["status"] = "failed"
                            result["note"] = "差异检测失败，已阻止同步。"
                            result["target_after"] = target_before
                            table_results.append(result)
                            continue
                        if planned_keys is not None and not planned_keys:
                            if int(table_diff.get("new_rows") or 0) > 0 and target_before <= 0:
                                planned_keys = None
                            else:
                                result["status"] = "skipped"
                                result["note"] = "差异检测未发现需要写入本地的新增或变更记录。"
                                result["target_after"] = target_before
                                table_results.append(result)
                                _emit_progress(
                                    progress_callback,
                                    phase="table_done",
                                    table=table,
                                    table_index=table_index,
                                    total_tables=total_tables,
                                    source_rows=0,
                                    processed_rows=0,
                                    status="skipped",
                                    message=f"表 {table} 没有需要写入本地的差异，已跳过",
                                )
                                continue
                        if planned_keys is not None:
                            result["source_total_rows"] = source_count
                            source_count = len(planned_keys)
                            result["source_rows"] = source_count
                    if not pk_cols and target_before > 0:
                        result["status"] = "skipped"
                        result["note"] = "本地表没有主键且已有数据，为避免重复已跳过。"
                        table_results.append(result)
                        _emit_progress(
                            progress_callback,
                            phase="table_done",
                            table=table,
                            table_index=table_index,
                            total_tables=total_tables,
                            source_rows=source_count,
                            processed_rows=0,
                            status="skipped",
                            message=f"表 {table} 无主键且目标已有数据，已跳过",
                        )
                        continue
                    insert_sql = _sqlite_insert_sql(table, columns, pk_cols, conflict_action)
                    select_sql = text(
                        f"SELECT {', '.join(quote_ident(col) for col in columns)} FROM {quote_ident(table)}"
                    )
                    _emit_progress(
                        progress_callback,
                        phase="read",
                        direction="postgres_to_sqlite",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=source_count,
                        processed_rows=0,
                        message=f"表 {table}: 开始读取 Neon 并写入本地",
                    )
                    processed = 0
                    if planned_keys is None:
                        query_result = pg_conn.execute(select_sql)
                        batch_iter = iter(lambda: query_result.fetchmany(BATCH_SIZE), [])
                    else:
                        key_batches = _chunked(planned_keys, KEY_SELECT_BATCH_SIZE)
                        batch_iter = (
                            _pg_rows_for_keys(pg_conn, table, columns, pk_cols, key_batch)
                            for key_batch in key_batches
                        )
                    for batch in batch_iter:
                        if not batch:
                            continue
                        values = [
                            tuple(normalize_sqlite_value(value) for value in row)
                            for row in batch
                        ]
                        sqlite_conn.executemany(insert_sql, values)
                        processed += len(values)
                        _emit_progress(
                            progress_callback,
                            phase="batch",
                            direction="postgres_to_sqlite",
                            table=table,
                            table_index=table_index,
                            total_tables=total_tables,
                            source_rows=source_count,
                            processed_rows=processed,
                            message=f"表 {table}: 已处理 {processed}/{source_count} 行",
                        )
                    result["processed_rows"] = processed
                    result["target_after"] = sqlite_count(sqlite_conn, table)
                except Exception as exc:
                    result["status"] = "failed"
                    result["note"] = f"{type(exc).__name__}: {exc}"
                    _emit_progress(
                        progress_callback,
                        phase="table_failed",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=result.get("source_rows"),
                        processed_rows=result.get("processed_rows"),
                        status="failed",
                        message=f"表 {table} 同步失败：{type(exc).__name__}",
                    )
                table_results.append(result)
                if result.get("status") != "failed":
                    _emit_progress(
                        progress_callback,
                        phase="table_done",
                        table=table,
                        table_index=table_index,
                        total_tables=total_tables,
                        source_rows=result.get("source_rows"),
                        processed_rows=result.get("processed_rows"),
                        status=result.get("status"),
                        message=f"表 {table} 处理完成",
                    )
        sqlite_conn.commit()
    _emit_progress(progress_callback, phase="done", message="Neon 到 SQLite 同步完成", total_tables=len(table_results))
    return {
        "direction": "postgres_to_sqlite",
        "conflict_action": conflict_action,
        "backup_path": str(backup_path) if backup_path is not None else "",
        "tables": table_results,
        "failed_tables": [row["table"] for row in table_results if row["status"] == "failed"],
        "processed_rows": sum(int(row.get("processed_rows") or 0) for row in table_results),
    }
