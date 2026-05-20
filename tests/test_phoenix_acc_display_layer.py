import importlib.util
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd
from matplotlib.axes import Axes


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_display_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PhoenixAccDisplayLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_build_phoenix_detail_card_frame(self) -> None:
        resolved = {
            "strategy_code": "PHOENIX_ACC_CALL_FIXED",
            "kind": "ACC",
            "name": "凤凰累计",
            "entry_price": 100.0,
            "barrier_in": 95.0,
            "knock_out_price": 110.0,
            "knock_in_exercise_price": 96.0,
            "subsidy_per_ton": 5.0,
            "multiple": 2.0,
            "knock_in_qty_mode": "remaining",
            "knock_out_settlement_mode": "delivery",
            "knock_out_exercise_price": 108.0,
        }
        latest_daily = {
            "状态": "敲出熔断-给量",
            "事件类型": "knock_out_delivery_terminate",
            "给量方向": "BUY",
            "终止原因": "knock_out_delivery",
        }
        detail_df = self.app.build_phoenix_detail_card_frame(resolved, latest_daily)
        detail_map = dict(zip(detail_df["项目"], detail_df["内容"]))
        self.assertEqual(detail_map["结构名称"], "凤凰累购")
        self.assertEqual(detail_map["方向"], "看涨")
        self.assertEqual(detail_map["敲入给量模式"], "剩余数量")
        self.assertEqual(detail_map["敲出结算模式"], "头寸")
        self.assertEqual(detail_map["参与率"], "2倍")
        self.assertEqual(detail_map["敲出行权价"], "108.0")
        self.assertEqual(detail_map["当前状态"], "敲出熔断-给量")
        self.assertEqual(detail_map["当前事件类型"], "knock_out_delivery_terminate")
        self.assertEqual(detail_map["当前给量方向"], "BUY")
        self.assertEqual(detail_map["当前终止原因"], "knock_out_delivery")

    def test_build_phoenix_detail_card_frame_marks_finished_when_remaining_days_non_positive(self) -> None:
        resolved = {
            "strategy_code": "PHOENIX_ACC_CALL_FIXED",
            "kind": "ACC",
            "name": "凤凰累计",
            "entry_price": 100.0,
            "barrier_in": 95.0,
            "knock_out_price": 110.0,
            "knock_in_exercise_price": 96.0,
            "subsidy_per_ton": 5.0,
            "multiple": 2.0,
            "knock_in_qty_mode": "remaining",
            "knock_out_settlement_mode": "delivery",
            "knock_out_exercise_price": 108.0,
        }
        latest_daily = {
            "状态": "敲出熔断-给量",
            "剩余交易日": 0,
            "事件类型": "knock_out_delivery_terminate",
        }
        detail_df = self.app.build_phoenix_detail_card_frame(resolved, latest_daily)
        detail_map = dict(zip(detail_df["项目"], detail_df["内容"]))
        self.assertEqual(detail_map["当前状态"], "熔断结束")

    def test_build_structure_daily_export_view(self) -> None:
        display_df = pd.DataFrame(
            [
                {
                    "日期": "2026-03-17",
                    "结构ID": "S1",
                    "结构": "S1-凤凰累购-海证资本-入场价（100.00）-行权价（96.00）",
                    "结构名称": "凤凰累购",
                    "方向": "看涨",
                    "状态": "敲入熔断",
                    "收盘价": 94.0,
                    "观察日序号": 2,
                    "每日基准量": 10.0,
                    "事件类型": "knock_in_terminate",
                    "终止原因": "knock_in",
                    "当日生成量": 30.0,
                    "生成价": 96.0,
                    "当日补贴盈亏": 0.0,
                    "累计补贴盈亏": 50.0,
                    "给量方向": "BUY",
                }
            ]
        )
        export_df = self.app.build_structure_daily_export_view(display_df)
        row = export_df.iloc[0]
        self.assertEqual(row["structure_name"], "凤凰累购")
        self.assertEqual(row["direction"], "看涨")
        self.assertEqual(row["status"], "敲入熔断")
        self.assertEqual(row["event_type"], "knock_in_terminate")
        self.assertEqual(row["terminate_reason"], "knock_in")
        self.assertAlmostEqual(float(row["generated_qty"]), 30.0)
        self.assertAlmostEqual(float(row["gen_price"]), 96.0)
        self.assertAlmostEqual(float(row["day_subsidy_pnl"]), 0.0)
        self.assertAlmostEqual(float(row["cum_subsidy_pnl"]), 50.0)
        self.assertEqual(row["delivered_side"], "BUY")

    def test_build_structure_daily_export_view_marks_finished_when_remaining_days_non_positive(self) -> None:
        display_df = pd.DataFrame(
            [
                {
                    "日期": "2026-03-17",
                    "结构ID": "S1",
                    "结构名称": "凤凰累购",
                    "方向": "看涨",
                    "状态": "敲入熔断",
                    "剩余交易日": -1,
                }
            ]
        )
        export_df = self.app.build_structure_daily_export_view(display_df)
        row = export_df.iloc[0]
        self.assertEqual(row["状态"], "熔断结束")
        self.assertEqual(row["status"], "熔断结束")

    def test_status_to_cn_for_phoenix_normal_subsidy(self) -> None:
        self.assertEqual(self.app.status_to_cn("normal_subsidy", 0.0, 1.0), "震荡获得补贴")
        self.assertEqual(self.app.status_to_cn("震荡获得补贴", 0.0, 0.0), "震荡获得补贴")

    def test_cumulative_surviving_side_qty_summary_uses_open_position_qty(self) -> None:
        summary = self.app.report_cumulative_surviving_side_qty_breakdown(
            [
                {"kind": "ACC", "open_position_qty": 16000.0},
                {"kind": "DEC", "open_position_qty": 12000.0},
                {"kind": "ACC", "open_position_qty_signed": 3000.0},
                {"kind": "DEC", "open_position_qty_signed": -500.0},
                {"side_cn": "多单", "open_position_qty": 200.0},
                {"side_cn": "空单", "open_position_qty": 100.0},
            ]
        )
        self.assertAlmostEqual(float(summary["long_qty"]), 19200.0)
        self.assertAlmostEqual(float(summary["short_qty"]), 12600.0)
        self.assertEqual(
            self.app.report_cumulative_surviving_side_qty_summary_text(
                [
                    {"kind": "ACC", "open_position_qty": 16000.0},
                    {"kind": "DEC", "open_position_qty": 12000.0},
                ]
            ),
            "汇总：多单16,000吨\n　　　空单12,000吨",
        )
        summary_with_avg = self.app.report_cumulative_surviving_side_qty_breakdown(
            [
                {"kind": "ACC", "open_position_qty": 10000.0, "open_avg_price": 780.0},
                {"kind": "ACC", "open_position_qty": 6000.0, "open_avg_price": 800.0},
                {"kind": "DEC", "open_position_qty": 12000.0, "open_avg_price": 815.0},
            ],
            include_avg=True,
        )
        self.assertAlmostEqual(float(summary_with_avg["long_avg_price"]), 787.5)
        self.assertAlmostEqual(float(summary_with_avg["short_avg_price"]), 815.0)
        self.assertEqual(
            self.app.report_cumulative_surviving_side_qty_summary_text(
                [
                    {"kind": "ACC", "open_position_qty": 10000.0, "open_avg_price": 780.0},
                    {"kind": "ACC", "open_position_qty": 6000.0, "open_avg_price": 800.0},
                    {"kind": "DEC", "open_position_qty": 12000.0, "open_avg_price": 815.0},
                ]
            ),
            "汇总：多单16,000吨 均价787.50\n　　　空单12,000吨 均价815.00",
        )
        self.assertEqual(
            self.app.report_cumulative_surviving_side_qty_summary_text(
                [
                    {"kind": "ACC", "open_position_qty": 0.0, "open_avg_price": 780.0},
                    {"kind": "DEC", "open_position_qty": 12000.0, "open_avg_price": 815.0},
                ]
            ),
            "汇总：多单0吨\n　　　空单12,000吨 均价815.00",
        )

    def test_cumulative_price_summary_text_keeps_three_fields_on_one_line(self) -> None:
        self.assertEqual(
            self.app.report_cumulative_surviving_price_summary_text(
                {
                    "barrier_avg_price": 770.32,
                    "entry_avg_price": 772.71,
                    "strike_avg_price": 802.71,
                }
            ),
            "障碍均价770.3 入场均价772.7 行权均价802.7",
        )
        self.assertEqual(
            self.app.report_cumulative_surviving_price_summary_text(
                {
                    "barrier_avg_price": None,
                    "entry_avg_price": 772.0,
                    "strike_avg_price": 802.0,
                }
            ),
            "障碍均价-- 入场均价772.0 行权均价802.0",
        )

    def test_render_report_image_keeps_cumulative_price_summary_readable(self) -> None:
        captured_text_calls: list[tuple[str, float | None, str | None, float | None]] = []
        original_text = Axes.text

        def spy_text(ax, x, y, s, *args, **kwargs):
            captured_text_calls.append((str(s), kwargs.get("fontsize"), kwargs.get("color"), y))
            return original_text(ax, x, y, s, *args, **kwargs)

        summary = {
            "group_id": "G003",
            "group_name": "G003 - summary font",
            "underlying": "I2609",
            "date": "2026-04-16",
            "gen_total_qty": 0.0,
            "net_gen_qty": 0.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 0.0,
            "remaining_max_signed": -56000.0,
            "gen_avg_price": None,
            "today_long_avg": None,
            "today_short_avg": None,
            "day_close_price": 780.0,
            "day_close_price_map": {"I2609": 780.0},
            "lock_qty": 0.0,
            "lock_pnl": 0.0,
            "has_snowball": False,
            "has_vanilla": False,
            "has_airbag": False,
            "cumulative_rows": [
                {
                    "structure_id": "S010",
                    "structure": "S010-普通累购-海证资本",
                    "status_cn": "震荡",
                    "remaining_max_qty": 6000.0,
                    "remaining_max_qty_signed": 6000.0,
                    "remaining_min_qty": 3000.0,
                    "remaining_min_qty_signed": 3000.0,
                    "remaining_trading_days": 1,
                    "total_trading_days": 20,
                    "end_date": "2026-04-17",
                    "today_generated_qty": 3000.0,
                    "today_generated_qty_signed": 3000.0,
                    "open_position_qty": 35000.0,
                    "open_position_qty_signed": 35000.0,
                    "open_avg_price": 802.71,
                    "entry_price": 772.71,
                    "strike_price": 802.71,
                    "barrier_price": 770.32,
                    "daily_scale_qty": 3000.0,
                    "daily_scale_qty_signed": 3000.0,
                    "kind": "ACC",
                    "side_cn": "多单",
                }
            ],
            "snowball_rows": [],
            "vanilla_rows": [],
            "airbag_rows": [],
            "report_layout": {},
            "_test_id": "cumulative-summary-font",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "report.png"
            with mock.patch.object(Axes, "text", new=spy_text):
                png_bytes = self.app.render_report_image(summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        summary_fonts = [
            float(font)
            for text, font, _color, _y in captured_text_calls
            if text in {"障碍均价", "入场均价", "行权均价", "770.3", "772.7", "802.7"} and font is not None
        ]
        self.assertTrue(summary_fonts)
        self.assertGreaterEqual(min(summary_fonts), 13.0)
        qty_summary_fonts = [
            float(font)
            for text, font, _color, _y in captured_text_calls
            if text in {"汇总：", "多单", "空单", "35,000吨", "0吨"} and font is not None
        ]
        self.assertTrue(qty_summary_fonts)
        self.assertGreaterEqual(min(qty_summary_fonts), 13.0)
        label_colors = {
            text: str(color)
            for text, _font, color, _y in captured_text_calls
            if text in {"障碍均价", "入场均价", "行权均价"} and color is not None
        }
        self.assertEqual(set(label_colors), {"障碍均价", "入场均价", "行权均价"})
        self.assertEqual(len(set(label_colors.values())), 3)
        pct_fonts = [
            float(font)
            for text, font, _color, _y in captured_text_calls
            if text == "5.0%" and font is not None
        ]
        self.assertTrue(pct_fonts)
        self.assertGreaterEqual(max(pct_fonts), 15.0)
        price_line_y = [
            float(y)
            for text, _font, _color, y in captured_text_calls
            if text == "770.3" and y is not None
        ]
        first_qty_line_y = [
            float(y)
            for text, _font, _color, y in captured_text_calls
            if "35,000" in text and y is not None
        ]
        self.assertTrue(price_line_y)
        self.assertTrue(first_qty_line_y)
        self.assertGreater(price_line_y[0] - first_qty_line_y[0], 0.012)

    def test_cumulative_monitor_title_marks_terminated_positions(self) -> None:
        self.assertEqual(
            self.app.CUMULATIVE_MONITOR_TITLE,
            "累计结构监控（含已终止但仍有头寸）",
        )

    def test_report_monitor_filter_structure_bounds_keeps_terminated_with_position(self) -> None:
        bounds_df = pd.DataFrame(
            [
                {"structure_id": "ACC_ACTIVE", "remaining_max_qty": 1000.0},
                {"structure_id": "ACC_TERM_WITH_POS", "remaining_max_qty": 0.0},
                {"structure_id": "ACC_TERM_NO_POS", "remaining_max_qty": 0.0},
            ]
        )
        filtered = self.app.report_monitor_filter_structure_bounds_for_display(
            bounds_df,
            inactive_sid_block={"ACC_TERM_WITH_POS", "ACC_TERM_NO_POS"},
            terminated_with_position_sid_set={"ACC_TERM_WITH_POS"},
        )
        self.assertEqual(
            filtered["structure_id"].astype(str).tolist(),
            ["ACC_ACTIVE", "ACC_TERM_WITH_POS"],
        )

    def test_vanilla_exercise_distance_uses_option_direction(self) -> None:
        self.assertAlmostEqual(float(self.app.vanilla_exercise_distance("call", 800.0, 780.0)), 20.0)
        self.assertAlmostEqual(float(self.app.vanilla_exercise_distance("call", 800.0, 820.0)), -20.0)
        self.assertAlmostEqual(float(self.app.vanilla_exercise_distance("put", 800.0, 780.0)), -20.0)
        self.assertAlmostEqual(float(self.app.vanilla_exercise_distance("put", 800.0, 820.0)), 20.0)
        self.assertIsNone(self.app.vanilla_exercise_distance("call", None, 780.0))

    def test_render_report_image_hides_empty_structure_blocks(self) -> None:
        captured_texts: list[str] = []
        original_text = Axes.text

        def spy_text(ax, x, y, s, *args, **kwargs):
            captured_texts.append(str(s))
            return original_text(ax, x, y, s, *args, **kwargs)

        summary = {
            "group_id": "G003",
            "group_name": "G003 - 卖出香早组",
            "underlying": "全部品种",
            "date": "2026-04-16",
            "gen_total_qty": 0.0,
            "net_gen_qty": 0.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 0.0,
            "remaining_max_signed": -60000.0,
            "gen_avg_price": None,
            "today_long_avg": None,
            "today_short_avg": None,
            "day_close_price": None,
            "day_close_price_map": {"I2609": 782.5},
            "lock_qty": 0.0,
            "lock_pnl": 0.0,
            "has_snowball": False,
            "has_vanilla": True,
            "has_airbag": False,
            "cumulative_rows": [],
            "snowball_rows": [],
            "vanilla_rows": [
                {
                    "structure_id": "S001",
                    "structure": "S001-卖出看涨-东海资本",
                    "status_cn": "未行权",
                    "premium": 9.2,
                    "remaining_trading_days": 18,
                    "end_date": "2026-05-15",
                    "open_position_qty": 10000.0,
                    "kind": "DEC",
                    "buy_sell_side": "sell",
                    "is_vanilla": True,
                }
            ],
            "airbag_rows": [],
            "report_layout": {},
            "_test_id": "hide-empty-structure-blocks",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "report.png"
            with mock.patch.object(Axes, "text", new=spy_text):
                png_bytes = self.app.render_report_image(summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        self.assertIn("香草期权监控", captured_texts)
        self.assertNotIn(self.app.CUMULATIVE_MONITOR_TITLE, captured_texts)
        self.assertNotIn("雪球结构监控", captured_texts)
        self.assertNotIn("气囊结构监控（含已终止但仍有头寸）", captured_texts)
        self.assertNotIn("暂无结构数据", captured_texts)

    def test_render_report_image_vanilla_status_shows_exercise_distance(self) -> None:
        captured_texts: list[str] = []
        captured_cells: list[str] = []
        captured_headers: list[str] = []
        original_text = Axes.text
        original_table = Axes.table

        def spy_text(ax, x, y, s, *args, **kwargs):
            captured_texts.append(str(s))
            return original_text(ax, x, y, s, *args, **kwargs)

        def spy_table(ax, *args, **kwargs):
            for header in kwargs.get("colLabels", []) or []:
                captured_headers.append(str(header))
            for row in kwargs.get("cellText", []) or []:
                if isinstance(row, (list, tuple)):
                    captured_cells.extend(str(cell) for cell in row)
            return original_table(ax, *args, **kwargs)

        summary = {
            "group_id": "G003",
            "group_name": "G003 - vanilla distance",
            "underlying": "I2609",
            "date": "2026-04-16",
            "gen_total_qty": 0.0,
            "net_gen_qty": 0.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 0.0,
            "remaining_max_signed": 0.0,
            "gen_avg_price": None,
            "today_long_avg": None,
            "today_short_avg": None,
            "day_close_price": 780.0,
            "day_close_price_map": {"I2609": 780.0},
            "lock_qty": 0.0,
            "lock_pnl": 0.0,
            "has_snowball": False,
            "has_vanilla": True,
            "has_airbag": False,
            "cumulative_rows": [],
            "snowball_rows": [],
            "vanilla_rows": [
                {
                    "structure_id": "S002",
                    "structure": "S002-卖出看涨",
                    "status_cn": "未行权",
                    "premium": 3.8,
                    "remaining_trading_days": 14,
                    "total_trading_days": 20,
                    "end_date": "2026-05-11",
                    "open_position_qty": 50000.0,
                    "kind": "DEC",
                    "buy_sell_side": "sell",
                    "option_type": "call",
                    "strike_price": 800.0,
                    "settle_price": 780.0,
                    "is_vanilla": True,
                }
            ],
            "airbag_rows": [],
            "report_layout": {},
            "_test_id": "vanilla-exercise-distance",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "report.png"
            with mock.patch.object(Axes, "text", new=spy_text), mock.patch.object(Axes, "table", new=spy_table):
                png_bytes = self.app.render_report_image(summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        self.assertIn("未行权", captured_texts)
        self.assertIn("距离行权：20.0", captured_texts)
        self.assertIn("剩余交易日", captured_headers)
        self.assertIn("\u8f6c\u5934\u5bf8\u4ef7\u683c", captured_headers)
        self.assertIn("14/20\n2026-05-11", captured_cells)
        self.assertIn("803.80", captured_cells)

    def test_render_report_image_cumulative_and_airbag_remaining_days_show_ratio_without_shrinking(self) -> None:
        captured_cells: list[str] = []
        captured_headers: list[str] = []
        captured_text_calls: list[tuple[str, float | None]] = []
        captured_title_y: list[float] = []
        captured_tables: list[tuple[list[str], list[float], list[float]]] = []
        original_text = Axes.text
        original_table = Axes.table

        def spy_text(ax, x, y, s, *args, **kwargs):
            text = str(s)
            captured_text_calls.append((text, kwargs.get("fontsize")))
            if text == self.app.CUMULATIVE_MONITOR_TITLE:
                captured_title_y.append(float(y))
            return original_text(ax, x, y, s, *args, **kwargs)

        def spy_table(ax, *args, **kwargs):
            headers = [str(header) for header in (kwargs.get("colLabels", []) or [])]
            widths = [float(x) for x in (kwargs.get("colWidths", []) or [])]
            bbox = [float(x) for x in (kwargs.get("bbox", []) or [])]
            captured_tables.append((headers, widths, bbox))
            for header in headers:
                captured_headers.append(header)
            for row in kwargs.get("cellText", []) or []:
                if isinstance(row, (list, tuple)):
                    captured_cells.extend(str(cell) for cell in row)
            return original_table(ax, *args, **kwargs)

        summary = {
            "group_id": "G003",
            "group_name": "G003 - ratio display",
            "underlying": "I2609",
            "date": "2026-04-16",
            "gen_total_qty": 0.0,
            "net_gen_qty": 0.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 0.0,
            "remaining_max_signed": -56000.0,
            "gen_avg_price": None,
            "today_long_avg": None,
            "today_short_avg": None,
            "day_close_price": 780.0,
            "day_close_price_map": {"I2609": 780.0},
            "lock_qty": 0.0,
            "lock_pnl": 0.0,
            "has_snowball": False,
            "has_vanilla": False,
            "has_airbag": True,
            "cumulative_rows": [
                {
                    "structure_id": "S010",
                    "structure": "S010-普通累购-海证资本",
                    "status_cn": "震荡",
                    "remaining_max_qty": 6000.0,
                    "remaining_max_qty_signed": 6000.0,
                    "remaining_min_qty": 3000.0,
                    "remaining_min_qty_signed": 3000.0,
                    "remaining_trading_days": 1,
                    "total_trading_days": 20,
                    "end_date": "2026-04-17",
                    "today_generated_qty": 3000.0,
                    "today_generated_qty_signed": 3000.0,
                    "open_position_qty": 35000.0,
                    "open_position_qty_signed": 35000.0,
                    "daily_scale_qty": 3000.0,
                    "daily_scale_qty_signed": 3000.0,
                    "kind": "ACC",
                    "side_cn": "多单",
                }
            ],
            "snowball_rows": [],
            "vanilla_rows": [],
            "airbag_rows": [
                {
                    "structure_id": "S021",
                    "structure": "S021-看跌安全气囊-瑞达新控",
                    "status_cn": "未敲入观察",
                    "remaining_trading_days": 7,
                    "total_trading_days": 30,
                    "end_date": "2026-04-27",
                    "display_slot_qty": -50000.0,
                    "kind": "DEC",
                    "multiplier": 0.2,
                    "airbag_ki_distance_abs": 23.0,
                    "airbag_ki_distance_pct": 2.94,
                    "is_airbag": True,
                }
            ],
            "report_layout": {},
            "_test_id": "cumulative-airbag-days-ratio",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "report.png"
            with mock.patch.object(Axes, "text", new=spy_text), mock.patch.object(Axes, "table", new=spy_table):
                png_bytes = self.app.render_report_image(summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        self.assertIn("剩余交易日", captured_headers)
        self.assertIn("1/20\n04-17", captured_cells)
        self.assertIn("7/30\n04-27", captured_cells)
        self.assertTrue(any("1.0/20.0" in cell for cell in captured_cells))
        self.assertTrue(any("7.0/30.0" in cell for cell in captured_cells))
        cumulative_headers, cumulative_widths, cumulative_bbox = next(
            (headers, widths, bbox)
            for headers, widths, bbox in captured_tables
            if "震荡最小" in headers
        )
        self.assertIn("结构详情", cumulative_headers)
        self.assertLessEqual(cumulative_widths[0], 0.40)
        self.assertGreaterEqual(sum(cumulative_widths[1:]), 0.60)
        self.assertTrue(captured_title_y)
        self.assertGreater(captured_title_y[0] - (cumulative_bbox[1] + cumulative_bbox[3]), 0.012)
        cumulative_right = cumulative_bbox[0] + cumulative_bbox[2]
        self.assertGreaterEqual(cumulative_right, 0.925)
        self.assertLessEqual(cumulative_right, 0.952)
        self.assertGreaterEqual(1.0 - cumulative_right, 0.045)
        cum_days_fonts = [font for text, font in captured_text_calls if text in {"1", "/20"}]
        airbag_days_fonts = [font for text, font in captured_text_calls if text in {"7", "/30"}]
        self.assertTrue(any(font is not None and float(font) >= 15.0 for font in cum_days_fonts))
        self.assertTrue(any(font is not None and float(font) >= 15.0 for font in airbag_days_fonts))

    def test_render_report_image_dense_cumulative_table_stays_inside_monitor_box(self) -> None:
        captured_tables: list[tuple[list[str], list[float], list[float]]] = []
        captured_table_objects = []
        captured_cells: list[str] = []
        captured_axes_state: list[tuple[tuple[float, float], tuple[float, float], bool, float]] = []
        original_table = Axes.table

        def spy_table(ax, *args, **kwargs):
            headers = [str(header) for header in (kwargs.get("colLabels", []) or [])]
            widths = [float(x) for x in (kwargs.get("colWidths", []) or [])]
            bbox = [float(x) for x in (kwargs.get("bbox", []) or [])]
            captured_tables.append((headers, widths, bbox))
            captured_axes_state.append(
                (
                    tuple(float(v) for v in ax.get_xlim()),
                    tuple(float(v) for v in ax.get_ylim()),
                    bool(ax.get_autoscale_on()),
                    float(ax.figure.get_size_inches()[0]),
                )
            )
            for row in kwargs.get("cellText", []) or []:
                if isinstance(row, (list, tuple)):
                    captured_cells.extend(str(cell) for cell in row)
            tbl = original_table(ax, *args, **kwargs)
            captured_table_objects.append((headers, tbl))
            return tbl

        rows = []
        for idx in range(12):
            rows.append(
                {
                    "structure_id": f"S{idx:03d}",
                    "structure": f"S{idx:03d}-普通累购-测试机构",
                    "status_cn": "震荡",
                    "remaining_max_qty": 42000.0 + idx * 1000.0,
                    "remaining_max_qty_signed": -(42000.0 + idx * 1000.0),
                    "remaining_min_qty": 14000.0,
                    "remaining_min_qty_signed": -14000.0,
                    "remaining_trading_days": 14 + idx,
                    "total_trading_days": 25,
                    "end_date": "2026-05-22",
                    "today_generated_qty": 1000.0,
                    "today_generated_qty_signed": -1000.0,
                    "open_position_qty": 1000.0,
                    "open_position_qty_signed": -1000.0,
                    "daily_scale_qty": 1000.0,
                    "daily_scale_qty_signed": -1000.0,
                    "kind": "DEC",
                    "side_cn": "空单",
                }
            )

        summary = {
            "group_id": "G004",
            "group_name": "G004 - dense cumulative",
            "underlying": "I2609",
            "date": "2026-04-29",
            "gen_total_qty": -13200.0,
            "net_gen_qty": -13200.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 13200.0,
            "remaining_max_signed": -744800.0,
            "gen_avg_price": None,
            "today_long_avg": None,
            "today_short_avg": 799.47,
            "day_close_price": 787.5,
            "day_close_price_map": {"I2609": 787.5},
            "lock_qty": 0.0,
            "lock_pnl": 0.0,
            "has_snowball": False,
            "has_vanilla": False,
            "has_airbag": False,
            "cumulative_rows": rows,
            "snowball_rows": [],
            "vanilla_rows": [],
            "airbag_rows": [],
            "report_layout": {},
            "_test_id": "dense-cumulative-table-fit",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "report.png"
            with mock.patch.object(Axes, "table", new=spy_table):
                png_bytes = self.app.render_report_image(summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        cumulative_headers, cumulative_widths, cumulative_bbox = next(
            (headers, widths, bbox)
            for headers, widths, bbox in captured_tables
            if "震荡最小" in headers
        )
        self.assertIn("当日生成", cumulative_headers)
        self.assertIn("存续吨数", cumulative_headers)
        self.assertLessEqual(cumulative_widths[0], 0.40)
        self.assertGreaterEqual(sum(cumulative_widths[1:]), 0.60)
        cumulative_right = cumulative_bbox[0] + cumulative_bbox[2]
        self.assertGreaterEqual(cumulative_right, 0.925)
        self.assertLessEqual(cumulative_right, 0.952)
        self.assertGreaterEqual(1.0 - cumulative_right, 0.045)
        self.assertTrue(captured_axes_state)
        xlim, ylim, autoscale_on, fig_width = captured_axes_state[0]
        self.assertEqual(xlim, (0.0, 1.0))
        self.assertEqual(ylim, (0.0, 1.0))
        self.assertFalse(autoscale_on)
        self.assertGreaterEqual(fig_width, 18.8)
        cumulative_tbl = next(tbl for headers, tbl in captured_table_objects if "震荡最小" in headers)
        summary_row_idx = len(rows) + 1
        rem_summary_fs = float(cumulative_tbl[(summary_row_idx, 2)].get_text().get_fontsize())
        today_summary_fs = float(cumulative_tbl[(summary_row_idx, 5)].get_text().get_fontsize())
        surviving_summary_fs = float(cumulative_tbl[(summary_row_idx, 6)].get_text().get_fontsize())
        self.assertAlmostEqual(today_summary_fs, rem_summary_fs, places=3)
        self.assertAlmostEqual(surviving_summary_fs, rem_summary_fs, places=3)
        self.assertTrue(any("-1,000" in cell for cell in captured_cells))

    def test_render_report_image_net_risk_uses_visible_rows_instead_of_stale_summary_value(self) -> None:
        captured_texts: list[str] = []
        original_text = Axes.text

        def spy_text(ax, x, y, s, *args, **kwargs):
            captured_texts.append(str(s))
            return original_text(ax, x, y, s, *args, **kwargs)

        summary = {
            "group_id": "G002",
            "group_name": "G002 - visible remaining",
            "underlying": "I2605",
            "date": "2026-04-23",
            "gen_total_qty": 0.0,
            "net_gen_qty": 0.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 0.0,
            "remaining_max_signed": 426212.0,
            "gen_avg_price": None,
            "today_long_avg": None,
            "today_short_avg": None,
            "day_close_price": 807.0,
            "day_close_price_map": {"I2605": 807.0},
            "lock_qty": 0.0,
            "lock_pnl": 0.0,
            "has_snowball": False,
            "has_vanilla": False,
            "has_airbag": True,
            "cumulative_rows": [],
            "snowball_rows": [],
            "vanilla_rows": [],
            "airbag_rows": [
                {
                    "structure_id": "S021",
                    "structure": "S021-airbag-a",
                    "status_cn": "未敲入观察",
                    "remaining_trading_days": 2,
                    "total_trading_days": 11,
                    "end_date": "2026-04-27",
                    "display_slot_qty": -50000.0,
                    "kind": "DEC",
                    "multiplier": 0.2,
                    "airbag_ki_distance_abs": 24.5,
                    "airbag_ki_distance_pct": 3.13,
                    "is_airbag": True,
                },
                {
                    "structure_id": "S019",
                    "structure": "S019-airbag-b",
                    "status_cn": "未敲入观察",
                    "remaining_trading_days": 3,
                    "total_trading_days": 13,
                    "end_date": "2026-04-28",
                    "display_slot_qty": -28000.0,
                    "kind": "DEC",
                    "multiplier": 0.35,
                    "airbag_ki_distance_abs": 13.0,
                    "airbag_ki_distance_pct": 1.68,
                    "is_airbag": True,
                },
                {
                    "structure_id": "S018",
                    "structure": "S018-airbag-c",
                    "status_cn": "未敲入观察",
                    "remaining_trading_days": 1,
                    "total_trading_days": 11,
                    "end_date": "2026-04-24",
                    "display_slot_qty": -65000.0,
                    "kind": "DEC",
                    "multiplier": 0.3,
                    "airbag_ki_distance_abs": 17.0,
                    "airbag_ki_distance_pct": 2.20,
                    "is_airbag": True,
                },
                {
                    "structure_id": "S020",
                    "structure": "S020-airbag-d",
                    "status_cn": "未敲入观察",
                    "remaining_trading_days": 3,
                    "total_trading_days": 13,
                    "end_date": "2026-04-28",
                    "display_slot_qty": -40000.0,
                    "kind": "DEC",
                    "multiplier": 0.35,
                    "airbag_ki_distance_abs": 13.0,
                    "airbag_ki_distance_pct": 1.68,
                    "is_airbag": True,
                },
            ],
            "report_layout": {},
            "_test_id": "visible-rows-net-risk",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "report.png"
            with mock.patch.object(Axes, "text", new=spy_text):
                png_bytes = self.app.render_report_image(summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        self.assertIn("-183,000 吨", captured_texts)
        self.assertIn("方向 = 空单", captured_texts)
        self.assertNotIn("426,212 吨", captured_texts)

    def test_merge_phoenix_editor_payload_preserves_specific_params_and_editor_columns(self) -> None:
        params_json, meta_json = self.app.merge_phoenix_acc_editor_payload(
            {
                "legacy_ext": "keep",
                "knock_in_qty_mode": "all",
                "knock_out_settlement_mode": "subsidy",
            },
            {"legacy_meta": "keep"},
            phoenix_terms={
                "entry_price": 100.0,
                "knock_in_price": 95.0,
                "knock_in_exercise_price": 96.0,
                "subsidy_per_ton": 5.0,
                "knock_out_price": 110.0,
                "participation_rate": 2.0,
                "knock_in_qty_mode": "remaining",
                "knock_out_settlement_mode": "delivery",
                "knock_out_exercise_price": 108.0,
            },
        )

        self.assertEqual(params_json["legacy_ext"], "keep")
        self.assertEqual(params_json["knock_in_qty_mode"], "remaining")
        self.assertEqual(params_json["knock_out_settlement_mode"], "delivery")
        self.assertEqual(float(params_json["knock_out_exercise_price"]), 108.0)
        self.assertEqual(meta_json["legacy_meta"], "keep")
        self.assertTrue(meta_json["ko_terminate"])

        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "P001",
                    "name": "凤凰累计",
                    "underlying": "I2605",
                    "risk_party": "海证资本",
                    "kind": "ACC",
                    "strategy": "PHOENIX_ACC_CALL_FIXED",
                    "strategy_code": "PHOENIX_ACC_CALL_FIXED",
                    "contract_month": "",
                    "trade_date": None,
                    "start_date": "2026-03-30",
                    "end_date": "2026-04-27",
                    "expiry_date": None,
                    "base_qty_per_day": 10.0,
                    "entry_price": 100.0,
                    "barrier_in": 95.0,
                    "strike_price": 96.0,
                    "premium": None,
                    "barrier_out": 110.0,
                    "knock_out_price": 110.0,
                    "ko_strike_price": 108.0,
                    "multiple": 2.0,
                    "note": "",
                    "params_json": json.dumps(params_json, ensure_ascii=False),
                    "meta_json": json.dumps(meta_json, ensure_ascii=False),
                }
            ]
        )

        show = self.app.build_structure_table_view(structs_df)
        self.assertEqual(show.loc[0, "敲入给量口径"], "剩余数量")
        self.assertEqual(show.loc[0, "敲出结算方式"], "头寸")
        self.assertEqual(float(show.loc[0, "行权价"]), 96.0)
        self.assertEqual(float(show.loc[0, "熔断行权价"]), 108.0)


if __name__ == "__main__":
    unittest.main()
