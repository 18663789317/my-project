"""PostgreSQL helpers for the phased dual-database rollout."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

import streamlit as st

from db_config import get_db_backend


PROJECT_ROOT = Path(__file__).resolve().parent

PG_CORE_TABLES: tuple[str, ...] = (
    "strategy_group",
    "structure",
    "price",
    "close_trade",
    "close_trade2",
    "app_kv",
)

PG_BUSINESS_TABLES: tuple[str, ...] = (
    "strategy_group",
    "structure",
    "price",
    "trading_calendar_override",
    "close_trade",
    "close_trade2",
    "snowball_conversion",
    "close_revert_log",
    "structure_position_adjustment",
    "spot_position_lot",
    "spot_hedge_match_log",
    "spot_summary_hidden",
    "app_kv",
    "risk_credit_limit",
    "structure_template",
    "self_quote_multi_value_preset",
    "probexp_market_input",
    "probexp_calc_log",
    "precise_hedge_calc_log",
    "winrate_valuation_surface_cache",
)

SQLITE_TRIGGERS_SKIPPED_FOR_PG: tuple[str, ...] = (
    "trg_close_trade2_structure_ref_ins",
    "trg_close_trade2_structure_ref_upd",
    "trg_struct_pos_adj_structure_ref_ins",
    "trg_struct_pos_adj_structure_ref_upd",
    "trg_spot_match_lot_ref_ins",
    "trg_spot_match_lot_ref_upd",
    "trg_spot_match_structure_ref_ins",
    "trg_spot_match_structure_ref_upd",
    "trg_spot_lot_delete_restrict",
)

PG_DDL_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS strategy_group (
        group_id TEXT PRIMARY KEY,
        group_name TEXT NOT NULL,
        underlying TEXT NOT NULL DEFAULT 'I.DCE',
        is_hidden INTEGER DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS structure (
        structure_id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        structure_code TEXT,
        name TEXT NOT NULL,
        underlying TEXT NOT NULL,
        risk_party TEXT NOT NULL DEFAULT '海证资本',
        kind TEXT NOT NULL,
        strategy TEXT NOT NULL DEFAULT 'BASIC_RANGE',
        strategy_code TEXT,
        structure_type TEXT,
        customer_name TEXT DEFAULT '',
        counterparty TEXT DEFAULT '',
        contract_month TEXT DEFAULT '',
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        trade_date TEXT,
        expiry_date TEXT,
        base_qty_per_day DOUBLE PRECISION NOT NULL,
        entry_price DOUBLE PRECISION,
        strike_price DOUBLE PRECISION,
        barrier_in DOUBLE PRECISION,
        barrier_out DOUBLE PRECISION,
        knock_out_price DOUBLE PRECISION,
        ko_strike_price DOUBLE PRECISION,
        multiple DOUBLE PRECISION,
        option_type TEXT,
        side TEXT,
        premium DOUBLE PRECISION,
        note TEXT DEFAULT '',
        meta_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT '',
        barrier_price DOUBLE PRECISION,
        melt_price DOUBLE PRECISION,
        melt_strike DOUBLE PRECISION,
        gen_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        total_cap_qty DOUBLE PRECISION,
        daily_cap_qty DOUBLE PRECISION,
        params_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS price (
        dt TEXT NOT NULL,
        underlying TEXT NOT NULL,
        settle DOUBLE PRECISION NOT NULL,
        source TEXT DEFAULT 'manual',
        is_locked INTEGER DEFAULT 0,
        updated_at TEXT,
        PRIMARY KEY (dt, underlying)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trading_calendar_override (
        cal_date TEXT PRIMARY KEY,
        is_trading_day INTEGER NOT NULL,
        source TEXT NOT NULL DEFAULT 'manual',
        note TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS close_trade (
        dt TEXT NOT NULL,
        group_id TEXT NOT NULL,
        underlying TEXT NOT NULL,
        side TEXT NOT NULL,
        qty DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (dt, group_id, underlying, side, qty)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS close_trade2 (
        close_id TEXT PRIMARY KEY,
        dt TEXT NOT NULL,
        group_id TEXT NOT NULL,
        structure_id TEXT NOT NULL,
        underlying TEXT NOT NULL,
        side TEXT NOT NULL,
        qty DOUBLE PRECISION NOT NULL,
        open_price DOUBLE PRECISION,
        close_price DOUBLE PRECISION NOT NULL,
        pnl DOUBLE PRECISION NOT NULL,
        roll_target_underlying TEXT NOT NULL DEFAULT '',
        roll_target_price DOUBLE PRECISION,
        roll_spread_pnl DOUBLE PRECISION NOT NULL DEFAULT 0,
        close_category TEXT NOT NULL DEFAULT '结构平仓',
        quick_batch_id TEXT,
        source_gen_date TEXT,
        is_external INTEGER NOT NULL DEFAULT 0
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS snowball_conversion (
        conversion_id TEXT PRIMARY KEY,
        structure_id TEXT NOT NULL,
        group_id TEXT NOT NULL,
        underlying TEXT NOT NULL,
        kind TEXT NOT NULL,
        trigger_date TEXT NOT NULL,
        conversion_qty DOUBLE PRECISION NOT NULL,
        conversion_price DOUBLE PRECISION NOT NULL,
        notional_amount DOUBLE PRECISION NOT NULL DEFAULT 0,
        source_status TEXT NOT NULL DEFAULT '雪球折价转期货',
        source_calc_date TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL,
        CONSTRAINT uq_snowball_conversion_structure_trigger UNIQUE(structure_id, trigger_date)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS close_revert_log (
        log_id TEXT PRIMARY KEY,
        reverted_at TEXT NOT NULL,
        batch_id TEXT,
        close_id TEXT NOT NULL,
        payload_json TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS structure_position_adjustment (
        adjustment_id TEXT PRIMARY KEY,
        adjust_batch_id TEXT NOT NULL,
        group_id TEXT NOT NULL,
        structure_id TEXT NOT NULL,
        underlying TEXT NOT NULL DEFAULT '',
        adjust_dt TEXT NOT NULL,
        delta_qty DOUBLE PRECISION NOT NULL,
        before_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
        after_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
        basis_open_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        previous_basis_open_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        action_type TEXT NOT NULL DEFAULT 'INCREASE',
        revert_of_adjustment_id TEXT NOT NULL DEFAULT '',
        is_reverted INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spot_position_lot (
        lot_id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        spot_name TEXT NOT NULL,
        buy_dt TEXT NOT NULL,
        qty DOUBLE PRECISION NOT NULL,
        buy_price DOUBLE PRECISION NOT NULL,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        created_by TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spot_hedge_match_log (
        match_id TEXT PRIMARY KEY,
        group_id TEXT NOT NULL,
        match_dt TEXT NOT NULL,
        matched_at TEXT NOT NULL,
        matched_by TEXT NOT NULL DEFAULT '',
        spot_name TEXT NOT NULL,
        spot_lot_id TEXT NOT NULL DEFAULT '',
        structure_id TEXT NOT NULL,
        structure_kind TEXT NOT NULL,
        structure_side TEXT NOT NULL,
        matched_qty DOUBLE PRECISION NOT NULL,
        spot_buy_avg_price DOUBLE PRECISION NOT NULL,
        spot_sell_price DOUBLE PRECISION NOT NULL,
        spot_cost_amount DOUBLE PRECISION NOT NULL,
        spot_pnl DOUBLE PRECISION NOT NULL,
        structure_close_price DOUBLE PRECISION NOT NULL,
        structure_pnl DOUBLE PRECISION NOT NULL,
        total_pnl DOUBLE PRECISION NOT NULL,
        close_batch_id TEXT NOT NULL,
        note TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS spot_summary_hidden (
        group_id TEXT NOT NULL,
        spot_name TEXT NOT NULL,
        hidden_at TEXT NOT NULL,
        hidden_by TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (group_id, spot_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS app_kv (
        k TEXT PRIMARY KEY,
        v TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS risk_credit_limit (
        risk_party TEXT PRIMARY KEY,
        credit_limit_wan DOUBLE PRECISION NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS structure_template (
        template_id TEXT PRIMARY KEY,
        template_name TEXT NOT NULL DEFAULT '',
        underlying_name TEXT NOT NULL DEFAULT '',
        underlying TEXT NOT NULL DEFAULT '',
        strategy_code TEXT NOT NULL DEFAULT '',
        kind TEXT NOT NULL DEFAULT '',
        note TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}',
        usage_count INTEGER NOT NULL DEFAULT 0,
        last_used_at TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS self_quote_multi_value_preset (
        preset_id TEXT PRIMARY KEY,
        strategy_code TEXT NOT NULL DEFAULT '',
        field_key TEXT NOT NULL DEFAULT '',
        field_label TEXT NOT NULL DEFAULT '',
        value_text TEXT NOT NULL DEFAULT '',
        values_json TEXT NOT NULL DEFAULT '[]',
        normalized_key TEXT NOT NULL DEFAULT '',
        sort_order INTEGER NOT NULL DEFAULT 0,
        usage_count INTEGER NOT NULL DEFAULT 0,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_by TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT '',
        last_used_at TEXT NOT NULL DEFAULT '',
        CONSTRAINT uq_self_quote_multi_value_preset_key UNIQUE(strategy_code, field_key, normalized_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS probexp_market_input (
        dt TEXT NOT NULL,
        underlying TEXT NOT NULL,
        atm_iv DOUBLE PRECISION NOT NULL DEFAULT 0,
        skew DOUBLE PRECISION NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT 'manual',
        updated_at TEXT NOT NULL,
        PRIMARY KEY (dt, underlying)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS probexp_calc_log (
        log_id TEXT PRIMARY KEY,
        dt TEXT NOT NULL,
        group_id TEXT NOT NULL,
        structure_id TEXT NOT NULL,
        underlying TEXT NOT NULL,
        close_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        target_hedge_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
        current_position_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        current_position_after_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        target_position_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        suggested_adjust_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        no_trade_band_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        atm_iv DOUBLE PRECISION NOT NULL DEFAULT 0,
        skew DOUBLE PRECISION NOT NULL DEFAULT 0,
        mc_paths INTEGER NOT NULL DEFAULT 0,
        decision_quantile TEXT NOT NULL DEFAULT 'P50',
        realized_qty DOUBLE PRECISION NOT NULL DEFAULT 0,
        remaining_days INTEGER NOT NULL DEFAULT 0,
        p10 DOUBLE PRECISION NOT NULL DEFAULT 0,
        p20 DOUBLE PRECISION NOT NULL DEFAULT 0,
        p50 DOUBLE PRECISION NOT NULL DEFAULT 0,
        p80 DOUBLE PRECISION NOT NULL DEFAULT 0,
        p95 DOUBLE PRECISION NOT NULL DEFAULT 0,
        p975 DOUBLE PRECISION NOT NULL DEFAULT 0,
        model_version TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CONSTRAINT uq_probexp_calc_log_dt_structure UNIQUE(dt, structure_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS precise_hedge_calc_log (
        save_id TEXT PRIMARY KEY,
        dt TEXT NOT NULL,
        group_id TEXT NOT NULL,
        structure_id TEXT NOT NULL,
        underlying TEXT NOT NULL,
        version_no INTEGER NOT NULL DEFAULT 1,
        close_price DOUBLE PRECISION NOT NULL DEFAULT 0,
        current_position_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        target_center_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        target_lower_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        target_upper_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        recommended_position_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        suggested_adjust_tons DOUBLE PRECISION NOT NULL DEFAULT 0,
        current_hit_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
        under_prob DOUBLE PRECISION NOT NULL DEFAULT 0,
        over_prob DOUBLE PRECISION NOT NULL DEFAULT 0,
        history_samples INTEGER NOT NULL DEFAULT 0,
        mc_paths INTEGER NOT NULL DEFAULT 0,
        atm_iv DOUBLE PRECISION NOT NULL DEFAULT 0,
        skew DOUBLE PRECISION NOT NULL DEFAULT 0,
        current_zone TEXT NOT NULL DEFAULT '',
        action_type TEXT NOT NULL DEFAULT '',
        confidence_level TEXT NOT NULL DEFAULT '',
        risk_focus TEXT NOT NULL DEFAULT '',
        fusion_mode TEXT NOT NULL DEFAULT '',
        frozen_reason TEXT NOT NULL DEFAULT '',
        state_weighted_optimal DOUBLE PRECISION NOT NULL DEFAULT 0,
        history_suggestion DOUBLE PRECISION NOT NULL DEFAULT 0,
        mc_suggestion DOUBLE PRECISION NOT NULL DEFAULT 0,
        fused_position DOUBLE PRECISION NOT NULL DEFAULT 0,
        model_version TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS winrate_valuation_surface_cache (
        save_id TEXT PRIMARY KEY,
        dt TEXT NOT NULL,
        group_id TEXT NOT NULL,
        structure_id TEXT NOT NULL,
        signature TEXT NOT NULL,
        z_axis_mode TEXT NOT NULL DEFAULT 'unit',
        params_json TEXT NOT NULL DEFAULT '{}',
        result_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CONSTRAINT uq_winrate_valuation_surface_cache_lookup UNIQUE(dt, structure_id, signature)
    )
    """,
)

