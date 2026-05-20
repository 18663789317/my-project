from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd
from pandas.testing import assert_frame_equal


def load_app_core_namespace(app_path: Path) -> Dict[str, Any]:
    src = app_path.read_text(encoding="utf-8-sig")
    cut_idx = src.find("\nst.set_page_config(")
    if cut_idx <= 0:
        raise RuntimeError("Cannot find Streamlit bootstrap in app.py.")
    ns: Dict[str, Any] = {}
    exec(compile(src[:cut_idx], str(app_path), "exec"), ns, ns)
    if "kind_cn_for_strategy" not in ns:
        ns["kind_cn_for_strategy"] = lambda kind, strategy_value: str(
            ns["direction_display_cn"](str(kind or "").upper())
        )
    return ns


def parse_date(value: str) -> date:
    return datetime.strptime(str(value).strip(), "%Y-%m-%d").date()


def list_group_dates(ns: Dict[str, Any], conn: Any, gid: str) -> List[str]:
    struct_df, group_df, _ = ns["compute_ledgers_cached"](conn, copy_out=False)
    close2_df = ns["fetch_closes2"](conn, copy=False)
    out: set[str] = set()
    if not struct_df.empty:
        out |= set(struct_df[struct_df["group_id"].astype(str) == str(gid)]["date"].astype(str).dropna().tolist())
    if not group_df.empty:
        out |= set(group_df[group_df["group_id"].astype(str) == str(gid)]["date"].astype(str).dropna().tolist())
    if not close2_df.empty:
        out |= set(close2_df[close2_df["group_id"].astype(str) == str(gid)]["dt"].astype(str).dropna().tolist())
    valid = []
    for raw in out:
        txt = str(raw).strip()
        if not txt:
            continue
        try:
            parse_date(txt)
        except Exception:
            continue
        valid.append(txt)
    valid.sort()
    return valid


def _compare_frames(left: pd.DataFrame, right: pd.DataFrame, label: str) -> None:
    assert_frame_equal(
        left.reset_index(drop=True),
        right.reset_index(drop=True),
        check_dtype=False,
        check_like=False,
        obj=label,
    )


def verify_asof_parity(ns: Dict[str, Any], conn: Any, gid: str, as_of_s: str) -> None:
    direct_struct, direct_group, direct_bounds = ns["compute_ledgers"](conn, as_of_date=as_of_s)
    cached_struct, cached_group, cached_bounds = ns["compute_ledgers_cached"](conn, as_of_date=as_of_s, copy_out=False)
    _compare_frames(direct_struct, cached_struct, f"struct parity {gid} {as_of_s}")
    _compare_frames(direct_group, cached_group, f"group parity {gid} {as_of_s}")
    _compare_frames(direct_bounds, cached_bounds, f"bounds parity {gid} {as_of_s}")


def build_monitor_inputs(ns: Dict[str, Any], conn: Any, gid: str, as_of_s: str) -> Dict[str, Any]:
    close2_df = ns["fetch_closes2"](conn, copy=False)
    adjustment_df = ns["fetch_structure_position_adjustments"](conn, copy=False)
    struct_asof, _, bounds_asof = ns["compute_ledgers_cached"](conn, as_of_date=as_of_s, copy_out=False)
    structs_df = ns["fetch_structures"](conn, copy=False)
    snowball_conv_df = ns["fetch_snowball_conversions"](conn, copy=False)
    rep_date_obj = ns["parse_date_maybe"](as_of_s)
    manual_reduce_qty_map = ns["build_manual_structure_reduction_qty_map"](
        close2_df,
        group_id=str(gid),
        as_of_date=rep_date_obj,
    )
    monitor_scope_meta = ns["build_monitor_structure_scope_meta_cached"](
        structs_df,
        rep_gid=str(gid),
        rep_und="全部",
        rep_date=as_of_s,
        rep_und_all=True,
        reduction_qty_map=manual_reduce_qty_map,
    )
    struct_df_scope = struct_asof[struct_asof["group_id"].astype(str) == str(gid)].copy()
    bounds_df_scope = bounds_asof[bounds_asof["group_id"].astype(str) == str(gid)].copy()
    dsub = struct_df_scope[struct_df_scope["date"].astype(str) == str(as_of_s)].copy()
    if dsub.empty and not struct_df_scope.empty:
        last_day = sorted(struct_df_scope["date"].astype(str).unique().tolist())[-1]
        dsub = struct_df_scope[struct_df_scope["date"].astype(str) == str(last_day)].copy()
    snowball_conv_asof = snowball_conv_df.copy()
    if not snowball_conv_asof.empty:
        for col in ("group_id", "underlying", "trigger_date"):
            if col not in snowball_conv_asof.columns:
                snowball_conv_asof[col] = ""
        snowball_conv_asof["group_id"] = snowball_conv_asof["group_id"].astype(str)
        snowball_conv_asof["underlying"] = snowball_conv_asof["underlying"].astype(str)
        snowball_conv_asof["trigger_date"] = snowball_conv_asof["trigger_date"].astype(str)
        snowball_conv_asof = snowball_conv_asof[
            (snowball_conv_asof["group_id"] == str(gid))
            & (snowball_conv_asof["trigger_date"] <= str(as_of_s))
        ].copy()
    return {
        "struct_df_scope": struct_df_scope,
        "dsub": dsub,
        "bounds_df_scope": bounds_df_scope,
        "close2_df": close2_df,
        "adjustment_df": adjustment_df,
        "snowball_conv_asof": snowball_conv_asof,
        "structs_df": structs_df,
        "monitor_scope_meta": monitor_scope_meta,
    }


