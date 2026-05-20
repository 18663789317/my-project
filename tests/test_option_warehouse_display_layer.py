import importlib.util
import pathlib
import sys
import unittest
from unittest import mock

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_option_warehouse_display_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OptionWarehouseDisplayLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_scope_text_summarizes_selected_underlyings(self) -> None:
        self.assertEqual(self.app.build_option_warehouse_scope_text([]), "全部品种")
        self.assertEqual(
            self.app.build_option_warehouse_scope_text(["I2609", "I2610"]),
            "已筛品种：I2609、I2610",
        )
        self.assertEqual(
            self.app.build_option_warehouse_scope_text(["I2609", "I2610", "I2611", "I2612"]),
            "已筛 4 个品种：I2609、I2610、I2611 等",
        )

    def test_quick_filter_button_text_reflects_selection_count(self) -> None:
        self.assertEqual(self.app.build_option_warehouse_quick_filter_button_text([]), "品种筛选")
        self.assertEqual(
            self.app.build_option_warehouse_quick_filter_button_text(["I2609", "I2610"]),
            "品种筛选（2）",
        )

    def test_avg_price_filter_options_are_display_precision_unique_and_sorted(self) -> None:
        rows = pd.DataFrame(
            {
                "结构ID": ["S001", "S002", "S003", "S004"],
                "在库均价": [816.0, 804.0, 805.364, 805.361],
            }
        )

        self.assertEqual(
            self.app.build_option_warehouse_avg_price_filter_options(rows),
            ["804.00", "805.36", "816.00"],
        )

    def test_apply_avg_price_filter_matches_selected_display_prices(self) -> None:
        rows = pd.DataFrame(
            {
                "结构ID": ["S009", "S010", "S011", "S012"],
                "在库均价": [804.0, 805.36, 815.0, 816.0],
            }
        )

        filtered = self.app.apply_option_warehouse_avg_price_filter(rows, ["804.00", "816.00"])

        self.assertEqual(filtered["结构ID"].tolist(), ["S009", "S012"])

    def test_overview_cards_cover_dual_side_inventory_metrics(self) -> None:
        cards = self.app.build_option_warehouse_overview_cards(
            total_qty=78000.0,
            total_avg=785.0,
            long_qty=41000.0,
            short_qty=37000.0,
            long_avg=738.29,
            short_avg=838.43,
        )

        self.assertEqual(len(cards), 9)
        self.assertEqual(cards[0]["label"], "多头在库数量（吨）")
        self.assertEqual(cards[0]["tone"], "long")
        self.assertEqual(cards[1]["label"], "多单平均价格")
        self.assertEqual(cards[1]["tone"], "long")
        self.assertEqual(cards[2]["label"], "空头在库数量（吨）")
        self.assertEqual(cards[2]["tone"], "short")
        self.assertEqual(cards[3]["label"], "空单平均价格")
        self.assertEqual(cards[3]["tone"], "short")
        self.assertEqual(cards[4]["label"], "净头寸（多-空）")
        self.assertEqual(cards[4]["value_text"], "4,000.00")
        self.assertEqual(cards[4]["tone"], "long")
        self.assertEqual(cards[7]["label"], "对冲价差收益")
        self.assertEqual(cards[7]["value_text"], "3,705,180.00")
        self.assertEqual(cards[7]["tone"], "positive")
        self.assertEqual(cards[8]["label"], "头寸保证金占用")
        self.assertEqual(cards[8]["value_text"], "3,329,687.90")
        self.assertIn("按多头侧", cards[8]["note"])

    def test_overview_cards_fall_back_to_total_metrics_for_single_side_inventory(self) -> None:
        cards = self.app.build_option_warehouse_overview_cards(
            total_qty=16000.0,
            total_avg=720.0,
            long_qty=16000.0,
            short_qty=0.0,
            long_avg=720.0,
            short_avg=0.0,
        )

        self.assertEqual(len(cards), 3)
        self.assertEqual(cards[0]["label"], "在库头寸总数量（吨）")
        self.assertEqual(cards[0]["value_text"], "16,000.00")
        self.assertEqual(cards[1]["label"], "在库头寸平均价格")
        self.assertEqual(cards[1]["value_text"], "720.00")
        self.assertEqual(cards[2]["label"], "头寸保证金占用")
        self.assertEqual(cards[2]["value_text"], "1,267,200.00")

    def test_overview_margin_usage_uses_larger_side_avg_price(self) -> None:
        cards = self.app.build_option_warehouse_overview_cards(
            total_qty=180000.0,
            total_avg=815.0,
            long_qty=80000.0,
            short_qty=100000.0,
            long_avg=760.0,
            short_avg=840.0,
            margin_rate_pct=12.0,
        )

        margin_card = cards[-1]
        self.assertEqual(margin_card["label"], "头寸保证金占用")
        self.assertEqual(margin_card["value_text"], "10,080,000.00")
        self.assertIn("按空头侧", margin_card["note"])
        self.assertIn("840.00", margin_card["note"])

    def test_structure_verbose_label_uses_melt_label_for_melt_strategies_only(self) -> None:
        fixed_label = self.app.structure_verbose_label(
            "S006",
            "固赔熔断累沽",
            "国泰君安",
            kind="DEC",
            entry_price=760.0,
            strike_price=790.0,
            strategy_value="FIXED_SUBSIDY",
            barrier_price=752.0,
        )
        float_label = self.app.structure_verbose_label(
            "S014",
            "浮动熔断累沽",
            "国联汇富",
            kind="DEC",
            entry_price=785.0,
            strike_price=800.0,
            strategy_value="FLOAT_KO",
            barrier_price=770.0,
        )
        normal_label = self.app.structure_verbose_label(
            "S009",
            "普通累沽",
            "光大光子",
            kind="DEC",
            entry_price=774.0,
            strike_price=804.0,
            strategy_value="BASIC_RANGE",
            barrier_price=769.0,
        )

        self.assertIn("\u7194\u65ad\u4ef7\uff08752.0\uff09", fixed_label)
        self.assertIn("\u7194\u65ad\u4ef7\uff08770.0\uff09", float_label)
        self.assertIn("\u969c\u788d\u4ef7\uff08769.0\uff09", normal_label)
        self.assertNotIn("\u969c\u788d\u4ef7", fixed_label)
        self.assertNotIn("\u969c\u788d\u4ef7", float_label)

    def test_normalize_warehouse_edit_state_syncs_qty_after_available_qty_changes(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "结构ID": "S006",
                    "kind": "ACC",
                    "平仓方向": "买平仓",
                    "可平数量": 44700.0,
                    "在库均价": 797.0,
                }
            ]
        )
        state = self.app.normalize_option_warehouse_edit_state(
            rows,
            {
                "S006": {
                    "平仓方向": "买平仓",
                    "平仓数量": 45400.0,
                    "平仓价格": 797.0,
                    "可平数量": 45400.0,
                    "在库均价": 797.0,
                }
            },
        )

        self.assertEqual(state["S006"]["平仓数量"], 44700.0)
        self.assertEqual(state["S006"]["可平数量"], 44700.0)

    def test_normalize_warehouse_edit_state_keeps_custom_qty_when_available_qty_unchanged(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "结构ID": "S006",
                    "kind": "ACC",
                    "平仓方向": "买平仓",
                    "可平数量": 44700.0,
                    "在库均价": 797.0,
                }
            ]
        )
        state = self.app.normalize_option_warehouse_edit_state(
            rows,
            {
                "S006": {
                    "平仓方向": "买平仓",
                    "平仓数量": 10000.0,
                    "平仓价格": 797.0,
                    "可平数量": 44700.0,
                    "在库均价": 797.0,
                }
            },
        )

        self.assertEqual(state["S006"]["平仓数量"], 10000.0)

    def test_apply_option_warehouse_editor_submission_preserves_hidden_selection(self) -> None:
        edited_rows = pd.DataFrame(
            [
                {
                    "结构ID": "S006",
                    "选择平仓": True,
                    "平仓方向": "买平仓",
                    "平仓数量": 12000.0,
                    "可平数量": 44700.0,
                    "在库均价": 797.0,
                    "平仓价格": 798.0,
                    "头寸数量": 45000.0,
                },
                {
                    "结构ID": "S007",
                    "选择平仓": False,
                    "平仓方向": "买平仓",
                    "平仓数量": 40000.0,
                    "可平数量": 32500.0,
                    "在库均价": 818.0,
                    "平仓价格": 819.0,
                    "头寸数量": 33000.0,
                },
            ]
        )

        next_edit_state, next_pos_state, next_selected_ids = self.app.apply_option_warehouse_editor_submission(
            edited_rows,
            current_edit_state={"S999": {"平仓方向": "卖平仓", "平仓数量": 100.0, "平仓价格": 790.0}},
            current_pos_qty_state={"S999": {"头寸数量": 100.0, "当前数量": 100.0, "在库均价": 790.0}},
            current_selected_ids=["S999", "S007"],
            visible_ids=["S006", "S007"],
        )

        self.assertEqual(next_selected_ids, ["S999", "S006"])
        self.assertAlmostEqual(float(next_edit_state["S006"]["平仓数量"]), 12000.0)
        self.assertAlmostEqual(float(next_edit_state["S007"]["平仓数量"]), 32500.0)
        self.assertAlmostEqual(float(next_pos_state["S006"]["头寸数量"]), 45000.0)
        self.assertAlmostEqual(float(next_pos_state["S007"]["头寸数量"]), 33000.0)
        self.assertAlmostEqual(float(next_pos_state["S006"]["当前数量"]), 44700.0)
        self.assertAlmostEqual(float(next_pos_state["S007"]["当前数量"]), 32500.0)

    def test_position_qty_edit_state_survives_rerun_after_editor_submission(self) -> None:
        edited_rows = pd.DataFrame(
            [
                {
                    "结构ID": "S006",
                    "选择平仓": False,
                    "平仓方向": "买平仓",
                    "平仓数量": 44700.0,
                    "可平数量": 44700.0,
                    "在库均价": 797.0,
                    "平仓价格": 797.0,
                    "头寸数量": 45000.0,
                }
            ]
        )
        base_rows = pd.DataFrame(
            [
                {
                    "结构ID": "S006",
                    "头寸数量": 44700.0,
                    "可平数量": 44700.0,
                    "在库均价": 797.0,
                }
            ]
        )

        _, next_pos_state, _ = self.app.apply_option_warehouse_editor_submission(
            edited_rows,
            current_edit_state={},
            current_pos_qty_state={},
            current_selected_ids=[],
            visible_ids=["S006"],
        )
        rerun_state = self.app.normalize_structure_position_qty_edit_state(base_rows, next_pos_state)

        self.assertAlmostEqual(float(rerun_state["S006"]["头寸数量"]), 45000.0)
        self.assertAlmostEqual(float(rerun_state["S006"]["当前数量"]), 44700.0)

    def test_build_option_warehouse_selected_rows_uses_committed_edit_state(self) -> None:
        view_rows = pd.DataFrame(
            [
                {
                    "结构ID": "S006",
                    "结构": "Struct-6",
                    "平仓方向": "买平仓",
                    "平仓数量": 44700.0,
                    "平仓价格": 797.0,
                },
                {
                    "结构ID": "S007",
                    "结构": "Struct-7",
                    "平仓方向": "买平仓",
                    "平仓数量": 32500.0,
                    "平仓价格": 818.0,
                },
            ]
        )

        selected_rows = self.app.build_option_warehouse_selected_rows(
            view_rows,
            ["S999", "S007"],
            {
                "S007": {
                    "平仓方向": "卖平仓",
                    "平仓数量": 3000.0,
                    "平仓价格": 795.5,
                }
            },
        )

        self.assertEqual(selected_rows["结构ID"].tolist(), ["S007"])
        self.assertEqual(selected_rows.iloc[0]["平仓方向"], "卖平仓")
        self.assertAlmostEqual(float(selected_rows.iloc[0]["平仓数量"]), 3000.0)
        self.assertAlmostEqual(float(selected_rows.iloc[0]["平仓价格"]), 795.5)

    def test_render_overview_panel_emits_expected_html_structure(self) -> None:
        cards = [
            {"label": "多头在库数量（吨）", "value_text": "41,000.00", "note": "看涨结构在库合计", "tone": "long"},
            {"label": "空头在库数量（吨）", "value_text": "37,000.00", "note": "看跌结构在库合计", "tone": "short"},
        ]

        with mock.patch.object(self.app.st, "markdown") as mocked_markdown:
            self.app.render_option_warehouse_overview_panel(
                asof_text="2026-04-07",
                scope_text="已筛品种：I2609、I2610",
                cards=cards,
            )

        html_text = mocked_markdown.call_args.args[0]
        self.assertIn("Inventory Focus", html_text)
        self.assertIn("统计日期 2026-04-07", html_text)
        self.assertIn("范围 已筛品种：I2609、I2610", html_text)
        self.assertIn("多头在库数量（吨）", html_text)
        self.assertIn("空头在库数量（吨）", html_text)
        self.assertIn("tone-long", html_text)
        self.assertIn("tone-short", html_text)

    def test_render_overview_panel_uses_balanced_grid_for_eight_cards(self) -> None:
        cards = self.app.build_option_warehouse_overview_cards(
            total_qty=78000.0,
            total_avg=785.0,
            long_qty=41000.0,
            short_qty=37000.0,
            long_avg=738.29,
            short_avg=838.43,
        )

        with mock.patch.object(self.app.st, "markdown") as mocked_markdown:
            self.app.render_option_warehouse_overview_panel(
                asof_text="2026-04-07",
                scope_text="全部品种",
                cards=cards,
            )

        html_text = mocked_markdown.call_args.args[0]
        self.assertIn("otc-warehouse-overview-grid layout-eight", html_text)


if __name__ == "__main__":
    unittest.main()