PG_COLUMN_UPGRADE_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE strategy_group ADD COLUMN IF NOT EXISTS is_hidden INTEGER DEFAULT 0",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS structure_code TEXT",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS strategy_code TEXT",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS structure_type TEXT",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS risk_party TEXT DEFAULT '海证资本'",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS customer_name TEXT DEFAULT ''",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS counterparty TEXT DEFAULT ''",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS contract_month TEXT DEFAULT ''",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS entry_price DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS strike_price DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS barrier_in DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS barrier_out DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS knock_out_price DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS ko_strike_price DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS multiple DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS trade_date TEXT",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS expiry_date TEXT",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS option_type TEXT",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS side TEXT",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS premium DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS note TEXT DEFAULT ''",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS meta_json TEXT NOT NULL DEFAULT '{}'",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS barrier_price DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS melt_price DOUBLE PRECISION",
    "ALTER TABLE structure ADD COLUMN IF NOT EXISTS melt_strike DOUBLE PRECISION",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS open_price DOUBLE PRECISION",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS close_category TEXT DEFAULT '结构平仓'",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS quick_batch_id TEXT",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS source_gen_date TEXT",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS is_external INTEGER DEFAULT 0",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS roll_target_underlying TEXT DEFAULT ''",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS roll_target_price DOUBLE PRECISION",
    "ALTER TABLE close_trade2 ADD COLUMN IF NOT EXISTS roll_spread_pnl DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS adjust_batch_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS group_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS structure_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS underlying TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS adjust_dt TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS delta_qty DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS before_qty DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS after_qty DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS basis_open_price DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS previous_basis_open_price DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS action_type TEXT NOT NULL DEFAULT 'INCREASE'",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS revert_of_adjustment_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS is_reverted INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS created_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE structure_position_adjustment ADD COLUMN IF NOT EXISTS created_by TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS structure_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS group_id TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS underlying TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS trigger_date TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS conversion_qty DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS conversion_price DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS notional_amount DOUBLE PRECISION NOT NULL DEFAULT 0",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS source_status TEXT NOT NULL DEFAULT '雪球折价转期货'",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS source_calc_date TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE snowball_conversion ADD COLUMN IF NOT EXISTS updated_at TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE price ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'manual'",
    "ALTER TABLE price ADD COLUMN IF NOT EXISTS is_locked INTEGER DEFAULT 0",
    "ALTER TABLE price ADD COLUMN IF NOT EXISTS updated_at TEXT",
)

