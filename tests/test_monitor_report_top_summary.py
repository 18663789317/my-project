import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_report_top_summary_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorReportTopSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_build_five_trading_day_close_delta_map_requires_five_prior_price_rows(self) -> None:
        prices_df = pd.DataFrame(
            {
                "dt": [
                    "2026-04-01",
                    "2026-04-02",
                    "2026-04-03",
                    "2026-04-06",
                    "2026-04-07",
                    "2026-04-08",
                    "2026-04-08",
                ],
                "underlying": ["I2609"] * 7,
                "settle": [800.0, 806.0, 810.0, 812.0, 818.0, 824.0, 825.0],
            }
        )

        actual = self.app.build_five_trading_day_close_delta_map(prices_df, ["I2609"], "2026-04-08")
        missing = self.app.build_five_trading_day_close_delta_map(prices_df, ["I2609"], "2026-04-07")

        self.assertEqual(actual, {"I2609": 25.0})
        self.assertEqual(missing, {})

    def test_compute_option_warehouse_position_summary_matches_overview_side_avgs(self) -> None:
        open_lots = pd.DataFrame(
            [
                {"kind": "ACC", "open_qty": 10000.0, "gen_price": 790.0},
                {"kind": "ACC", "open_qty": 6000.0, "gen_price": 800.0},
                {"kind": "DEC", "open_qty": 14000.0, "gen_price": 810.0},
                {"kind": "DEC", "open_qty": 12000.0, "gen_price": 790.0},
            ]
        )

        summary = self.app.compute_option_warehouse_position_summary(open_lots)

        self.assertAlmostEqual(summary["long_qty"], 16000.0)
        self.assertAlmostEqual(summary["short_qty"], 26000.0)
        self.assertAlmostEqual(summary["long_avg"], 793.75)
        self.assertAlmostEqual(summary["short_avg"], 800.7692307692307)

    def test_format_report_position_summary_lines_shows_short_left_long_right(self) -> None:
        lines = self.app.format_report_position_summary_lines(
            {
                "short_qty": 268200.0,
                "short_avg": 800.73,
                "long_qty": 120000.0,
                "long_avg": 790.25,
            }
        )

        self.assertEqual(lines, ["-26.8W吨/+12.0W吨", "均价：800.73/790.25"])

    def test_format_report_position_summary_lines_keeps_single_side_on_one_line(self) -> None:
        short_only = self.app.format_report_position_summary_lines(
            {
                "short_qty": 50000.0,
                "short_avg": 803.8,
                "long_qty": 0.0,
                "long_avg": None,
            }
        )
        long_only = self.app.format_report_position_summary_lines(
            {
                "short_qty": 0.0,
                "short_avg": None,
                "long_qty": 120000.0,
                "long_avg": 790.25,
            }
        )

        self.assertEqual(short_only, ["-5.0W吨 均价：803.80"])
        self.assertEqual(long_only, ["+12.0W吨 均价：790.25"])

    def test_build_position_display_lines_keeps_single_side_on_one_line(self) -> None:
        lines = self.app._build_position_display_lines(
            {
                "short_qty": 50000.0,
                "short_avg": 803.8,
                "long_qty": 0.0,
                "long_avg": None,
            },
            "#red",
            "#green",
            "#white",
        )

        self.assertEqual(lines, [("-5.0W吨 均价：803.80", "#green")])

    def test_report_monitor_trs_float_pnl_value_uses_day_close_price_formula(self) -> None:
        item = {
            "strategy_code": "TRS",
            "kind": "DEC",
            "open_position_qty": 50000.0,
            "open_avg_price": 803.8,
            "settle_price": 809.5,
        }

        actual = self.app.report_monitor_trs_float_pnl_value(item)

        self.assertAlmostEqual(actual, -50000.0 * (809.5 - 803.8))

    def test_report_monitor_trs_float_pnl_value_uses_signed_quantity_without_double_flip(self) -> None:
        item = {
            "strategy_code": "TRS",
            "kind": "DEC",
            "open_position_qty": 50000.0,
            "open_position_qty_signed": -50000.0,
            "open_avg_price": 803.8,
            "settle_price": 803.0,
            "floating_pnl": -40000.0,
        }

        self.assertAlmostEqual(self.app.report_monitor_trs_float_pnl_value(item), 40000.0)

    def test_build_trs_monitor_frame_keeps_quantity_sign_for_short_trs(self) -> None:
        src = pd.DataFrame(
            [
                {
                    "日期": "2026-05-18",
                    "结构ID": "S002",
                    "结构": "S002-I2609-803.8-TRS",
                    "风险子": "CP",
                    "方向": "看跌",
                    "策略类型": "TRS头寸",
                    "当前持仓量": 50000.0,
                    "累计生成量": 50000.0,
                    "入场价": 803.8,
                    "当日浮盈亏": 40000.0,
                }
            ]
        )

        out = self.app.build_trs_monitor_frame(src)

        self.assertAlmostEqual(float(out.iloc[0]["数量"]), -50000.0)
        self.assertAlmostEqual(float(out.iloc[0]["当日浮盈亏"]), 40000.0)

    def test_report_monitor_trs_float_pnl_value_formula_overrides_stale_display_value(self) -> None:
        item = {
            "kind": "ACC",
            "open_position_qty": 100.0,
            "open_avg_price": 800.0,
            "settle_price": 805.0,
            "floating_pnl": -123.45,
        }

        self.assertAlmostEqual(self.app.report_monitor_trs_float_pnl_value(item), 500.0)

    def test_report_monitor_trs_float_pnl_value_reuses_explicit_value_without_prices(self) -> None:
        item = {
            "kind": "ACC",
            "open_position_qty": 100.0,
            "floating_pnl": -123.45,
        }

        self.assertAlmostEqual(self.app.report_monitor_trs_float_pnl_value(item), -123.45)


if __name__ == "__main__":
    unittest.main()
