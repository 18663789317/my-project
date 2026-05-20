import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_daily_structure_reminder_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DailyStructureReminderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_reminder_event_and_close_tables_keep_leading_column_ratios_aligned(self) -> None:
        event_total = float(self.app.DAILY_STRUCTURE_REMINDER_EVENT_TOTAL_WIDTH)
        close_total = float(self.app.DAILY_STRUCTURE_REMINDER_CLOSE_TOTAL_WIDTH)
        pairs = [
            (self.app.DAILY_STRUCTURE_REMINDER_LEAD_COL_WIDTH, self.app.DAILY_STRUCTURE_REMINDER_CLOSE_LEAD_COL_WIDTH),
            (self.app.DAILY_STRUCTURE_REMINDER_STRUCTURE_COL_WIDTH, self.app.DAILY_STRUCTURE_REMINDER_CLOSE_STRUCTURE_COL_WIDTH),
            (self.app.DAILY_STRUCTURE_REMINDER_CONTEXT_COL_WIDTH, self.app.DAILY_STRUCTURE_REMINDER_CLOSE_CONTEXT_COL_WIDTH),
            (self.app.DAILY_STRUCTURE_REMINDER_SIDE_COL_WIDTH, self.app.DAILY_STRUCTURE_REMINDER_CLOSE_SIDE_COL_WIDTH),
        ]
        for event_width, close_width in pairs:
            self.assertAlmostEqual(float(event_width) / event_total, float(close_width) / close_total, places=3)

    def test_payload_collects_events_and_all_close_qty_pnl(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-22",
                    "group_id": "G1",
                    "structure_id": "S_AB",
                    "name": "安全气囊",
                    "underlying": "I2605",
                    "kind": "DEC",
                    "strategy_code": "SAFETY_AIRBAG",
                    "status": "敲入转线性",
                    "raw_status": "敲入转线性",
                    "normalized_status": "airbag_knock_in_linear",
                    "generated_qty": 0.0,
                    "gen_price": 773.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                },
                {
                    "date": "2026-04-22",
                    "group_id": "G1",
                    "structure_id": "S_SB_KI",
                    "name": "雪球",
                    "underlying": "I2605",
                    "kind": "DEC",
                    "strategy_code": "SNOWBALL",
                    "status": "雪球已敲入计息中",
                    "raw_status": "雪球已敲入计息中",
                    "normalized_status": "snowball_knocked_in_observe",
                    "snowball_first_ki_date": "2026-04-22",
                    "generated_qty": 0.0,
                    "gen_price": 0.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                },
                {
                    "date": "2026-04-22",
                    "group_id": "G1",
                    "structure_id": "S_SB_KO",
                    "name": "雪球",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "strategy_code": "SNOWBALL",
                    "status": "雪球敲出",
                    "raw_status": "雪球敲出",
                    "normalized_status": "snowball_knock_out",
                    "generated_qty": 0.0,
                    "gen_price": 0.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 1200.0,
                },
                {
                    "date": "2026-04-22",
                    "group_id": "G1",
                    "structure_id": "S_MELT",
                    "name": "浮动熔断",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "strategy_code": "FLOAT_KO",
                    "status": "敲出熔断",
                    "raw_status": "敲出熔断",
                    "normalized_status": "accumulator_knock_out_terminate",
                    "generated_qty": 30000.0,
                    "gen_price": 820.0,
                    "day_pnl": 120000.0,
                    "day_subsidy_pnl": 0.0,
                },
            ]
        )
        close_detail = pd.DataFrame(
            [
                {
                    "日期": "2026-04-22",
                    "平仓类别": self.app.MANUAL_STRUCT_CLOSE_CATEGORY,
                    "结构": "S_MAN",
                    "品种": "I2605",
                    "方向": "卖平仓",
                    "数量": 30000.0,
                    "平仓价": 800.0,
                    "平仓盈亏": 200000.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 200000.0,
                },
                {
                    "日期": "2026-04-22",
                    "平仓类别": self.app.SUBSIDY_CLOSE_CATEGORY,
                    "结构": "S_FIX",
                    "品种": "I2605",
                    "方向": "买平仓",
                    "数量": 70000.0,
                    "平仓价": 0.0,
                    "平仓盈亏": 50000.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 50000.0,
                },
                {
                    "日期": "2026-04-21",
                    "平仓类别": self.app.STRUCT_CLOSE_CATEGORY,
                    "结构": "OLD",
                    "品种": "I2605",
                    "方向": "卖平仓",
                    "数量": 999.0,
                    "平仓价": 790.0,
                    "平仓盈亏": 999.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 999.0,
                },
            ]
        )

        payload = self.app.build_daily_structure_reminder_payload(
            struct_daily,
            close_detail,
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-04-22",
            sid_structure_detail_label_map={
                "S_AB": "S_AB-安全气囊",
                "S_SB_KI": "S_SB_KI-雪球",
                "S_SB_KO": "S_SB_KO-雪球",
                "S_MELT": "S_MELT-浮动熔断",
            },
        )

        self.assertTrue(payload["has_items"])
        metrics = payload["metrics"]
        self.assertAlmostEqual(float(metrics["close_qty_sum"]), 100000.0)
        self.assertAlmostEqual(float(metrics["close_total_pnl"]), 250000.0)
        self.assertAlmostEqual(float(metrics["long_close_qty"]), 30000.0)
        self.assertAlmostEqual(float(metrics["short_close_qty"]), 70000.0)

        event_text = " ".join(payload["events"]["事项"].astype(str).tolist())
        self.assertIn("气囊敲入", event_text)
        self.assertIn("雪球敲入", event_text)
        self.assertIn("雪球敲出", event_text)
        self.assertIn("熔断类结构", event_text)

        categories = set(payload["close_summary"]["平仓类别"].astype(str).tolist())
        self.assertIn(self.app.MANUAL_STRUCT_CLOSE_CATEGORY, categories)
        self.assertIn(self.app.SUBSIDY_CLOSE_CATEGORY, categories)

    def test_payload_uses_remaining_qty_for_natural_maturity(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-24",
                    "group_id": "G002",
                    "structure_id": "S018",
                    "name": "看跌安全气囊",
                    "underlying": "I2605",
                    "kind": "DEC",
                    "strategy_code": "SAFETY_AIRBAG",
                    "status": "未敲入到期保护",
                    "raw_status": "未敲入到期保护",
                    "normalized_status": "airbag_maturity_protect",
                    "generated_qty": 0.0,
                    "cum_qty": 5000.0,
                    "gen_price": 773.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                }
            ]
        )
        close_detail = pd.DataFrame(
            [
                {
                    "日期": "2026-04-24",
                    "平仓类别": self.app.NATURAL_MATURITY_CLOSE_CATEGORY,
                    "结构": "S018-看跌安全气囊",
                    "品种": "I2605",
                    "方向": "到期结束",
                    "数量": 5000.0,
                    "平仓价": 773.0,
                    "平仓盈亏": 0.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 0.0,
                }
            ]
        )

        payload = self.app.build_daily_structure_reminder_payload(
            struct_daily,
            close_detail,
            rep_gid="G002",
            rep_und="I2605",
            rep_date="2026-04-24",
            sid_structure_detail_label_map={"S018": "S018-看跌安全气囊"},
        )

        self.assertTrue(payload["has_items"])
        self.assertAlmostEqual(float(payload["events"].iloc[0]["吨数"]), 5000.0)
        self.assertAlmostEqual(float(payload["close_summary"].iloc[0]["吨数"]), 5000.0)
        self.assertAlmostEqual(float(payload["metrics"]["close_qty_sum"]), 5000.0)

    def test_payload_uses_natural_close_detail_pnl_for_vanilla_event(self) -> None:
        struct_label = "S002-\u5356\u51fa\u770b\u6da8-\u6d77\u8bc1\u8d44\u672c"
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-05-11",
                    "group_id": "G003",
                    "structure_id": "V_CALL_SELL",
                    "name": "\u5356\u51fa\u770b\u6da8",
                    "underlying": "I2609",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "status": "\u884c\u6743",
                    "status_cn": "\u884c\u6743",
                    "raw_status": "\u5230\u671f\u7ed3\u675f-\u5b9e\u503c\u5356\u51fa\u770b\u6da8",
                    "normalized_status": "vanilla_expired_itm",
                    "generated_qty": 0.0,
                    "base_qty_per_day": 50000.0,
                    "current_open_qty": 50000.0,
                    "gen_price": 3.8,
                    "settle": 822.5,
                    "day_pnl": -400000.0,
                    "day_subsidy_pnl": 0.0,
                }
            ]
        )
        close_detail = pd.DataFrame(
            [
                {
                    "\u65e5\u671f": "2026-05-11",
                    "\u5e73\u4ed3\u7c7b\u522b": self.app.VANILLA_MATURITY_ROLL_CLOSE_CATEGORY,
                    "\u7ed3\u6784": struct_label,
                    "\u54c1\u79cd": "I2609",
                    "\u65b9\u5411": "\u5356\u5e73\u4ed3",
                    "\u6570\u91cf": 50000.0,
                    "\u5e73\u4ed3\u4ef7": 822.5,
                    "\u5e73\u4ed3\u76c8\u4e8f": -935000.0,
                    "\u73b0\u8d27\u76c8\u4e8f": 0.0,
                    "\u5408\u8ba1\u76c8\u4e8f": -935000.0,
                    "\u5e73\u4ed3\u6279\u6b21\u53f7": "VMAT_V_CALL_SELL_20260511",
                }
            ]
        )

        payload = self.app.build_daily_structure_reminder_payload(
            struct_daily,
            close_detail,
            rep_gid="G003",
            rep_und="I2609",
            rep_date="2026-05-11",
            sid_structure_detail_label_map={"V_CALL_SELL": struct_label},
        )

        self.assertTrue(payload["has_items"])
        self.assertAlmostEqual(float(payload["events"].iloc[0]["\u76c8\u4e8f"]), -935000.0)
        self.assertAlmostEqual(float(payload["close_summary"].iloc[0]["\u5e73\u4ed3\u76c8\u4e8f"]), -935000.0)
        self.assertAlmostEqual(float(payload["metrics"]["close_total_pnl"]), -935000.0)

    def test_payload_backfills_zero_safety_airbag_close_qty_from_display_notional(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-24",
                    "group_id": "G002",
                    "structure_id": "S018",
                    "name": "看跌安全气囊",
                    "underlying": "I2605",
                    "kind": "DEC",
                    "strategy_code": "SAFETY_AIRBAG",
                    "status": "未敲入到期保护",
                    "raw_status": "未敲入到期保护",
                    "normalized_status": "airbag_maturity_protect",
                    "generated_qty": 0.0,
                    "cum_qty": 0.0,
                    "current_open_qty": 0.0,
                    "base_qty_per_day": 5000.0,
                    "gen_price": 773.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                }
            ]
        )
        close_detail = pd.DataFrame(
            [
                {
                    "日期": "2026-04-24",
                    "平仓类别": self.app.NATURAL_MATURITY_CLOSE_CATEGORY,
                    "结构": "S018-看跌安全气囊",
                    "品种": "I2605",
                    "方向": "到期结束",
                    "数量": 0.0,
                    "平仓价": 773.0,
                    "平仓盈亏": 0.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 0.0,
                    "平仓批次号": "NATURAL_MATURITY_S018_2026-04-24",
                }
            ]
        )

        payload = self.app.build_daily_structure_reminder_payload(
            struct_daily,
            close_detail,
            rep_gid="G002",
            rep_und="I2605",
            rep_date="2026-04-24",
            sid_structure_detail_label_map={"S018": "S018-看跌安全气囊"},
            sid_display_notional_qty_map={"S018": -10000.0},
        )

        self.assertTrue(payload["has_items"])
        self.assertAlmostEqual(float(payload["events"].iloc[0]["吨数"]), 10000.0)
        self.assertAlmostEqual(float(payload["close_summary"].iloc[0]["吨数"]), 10000.0)
        self.assertAlmostEqual(float(payload["metrics"]["close_qty_sum"]), 10000.0)

    def test_payload_uses_snowball_discount_futures_float_pnl_for_tracking_event(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-22",
                    "group_id": "G1",
                    "structure_id": "S_DISC",
                    "name": "Snowball",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "strategy_code": "SNOWBALL",
                    "status": "雪球折价转期货跟踪",
                    "raw_status": "雪球折价转期货跟踪",
                    "normalized_status": "snowball_discount_track",
                    "generated_qty": 0.0,
                    "gen_price": 760.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                    "snowball_futures_float_pnl": -12345.67,
                }
            ]
        )

        payload = self.app.build_daily_structure_reminder_payload(
            struct_daily,
            pd.DataFrame(),
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-04-22",
            sid_structure_detail_label_map={"S_DISC": "S_DISC-Snowball"},
        )

        pnl_col = self.app.DAILY_STRUCTURE_REMINDER_EVENT_COLUMNS[-1]
        self.assertTrue(payload["has_items"])
        self.assertAlmostEqual(float(payload["events"].iloc[0][pnl_col]), -12345.67)

    def test_close_record_count_uses_summary_rows_not_underlying_detail_rows(self) -> None:
        close_detail = pd.DataFrame(
            [
                {
                    "日期": "2026-05-19",
                    "平仓类别": self.app.STRUCT_CLOSE_CATEGORY,
                    "结构": "S012-固定熔断",
                    "品种": "I2609",
                    "方向": "买平仓",
                    "数量": 1000.0,
                    "平仓价": 799.5,
                    "平仓盈亏": 100.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 100.0,
                },
                {
                    "日期": "2026-05-19",
                    "平仓类别": self.app.STRUCT_CLOSE_CATEGORY,
                    "结构": "S012-固定熔断",
                    "品种": "I2609",
                    "方向": "买平仓",
                    "数量": 1000.0,
                    "平仓价": 799.5,
                    "平仓盈亏": 200.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 200.0,
                },
            ]
        )

        payload = self.app.build_daily_structure_reminder_payload(
            pd.DataFrame(),
            close_detail,
            rep_gid="G1",
            rep_und="I2609",
            rep_date="2026-05-19",
        )

        self.assertEqual(len(payload["close_detail"]), 2)
        self.assertEqual(len(payload["close_summary"]), 1)
        self.assertAlmostEqual(float(payload["metrics"]["close_record_count"]), 1.0)
        self.assertAlmostEqual(float(payload["metrics"]["close_qty_sum"]), 2000.0)

    def test_payload_hides_when_no_same_day_items(self) -> None:
        payload = self.app.build_daily_structure_reminder_payload(
            pd.DataFrame(
                [
                    {
                        "date": "2026-04-21",
                        "group_id": "G1",
                        "structure_id": "S1",
                        "underlying": "I2605",
                        "strategy_code": "FLOAT_KO",
                        "status": "敲出熔断",
                        "normalized_status": "accumulator_knock_out_terminate",
                    }
                ]
            ),
            pd.DataFrame(
                [
                    {
                        "日期": "2026-04-21",
                        "平仓类别": self.app.STRUCT_CLOSE_CATEGORY,
                        "结构": "S1",
                        "品种": "I2605",
                        "方向": "卖平仓",
                        "数量": 100.0,
                        "平仓盈亏": 1.0,
                        "现货盈亏": 0.0,
                        "合计盈亏": 1.0,
                    }
                ]
            ),
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-04-22",
        )

        self.assertFalse(payload["has_items"])
        self.assertTrue(payload["events"].empty)
        self.assertTrue(payload["close_summary"].empty)


if __name__ == "__main__":
    unittest.main()
