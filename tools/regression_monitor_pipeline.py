from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

import pandas as pd

EPS = 1e-6


@dataclass
class CheckResult:
    name: str
    status: str  # pass / skip / fail
    detail: str


def pick_first(*vals: Any) -> Any:
    for v in vals:
        if v is None:
            continue
        if isinstance(v, float) and pd.isna(v):
            continue
        return v
    return None


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return float(default)
        if isinstance(v, float) and pd.isna(v):
            return float(default)
        return float(v)
    except Exception:
        return float(default)


def to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(pick_first(v, "")).strip().lower()
    return s in {"1", "true", "yes", "y", "t", "on"}


def parse_ymd(v: str, arg_name: str) -> date:
    txt = str(v).strip()
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"{arg_name} must be YYYY-MM-DD, got: {txt}") from exc


def load_app_core_namespace(app_path: Path) -> Dict[str, Any]:
    src = app_path.read_text(encoding="utf-8-sig")
    cut_idx = src.find("\nst.set_page_config(")
    if cut_idx <= 0:
        raise RuntimeError("Cannot find Streamlit UI bootstrap in app.py (st.set_page_config).")
    core_src = src[:cut_idx]
    ns: Dict[str, Any] = {}
    exec(compile(core_src, str(app_path), "exec"), ns, ns)
    return ns


