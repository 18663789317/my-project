import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_option_warehouse_cross_page_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OptionWarehouseCrossPageLinkageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.app._FETCH_SQL_MEMO_CACHE.clear()
        self.app._LEDGER_MEMO_CACHE.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "CrossLink", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def insert_basic_range_structure(
        self,
        structure_id: str,
        *,
        start_date: str,
        end_date: str,
        underlying: str = "I.TEST",
        kind: str = "ACC",
        base_qty: float = 1000.0,
        entry_price: float = 100.0,
        strike_price: float = 95.0,
        knock_out_price: float = 110.0,
        multiple: float = 3.0,
    ) -> None:
        params = {}
        meta = {"ko_terminate": False}
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_in,
                barrier_out, knock_out_price, ko_strike_price, multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                "G1",
                structure_id,
                underlying,
                "华泰长城",
                kind,
                "BASIC_RANGE",
                "BASIC_RANGE",
                start_date,
                end_date,
                base_qty,
                entry_price,
                strike_price,
                None,
                knock_out_price,
                knock_out_price,
                None,
                multiple,
                json.dumps(params, ensure_ascii=False),
                json.dumps(meta, ensure_ascii=False),
            ),
        )

    def insert_safety_airbag_structure(
        self,
        structure_id: str,
        *,
        start_date: str,
        end_date: str,
        underlying: str = "I.TEST",
        kind: str = "ACC",
        total_scale_qty: float = 150000.0,
        entry_price: float = 100.0,
        strike_price: float = 95.0,
        barrier_price: float = 80.0,
        participation_pct: float = 80.0,
    ) -> None:
        total_days = len(self.app.trading_days_between(self.app.parse_date_maybe(start_date), self.app.parse_date_maybe(end_date)))
        base_qty = float(total_scale_qty) / float(max(total_days, 1))
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_out,
                knock_out_price, multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                "G1",
                structure_id,
                underlying,
                "华泰长城",
                kind,
                "SAFETY_AIRBAG",
                "SAFETY_AIRBAG",
                start_date,
                end_date,
                base_qty,
                entry_price,
                strike_price,
                barrier_price,
                barrier_price,
                participation_pct,
                json.dumps({}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )

    def insert_prices(self, underlying: str, rows: list[tuple[str, float]]) -> None:
        self.conn.executemany(
            "INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)",
            [(dt_s, underlying, float(settle)) for dt_s, settle in rows],
        )
        self.conn.commit()

    def fetch_core_frames(self, *, as_of_date: str):
        struct_asof, _, bounds_asof = self.app.compute_ledgers_cached(self.conn, as_of_date=as_of_date)
        close2_df = self.app.fetch_closes2(self.conn)
        return struct_asof, bounds_asof, close2_df

    def warehouse_open_lots(self, structure_id: str, *, as_of_date: str) -> pd.DataFrame:
        struct_asof, _, close2_df = self.fetch_core_frames(as_of_date=as_of_date)
        struct_cut = struct_asof[struct_asof["structure_id"].astype(str) == str(structure_id)].copy()
        return self.app.build_open_lot_rows(struct_cut, close2_df, as_of_date)

    def warehouse_open_qty(self, structure_id: str, *, as_of_date: str) -> float:
        open_lots = self.warehouse_open_lots(structure_id, as_of_date=as_of_date)
        if open_lots.empty:
            return 0.0
        return float(pd.to_numeric(open_lots["open_qty"], errors="coerce").fillna(0.0).sum())

    def report_latest_row(self, structure_id: str, *, as_of_date: str) -> pd.Series:
        struct_asof, _, close2_df = self.fetch_core_frames(as_of_date=as_of_date)
        enriched = self.app.enrich_accumulator_daily_rows(
            struct_asof.copy(),
            close2_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date=as_of_date,
        )
        sub = (
            enriched[enriched["structure_id"].astype(str) == str(structure_id)]
            .sort_values(["date", "structure_id"])
            .reset_index(drop=True)
        )
        self.assertFalse(sub.empty)
        return sub.iloc[-1]

    def runtime_seed(self, structure_id: str, *, as_of_date: str) -> dict:
        structs_df = self.app.fetch_structures(self.conn)
        prices_df = self.app.fetch_prices(self.conn)
        struct_row = (
            structs_df[structs_df["structure_id"].astype(str) == str(structure_id)]
            .iloc[0]
            .to_dict()
        )
        settle_now = float(
            prices_df[
                (prices_df["underlying"].astype(str) == str(struct_row.get("underlying", "")))
                & (prices_df["dt"].astype(str) == str(as_of_date))
            ]["settle"].iloc[0]
        )
        struct_asof, bounds_asof, close2_df = self.fetch_core_frames(as_of_date=as_of_date)
        return self.app.special_build_runtime_state_seed(
            struct_row=struct_row,
            rep_date=as_of_date,
            current_price=settle_now,
            prices_df=prices_df,
            struct_asof=struct_asof,
            bounds_asof=bounds_asof,
            close2_df=close2_df,
        )

    def close_detail_table(self, *, rep_date: str) -> pd.DataFrame:
        groups_df = self.app.fetch_groups(self.conn)
        structs_df = self.app.fetch_structures(self.conn)
        close2_df = self.app.fetch_closes2(self.conn)
        spot_match_df = self.app.fetch_spot_hedge_logs(self.conn)
        group_name_map = groups_df.set_index("group_id")["group_name"].to_dict()
        return self.app.build_close_detail_table(
            close2_df,
            spot_match_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date=rep_date,
            group_name_map=group_name_map,
            structs_df=structs_df,
            groups_df=groups_df,
        )

    def test_internal_close_updates_warehouse_monitor_and_close_detail_pages(self) -> None:
        self.insert_basic_range_structure("S_INT", start_date="2026-04-01", end_date="2026-04-03")
        self.insert_prices(
            "I.TEST",
            [("2026-04-01", 100.0), ("2026-04-02", 101.0), ("2026-04-03", 102.0)],
        )

        before_qty = self.warehouse_open_qty("S_INT", as_of_date="2026-04-03")
        before_report = self.report_latest_row("S_INT", as_of_date="2026-04-03")
        before_seed = self.runtime_seed("S_INT", as_of_date="2026-04-03")
        self.assertAlmostEqual(before_qty, 3000.0)
        self.assertAlmostEqual(float(before_report["current_open_qty"]), 3000.0)
        self.assertAlmostEqual(float(before_seed["current_open_qty"]), 3000.0)

        open_lots = self.warehouse_open_lots("S_INT", as_of_date="2026-04-03")
        plan = self.app.build_manual_structure_close_rows(
            open_lots.to_dict("records"),
            kind="ACC",
            side="SELL",
            qty=1500.0,
            total_pnl=3000.0,
            close_dt="2026-04-03",
            group_id="G1",
            structure_id="S_INT",
            underlying="I.TEST",
            quick_batch_id="MANUAL_LINK_TEST",
        )
        self.app.insert_close_rows(self.conn, plan["rows"])

        after_qty = self.warehouse_open_qty("S_INT", as_of_date="2026-04-03")
        after_report = self.report_latest_row("S_INT", as_of_date="2026-04-03")
        after_seed = self.runtime_seed("S_INT", as_of_date="2026-04-03")
        close_detail = self.close_detail_table(rep_date="2026-04-03")
        metrics = self.app.summarize_close_metrics(close_detail)

        self.assertAlmostEqual(after_qty, 1500.0)
        self.assertAlmostEqual(float(after_report["current_open_qty"]), 1500.0)
        self.assertAlmostEqual(float(after_report["day_close_qty"]), 1500.0)
        self.assertAlmostEqual(float(after_seed["current_open_qty"]), 1500.0)
        self.assertEqual(int(close_detail.shape[0]), 2)
        self.assertEqual(
            set(close_detail["平仓类别"].astype(str).tolist()),
            {self.app.STRUCT_CLOSE_CATEGORY},
        )
        self.assertAlmostEqual(float(pd.to_numeric(close_detail["数量"], errors="coerce").sum()), 1500.0)
        self.assertAlmostEqual(float(pd.to_numeric(close_detail["平仓盈亏"], errors="coerce").sum()), 3000.0)
        self.assertAlmostEqual(float(metrics["qty_sum"]), 1500.0)
        self.assertAlmostEqual(float(metrics["total_pnl_sum"]), 3000.0)

    def test_multi_structure_manual_batch_and_symmetric_close_keep_pages_consistent(self) -> None:
        self.insert_basic_range_structure("S_LONG_A", start_date="2026-04-01", end_date="2026-04-03", kind="ACC", base_qty=1000.0)
        self.insert_basic_range_structure("S_LONG_B", start_date="2026-04-01", end_date="2026-04-03", kind="ACC", base_qty=500.0)
        self.insert_basic_range_structure("S_SHORT_A", start_date="2026-04-01", end_date="2026-04-03", kind="DEC", base_qty=800.0, strike_price=105.0, knock_out_price=90.0)
        self.insert_basic_range_structure("S_SHORT_B", start_date="2026-04-01", end_date="2026-04-03", kind="DEC", base_qty=700.0, strike_price=105.0, knock_out_price=90.0)
        self.insert_prices(
            "I.TEST",
            [("2026-04-01", 100.0), ("2026-04-02", 101.0), ("2026-04-03", 102.0)],
        )

        def open_qty_map() -> dict[str, float]:
            struct_asof, _, close2_df = self.fetch_core_frames(as_of_date="2026-04-03")
            open_lots = self.app.build_open_lot_rows(struct_asof, close2_df, "2026-04-03")
            if open_lots.empty:
                return {}
            return open_lots.groupby(open_lots["structure_id"].astype(str))["open_qty"].sum().astype(float).to_dict()

        self.assertEqual(
            open_qty_map(),
            {"S_LONG_A": 3000.0, "S_LONG_B": 1500.0, "S_SHORT_A": 2400.0, "S_SHORT_B": 2100.0},
        )

        manual_a = self.app.build_manual_structure_close_rows(
            self.warehouse_open_lots("S_LONG_A", as_of_date="2026-04-03").to_dict("records"),
            kind="ACC",
            side="SELL",
            qty=1200.0,
            total_pnl=2400.0,
            close_dt="2026-04-03",
            group_id="G1",
            structure_id="S_LONG_A",
            underlying="I.TEST",
            quick_batch_id="MANUAL_MIX_A",
        )
        batch_b = self.app.build_manual_structure_close_rows(
            self.warehouse_open_lots("S_LONG_B", as_of_date="2026-04-03").to_dict("records"),
            kind="ACC",
            side="SELL",
            qty=500.0,
            total_pnl=1000.0,
            close_dt="2026-04-03",
            group_id="G1",
            structure_id="S_LONG_B",
            underlying="I.TEST",
            quick_batch_id="BATCH_MIX_B",
        )
        self.app.insert_close_rows(self.conn, manual_a["rows"] + batch_b["rows"])
        self.conn.commit()

        struct_asof, _, close2_df = self.fetch_core_frames(as_of_date="2026-04-03")
        open_after_first = self.app.build_open_lot_rows(struct_asof, close2_df, "2026-04-03")
        lot_state = self.app.build_sym_close_lot_state(open_after_first)
        sym_long_rows, sym_long_pnl = self.app.consume_sym_close_lots(
            lot_state=lot_state,
            gid="G1",
            batch_id="SYM_MIX",
            pair_dt_s="2026-04-03",
            structure_id="S_LONG_B",
            qty=400.0,
            kind="ACC",
            side="SELL",
            close_price=103.0,
            underlying_fallback="I.TEST",
        )
        sym_short_rows, sym_short_pnl = self.app.consume_sym_close_lots(
            lot_state=lot_state,
            gid="G1",
            batch_id="SYM_MIX",
            pair_dt_s="2026-04-03",
            structure_id="S_SHORT_A",
            qty=400.0,
            kind="DEC",
            side="BUY",
            close_price=103.0,
            underlying_fallback="I.TEST",
        )
        self.app.insert_close_rows(self.conn, sym_long_rows + sym_short_rows)
        self.conn.commit()

        final_qty = open_qty_map()
        self.assertAlmostEqual(final_qty["S_LONG_A"], 1800.0)
        self.assertAlmostEqual(final_qty["S_LONG_B"], 600.0)
        self.assertAlmostEqual(final_qty["S_SHORT_A"], 2000.0)
        self.assertAlmostEqual(final_qty["S_SHORT_B"], 2100.0)
        self.assertAlmostEqual(float(self.report_latest_row("S_LONG_B", as_of_date="2026-04-03")["current_open_qty"]), 600.0)
        self.assertAlmostEqual(float(self.report_latest_row("S_SHORT_A", as_of_date="2026-04-03")["current_open_qty"]), 2000.0)

        close_detail = self.close_detail_table(rep_date="2026-04-03")
        metrics = self.app.summarize_close_metrics(close_detail)
        expected_rows = manual_a["rows"] + batch_b["rows"] + sym_long_rows + sym_short_rows
        expected_qty = sum(float(row["qty"]) for row in expected_rows)
        expected_pnl = sum(float(row["pnl"]) for row in expected_rows)

        self.assertEqual(set(close_detail["平仓类别"].astype(str).tolist()), {self.app.STRUCT_CLOSE_CATEGORY, self.app.SYMMETRIC_CLOSE_CATEGORY})
        self.assertEqual(
            set(close_detail["平仓批次号"].astype(str).tolist()),
            {"MANUAL_MIX_A", "BATCH_MIX_B", "SYM_MIX"},
        )
        self.assertAlmostEqual(float(pd.to_numeric(close_detail["数量"], errors="coerce").sum()), expected_qty)
        self.assertAlmostEqual(float(pd.to_numeric(close_detail["平仓盈亏"], errors="coerce").sum()), expected_pnl)
        self.assertAlmostEqual(float(metrics["qty_sum"]), expected_qty)
        self.assertAlmostEqual(float(metrics["total_pnl_sum"]), expected_pnl)

    def test_reverting_close_rows_restores_warehouse_monitor_detail_and_pnl(self) -> None:
        self.insert_basic_range_structure("S_REVERT", start_date="2026-04-01", end_date="2026-04-03")
        self.insert_prices(
            "I.TEST",
            [("2026-04-01", 100.0), ("2026-04-02", 101.0), ("2026-04-03", 102.0)],
        )

        before_qty = self.warehouse_open_qty("S_REVERT", as_of_date="2026-04-03")
        before_report = self.report_latest_row("S_REVERT", as_of_date="2026-04-03")
        self.assertAlmostEqual(before_qty, 3000.0)
        self.assertAlmostEqual(float(before_report["current_open_qty"]), 3000.0)

        plan = self.app.build_manual_structure_close_rows(
            self.warehouse_open_lots("S_REVERT", as_of_date="2026-04-03").to_dict("records"),
            kind="ACC",
            side="SELL",
            qty=1800.0,
            total_pnl=5400.0,
            close_dt="2026-04-03",
            group_id="G1",
            structure_id="S_REVERT",
            underlying="I.TEST",
            quick_batch_id="REVERT_TEST",
        )
        self.app.insert_close_rows(self.conn, plan["rows"])
        self.conn.commit()

        after_close_qty = self.warehouse_open_qty("S_REVERT", as_of_date="2026-04-03")
        after_close_detail = self.close_detail_table(rep_date="2026-04-03")
        after_close_metrics = self.app.summarize_close_metrics(after_close_detail)
        self.assertAlmostEqual(after_close_qty, 1200.0)
        self.assertAlmostEqual(float(after_close_metrics["qty_sum"]), 1800.0)
        self.assertAlmostEqual(float(after_close_metrics["total_pnl_sum"]), 5400.0)

        close_rows = self.app.fetch_closes2(self.conn)
        revert_ids = close_rows["close_id"].astype(str).tolist()
        self.conn.execute("BEGIN IMMEDIATE")
        for _, row in close_rows.iterrows():
            self.app.archive_close_record_for_revert(self.conn, row.to_dict(), "REVERT_TEST")
        self.conn.executemany("DELETE FROM close_trade2 WHERE close_id=?", [(cid,) for cid in revert_ids])
        self.conn.commit()

        restored_qty = self.warehouse_open_qty("S_REVERT", as_of_date="2026-04-03")
        restored_report = self.report_latest_row("S_REVERT", as_of_date="2026-04-03")
        restored_detail = self.close_detail_table(rep_date="2026-04-03")
        restored_metrics = self.app.summarize_close_metrics(restored_detail)
        revert_log_count = self.conn.execute("SELECT COUNT(*) FROM close_revert_log").fetchone()[0]

        self.assertEqual(int(revert_log_count), len(revert_ids))
        self.assertAlmostEqual(restored_qty, before_qty)
        self.assertAlmostEqual(float(restored_report["current_open_qty"]), 3000.0)
        self.assertAlmostEqual(float(restored_report["day_close_qty"]), 0.0)
        self.assertTrue(restored_detail.empty)
        self.assertAlmostEqual(float(restored_metrics["qty_sum"]), 0.0)
        self.assertAlmostEqual(float(restored_metrics["total_pnl_sum"]), 0.0)

    def test_manual_structure_close_marker_stops_future_generation_and_marks_other_pages(self) -> None:
        self.insert_basic_range_structure("S_MANUAL", start_date="2026-04-01", end_date="2026-04-06")
        self.insert_prices(
            "I.TEST",
            [("2026-04-01", 100.0), ("2026-04-02", 101.0), ("2026-04-03", 102.0)],
        )

        before_struct_asof, _, _ = self.fetch_core_frames(as_of_date="2026-04-03")
        before_struct_cut = (
            before_struct_asof[before_struct_asof["structure_id"].astype(str) == "S_MANUAL"]
            .sort_values(["date", "structure_id"])
            .reset_index(drop=True)
        )
        before_seed = self.runtime_seed("S_MANUAL", as_of_date="2026-04-03")
        self.assertFalse(bool(before_seed["manual_closed"]))
        self.assertAlmostEqual(float(before_seed["current_open_qty"]), 3000.0)
        self.assertEqual(before_struct_cut["date"].astype(str).tolist(), ["2026-04-01", "2026-04-02", "2026-04-03"])

        touched = self.app.upsert_manual_close_markers_for_structures(
            self.conn,
            structure_ids=["S_MANUAL"],
            group_id="G1",
            close_dt="2026-04-02",
        )
        self.assertEqual(touched, ["S_MANUAL"])

        struct_asof, _, close2_df = self.fetch_core_frames(as_of_date="2026-04-03")
        manual_close_map = self.app.build_manual_close_date_map(
            close2_df,
            group_id="G1",
            as_of_date=self.app.parse_date_maybe("2026-04-03"),
        )
        struct_cut = (
            struct_asof[struct_asof["structure_id"].astype(str) == "S_MANUAL"]
            .sort_values(["date", "structure_id"])
            .reset_index(drop=True)
        )
        open_qty_after = self.warehouse_open_qty("S_MANUAL", as_of_date="2026-04-03")
        after_seed = self.runtime_seed("S_MANUAL", as_of_date="2026-04-03")
        close_detail = self.close_detail_table(rep_date="2026-04-03")

        self.assertEqual(manual_close_map["S_MANUAL"], self.app.parse_date_maybe("2026-04-02"))
        self.assertEqual(struct_cut["date"].astype(str).tolist(), ["2026-04-01"])
        self.assertAlmostEqual(open_qty_after, 1000.0)
        self.assertTrue(bool(after_seed["manual_closed"]))
        self.assertEqual(int(after_seed["remaining_days"]), 0)
        self.assertAlmostEqual(float(after_seed["remaining_executable_qty"]), 0.0)
        self.assertAlmostEqual(float(after_seed["current_open_qty"]), 1000.0)
        self.assertEqual(int(close_detail.shape[0]), 1)
        self.assertEqual(str(close_detail.iloc[0]["平仓类别"]), self.app.MANUAL_STRUCT_CLOSE_CATEGORY)
        self.assertEqual(str(close_detail.iloc[0]["结构状态"]), "已手动平仓")

    def test_manual_structure_reduction_scales_future_generation_and_close_detail(self) -> None:
        self.insert_basic_range_structure("S_PART", start_date="2026-04-01", end_date="2026-04-08", base_qty=30000.0, knock_out_price=200.0)
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 100.0),
                ("2026-04-02", 101.0),
                ("2026-04-03", 102.0),
                ("2026-04-07", 103.0),
                ("2026-04-08", 104.0),
            ],
        )
        self.app.insert_close_rows(
            self.conn,
            [
                {
                    "close_id": "MANUAL_REDUCE_PART",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_PART",
                    "underlying": "I.TEST",
                    "side": "平仓",
                    "qty": 50000.0,
                    "open_price": 100.0,
                    "close_price": 102.0,
                    "pnl": 6000.0,
                    "close_category": self.app.MANUAL_STRUCT_REDUCTION_CATEGORY,
                    "quick_batch_id": "MANUAL_STRUCT_REDUCE_TEST",
                    "source_gen_date": "2026-04-03",
                    "is_external": 1,
                }
            ],
        )

        struct_asof, bounds_asof, close2_df = self.fetch_core_frames(as_of_date="2026-04-08")
        struct_cut = (
            struct_asof[struct_asof["structure_id"].astype(str) == "S_PART"]
            .sort_values(["date", "structure_id"])
            .reset_index(drop=True)
        )
        bounds_cut = bounds_asof[
            bounds_asof["level"].astype(str).str.upper().eq("STRUCTURE")
            & bounds_asof["structure_id"].astype(str).eq("S_PART")
        ].copy()
        close_detail = self.close_detail_table(rep_date="2026-04-08")

        self.assertEqual(struct_cut["date"].astype(str).tolist(), ["2026-04-01", "2026-04-02", "2026-04-03", "2026-04-07", "2026-04-08"])
        self.assertEqual(
            pd.to_numeric(struct_cut["generated_qty"], errors="coerce").round(6).tolist(),
            [30000.0, 30000.0, 20000.0, 20000.0, 20000.0],
        )
        self.assertAlmostEqual(float(pd.to_numeric(struct_cut["cum_qty"], errors="coerce").iloc[-1]), 120000.0)
        self.assertFalse(bounds_cut.empty)
        self.assertAlmostEqual(float(pd.to_numeric(bounds_cut["remaining_max_qty"], errors="coerce").iloc[-1]), 0.0)
        reduction_rows = close_detail[close_detail["平仓类别"].astype(str) == self.app.MANUAL_STRUCT_REDUCTION_CATEGORY].copy()
        self.assertEqual(int(reduction_rows.shape[0]), 1)
        self.assertAlmostEqual(float(pd.to_numeric(reduction_rows["数量"], errors="coerce").iloc[0]), 50000.0)
        self.assertEqual(str(reduction_rows.iloc[0]["结构状态"]), "整体减仓")

    def test_manual_structure_reduction_updates_monitor_price_gap_airbag_display(self) -> None:
        self.insert_safety_airbag_structure(
            "S_AIR_PART",
            start_date="2026-04-01",
            end_date="2026-04-07",
            total_scale_qty=150000.0,
            barrier_price=80.0,
            entry_price=100.0,
            strike_price=95.0,
        )
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 100.0),
                ("2026-04-02", 101.0),
                ("2026-04-03", 102.0),
            ],
        )
        self.app.insert_close_rows(
            self.conn,
            [
                {
                    "close_id": "MANUAL_REDUCE_AIRBAG",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_AIR_PART",
                    "underlying": "I.TEST",
                    "side": "平仓",
                    "qty": 50000.0,
                    "open_price": 100.0,
                    "close_price": 102.0,
                    "pnl": 3000.0,
                    "close_category": self.app.MANUAL_STRUCT_REDUCTION_CATEGORY,
                    "quick_batch_id": "MANUAL_STRUCT_REDUCE_AIRBAG",
                    "source_gen_date": "2026-04-03",
                    "is_external": 1,
                }
            ],
        )

        structs_df = self.app.fetch_structures(self.conn)
        prices_df = self.app.fetch_prices(self.conn)
        close2_df = self.app.fetch_closes2(self.conn)
        gap_df = self.app.compute_price_gap_table(
            structs_df,
            prices_df,
            close2_df,
            as_of_date=self.app.parse_date_maybe("2026-04-03"),
        )
        gap_row = gap_df[gap_df["结构ID"].astype(str) == "S_AIR_PART"].iloc[0]
        reduced_display_map = self.app.build_structure_display_notional_qty_map(
            structs_df,
            strategy_code_filter="SAFETY_AIRBAG",
            signed=True,
            reduction_qty_map=self.app.build_manual_structure_reduction_qty_map(
                close2_df,
                group_id="G1",
                as_of_date=self.app.parse_date_maybe("2026-04-03"),
            ),
        )

        self.assertAlmostEqual(float(gap_row["剩余震荡最大头寸规模"]), 100000.0)
        self.assertAlmostEqual(float(reduced_display_map["S_AIR_PART"]), 100000.0)

    def test_spot_hedge_close_keeps_structure_spot_inventory_and_batch_summary_in_sync(self) -> None:
        self.insert_basic_range_structure("S_SPOT", start_date="2026-04-01", end_date="2026-04-03")
        self.insert_prices(
            "I.TEST",
            [("2026-04-01", 100.0), ("2026-04-02", 101.0), ("2026-04-03", 102.0)],
        )
        self.conn.execute(
            """
            INSERT INTO spot_position_lot(
                lot_id, group_id, spot_name, buy_dt, qty, buy_price, note, created_at, created_by
            ) VALUES(?,?,?,?,?,?,?,?,?)
            """,
            ("LOT1", "G1", "现货A", "2026-04-01", 1000.0, 800.0, "", "2026-04-01 09:00:00", "test"),
        )
        self.app.insert_close_rows(
            self.conn,
            [
                {
                    "close_id": "CLOSE_SPOT_STRUCT",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_SPOT",
                    "underlying": "I.TEST",
                    "side": "SELL",
                    "qty": 600.0,
                    "open_price": 95.0,
                    "close_price": 90.0,
                    "pnl": -3000.0,
                    "close_category": self.app.SPOT_HEDGE_CLOSE_CATEGORY,
                    "quick_batch_id": "SPH_TEST_BATCH",
                    "source_gen_date": "2026-04-01",
                    "is_external": 0,
                }
            ],
        )
        self.conn.execute(
            """
            INSERT INTO spot_hedge_match_log(
                match_id, group_id, match_dt, matched_at, matched_by, spot_name, spot_lot_id,
                structure_id, structure_kind, structure_side, matched_qty, spot_buy_avg_price,
                spot_sell_price, spot_cost_amount, spot_pnl, structure_close_price, structure_pnl,
                total_pnl, close_batch_id, note
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "MATCH1",
                "G1",
                "2026-04-03",
                "2026-04-03 10:00:00",
                "test",
                "现货A",
                "LOT1",
                "S_SPOT",
                "ACC",
                "SELL",
                600.0,
                800.0,
                820.0,
                480000.0,
                12000.0,
                90.0,
                -3000.0,
                9000.0,
                "SPH_TEST_BATCH",
                "",
            ),
        )

        open_qty_after = self.warehouse_open_qty("S_SPOT", as_of_date="2026-04-03")
        spot_summary = self.app.compute_spot_inventory_summary(
            self.app.fetch_spot_lots(self.conn),
            self.app.fetch_spot_hedge_logs(self.conn),
            group_id="G1",
        )
        close_detail = self.close_detail_table(rep_date="2026-04-03")
        batch_summary, _ = self.app.build_spot_batch_summary(close_detail)

        self.assertAlmostEqual(open_qty_after, 2400.0)
        self.assertEqual(int(spot_summary.shape[0]), 1)
        self.assertAlmostEqual(float(spot_summary.iloc[0]["可用数量"]), 400.0)
        self.assertAlmostEqual(float(spot_summary.iloc[0]["可用成本"]), 320000.0)
        self.assertEqual(set(close_detail["记录类型"].astype(str).tolist()), {"结构记录", "现货记录"})
        self.assertEqual(set(close_detail["平仓类别"].astype(str).tolist()), {self.app.SPOT_HEDGE_CLOSE_CATEGORY})
        self.assertEqual(int(batch_summary.shape[0]), 1)
        self.assertAlmostEqual(float(batch_summary.iloc[0]["平仓数量（吨）"]), 600.0)
        self.assertAlmostEqual(float(batch_summary.iloc[0]["合计盈亏"]), 9000.0)

    def test_airbag_hedge_close_category_reduces_structure_remaining_notional(self) -> None:
        self.insert_safety_airbag_structure(
            "S_AIR_HEDGE",
            start_date="2026-04-01",
            end_date="2026-04-03",
            kind="DEC",
            total_scale_qty=3000.0,
        )

        closes2 = pd.DataFrame(
            [
                {
                    "close_id": "C_AIR_HEDGE_1",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_AIR_HEDGE",
                    "qty": 1000.0,
                    "side": "平仓",
                    "is_external": 1,
                    "close_category": self.app.AIRBAG_HEDGE_CLOSE_CATEGORY,
                }
            ]
        )

        reduce_map = self.app.build_manual_structure_reduction_qty_map(
            closes2,
            group_id="G1",
            as_of_date=self.app.parse_date_maybe("2026-04-03"),
        )
        display_map = self.app.build_structure_display_notional_qty_map(
            self.app.fetch_structures(self.conn),
            strategy_code_filter="SAFETY_AIRBAG",
            reduction_qty_map=reduce_map,
        )

        self.assertAlmostEqual(float(reduce_map["S_AIR_HEDGE"]), 1000.0)
        self.assertAlmostEqual(float(display_map["S_AIR_HEDGE"]), 2000.0)

    def test_airbag_hedge_batch_updates_linear_inventory_and_airbag_remaining_together(self) -> None:
        self.insert_basic_range_structure(
            "S_LINEAR_HEDGE",
            start_date="2026-04-01",
            end_date="2026-04-03",
            kind="ACC",
            base_qty=1000.0,
        )
        self.insert_safety_airbag_structure(
            "S_AIRBAG_HEDGE",
            start_date="2026-04-01",
            end_date="2026-04-03",
            kind="DEC",
            total_scale_qty=3000.0,
        )
        self.insert_prices(
            "I.TEST",
            [("2026-04-01", 100.0), ("2026-04-02", 101.0), ("2026-04-03", 102.0)],
        )

        before_linear_open = self.warehouse_open_qty("S_LINEAR_HEDGE", as_of_date="2026-04-03")
        self.assertAlmostEqual(before_linear_open, 3000.0)

        self.app.insert_close_rows(
            self.conn,
            [
                {
                    "close_id": "AIRBAG_HEDGE_LINEAR_ROW",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_LINEAR_HEDGE",
                    "underlying": "I.TEST",
                    "side": "SELL",
                    "qty": 1500.0,
                    "open_price": 100.0,
                    "close_price": 102.0,
                    "pnl": 3000.0,
                    "close_category": self.app.AIRBAG_HEDGE_CLOSE_CATEGORY,
                    "quick_batch_id": "SYMAB_TEST_BATCH",
                    "source_gen_date": "2026-04-01",
                    "is_external": 0,
                },
                {
                    "close_id": "AIRBAG_HEDGE_AIRBAG_ROW",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_AIRBAG_HEDGE",
                    "underlying": "I.TEST",
                    "side": "平仓",
                    "qty": 1500.0,
                    "open_price": 95.0,
                    "close_price": 102.0,
                    "pnl": 1200.0,
                    "close_category": self.app.AIRBAG_HEDGE_CLOSE_CATEGORY,
                    "quick_batch_id": "SYMAB_TEST_BATCH",
                    "source_gen_date": "2026-04-03",
                    "is_external": 1,
                },
            ],
        )

        after_linear_open = self.warehouse_open_qty("S_LINEAR_HEDGE", as_of_date="2026-04-03")
        close_detail = self.close_detail_table(rep_date="2026-04-03")
        reduce_map = self.app.build_manual_structure_reduction_qty_map(
            self.app.fetch_closes2(self.conn),
            group_id="G1",
            as_of_date=self.app.parse_date_maybe("2026-04-03"),
        )
        display_map = self.app.build_structure_display_notional_qty_map(
            self.app.fetch_structures(self.conn),
            strategy_code_filter="SAFETY_AIRBAG",
            reduction_qty_map=reduce_map,
        )

        self.assertAlmostEqual(after_linear_open, 1500.0)
        self.assertAlmostEqual(float(reduce_map["S_AIRBAG_HEDGE"]), 1500.0)
        self.assertAlmostEqual(float(display_map["S_AIRBAG_HEDGE"]), 1500.0)
        self.assertEqual(
            set(close_detail["平仓类别"].astype(str).tolist()),
            {self.app.AIRBAG_HEDGE_CLOSE_CATEGORY},
        )


if __name__ == "__main__":
    unittest.main()
