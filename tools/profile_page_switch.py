from __future__ import annotations

import argparse
import cProfile
import io
import logging
import pstats
import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Sequence, Tuple


APP_FILE = Path(__file__).resolve().parents[1] / "app.py"


def _quiet_streamlit_logs() -> None:
    logging.disable(logging.CRITICAL)
    warnings.filterwarnings("ignore", category=FutureWarning)
    for logger_name in (
        "streamlit",
        "streamlit.runtime",
        "streamlit.runtime.scriptrunner_utils.script_run_context",
        "streamlit.runtime.state.session_state_proxy",
    ):
        logging.getLogger(logger_name).setLevel(logging.ERROR)


def load_app_namespace() -> Dict[str, Any]:
    text = APP_FILE.read_text(encoding="utf-8-sig")
    lines = text.splitlines(True)
    cut = next(
        idx
        for idx, line in enumerate(lines)
        if line.lstrip().startswith("st.set_page_config(")
    )
    ns: Dict[str, Any] = {}
    exec(compile("".join(lines[:cut]), "app_partial.py", "exec"), ns)
    if "kind_cn_for_strategy" not in ns:
        ns["kind_cn_for_strategy"] = lambda kind, strategy_value: str(
            ns["direction_display_cn"](str(kind or "").upper())
        )
    return ns


def pick_default_monitor_date(ns: Dict[str, Any], options: Sequence[str]) -> str:
    if not options:
        return ""
    parsed: List[Tuple[str, Any]] = []
    for raw in options:
        value = str(raw).strip()
        if not value:
            continue
        parsed_date = ns["parse_date_maybe"](value)
        if parsed_date is not None:
            parsed.append((value, parsed_date))
    if parsed:
        parsed.sort(key=lambda item: item[1])
        return parsed[-1][0]
    return sorted(str(x).strip() for x in options if str(x).strip())[-1]


@dataclass
class StepRow:
    name: str
    seconds: float
    rows: int | None = None
    note: str = ""


class StepCollector:
    def __init__(self) -> None:
        self.rows: List[StepRow] = []

    @contextmanager
    def track(self, name: str, *, row_getter: Callable[[], int | None] | None = None, note: str = ""):
        started = time.perf_counter()
        result_rows: int | None = None
        try:
            yield
        finally:
            if row_getter is not None:
                try:
                    result_rows = row_getter()
                except Exception:
                    result_rows = None
            self.rows.append(
                StepRow(
                    name=str(name),
                    seconds=float(time.perf_counter() - started),
                    rows=result_rows,
                    note=str(note or ""),
                )
            )


def _top_local_stats(profile: cProfile.Profile, *, topn: int) -> List[Tuple[float, float, int, str]]:
    stats = pstats.Stats(profile)
    rows: List[Tuple[float, float, int, str]] = []
    for (filename, line_no, func_name), values in stats.stats.items():
        if filename != "app_partial.py":
            continue
        primitive_calls, total_calls, total_time, cumulative_time, _callers = values
        label = f"{func_name} @ L{line_no}"
        rows.append((float(cumulative_time), float(total_time), int(total_calls), label))
    rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return rows[:topn]


def _first_non_empty(values: Iterable[Any]) -> str:
    for raw in values:
        value = str(raw).strip()
        if value:
            return value
    return ""


def _kind_cn_for_strategy(ns: Dict[str, Any], kind: Any, strategy_value: Any) -> str:
    if callable(ns.get("kind_cn_for_strategy")):
        return str(ns["kind_cn_for_strategy"](kind, strategy_value))
    return str(ns["direction_display_cn"](str(kind or "").upper()))


