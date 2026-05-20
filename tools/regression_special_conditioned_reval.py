from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


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


def load_app_core_namespace(app_path: Path) -> Dict[str, Any]:
    src = app_path.read_text(encoding="utf-8-sig")
    cut_idx = src.find("\nst.set_page_config(")
    if cut_idx <= 0:
        raise RuntimeError("Cannot find st.set_page_config in app.py.")
    ns: Dict[str, Any] = {}
    exec(compile(src[:cut_idx], str(app_path), "exec"), ns, ns)
    return ns


def parse_ymd(txt: str) -> date:
    return datetime.strptime(str(txt).strip(), "%Y-%m-%d").date()


def check(cond: bool, name: str, detail_ok: str, detail_fail: str) -> CheckResult:
    return CheckResult(name=name, status="pass" if cond else "fail", detail=detail_ok if cond else detail_fail)


def synthetic_cap_freeze(ns: Dict[str, Any]) -> CheckResult:
    struct_row = {
        "structure_id": "SYN_CAP",
        "strategy_code": "NO_KO",
        "kind": "ACC",
        "entry_price": 100.0,
        "strike_price": 95.0,
        "base_qty_per_day": 10.0,
        "multiple": 2.0,
        "meta": {},
    }
    seed = {
        "current_price": 101.0,
        "remaining_days": 3,
        "live_remaining_days": 3,
        "cum_qty": 30.0,
        "executed_qty": 30.0,
        "remaining_cap_qty": 0.0,
        "remaining_executable_qty": 0.0,
        "current_open_qty": 20.0,
    }
    res = ns["probexp_simulate_future_qty"](
        struct_row,
        start_price=101.0,
        remaining_days=3,
        atm_iv_pct=25.0,
        skew=0.0,
        paths=10000,
        evaluation_basis="live",
        state_seed=seed,
        seed_hint="synthetic_cap_freeze",
    )
    ok = (
        str(pick_first(res.get("frozen_reason"), "")) == "remaining_cap_exhausted"
        and np.allclose(np.asarray(res.get("future_qty_paths"), dtype=float), 0.0)
        and np.allclose(np.asarray(res.get("cum_exec_paths"), dtype=float), 30.0)
        and abs(float(pick_first(res.get("structure_survival_prob"), 0.0) or 0.0) - 1.0) <= 1e-9
    )
    return check(
        ok,
        "synthetic-cap-freeze",
        "remaining_cap_exhausted froze future increment and preserved cum_qty alias.",
        f"unexpected freeze result: frozen={res.get('frozen_reason')} cum_exec_p50={np.quantile(np.asarray(res.get('cum_exec_paths'), dtype=float), 0.5) if np.asarray(res.get('cum_exec_paths'), dtype=float).size else 'na'}",
    )


def synthetic_snowball_knockin_filter(ns: Dict[str, Any]) -> CheckResult:
    resolved = {
        "structure_id": "SYN_SB",
        "group_id": "SYN_G",
        "strategy_code": "SNOWBALL",
        "kind": "ACC",
        "name": "Synthetic Snowball",
        "entry_price": 100.0,
        "barrier_in": 95.0,
        "barrier_out": 95.0,
        "knock_out_price": 105.0,
        "start_date": "2026-01-02",
        "end_date": "2026-01-09",
        "underlying": "TEST",
    }
    template = ns["winrate_prepare_structure_template"](resolved)
    seed = {
        "rep_date": "2026-01-07",
        "current_price": 95.0,
        "remaining_days": 2,
        "live_remaining_days": 2,
        "sb_knocked_in": True,
    }
    conditioned = ns["winrate_prepare_conditioned_template"](template, seed)
    defs = ns["winrate_resolve_scenario_definitions"](conditioned)
    labels = [str(x.get("label", "")) for x in defs if isinstance(x, dict)]
    ok = labels and all("未敲入" not in label for label in labels)
    return check(
        ok,
        "synthetic-snowball-filter",
        f"scenario labels trimmed after knock-in: {labels}",
        f"unexpected snowball live labels: {labels}",
    )


