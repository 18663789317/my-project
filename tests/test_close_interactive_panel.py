import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_close_interactive_panel_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CloseInteractivePanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_close_event_daily_aggregates_qty_pnl_and_cumulative(self) -> None:
        close_detail = pd.DataFrame(
            [
                {"日期": "2026-04-01", "结构": "S1", "品种": "I.TEST", "数量": 100.0, "平仓价": 780.0, "平仓盈亏": 1200.0, "现货盈亏": 0.0, "合计盈亏": 1200.0},
                {"日期": "2026-04-01", "结构": "S2", "品种": "I.TEST", "数量": 300.0, "平仓价": 790.0, "平仓盈亏": -500.0, "现货盈亏": 200.0, "合计盈亏": -300.0},
                {"日期": "2026-04-02", "结构": "S3", "品种": "I.TEST", "数量": 200.0, "平仓价": 800.0, "平仓盈亏": 1000.0, "现货盈亏": 0.0, "合计盈亏": 1000.0},
            ]
        )

        daily = self.app.build_close_event_daily(close_detail)

        self.assertEqual(daily["日期"].astype(str).tolist(), ["2026-04-01", "2026-04-02"])
        first = daily.iloc[0]
        self.assertEqual(int(first["记录数"]), 2)
        self.assertAlmostEqual(float(first["平仓数量"]), 400.0)
        self.assertAlmostEqual(float(first["平仓均价"]), 787.5)
        self.assertAlmostEqual(float(first["结构盈亏"]), 700.0)
        self.assertAlmostEqual(float(first["现货盈亏"]), 200.0)
        self.assertAlmostEqual(float(first["合计盈亏"]), 900.0)
        self.assertAlmostEqual(float(daily.iloc[-1]["累计盈亏"]), 1900.0)

    def test_profit_kline_plot_df_uses_daily_pnl_as_candle_body(self) -> None:
        close_detail = pd.DataFrame(
            [
                {"日期": "2026-04-01", "结构": "S1", "品种": "I.TEST", "数量": 100.0, "平仓价": 780.0, "平仓盈亏": 1200.0, "现货盈亏": 0.0, "合计盈亏": 1200.0},
                {"日期": "2026-04-01", "结构": "S2", "品种": "I.TEST", "数量": 300.0, "平仓价": 790.0, "平仓盈亏": -500.0, "现货盈亏": 200.0, "合计盈亏": -300.0},
                {"日期": "2026-04-02", "结构": "S3", "品种": "I.TEST", "数量": 200.0, "平仓价": 800.0, "平仓盈亏": -400.0, "现货盈亏": 0.0, "合计盈亏": -400.0},
            ]
        )
        daily = self.app.build_close_event_daily(close_detail)

        plot_df = self.app.build_close_profit_kline_plot_df(daily)

        self.assertEqual(plot_df["日期"].astype(str).tolist(), ["2026-04-01", "2026-04-02"])
        self.assertAlmostEqual(float(plot_df.iloc[0]["开盘累计盈亏"]), 0.0)
        self.assertAlmostEqual(float(plot_df.iloc[0]["收盘累计盈亏"]), 900.0)
        self.assertAlmostEqual(float(plot_df.iloc[0]["当日盈亏"]), 900.0)
        self.assertAlmostEqual(float(plot_df.iloc[1]["开盘累计盈亏"]), 900.0)
        self.assertAlmostEqual(float(plot_df.iloc[1]["收盘累计盈亏"]), 500.0)
        self.assertAlmostEqual(float(plot_df.iloc[1]["最高累计盈亏"]), 900.0)
        self.assertAlmostEqual(float(plot_df.iloc[1]["最低累计盈亏"]), 500.0)

    def test_profit_kline_figure_removes_price_subplot_and_range_slider(self) -> None:
        if importlib.util.find_spec("plotly") is None:
            self.skipTest("plotly is not installed")
        plot_df = pd.DataFrame(
            [
                {"日期": "2026-04-01", "开盘累计盈亏": 0.0, "最高累计盈亏": 900.0, "最低累计盈亏": 0.0, "收盘累计盈亏": 900.0, "当日盈亏": 900.0, "累计盈亏": 900.0, "记录数": 2, "平仓数量": 400.0, "平仓均价": 787.5, "结构盈亏": 700.0, "现货盈亏": 200.0, "结构摘要": "S1、S2"},
                {"日期": "2026-04-02", "开盘累计盈亏": 900.0, "最高累计盈亏": 900.0, "最低累计盈亏": 500.0, "收盘累计盈亏": 500.0, "当日盈亏": -400.0, "累计盈亏": 500.0, "记录数": 1, "平仓数量": 200.0, "平仓均价": 800.0, "结构盈亏": -400.0, "现货盈亏": 0.0, "结构摘要": "S3"},
            ]
        )

        fig = self.app.build_close_profit_kline_figure(plot_df)

        trace_names = [str(trace.name) for trace in fig.data]
        self.assertEqual(trace_names, ["盈亏K线", "日期选择点"])
        self.assertFalse(any("价格" in name or "收盘价" in name for name in trace_names))
        self.assertFalse(bool(fig.layout.xaxis.rangeslider.visible))
        self.assertGreaterEqual(int(fig.layout.hoverlabel.font.size), 16)
        candle = fig.data[0]
        self.assertEqual(candle.increasing.line.color, "#ff6f7f")
        self.assertEqual(candle.decreasing.line.color, "#48d597")
        self.assertIn("#ff6f7f", str(candle.customdata[0][1]))
        self.assertIn("#48d597", str(candle.customdata[1][1]))
        self.assertIn("现货盈亏", str(candle.customdata[0][4]))
        self.assertEqual(str(candle.customdata[1][4]), "")

    def test_profit_kline_axis_ticks_use_wan_unit(self) -> None:
        if importlib.util.find_spec("plotly") is None:
            self.skipTest("plotly is not installed")
        plot_df = pd.DataFrame(
            [
                {"日期": "2026-04-01", "开盘累计盈亏": 0.0, "最高累计盈亏": 8000000.0, "最低累计盈亏": 0.0, "收盘累计盈亏": 8000000.0, "当日盈亏": 8000000.0, "累计盈亏": 8000000.0, "记录数": 1, "平仓数量": 100.0, "平仓均价": 800.0, "结构盈亏": 8000000.0, "现货盈亏": 0.0, "结构摘要": "S1"},
            ]
        )

        fig = self.app.build_close_profit_kline_figure(plot_df)

        tick_text = [str(x) for x in fig.layout.yaxis.ticktext]
        self.assertIn("800W", tick_text)
        self.assertFalse(any("M" in x for x in tick_text))

    def test_selected_date_detail_filters_rows_and_metrics(self) -> None:
        close_detail = pd.DataFrame(
            [
                {"日期": "2026-04-01", "数量": 100.0, "平仓盈亏": 1200.0, "现货盈亏": 0.0, "合计盈亏": 1200.0},
                {"日期": "2026-04-02", "数量": 200.0, "平仓盈亏": -300.0, "现货盈亏": 50.0, "合计盈亏": -250.0},
                {"日期": "2026-04-02", "数量": 300.0, "平仓盈亏": 500.0, "现货盈亏": 20.0, "合计盈亏": 520.0},
            ]
        )

        detail, metrics = self.app.build_close_selected_date_detail(close_detail, "2026-04-02")

        self.assertEqual(int(len(detail)), 2)
        self.assertAlmostEqual(float(metrics["qty_sum"]), 500.0)
        self.assertAlmostEqual(float(metrics["struct_pnl_sum"]), 200.0)
        self.assertAlmostEqual(float(metrics["spot_pnl_sum"]), 70.0)
        self.assertAlmostEqual(float(metrics["total_pnl_sum"]), 270.0)
        self.assertAlmostEqual(float(metrics["cum_pnl_sum"]), 1470.0)
        self.assertEqual(int(metrics["record_count"]), 2)

    def test_summarize_close_directional_metrics_splits_long_short_and_other_qty(self) -> None:
        edited_close = pd.DataFrame(
            [
                {"方向": "卖平仓", "平仓数量": 1000.0, "平仓盈亏": 120000.0},
                {"方向": "买平仓", "平仓数量": 800.0, "平仓盈亏": -50000.0},
                {"方向": "平仓", "平仓数量": 200.0, "平仓盈亏": 10000.0},
            ]
        )

        metrics = self.app.summarize_close_directional_metrics(edited_close)

        self.assertAlmostEqual(float(metrics["long_close_qty"]), 1000.0)
        self.assertAlmostEqual(float(metrics["short_close_qty"]), 800.0)
        self.assertAlmostEqual(float(metrics["other_close_qty"]), 200.0)
        self.assertAlmostEqual(float(metrics["pnl_sum"]), 80000.0)

    def test_close_price_line_df_filters_underlying_and_dates(self) -> None:
        prices_df = pd.DataFrame(
            [
                {"dt": "2026-04-01", "underlying": "I.TEST", "settle": 780.0},
                {"dt": "2026-04-02", "underlying": "I.TEST", "settle": 790.0},
                {"dt": "2026-04-03", "underlying": "I.TEST", "settle": 800.0},
                {"dt": "2026-04-02", "underlying": "RB.TEST", "settle": 3500.0},
            ]
        )

        line_df = self.app.build_close_price_line_df(prices_df, "I.TEST", "2026-04-02", "2026-04-03")

        self.assertEqual(line_df["日期"].astype(str).tolist(), ["2026-04-02", "2026-04-03"])
        self.assertEqual(line_df["close"].astype(float).tolist(), [790.0, 800.0])

    def test_extract_ak_daily_ohlc_keeps_real_ohlc_columns(self) -> None:
        raw_df = pd.DataFrame(
            {
                "日期": ["2026-04-01", "2026-04-02"],
                "开盘价": [780.0, 790.0],
                "最高价": [800.0, 805.0],
                "最低价": [770.0, 785.0],
                "收盘价": [795.0, 800.0],
            }
        )

        ohlc = self.app._extract_ak_daily_ohlc_df(raw_df)

        self.assertEqual(list(ohlc.columns), ["dt", "open", "high", "low", "close"])
        self.assertEqual(len(ohlc), 2)
        self.assertAlmostEqual(float(ohlc.iloc[0]["open"]), 780.0)
        self.assertAlmostEqual(float(ohlc.iloc[0]["high"]), 800.0)
        self.assertAlmostEqual(float(ohlc.iloc[0]["low"]), 770.0)
        self.assertAlmostEqual(float(ohlc.iloc[0]["close"]), 795.0)

    def test_extract_plotly_selected_date_reads_customdata(self) -> None:
        selected = {"selection": {"points": [{"customdata": ["2026-04-02"]}]}}

        self.assertEqual(self.app._extract_plotly_selected_date(selected), "2026-04-02")

    def test_sync_close_selected_date_state_defaults_to_latest_record_date(self) -> None:
        state = {}
        key = "selected_close_date"

        self.app.sync_close_selected_date_state(
            state,
            selected_date_key=key,
            date_options=["2026-04-08", "2026-04-13", "2026-04-21"],
        )

        self.assertEqual(state[key], "2026-04-21")

        state[key] = "2026-04-13"
        self.app.sync_close_selected_date_state(
            state,
            selected_date_key=key,
            date_options=["2026-04-08", "2026-04-13", "2026-04-21"],
        )
        self.assertEqual(state[key], "2026-04-13")

        self.app.sync_close_selected_date_state(
            state,
            selected_date_key=key,
            date_options=["2026-04-08", "2026-04-13", "2026-04-21", "2026-04-22"],
        )

        self.assertEqual(state[key], "2026-04-22")

    def test_build_close_group_summary_aggregates_by_group_and_fills_empty_label(self) -> None:
        close_df = pd.DataFrame(
            [
                {"风险子": "海证资本", "方向": "卖平仓", "平仓数量": 1000.0, "平仓盈亏": 120000.0},
                {"风险子": "海证资本", "方向": "买平仓", "平仓数量": 800.0, "平仓盈亏": -50000.0},
                {"风险子": "", "方向": "平仓", "平仓数量": 200.0, "平仓盈亏": 10000.0},
            ]
        )

        summary = self.app.build_close_group_summary(close_df, "风险子")

        self.assertEqual(summary.iloc[0]["风险子"], "海证资本")
        self.assertEqual(int(summary.iloc[0]["记录数"]), 2)
        self.assertAlmostEqual(float(summary.iloc[0]["平仓总量(吨)"]), 1800.0)
        self.assertAlmostEqual(float(summary.iloc[0]["平多单(吨)"]), 1000.0)
        self.assertAlmostEqual(float(summary.iloc[0]["平空单(吨)"]), 800.0)
        self.assertAlmostEqual(float(summary.iloc[0]["其他记录量(吨)"]), 0.0)
        self.assertAlmostEqual(float(summary.iloc[0]["平仓盈亏合计"]), 70000.0)
        self.assertEqual(summary.iloc[1]["风险子"], "未填写")
        self.assertAlmostEqual(float(summary.iloc[1]["其他记录量(吨)"]), 200.0)


    def test_close_event_daily_excludes_subsidy_qty_but_keeps_pnl(self) -> None:
        close_detail = pd.DataFrame(
            [
                {
                    "日期": "2026-04-01",
                    "结构": "S_SUB",
                    "平仓类别": self.app.SUBSIDY_CLOSE_CATEGORY,
                    "方向": "卖平仓",
                    "数量": 22000.0,
                    "平仓价": 810.0,
                    "平仓盈亏": 500.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 500.0,
                },
                {
                    "日期": "2026-04-01",
                    "结构": "S_MANUAL",
                    "平仓类别": self.app.STRUCT_CLOSE_CATEGORY,
                    "方向": "卖平仓",
                    "数量": 1000.0,
                    "平仓价": 820.0,
                    "平仓盈亏": 300.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 300.0,
                },
            ]
        )

        daily = self.app.build_close_event_daily(close_detail)

        self.assertEqual(len(daily), 1)
        self.assertAlmostEqual(float(daily.iloc[0]["平仓数量"]), 1000.0)
        self.assertAlmostEqual(float(daily.iloc[0]["平仓均价"]), 820.0)
        self.assertAlmostEqual(float(daily.iloc[0]["合计盈亏"]), 800.0)

    def test_selected_date_detail_excludes_subsidy_qty_from_qty_split_metrics(self) -> None:
        close_detail = pd.DataFrame(
            [
                {
                    "日期": "2026-04-02",
                    "平仓类别": self.app.SUBSIDY_CLOSE_CATEGORY,
                    "方向": "卖平仓",
                    "数量": 22000.0,
                    "平仓盈亏": 400.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 400.0,
                },
                {
                    "日期": "2026-04-02",
                    "平仓类别": self.app.STRUCT_CLOSE_CATEGORY,
                    "方向": "卖平仓",
                    "数量": 800.0,
                    "平仓盈亏": 100.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 100.0,
                },
                {
                    "日期": "2026-04-02",
                    "平仓类别": self.app.SYMMETRIC_CLOSE_CATEGORY,
                    "方向": "买平仓",
                    "数量": 600.0,
                    "平仓盈亏": -50.0,
                    "现货盈亏": 30.0,
                    "合计盈亏": -20.0,
                },
            ]
        )

        detail, metrics = self.app.build_close_selected_date_detail(close_detail, "2026-04-02")

        self.assertEqual(int(len(detail)), 3)
        self.assertAlmostEqual(float(metrics["qty_sum"]), 1400.0)
        self.assertAlmostEqual(float(metrics["long_close_qty"]), 800.0)
        self.assertAlmostEqual(float(metrics["short_close_qty"]), 600.0)
        self.assertAlmostEqual(float(metrics["other_close_qty"]), 0.0)
        self.assertAlmostEqual(float(metrics["total_pnl_sum"]), 480.0)

    def test_summarize_close_metrics_excludes_subsidy_qty_and_batch_count(self) -> None:
        close_detail = pd.DataFrame(
            [
                {
                    "日期": "2026-04-02",
                    "平仓类别": self.app.SUBSIDY_CLOSE_CATEGORY,
                    "方向": "卖平仓",
                    "数量": 22000.0,
                    "头寸价格": 780.0,
                    "平仓价": 810.0,
                    "平仓盈亏": 400.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 400.0,
                    "平仓批次号": "__AUTO_SUBSIDY__",
                },
                {
                    "日期": "2026-04-02",
                    "平仓类别": self.app.STRUCT_CLOSE_CATEGORY,
                    "方向": "卖平仓",
                    "数量": 800.0,
                    "头寸价格": 780.0,
                    "平仓价": 820.0,
                    "平仓盈亏": 100.0,
                    "现货盈亏": 0.0,
                    "合计盈亏": 100.0,
                    "平仓批次号": "MANUAL_A",
                },
                {
                    "日期": "2026-04-02",
                    "平仓类别": self.app.SYMMETRIC_CLOSE_CATEGORY,
                    "方向": "买平仓",
                    "数量": 600.0,
                    "头寸价格": 800.0,
                    "平仓价": 790.0,
                    "平仓盈亏": -50.0,
                    "现货盈亏": 30.0,
                    "合计盈亏": -20.0,
                    "平仓批次号": "MANUAL_B",
                },
            ]
        )

        metrics = self.app.summarize_close_metrics(close_detail)

        self.assertAlmostEqual(float(metrics["qty_sum"]), 1400.0)
        self.assertAlmostEqual(float(metrics["long_close_qty"]), 800.0)
        self.assertAlmostEqual(float(metrics["short_close_qty"]), 600.0)
        self.assertAlmostEqual(float(metrics["batch_cnt"]), 2.0)
        self.assertAlmostEqual(float(metrics["total_pnl_sum"]), 480.0)


if __name__ == "__main__":
    unittest.main()
