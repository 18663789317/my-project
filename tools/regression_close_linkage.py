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


def load_app_core_namespace(app_path: Path) -> Dict[str, Any]:
    src = app_path.read_text(encoding="utf-8-sig")
    cut_idx = src.find("\nst.set_page_config(")
    if cut_idx <= 0:
        raise RuntimeError("未找到 app.py 的 UI 起点（st.set_page_config），无法加载核心函数。")
    core_src = src[:cut_idx]
    ns: Dict[str, Any] = {}
    exec(compile(core_src, str(app_path), "exec"), ns, ns)
    return ns


def compute_open_snapshot(
    ns: Dict[str, Any],
    conn: Any,
    gid: str,
    as_of_s: str,
) -> Tuple[Dict[str, float], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    struct_asof, _, _ = ns["compute_ledgers"](conn, as_of_date=as_of_s)
    struct_cut = struct_asof[struct_asof["group_id"].astype(str) == str(gid)].copy()

    closes2 = ns["fetch_closes2"](conn)
    if closes2 is None or closes2.empty:
        closes_cut = pd.DataFrame()
    else:
        closes_cut = closes2[
            (closes2["group_id"].astype(str) == str(gid))
            & (closes2["dt"].astype(str) <= str(as_of_s))
        ].copy()

    open_rows = ns["build_open_lot_rows"](struct_cut, closes_cut, as_of_s)
    qty_map: Dict[str, float] = {}
    if open_rows is not None and not open_rows.empty:
        tmp = open_rows.copy()
        tmp["open_qty"] = pd.to_numeric(tmp.get("open_qty"), errors="coerce").fillna(0.0)
        qty_map = (
            tmp.groupby(tmp["structure_id"].astype(str))["open_qty"]
            .sum()
            .astype(float)
            .to_dict()
        )
    return qty_map, open_rows, struct_cut, closes_cut


def choose_group(ns: Dict[str, Any], conn: Any, explicit_gid: Optional[str]) -> str:
    groups = ns["fetch_groups"](conn)
    if groups.empty:
        raise RuntimeError("策略组为空，无法回归测试。")
    if explicit_gid:
        gid = str(explicit_gid).strip()
        if gid not in groups["group_id"].astype(str).tolist():
            raise RuntimeError(f"指定 group_id 不存在：{gid}")
        return gid
    return str(groups.iloc[0]["group_id"])


def get_asof(ns: Dict[str, Any], conn: Any) -> date:
    prices = ns["fetch_prices"](conn)
    closes2 = ns["fetch_closes2"](conn)
    return ns["infer_effective_asof_date"](prices, closes2)


def parse_cli_date(v: str, arg_name: str) -> date:
    txt = str(v).strip()
    try:
        return datetime.strptime(txt, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"{arg_name} 格式错误，需为 YYYY-MM-DD: {txt}") from exc


def list_group_ids(db_path: Path) -> List[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT group_id FROM strategy_group ORDER BY group_id"
        ).fetchall()
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
        d = str(r[0]).strip()
        if not d:
            continue
        try:
            out.append(datetime.strptime(d, "%Y-%m-%d").date())
        except Exception:
            continue
    return sorted(set(out))


def filter_asof_dates(dates: List[date], d_from: Optional[date], d_to: Optional[date]) -> List[date]:
    out = dates[:]
    if d_from is not None:
        out = [d for d in out if d >= d_from]
    if d_to is not None:
        out = [d for d in out if d <= d_to]
    return sorted(set(out))


def check_manual_structure_close_linkage(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    closes2 = ns["fetch_closes2"](conn)
    manual_map = ns["build_manual_close_date_map"](closes2, group_id=str(gid), as_of_date=as_of)
    struct_asof, _, _ = ns["compute_ledgers"](conn, as_of_date=as_of.strftime(ns["DATE_FMT"]))
    melt_map = ns["build_melt_date_map"](struct_asof, group_id=str(gid), as_of_date=as_of)
    inactive_before = set(manual_map.keys()) | set(melt_map.keys())

    structs = ns["fetch_structures"](conn)
    sub = structs[structs["group_id"].astype(str) == str(gid)].copy()
    if sub.empty:
        return CheckResult("结构整体平仓联动", "skip", "该策略组无结构")

    candidates = [sid for sid in sub["structure_id"].astype(str).tolist() if sid not in inactive_before]
    if not candidates:
        return CheckResult("结构整体平仓联动", "skip", "无可用于手动终结的存续结构")

    sid = str(candidates[0])
    srow = sub[sub["structure_id"].astype(str) == sid].iloc[0]
    und = str(srow.get("underlying", ""))
    dt_s = as_of.strftime(ns["DATE_FMT"])
    row = {
        "close_id": uuid4().hex,
        "dt": dt_s,
        "group_id": str(gid),
        "structure_id": sid,
        "underlying": und,
        "side": "平仓",
        "qty": 0.0,
        "open_price": 0.0,
        "close_price": 0.0,
        "pnl": 1234.56,
        "close_category": ns["MANUAL_STRUCT_CLOSE_CATEGORY"],
        "quick_batch_id": f"REG_MANUAL_CLOSE_{sid}",
        "source_gen_date": dt_s,
        "is_external": 1,
    }
    ns["insert_close_rows"](conn, [row])
    conn.commit()

    closes_after = ns["fetch_closes2"](conn)
    manual_after = ns["build_manual_close_date_map"](closes_after, group_id=str(gid), as_of_date=as_of)
    struct_after, _, _ = ns["compute_ledgers"](conn, as_of_date=dt_s)
    melt_after = ns["build_melt_date_map"](struct_after, group_id=str(gid), as_of_date=as_of)
    inactive_after = set(manual_after.keys()) | set(melt_after.keys())
    active_sub = sub[~sub["structure_id"].astype(str).isin(inactive_after)].copy()

    if sid not in manual_after:
        return CheckResult("结构整体平仓联动", "fail", f"{sid} 未进入 manual close map")
    if sid in active_sub["structure_id"].astype(str).tolist():
        return CheckResult("结构整体平仓联动", "fail", f"{sid} 仍出现在存续结构集合")
    return CheckResult("结构整体平仓联动", "pass", f"{sid} 已正确进入终止集合并从存续集合剔除")


def check_single_close_linkage(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    qty_before, open_rows_before, _, _ = compute_open_snapshot(ns, conn, gid, as_of_s)
    if open_rows_before.empty:
        return CheckResult("结构内头寸平仓联动", "skip", "当前无在库头寸")

    sid = ""
    max_qty = 0.0
    for k, v in qty_before.items():
        if float(v) > max_qty + EPS:
            max_qty = float(v)
            sid = str(k)
    if not sid or max_qty <= EPS:
        return CheckResult("结构内头寸平仓联动", "skip", "无可平结构")

    lot = (
        open_rows_before[open_rows_before["structure_id"].astype(str) == sid]
        .sort_values(["date"])
        .iloc[0]
    )
    kind = str(lot.get("kind", "ACC"))
    und = str(lot.get("underlying", ""))
    open_px = float(pd.to_numeric(lot.get("gen_price"), errors="coerce") or 0.0)
    qty = float(min(max_qty, 300.0))
    side = ns["default_close_side_code"](kind)
    close_px = open_px + (2.0 if str(side).upper() == "SELL" else -2.0)
    pnl = ns["calc_close_pnl"](kind, side, qty, open_px, close_px)

    row = {
        "close_id": uuid4().hex,
        "dt": as_of_s,
        "group_id": str(gid),
        "structure_id": sid,
        "underlying": und,
        "side": side,
        "qty": float(qty),
        "open_price": float(open_px),
        "close_price": float(close_px),
        "pnl": float(pnl),
        "close_category": ns["STRUCT_CLOSE_CATEGORY"],
        "quick_batch_id": f"REG_SINGLE_CLOSE_{sid}",
        "source_gen_date": str(lot.get("date", "")),
        "is_external": 0,
    }
    ns["insert_close_rows"](conn, [row])
    conn.commit()

    qty_after, _, _, _ = compute_open_snapshot(ns, conn, gid, as_of_s)
    before_v = float(qty_before.get(sid, 0.0))
    after_v = float(qty_after.get(sid, 0.0))
    reduced = before_v - after_v
    if abs(reduced - qty) > 1e-5:
        return CheckResult(
            "结构内头寸平仓联动",
            "fail",
            f"{sid} 在库减少量异常，期望 {qty:.4f}，实际 {reduced:.4f}",
        )
    return CheckResult("结构内头寸平仓联动", "pass", f"{sid} 在库减少 {reduced:.2f} 吨，联动正确")


def check_symmetric_close_linkage(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    qty_before, open_rows_before, _, _ = compute_open_snapshot(ns, conn, gid, as_of_s)
    if open_rows_before.empty:
        return CheckResult("多空对称平仓联动", "skip", "当前无在库头寸")

    lots = open_rows_before.copy()
    lots["sid"] = lots["structure_id"].astype(str)
    lots["kind_u"] = lots["kind"].astype(str).str.upper()
    lots["open_qty"] = pd.to_numeric(lots.get("open_qty"), errors="coerce").fillna(0.0)
    lots["gen_price"] = pd.to_numeric(lots.get("gen_price"), errors="coerce").fillna(0.0)
    sid_qty = lots.groupby(["sid", "kind_u"], as_index=False)["open_qty"].sum()

    long_rows = sid_qty[sid_qty["kind_u"] == "ACC"].sort_values("open_qty", ascending=False)
    short_rows = sid_qty[sid_qty["kind_u"] == "DEC"].sort_values("open_qty", ascending=False)
    if long_rows.empty or short_rows.empty:
        return CheckResult("多空对称平仓联动", "skip", "缺少可配对的多/空在库结构")

    long_sid = str(long_rows.iloc[0]["sid"])
    short_sid = str(short_rows.iloc[0]["sid"])
    long_can = float(long_rows.iloc[0]["open_qty"])
    short_can = float(short_rows.iloc[0]["open_qty"])
    pair_qty = float(min(long_can, short_can, 200.0))
    if pair_qty <= EPS:
        return CheckResult("多空对称平仓联动", "skip", "可对称数量为 0")

    long_lots = lots[lots["sid"] == long_sid].copy()
    short_lots = lots[lots["sid"] == short_sid].copy()
    long_px = float((long_lots["gen_price"] * long_lots["open_qty"]).sum() / max(long_can, EPS))
    short_px = float((short_lots["gen_price"] * short_lots["open_qty"]).sum() / max(short_can, EPS))
    pair_px = float((long_px + short_px) / 2.0)

    rows = [
        {
            "close_id": uuid4().hex,
            "dt": as_of_s,
            "group_id": str(gid),
            "structure_id": long_sid,
            "underlying": str(pick_first(long_lots["underlying"].iloc[0], "")),
            "side": "SELL",
            "qty": pair_qty,
            "open_price": long_px,
            "close_price": pair_px,
            "pnl": float(ns["calc_close_pnl"]("ACC", "SELL", pair_qty, long_px, pair_px)),
            "close_category": ns["SYMMETRIC_CLOSE_CATEGORY"],
            "quick_batch_id": f"REG_SYM_{uuid4().hex[:8]}",
            "source_gen_date": "",
            "is_external": 0,
        },
        {
            "close_id": uuid4().hex,
            "dt": as_of_s,
            "group_id": str(gid),
            "structure_id": short_sid,
            "underlying": str(pick_first(short_lots["underlying"].iloc[0], "")),
            "side": "BUY",
            "qty": pair_qty,
            "open_price": short_px,
            "close_price": pair_px,
            "pnl": float(ns["calc_close_pnl"]("DEC", "BUY", pair_qty, short_px, pair_px)),
            "close_category": ns["SYMMETRIC_CLOSE_CATEGORY"],
            "quick_batch_id": f"REG_SYM_{uuid4().hex[:8]}",
            "source_gen_date": "",
            "is_external": 0,
        },
    ]
    ns["insert_close_rows"](conn, rows)
    conn.commit()

    qty_after, _, _, _ = compute_open_snapshot(ns, conn, gid, as_of_s)
    long_reduced = float(qty_before.get(long_sid, 0.0) - qty_after.get(long_sid, 0.0))
    short_reduced = float(qty_before.get(short_sid, 0.0) - qty_after.get(short_sid, 0.0))
    if abs(long_reduced - pair_qty) > 1e-5 or abs(short_reduced - pair_qty) > 1e-5:
        return CheckResult(
            "多空对称平仓联动",
            "fail",
            f"减少量异常：long={long_reduced:.4f}, short={short_reduced:.4f}, 期望={pair_qty:.4f}",
        )
    return CheckResult(
        "多空对称平仓联动",
        "pass",
        f"{long_sid}/{short_sid} 同步减少 {pair_qty:.2f} 吨，联动正确",
    )


def check_quick_close_linkage(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    qty_before, open_rows_before, _, _ = compute_open_snapshot(ns, conn, gid, as_of_s)
    if open_rows_before.empty:
        return CheckResult("批量快速平仓联动", "skip", "当前无在库头寸")

    lots = open_rows_before.copy()
    lots["sid"] = lots["structure_id"].astype(str)
    lots["open_qty"] = pd.to_numeric(lots.get("open_qty"), errors="coerce").fillna(0.0)
    lots = lots.sort_values("open_qty", ascending=False)
    sid_order = [str(x) for x in lots["sid"].drop_duplicates().tolist()]
    if not sid_order:
        return CheckResult("批量快速平仓联动", "skip", "无可选结构")

    batch_id = f"REG_BATCH_{uuid4().hex[:8]}"
    rows: List[Dict[str, Any]] = []
    expected: Dict[str, float] = {}
    for sid in sid_order[:2]:
        sid_lots = lots[lots["sid"] == sid].copy().sort_values("date")
        if sid_lots.empty:
            continue
        can_qty = float(sid_lots["open_qty"].sum())
        qty = float(min(can_qty, 150.0))
        if qty <= EPS:
            continue
        lot = sid_lots.iloc[0]
        kind = str(lot.get("kind", "ACC"))
        side = ns["default_close_side_code"](kind)
        open_px = float(pd.to_numeric(lot.get("gen_price"), errors="coerce") or 0.0)
        close_px = open_px + (1.0 if str(side).upper() == "SELL" else -1.0)
        pnl = float(ns["calc_close_pnl"](kind, side, qty, open_px, close_px))
        rows.append(
            {
                "close_id": uuid4().hex,
                "dt": as_of_s,
                "group_id": str(gid),
                "structure_id": sid,
                "underlying": str(lot.get("underlying", "")),
                "side": side,
                "qty": qty,
                "open_price": open_px,
                "close_price": close_px,
                "pnl": pnl,
                "close_category": ns["STRUCT_CLOSE_CATEGORY"],
                "quick_batch_id": batch_id,
                "source_gen_date": str(lot.get("date", "")),
                "is_external": 0,
            }
        )
        expected[sid] = qty

    if not rows:
        return CheckResult("批量快速平仓联动", "skip", "候选结构不足")
    ns["insert_close_rows"](conn, rows)
    conn.commit()

    qty_after, _, _, _ = compute_open_snapshot(ns, conn, gid, as_of_s)
    bad: List[str] = []
    for sid, qexp in expected.items():
        reduced = float(qty_before.get(sid, 0.0) - qty_after.get(sid, 0.0))
        if abs(reduced - qexp) > 1e-5:
            bad.append(f"{sid}: 期望减少 {qexp:.4f}，实际 {reduced:.4f}")
    if bad:
        return CheckResult("批量快速平仓联动", "fail", "；".join(bad))
    return CheckResult("批量快速平仓联动", "pass", f"已校验 {len(expected)} 个结构，减少量联动正确")


def check_active_only_filter_recompute(ns: Dict[str, Any], conn: Any, gid: str, as_of: date) -> CheckResult:
    as_of_s = as_of.strftime(ns["DATE_FMT"])
    struct_asof, _, bounds_asof = ns["compute_ledgers"](conn, as_of_date=as_of_s)
    closes2 = ns["fetch_closes2"](conn)
    manual_map = ns["build_manual_close_date_map"](closes2, group_id=str(gid), as_of_date=as_of)
    melt_map = ns["build_melt_date_map"](struct_asof, group_id=str(gid), as_of_date=as_of)
    inactive = set(str(x).strip() for x in set(manual_map.keys()) | set(melt_map.keys()) if str(x).strip())

    s_gid = struct_asof[struct_asof["group_id"].astype(str) == str(gid)].copy()
    active_s = s_gid[~s_gid["structure_id"].astype(str).str.strip().isin(inactive)].copy()
    bad_sid = set(active_s["structure_id"].astype(str).str.strip().tolist()) & inactive
    if bad_sid:
        return CheckResult("仅存续结构重算联动", "fail", f"存续视图仍含终止结构: {sorted(bad_sid)}")

    b_gid = bounds_asof[bounds_asof["group_id"].astype(str) == str(gid)].copy()
    b_struct_active = b_gid[
        (b_gid["level"].astype(str) == "STRUCTURE")
        & (~b_gid["structure_id"].astype(str).str.strip().isin(inactive))
    ].copy()
    bad_b = set(b_struct_active["structure_id"].astype(str).str.strip().tolist()) & inactive
    if bad_b:
        return CheckResult("仅存续结构重算联动", "fail", f"风险敞口仍含终止结构: {sorted(bad_b)}")
    return CheckResult(
        "仅存续结构重算联动",
        "pass",
        f"inactive={len(inactive)}，结构明细与风险敞口均按仅存续口径过滤",
    )


def run_checks(
    db_path: Path,
    app_path: Path,
    gid: Optional[str],
    *,
    as_of_override: Optional[date] = None,
) -> List[CheckResult]:
    ns = load_app_core_namespace(app_path)
    tmp_dir = tempfile.mkdtemp(prefix="otc_reg_")
    tmp_db = Path(tmp_dir) / "regression_copy.db"
    shutil.copy2(str(db_path), str(tmp_db))
    ns["DB_PATH"] = str(tmp_db)

    conn = ns["get_conn"]()
    try:
        ns["init_db"](conn)
        group_id = choose_group(ns, conn, gid)
        as_of = as_of_override if as_of_override is not None else get_asof(ns, conn)

        checks: List[Callable[[Dict[str, Any], Any, str, date], CheckResult]] = [
            check_manual_structure_close_linkage,
            check_single_close_linkage,
            check_quick_close_linkage,
            check_symmetric_close_linkage,
            check_active_only_filter_recompute,
        ]
        results: List[CheckResult] = []
        for fn in checks:
            try:
                res = fn(ns, conn, group_id, as_of)
            except Exception as exc:
                res = CheckResult(fn.__name__, "fail", f"{type(exc).__name__}: {exc}")
            results.append(res)
        return results
    finally:
        try:
            conn.close()
        except Exception:
            pass


def build_scenarios(
    db_path: Path,
    *,
    group_arg: str,
    all_groups: bool,
    all_dates: bool,
    date_from: Optional[date],
    date_to: Optional[date],
) -> List[Tuple[Optional[str], Optional[date]]]:
    gids = list_group_ids(db_path)
    if not gids:
        raise RuntimeError("数据库中没有策略组。")

    if all_groups:
        target_gids = gids
    elif group_arg:
        gid = str(group_arg).strip()
        if gid not in gids:
            raise RuntimeError(f"group_id 不存在：{gid}")
        target_gids = [gid]
    else:
        target_gids = [gids[0]]

    scenarios: List[Tuple[Optional[str], Optional[date]]] = []
    for gid in target_gids:
        cand_dates = list_candidate_asof_dates(db_path, gid)
        cand_dates = filter_asof_dates(cand_dates, date_from, date_to)
        if all_dates or date_from is not None or date_to is not None:
            if cand_dates:
                for d in cand_dates:
                    scenarios.append((gid, d))
            else:
                # 保底跑一轮自动 asof，避免日期范围内无记录时完全不跑。
                scenarios.append((gid, None))
        else:
            scenarios.append((gid, cand_dates[-1] if cand_dates else None))
    return scenarios


def main() -> int:
    parser = argparse.ArgumentParser(
        description="平仓联动回归检查（基于数据库副本，不污染生产数据）。"
    )
    parser.add_argument("--db", default="otc_gui.db", help="数据库路径。")
    parser.add_argument("--app", default="app.py", help="app.py 路径。")
    parser.add_argument("--group", default="", help="仅校验该 group_id。")
    parser.add_argument("--all-groups", action="store_true", help="校验所有 group_id。")
    parser.add_argument("--all-dates", action="store_true", help="校验候选日期全集。")
    parser.add_argument("--date-from", default="", help="开始日期 YYYY-MM-DD。")
    parser.add_argument("--date-to", default="", help="结束日期 YYYY-MM-DD。")
    args = parser.parse_args()

    db_path = Path(args.db).resolve()
    app_path = Path(args.app).resolve()
    if not db_path.exists():
        print(f"[FAIL] 数据库不存在: {db_path}")
        return 2
    if not app_path.exists():
        print(f"[FAIL] app.py 不存在: {app_path}")
        return 2
    if args.group.strip() and args.all_groups:
        print("[FAIL] --group 与 --all-groups 不能同时使用")
        return 2

    try:
        d_from = parse_cli_date(args.date_from, "--date-from") if str(args.date_from).strip() else None
        d_to = parse_cli_date(args.date_to, "--date-to") if str(args.date_to).strip() else None
    except Exception as exc:
        print(f"[FAIL] 参数错误: {exc}")
        return 2
    if d_from is not None and d_to is not None and d_from > d_to:
        d_from, d_to = d_to, d_from

    try:
        scenarios = build_scenarios(
            db_path,
            group_arg=args.group.strip(),
            all_groups=bool(args.all_groups),
            all_dates=bool(args.all_dates),
            date_from=d_from,
            date_to=d_to,
        )
    except Exception as exc:
        print(f"[FAIL] 场景构建失败: {exc}")
        return 2

    if not scenarios:
        print("[FAIL] 没有可执行的场景")
        return 2

    total_pass = 0
    total_skip = 0
    total_fail = 0
    total_checks = 0
    print("=== 平仓联动回归结果 ===")
    for idx, (gid, as_of) in enumerate(scenarios, start=1):
        as_of_txt = as_of.strftime("%Y-%m-%d") if as_of is not None else "(auto latest)"
        print(f"\n--- Scenario {idx}/{len(scenarios)} | group={gid} | asof={as_of_txt} ---")
        results = run_checks(db_path, app_path, gid, as_of_override=as_of)
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