PG_INDEX_STATEMENTS: tuple[str, ...] = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_snowball_conversion_structure_trigger ON snowball_conversion(structure_id, trigger_date)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_self_quote_multi_value_preset_key ON self_quote_multi_value_preset(strategy_code, field_key, normalized_key)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_probexp_calc_log_dt_structure ON probexp_calc_log(dt, structure_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_winrate_valuation_surface_cache_lookup ON winrate_valuation_surface_cache(dt, structure_id, signature)",
    "CREATE INDEX IF NOT EXISTS idx_precise_hedge_calc_log_lookup ON precise_hedge_calc_log(dt, structure_id, version_no DESC, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_winrate_valuation_surface_cache_lookup ON winrate_valuation_surface_cache(dt, structure_id, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_structure_template_active_sort ON structure_template(is_active, last_used_at DESC, usage_count DESC, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_structure_template_strategy ON structure_template(strategy_code, kind, underlying)",
    "CREATE INDEX IF NOT EXISTS idx_self_quote_multi_value_preset_lookup ON self_quote_multi_value_preset(strategy_code, field_key, is_active, sort_order, usage_count)",
    "CREATE INDEX IF NOT EXISTS idx_self_quote_multi_value_preset_updated ON self_quote_multi_value_preset(strategy_code, field_key, updated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_structure_group_id ON structure(group_id)",
    "CREATE INDEX IF NOT EXISTS idx_structure_group_structure_code ON structure(group_id, structure_code)",
    "CREATE INDEX IF NOT EXISTS idx_structure_group_underlying ON structure(group_id, underlying)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_structure_group_structure_code ON structure(group_id, structure_code)",
    "CREATE INDEX IF NOT EXISTS idx_price_underlying_dt ON price(underlying, dt)",
    "CREATE INDEX IF NOT EXISTS idx_close_trade_gid_dt ON close_trade(group_id, dt)",
    "CREATE INDEX IF NOT EXISTS idx_close_trade2_gid_dt ON close_trade2(group_id, dt)",
    "CREATE INDEX IF NOT EXISTS idx_close_trade2_sid_dt ON close_trade2(structure_id, dt)",
    "CREATE INDEX IF NOT EXISTS idx_close_trade2_gid_sid_dt ON close_trade2(group_id, structure_id, dt)",
    "CREATE INDEX IF NOT EXISTS idx_close_trade2_quick_batch_id ON close_trade2(quick_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_close_trade2_gid_quick_batch_id ON close_trade2(group_id, quick_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_snowball_conv_gid_date ON snowball_conversion(group_id, trigger_date)",
    "CREATE INDEX IF NOT EXISTS idx_snowball_conv_sid_date ON snowball_conversion(structure_id, trigger_date)",
    "CREATE INDEX IF NOT EXISTS idx_spot_lot_gid_buy_dt ON spot_position_lot(group_id, buy_dt)",
    "CREATE INDEX IF NOT EXISTS idx_spot_match_gid_dt ON spot_hedge_match_log(group_id, match_dt)",
    "CREATE INDEX IF NOT EXISTS idx_spot_match_gid_batch ON spot_hedge_match_log(group_id, close_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_close_revert_log_close_id ON close_revert_log(close_id)",
    "CREATE INDEX IF NOT EXISTS idx_struct_pos_adj_gid_dt ON structure_position_adjustment(group_id, adjust_dt)",
    "CREATE INDEX IF NOT EXISTS idx_struct_pos_adj_sid_dt ON structure_position_adjustment(structure_id, adjust_dt)",
    "CREATE INDEX IF NOT EXISTS idx_struct_pos_adj_batch ON structure_position_adjustment(adjust_batch_id)",
    "CREATE INDEX IF NOT EXISTS idx_struct_pos_adj_revert ON structure_position_adjustment(revert_of_adjustment_id)",
)

