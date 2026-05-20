import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_warehouse_close_cmd_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WarehouseCloseCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def tearDown(self) -> None:
        for key in [
            "warehouse_close_cmd_payload_test",
            "warehouse_close_cmd_open_test",
            self.app.WAREHOUSE_CLOSE_CMD_DIALOG_META_KEY,
        ]:
            self.app.st.session_state.pop(key, None)

    def test_build_detail_rows_and_sections_group_by_risk_direction_and_strike(self) -> None:
        selected_rows = pd.DataFrame(
            [
                {
                    "结构ID": "S057",
                    "结构": "S057-浮动熔断累沽-华泰长城-入场价(785.50)-行权价(798.50)",
                    "风险子": "华泰长城",
                    "方向": "看跌",
                    "平仓数量": 9000.0,
                    "可平数量": 9000.0,
                },
                {
                    "结构ID": "S060",
                    "结构": "S060-普通累购-华泰长城-入场价(776.00)-行权价(796.00)",
                    "风险子": "华泰长城",
                    "方向": "看跌",
                    "平仓数量": 50500.0,
                    "可平数量": 50500.0,
                },
                {
                    "结构ID": "S063",
                    "结构": "S063-普通累购-海证资本-入场价(815.50)-行权价(820.00)",
                    "风险子": "海证资本",
                    "方向": "看涨",
                    "平仓数量": 3000.0,
                    "可平数量": 3000.0,
                },
                {
                    "结构ID": "S064",
                    "结构": "S064-普通累购-海证资本-入场价(815.00)-行权价(820.00)",
                    "风险子": "海证资本",
                    "方向": "看涨",
                    "平仓数量": 2000.0,
                    "可平数量": 2000.0,
                },
            ]
        )
        struct_meta_map = {
            "S057": {"strike_price": 785.50, "risk_party": "华泰长城", "kind": "DEC", "strategy_code": "ACC"},
            "S060": {"strike_price": 796.00, "risk_party": "华泰长城", "kind": "DEC", "strategy_code": "ACC"},
            "S063": {"strike_price": 820.00, "risk_party": "海证资本", "kind": "ACC", "strategy_code": "ACC"},
            "S064": {"strike_price": 820.00, "risk_party": "海证资本", "kind": "ACC", "strategy_code": "ACC"},
        }

        detail_rows = self.app.build_warehouse_close_command_detail_rows(selected_rows, struct_meta_map)
        self.assertEqual(len(detail_rows), 4)
        self.assertEqual(detail_rows[0]["action_label"], "平空单")
        self.assertEqual(detail_rows[2]["action_label"], "平多单")

        sections = self.app.build_warehouse_close_command_sections(detail_rows)
        self.assertEqual(len(sections), 2)
        self.assertEqual(sections[0]["risk_party"], "华泰长城")
        self.assertEqual(len(sections[0]["actions"]), 2)
        self.assertEqual([float(x["qty"]) for x in sections[0]["actions"]], [9000.0, 50500.0])
        self.assertEqual([float(x["strike_price"]) for x in sections[0]["actions"]], [785.50, 796.00])
        self.assertEqual(sections[1]["risk_party"], "海证资本")
        self.assertEqual(len(sections[1]["actions"]), 1)
        self.assertEqual(float(sections[1]["actions"][0]["qty"]), 5000.0)
        self.assertEqual(float(sections[1]["actions"][0]["strike_price"]), 820.00)

    def test_build_command_text_merges_same_strike_and_splits_different_strikes(self) -> None:
        detail_rows = [
            {
                "risk_party": "华泰长城",
                "direction": "看跌",
                "action_label": "平空单",
                "action_short_label": "平空",
                "qty": 9000.0,
                "strike_price": 785.50,
                "structure_id": "S057",
                "structure_label": "S057",
            },
            {
                "risk_party": "华泰长城",
                "direction": "看跌",
                "action_label": "平空单",
                "action_short_label": "平空",
                "qty": 50500.0,
                "strike_price": 796.00,
                "structure_id": "S060",
                "structure_label": "S060",
            },
            {
                "risk_party": "海证资本",
                "direction": "看涨",
                "action_label": "平多单",
                "action_short_label": "平多",
                "qty": 3000.0,
                "strike_price": 820.00,
                "structure_id": "S063",
                "structure_label": "S063",
            },
            {
                "risk_party": "海证资本",
                "direction": "看涨",
                "action_label": "平多单",
                "action_short_label": "平多",
                "qty": 2000.0,
                "strike_price": 820.00,
                "structure_id": "S064",
                "structure_label": "S064",
            },
        ]

        text = self.app.build_warehouse_close_command_text("2026/04/03", detail_rows)
        summary = self.app.summarize_warehouse_close_command(detail_rows)

        self.assertIn("平仓口令", text)
        self.assertIn("日期：2026/04/03", text)
        self.assertIn("1. 风险子：华泰长城", text)
        self.assertIn("平空单9,000.00吨（行权价：785.50） + 平空单50,500.00吨（行权价：796.00）", text)
        self.assertIn("2. 风险子：海证资本", text)
        self.assertIn("平多单5,000.00吨（行权价：820.00）", text)
        self.assertIn("平仓总量：64,500.00吨", text)

        self.assertEqual(int(summary["risk_count"]), 2)
        self.assertEqual(int(summary["structure_count"]), 4)
        self.assertEqual(int(summary["action_count"]), 3)
        self.assertAlmostEqual(float(summary["long_qty"]), 5000.0)
        self.assertAlmostEqual(float(summary["short_qty"]), 59500.0)
        self.assertAlmostEqual(float(summary["total_qty"]), 64500.0)

    def test_preview_html_and_detail_df_contain_expected_fields(self) -> None:
        detail_rows = [
            {
                "risk_party": "海证资本",
                "direction": "看涨",
                "action_label": "平多单",
                "action_short_label": "平多",
                "qty": 5000.0,
                "strike_price": 820.00,
                "structure_id": "S063",
                "structure_label": "S063-普通累购-海证资本-入场价(815.50)-行权价(820.00)",
            },
            {
                "risk_party": "华泰长城",
                "direction": "看跌",
                "action_label": "平空单",
                "action_short_label": "平空",
                "qty": 9000.0,
                "strike_price": 785.50,
                "structure_id": "S057",
                "structure_label": "S057-浮动熔断累沽-华泰长城-入场价(785.50)-行权价(798.50)",
            },
        ]

        preview_html = self.app.build_warehouse_close_command_preview_html(detail_rows)
        detail_df = self.app.build_warehouse_close_command_detail_df(detail_rows)

        self.assertIn("口令预览", preview_html)
        self.assertIn("按风险子汇总", preview_html)
        self.assertIn("平多", preview_html)
        self.assertIn("平空", preview_html)
        self.assertIn("行权价：820.00", preview_html)
        self.assertIn("行权价：785.50", preview_html)

        self.assertEqual(detail_df.shape[0], 2)
        self.assertIn("风险子", detail_df.columns)
        self.assertIn("结构详情", detail_df.columns)
        self.assertIn("行权价", detail_df.columns)
        self.assertIn("平仓数量（吨）", detail_df.columns)

    def test_simulated_close_price_flows_into_summary_preview_text_and_detail_df(self) -> None:
        detail_rows = [
            {
                "risk_party": "海证资本",
                "direction": "看涨",
                "action_label": "平多单",
                "action_short_label": "平多",
                "qty": 4000.0,
                "strike_price": 793.00,
                "structure_id": "S056",
                "structure_label": "S056",
                "kind_code": "ACC",
                "close_side_code": "SELL",
                "open_price": 780.0,
            },
            {
                "risk_party": "华泰长城",
                "direction": "看跌",
                "action_label": "平空单",
                "action_short_label": "平空",
                "qty": 6000.0,
                "strike_price": 796.00,
                "structure_id": "S060",
                "structure_label": "S060",
                "kind_code": "DEC",
                "close_side_code": "BUY",
                "open_price": 805.0,
            },
        ]

        display_rows = self.app.enrich_warehouse_close_command_detail_rows(detail_rows, close_price=790.0)
        summary = self.app.summarize_warehouse_close_command(display_rows)
        summary_html = self.app.build_warehouse_close_command_summary_html("2026/04/03", display_rows)
        preview_html = self.app.build_warehouse_close_command_preview_html(display_rows)
        text = self.app.build_warehouse_close_command_text("2026/04/03", display_rows)
        detail_df = self.app.build_warehouse_close_command_detail_df(display_rows)

        self.assertAlmostEqual(float(summary["estimated_pnl"]), 130000.0)
        self.assertIn("平仓盈亏", summary_html)
        self.assertIn("平仓价格", preview_html)
        self.assertIn("平仓盈亏", preview_html)
        self.assertIn("价格：790.00", text)
        self.assertIn("平仓价格：790.00", text)
        self.assertIn("平仓预估利润：40,000.00", text)
        self.assertIn("平仓预估利润：90,000.00", text)
        self.assertIn("平仓盈亏：130,000.00", text)
        self.assertIn("在库均价", detail_df.columns)
        self.assertIn("平仓价格", detail_df.columns)
        self.assertIn("平仓盈亏", detail_df.columns)
        self.assertAlmostEqual(float(detail_df.iloc[0]["平仓盈亏"]), 40000.0)
        self.assertAlmostEqual(float(detail_df.iloc[1]["平仓盈亏"]), 90000.0)

    def test_parse_warehouse_close_price_inputs_accepts_space_separated_prices(self) -> None:
        prices, invalid_tokens = self.app.parse_warehouse_close_price_inputs("790 800.5  810")

        self.assertEqual(prices, [790.0, 800.5, 810.0])
        self.assertEqual(invalid_tokens, [])

    def test_parse_warehouse_close_price_inputs_reports_invalid_tokens(self) -> None:
        prices, invalid_tokens = self.app.parse_warehouse_close_price_inputs("790 abc 0 -1")

        self.assertEqual(prices, [790.0])
        self.assertEqual(invalid_tokens, ["abc", "-1"])

    def test_multi_price_preview_rows_reuse_existing_estimated_pnl_logic(self) -> None:
        detail_rows = [
            {
                "risk_party": "海证资本",
                "direction": "看涨",
                "action_label": "平多单",
                "action_short_label": "平多",
                "qty": 4000.0,
                "strike_price": 793.00,
                "structure_id": "S056",
                "structure_label": "S056",
                "kind_code": "ACC",
                "close_side_code": "SELL",
                "open_price": 780.0,
            },
            {
                "risk_party": "华泰长城",
                "direction": "看跌",
                "action_label": "平空单",
                "action_short_label": "平空",
                "qty": 6000.0,
                "strike_price": 796.00,
                "structure_id": "S060",
                "structure_label": "S060",
                "kind_code": "DEC",
                "close_side_code": "BUY",
                "open_price": 805.0,
            },
        ]

        preview_rows = self.app.build_warehouse_close_price_preview_rows(detail_rows, [790.0, 800.0])

        self.assertEqual([float(x["拟平仓价格"]) for x in preview_rows], [790.0, 800.0])
        self.assertAlmostEqual(float(preview_rows[0]["拟平仓预估利润"]), 130000.0)
        self.assertAlmostEqual(float(preview_rows[1]["拟平仓预估利润"]), 110000.0)

        preview_html = self.app.build_warehouse_close_price_preview_html(preview_rows)
        self.assertIn("warehouse-price-preview-card", preview_html)
        self.assertIn("790.00", preview_html)
        self.assertIn("+130,000.00", preview_html)
        self.assertIn("800.00", preview_html)
        self.assertIn("+110,000.00", preview_html)

    def test_dismiss_active_warehouse_close_command_dialog_clears_registered_state(self) -> None:
        payload_key = "warehouse_close_cmd_payload_test"
        open_key = "warehouse_close_cmd_open_test"
        self.app.st.session_state[payload_key] = {"detail_rows": []}
        self.app.st.session_state[open_key] = True

        self.app.remember_warehouse_close_command_dialog_state(payload_key, open_key)
        self.app.dismiss_active_warehouse_close_command_dialog()

        self.assertNotIn(payload_key, self.app.st.session_state)
        self.assertFalse(bool(self.app.st.session_state.get(open_key, False)))
        self.assertNotIn(self.app.WAREHOUSE_CLOSE_CMD_DIALOG_META_KEY, self.app.st.session_state)


if __name__ == "__main__":
    unittest.main()