def pick_runtime_case(ns: Dict[str, Any], conn: sqlite3.Connection, rep_date_arg: Optional[str]) -> Tuple[Dict[str, Any], Dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    structs_df = ns["fetch_structures"](conn)
    prices_df = ns["fetch_prices"](conn)
    close2_df = ns["fetch_closes2"](conn)
    if structs_df.empty or prices_df.empty:
        raise RuntimeError("DB is missing structures or prices.")

    if rep_date_arg:
        rep_date = str(rep_date_arg).strip()
    else:
        rep_date = ns["infer_effective_asof_date"](prices_df, close2_df).strftime(ns["DATE_FMT"])

    struct_asof, _group_asof, bounds_asof = ns["compute_ledgers"](conn, as_of_date=rep_date)
    groups = ns["fetch_groups"](conn)
    gids = groups["group_id"].astype(str).tolist() if not groups.empty else structs_df["group_id"].astype(str).dropna().unique().tolist()
    for gid in gids:
        candidates = ns["probexp_build_structure_candidates"](
            structs_df=structs_df,
            struct_asof=struct_asof,
            bounds_asof=bounds_asof,
            prices_df=prices_df,
            close2_df=close2_df,
            rep_gid=str(gid),
            rep_date=str(rep_date),
            rep_und="全部",
            rep_und_all=True,
        )
        if candidates:
            return candidates[0], {"rep_date": rep_date, "gid": str(gid)}, structs_df, prices_df, close2_df
    raise RuntimeError(f"No accumulator candidate found for rep_date={rep_date}.")


def db_cross_special_consistency(ns: Dict[str, Any], conn: sqlite3.Connection, rep_date_arg: Optional[str]) -> List[CheckResult]:
    candidate, ctx, _structs_df, prices_df, close2_df = pick_runtime_case(ns, conn, rep_date_arg)
    rep_date = str(ctx["rep_date"])
    struct_asof, _group_asof, bounds_asof = ns["compute_ledgers"](conn, as_of_date=rep_date)
    snapshot = ns["probexp_build_structure_snapshot"](
        candidate=candidate,
        struct_asof=struct_asof,
        prices_df=prices_df,
        close2_df=close2_df,
        rep_date=rep_date,
        include_history=False,
    )
    resolved = candidate.get("resolved", {}) if isinstance(candidate.get("resolved", {}), dict) else {}
    current_price = float(pick_first(snapshot.get("current_close"), resolved.get("entry_price"), 0.0) or 0.0)
    seed = ns["special_build_runtime_state_seed"](
        struct_row=resolved,
        rep_date=rep_date,
        current_price=current_price,
        prices_df=prices_df,
        struct_asof=struct_asof,
        bounds_asof=bounds_asof,
        close2_df=close2_df,
    )
    template = ns["winrate_prepare_structure_template"](resolved)
    price_hist = prices_df[
        (prices_df["underlying"].astype(str) == str(pick_first(resolved.get("underlying"), "")))
        & (prices_df["dt"].astype(str) <= str(rep_date))
    ][["dt", "settle"]].copy()
    price_hist = price_hist.sort_values("dt").reset_index(drop=True)
    if price_hist.empty:
        return [CheckResult("db-cross-special-consistency", "skip", "no local price history for selected accumulator")]

    task1_live_history = ns["winrate_run_accumulator_history_backtest"](
        template,
        price_hist,
        bin_count=20,
        evaluation_basis="live",
        runtime_state_seed=seed,
    )
    task2_live_mc = ns["probexp_simulate_future_qty"](
        resolved,
        start_price=current_price,
        remaining_days=int(pick_first(seed.get("live_remaining_days"), 0) or 0),
        atm_iv_pct=25.0,
        skew=0.0,
        paths=10000,
        evaluation_basis="live",
        state_seed=seed,
        seed_hint="regression_special_conditioned_reval",
    )
    target_center = float(pick_first(snapshot.get("nominal_target_qty"), 0.0) or 0.0)
    target_lower, target_upper = ns["precise_hedge_default_target_bounds"](target_center, resolved.get("kind"))
    decision = ns["precise_hedge_build_decision_payload"](
        history_result=task1_live_history,
        mc_result=task2_live_mc,
        template=template,
        snapshot=snapshot,
        current_position=float(pick_first(snapshot.get("current_position_tons"), 0.0) or 0.0),
        target_center=target_center,
        target_lower=target_lower,
        target_upper=target_upper,
        scan_step_tons=500.0,
        scan_steps=8,
        fusion_mode="平衡",
        entry_price=resolved.get("entry_price"),
        rep_date=rep_date,
    )
    checks: List[CheckResult] = []
    hist_seed = task1_live_history.get("runtime_state_seed", {}) if isinstance(task1_live_history.get("runtime_state_seed", {}), dict) else {}
    mc_seed = task2_live_mc.get("runtime_state_seed", {}) if isinstance(task2_live_mc.get("runtime_state_seed", {}), dict) else {}
    fields = [
        "remaining_days",
        "live_remaining_days",
        "terminated",
        "manual_closed",
        "knocked_out",
        "cum_qty",
        "executed_qty",
        "remaining_cap_qty",
        "frozen_reason",
    ]
    mismatches: List[str] = []
    for field in fields:
        sv = pick_first(seed.get(field), "")
        hv = pick_first(hist_seed.get(field), "")
        mv = pick_first(mc_seed.get(field), "")
        if str(sv) != str(hv) or str(sv) != str(mv):
            mismatches.append(f"{field}: seed={sv} hist={hv} mc={mv}")
    checks.append(
        check(
            not mismatches,
            "db-cross-special-state",
            f"matched fields={fields}",
            " | ".join(mismatches[:6]),
        )
    )

    frozen_reason = str(pick_first(seed.get("frozen_reason"), task2_live_mc.get("frozen_reason"), "")).strip()
    if frozen_reason:
        future_qty = np.asarray(task2_live_mc.get("future_qty_paths"), dtype=float)
        checks.append(
            check(
                np.allclose(future_qty, 0.0),
                "db-frozen-future-zero",
                f"frozen={frozen_reason} future increment stayed zero",
                f"frozen={frozen_reason} but future paths not zero",
            )
        )
    else:
        checks.append(CheckResult("db-frozen-future-zero", "skip", "selected runtime case is not frozen"))

    checks.append(
        check(
            int(pick_first(seed.get("executed_qty"), 0) or 0) == int(pick_first(seed.get("cum_qty"), 0) or 0),
            "db-executed-alias",
            f"executed_qty aliases cum_qty={pick_first(seed.get('cum_qty'), 0)}",
            f"executed_qty={seed.get('executed_qty')} cum_qty={seed.get('cum_qty')}",
        )
    )
    checks.append(
        check(
            isinstance(decision, dict) and bool(decision),
            "db-precise-smoke",
            f"precise decision built for structure_id={candidate.get('structure_id')}",
            "precise decision payload is empty",
        )
    )
    return checks


def run_checks(db_path: Path, rep_date: Optional[str]) -> List[CheckResult]:
    app_path = db_path.parent / "app.py"
    ns = load_app_core_namespace(app_path)
    checks: List[CheckResult] = [
        synthetic_cap_freeze(ns),
        synthetic_snowball_knockin_filter(ns),
    ]
    conn = sqlite3.connect(str(db_path))
    try:
        checks.extend(db_cross_special_consistency(ns, conn, rep_date))
    finally:
        conn.close()
    return checks


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Regression checks for conditioned revaluation across special pages.")
    parser.add_argument("--db", default="otc_gui.db", help="Path to sqlite DB (default: otc_gui.db)")
    parser.add_argument("--rep-date", default="", help="Optional rep_date in YYYY-MM-DD")
    args = parser.parse_args(argv)

    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"DB not found: {db_path}", file=sys.stderr)
        return 2
    rep_date = str(args.rep_date).strip() or None
    if rep_date:
        parse_ymd(rep_date)

    checks = run_checks(db_path, rep_date)
    fail_count = 0
    skip_count = 0
    for item in checks:
        print(f"[{item.status.upper()}] {item.name}: {item.detail}")
        if item.status == "fail":
            fail_count += 1
        elif item.status == "skip":
            skip_count += 1
    print(f"summary: total={len(checks)} pass={len(checks) - fail_count - skip_count} skip={skip_count} fail={fail_count}")
    return 1 if fail_count else 0


if __name__ == "__main__":
    raise SystemExit(main())
