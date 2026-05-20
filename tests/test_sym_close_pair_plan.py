import importlib.util
import inspect
import pathlib
import sys
import unittest
from unittest import mock

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_sym_close_plan_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SymClosePairPlanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def tearDown(self) -> None:
        for key in [
            "sym_close_cmd_payload_test",
            "sym_close_cmd_open_test",
            self.app.SYM_CLOSE_CMD_DIALOG_META_KEY,
            "sym_close_pending_test",
            "sym_close_confirm_open_test",
            self.app.SYM_CLOSE_CONFIRM_DIALOG_META_KEY,
        ]:
            self.app.st.session_state.pop(key, None)
        for key in list(self.app.st.session_state.keys()):
            if str(key).startswith("sym_test_"):
                self.app.st.session_state.pop(key, None)

    def test_plan_sym_close_pairs_allocates_long_multi_against_single_short_by_order(self) -> None:
        plan = self.app.plan_sym_close_pairs(
            [
                {"sid": "S054", "label": "多头A", "can_qty": 12000.0},
                {"sid": "S073", "label": "多头B", "can_qty": 10000.0},
            ],
            [
                {"sid": "S055", "label": "空头X", "can_qty": 13000.0},
            ],
        )

        self.assertEqual(plan["selection_mode"], "long_multi")
        self.assertEqual(plan["shared_side"], "short")
        self.assertEqual(plan["shared_sid"], "S055")
        self.assertAlmostEqual(float(plan["default_total_qty"]), 13000.0)
        self.assertEqual(len(plan["pairs"]), 2)
        self.assertAlmostEqual(float(plan["pairs"][0]["default_qty"]), 12000.0)
        self.assertAlmostEqual(float(plan["pairs"][1]["default_qty"]), 1000.0)

    def test_plan_sym_close_pairs_allocates_short_multi_against_single_long_by_order(self) -> None:
        plan = self.app.plan_sym_close_pairs(
            [
                {"sid": "S054", "label": "多头A", "can_qty": 9000.0},
            ],
            [
                {"sid": "S055", "label": "空头X", "can_qty": 3000.0},
                {"sid": "S056", "label": "空头Y", "can_qty": 9000.0},
            ],
        )

        self.assertEqual(plan["selection_mode"], "short_multi")
        self.assertEqual(plan["shared_side"], "long")
        self.assertEqual(plan["shared_sid"], "S054")
        self.assertAlmostEqual(float(plan["default_total_qty"]), 9000.0)
        self.assertEqual(len(plan["pairs"]), 2)
        self.assertAlmostEqual(float(plan["pairs"][0]["default_qty"]), 3000.0)
        self.assertAlmostEqual(float(plan["pairs"][1]["default_qty"]), 6000.0)

    def test_build_sym_close_command_text_emits_multiple_entries(self) -> None:
        text = self.app.build_sym_close_command_text(
            "2026/03/31",
            [
                {
                    "long_label": "多头A",
                    "short_label": "空头X",
                    "pair_qty": 12000.0,
                    "long_avg_price": 750.0,
                    "short_avg_price": 830.0,
                    "long_risk_party": "海证资本",
                    "short_risk_party": "海证资本",
                },
                {
                    "long_label": "多头B",
                    "short_label": "空头X",
                    "pair_qty": 1000.0,
                    "long_avg_price": 800.0,
                    "short_avg_price": 838.0,
                    "long_risk_party": "中证资本",
                    "short_risk_party": "中证资本",
                },
                {"long_label": "多头C", "short_label": "空头X", "pair_qty": 0.0},
            ],
            total_profit=944000.0,
        )

        self.assertIn("多空平仓口令", text)
        self.assertIn("日期：2026/03/31", text)
        self.assertIn("价格：按统一竞价价格", text)
        self.assertIn("动作：对称平仓 数量和对应结构如下", text)
        self.assertIn("1. 风险子：海证资本", text)
        self.assertIn("   多头：多头A", text)
        self.assertIn("数量：平多单12,000.00吨；平空单12,000.00吨；预计利润960,000.00", text)
        self.assertIn("\n\n2. 风险子：中证资本\n   多头：多头B", text)
        self.assertIn("   多头：多头B", text)
        self.assertIn("数量：平多单1,000.00吨；平空单1,000.00吨；预计利润38,000.00", text)
        self.assertIn("平仓利润：944,000.00", text)
        self.assertNotIn("多头C", text)

    def test_build_sym_close_command_text_places_cross_risk_rows_at_bottom(self) -> None:
        text = self.app.build_sym_close_command_text(
            "2026/04/01",
            [
                {
                    "seq": 1,
                    "long_label": "多头A",
                    "short_label": "空头A",
                    "pair_qty": 1000.0,
                    "long_risk_party": "海证资本",
                    "short_risk_party": "中证资本",
                    "long_avg_price": 700.0,
                    "short_avg_price": 800.0,
                    "match_type": "lowest_strike_fallback",
                },
                {
                    "seq": 2,
                    "long_label": "多头B",
                    "short_label": "空头B",
                    "pair_qty": 2000.0,
                    "long_risk_party": "海证资本",
                    "short_risk_party": "海证资本",
                    "long_avg_price": 710.0,
                    "short_avg_price": 810.0,
                },
            ],
            total_profit=300000.0,
        )

        same_risk_pos = text.find("风险子：海证资本")
        cross_risk_pos = text.find("多头风险子：海证资本；空头风险子：中证资本")
        self.assertGreaterEqual(same_risk_pos, 0)
        self.assertGreaterEqual(cross_risk_pos, 0)
        self.assertLess(same_risk_pos, cross_risk_pos)
        self.assertIn("1. 风险子：海证资本", text)
        self.assertIn("   多头：多头B", text)
        self.assertIn("2. 多头风险子：海证资本；空头风险子：中证资本", text)
        self.assertIn("   多头：多头A", text)

    def test_build_sym_close_command_summary_html_contains_core_metrics(self) -> None:
        html = self.app.build_sym_close_command_summary_html(
            "2026/04/01",
            [
                {"pair_qty": 12000.0, "long_risk_party": "海证资本", "short_risk_party": "海证资本"},
                {"pair_qty": 8000.0, "long_risk_party": "海证资本", "short_risk_party": "中证资本", "match_type": "lowest_strike_fallback"},
            ],
            total_profit=3244000.0,
        )

        self.assertIn("执行摘要", html)
        self.assertIn("2026/04/01", html)
        self.assertIn("20,000.00", html)
        self.assertIn("3,244,000.00", html)
        self.assertIn("12,000.00", html)
        self.assertIn("8,000.00", html)

    def test_build_sym_close_preview_label_html_only_highlights_strike_segment(self) -> None:
        html = self.app.build_sym_close_preview_label_html(
            "S054-普通累购-海证资本-入场价（750.00）-行权价（720.00）"
        )

        self.assertIn("S054-普通累购-海证资本-入场价（750.00）-", html)
        self.assertIn("<span class='sym-close-cmd-strike'>行权价（720.00）</span>", html)
        self.assertNotIn("sym-close-cmd-strike'>入场价", html)

    def test_build_sym_close_command_preview_html_splits_same_and_cross_risk_groups(self) -> None:
        html = self.app.build_sym_close_command_preview_html(
            [
                {
                    "seq": 1,
                    "long_label": "多头A-入场价（750.00）-行权价（720.00）",
                    "short_label": "空头A-入场价（780.00）-行权价（830.00）",
                    "pair_qty": 12000.0,
                    "long_risk_party": "海证资本",
                    "short_risk_party": "海证资本",
                    "long_avg_price": 750.0,
                    "short_avg_price": 830.0,
                },
                {
                    "seq": 2,
                    "long_label": "多头B-入场价（800.00）-行权价（750.00）",
                    "short_label": "空头B-入场价（820.00）-行权价（838.00）",
                    "pair_qty": 8000.0,
                    "long_risk_party": "海证资本",
                    "short_risk_party": "中证资本",
                    "long_avg_price": 800.0,
                    "short_avg_price": 838.0,
                    "match_type": "lowest_strike_fallback",
                },
            ],
            total_profit=3244000.0,
        )

        same_pos = html.find("同风险子优先")
        cross_pos = html.find("跨风险子补配")
        self.assertGreaterEqual(same_pos, 0)
        self.assertGreaterEqual(cross_pos, 0)
        self.assertLess(same_pos, cross_pos)
        self.assertIn("优先在同一风险子内完成对称平仓", html)
        self.assertIn("剩余多头按全局最低行权价空头继续补配", html)
        self.assertIn("1. 风险子：海证资本", html)
        self.assertIn("数量：平多单12,000.00吨；平空单12,000.00吨", html)
        self.assertNotIn("数量：平多单12,000.00吨；平空单12,000.00吨；预计利润", html)
        self.assertIn("sym-close-cmd-strike", html)
        self.assertIn("<span class='sym-close-cmd-strike'>行权价（720.00）</span>", html)

    def test_plan_sym_close_pairs_rejects_double_multi(self) -> None:
        with self.assertRaisesRegex(ValueError, "单边多选"):
            self.app.plan_sym_close_pairs(
                [
                    {"sid": "S054", "label": "多头A", "can_qty": 12000.0},
                    {"sid": "S073", "label": "多头B", "can_qty": 10000.0},
                ],
                [
                    {"sid": "S055", "label": "空头X", "can_qty": 13000.0},
                    {"sid": "S056", "label": "空头Y", "can_qty": 5000.0},
                ],
            )

    def test_plan_sym_close_auto_pairs_prioritizes_same_risk_before_cross_risk_fallback(self) -> None:
        plan = self.app.plan_sym_close_auto_pairs(
            [
                {"sid": "L1", "label": "多头1", "risk_party": "海证资本", "can_qty": 100.0, "avg_price": 700.0},
                {"sid": "L2", "label": "多头2", "risk_party": "渤海资本", "can_qty": 60.0, "avg_price": 710.0},
            ],
            [
                {"sid": "S1", "label": "空头1", "risk_party": "海证资本", "can_qty": 70.0, "strike_price": 788.0, "avg_price": 800.0},
                {"sid": "S2", "label": "空头2", "risk_party": "海证资本", "can_qty": 30.0, "strike_price": 800.0, "avg_price": 805.0},
                {"sid": "S3", "label": "空头3", "risk_party": "渤海资本", "can_qty": 30.0, "strike_price": 780.0, "avg_price": 790.0},
            ],
        )

        pairs = plan["pairs"]
        self.assertEqual([row["short_sid"] for row in pairs[:2]], ["S1", "S2"])
        self.assertTrue(all(row["match_type"] == "same_risk" for row in pairs[:3]))
        self.assertAlmostEqual(float(plan["same_risk_total_qty"]), 130.0)
        self.assertAlmostEqual(float(plan["cross_risk_total_qty"]), 0.0)
        self.assertEqual(plan["unmatched_longs"][0]["sid"], "L2")
        self.assertAlmostEqual(float(plan["unmatched_longs"][0]["remaining_qty"]), 30.0)

    def test_plan_sym_close_auto_pairs_uses_global_lowest_strike_for_remaining_longs(self) -> None:
        plan = self.app.plan_sym_close_auto_pairs(
            [
                {"sid": "L1", "label": "多头1", "risk_party": "海证资本", "can_qty": 120.0, "avg_price": 700.0},
            ],
            [
                {"sid": "S1", "label": "空头1", "risk_party": "海证资本", "can_qty": 40.0, "strike_price": 800.0, "avg_price": 810.0},
                {"sid": "S2", "label": "空头2", "risk_party": "渤海资本", "can_qty": 30.0, "strike_price": 788.0, "avg_price": 808.0},
                {"sid": "S3", "label": "空头3", "risk_party": "渤海资本", "can_qty": 40.0, "strike_price": 795.0, "avg_price": 809.0},
            ],
        )

        pairs = plan["pairs"]
        self.assertEqual([(row["short_sid"], float(row["pair_qty"])) for row in pairs], [("S1", 40.0), ("S2", 30.0), ("S3", 40.0)])
        self.assertEqual([row["match_type"] for row in pairs], ["same_risk", "lowest_strike_fallback", "lowest_strike_fallback"])
        self.assertAlmostEqual(float(plan["same_risk_total_qty"]), 40.0)
        self.assertAlmostEqual(float(plan["cross_risk_total_qty"]), 70.0)
        self.assertEqual(plan["unmatched_longs"][0]["sid"], "L1")
        self.assertAlmostEqual(float(plan["unmatched_longs"][0]["remaining_qty"]), 10.0)

    def test_resolve_sym_close_shared_risk_only_returns_single_risk_when_consistent(self) -> None:
        row_map = {
            "L1": {"风险子": "海证资本"},
            "L2": {"risk_party": "海证资本"},
            "L3": {"风险子": "渤海资本"},
        }

        self.assertEqual(self.app.resolve_sym_close_shared_risk(["L1", "L2"], row_map), "海证资本")
        self.assertEqual(self.app.resolve_sym_close_shared_risk(["L1", "L3"], row_map), "")
        self.assertEqual(self.app.resolve_sym_close_shared_risk(["L1", "L9"], row_map), "")

    def test_sort_sym_close_candidate_sids_and_auto_match_prioritize_same_risk_low_strike(self) -> None:
        row_map = {
            "S900": {"风险子": "渤海资本", "strike_price": 900.0},
            "S800": {"风险子": "海证资本", "strike_price": 800.0},
            "S788": {"风险子": "海证资本", "strike_price": 788.0},
        }

        ordered = self.app.sort_sym_close_candidate_sids(
            ["S900", "S800", "S788"],
            row_map,
            priority_risk="海证资本",
        )

        self.assertEqual(ordered, ["S788", "S800", "S900"])
        self.assertEqual(
            self.app.pick_sym_close_auto_match_sid(
                ["S900", "S800", "S788"],
                row_map,
                priority_risk="海证资本",
            ),
            "S788",
        )

    def test_sync_sym_close_risk_batch_selection_respects_manual_adjustments_until_risk_changes(self) -> None:
        risk_key = "sym_test_risk"
        prev_key = "sym_test_risk_prev"
        struct_key = "sym_test_struct"
        order_key = "sym_test_order"

        self.app.st.session_state[risk_key] = ["海证资本"]
        self.app.st.session_state[prev_key] = []
        self.app.st.session_state[struct_key] = []
        self.app.st.session_state[order_key] = []

        self.app.sync_sym_close_risk_batch_selection(
            risk_key=risk_key,
            risk_prev_key=prev_key,
            struct_key=struct_key,
            order_key=order_key,
            valid_risks=["海证资本", "渤海资本"],
            valid_sids=["S1", "S2", "S3"],
            risk_to_sids={"海证资本": ["S2", "S1"], "渤海资本": ["S3"]},
        )
        self.assertEqual(self.app.st.session_state[struct_key], ["S2", "S1"])
        self.assertEqual(self.app.st.session_state[order_key], ["S2", "S1"])

        self.app.st.session_state[struct_key] = ["S2"]
        self.app.st.session_state[order_key] = ["S2"]
        self.app.sync_sym_close_risk_batch_selection(
            risk_key=risk_key,
            risk_prev_key=prev_key,
            struct_key=struct_key,
            order_key=order_key,
            valid_risks=["海证资本", "渤海资本"],
            valid_sids=["S1", "S2", "S3"],
            risk_to_sids={"海证资本": ["S2", "S1"], "渤海资本": ["S3"]},
        )
        self.assertEqual(self.app.st.session_state[struct_key], ["S2"])
        self.assertEqual(self.app.st.session_state[order_key], ["S2"])

        self.app.st.session_state[risk_key] = ["渤海资本"]
        self.app.sync_sym_close_risk_batch_selection(
            risk_key=risk_key,
            risk_prev_key=prev_key,
            struct_key=struct_key,
            order_key=order_key,
            valid_risks=["海证资本", "渤海资本"],
            valid_sids=["S1", "S2", "S3"],
            risk_to_sids={"海证资本": ["S2", "S1"], "渤海资本": ["S3"]},
        )
        self.assertEqual(self.app.st.session_state[struct_key], ["S3"])
        self.assertEqual(self.app.st.session_state[order_key], ["S3"])

    def test_build_sym_close_detail_df_uses_flat_close_qty_column_title(self) -> None:
        df = self.app.build_sym_close_detail_df(
            [
                {"seq": 1, "long_label": "多头A", "short_label": "空头B", "pair_qty": 1000.0},
            ]
        )

        self.assertIn("平仓数量（吨）", df.columns.tolist())
        self.assertNotIn("数量(吨)", df.columns.tolist())

    def test_build_sym_close_auto_selection_df_orders_rows_and_marks_selected_pairs(self) -> None:
        same_row = {
            "seq": 2,
            "long_sid": "L1",
            "long_label": "Long Same",
            "long_risk_party": "Risk-A",
            "long_avg_price": 700.0,
            "short_sid": "S1",
            "short_label": "Short Same",
            "short_risk_party": "Risk-A",
            "short_avg_price": 800.0,
            "pair_qty": 1000.0,
            "match_type": "same_risk",
            "match_type_label": "same",
        }
        cross_row = {
            "seq": 1,
            "long_sid": "L2",
            "long_label": "Long Cross",
            "long_risk_party": "Risk-A",
            "long_avg_price": 710.0,
            "short_sid": "S2",
            "short_label": "Short Cross",
            "short_risk_party": "Risk-B",
            "short_avg_price": 830.0,
            "pair_qty": 2000.0,
            "match_type": "lowest_strike_fallback",
            "match_type_label": "cross",
        }

        df = self.app.build_sym_close_auto_selection_df(
            [cross_row, same_row],
            [self.app.build_sym_close_pair_signature(same_row)],
        )

        self.assertEqual(df["多头结构"].tolist(), ["Long Same", "Long Cross"])
        self.assertEqual(df["空头结构"].tolist(), ["Short Same", "Short Cross"])
        self.assertTrue(bool(df.iloc[0]["选择平仓"]))
        self.assertFalse(bool(df.iloc[1]["选择平仓"]))
        self.assertIn("预计利润", df.columns.tolist())
        self.assertEqual(df.columns.tolist()[-1], "__pair_signature__")
        self.assertAlmostEqual(float(df.iloc[0]["预计利润"]), 100000.0)
        self.assertAlmostEqual(float(df.iloc[1]["预计利润"]), 240000.0)

    def test_ensure_hidden_batch_pairing_enabled_overrides_stale_false_state(self) -> None:
        key = "sym_test_hidden_batch_mode"
        self.app.st.session_state[key] = False

        enabled = self.app.ensure_hidden_batch_pairing_enabled(key)

        self.assertTrue(enabled)
        self.assertTrue(bool(self.app.st.session_state.get(key)))

    def test_filter_sym_close_pairs_by_signatures_and_summary_only_use_selected_subset(self) -> None:
        same_row = {
            "seq": 1,
            "long_sid": "L1",
            "long_label": "Long Same",
            "long_risk_party": "Risk-A",
            "long_avg_price": 700.0,
            "short_sid": "S1",
            "short_label": "Short Same",
            "short_risk_party": "Risk-A",
            "short_avg_price": 800.0,
            "pair_qty": 1000.0,
            "match_type": "same_risk",
            "match_type_label": "same",
        }
        cross_row = {
            "seq": 2,
            "long_sid": "L2",
            "long_label": "Long Cross",
            "long_risk_party": "Risk-A",
            "long_avg_price": 710.0,
            "short_sid": "S2",
            "short_label": "Short Cross",
            "short_risk_party": "Risk-B",
            "short_avg_price": 830.0,
            "pair_qty": 2000.0,
            "match_type": "lowest_strike_fallback",
            "match_type_label": "cross",
        }

        filtered = self.app.filter_sym_close_pairs_by_signatures(
            [same_row, cross_row],
            [self.app.build_sym_close_pair_signature(cross_row)],
        )
        summary = self.app.summarize_sym_close_pair_rows(filtered)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["long_sid"], "L2")
        self.assertAlmostEqual(float(summary["pair_count"]), 1.0)
        self.assertAlmostEqual(float(summary["pair_total_qty"]), 2000.0)
        self.assertAlmostEqual(float(summary["same_risk_total_qty"]), 0.0)
        self.assertAlmostEqual(float(summary["cross_risk_total_qty"]), 2000.0)
        self.assertAlmostEqual(float(summary["pair_total_profit"]), 240000.0)

    def test_preview_profit_prefers_pair_profit_basis_price_over_avg_price(self) -> None:
        row = {
            "seq": 1,
            "long_sid": "L1",
            "long_label": "Long-1",
            "long_avg_price": 795.0,
            "long_strike_price": 795.0,
            "long_profit_basis_price": 795.0,
            "short_sid": "S1",
            "short_label": "Short-1",
            "short_avg_price": 795.47674375,
            "short_strike_price": 798.5,
            "short_profit_basis_price": 798.5,
            "pair_qty": 8000.0,
            "match_type": "same_risk",
            "match_type_label": "same",
        }

        df = self.app.build_sym_close_auto_selection_df([row])
        summary = self.app.summarize_sym_close_pair_rows([row])

        self.assertAlmostEqual(float(self.app.calc_sym_close_row_profit(row)), 28000.0)
        self.assertAlmostEqual(float(df.iloc[0]["预计利润"]), 28000.0)
        self.assertAlmostEqual(float(summary["pair_total_profit"]), 28000.0)

    def test_prepare_sym_close_pending_payload_prices_profit_by_pair_profit_basis(self) -> None:
        open_lots = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "L1",
                    "underlying": "I.TEST",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 60.0,
                    "open_qty": 60.0,
                    "gen_price": 780.0,
                },
                {
                    "group_id": "G1",
                    "structure_id": "L1",
                    "underlying": "I.TEST",
                    "kind": "ACC",
                    "date": "2026-04-02",
                    "generated_qty": 40.0,
                    "open_qty": 40.0,
                    "gen_price": 790.0,
                },
                {
                    "group_id": "G1",
                    "structure_id": "S1",
                    "underlying": "I.TEST",
                    "kind": "DEC",
                    "date": "2026-04-01",
                    "generated_qty": 100.0,
                    "open_qty": 100.0,
                    "gen_price": 820.0,
                },
            ]
        )
        pair_rows = [
            {
                "seq": 1,
                "long_sid": "L1",
                "long_label": "Long-1",
                "long_underlying": "I.TEST",
                "long_risk_party": "Risk-A",
                "long_avg_price": 784.0,
                "long_strike_price": 795.0,
                "long_profit_basis_price": 795.0,
                "short_sid": "S1",
                "short_label": "Short-1",
                "short_underlying": "I.TEST",
                "short_risk_party": "Risk-A",
                "short_avg_price": 820.0,
                "short_strike_price": 798.5,
                "short_profit_basis_price": 798.5,
                "pair_qty": 80.0,
            }
        ]
        plan_payload = {
            "pair_dt": "2026-04-03",
            "pair_dt_cmd": "2026/04/03",
            "pair_px": 796.0,
            "entry_origin": "auto",
            "selection_mode": "auto",
            "token": "TEST1234",
        }

        with mock.patch.object(self.app, "compute_sym_close_open_lots", return_value=(open_lots, "")), mock.patch.object(
            self.app,
            "validate_no_worse_over_close",
            return_value=(True, ""),
        ):
            pending, err = self.app.prepare_sym_close_pending_payload(
                None,
                gid="G1",
                plan_payload=plan_payload,
                pair_rows=pair_rows,
            )

        self.assertEqual(err, "")
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertAlmostEqual(float(pending["pnl_long"]), 80.0)
        self.assertAlmostEqual(float(pending["pnl_short"]), 200.0)
        self.assertAlmostEqual(float(pending["pnl_total"]), 280.0)
        self.assertAlmostEqual(float(pending["pair_total_qty"]), 80.0)
        saved_rows = pd.DataFrame(pending["rows"])
        long_rows = saved_rows[saved_rows["structure_id"].astype(str) == "L1"].copy()
        self.assertEqual(long_rows["source_gen_date"].astype(str).tolist(), ["2026-04-01", "2026-04-02"])
        self.assertEqual(pd.to_numeric(long_rows["qty"], errors="coerce").round(6).tolist(), [60.0, 20.0])
        self.assertEqual(pd.to_numeric(long_rows["open_price"], errors="coerce").round(6).tolist(), [795.0, 795.0])

    def test_apply_airbag_hedge_manual_total_to_rows_distributes_airbag_profit_by_qty(self) -> None:
        rows = [
            {
                "close_category": self.app.AIRBAG_HEDGE_CLOSE_CATEGORY,
                "side": "SELL",
                "qty": 100.0,
                "pnl": 120.0,
            },
            {
                "close_category": self.app.AIRBAG_HEDGE_CLOSE_CATEGORY,
                "side": "平仓",
                "qty": 30.0,
                "pnl": 0.0,
            },
            {
                "close_category": self.app.AIRBAG_HEDGE_CLOSE_CATEGORY,
                "side": "平仓",
                "qty": 70.0,
                "pnl": 0.0,
            },
        ]

        adjusted = self.app.apply_airbag_hedge_manual_total_to_rows(rows, 520.0)

        airbag_rows = [row for row in adjusted if str(row.get("side")) == "平仓"]
        self.assertAlmostEqual(sum(float(row.get("pnl", 0.0)) for row in airbag_rows), 400.0)
        self.assertAlmostEqual(float(airbag_rows[0]["pnl"]), 120.0)
        self.assertAlmostEqual(float(airbag_rows[1]["pnl"]), 280.0)

    def test_prepare_airbag_hedge_pending_payload_reduces_linear_lots_and_builds_structure_reduction_rows(self) -> None:
        open_lots = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "L1",
                    "underlying": "I.TEST",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 60.0,
                    "open_qty": 60.0,
                    "gen_price": 780.0,
                },
                {
                    "group_id": "G1",
                    "structure_id": "L1",
                    "underlying": "I.TEST",
                    "kind": "ACC",
                    "date": "2026-04-02",
                    "generated_qty": 40.0,
                    "open_qty": 40.0,
                    "gen_price": 790.0,
                },
            ]
        )
        pair_rows = [
            {
                "seq": 1,
                "long_sid": "L1",
                "long_label": "Linear-1",
                "long_underlying": "I.TEST",
                "long_risk_party": "Risk-A",
                "long_avg_price": 784.0,
                "long_strike_price": 795.0,
                "long_profit_basis_price": 795.0,
                "short_sid": "A1",
                "short_label": "Airbag-1",
                "short_underlying": "I.TEST",
                "short_risk_party": "Risk-A",
                "short_avg_price": 820.0,
                "short_strike_price": 798.5,
                "short_profit_basis_price": 798.5,
                "short_can": 100.0,
                "pair_qty": 80.0,
            }
        ]
        plan_payload = {
            "pair_dt": "2026-04-03",
            "pair_dt_cmd": "2026/04/03",
            "pair_px": 796.0,
            "entry_origin": "manual",
            "selection_mode": "single",
            "linear_kind": "ACC",
            "airbag_kind": "DEC",
            **self.app.resolve_airbag_hedge_mode_meta("linear_long_vs_dec"),
        }

        with mock.patch.object(self.app, "compute_sym_close_open_lots", return_value=(open_lots, "")), mock.patch.object(
            self.app,
            "validate_no_worse_over_close",
            return_value=(True, ""),
        ):
            pending, err = self.app.prepare_airbag_hedge_pending_payload(
                None,
                gid="G1",
                plan_payload=plan_payload,
                pair_rows=pair_rows,
            )

        self.assertEqual(err, "")
        self.assertIsNotNone(pending)
        assert pending is not None
        self.assertTrue(bool(pending["manual_profit_required"]))
        self.assertAlmostEqual(float(pending["linear_pnl"]), 80.0)
        self.assertAlmostEqual(float(pending["reference_total_pnl"]), 280.0)
        saved_rows = pd.DataFrame(pending["rows"])
        self.assertTrue((saved_rows["close_category"].astype(str) == self.app.AIRBAG_HEDGE_CLOSE_CATEGORY).all())
        linear_rows = saved_rows[saved_rows["structure_id"].astype(str) == "L1"].copy()
        airbag_rows = saved_rows[saved_rows["structure_id"].astype(str) == "A1"].copy()
        self.assertEqual(linear_rows["source_gen_date"].astype(str).tolist(), ["2026-04-01", "2026-04-02"])
        self.assertEqual(pd.to_numeric(linear_rows["qty"], errors="coerce").round(6).tolist(), [60.0, 20.0])
        self.assertEqual(pd.to_numeric(linear_rows["is_external"], errors="coerce").astype(int).tolist(), [0, 0])
        self.assertEqual(airbag_rows["side"].astype(str).tolist(), ["平仓"])
        self.assertEqual(pd.to_numeric(airbag_rows["qty"], errors="coerce").round(6).tolist(), [80.0])
        adjusted_rows = self.app.apply_airbag_hedge_manual_total_to_rows(pending["rows"], 500.0)
        adjusted_airbag = [row for row in adjusted_rows if str(row.get("structure_id")) == "A1"]
        self.assertAlmostEqual(sum(float(row.get("pnl", 0.0)) for row in adjusted_airbag), 420.0)

    def test_prepare_airbag_hedge_plan_payload_supports_multi_airbags_against_single_linear(self) -> None:
        open_lots = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "L1",
                    "underlying": "I.TEST",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 5000.0,
                    "open_qty": 5000.0,
                    "gen_price": 780.0,
                }
            ]
        )
        linear_map = {
            "L1": {
                "结构": "Linear-1",
                "品种": "I.TEST",
                "风险子": "Risk-A",
                "行权价": 792.0,
            }
        }
        airbag_map = {
            "A1": {
                "结构": "Airbag-1",
                "品种": "I.TEST",
                "风险子": "Risk-A",
                "可平数量": 3000.0,
                "在库均价": 820.0,
                "行权价": 810.0,
            },
            "A2": {
                "结构": "Airbag-2",
                "品种": "I.TEST",
                "风险子": "Risk-A",
                "可平数量": 4000.0,
                "在库均价": 825.0,
                "行权价": 815.0,
            },
        }

        with mock.patch.object(self.app, "compute_sym_close_open_lots", return_value=(open_lots, "")):
            plan, err = self.app.prepare_airbag_hedge_plan_payload(
                None,
                gid="G1",
                pair_dt_obj=self.app.parse_date_maybe("2026-04-03"),
                pair_close_px=796.0,
                linear_sids=["L1"],
                airbag_sids=["A1", "A2"],
                linear_map=linear_map,
                airbag_map=airbag_map,
                mode_meta=self.app.resolve_airbag_hedge_mode_meta("linear_long_vs_dec"),
                fallback_underlying="I.TEST",
            )

        self.assertEqual(err, "")
        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan["selection_mode"], "short_multi")
        self.assertEqual(plan["shared_side"], "long")
        self.assertEqual(plan["shared_sid"], "L1")
        self.assertEqual([row["short_sid"] for row in plan["pairs"]], ["A1", "A2"])
        self.assertAlmostEqual(float(plan["pairs"][0]["default_qty"]), 3000.0)
        self.assertAlmostEqual(float(plan["pairs"][1]["default_qty"]), 2000.0)

    def test_dismiss_active_sym_close_command_dialog_clears_registered_state(self) -> None:
        payload_key = "sym_close_cmd_payload_test"
        open_key = "sym_close_cmd_open_test"
        self.app.st.session_state[payload_key] = {"group_id": "G1"}
        self.app.st.session_state[open_key] = True

        self.app.remember_sym_close_command_dialog_state(payload_key, open_key)
        self.app.dismiss_active_sym_close_command_dialog()

        self.assertFalse(bool(self.app.st.session_state.get(open_key, False)))
        self.assertIsNone(self.app.st.session_state.get(payload_key))
        self.assertIsNone(self.app.st.session_state.get(self.app.SYM_CLOSE_CMD_DIALOG_META_KEY))

    def test_dismiss_active_sym_close_confirm_dialog_clears_registered_state(self) -> None:
        pending_key = "sym_close_pending_test"
        open_key = "sym_close_confirm_open_test"
        self.app.st.session_state[pending_key] = {"group_id": "G1", "entry_origin": "auto"}
        self.app.st.session_state[open_key] = True

        self.app.remember_sym_close_confirm_dialog_state(pending_key, open_key)
        self.app.dismiss_active_sym_close_confirm_dialog()

        self.assertFalse(bool(self.app.st.session_state.get(open_key, False)))
        self.assertIsNone(self.app.st.session_state.get(pending_key))
        self.assertIsNone(self.app.st.session_state.get(self.app.SYM_CLOSE_CONFIRM_DIALOG_META_KEY))

    def test_sym_close_confirm_dialog_saves_without_over_close_recheck(self) -> None:
        source = inspect.getsource(self.app.sym_close_confirm_dialog)

        self.assertIn("insert_close_rows(conn, rows_to_save)", source)
        self.assertNotIn("validate_no_worse_over_close(", source)


if __name__ == "__main__":
    unittest.main()