def profile_option_warehouse(ns: Dict[str, Any]) -> Dict[str, Any]:
    conn = ns["get_conn"]()
    steps = StepCollector()
    profile = cProfile.Profile()
    profile.enable()
    started = time.perf_counter()

    with steps.track("fetch_groups"):
        groups_df = ns["fetch_groups"](conn, copy=False)
    with steps.track("fetch_structures"):
        structs_df = ns["fetch_structures"](conn, copy=False)
    with steps.track("fetch_closes2"):
        close2_df = ns["fetch_closes2"](conn, copy=False)
    with steps.track("fetch_snowball_conversions"):
        snowball_conv_df = ns["fetch_snowball_conversions"](conn, copy=False)
    with steps.track("fetch_prices"):
        prices_df = ns["fetch_prices"](conn, copy=False)
    with steps.track("infer_effective_asof_date"):
        asof_date = ns["infer_effective_asof_date"](prices_df, close2_df)

    group_id = _first_non_empty(groups_df.get("group_id", []).tolist())
    sub = structs_df[structs_df["group_id"].astype(str) == str(group_id)].copy() if not structs_df.empty else structs_df.copy()

    with steps.track("build_manual_close_date_map"):
        manual_close_map = ns["build_manual_close_date_map"](close2_df, group_id=str(group_id), as_of_date=asof_date)
    with steps.track("compute_ledgers_cached(full)", row_getter=lambda: int(len(warehouse_struct_df))):
        warehouse_struct_df, _group_all_ignore, _bounds_all_ignore = ns["compute_ledgers_cached"](conn, copy_out=False)
    with steps.track("build_melt_date_map"):
        melt_date_map = ns["build_melt_date_map"](warehouse_struct_df, group_id=str(group_id), as_of_date=asof_date)
    with steps.track("build_melt_status_map"):
        _melt_status_map = ns["build_melt_status_map"](warehouse_struct_df, group_id=str(group_id), as_of_date=asof_date)

    warehouse_group_df = (
        warehouse_struct_df[warehouse_struct_df["group_id"].astype(str) == str(group_id)].copy()
        if not warehouse_struct_df.empty
        else warehouse_struct_df.copy()
    )
    close2_group_df = (
        close2_df[close2_df["group_id"].astype(str) == str(group_id)].copy()
        if not close2_df.empty
        else close2_df.copy()
    )
    warehouse_date_options = sorted(
        set(warehouse_group_df.get("date", []).astype(str).unique().tolist())
        | set(close2_group_df.get("dt", []).astype(str).unique().tolist() if not close2_group_df.empty else [])
    )
    warehouse_asof = warehouse_date_options[-1] if warehouse_date_options else ""
    warehouse_cut = (
        warehouse_group_df[warehouse_group_df["date"].astype(str) <= str(warehouse_asof)].copy()
        if not warehouse_group_df.empty
        else warehouse_group_df.copy()
    )

    with steps.track("fetch_structure_position_adjustments"):
        adjustment_df = ns["fetch_structure_position_adjustments"](conn, copy=False)
    with steps.track("build_open_lot_rows", row_getter=lambda: int(len(open_lots))):
        open_lots = ns["build_open_lot_rows"](
            warehouse_cut,
            close2_group_df,
            str(warehouse_asof),
            adjustment_df,
        )

    def build_structure_table() -> Any:
        meta_map: Dict[str, Dict[str, Any]] = {}
        if not sub.empty:
            for _, row in sub.iterrows():
                structure_id = str(row.get("structure_id", "")).strip()
                if not structure_id:
                    continue
                meta_map[structure_id] = {
                    "structure_code": ns["resolve_structure_display_code"](
                        row.get("structure_id", ""),
                        row.get("structure_code", ""),
                    ),
                    "name": row.get("name", ""),
                    "risk_party": row.get("risk_party", ""),
                    "kind": row.get("kind", ""),
                    "underlying": row.get("underlying", ""),
                    "strategy_code": ns["pick_first"](row.get("strategy_code"), row.get("strategy"), ""),
                    "entry_price": ns["pick_first"](
                        ns["to_float"](row.get("entry_price")),
                        ns["to_float"](row.get("gen_price")),
                    ),
                    "strike_price": ns["to_float"](row.get("strike_price")),
                    "barrier_in": ns["to_float"](row.get("barrier_in")),
                    "barrier_out": ns["to_float"](ns["pick_first"](row.get("barrier_out"), row.get("barrier_price"))),
                }
        work = open_lots.copy()
        if work.empty:
            return work
        work["open_value"] = (
            ns["pd"].to_numeric(work.get("open_qty"), errors="coerce").fillna(0.0)
            * ns["pd"].to_numeric(work.get("gen_price"), errors="coerce").fillna(0.0)
        )
        grouped = work.groupby(
            ["structure_id", "name", "risk_party", "underlying", "kind", "strategy_code"],
            as_index=False,
        ).agg(
            open_qty_sum=("open_qty", "sum"),
            open_value_sum=("open_value", "sum"),
        )
        grouped["open_avg_price"] = grouped.apply(
            lambda row: (
                float(row["open_value_sum"]) / float(row["open_qty_sum"])
                if float(row["open_qty_sum"]) > 1e-12
                else 0.0
            ),
            axis=1,
        )
        grouped["direction_cn"] = grouped.apply(
            lambda row: _kind_cn_for_strategy(ns, row.get("kind"), row.get("strategy_code")),
            axis=1,
        )
        grouped["structure_label"] = grouped.apply(
            lambda row: ns["structure_verbose_label"](
                meta_map.get(str(row.get("structure_id", "")), {}).get("structure_code", row.get("structure_id", "")),
                meta_map.get(str(row.get("structure_id", "")), {}).get("name", row.get("name", "")),
                meta_map.get(str(row.get("structure_id", "")), {}).get("risk_party", row.get("risk_party", "")),
                meta_map.get(str(row.get("structure_id", "")), {}).get("kind", row.get("kind", "")),
                meta_map.get(str(row.get("structure_id", "")), {}).get("underlying", row.get("underlying", "")),
                meta_map.get(str(row.get("structure_id", "")), {}).get("entry_price"),
                meta_map.get(str(row.get("structure_id", "")), {}).get("strike_price"),
                strategy_value=meta_map.get(str(row.get("structure_id", "")), {}).get("strategy_code", ""),
                knock_in_price=meta_map.get(str(row.get("structure_id", "")), {}).get("barrier_in"),
                barrier_price=ns["resolve_display_barrier_price"](
                    meta_map.get(str(row.get("structure_id", "")), {}).get("strategy_code", ""),
                    barrier_out=meta_map.get(str(row.get("structure_id", "")), {}).get("barrier_out"),
                    barrier_in=meta_map.get(str(row.get("structure_id", "")), {}).get("barrier_in"),
                    strike_price=meta_map.get(str(row.get("structure_id", "")), {}).get("strike_price"),
                ),
            ),
            axis=1,
        )
        return grouped

    with steps.track("build_structure_table_base", row_getter=lambda: int(len(structure_table))):
        structure_table = build_structure_table()

    total_seconds = float(time.perf_counter() - started)
    profile.disable()
    return {
        "page": "option_warehouse",
        "group_id": str(group_id),
        "date": str(warehouse_asof),
        "total_seconds": total_seconds,
        "steps": steps.rows,
        "top_local_stats": _top_local_stats(profile, topn=18),
        "meta": {
            "groups": int(len(groups_df)),
            "structures": int(len(structs_df)),
            "warehouse_rows": int(len(warehouse_struct_df)),
            "warehouse_group_rows": int(len(warehouse_group_df)),
            "open_lot_rows": int(len(open_lots)),
            "structure_table_rows": int(len(structure_table)),
            "close_rows": int(len(close2_df)),
            "manual_closed_count": int(len(manual_close_map)),
            "melted_count": int(len(melt_date_map)),
            "snowball_conversion_rows": int(len(snowball_conv_df)),
        },
    }