PG_BACKFILL_STATEMENTS: tuple[str, ...] = (
    "UPDATE strategy_group SET is_hidden = COALESCE(is_hidden, 0)",
    """
    UPDATE structure
    SET structure_code = COALESCE(NULLIF(TRIM(structure_code), ''), TRIM(structure_id))
    WHERE COALESCE(NULLIF(TRIM(structure_code), ''), '') = ''
    """,
    """
    UPDATE price
    SET
        source = COALESCE(NULLIF(TRIM(source), ''), 'manual'),
        is_locked = COALESCE(is_locked, 0),
        updated_at = COALESCE(NULLIF(TRIM(updated_at), ''), TO_CHAR(CURRENT_TIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'))
    """,
)


def _require_postgres_backend() -> None:
    backend = get_db_backend()
    if backend != "postgres":
        raise RuntimeError(
            f"当前 APP_DB_BACKEND={backend!r}，已阻止访问 PostgreSQL。"
            " 如需连接 Neon，请设置 APP_DB_BACKEND=postgres。"
        )


def get_pg_connection() -> Any:
    _require_postgres_backend()
    return st.connection("postgres", type="sql")


def _normalize_database_url(url: Any) -> str:
    url_s = str(url or "").strip()
    if url_s.startswith("postgres://"):
        return "postgresql+psycopg2://" + url_s[len("postgres://") :]
    return url_s


