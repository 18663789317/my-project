import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_vanilla_maturity_processing_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VanillaMaturityProcessingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        for cache_name in [
            "_FETCH_SQL_MEMO_CACHE",
            "_LEDGER_MEMO_CACHE",
            "_OPEN_LOT_MEMO_CACHE",
            "_STRUCT_DERIVED_MEMO_CACHE",
            "_MONITOR_UI_MEMO_CACHE",
            "_MONITOR_REPORT_MEMO_CACHE",
        ]:
            cache_obj = getattr(self.app, cache_name, None)
            if hasattr(cache_obj, "clear"):
                cache_obj.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "香草到期处理测试组", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def insert_vanilla_structure(
        self,
        structure_id: str,
        *,
        group_id: str = "G1",
        underlying: str = "I.TEST",
        start_date: str = "2026-04-01",
        end_date: str = "2026-04-03",
        option_type: str = "call",
        side: str = "sell",
        base_qty: float = 10000.0,
        entry_price: float = 100.0,
        strike_price: float = 100.0,
        premium: float = 5.0,
        maturity_mode: str | None = None,
        maturity_roll_qty: float | None = None,
    ) -> None:
        params = {
            "multiplier": 1.0,
            "subsidy_per_ton": 0.0,
            "option_type": option_type,
            "side": side,
            "premium": premium,
            "trade_date": start_date,
            "expiry_date": end_date,
        }
        if maturity_mode is not None:
            params[self.app.VANILLA_MATURITY_MODE_PARAM_KEY] = maturity_mode
        if maturity_roll_qty is not None:
            params[self.app.VANILLA_MATURITY_ROLL_QTY_PARAM_KEY] = float(maturity_roll_qty)
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, structure_code, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, multiple,
                trade_date, expiry_date, option_type, side, premium, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                group_id,
                structure_id,
                structure_id,
                underlying,
                "海证资本",
                "DEC" if side == "sell" else "ACC",
                self.app.VANILLA_OPTION_CODE,
                self.app.VANILLA_OPTION_CODE,
                start_date,
                end_date,
                base_qty,
                entry_price,
                strike_price,
                1.0,
                start_date,
                end_date,
                option_type,
                side,
                premium,
                json.dumps(params, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def insert_prices(self, underlying: str, rows: list[tuple[str, float]]) -> None:
        self.conn.executemany(
            "INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)",
            [(dt_s, underlying, float(settle)) for dt_s, settle in rows],
        )
        self.conn.commit()

    def test_build_vanilla_maturity_outcome_partial_roll_for_unfavorable_sell_call(self) -> None:
        outcome = self.app.build_vanilla_maturity_outcome(
            {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "option_type": "call",
                "side": "sell",
                "strike_price": 100.0,
                "premium": 5.0,
            },
            settle_price=120.0,
            total_qty=10000.0,
            settlement_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            requested_roll_qty=6000.0,
        )

        self.assertFalse(bool(outcome["favorable"]))
        self.assertAlmostEqual(float(outcome["roll_target_price"]), 105.0)
        self.assertEqual(str(outcome["roll_trade_side"]), "SELL")
        self.assertAlmostEqual(float(outcome["actual_roll_qty"]), 6000.0)
        self.assertAlmostEqual(float(outcome["cash_qty"]), 4000.0)
        self.assertAlmostEqual(float(outcome["cash_pnl"]), -60000.0)
        self.assertAlmostEqual(float(outcome["roll_pnl"]), -90000.0)
        self.assertAlmostEqual(float(outcome["total_pnl"]), -150000.0)

    def test_build_vanilla_maturity_outcome_favorable_roll_mode_cash_settles_full_sell_put_qty(self) -> None:
        outcome = self.app.build_vanilla_maturity_outcome(
            {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "option_type": "put",
                "side": "sell",
                "strike_price": 120.0,
                "premium": 10.0,
            },
            settle_price=115.0,
            total_qty=8000.0,
            settlement_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            requested_roll_qty=5000.0,
        )

        self.assertTrue(bool(outcome["favorable"]))
        self.assertAlmostEqual(float(outcome["roll_target_price"]), 110.0)
        self.assertAlmostEqual(float(outcome["actual_roll_qty"]), 0.0)
        self.assertAlmostEqual(float(outcome["cash_qty"]), 8000.0)
        self.assertAlmostEqual(float(outcome["cash_pnl"]), 40000.0)
        self.assertAlmostEqual(float(outcome["roll_pnl"]), 0.0)
        self.assertAlmostEqual(float(outcome["total_pnl"]), 40000.0)

    def test_build_open_lot_rows_supports_adjustment_only_vanilla_position(self) -> None:
        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "V_ONLY",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "date": "2026-04-01",
                    "generated_qty": 0.0,
                    "gen_price": 5.0,
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                },
                {
                    "group_id": "G1",
                    "structure_id": "V_ONLY",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "date": "2026-04-03",
                    "generated_qty": 0.0,
                    "gen_price": 5.0,
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                },
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "A_V_ONLY",
                    "adjust_batch_id": "VMAT_V_ONLY_20260403",
                    "group_id": "G1",
                    "structure_id": "V_ONLY",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 600.0,
                    "before_qty": 0.0,
                    "after_qty": 600.0,
                    "basis_open_price": 105.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 10:00:00",
                    "created_by": "tester",
                }
            ]
        )

        out = self.app.build_open_lot_rows(wh_cut, pd.DataFrame(), "2026-04-03", adjustments)

        self.assertAlmostEqual(float(pd.to_numeric(out["open_qty"], errors="coerce").sum()), 600.0)
        self.assertEqual(out["structure_id"].astype(str).tolist(), ["V_ONLY"])
        self.assertAlmostEqual(float(out.iloc[0]["gen_price"]), 105.0)

    def test_vanilla_maturity_adjustment_open_lot_is_trs_view(self) -> None:
        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "V_ROLL",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "date": "2026-04-03",
                    "generated_qty": 0.0,
                    "gen_price": 5.0,
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                    "option_type": "call",
                    "status": "行权",
                }
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "A_V_ROLL",
                    "adjust_batch_id": "VMAT_V_ROLL_20260403",
                    "group_id": "G1",
                    "structure_id": "V_ROLL",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 600.0,
                    "before_qty": 0.0,
                    "after_qty": 600.0,
                    "basis_open_price": 105.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 10:00:00",
                    "created_by": "tester",
                }
            ]
        )

        out = self.app.build_open_lot_rows(wh_cut, pd.DataFrame(), "2026-04-03", adjustments)

        self.assertEqual(out["structure_id"].astype(str).tolist(), ["V_ROLL"])
        self.assertEqual(str(out.iloc[0]["strategy_code"]), "TRS")
        self.assertEqual(str(out.iloc[0]["kind"]), "DEC")
        self.assertEqual(str(out.iloc[0]["status"]), "TRS持仓")
        self.assertEqual(int(out.iloc[0]["__vanilla_maturity_trs__"]), 1)
        self.assertIn("TRS", str(out.iloc[0]["name"]))
        self.assertAlmostEqual(float(out.iloc[0]["open_qty"]), 600.0)
        self.assertAlmostEqual(float(out.iloc[0]["gen_price"]), 105.0)

    def test_vanilla_maturity_put_roll_becomes_long_trs_kind(self) -> None:
        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "V_PUT_ROLL",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "date": "2026-04-03",
                    "generated_qty": 0.0,
                    "gen_price": 10.0,
                    "entry_price": 120.0,
                    "strike_price": 120.0,
                    "option_type": "put",
                    "status": "行权",
                }
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "A_V_PUT_ROLL",
                    "adjust_batch_id": "VMAT_V_PUT_ROLL_20260403",
                    "group_id": "G1",
                    "structure_id": "V_PUT_ROLL",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 600.0,
                    "before_qty": 0.0,
                    "after_qty": 600.0,
                    "basis_open_price": 110.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 10:00:00",
                    "created_by": "tester",
                }
            ]
        )

        out = self.app.build_open_lot_rows(wh_cut, pd.DataFrame(), "2026-04-03", adjustments)

        self.assertEqual(str(out.iloc[0]["strategy_code"]), "TRS")
        self.assertEqual(str(out.iloc[0]["kind"]), "ACC")

    def test_vanilla_maturity_trs_adjustment_does_not_reopen_original_vanilla_timeline(self) -> None:
        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "V_TIMELINE",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "date": "2026-04-02",
                    "generated_qty": 0.0,
                    "gen_price": 5.0,
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                    "option_type": "call",
                    "status": "未行权",
                },
                {
                    "group_id": "G1",
                    "structure_id": "V_TIMELINE",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "date": "2026-04-03",
                    "generated_qty": 0.0,
                    "gen_price": 5.0,
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                    "option_type": "call",
                    "status": "行权",
                },
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "A_V_TIMELINE",
                    "adjust_batch_id": "VMAT_V_TIMELINE_20260403",
                    "group_id": "G1",
                    "structure_id": "V_TIMELINE",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 600.0,
                    "before_qty": 0.0,
                    "after_qty": 600.0,
                    "basis_open_price": 105.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 10:00:00",
                    "created_by": "tester",
                }
            ]
        )

        timeline = self.app.build_structure_position_timeline_frame(
            wh_cut,
            pd.DataFrame(),
            adjustments,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
        )

        self.assertFalse(timeline.empty)
        self.assertAlmostEqual(float(timeline.iloc[-1]["current_open_qty"]), 0.0)

    def test_monitor_daily_frame_shows_vanilla_maturity_roll_as_trs_position(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "V_MON",
                    "structure_code": "S017",
                    "name": "卖出看涨",
                    "risk_party": "海证资本",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "status": "行权",
                    "raw_status": "到期结束-实值看涨卖出",
                    "normalized_status": "vanilla_expired_itm",
                    "flags": "VANILLA_EXPIRED_ITM",
                    "generated_qty": 0.0,
                    "cum_qty": 0.0,
                    "gen_price": 5.0,
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                    "premium": 5.0,
                    "option_type": "call",
                    "side": "sell",
                    "settle": 120.0,
                    "day_pnl": -15000.0,
                    "cum_pnl": -15000.0,
                    "day_subsidy_pnl": 0.0,
                    "cum_subsidy_pnl": 0.0,
                    "remaining_trading_days": 0,
                }
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "A_V_MON",
                    "adjust_batch_id": "VMAT_V_MON_20260403",
                    "group_id": "G1",
                    "structure_id": "V_MON",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 600.0,
                    "before_qty": 0.0,
                    "after_qty": 600.0,
                    "basis_open_price": 105.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 10:00:00",
                    "created_by": "tester",
                }
            ]
        )

        out = self.app.build_monitor_structure_daily_frame_cached(
            struct_daily,
            pd.DataFrame(),
            adjustments,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            sid_base_qty_per_day_map={"V_MON": 600.0},
            sid_structure_name_display_map={"V_MON": "卖出看涨"},
            sid_direction_display_map={"V_MON": "看涨"},
            sid_buy_sell_direction_map={"V_MON": "卖出"},
            sid_structure_detail_label_map={"V_MON": "S017-卖出看涨-海证资本"},
            structure_code_map={"V_MON": "S017"},
        )

        strategy_col = "\u7b56\u7565\u7c7b\u578b"
        trs_rows = out[out[strategy_col].astype(str).eq("TRS\u5934\u5bf8")].copy()
        vanilla_rows = out[out[strategy_col].astype(str).eq("\u9999\u8349\u671f\u6743")].copy()
        self.assertEqual(len(trs_rows), 1)
        self.assertEqual(str(trs_rows.iloc[0]["\u72b6\u6001"]), "TRS\u6301\u4ed3")
        self.assertAlmostEqual(float(trs_rows.iloc[0]["\u5f53\u524d\u6301\u4ed3\u91cf"]), 600.0)
        self.assertAlmostEqual(float(trs_rows.iloc[0]["\u5165\u573a\u4ef7"]), 105.0)
        self.assertAlmostEqual(float(trs_rows.iloc[0]["\u5f53\u65e5\u6d6e\u76c8\u4e8f"]), -9000.0)
        self.assertEqual(len(vanilla_rows), 1)
        self.assertAlmostEqual(float(vanilla_rows.iloc[0]["\u5f53\u524d\u6301\u4ed3\u91cf"]), 0.0)

    def test_monitor_report_runtime_separates_vmat_trs_lot_from_original_vanilla(self) -> None:
        self.insert_vanilla_structure(
            "V_REPORT",
            option_type="call",
            side="sell",
            base_qty=1000.0,
            strike_price=100.0,
            premium=5.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=600.0,
        )
        self.insert_prices("I.TEST", [("2026-04-03", 120.0)])
        self.app.sync_vanilla_maturity_records(self.conn)

        struct_df, _, bounds_df = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        runtime = self.app.build_monitor_report_runtime_cached(
            struct_df,
            struct_df,
            struct_df[struct_df["date"].astype(str).eq("2026-04-03")].copy(),
            bounds_df,
            self.app.fetch_closes2(self.conn),
            self.app.fetch_structure_position_adjustments(self.conn),
            pd.DataFrame(),
            self.app.fetch_structures(self.conn),
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            rep_und_all=False,
            inactive_sid_block={"V_REPORT"},
        )

        self.assertNotIn("V_REPORT", runtime.get("rep_open_qty_map", {}))
        vmat_lots = runtime.get("vmat_trs_open_lots")
        self.assertIsInstance(vmat_lots, pd.DataFrame)
        self.assertEqual(len(vmat_lots), 1)
        self.assertEqual(str(vmat_lots.iloc[0]["strategy_code"]), "TRS")
        self.assertEqual(str(vmat_lots.iloc[0]["kind"]), "DEC")
        self.assertAlmostEqual(float(vmat_lots.iloc[0]["open_qty"]), 600.0)
        self.assertAlmostEqual(float(vmat_lots.iloc[0]["gen_price"]), 105.0)

    def test_sync_vanilla_maturity_records_creates_cash_and_roll_records(self) -> None:
        self.insert_vanilla_structure(
            "V_SYNC",
            option_type="call",
            side="sell",
            base_qty=10000.0,
            strike_price=100.0,
            premium=5.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=6000.0,
        )
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 101.0),
                ("2026-04-02", 108.0),
                ("2026-04-03", 120.0),
            ],
        )

        result = self.app.sync_vanilla_maturity_records(self.conn)

        self.assertEqual(result["close_rows"], 2)
        self.assertEqual(result["adjust_rows"], 1)
        close2_df = self.app.fetch_closes2(self.conn)
        adj_df = self.app.fetch_structure_position_adjustments(self.conn)
        cash_rows = close2_df[
            close2_df["close_category"].astype(str).str.strip().eq(self.app.VANILLA_MATURITY_CASH_CLOSE_CATEGORY)
        ].copy()
        roll_rows = close2_df[
            close2_df["close_category"].astype(str).str.strip().eq(self.app.VANILLA_MATURITY_ROLL_CLOSE_CATEGORY)
        ].copy()

        self.assertEqual(len(cash_rows), 1)
        self.assertEqual(len(roll_rows), 1)
        self.assertAlmostEqual(float(cash_rows.iloc[0]["qty"]), 4000.0)
        self.assertAlmostEqual(float(cash_rows.iloc[0]["pnl"]), -60000.0)
        self.assertEqual(int(cash_rows.iloc[0]["is_external"]), 1)
        self.assertAlmostEqual(float(roll_rows.iloc[0]["qty"]), 6000.0)
        self.assertAlmostEqual(float(roll_rows.iloc[0]["pnl"]), 0.0)
        self.assertAlmostEqual(float(roll_rows.iloc[0]["roll_spread_pnl"]), 0.0)
        self.assertEqual(str(roll_rows.iloc[0]["side"]).upper(), "SELL")
        self.assertEqual(int(roll_rows.iloc[0]["is_external"]), 0)
        self.assertEqual(len(adj_df), 1)
        self.assertAlmostEqual(float(adj_df.iloc[0]["delta_qty"]), 6000.0)
        self.assertAlmostEqual(float(adj_df.iloc[0]["basis_open_price"]), 105.0)

        struct_df, group_df, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        struct_cut = struct_df[struct_df["group_id"].astype(str) == "G1"].copy()
        open_lots = self.app.build_open_lot_rows(struct_cut, close2_df, "2026-04-03", adj_df)
        self.assertAlmostEqual(float(pd.to_numeric(open_lots["open_qty"], errors="coerce").sum()), 6000.0)
        group_cut = group_df[
            group_df["date"].astype(str).eq("2026-04-03")
            & group_df["group_id"].astype(str).eq("G1")
            & group_df["underlying"].astype(str).eq("I.TEST")
        ].copy()
        self.assertEqual(len(group_cut), 1)
        self.assertAlmostEqual(float(group_cut.iloc[0]["close_pnl"]), -60000.0)
        self.assertAlmostEqual(float(group_cut.iloc[0]["option_pnl"]), 0.0)
        self.assertAlmostEqual(float(group_cut.iloc[0]["total_pnl"]), -60000.0)

        batch_snapshot = self.app.build_vanilla_maturity_batch_snapshot(
            close2_df,
            adj_df,
            structure_id="V_SYNC",
            expiry_date="2026-04-03",
        )
        self.assertTrue(bool(batch_snapshot["processed"]))
        self.assertAlmostEqual(float(batch_snapshot["cash_qty"]), 4000.0)
        self.assertAlmostEqual(float(batch_snapshot["roll_qty"]), 6000.0)
        self.assertAlmostEqual(float(batch_snapshot["roll_pnl"]), 0.0)
        self.assertAlmostEqual(float(batch_snapshot["total_pnl"]), -60000.0)

    def test_full_roll_recognizes_pnl_only_when_transferred_position_closes(self) -> None:
        self.insert_vanilla_structure(
            "V_ROLL_CLOSE",
            option_type="call",
            side="sell",
            base_qty=1000.0,
            strike_price=100.0,
            premium=5.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=1000.0,
        )
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 100.0),
                ("2026-04-02", 110.0),
                ("2026-04-03", 120.0),
                ("2026-04-07", 130.0),
            ],
        )

        self.app.sync_vanilla_maturity_records(
            self.conn,
            as_of_date="2026-04-03",
            structure_ids=["V_ROLL_CLOSE"],
        )
        close2_df = self.app.fetch_closes2(self.conn)
        adj_df = self.app.fetch_structure_position_adjustments(self.conn)
        struct_df, group_df, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        expiry_group = group_df[
            group_df["date"].astype(str).eq("2026-04-03")
            & group_df["group_id"].astype(str).eq("G1")
            & group_df["underlying"].astype(str).eq("I.TEST")
        ].copy()
        self.assertEqual(len(expiry_group), 1)
        self.assertAlmostEqual(float(expiry_group.iloc[0]["close_pnl"]), 0.0)
        self.assertAlmostEqual(float(expiry_group.iloc[0]["option_pnl"]), 0.0)
        self.assertAlmostEqual(float(expiry_group.iloc[0]["total_pnl"]), 0.0)

        open_lots = self.app.build_open_lot_rows(struct_df, close2_df, "2026-04-03", adj_df)
        self.assertAlmostEqual(float(pd.to_numeric(open_lots["open_qty"], errors="coerce").sum()), 1000.0)
        self.assertEqual(str(open_lots.iloc[0]["kind"]).upper(), "DEC")
        close_plan = self.app.build_manual_structure_close_rows(
            open_lots.to_dict("records"),
            kind=str(open_lots.iloc[0]["kind"]),
            side="BUY",
            qty=1000.0,
            total_pnl=-25000.0,
            close_dt="2026-04-07",
            group_id="G1",
            structure_id="V_ROLL_CLOSE",
            underlying="I.TEST",
            quick_batch_id="MANUAL_ROLL_CLOSE",
            close_category=self.app.STRUCT_CLOSE_CATEGORY,
        )
        self.app.insert_close_rows(self.conn, close_plan["rows"])
        self.conn.commit()

        _, group_after, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-07")
        close_group = group_after[
            group_after["date"].astype(str).eq("2026-04-07")
            & group_after["group_id"].astype(str).eq("G1")
            & group_after["underlying"].astype(str).eq("I.TEST")
        ].copy()
        self.assertEqual(len(close_group), 1)
        self.assertAlmostEqual(float(close_group.iloc[0]["close_pnl"]), -25000.0)
        self.assertAlmostEqual(float(close_group.iloc[0]["option_pnl"]), 0.0)
        self.assertAlmostEqual(float(close_group.iloc[0]["total_pnl"]), -25000.0)

    def test_close_detail_hides_full_roll_record_from_realized_close_monitor(self) -> None:
        self.insert_vanilla_structure(
            "V_FULL_ROLL",
            option_type="call",
            side="sell",
            base_qty=50000.0,
            strike_price=800.0,
            premium=3.8,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=50000.0,
            start_date="2026-04-16",
            end_date="2026-05-11",
            underlying="I2609",
        )
        self.insert_prices("I2609", [("2026-05-11", 822.5)])
        batch_id = self.app.build_vanilla_maturity_batch_id("V_FULL_ROLL", "2026-05-11")
        self.app.insert_close_rows(
            self.conn,
            [
                {
                    "close_id": f"{batch_id}_ROLL",
                    "dt": "2026-05-11",
                    "group_id": "G1",
                    "structure_id": "V_FULL_ROLL",
                    "underlying": "I2609",
                    "side": "SELL",
                    "qty": 50000.0,
                    "open_price": 803.8,
                    "close_price": 803.8,
                    "pnl": 0.0,
                    "roll_target_underlying": "I2609",
                    "roll_target_price": 803.8,
                    "roll_spread_pnl": 0.0,
                    "close_category": self.app.VANILLA_MATURITY_ROLL_CLOSE_CATEGORY,
                    "quick_batch_id": batch_id,
                    "is_external": 0,
                }
            ],
        )
        self.conn.commit()

        struct_daily, _, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-05-11")
        detail = self.app.build_close_detail_table(
            close2_df=self.app.fetch_closes2(self.conn),
            spot_match_df=pd.DataFrame(),
            rep_gid="G1",
            rep_und="I2609",
            rep_date="2026-05-11",
            group_name_map={"G1": "Group"},
            structs_df=self.app.fetch_structures(self.conn),
            groups_df=self.app.fetch_groups(self.conn),
            struct_daily_df=struct_daily,
        )

        self.assertTrue(detail.empty)


if __name__ == "__main__":
    unittest.main()