def profile_monitor(ns: Dict[str, Any]) -> Dict[str, Any]:
    conn = ns["get_conn"]()
    steps = StepCollector()
    profile = cProfile.Profile()
    profile.enable()
    started = time.perf_counter()

    with steps.track("run_core_syncs_if_needed"):
        ns["_run_core_syncs_if_needed"](conn)
    with steps.track("fetch_closes2"):
        close2_df = ns["fetch_closes2"](conn, copy=False)
    with steps.track("fetch_structure_position_adjustments"):
        adjustment_df = ns["fetch_structure_position_adjustments"](conn, copy=False)
    with steps.track("fetch_prices"):
        prices_df = ns["fetch_prices"](conn, copy=False)
    with steps.track("compute_ledgers_cached(full)", row_getter=lambda: int(len(struct_df))):
        struct_df, group_df, bounds_df = ns["compute_ledgers_cached"](conn, copy_out=False)
    with steps.track("fetch_snowball_conversions"):
        snowball_conv_df = ns["fetch_snowball_conversions"](conn, copy=False)
    with steps.track("fetch_spot_hedge_logs"):
        spot_match_df = ns["fetch_spot_hedge_logs"](conn, copy=False)
    with steps.track("fetch_structures"):
        structs_df = ns["fetch_structures"](conn, copy=False)
    with steps.track("fetch_groups"):
        groups_df = ns["fetch_groups"](conn, copy=False)

    gid_options = sorted(struct_df["group_id"].astype(str).dropna().unique().tolist()) if not struct_df.empty else []
    group_id = gid_options[0] if gid_options else ""
    rep_date_set: set[str] = set()
    if not struct_df.empty:
        rep_date_set |= set(
            struct_df[struct_df["group_id"].astype(str) == str(group_id)]["date"].astype(str).dropna().tolist()
        )
    if not group_df.empty:
        rep_date_set |= set(
            group_df[group_df["group_id"].astype(str) == str(group_id)]["date"].astype(str).dropna().tolist()
        )
    if not close2_df.empty:
        rep_date_set |= set(
            close2_df[close2_df["group_id"].astype(str) == str(group_id)]["dt"].astype(str).dropna().tolist()
        )
    report_date = pick_default_monitor_date(ns, sorted(rep_date_set))
    report_underlying = "全部"
    report_underlying_all = True

    with steps.track("compute_ledgers_cached(asof)", row_getter=lambda: int(len(struct_asof))):
        struct_asof, group_asof, bounds_asof = ns["compute_ledgers_cached"](
            conn,
            as_of_date=str(report_date),
            copy_out=False,
        )
    report_date_obj = ns["parse_date_maybe"](report_date)
    with steps.track("build_manual_close_date_map"):
        manual_close_map = ns["build_manual_close_date_map"](
            close2_df,
            group_id=str(group_id),
            as_of_date=report_date_obj,
        )
    with steps.track("build_manual_structure_reduction_qty_map"):
        manual_reduction_map = ns["build_manual_structure_reduction_qty_map"](
            close2_df,
            group_id=str(group_id),
            as_of_date=report_date_obj,
        )
    with steps.track("build_melt_date_map"):
        melt_date_map = ns["build_melt_date_map"](
            struct_asof,
            group_id=str(group_id),
            as_of_date=report_date_obj,
        )
    with steps.track("build_melt_status_map"):
        melt_status_map = ns["build_melt_status_map"](
            struct_asof,
            group_id=str(group_id),
            as_of_date=report_date_obj,
        )
    inactive_sid_block = {
        str(value).strip()
        for value in (set(manual_close_map.keys()) | set(melt_date_map.keys()))
        if str(value).strip()
    }

    with steps.track("build_monitor_gap_scope_cached"):
        gap_scope = ns["build_monitor_gap_scope_cached"](
            structs_df,
            struct_asof,
            prices_df,
            close2_df,
            rep_gid=str(group_id),
            rep_und=str(report_underlying),
            rep_date=str(report_date),
            rep_und_all=bool(report_underlying_all),
            inactive_sid_block=inactive_sid_block,
            manual_reduce_qty_map=manual_reduction_map,
            manual_close_date_map=manual_close_map,
            melt_date_map=melt_date_map,
            melt_status_map=melt_status_map,
        )
    with steps.track("build_monitor_structure_scope_meta_cached"):
        scope_meta = ns["build_monitor_structure_scope_meta_cached"](
            structs_df,
            rep_gid=str(group_id),
            rep_und=str(report_underlying),
            rep_date=str(report_date),
            rep_und_all=bool(report_underlying_all),
            reduction_qty_map=manual_reduction_map,
        )

    daily_struct_df = (
        struct_df[struct_df["date"].astype(str) == str(report_date)].copy()
        if not struct_df.empty
        else struct_df.copy()
    )
    with steps.track("build_monitor_report_runtime_cached"):
        report_runtime = ns["build_monitor_report_runtime_cached"](
            struct_df,
            struct_df,
            daily_struct_df,
            bounds_df,
            close2_df,
            adjustment_df,
            snowball_conv_df,
            structs_df,
            rep_gid=str(group_id),
            rep_und=str(report_underlying),
            rep_date=str(report_date),
            rep_und_all=bool(report_underlying_all),
            inactive_sid_block=inactive_sid_block,
        )
    with steps.track("build_structure_code_map"):
        structure_code_map = ns["build_structure_code_map"](structs_df)

    structure_daily = struct_df.iloc[0:0].copy()
    group_daily = group_df.iloc[0:0].copy()
    bounds_frame = bounds_asof.iloc[0:0].copy()
    with steps.track("build_monitor_overview_frame_cached"):
        overview_frame = ns["build_monitor_overview_frame_cached"](
            bounds_asof,
            rep_gid=str(group_id),
            rep_und=str(report_underlying),
            rep_date=str(report_date),
            manual_closed_sids=set(manual_close_map.keys()),
            structure_code_map=structure_code_map,
            sid_direction_display_map=scope_meta.get("sid_direction_display_map", {}),
            sid_buy_sell_direction_map=scope_meta.get("sid_buy_sell_direction_map", {}),
            sid_risk_party_map=scope_meta.get("sid_risk_party_map", {}),
            sid_strategy_code_map=scope_meta.get("sid_strategy_code_map", {}),
            sid_structure_detail_label_map=scope_meta.get("sid_structure_detail_label_map", {}),
            sid_is_snowball_map=scope_meta.get("sid_is_snowball_map", {}),
            sid_snowball_discount_enabled_map=scope_meta.get("sid_snowball_discount_enabled_map", {}),
            sid_snowball_next_ko_text_map=scope_meta.get("sid_snowball_next_ko_text_map", {}),
            struct_scale_map_overview=scope_meta.get("struct_scale_map_overview", {}),
            struct_end_date_map_overview=scope_meta.get("struct_end_date_map_overview", {}),
            rep_state_map=report_runtime.get("rep_state_map", {}),
            rep_snowball_coupon_pct_map=report_runtime.get("rep_snowball_coupon_pct_map", {}),
            sb_phase_map=report_runtime.get("sb_phase_map", {}),
            sb_ko_line_map=report_runtime.get("sb_ko_line_map", {}),
            current_float_map=report_runtime.get("current_float_map", {}),
            sb_knocked_in_map=report_runtime.get("sb_knocked_in_map", {}),
            sb_first_ki_map=report_runtime.get("sb_first_ki_map", {}),
            sb_discount_map=report_runtime.get("sb_discount_map", {}),
            sb_convert_qty_map=report_runtime.get("sb_convert_qty_map", {}),
            sb_convert_px_map=report_runtime.get("sb_convert_px_map", {}),
            sb_fut_float_map=report_runtime.get("sb_fut_float_map", {}),
            finished_sid_set=set(),
        )

    total_seconds = float(time.perf_counter() - started)
    profile.disable()
    return {
        "page": "monitor",
        "group_id": str(group_id),
        "date": str(report_date),
        "total_seconds": total_seconds,
        "steps": steps.rows,
        "top_local_stats": _top_local_stats(profile, topn=20),
        "meta": {
            "groups": int(len(groups_df)),
            "structures": int(len(structs_df)),
            "struct_rows": int(len(struct_df)),
            "group_rows": int(len(group_df)),
            "bounds_rows": int(len(bounds_df)),
            "close_rows": int(len(close2_df)),
            "spot_match_rows": int(len(spot_match_df)),
            "gap_active_rows": int(len(gap_scope.get("gap_active", []))),
            "structure_daily_rows": int(len(structure_daily)),
            "group_daily_rows": int(len(group_daily)),
            "bounds_frame_rows": int(len(bounds_frame)),
            "overview_rows": int(len(overview_frame)),
        },
    }