def verify_runtime_parity_with_copies(ns: Dict[str, Any], conn: Any, gid: str, as_of_s: str) -> None:
    ns["_MONITOR_REPORT_MEMO_CACHE"].clear()
    inputs = build_monitor_inputs(ns, conn, gid, as_of_s)
    original = ns["build_monitor_report_runtime_cached"](
        inputs["struct_df_scope"],
        inputs["struct_df_scope"],
        inputs["dsub"],
        inputs["bounds_df_scope"],
        inputs["close2_df"],
        inputs["adjustment_df"],
        inputs["snowball_conv_asof"],
        inputs["structs_df"],
        rep_gid=str(gid),
        rep_und="全部",
        rep_date=as_of_s,
        rep_und_all=True,
        inactive_sid_block=set(),
    )
    copied = ns["build_monitor_report_runtime_cached"](
        inputs["struct_df_scope"].copy(),
        inputs["struct_df_scope"].copy(),
        inputs["dsub"].copy(),
        inputs["bounds_df_scope"].copy(),
        inputs["close2_df"].copy(),
        inputs["adjustment_df"].copy(),
        inputs["snowball_conv_asof"].copy(),
        inputs["structs_df"].copy(),
        rep_gid=str(gid),
        rep_und="全部",
        rep_date=as_of_s,
        rep_und_all=True,
        inactive_sid_block=set(),
    )
    for key, value in original.items():
        other = copied.get(key)
        if isinstance(value, pd.DataFrame):
            _compare_frames(value, other, f"runtime df parity {gid} {as_of_s} {key}")
        else:
            if value != other:
                raise AssertionError(f"runtime parity mismatch {gid} {as_of_s} key={key}")


def iter_scenarios(ns: Dict[str, Any], conn: Any, *, all_groups: bool, all_dates: bool) -> Iterable[Tuple[str, str]]:
    groups_df = ns["fetch_groups"](conn, copy=False)
    gids = sorted(groups_df["group_id"].astype(str).dropna().tolist()) if not groups_df.empty else []
    if not gids:
        return []
    for gid in gids if all_groups else gids[:1]:
        dates = list_group_dates(ns, conn, gid)
        if not dates:
            continue
        selected = dates if all_dates else [dates[-1]]
        for as_of_s in selected:
            yield gid, as_of_s


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify monitor perf optimizations do not change results.")
    parser.add_argument("--db", default="otc_gui.db", help="Path to sqlite DB.")
    parser.add_argument("--app", default="app.py", help="Path to app.py.")
    parser.add_argument("--all-groups", action="store_true", help="Check every strategy group.")
    parser.add_argument("--all-dates", action="store_true", help="Check every candidate date for each selected group.")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    app_path = Path(args.app).resolve()
    if not db_path.exists():
        print(f"[FAIL] DB not found: {db_path}")
        return 2
    if not app_path.exists():
        print(f"[FAIL] app.py not found: {app_path}")
        return 2

    ns = load_app_core_namespace(app_path)
    ns["DB_PATH"] = str(db_path)
    conn = ns["get_conn"]()
    try:
        scenarios = list(iter_scenarios(ns, conn, all_groups=bool(args.all_groups), all_dates=bool(args.all_dates)))
        if not scenarios:
            print("[FAIL] No scenarios found.")
            return 2
        print("=== Monitor Perf Safety Verification ===")
        for idx, (gid, as_of_s) in enumerate(scenarios, start=1):
            print(f"[RUN] {idx}/{len(scenarios)} group={gid} asof={as_of_s}")
            verify_asof_parity(ns, conn, gid, as_of_s)
            verify_runtime_parity_with_copies(ns, conn, gid, as_of_s)
            print(f"[PASS] group={gid} asof={as_of_s}")
        print(f"[PASS] all scenarios={len(scenarios)}")
        return 0
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        return 1
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