def _read_database_url_from_streamlit_secrets() -> str:
    try:
        connections = st.secrets.get("connections", {})
        postgres = connections.get("postgres", {}) if connections is not None else {}
        return _normalize_database_url(postgres.get("url"))
    except Exception:
        return ""


def _read_database_url_from_secrets_file() -> str:
    secrets_path = PROJECT_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return ""
    try:
        data = tomllib.loads(secrets_path.read_text(encoding="utf-8-sig"))
        connections = data.get("connections", {})
        postgres = connections.get("postgres", {}) if isinstance(connections, dict) else {}
        return _normalize_database_url(postgres.get("url"))
    except Exception:
        return ""


def get_pg_database_url() -> str:
    url = _normalize_database_url(os.getenv("DATABASE_URL"))
    if not url:
        url = _read_database_url_from_streamlit_secrets()
    if not url:
        url = _read_database_url_from_secrets_file()
    if not url:
        raise RuntimeError(
            "未找到 PostgreSQL 连接串。请设置环境变量 DATABASE_URL，"
            "或在 .streamlit/secrets.toml 的 [connections.postgres].url 中配置。"
        )
    return url


def get_pg_engine(*, require_postgres_backend: bool = True) -> Any:
    if require_postgres_backend:
        _require_postgres_backend()
    from sqlalchemy import create_engine

    return create_engine(
        get_pg_database_url(),
        future=True,
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": 15,
            "options": "-c statement_timeout=60000 -c lock_timeout=15000",
        },
    )