def list_group_ids(db_path: Path) -> List[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT group_id FROM strategy_group ORDER BY group_id").fetchall()
        return [str(r[0]).strip() for r in rows if str(r[0]).strip()]
    finally:
        conn.close()


def list_candidate_asof_dates(db_path: Path, gid: str) -> List[date]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT p.dt AS dt
            FROM price p
            INNER JOIN structure s
                ON s.underlying = p.underlying
               AND s.group_id = ?
            UNION
            SELECT DISTINCT c.dt AS dt
            FROM close_trade2 c
            WHERE c.group_id = ?
            ORDER BY dt
            """,
            (str(gid), str(gid)),
        ).fetchall()
    finally:
        conn.close()

    out: List[date] = []
    for r in rows:
        txt = str(pick_first(r[0], "")).strip()
        if not txt:
            continue
        try:
            out.append(datetime.strptime(txt, "%Y-%m-%d").date())
        except Exception:
            continue
    return sorted(set(out))


def filter_dates(dates: List[date], d_from: Optional[date], d_to: Optional[date]) -> List[date]:
    out = list(dates)
    if d_from is not None:
        out = [d for d in out if d >= d_from]
    if d_to is not None:
        out = [d for d in out if d <= d_to]
    return sorted(set(out))


def choose_group_ids(db_path: Path, group_arg: str, all_groups: bool) -> List[str]:
    gids = list_group_ids(db_path)
    if not gids:
        raise RuntimeError("No strategy groups in DB.")
    if all_groups:
        return gids
    if group_arg.strip():
        g = group_arg.strip()
        if g not in gids:
            raise RuntimeError(f"group_id not found: {g}")
        return [g]
    return [gids[0]]


def build_scenarios(
    db_path: Path,
    *,
    group_arg: str,
    all_groups: bool,
    as_of_fixed: Optional[date],
    all_dates: bool,
    date_from: Optional[date],
    date_to: Optional[date],
) -> List[Tuple[str, Optional[date]]]:
    gids = choose_group_ids(db_path, group_arg=group_arg, all_groups=all_groups)
    scenarios: List[Tuple[str, Optional[date]]] = []
    for gid in gids:
        if as_of_fixed is not None:
            scenarios.append((gid, as_of_fixed))
            continue
        cand = filter_dates(list_candidate_asof_dates(db_path, gid), date_from, date_to)
        if all_dates or date_from is not None or date_to is not None:
            if cand:
                scenarios.extend([(gid, d) for d in cand])
            else:
                scenarios.append((gid, None))
        else:
            scenarios.append((gid, cand[-1] if cand else None))
    return scenarios


def compute_asof_frames(ns: Dict[str, Any], conn: Any, as_of: date) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    return ns["compute_ledgers"](conn, as_of_date=as_of_s)


def pick_asof_date(ns: Dict[str, Any], conn: Any, fallback: Optional[date]) -> date:
    if isinstance(fallback, date):
        return fallback
    prices = ns["fetch_prices"](conn)
    closes2 = ns["fetch_closes2"](conn)
    return ns["infer_effective_asof_date"](prices, closes2)


def _fail_examples(df: pd.DataFrame, cols: List[str], max_rows: int = 3) -> str:
    if df.empty:
        return ""
    show = df[cols].head(max_rows).to_dict("records")
    return "; ".join([str(x) for x in show])


def check_group_daily_aggregation(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    struct_df, group_df, _ = compute_asof_frames(ns, conn, as_of)
    s = struct_df[struct_df["group_id"].astype(str) == str(gid)].copy()
    g = group_df[group_df["group_id"].astype(str) == str(gid)].copy()
    if s.empty or g.empty:
        return CheckResult("monitor-group-daily-aggregation", "skip", "no structure/group rows for group")

    s["generated_qty"] = pd.to_numeric(s.get("generated_qty"), errors="coerce").fillna(0.0)
    s["day_pnl"] = pd.to_numeric(s.get("day_pnl"), errors="coerce").fillna(0.0)
    s["day_subsidy_pnl"] = pd.to_numeric(s.get("day_subsidy_pnl"), errors="coerce").fillna(0.0)
    kind_u = s.get("kind", "").astype(str).str.upper()
    s["__signed_qty"] = s["generated_qty"].where(kind_u.eq("ACC"), -s["generated_qty"])
    s["__abs_qty"] = s["generated_qty"].abs()

    s_day = (
        s.groupby(["date", "group_id", "underlying"], as_index=False)
        .agg(
            sum_day_pnl=("day_pnl", "sum"),
            sum_day_subsidy=("day_subsidy_pnl", "sum"),
            sum_abs_qty=("__abs_qty", "sum"),
            sum_signed_qty=("__signed_qty", "sum"),
        )
    )
    merged = g.merge(s_day, on=["date", "group_id", "underlying"], how="left")
    for c in ["sum_day_pnl", "sum_day_subsidy", "sum_abs_qty", "sum_signed_qty"]:
        merged[c] = pd.to_numeric(merged.get(c), errors="coerce").fillna(0.0)

    merged["diff_day_pnl"] = (
        pd.to_numeric(merged.get("structure_day_pnl_sum"), errors="coerce").fillna(0.0) - merged["sum_day_pnl"]
    ).abs()
    merged["diff_day_subsidy"] = (
        pd.to_numeric(merged.get("day_subsidy_pnl"), errors="coerce").fillna(0.0) - merged["sum_day_subsidy"]
    ).abs()
    merged["diff_abs_qty"] = (
        pd.to_numeric(merged.get("struct_gen_abs_qty"), errors="coerce").fillna(0.0) - merged["sum_abs_qty"]
    ).abs()
    merged["diff_signed_qty"] = (
        pd.to_numeric(merged.get("struct_gen_signed_qty"), errors="coerce").fillna(0.0) - merged["sum_signed_qty"]
    ).abs()

    bad = merged[
        (merged["diff_day_pnl"] > 1e-5)
        | (merged["diff_day_subsidy"] > 1e-5)
        | (merged["diff_abs_qty"] > 1e-5)
        | (merged["diff_signed_qty"] > 1e-5)
    ].copy()
    if bad.empty:
        return CheckResult("monitor-group-daily-aggregation", "pass", f"rows={len(merged)} matched")
    detail = _fail_examples(
        bad,
        ["date", "underlying", "diff_day_pnl", "diff_day_subsidy", "diff_abs_qty", "diff_signed_qty"],
        max_rows=3,
    )
    return CheckResult("monitor-group-daily-aggregation", "fail", f"mismatch_rows={len(bad)} | {detail}")


def check_close_pnl_daily_alignment(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    struct_df, group_df, _ = compute_asof_frames(ns, conn, as_of)
    g = group_df[group_df["group_id"].astype(str) == str(gid)].copy()
    if g.empty:
        return CheckResult("monitor-close-pnl-daily-alignment", "skip", "no group rows")

    g = g.sort_values(["underlying", "date"]).copy()
    g["close_pnl"] = pd.to_numeric(g.get("close_pnl"), errors="coerce").fillna(0.0)
    g["actual_close_day"] = g.groupby("underlying")["close_pnl"].diff()
    g["actual_close_day"] = g["actual_close_day"].fillna(g["close_pnl"])

    closes2 = ns["fetch_closes2"](conn)
    if closes2 is None or closes2.empty:
        close2_day = pd.DataFrame(columns=["date", "underlying", "close2_day"])
    else:
        c = closes2[
            (closes2["group_id"].astype(str) == str(gid))
            & (closes2["dt"].astype(str) <= str(as_of_s))
        ].copy()
        c["pnl"] = pd.to_numeric(c.get("pnl"), errors="coerce").fillna(0.0)
        close2_day = c.groupby(["dt", "underlying"], as_index=False)["pnl"].sum().rename(
            columns={"dt": "date", "pnl": "close2_day"}
        )

    s = struct_df[struct_df["group_id"].astype(str) == str(gid)].copy()
    if s.empty:
        option_day = pd.DataFrame(columns=["date", "underlying", "option_day"])
    else:
        s["day_option_pnl"] = pd.to_numeric(s.get("day_option_pnl"), errors="coerce").fillna(0.0)
        option_day = s.groupby(["date", "underlying"], as_index=False)["day_option_pnl"].sum().rename(
            columns={"day_option_pnl": "option_day"}
        )

    expected = close2_day.merge(option_day, on=["date", "underlying"], how="outer")
    if expected.empty:
        expected = pd.DataFrame(columns=["date", "underlying", "close2_day", "option_day"])
    expected["close2_day"] = pd.to_numeric(expected.get("close2_day"), errors="coerce").fillna(0.0)
    expected["option_day"] = pd.to_numeric(expected.get("option_day"), errors="coerce").fillna(0.0)
    expected["expected_close_day"] = expected["close2_day"] + expected["option_day"]

    merged = g.merge(expected[["date", "underlying", "expected_close_day"]], on=["date", "underlying"], how="left")
    merged["expected_close_day"] = pd.to_numeric(merged.get("expected_close_day"), errors="coerce").fillna(0.0)
    merged["diff"] = (merged["actual_close_day"] - merged["expected_close_day"]).abs()
    bad = merged[merged["diff"] > 1e-5].copy()
    if bad.empty:
        return CheckResult("monitor-close-pnl-daily-alignment", "pass", f"rows={len(merged)} matched")
    detail = _fail_examples(bad, ["date", "underlying", "actual_close_day", "expected_close_day", "diff"], max_rows=3)
    return CheckResult("monitor-close-pnl-daily-alignment", "fail", f"mismatch_rows={len(bad)} | {detail}")


def check_spot_match_total_pnl_identity(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    logs = ns["fetch_spot_hedge_logs"](conn)
    if logs is None or logs.empty:
        return CheckResult("monitor-spot-match-total-pnl", "skip", "no spot hedge logs")
    sub = logs[
        (logs["group_id"].astype(str) == str(gid))
        & (logs["match_dt"].astype(str) <= as_of.strftime(ns["DATE_FMT"]))
    ].copy()
    if sub.empty:
        return CheckResult("monitor-spot-match-total-pnl", "skip", "no logs for group/asof")
    sub["spot_pnl"] = pd.to_numeric(sub.get("spot_pnl"), errors="coerce").fillna(0.0)
    sub["structure_pnl"] = pd.to_numeric(sub.get("structure_pnl"), errors="coerce").fillna(0.0)
    sub["total_pnl"] = pd.to_numeric(sub.get("total_pnl"), errors="coerce").fillna(0.0)
    sub["diff"] = (sub["total_pnl"] - (sub["spot_pnl"] + sub["structure_pnl"])).abs()
    bad = sub[sub["diff"] > 1e-5].copy()
    if bad.empty:
        return CheckResult("monitor-spot-match-total-pnl", "pass", f"rows={len(sub)} matched")
    detail = _fail_examples(bad, ["match_id", "match_dt", "spot_pnl", "structure_pnl", "total_pnl", "diff"], max_rows=3)
    return CheckResult("monitor-spot-match-total-pnl", "fail", f"mismatch_rows={len(bad)} | {detail}")


def check_snowball_observation_plan_consistency(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    structs = ns["fetch_structures"](conn)
    if structs is None or structs.empty:
        return CheckResult("monitor-snowball-observation-plan", "skip", "no structures")
    sub = structs[
        (structs["group_id"].astype(str) == str(gid))
        & (structs["strategy_code"].astype(str).str.upper() == "SNOWBALL")
        & (structs["start_date"].astype(str) <= as_of.strftime(ns["DATE_FMT"]))
    ].copy()
    if sub.empty:
        return CheckResult("monitor-snowball-observation-plan", "skip", "no snowball structures for group")

    issues: List[str] = []
    checked = 0
    for _, row in sub.iterrows():
        sid = str(pick_first(row.get("structure_id"), "")).strip()
        if not sid:
            continue
        params = ns["parse_json_obj"](row.get("params_json"), {})
        try:
            start_d = datetime.strptime(str(row.get("start_date")), ns["DATE_FMT"]).date()
        except Exception:
            issues.append(f"{sid}: invalid start_date")
            continue
        term_unit = str(pick_first(params.get("sb_term_unit"), "WEEK")).strip().upper()
        term_count = int(round(to_float(pick_first(params.get("sb_term_count"), 1), 1.0)))
        term_count = max(term_count, 1)
        ko_freq = ns["_snowball_normalize_obs_freq"](pick_first(params.get("sb_ko_obs_freq"), "WEEKLY"))
        maturity_natural = ns["_snowball_add_period"](start_d, term_unit, term_count)
        obs = ns["_snowball_build_observations"](start_d, maturity_natural, ko_freq)
        if not obs:
            issues.append(f"{sid}: no observations")
            continue

        obs_dates = [x.get("obs_date") for x in obs if isinstance(x.get("obs_date"), date)]
        if len(obs_dates) != len(obs):
            issues.append(f"{sid}: observation date parse mismatch")
            continue
        bad_td = [d for d in obs_dates if not bool(ns["is_trading_day"](d))]
        if bad_td:
            issues.append(f"{sid}: has non-trading observation dates")
            continue
        if str(ko_freq).upper() == "WEEKLY":
            week_keys = [(d.isocalendar()[0], d.isocalendar()[1]) for d in obs_dates]
            if len(set(week_keys)) != len(week_keys):
                issues.append(f"{sid}: weekly observation contains duplicate ISO week")
                continue

        entry_price = to_float(pick_first(params.get("sb_entry_price"), row.get("entry_price"), row.get("strike_price")), 0.0)
        ko_base_price = to_float(
            pick_first(
                params.get("sb_ko_base_price"),
                params.get("sb_ko_price"),
                row.get("knock_out_price"),
                entry_price,
                0.0001,
            ),
            max(entry_price, 0.0001),
        )
        lock_enabled = to_bool(params.get("sb_lock_enabled"))
        lock_n = int(round(to_float(pick_first(params.get("sb_lock_ko_obs"), 0), 0.0))) if lock_enabled else 0
        plan = ns["_snowball_build_observation_plan"](
            observations=obs,
            lock_ko_obs=lock_n,
            entry_price=entry_price,
            ko_base_price=ko_base_price,
            ko_base_pct=(to_float(params.get("sb_ko_pct"), -1.0) if params.get("sb_ko_pct") is not None else None),
            auto_stepdown=to_bool(params.get("sb_auto_stepdown")),
            stepdown_pct=to_float(pick_first(params.get("sb_stepdown_pct"), 0.0), 0.0),
            min_ko_price=max(
                to_float(pick_first(row.get("ko_strike_price"), row.get("barrier_out"), 0.0001), 0.0001),
                0.0001,
            ),
        )
        if len(plan) != len(obs):
            issues.append(f"{sid}: plan size mismatch")
            continue

        eligible = [r for r in plan if not bool(r.get("is_locked", False))]
        locked = [r for r in plan if bool(r.get("is_locked", False))]
        if any((r.get("ko_price") is not None) for r in locked):
            issues.append(f"{sid}: locked rows should not have ko_price")
            continue
        eligible_idx = [int(to_float(r.get("eligible_idx"), 0.0)) for r in eligible]
        if eligible_idx and eligible_idx != list(range(1, len(eligible_idx) + 1)):
            issues.append(f"{sid}: eligible_idx sequence invalid")
            continue
        if to_bool(params.get("sb_auto_stepdown")):
            ko_prices = [to_float(r.get("ko_price"), 0.0) for r in eligible if r.get("ko_price") is not None]
            for i in range(1, len(ko_prices)):
                if ko_prices[i] - ko_prices[i - 1] > 1e-8:
                    issues.append(f"{sid}: auto-stepdown ko_price should be non-increasing")
                    break
            if issues:
                continue
        checked += 1

    if issues:
        return CheckResult("monitor-snowball-observation-plan", "fail", "; ".join(issues[:3]))
    return CheckResult("monitor-snowball-observation-plan", "pass", f"checked={checked}")


def check_external_close_pnl_coverage(
    ns: Dict[str, Any],
    conn: Any,
    tmp_db_path: Path,
    gid: str,
    as_of: date,
) -> CheckResult:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    close2 = ns["fetch_closes2"](conn)
    if close2 is None or close2.empty:
        return CheckResult("monitor-external-close-coverage", "skip", "no close_trade2 rows")
    ext = close2[
        (close2["group_id"].astype(str) == str(gid))
        & (pd.to_numeric(close2.get("is_external"), errors="coerce").fillna(0).astype(int) == 1)
        & (close2["dt"].astype(str) <= str(as_of_s))
    ].copy()
    if ext.empty:
        return CheckResult("monitor-external-close-coverage", "skip", "no external close rows for group/asof")

    _, group_base, _ = compute_asof_frames(ns, conn, as_of)
    gb = group_base[group_base["group_id"].astype(str) == str(gid)].copy()
    if gb.empty:
        return CheckResult("monitor-external-close-coverage", "skip", "group rows empty")
    gb["close_pnl"] = pd.to_numeric(gb.get("close_pnl"), errors="coerce").fillna(0.0)

    conn2 = sqlite3.connect(str(tmp_db_path), check_same_thread=False)
    try:
        conn2.execute("PRAGMA foreign_keys=ON;")
        ns["init_db"](conn2)
        conn2.execute(
            "DELETE FROM close_trade2 WHERE group_id=? AND is_external=1 AND dt<=?",
            (str(gid), str(as_of_s)),
        )
        conn2.commit()
        _, group_noext, _ = compute_asof_frames(ns, conn2, as_of)
    finally:
        conn2.close()

    gn = group_noext[group_noext["group_id"].astype(str) == str(gid)].copy()
    gn["close_pnl_noext"] = pd.to_numeric(gn.get("close_pnl"), errors="coerce").fillna(0.0)
    merged = gb.merge(
        gn[["date", "group_id", "underlying", "close_pnl_noext"]],
        on=["date", "group_id", "underlying"],
        how="left",
    )
    merged["close_pnl_noext"] = pd.to_numeric(merged.get("close_pnl_noext"), errors="coerce").fillna(0.0)
    merged["actual_ext_cum"] = merged["close_pnl"] - merged["close_pnl_noext"]

    ext["pnl"] = pd.to_numeric(ext.get("pnl"), errors="coerce").fillna(0.0)
    ext_day = ext.groupby(["dt", "underlying"], as_index=False)["pnl"].sum().rename(columns={"dt": "date", "pnl": "ext_day"})

    expected_parts: List[pd.DataFrame] = []
    key_df = merged[["date", "underlying"]].drop_duplicates().copy()
    for und, sub_keys in key_df.groupby("underlying"):
        k = sub_keys.sort_values("date").copy()
        e = ext_day[ext_day["underlying"].astype(str) == str(und)].copy()
        e = e.sort_values("date")
        e = e.set_index("date")["ext_day"] if not e.empty else pd.Series(dtype=float)
        seq = pd.to_numeric(k["date"], errors="coerce")
        _ = seq  # keep variable for lint parity
        vals = []
        run = 0.0
        day_map = {str(idx): float(val) for idx, val in e.to_dict().items()} if isinstance(e, pd.Series) else {}
        for d in k["date"].astype(str).tolist():
            run += float(day_map.get(d, 0.0))
            vals.append(run)
        k["expected_ext_cum"] = vals
        expected_parts.append(k)
    expected_df = pd.concat(expected_parts, ignore_index=True) if expected_parts else pd.DataFrame(
        columns=["date", "underlying", "expected_ext_cum"]
    )
    merged = merged.merge(expected_df, on=["date", "underlying"], how="left")
    merged["expected_ext_cum"] = pd.to_numeric(merged.get("expected_ext_cum"), errors="coerce").fillna(0.0)
    merged["diff"] = (merged["actual_ext_cum"] - merged["expected_ext_cum"]).abs()
    bad = merged[merged["diff"] > 1e-5].copy()
    if bad.empty:
        return CheckResult("monitor-external-close-coverage", "pass", f"rows={len(merged)} matched")
    detail = _fail_examples(bad, ["date", "underlying", "actual_ext_cum", "expected_ext_cum", "diff"], max_rows=3)
    return CheckResult("monitor-external-close-coverage", "fail", f"mismatch_rows={len(bad)} | {detail}")


def check_cache_invalidation_after_write(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    _, g1, _ = ns["compute_ledgers_cached"](conn, as_of_date=as_of_s)
    g1 = g1[g1["group_id"].astype(str) == str(gid)].copy()
    if g1.empty:
        return CheckResult("monitor-cache-invalidation", "skip", "no group rows for cache check")
    g1 = g1.sort_values(["date", "underlying"])
    row0 = g1.iloc[-1]
    und = str(row0.get("underlying", "")).strip()
    dt_s = str(row0.get("date", as_of_s)).strip() or as_of_s
    base_close = float(to_float(row0.get("close_pnl"), 0.0))
    if not und:
        return CheckResult("monitor-cache-invalidation", "skip", "no underlying in group row")

    pnl_bump = 777.0
    close_id = f"REG_CACHE_{uuid4().hex[:16]}"
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            """
            INSERT INTO close_trade2(
                close_id, dt, group_id, structure_id, underlying, side, qty, open_price, close_price, pnl, close_category, is_external
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                close_id,
                dt_s,
                str(gid),
                "外部",
                und,
                "平仓",
                0.0,
                0.0,
                0.0,
                float(pnl_bump),
                "多头头寸",
                1,
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        return CheckResult("monitor-cache-invalidation", "fail", "insert external row failed")

    _, g2, _ = ns["compute_ledgers_cached"](conn, as_of_date=as_of_s)
    _, g2_direct, _ = ns["compute_ledgers"](conn, as_of_date=as_of_s)
    g2 = g2[
        (g2["group_id"].astype(str) == str(gid))
        & (g2["date"].astype(str) == str(dt_s))
        & (g2["underlying"].astype(str) == str(und))
    ].copy()
    g2_direct = g2_direct[
        (g2_direct["group_id"].astype(str) == str(gid))
        & (g2_direct["date"].astype(str) == str(dt_s))
        & (g2_direct["underlying"].astype(str) == str(und))
    ].copy()
    cleanup_ok = True
    try:
        conn.execute("DELETE FROM close_trade2 WHERE close_id=?", (close_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        cleanup_ok = False

    if g2.empty:
        return CheckResult("monitor-cache-invalidation", "fail", "post-write group row missing")
    if g2_direct.empty:
        return CheckResult("monitor-cache-invalidation", "fail", "direct compute row missing after write")
    new_close = float(to_float(g2.iloc[0].get("close_pnl"), 0.0))
    direct_close = float(to_float(g2_direct.iloc[0].get("close_pnl"), 0.0))
    delta = new_close - base_close
    if abs(new_close - direct_close) > 1e-5:
        return CheckResult(
            "monitor-cache-invalidation",
            "fail",
            f"cached/direct mismatch after write, cached={new_close:.4f}, direct={direct_close:.4f}",
        )
    if abs(delta) <= 1e-8:
        return CheckResult("monitor-cache-invalidation", "fail", "close_pnl unchanged after write")
    if not cleanup_ok:
        return CheckResult("monitor-cache-invalidation", "fail", "cleanup failed after cache check")
    return CheckResult("monitor-cache-invalidation", "pass", f"delta={delta:.2f}, cached==direct")


def run_checks_for_scenario(
    db_path: Path,
    app_path: Path,
    gid: str,
    as_of_override: Optional[date],
) -> Tuple[date, List[CheckResult]]:
    ns = load_app_core_namespace(app_path)
    tmp_dir = tempfile.mkdtemp(prefix="otc_monitor_reg_")
    tmp_db = Path(tmp_dir) / "monitor_reg_copy.db"
    shutil.copy2(str(db_path), str(tmp_db))
    ns["DB_PATH"] = str(tmp_db)

    conn = ns["get_conn"]()
    try:
        ns["init_db"](conn)
        as_of = pick_asof_date(ns, conn, as_of_override)
        checks: List[Callable[..., CheckResult]] = [
            check_group_daily_aggregation,
            check_close_pnl_daily_alignment,
            check_spot_match_total_pnl_identity,
            check_snowball_observation_plan_consistency,
            check_external_close_pnl_coverage,
            check_cache_invalidation_after_write,
        ]
        results: List[CheckResult] = []
        for fn in checks:
            try:
                if fn is check_external_close_pnl_coverage:
                    res = fn(ns, conn, tmp_db, gid, as_of)
                else:
                    res = fn(ns, conn, gid, as_of)
            except Exception as exc:
                res = CheckResult(fn.__name__, "fail", f"{type(exc).__name__}: {exc}")
            results.append(res)
        return as_of, results
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Monitor pipeline regression checks (runs on a temporary DB copy)."
    )
    parser.add_argument("--db", default="otc_gui.db", help="Path to sqlite DB.")
    parser.add_argument("--app", default="app.py", help="Path to app.py.")
    parser.add_argument("--group", default="", help="Run only this group_id.")
    parser.add_argument("--all-groups", action="store_true", help="Run all groups.")
    parser.add_argument("--as-of", default="", help="Fixed as-of date YYYY-MM-DD.")
    parser.add_argument("--all-dates", action="store_true", help="Run all candidate as-of dates.")
    parser.add_argument("--date-from", default="", help="Lower as-of bound YYYY-MM-DD.")
    parser.add_argument("--date-to", default="", help="Upper as-of bound YYYY-MM-DD.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    app_path = Path(args.app).resolve()
    if not db_path.exists():
        print(f"[FAIL] DB not found: {db_path}")
        return 2
    if not app_path.exists():
        print(f"[FAIL] app.py not found: {app_path}")
        return 2
    if args.group.strip() and args.all_groups:
        print("[FAIL] --group cannot be used together with --all-groups")
        return 2

    try:
        as_of_fixed = parse_ymd(args.as_of, "--as-of") if str(args.as_of).strip() else None
        d_from = parse_ymd(args.date_from, "--date-from") if str(args.date_from).strip() else None
        d_to = parse_ymd(args.date_to, "--date-to") if str(args.date_to).strip() else None
    except Exception as exc:
        print(f"[FAIL] arg parse error: {exc}")
        return 2
    if d_from is not None and d_to is not None and d_from > d_to:
        d_from, d_to = d_to, d_from

    try:
        scenarios = build_scenarios(
            db_path,
            group_arg=str(args.group).strip(),
            all_groups=bool(args.all_groups),
            as_of_fixed=as_of_fixed,
            all_dates=bool(args.all_dates),
            date_from=d_from,
            date_to=d_to,
        )
    except Exception as exc:
        print(f"[FAIL] scenario build error: {exc}")
        return 2

    if not scenarios:
        print("[FAIL] no scenarios to run")
        return 2

    total_pass = 0
    total_skip = 0
    total_fail = 0
    total_checks = 0
    print("=== Monitor Pipeline Regression ===")
    for i, (gid, as_of_override) in enumerate(scenarios, start=1):
        try:
            as_of_used, results = run_checks_for_scenario(db_path, app_path, gid, as_of_override)
        except Exception as exc:
            print(f"\n--- Scenario {i}/{len(scenarios)} | group={gid} ---")
            print(f"[FAIL] scenario bootstrap failed: {type(exc).__name__}: {exc}")
            total_fail += 1
            continue
        print(f"\n--- Scenario {i}/{len(scenarios)} | group={gid} | asof={as_of_used.strftime('%Y-%m-%d')} ---")
        for r in results:
            print(f"[{r.status.upper()}] {r.name}: {r.detail}")
        p = sum(1 for r in results if r.status == "pass")
        s = sum(1 for r in results if r.status == "skip")
        f = sum(1 for r in results if r.status == "fail")
        print(f"Scenario summary: pass={p} | skip={s} | fail={f} | total={len(results)}")
        total_pass += p
        total_skip += s
        total_fail += f
        total_checks += len(results)

    print("\n=== Overall summary ===")
    print(
        f"scenarios={len(scenarios)} | pass={total_pass} | "
        f"skip={total_skip} | fail={total_fail} | total_checks={total_checks}"
    )
    return 1 if total_fail > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
