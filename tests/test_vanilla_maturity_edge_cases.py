"""验证报告中未覆盖的三个边界场景：
1. 全部现金结算（无转远期）→ total_pnl 应等于 cash_pnl
2. cash_settle_pnl 与 option_pnl 的 settle 来源一致性
3. 转远期 close 记录不进入 close_pnl（通过 close2 遍历 continue 跳过）
"""
import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_vanilla_maturity_edge_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VanillaMaturityEdgeCaseTests(unittest.TestCase):
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
            ("G1", "香草边界测试组", "I.TEST"),
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
                structure_id, group_id, structure_id, structure_id, underlying,
                "海证资本",
                "DEC" if side == "sell" else "ACC",
                self.app.VANILLA_OPTION_CODE,
                self.app.VANILLA_OPTION_CODE,
                start_date, end_date, base_qty, entry_price, strike_price, 1.0,
                start_date, end_date, option_type, side, premium,
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

    # -------------------------------------------------------------------
    # 问题2：全部现金结算（无转远期）
    # -------------------------------------------------------------------
    def test_full_cash_settle_no_roll_total_pnl_equals_cash_pnl(self) -> None:
        """mode=CASH，全部走现金结算，无转远期。
        到期日 total_pnl 应等于 cash_pnl（即 unit_pnl * total_qty）。"""
        self.insert_vanilla_structure(
            "V_FULL_CASH",
            option_type="call",
            side="sell",
            base_qty=10000.0,
            strike_price=100.0,
            premium=5.0,
            # 强制现金结算模式
            maturity_mode=self.app.VANILLA_MATURITY_MODE_CASH,
            maturity_roll_qty=0.0,
        )
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 101.0),
                ("2026-04-02", 108.0),
                ("2026-04-03", 120.0),  # 到期日结算价
            ],
        )

        # sync 生成 close 记录
        result = self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-04-03")
        self.assertEqual(result["close_rows"], 1, "应只生成1条现金结算记录，无转远期记录")

        close2_df = self.app.fetch_closes2(self.conn)
        cash_rows = close2_df[
            close2_df["close_category"].astype(str).str.strip().eq(self.app.VANILLA_MATURITY_CASH_CLOSE_CATEGORY)
        ].copy()
        roll_rows = close2_df[
            close2_df["close_category"].astype(str).str.strip().eq(self.app.VANILLA_MATURITY_ROLL_CLOSE_CATEGORY)
        ].copy()
        self.assertEqual(len(cash_rows), 1)
        self.assertEqual(len(roll_rows), 0, "CASH模式不应生成转远期记录")

        # call sell: roll_target_price = 100 + 5 = 105
        # unit_pnl = 105 - 120 = -15
        # cash_pnl = -15 * 10000 = -150000
        expected_cash_pnl = -150000.0
        self.assertAlmostEqual(float(cash_rows.iloc[0]["pnl"]), expected_cash_pnl)
        self.assertAlmostEqual(float(cash_rows.iloc[0]["qty"]), 10000.0)

        # 计算台账
        _, group_df, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        expiry_group = group_df[
            group_df["date"].astype(str).eq("2026-04-03")
            & group_df["group_id"].astype(str).eq("G1")
            & group_df["underlying"].astype(str).eq("I.TEST")
        ].copy()
        self.assertEqual(len(expiry_group), 1)

        actual_close_pnl = float(expiry_group.iloc[0]["close_pnl"])
        actual_option_pnl = float(expiry_group.iloc[0]["option_pnl"])
        actual_total_pnl = float(expiry_group.iloc[0]["total_pnl"])

        # close_pnl 应等于现金结算 pnl
        self.assertAlmostEqual(actual_close_pnl, expected_cash_pnl,
                               msg="close_pnl 应等于现金结算 pnl")
        # option_pnl 应为0（现金结算部分已从 option_pnl 扣除）
        self.assertAlmostEqual(actual_option_pnl, 0.0,
                               msg="option_pnl 应为0（现金结算已扣除）")
        # total_pnl = close_pnl + option_pnl + subsidy_pnl
        self.assertAlmostEqual(actual_total_pnl, expected_cash_pnl,
                               msg="total_pnl 应等于 cash_pnl")

    def test_full_cash_settle_put_option(self) -> None:
        """put 卖方全部现金结算。"""
        self.insert_vanilla_structure(
            "V_CASH_PUT",
            option_type="put",
            side="sell",
            base_qty=8000.0,
            strike_price=120.0,
            premium=10.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_CASH,
            maturity_roll_qty=0.0,
            start_date="2026-06-01",
            end_date="2026-06-05",
        )
        self.insert_prices(
            "I.TEST",
            [
                ("2026-06-01", 118.0),
                ("2026-06-02", 115.0),
                ("2026-06-03", 112.0),
                ("2026-06-04", 110.0),
                ("2026-06-05", 105.0),  # 到期日，跌到105
            ],
        )

        self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-06-05")

        # put sell: roll_target_price = 120 - 10 = 110
        # unit_pnl = settle - roll_target = 105 - 110 = -5
        # cash_pnl = -5 * 8000 = -40000
        expected_cash_pnl = -40000.0

        _, group_df, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-06-05")
        expiry_group = group_df[
            group_df["date"].astype(str).eq("2026-06-05")
            & group_df["group_id"].astype(str).eq("G1")
            & group_df["underlying"].astype(str).eq("I.TEST")
        ].copy()
        self.assertEqual(len(expiry_group), 1)
        self.assertAlmostEqual(float(expiry_group.iloc[0]["total_pnl"]), expected_cash_pnl,
                               msg="put 卖方全部现金结算 total_pnl 应等于 cash_pnl")
        self.assertAlmostEqual(float(expiry_group.iloc[0]["option_pnl"]), 0.0,
                               msg="option_pnl 应为0")

    # -------------------------------------------------------------------
    # 问题3：cash_settle_pnl 与 option_pnl 的 settle 来源一致性
    # -------------------------------------------------------------------
    def test_settle_price_consistency_between_sync_and_ledger(self) -> None:
        """sync_vanilla_maturity_records 用价格A写入 cash_pnl，
        compute_ledgers 用同一个价格表计算 option_pnl。
        两者基于相同 settle，扣减应精确抵消。
        如果价格表被修改（先sync再改价再算台账），则扣减不精确。"""
        self.insert_vanilla_structure(
            "V_CONSIST",
            option_type="call",
            side="sell",
            base_qty=10000.0,
            strike_price=100.0,
            premium=5.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=0.0,  # 全部走现金
        )
        # 场景A：sync 和 ledger 用同一个价格 → 应精确抵消
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 101.0),
                ("2026-04-02", 108.0),
                ("2026-04-03", 120.0),
            ],
        )

        self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-04-03")

        # 验证：同步价格 = ledger价格 → option_pnl 应为 0
        _, group_df_a, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        g_a = group_df_a[
            group_df_a["date"].astype(str).eq("2026-04-03")
            & group_df_a["group_id"].astype(str).eq("G1")
        ].copy()
        self.assertEqual(len(g_a), 1)
        option_pnl_a = float(g_a.iloc[0]["option_pnl"])
        self.assertAlmostEqual(option_pnl_a, 0.0, places=4,
                               msg="同一价格下 option_pnl 应精确为0（cash_settle_pnl 完全抵消）")

    def test_settle_price_mismatch_reveals_deduction_mismatch(self) -> None:
        """如果 sync 时价格=120，但之后价格被改为125再算台账，
        cash_settle_pnl 仍按120扣除，但 option_pnl 按125计算。
        这会导致 option_pnl 不为0（扣减不精确）。
        此测试验证这种不一致确实会发生（暴露时序依赖风险）。"""
        self.insert_vanilla_structure(
            "V_MISMATCH",
            option_type="call",
            side="sell",
            base_qty=10000.0,
            strike_price=100.0,
            premium=5.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=0.0,
        )
        # 先用价格120 sync
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 101.0),
                ("2026-04-02", 108.0),
                ("2026-04-03", 120.0),
            ],
        )
        self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-04-03")

        # 清缓存
        for cache_name in ["_FETCH_SQL_MEMO_CACHE", "_LEDGER_MEMO_CACHE"]:
            cache_obj = getattr(self.app, cache_name, None)
            if hasattr(cache_obj, "clear"):
                cache_obj.clear()

        # 修改到期日价格为125
        self.conn.execute(
            "UPDATE price SET settle=? WHERE dt=? AND underlying=?",
            (125.0, "2026-04-03", "I.TEST"),
        )
        self.conn.commit()

        _, group_df_b, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        g_b = group_df_b[
            group_df_b["date"].astype(str).eq("2026-04-03")
            & group_df_b["group_id"].astype(str).eq("G1")
        ].copy()
        self.assertEqual(len(g_b), 1)
        option_pnl_b = float(g_b.iloc[0]["option_pnl"])
        total_pnl_b = float(g_b.iloc[0]["total_pnl"])

        # cash_settle_pnl 按120计算 = (105-120)*10000 = -150000
        # option_pnl 按125计算：state machine 会生成一个到期 option_pnl
        # 扣减后 option_pnl = 原始option_pnl - (-150000)
        # 如果原始 option_pnl 按125算是 (105-125)*10000 = -200000
        # 则 option_pnl = -200000 - (-150000) = -50000
        # 这意味着 option_pnl 不为0，暴露了时序依赖
        self.assertNotAlmostEqual(option_pnl_b, 0.0, places=2,
                                  msg="价格不一致时 option_pnl 不应为0，暴露时序依赖风险")

        # total_pnl 也会有偏差
        # 业务上正确口径应按125计算 = -200000
        # 但实际 close_pnl 仍按120的 -150000，option_pnl = -50000
        # total_pnl = -150000 + (-50000) = -200000（恰好正确！）
        # 这是因为 close_pnl + option_pnl 恰好等于完整口径
        # 但如果 close_pnl 和 option_pnl 分别看，就不准确
        expected_total_if_125 = (105.0 - 125.0) * 10000.0  # -200000
        self.assertAlmostEqual(total_pnl_b, expected_total_if_125, places=2,
                               msg="total_pnl 在价格不一致时仍应等于最终价格的完整口径")

    # -------------------------------------------------------------------
    # 问题4：转远期 close 记录不进入 close_pnl
    # -------------------------------------------------------------------
    def test_roll_only_scenario_close_pnl_is_zero(self) -> None:
        """全部转远期（无现金结算），到期日 close_pnl 应为0。
        验证 close2 遍历中 continue 跳过转远期记录。"""
        self.insert_vanilla_structure(
            "V_ROLL_ONLY",
            option_type="call",
            side="sell",
            base_qty=10000.0,
            strike_price=100.0,
            premium=5.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=10000.0,  # 全部转远期
        )
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 101.0),
                ("2026-04-02", 108.0),
                ("2026-04-03", 120.0),
            ],
        )

        result = self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-04-03")
        # 不利时全部转远期：actual_roll_qty = 10000, cash_qty = 0
        self.assertEqual(result["close_rows"], 1, "应只有1条转远期记录，无现金结算")

        close2_df = self.app.fetch_closes2(self.conn)
        roll_rows = close2_df[
            close2_df["close_category"].astype(str).str.strip().eq(self.app.VANILLA_MATURITY_ROLL_CLOSE_CATEGORY)
        ].copy()
        self.assertEqual(len(roll_rows), 1)
        self.assertAlmostEqual(float(roll_rows.iloc[0]["pnl"]), 0.0, msg="转远期 pnl 应为0")

        _, group_df, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        expiry_group = group_df[
            group_df["date"].astype(str).eq("2026-04-03")
            & group_df["group_id"].astype(str).eq("G1")
            & group_df["underlying"].astype(str).eq("I.TEST")
        ].copy()
        self.assertEqual(len(expiry_group), 1)

        actual_close_pnl = float(expiry_group.iloc[0]["close_pnl"])
        actual_option_pnl = float(expiry_group.iloc[0]["option_pnl"])
        actual_total_pnl = float(expiry_group.iloc[0]["total_pnl"])

        self.assertAlmostEqual(actual_close_pnl, 0.0,
                               msg="全部转远期时 close_pnl 应为0（转远期记录被 continue 跳过）")
        self.assertAlmostEqual(actual_option_pnl, 0.0,
                               msg="全部转远期时 option_pnl 应为0（已扣除 roll_settle_pnl）")
        self.assertAlmostEqual(actual_total_pnl, 0.0,
                               msg="全部转远期时 total_pnl 应为0")

    def test_roll_close_record_does_not_enter_close_map(self) -> None:
        """验证转远期 close 记录不进入 close_map_by_dt：
        先sync生成转远期记录，再手动平仓该转远期头寸。
        手动平仓的 pnl 应该是最终确认的盈亏，不包含到期当天的隐含盈亏。"""
        self.insert_vanilla_structure(
            "V_ROLL_MAP",
            option_type="call",
            side="sell",
            base_qty=10000.0,
            strike_price=100.0,
            premium=5.0,
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=10000.0,
        )
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 101.0),
                ("2026-04-02", 108.0),
                ("2026-04-03", 120.0),  # 到期日
                ("2026-04-07", 130.0),  # 未来平仓日
            ],
        )

        self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-04-03")

        # 到期日 total_pnl 应为0
        _, group_df_expiry, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        g_expiry = group_df_expiry[
            group_df_expiry["date"].astype(str).eq("2026-04-03")
            & group_df_expiry["group_id"].astype(str).eq("G1")
        ].copy()
        self.assertEqual(len(g_expiry), 1)
        self.assertAlmostEqual(float(g_expiry.iloc[0]["total_pnl"]), 0.0,
                               msg="到期日 total_pnl 应为0")

        # 模拟未来手动平仓：以-25000的盈亏平掉转远期头寸
        close2_df = self.app.fetch_closes2(self.conn)
        adj_df = self.app.fetch_structure_position_adjustments(self.conn)
        struct_df, _, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        open_lots = self.app.build_open_lot_rows(struct_df, close2_df, "2026-04-03", adj_df)
        self.assertGreater(float(pd.to_numeric(open_lots["open_qty"], errors="coerce").sum()), 0.0,
                           msg="转远期后应有在库头寸")

        close_plan = self.app.build_manual_structure_close_rows(
            open_lots.to_dict("records"),
            kind=str(open_lots.iloc[0]["kind"]),
            side="BUY",
            qty=10000.0,
            total_pnl=-25000.0,
            close_dt="2026-04-07",
            group_id="G1",
            structure_id="V_ROLL_MAP",
            underlying="I.TEST",
            quick_batch_id="MANUAL_ROLL_CLOSE_2",
            close_category=self.app.STRUCT_CLOSE_CATEGORY,
        )
        self.app.insert_close_rows(self.conn, close_plan["rows"])
        self.conn.commit()

        # 清缓存
        for cache_name in ["_FETCH_SQL_MEMO_CACHE", "_LEDGER_MEMO_CACHE"]:
            cache_obj = getattr(self.app, cache_name, None)
            if hasattr(cache_obj, "clear"):
                cache_obj.clear()

        _, group_df_after, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-07")
        close_group = group_df_after[
            group_df_after["date"].astype(str).eq("2026-04-07")
            & group_df_after["group_id"].astype(str).eq("G1")
            & group_df_after["underlying"].astype(str).eq("I.TEST")
        ].copy()
        self.assertEqual(len(close_group), 1)
        self.assertAlmostEqual(float(close_group.iloc[0]["close_pnl"]), -25000.0,
                               msg="未来平仓的 close_pnl 应等于手工输入的盈亏")
        self.assertAlmostEqual(float(close_group.iloc[0]["total_pnl"]), -25000.0,
                               msg="未来平仓的 total_pnl 应等于 close_pnl")


if __name__ == "__main__":
    unittest.main()