def pg_query(sql: str, params: dict | None = None) -> Any:
    conn = get_pg_connection()
    return conn.query(sql, params=params or {}, ttl=0)


def pg_execute(sql: str, params: dict | None = None) -> int:
    from sqlalchemy import text

    conn = get_pg_connection()
    with conn.session as session:
        try:
            result = session.execute(text(sql), params or {})
            session.commit()
            return int(result.rowcount)
        except Exception:
            session.rollback()
            raise


def pg_execute_many(sql: str, rows: list[dict]) -> int:
    if not rows:
        return 0
    from sqlalchemy import text

    conn = get_pg_connection()
    with conn.session as session:
        try:
            result = session.execute(text(sql), rows)
            session.commit()
            return int(result.rowcount)
        except Exception:
            session.rollback()
            raise


def init_pg_db(*, require_postgres_backend: bool = True) -> None:
    # SQLite PRAGMA/WAL/busy_timeout settings are intentionally SQLite-only.
    # SQLite triggers are not hard-migrated here; later phases can add Python
    # validation or PostgreSQL triggers after dirty legacy data has been checked.
    from sqlalchemy import text

    engine = get_pg_engine(require_postgres_backend=require_postgres_backend)
    statements = (
        PG_DDL_STATEMENTS
        + PG_COLUMN_UPGRADE_STATEMENTS
        + PG_INDEX_STATEMENTS
        + PG_BACKFILL_STATEMENTS
    )
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))