def print_report(result: Dict[str, Any]) -> None:
    print(f"\n=== {result['page']} ===")
    print(f"group_id={result['group_id']}  date={result['date']}")
    print(f"total={result['total_seconds']:.3f}s")
    print("meta:")
    for key, value in result["meta"].items():
        print(f"  - {key}: {value}")
    print("steps:")
    ordered_steps = sorted(result["steps"], key=lambda row: row.seconds, reverse=True)
    for row in ordered_steps:
        extra = []
        if row.rows is not None:
            extra.append(f"rows={row.rows}")
        if row.note:
            extra.append(row.note)
        suffix = f" ({', '.join(extra)})" if extra else ""
        print(f"  - {row.name}: {row.seconds:.3f}s{suffix}")
    print("top_local_functions:")
    for cumulative_time, total_time, total_calls, label in result["top_local_stats"]:
        print(
            f"  - {label}: cum={cumulative_time:.3f}s, self={total_time:.3f}s, calls={total_calls}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile slow page-switch data pipelines.")
    parser.add_argument(
        "--page",
        choices=["monitor", "option_warehouse", "both"],
        default="both",
        help="Which page pipeline to profile.",
    )
    args = parser.parse_args()

    _quiet_streamlit_logs()

    if args.page in {"option_warehouse", "both"}:
        print_report(profile_option_warehouse(load_app_namespace()))
    if args.page in {"monitor", "both"}:
        print_report(profile_monitor(load_app_namespace()))


if __name__ == "__main__":
    main()
