import importlib.util
import json
import pathlib
import sqlite3
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_vanilla_display_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VanillaOptionDisplayLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_vanilla_name_and_detail_label_follow_new_pattern(self) -> None:
        legacy_name = "香草期权-看跌卖出-铁矿石-到期日(2026-04-27)-行权价(785.00)-期权费(5.00)"
        self.assertEqual(self.app.build_vanilla_option_name("put", "sell"), "卖出看跌")
        self.assertEqual(
            self.app.default_structure_name(self.app.VANILLA_OPTION_CODE, "DEC", fallback_name=legacy_name),
            "卖出看跌",
        )
        detail_label = self.app.structure_detail_label_unified(
            structure_id="S068",
            strategy_value=self.app.VANILLA_OPTION_CODE,
            kind_value="DEC",
            fallback_name=legacy_name,
            risk_party="海证资本",
            entry_price=820.0,
            strike_price=785.0,
        )
        self.assertEqual(detail_label, "S068-卖出看跌-海证资本-入场价（820.0）-行权价（785.0）")

    def test_build_vanilla_option_detail_card_frame_includes_special_metadata(self) -> None:
        resolved = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "kind": "DEC",
            "name": "香草期权-看跌卖出-铁矿石-到期日(2026-04-27)-行权价(785.00)-期权费(5.00)",
            "option_type": "put",
            "side": "sell",
            "underlying": "铁矿石",
            "trade_date": "2026-03-30",
            "expiry_date": "2026-04-27",
            "entry_price": 820.0,
            "strike_price": 785.0,
            "premium": 5.0,
            "customer_name": "应隐藏",
            "counterparty": "应隐藏",
            "contract_month": "应隐藏",
            "note": "应隐藏",
        }
        detail_df = self.app.build_vanilla_option_detail_card_frame(resolved)
        detail_map = dict(zip(detail_df["项目"], detail_df["内容"]))
        self.assertEqual(detail_map["结构名称"], "卖出看跌")
        self.assertEqual(detail_map["开始日期"], "2026-03-30")
        self.assertEqual(detail_map["入场价"], "820.0")
        self.assertEqual(detail_map["行权价"], "785.0")
        self.assertEqual(detail_map["期权费"], "5.0")
        self.assertEqual(detail_map["客户名称"], "应隐藏")
        self.assertEqual(detail_map["交易对手"], "应隐藏")
        self.assertEqual(detail_map["合约/月份"], "应隐藏")
        self.assertEqual(detail_map["备注"], "应隐藏")
        self.assertNotIn("交易日期", detail_map)

    def test_vanilla_option_maturity_sets_explicit_terminate(self) -> None:
        state = {}
        res = self.app._sm_vanilla_option(
            {
                "kind": "ACC",
                "option_type": "call",
                "side": "sell",
                "strike_price": 100.0,
                "premium": 2.0,
                "base_qty_per_day": 10.0,
            },
            110.0,
            {"remaining_days": 1},
            state,
        )

        self.assertEqual(res["flags"], ["VANILLA_EXPIRED_ITM"])
        self.assertTrue(res["terminate"])
        self.assertTrue(state["terminated"])

    def test_build_vanilla_option_detail_card_frame_marks_finished_when_remaining_days_non_positive(self) -> None:
        resolved = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "kind": "DEC",
            "name": "香草期权-看跌卖出-铁矿石-到期日(2026-04-27)-行权价(785.00)-期权费(5.00)",
            "option_type": "put",
            "side": "sell",
            "underlying": "铁矿石",
            "trade_date": "2026-03-30",
            "expiry_date": "2026-04-27",
            "entry_price": 820.0,
            "strike_price": 785.0,
            "premium": 5.0,
        }
        latest_daily = {
            "状态": "未行权",
            "剩余交易日": 0,
            "累计浮盈亏": 1200.0,
            "当前持仓量": 0.0,
        }
        detail_df = self.app.build_vanilla_option_detail_card_frame(resolved, latest_daily)
        detail_map = dict(zip(detail_df["项目"], detail_df["内容"]))
        self.assertEqual(detail_map["当前状态"], "已结束")

    def test_vanilla_status_cn_collapses_to_two_states(self) -> None:
        self.assertEqual(self.app.status_to_cn("存续中-卖出看跌", 0.0, 0.0), "未行权")
        self.assertEqual(self.app.status_to_cn("到期结束-实值卖出看跌", 0.0, 0.0), "行权")
        self.assertEqual(self.app.status_to_cn("到期结束-虚值卖出看跌", 0.0, 0.0), "未行权")

    def test_enrich_vanilla_option_daily_rows_tolerates_missing_base_qty_per_day(self) -> None:
        s_df = pd.DataFrame(
            [
                {
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "date": "2026-03-30",
                    "structure_id": "S068",
                    "kind": "DEC",
                    "base_qty": 20000.0,
                    "premium": 5.0,
                    "option_type": "put",
                    "strike_price": 780.0,
                    "settle": 770.0,
                }
            ]
        )
        out = self.app.enrich_vanilla_option_daily_rows(
            s_df,
            close2_df=pd.DataFrame(),
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-03-30",
        )
        self.assertEqual(float(out.loc[0, "current_open_qty"]), 20000.0)
        self.assertIn("cum_pnl", out.columns)

    def test_adjust_structure_daily_view_columns_hides_airbag_payoff_for_vanilla(self) -> None:
        strategy_col = "\u7b56\u7565\u7c7b\u578b"
        airbag_payoff_col = "\u5b89\u5168\u6c14\u56ca\u5230\u671f\u6536\u76ca"
        premium_col = "\u671f\u6743\u8d39"

        vanilla_view = pd.DataFrame(
            [{strategy_col: "\u9999\u8349\u671f\u6743", airbag_payoff_col: 75000.0, premium_col: 9.2}]
        )
        vanilla_out = self.app.adjust_structure_daily_view_columns(vanilla_view)
        self.assertNotIn(airbag_payoff_col, vanilla_out.columns)
        self.assertIn(premium_col, vanilla_out.columns)

        airbag_view = pd.DataFrame([{strategy_col: "\u5b89\u5168\u6c14\u56ca", airbag_payoff_col: 75000.0}])
        airbag_out = self.app.adjust_structure_daily_view_columns(airbag_view)
        self.assertIn(airbag_payoff_col, airbag_out.columns)

    def test_report_status_is_finished_does_not_misclassify_unexercised_vanilla(self) -> None:
        self.assertFalse(self.app.report_status_is_finished("存续中-卖出看跌", "未行权"))
        self.assertTrue(self.app.report_status_is_finished("到期结束-虚值卖出看跌", "未行权"))
        self.assertTrue(self.app.report_status_is_finished("到期结束-实值卖出看跌", "行权"))

    def test_normalize_structure_status_drives_finished_judgement(self) -> None:
        vanilla_active = self.app.normalize_structure_status("存续中-卖出看跌")
        vanilla_expired = self.app.normalize_structure_status("到期结束-虚值卖出看跌")
        phoenix_expired = self.app.normalize_structure_status("maturity_end")
        airbag_expired = self.app.normalize_structure_status("未敲入到期保护")
        snowball_expired = self.app.normalize_structure_status("雪球到期已敲入")

        self.assertEqual(vanilla_active, "vanilla_active")
        self.assertFalse(
            self.app.report_status_is_finished(
                "存续中-卖出看跌",
                "未行权",
                normalized_status=vanilla_active,
            )
        )
        self.assertTrue(
            self.app.report_status_is_finished(
                "到期结束-虚值卖出看跌",
                "未行权",
                normalized_status=vanilla_expired,
            )
        )
        self.assertTrue(
            self.app.report_status_is_finished(
                "maturity_end",
                "到期结束",
                normalized_status=phoenix_expired,
            )
        )
        self.assertTrue(
            self.app.report_status_is_finished(
                "未敲入到期保护",
                "未敲入到期保护",
                normalized_status=airbag_expired,
            )
        )
        self.assertTrue(
            self.app.report_status_is_finished(
                "雪球到期已敲入",
                "雪球到期已敲入",
                normalized_status=snowball_expired,
            )
        )

    def test_build_melt_maps_cover_natural_expiry_and_preserve_labels(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    "structure_id": "V1",
                    "group_id": "G1",
                    "date": "2026-03-30",
                    "status": "未行权",
                    "raw_status": "到期结束-虚值卖出看跌",
                    "normalized_status": "vanilla_expired_otm",
                    "status_cn": "未行权",
                },
                {
                    "structure_id": "P1",
                    "group_id": "G1",
                    "date": "2026-03-30",
                    "status": "到期结束",
                    "raw_status": "maturity_end",
                    "normalized_status": "phoenix_maturity_end",
                    "status_cn": "到期结束",
                },
                {
                    "structure_id": "A1",
                    "group_id": "G1",
                    "date": "2026-03-30",
                    "status": "未敲入到期保护",
                    "raw_status": "未敲入到期保护",
                    "normalized_status": "airbag_maturity_protect",
                    "status_cn": "未敲入到期保护",
                },
                {
                    "structure_id": "S1",
                    "group_id": "G1",
                    "date": "2026-03-30",
                    "status": "雪球到期已敲入",
                    "raw_status": "雪球到期已敲入",
                    "normalized_status": "snowball_maturity_loss",
                    "status_cn": "雪球到期已敲入",
                },
                {
                    "structure_id": "X1",
                    "group_id": "G1",
                    "date": "2026-03-30",
                    "status": "未行权",
                    "raw_status": "存续中-卖出看跌",
                    "normalized_status": "vanilla_active",
                    "status_cn": "未行权",
                },
            ]
        )

        melt_date_map = self.app.build_melt_date_map(rows, group_id="G1", as_of_date=self.app.parse_date_maybe("2026-03-30"))
        melt_status_map = self.app.build_melt_status_map(rows, group_id="G1", as_of_date=self.app.parse_date_maybe("2026-03-30"))

        self.assertEqual(set(melt_date_map.keys()), {"V1", "P1", "A1", "S1"})
        self.assertEqual(melt_status_map["V1"], "未行权")
        self.assertEqual(melt_status_map["P1"], "到期结束")
        self.assertEqual(melt_status_map["A1"], "未敲入到期保护")
        self.assertEqual(melt_status_map["S1"], "雪球到期已敲入")

    def test_report_monitor_snowball_coupon_value_prefers_cumulative_coupon(self) -> None:
        self.assertEqual(
            self.app.report_monitor_snowball_coupon_value(
                {"snowball_coupon_cum_pnl": 128.5, "snowball_coupon_float_pnl": 0.0}
            ),
            128.5,
        )
        self.assertEqual(
            self.app.report_monitor_snowball_coupon_value(
                {"snowball_coupon_float_pnl": 88.0}
            ),
            88.0,
        )

    def test_pick_first_text_skips_blank_strings(self) -> None:
        self.assertEqual(self.app.pick_first_text("", "2026-04-27", default="-"), "2026-04-27")
        self.assertEqual(self.app.pick_first_text(None, "  ", "2026-04-13", default="-"), "2026-04-13")

    def test_try_set_app_kv_returns_false_when_database_is_locked(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = pathlib.Path(tmpdir) / "prefs_locked.db"
            conn1 = sqlite3.connect(str(db_path), timeout=0.1)
            conn2 = sqlite3.connect(str(db_path), timeout=0.1)
            try:
                self.app.init_db(conn1)
                conn1.execute("BEGIN IMMEDIATE")
                saved = self.app.try_set_app_kv(conn2, self.app.UI_COMPACT_MODE_KV_KEY, "1")
                self.assertFalse(saved)
            finally:
                try:
                    conn1.rollback()
                except Exception:
                    pass
                conn1.close()
                conn2.close()

    def test_run_core_syncs_if_needed_skips_when_process_token_already_seen(self) -> None:
        self.app.st.session_state.clear()
        conn = mock.Mock()
        ledger_cache = {"hot": 1}
        with (
            mock.patch.object(self.app, "_CORE_SYNC_LAST_TOKEN_PROCESS", (7, 9)),
            mock.patch.object(self.app, "_LEDGER_MEMO_CACHE", ledger_cache),
            mock.patch.object(self.app, "_SPECIAL_SNAPSHOT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_SPECIAL_PAGE_UI_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_SPECIAL_PAGE_PREWARM_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_PROBEXP_MC_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_MC_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_HISTORY_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_ACC_HISTORY_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_db_file_version_token", return_value=(7, 9)),
            mock.patch.object(self.app, "cleanup_orphan_structure_link_records") as cleanup_mock,
            mock.patch.object(self.app, "sync_fixed_subsidy_close_records") as subsidy_mock,
            mock.patch.object(self.app, "sync_snowball_conversion_records") as snowball_mock,
        ):
            self.app._run_core_syncs_if_needed(conn)

            self.assertEqual(self.app.st.session_state.get("_core_sync_last_token"), (7, 9))
            self.assertEqual(ledger_cache, {"hot": 1})
            cleanup_mock.assert_not_called()
            subsidy_mock.assert_not_called()
            snowball_mock.assert_not_called()

    def test_run_core_syncs_if_needed_runs_once_per_db_token(self) -> None:
        self.app.st.session_state.clear()
        conn = mock.Mock()
        ledger_cache = {"hot": 1}
        with (
            mock.patch.object(self.app, "_CORE_SYNC_LAST_TOKEN_PROCESS", None),
            mock.patch.object(self.app, "_LEDGER_MEMO_CACHE", ledger_cache),
            mock.patch.object(self.app, "_SPECIAL_SNAPSHOT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_SPECIAL_PAGE_UI_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_SPECIAL_PAGE_PREWARM_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_PROBEXP_MC_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_MC_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_HISTORY_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_ACC_HISTORY_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_db_file_version_token", side_effect=[(10, 1), (11, 1), (11, 1)]),
            mock.patch.object(self.app, "cleanup_orphan_structure_link_records") as cleanup_mock,
            mock.patch.object(self.app, "sync_fixed_subsidy_close_records") as subsidy_mock,
            mock.patch.object(self.app, "sync_vanilla_maturity_records") as vanilla_maturity_mock,
            mock.patch.object(self.app, "sync_snowball_conversion_records") as snowball_mock,
        ):
            self.app._run_core_syncs_if_needed(conn)

            self.assertEqual(self.app.st.session_state.get("_core_sync_last_token"), (11, 1))
            self.assertEqual(self.app._CORE_SYNC_LAST_TOKEN_PROCESS, (11, 1))
            self.assertEqual(ledger_cache, {})

            ledger_cache["keep"] = 1
            self.app._run_core_syncs_if_needed(conn)

            cleanup_mock.assert_called_once_with(conn, manage_tx=True)
            subsidy_mock.assert_called_once_with(conn)
            vanilla_maturity_mock.assert_called_once_with(conn)
            snowball_mock.assert_called_once_with(conn)
            self.assertEqual(ledger_cache, {"keep": 1})

    def test_run_core_syncs_if_needed_warns_and_rolls_back_on_locked_db(self) -> None:
        self.app.st.session_state.clear()
        conn = mock.Mock()
        with (
            mock.patch.object(self.app, "_CORE_SYNC_LAST_TOKEN_PROCESS", None),
            mock.patch.object(self.app, "_LEDGER_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_SPECIAL_SNAPSHOT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_SPECIAL_PAGE_UI_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_SPECIAL_PAGE_PREWARM_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_PROBEXP_MC_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_MC_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_HISTORY_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_WINRATE_ACC_HISTORY_RESULT_MEMO_CACHE", {"hot": 1}),
            mock.patch.object(self.app, "_db_file_version_token", return_value=(20, 1)),
            mock.patch.object(
                self.app,
                "cleanup_orphan_structure_link_records",
                side_effect=sqlite3.OperationalError("database is locked"),
            ) as cleanup_mock,
            mock.patch.object(self.app, "sync_fixed_subsidy_close_records") as subsidy_mock,
            mock.patch.object(self.app, "sync_vanilla_maturity_records") as vanilla_maturity_mock,
            mock.patch.object(self.app, "sync_snowball_conversion_records") as snowball_mock,
            mock.patch.object(self.app.st, "warning") as warning_mock,
        ):
            self.app._run_core_syncs_if_needed(conn)

        cleanup_mock.assert_called_once_with(conn, manage_tx=True)
        subsidy_mock.assert_not_called()
        vanilla_maturity_mock.assert_not_called()
        snowball_mock.assert_not_called()
        conn.rollback.assert_called_once_with()
        warning_mock.assert_called_once()
        self.assertIsNone(self.app.st.session_state.get("_core_sync_last_token"))
        self.assertIsNone(self.app._CORE_SYNC_LAST_TOKEN_PROCESS)

    def test_build_cumulative_monitor_detail_meta_for_vanilla_matches_standard_two_line_style(self) -> None:
        detail_meta = self.app.build_cumulative_monitor_detail_meta(
            structure_id="S068",
            strategy_value=self.app.VANILLA_OPTION_CODE,
            kind_value="DEC",
            fallback_name="香草期权-看跌卖出-铁矿石",
            risk_party="海证资本",
            entry_price=800.0,
            strike_price=780.0,
        )
        self.assertEqual(detail_meta["line1"], "S068-卖出看跌-海证资本")
        self.assertEqual(detail_meta["line2"], "入场价（800.0）-行权价（780.0）-初始虚实（20.0）")
        self.assertEqual(detail_meta["rich_lines"][1][0]["text"], "入场价（800.0）-行权价（780.0）-初始虚实（20.0）")

    def test_build_cumulative_monitor_detail_meta_for_vanilla_call_initial_moneyness(self) -> None:
        detail_meta = self.app.build_cumulative_monitor_detail_meta(
            structure_id="S002",
            strategy_value=self.app.VANILLA_OPTION_CODE,
            kind_value="DEC",
            fallback_name="卖出看涨",
            risk_party="海证资本",
            entry_price=775.0,
            strike_price=800.0,
            option_type="call",
        )

        self.assertEqual(detail_meta["line1"], "S002-卖出看涨-海证资本")
        self.assertEqual(detail_meta["line2"], "入场价（775.0）-行权价（800.0）-初始虚实（25.0）")

    def test_build_cumulative_monitor_detail_meta_can_hide_risk_party_name(self) -> None:
        detail_meta = self.app.build_cumulative_monitor_detail_meta(
            structure_id="S068",
            strategy_value=self.app.VANILLA_OPTION_CODE,
            kind_value="DEC",
            fallback_name="香草期权-看跌卖出-铁矿石",
            risk_party="海证资本",
            entry_price=800.0,
            strike_price=780.0,
            hide_risk_party=True,
        )
        self.assertEqual(detail_meta["line1"], "S068-卖出看跌")
        self.assertNotIn("海证资本", detail_meta["line1"])
        self.assertEqual(detail_meta["line2"], "入场价（800.0）-行权价（780.0）-初始虚实（20.0）")

    def test_structure_detail_label_unified_appends_note_to_risk_party(self) -> None:
        detail_label = self.app.structure_detail_label_unified(
            structure_id="S022",
            strategy_value="BASIC_RANGE",
            kind_value="ACC",
            fallback_name="普通累计",
            risk_party="海证资本",
            note="测试期权",
            entry_price=815.5,
            strike_price=815.5,
            barrier_price=835.0,
        )

        self.assertIn("海证资本（测试期权）", detail_label)

    def test_build_cumulative_monitor_detail_meta_appends_note_to_risk_party(self) -> None:
        detail_meta = self.app.build_cumulative_monitor_detail_meta(
            structure_id="S022",
            strategy_value="BASIC_RANGE",
            kind_value="ACC",
            fallback_name="普通累计",
            risk_party="海证资本",
            note="测试期权",
            entry_price=815.5,
            strike_price=815.5,
            barrier_price=835.0,
        )

        self.assertEqual(detail_meta["line1"], "S022-普通累购-海证资本（测试期权）")

    def test_build_cumulative_report_line2_segments_highlights_strike_price_only(self) -> None:
        segments = self.app.build_cumulative_report_line2_segments(
            "障碍价（757.00）-入场价（776.00）-行权价（796.00）"
        )

        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0]["text"], "障碍价（757.00）-入场价（776.00）-")
        self.assertEqual(segments[0]["weight"], "normal")
        self.assertNotIn("color", segments[0])
        self.assertEqual(segments[1]["text"], "行权价（796.00）")
        self.assertEqual(segments[1]["weight"], "bold")
        self.assertEqual(segments[1]["color"], "#ff7f79")

    def test_structure_display_configs_use_two_decimal_precision(self) -> None:
        monitor_cfg = self.app.monitor_tab1_column_config()
        snowball_cfg = self.app.monitor_tab2_column_config()
        editor_cfg = self.app.build_structure_editor_column_config(pd.DataFrame(columns=["参与率（%）"]), [])

        self.assertEqual(monitor_cfg["当前票息(%)"]["type_config"]["format"], "%.2f")
        self.assertEqual(snowball_cfg["雪球当前票息(%)"]["type_config"]["format"], "%.2f")
        self.assertEqual(editor_cfg["入场价"]["type_config"]["format"], "%.2f")
        self.assertEqual(editor_cfg["敲入价"]["type_config"]["format"], "%.2f")
        self.assertEqual(editor_cfg["期权费"]["type_config"]["format"], "%.2f")
        self.assertEqual(editor_cfg["参与率（%）"]["type_config"]["format"], "%.2f")
        self.assertNotIn("客户名称", editor_cfg)
        self.assertNotIn("交易对手", editor_cfg)
        self.assertNotIn("交易日期", editor_cfg)
        self.assertNotIn("合约/月份", editor_cfg)
        self.assertIn("备注", editor_cfg)

    def test_structure_editor_column_order_hides_source_sid_and_moves_delete_first(self) -> None:
        show = pd.DataFrame(
            columns=["__源结构编号", "结构编号", "到期日", "交易日数量", "总量（吨）", "入场价", "删除"]
        )

        column_order = self.app.build_structure_editor_column_order(show)

        self.assertNotIn("__源结构编号", column_order)
        self.assertNotIn("到期日", column_order)
        self.assertEqual(column_order[0], "删除")
        self.assertLess(column_order.index("交易日数量"), column_order.index("总量（吨）"))

    def test_hide_empty_structure_editor_columns_keeps_note_column_for_later_edit(self) -> None:
        show = pd.DataFrame(
            [
                {
                    "\u7ed3\u6784\u7f16\u53f7": "S022",
                    "\u7ed3\u6784": "S022-\u666e\u901a\u7d2f\u8d2d-\u6d77\u8bc1\u8d44\u672c",
                    "\u98ce\u9669\u5b50": "\u6d77\u8bc1\u8d44\u672c",
                    "\u5907\u6ce8": "",
                    "\u65b9\u5411": "\u770b\u6da8",
                    "\u7b56\u7565\u7c7b\u578b": "\u666e\u901a\u7d2f\u8d2d",
                    "\u54c1\u79cd": "I2605",
                    "\u5f00\u59cb\u65e5\u671f": "2026-04-19",
                    "\u7ed3\u675f\u65e5\u671f": "2026-05-20",
                    "\u4ea4\u6613\u65e5\u6570\u91cf": 20,
                    "\u540d\u4e49\u89c4\u6a21\uff08\u5428\uff09": 1000.0,
                    "\u53c2\u4e0e\u500d\u6570": 3.0,
                    "\u5220\u9664": False,
                }
            ]
        )

        kept = self.app.hide_empty_structure_editor_columns(show)

        self.assertIn("\u5907\u6ce8", kept.columns)

    def test_resolve_structure_trade_day_count_prefers_saved_value_then_dates(self) -> None:
        self.assertEqual(
            self.app.resolve_structure_trade_day_count("2026-04-07", "2026-04-10"),
            4,
        )
        self.assertEqual(
            self.app.resolve_structure_trade_day_count(
                "2026-04-07",
                "2026-04-10",
                params_value={"n_days": 6},
            ),
            6,
        )

    def test_resolve_structure_editor_schedule_updates_end_date_from_trade_days(self) -> None:
        start_s, end_s, n_days = self.app.resolve_structure_editor_schedule(
            start_date_value="2026-04-07",
            end_date_value="2026-04-10",
            trade_days_value=3,
            fallback_start_date="2026-04-07",
            fallback_end_date="2026-04-10",
            fallback_trade_days=4,
        )

        self.assertEqual(start_s, "2026-04-07")
        self.assertEqual(end_s, "2026-04-09")
        self.assertEqual(n_days, 3)

    def test_resolve_structure_editor_base_qty_supports_total_override_for_accumulator(self) -> None:
        base_qty = self.app.resolve_structure_editor_base_qty(
            "BASIC_RANGE",
            daily_qty_value=1300.0,
            total_qty_value=30000.0,
            trade_day_count=20,
            old_daily_qty=1300.0,
            old_total_qty=26000.0,
        )

        self.assertEqual(base_qty, 1500.0)

    def test_build_cumulative_monitor_detail_meta_for_snowball_uses_knock_in_price_tail(self) -> None:
        detail_meta = self.app.build_cumulative_monitor_detail_meta(
            structure_id="S070",
            strategy_value="SNOWBALL",
            kind_value="DEC",
            fallback_name="看跌雪球",
            risk_party="海证资本",
            entry_price=800.0,
            strike_price=800.0,
            knock_in_price=815.0,
            barrier_price=720.0,
        )
        self.assertEqual(detail_meta["line1"], "S070-看跌雪球-海证资本")
        self.assertEqual(detail_meta["line2"], "敲出价（720.0）-入场价（800.0）-敲入价（815.0）")

    def test_format_relative_weekday_date_text_supports_next_next_week(self) -> None:
        text = self.app.format_relative_weekday_date_text("2026-04-14", "2026-04-05")
        self.assertEqual(text, "下下周二 2026-04-14")

    def test_resolve_snowball_next_ko_observation_skips_locked_dates(self) -> None:
        resolved = {
            "strategy_code": "SNOWBALL",
            "kind": "DEC",
            "start_date": "2026-03-03",
            "end_date": "2026-04-28",
            "trade_date": "2026-03-03",
            "entry_price": 800.0,
            "knock_out_price": 720.0,
            "barrier_out": 720.0,
            "params": {
                "sb_term_unit": "WEEK",
                "sb_term_count": 8,
                "sb_ko_obs_freq": "WEEKLY",
                "sb_lock_enabled": True,
                "sb_lock_ko_obs": 2,
                "sb_ko_pct": 90.0,
                "sb_auto_stepdown": False,
            },
        }

        next_ko = self.app.resolve_snowball_next_ko_observation(resolved, as_of_date="2026-03-12")

        self.assertEqual(next_ko["date_text"], "2026-03-24")
        self.assertEqual(next_ko["display_text"], "下下周二 2026-03-24")

    def test_fixed_subsidy_uses_structure_specific_payout_label(self) -> None:
        self.assertEqual(self.app.subsidy_amount_display_label("FIXED_SUBSIDY"), "熔断赔付金额")
        self.assertEqual(self.app.subsidy_amount_display_label("RANGE_SUBSIDY"), "每吨补贴金额")
        self.assertEqual(self.app.subsidy_amount_display_label("MELT_RANGE_SUBSIDY"), "每吨补贴金额")

    def test_rename_subsidy_display_column_only_for_fixed_subsidy_views(self) -> None:
        fixed_only = pd.DataFrame(
            [
                {"策略类型": "固赔熔断累计", "每吨补贴金额": 0.0},
            ]
        )
        fixed_show = self.app.rename_subsidy_display_column(fixed_only, strategy_col="策略类型")
        self.assertIn("熔断赔付金额", fixed_show.columns)
        self.assertNotIn("每吨补贴金额", fixed_show.columns)

        mixed = pd.DataFrame(
            [
                {"策略类型": "固赔熔断累计", "每吨补贴金额": 0.0},
                {"策略类型": "区间补贴累计", "每吨补贴金额": 5.0},
            ]
        )
        mixed_show = self.app.rename_subsidy_display_column(mixed, strategy_col="策略类型")
        self.assertIn("每吨补贴金额", mixed_show.columns)
        self.assertNotIn("熔断赔付金额", mixed_show.columns)

    def test_hide_empty_structure_editor_columns_hides_none_only_columns(self) -> None:
        show = pd.DataFrame(
            [
                {
                    "__源结构编号": "S001",
                    "结构编号": "S001",
                    "结构": "S001-普通累计",
                    "方向": "看跌",
                    "策略类型": "普通累计",
                    "品种": "铁矿石",
                    "开始日期": "2026-04-01",
                    "结束日期": "2026-04-29",
                    "到期日": "2026-04-29",
                    "名义规模（吨）": 20000.0,
                    "入场价": 790.0,
                    "敲入给量口径": "None",
                    "熔断行权价": None,
                    "删除": False,
                },
                {
                    "__源结构编号": "S002",
                    "结构编号": "S002",
                    "结构": "S002-普通累计",
                    "方向": "看跌",
                    "策略类型": "普通累计",
                    "品种": "铁矿石",
                    "开始日期": "2026-04-02",
                    "结束日期": "2026-04-30",
                    "到期日": "2026-04-30",
                    "名义规模（吨）": 18000.0,
                    "入场价": 795.0,
                    "敲入给量口径": None,
                    "熔断行权价": pd.NA,
                    "删除": False,
                },
            ]
        )

        hidden = self.app.hide_empty_structure_editor_columns(show)

        self.assertIn("__源结构编号", hidden.columns)
        self.assertIn("结构编号", hidden.columns)
        self.assertIn("入场价", hidden.columns)
        self.assertNotIn("敲入给量口径", hidden.columns)
        self.assertNotIn("熔断行权价", hidden.columns)

    def test_apply_structure_editor_filters_keeps_zero_value_columns_visible(self) -> None:
        show = pd.DataFrame(
            [
                {
                    "__源结构编号": "S001",
                    "结构编号": "S001",
                    "结构": "S001-固赔熔断累计",
                    "风险子": "海证资本",
                    "方向": "看跌",
                    "策略类型": "固赔熔断累计",
                    "品种": "铁矿石",
                    "开始日期": "2026-04-01",
                    "结束日期": "2026-04-29",
                    "到期日": "2026-04-29",
                    "总量（吨）": 40000.0,
                    "名义规模（吨）": 20000.0,
                    "入场价": 790.0,
                    "行权价": 825.0,
                    "熔断赔付金额": 0.0,
                    "敲入给量口径": None,
                    "删除": False,
                },
                {
                    "__源结构编号": "S002",
                    "结构编号": "S002",
                    "结构": "S002-固赔熔断累计",
                    "风险子": "海证资本",
                    "方向": "看跌",
                    "策略类型": "固赔熔断累计",
                    "品种": "铁矿石",
                    "开始日期": "2026-04-02",
                    "结束日期": "2026-04-30",
                    "到期日": "2026-04-30",
                    "总量（吨）": 36000.0,
                    "名义规模（吨）": 18000.0,
                    "入场价": 792.0,
                    "行权价": 826.0,
                    "熔断赔付金额": 0.0,
                    "敲入给量口径": "None",
                    "删除": False,
                },
            ]
        )

        with mock.patch.object(self.app, "apply_table_filters", side_effect=lambda df, *args, **kwargs: df):
            filtered = self.app.apply_structure_editor_filters(
                show,
                gid="G001",
                show_has_airbag=False,
                show_only_airbag=False,
            )

        self.assertIn("熔断赔付金额", filtered.columns)
        self.assertIn("总量（吨）", filtered.columns)
        self.assertNotIn("敲入给量口径", filtered.columns)

    def test_reorder_quote_price_fields_for_accumulator_uses_kind_specific_price_order(self) -> None:
        self.assertEqual(
            self.app.reorder_quote_price_fields_for_display(
                "BASIC_RANGE",
                "ACC",
                ["entry_price", "strike_price", "knock_out_price", "multiple"],
            ),
            ["knock_out_price", "entry_price", "strike_price", "multiple"],
        )
        self.assertEqual(
            self.app.reorder_quote_price_fields_for_display(
                "RANGE_SUBSIDY",
                "ACC",
                ["entry_price", "strike_price", "barrier_out", "multiple", "subsidy_per_ton"],
            ),
            ["barrier_out", "entry_price", "strike_price", "multiple", "subsidy_per_ton"],
        )
        self.assertEqual(
            self.app.reorder_quote_price_fields_for_display(
                "MELT_RANGE_SUBSIDY",
                "ACC",
                ["entry_price", "strike_price", "knock_out_price", "multiple", "subsidy_per_ton"],
            ),
            ["knock_out_price", "entry_price", "strike_price", "multiple", "subsidy_per_ton"],
        )
        self.assertEqual(
            self.app.reorder_quote_price_fields_for_display(
                "BASIC_RANGE",
                "DEC",
                ["entry_price", "strike_price", "knock_out_price", "multiple"],
            ),
            ["strike_price", "entry_price", "knock_out_price", "multiple"],
        )
        self.assertEqual(
            self.app.reorder_quote_price_fields_for_display(
                "FIXED_SUBSIDY",
                "DEC",
                ["entry_price", "strike_price", "barrier_out", "multiple", "subsidy_per_ton"],
            ),
            ["strike_price", "entry_price", "barrier_out", "multiple", "subsidy_per_ton"],
        )

    def test_build_structure_table_view_exposes_knock_in_price_column(self) -> None:
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "S070",
                    "name": "看跌雪球",
                    "underlying": "I2605",
                    "risk_party": "海证资本",
                    "kind": "DEC",
                    "strategy": "SNOWBALL",
                    "strategy_code": "SNOWBALL",
                    "contract_month": "",
                    "trade_date": None,
                    "start_date": "2026-03-30",
                    "end_date": "2026-04-27",
                    "expiry_date": None,
                    "base_qty_per_day": 0.0,
                    "entry_price": 800.0,
                    "barrier_in": 815.0,
                    "strike_price": 800.0,
                    "premium": None,
                    "barrier_out": 720.0,
                    "knock_out_price": 720.0,
                    "ko_strike_price": 800.0,
                    "multiple": 0.0,
                    "note": "",
                    "params_json": "{}",
                }
            ]
        )

        show = self.app.build_structure_table_view(structs_df)

        self.assertIn("敲入价", show.columns)
        self.assertEqual(float(show.loc[0, "敲入价"]), 815.0)

    def test_build_structure_table_view_shows_next_knock_out_day_for_snowball(self) -> None:
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "S070",
                    "group_id": "G1",
                    "name": "看跌雪球",
                    "underlying": "I2605",
                    "risk_party": "海证资本",
                    "kind": "DEC",
                    "strategy": "SNOWBALL",
                    "strategy_code": "SNOWBALL",
                    "contract_month": "",
                    "trade_date": None,
                    "start_date": "2026-03-17",
                    "end_date": "2026-04-28",
                    "expiry_date": None,
                    "base_qty_per_day": 0.0,
                    "entry_price": 800.0,
                    "barrier_in": 815.0,
                    "strike_price": 800.0,
                    "premium": None,
                    "barrier_out": 720.0,
                    "knock_out_price": 720.0,
                    "ko_strike_price": 800.0,
                    "multiple": 0.0,
                    "note": "",
                    "params_json": json.dumps(
                        {
                            "sb_term_unit": "WEEK",
                            "sb_term_count": 6,
                            "sb_ko_obs_freq": "WEEKLY",
                            "sb_ko_pct": 90.0,
                        },
                        ensure_ascii=False,
                    ),
                    "meta_json": "{}",
                }
            ]
        )

        show = self.app.build_structure_table_view(structs_df, as_of_date="2026-04-05")

        self.assertEqual(show.loc[0, "下次敲出日"], "下周二 2026-04-07")
        self.assertTrue(pd.isna(show.loc[0, "障碍价"]))
        self.assertEqual(float(show.loc[0, "敲出价"]), 720.0)

    def test_build_monitor_overview_frame_cached_includes_next_knock_out_day(self) -> None:
        bounds_df = pd.DataFrame(
            [
                {
                    "level": "STRUCTURE",
                    "structure_id": "S070",
                    "name": "看跌雪球",
                    "underlying": "I2605",
                    "kind": "DEC",
                    "strategy_code": "SNOWBALL",
                    "observed_generated_qty": 0.0,
                    "remaining_max_qty": 0.0,
                    "exposure_max_qty": 0.0,
                    "remaining_trading_days": 12,
                }
            ]
        )

        overview = self.app.build_monitor_overview_frame_cached(
            bounds_df,
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-04-05",
            manual_closed_sids=[],
            structure_code_map={"S070": "S070"},
            sid_direction_display_map={"S070": "看跌"},
            sid_buy_sell_direction_map={"S070": ""},
            sid_risk_party_map={"S070": "海证资本"},
            sid_strategy_code_map={"S070": "SNOWBALL"},
            sid_structure_detail_label_map={"S070": "S070-看跌雪球-海证资本"},
            sid_is_snowball_map={"S070": True},
            sid_snowball_discount_enabled_map={"S070": False},
            sid_snowball_next_ko_text_map={"S070": "下周二 2026-04-07"},
            struct_scale_map_overview={"S070": "500.00 万名义本金"},
            struct_end_date_map_overview={"S070": "2026-04-28"},
            rep_state_map={"S070": "雪球观察中"},
            rep_snowball_coupon_pct_map={"S070": 10.0},
            sb_phase_map={"S070": "单阶段"},
            sb_ko_line_map={"S070": 720.0},
            current_float_map={"S070": 1000.0},
            sb_knocked_in_map={"S070": 0},
            sb_first_ki_map={"S070": ""},
            sb_discount_map={"S070": ""},
            sb_convert_qty_map={"S070": 0.0},
            sb_convert_px_map={"S070": 0.0},
            sb_fut_float_map={"S070": 0.0},
            finished_sid_set=[],
        )

        self.assertIn("下次敲出日", overview.columns)
        self.assertEqual(overview.loc[0, "下次敲出日"], "下周二 2026-04-07")

    def test_compute_price_gap_table_keeps_vanilla_remaining_scale_at_signed_notional(self) -> None:
        structs = pd.DataFrame(
            [
                {
                    "structure_id": "V_DEC",
                    "structure_code": "S001",
                    "group_id": "G003",
                    "name": "卖出看涨",
                    "underlying": "I2609",
                    "risk_party": "海证资本",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "start_date": "2026-04-16",
                    "end_date": "2026-05-11",
                    "base_qty_per_day": 50000.0,
                    "entry_price": 775.0,
                    "strike_price": 800.0,
                    "premium": 3.8,
                    "option_type": "call",
                    "side": "sell",
                    "params_json": "{}",
                    "meta_json": "{}",
                },
                {
                    "structure_id": "V_ACC",
                    "structure_code": "S004",
                    "group_id": "G003",
                    "name": "买入看跌",
                    "underlying": "I2609",
                    "risk_party": "中证资本",
                    "kind": "ACC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "start_date": "2026-04-16",
                    "end_date": "2026-08-18",
                    "base_qty_per_day": 50000.0,
                    "entry_price": 780.0,
                    "strike_price": 743.0,
                    "premium": 20.55,
                    "option_type": "put",
                    "side": "buy",
                    "params_json": "{}",
                    "meta_json": "{}",
                },
            ]
        )
        prices = pd.DataFrame(
            [
                {"dt": "2026-04-16", "underlying": "I2609", "settle": 780.0},
            ]
        )

        out = self.app.compute_price_gap_table(
            structs,
            prices,
            as_of_date="2026-04-16",
        )
        scale_map = dict(zip(out["结构ID"], out["剩余震荡最大头寸规模"]))
        min_scale_map = dict(zip(out["结构ID"], out["剩余震荡最小头寸规模"]))

        self.assertEqual(float(scale_map["V_DEC"]), -50000.0)
        self.assertEqual(float(min_scale_map["V_DEC"]), -50000.0)
        self.assertEqual(float(scale_map["V_ACC"]), 50000.0)
        self.assertEqual(float(min_scale_map["V_ACC"]), 50000.0)

    def test_report_monitor_vanilla_total_premium_value_uses_buy_sell_sign(self) -> None:
        sell_total = self.app.report_monitor_vanilla_total_premium_value(
            {
                "kind": "DEC",
                "buy_sell_side": "sell",
                "premium": 3.8,
                "display_slot_qty": -50000.0,
            }
        )
        buy_total = self.app.report_monitor_vanilla_total_premium_value(
            {
                "kind": "ACC",
                "buy_sell_side": "buy",
                "premium": 20.55,
                "display_slot_qty": 50000.0,
            }
        )

        self.assertEqual(float(sell_total), 190000.0)
        self.assertEqual(float(buy_total), -1027500.0)

    def test_report_monitor_vanilla_roll_target_price_uses_call_put_formula(self) -> None:
        cases = [
            ({"option_type": "call", "side": "sell", "strike_price": 800.0, "premium": 3.8}, 803.8),
            ({"option_type": "call", "side": "buy", "strike_price": 800.0, "premium": 3.8}, 803.8),
            ({"option_type": "put", "side": "sell", "strike_price": 810.0, "premium": 20.55}, 789.45),
            ({"option_type": "put", "side": "buy", "strike_price": 743.0, "premium": 20.55}, 722.45),
        ]

        for item, expected in cases:
            with self.subTest(item=item):
                self.assertAlmostEqual(
                    float(self.app.report_monitor_vanilla_roll_target_price_value(item)),
                    expected,
                    places=8,
                )

    def test_merge_vanilla_editor_params_preserves_metadata_and_table_columns(self) -> None:
        merged = self.app.merge_vanilla_editor_params(
            {
                "legacy_ext": "keep",
                "customer_name": "旧客户",
                "counterparty": "旧对手",
                "contract_month": "I2604",
                "note": "旧备注",
            },
            option_type="put",
            side="sell",
            premium=5.0,
            trade_date="2026-03-30",
            expiry_date="2026-04-27",
            customer_name="新客户",
            counterparty="新对手",
            contract_month="I2605",
            note="新备注",
        )
        self.assertEqual(merged["legacy_ext"], "keep")
        self.assertEqual(merged["customer_name"], "新客户")
        self.assertEqual(merged["counterparty"], "新对手")
        self.assertEqual(merged["contract_month"], "I2605")
        self.assertEqual(merged["note"], "新备注")

        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "V001",
                    "name": "卖出看跌",
                    "underlying": "I2605",
                    "risk_party": "海证资本",
                    "kind": "DEC",
                    "strategy": self.app.VANILLA_OPTION_CODE,
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "contract_month": "",
                    "trade_date": "",
                    "start_date": "2026-03-30",
                    "end_date": "2026-04-27",
                    "expiry_date": "",
                    "base_qty_per_day": 2000.0,
                    "entry_price": 820.0,
                    "barrier_in": None,
                    "strike_price": 785.0,
                    "premium": 5.0,
                    "barrier_out": None,
                    "knock_out_price": None,
                    "ko_strike_price": None,
                    "multiple": 1.0,
                    "note": "",
                    "params_json": json.dumps(merged, ensure_ascii=False),
                    "meta_json": "{}",
                }
            ]
        )

        show = self.app.build_structure_table_view(structs_df)
        self.assertEqual(str(show.loc[0, "开始日期"]), "2026-03-30")
        self.assertNotIn("客户名称", show.columns)
        self.assertNotIn("交易对手", show.columns)
        self.assertNotIn("交易日期", show.columns)
        self.assertNotIn("合约/月份", show.columns)
        self.assertIn("\u5907\u6ce8", show.columns)
        self.assertEqual(str(show.loc[0, "\u5907\u6ce8"]), "\u65b0\u5907\u6ce8")

    def test_build_structure_table_view_merges_legacy_trade_date_into_start_date(self) -> None:
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "V002",
                    "name": "卖出看跌",
                    "underlying": "I2605",
                    "risk_party": "海证资本",
                    "kind": "DEC",
                    "strategy": self.app.VANILLA_OPTION_CODE,
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "trade_date": "2026-03-30",
                    "start_date": "",
                    "end_date": "2026-04-27",
                    "expiry_date": "",
                    "base_qty_per_day": 2000.0,
                    "entry_price": 820.0,
                    "barrier_in": None,
                    "strike_price": 785.0,
                    "premium": 5.0,
                    "barrier_out": None,
                    "knock_out_price": None,
                    "ko_strike_price": None,
                    "multiple": 1.0,
                    "params_json": "{}",
                    "meta_json": "{}",
                }
            ]
        )

        show = self.app.build_structure_table_view(structs_df)
        self.assertEqual(str(show.loc[0, "开始日期"]), "2026-03-30")
        self.assertNotIn("交易日期", show.columns)

    def test_build_structure_table_view_includes_trade_day_count_column(self) -> None:
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "S071",
                    "name": "普通累沽",
                    "underlying": "I2605",
                    "risk_party": "海证资本",
                    "kind": "DEC",
                    "strategy": "BASIC_RANGE",
                    "strategy_code": "BASIC_RANGE",
                    "start_date": "2026-04-07",
                    "end_date": "2026-04-10",
                    "trade_date": "",
                    "expiry_date": "",
                    "base_qty_per_day": 1000.0,
                    "entry_price": 800.0,
                    "barrier_in": None,
                    "strike_price": 780.0,
                    "premium": None,
                    "barrier_out": 830.0,
                    "knock_out_price": 830.0,
                    "ko_strike_price": None,
                    "multiple": 3.0,
                    "params_json": json.dumps({"n_days": 6}, ensure_ascii=False),
                    "meta_json": "{}",
                }
            ]
        )

        show = self.app.build_structure_table_view(structs_df)

        self.assertIn("交易日数量", show.columns)
        self.assertEqual(int(show.loc[0, "交易日数量"]), 6)
        self.assertEqual(float(show.loc[0, "总量（吨）"]), 6000.0)

    def test_prepare_structure_editor_view_preserves_accumulator_total_when_airbag_present(self) -> None:
        show = pd.DataFrame(
            [
                {
                    "__源结构编号": "S051",
                    "结构编号": "S051",
                    "结构": "S051-安全气囊",
                    "风险子": "海证资本",
                    "方向": "看跌",
                    "策略类型": "安全气囊",
                    "品种": "I2605",
                    "开始日期": "2026-03-10",
                    "结束日期": "2026-04-14",
                    "到期日": "2026-04-14",
                    "交易日数量": 25,
                    "名义规模（吨）": 150000.0,
                    "总量（吨）": pd.NA,
                    "参与倍数": 55.0,
                    "删除": False,
                },
                {
                    "__源结构编号": "S056",
                    "结构编号": "S056",
                    "结构": "S056-普通累计",
                    "风险子": "海证资本",
                    "方向": "看跌",
                    "策略类型": "普通累计",
                    "品种": "I2605",
                    "开始日期": "2026-03-09",
                    "结束日期": "2026-04-03",
                    "到期日": "2026-04-03",
                    "交易日数量": 20,
                    "名义规模（吨）": 1300.0,
                    "总量（吨）": 26000.0,
                    "参与倍数": 3.0,
                    "删除": False,
                },
            ]
        )

        prepared, show_has_airbag, show_only_airbag = self.app.prepare_structure_editor_view(show)

        self.assertTrue(show_has_airbag)
        self.assertFalse(show_only_airbag)
        self.assertEqual(float(prepared.loc[prepared["结构编号"] == "S051", "总量（吨）"].iloc[0]), 150000.0)
        self.assertEqual(float(prepared.loc[prepared["结构编号"] == "S056", "总量（吨）"].iloc[0]), 26000.0)

    def test_special_snapshot_range_text_appends_remaining_days(self) -> None:
        text = self.app.special_snapshot_range_text(
            {
                "start_date": "2026-03-30",
                "end_date": "2026-04-27",
                "remaining_days": 20,
            }
        )
        self.assertEqual(text, "2026-03-30 -> 2026-04-27 / 剩余20天")

    def test_crimson_silver_quote_theme_is_available(self) -> None:
        self.assertEqual(
            self.app.STRUCT_QUOTE_THEME_OPTIONS["Crimson Silver 绯红银灰"],
            "crimson_silver_business",
        )
        png_bytes = self.app.render_structure_quote_image(
            {
                "quote_date": "2026-03-30",
                "strategy_cn": "普通累计",
                "strategy_code": "BASIC_RANGE",
                "kind_cn": "看跌",
                "underlying_name": "铁矿石",
                "underlying": "I2605",
                "start_date": "2026-03-30",
                "end_date": "2026-04-27",
                "n_days": 20,
                "base_qty": 1000.0,
                "total_scale": 20000.0,
                "entry_price": 815.0,
                "strike_price": 880.2,
                "knock_out_price": 880.2,
                "multiple": 3.0,
                "terminal_participation_rate": 0,
                "theme": "crimson_silver_business",
                "price_fields": ["knock_out_price", "entry_price", "strike_price", "multiple"],
            }
        )
        self.assertGreater(len(png_bytes), 0)

    def test_snowball_editor_roundtrip_preserves_and_updates_notional_scale(self) -> None:
        params = {
            "sb_notional_amount": 5_000_000.0,
            "sb_notional_wan": 500.0,
            "sb_term_unit": "WEEK",
            "sb_term_count": 8,
            "sb_ko_obs_freq": "WEEKLY",
        }
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "S070",
                    "name": "看跌雪球",
                    "underlying": "I2605",
                    "risk_party": "海证资本",
                    "kind": "DEC",
                    "strategy": "SNOWBALL",
                    "strategy_code": "SNOWBALL",
                    "contract_month": "",
                    "trade_date": None,
                    "start_date": "2026-03-30",
                    "end_date": "2026-04-27",
                    "expiry_date": None,
                    "base_qty_per_day": 0.0,
                    "entry_price": 800.0,
                    "barrier_in": 815.0,
                    "strike_price": 800.0,
                    "premium": None,
                    "barrier_out": 720.0,
                    "knock_out_price": 720.0,
                    "ko_strike_price": 800.0,
                    "multiple": 0.0,
                    "note": "",
                    "params_json": json.dumps(params, ensure_ascii=False),
                }
            ]
        )

        show = self.app.build_structure_table_view(structs_df)
        self.assertAlmostEqual(float(show.loc[0, "名义规模（吨）"]), 6250.0)

        unchanged = self.app.snowball_editor_merge_notional_params(
            json.dumps(params, ensure_ascii=False),
            display_qty=6250.0,
            old_display_qty=6250.0,
            entry_price=800.0,
        )
        self.assertEqual(unchanged, params)

        changed = self.app.snowball_editor_merge_notional_params(
            json.dumps(params, ensure_ascii=False),
            display_qty=7000.0,
            old_display_qty=6250.0,
            entry_price=800.0,
        )
        self.assertAlmostEqual(float(changed["sb_notional_amount"]), 5_600_000.0)
        self.assertAlmostEqual(float(changed["sb_notional_wan"]), 560.0)

        reopened_df = structs_df.copy()
        reopened_df.loc[0, "params_json"] = json.dumps(changed, ensure_ascii=False)
        reopened = self.app.build_structure_table_view(reopened_df)
        self.assertAlmostEqual(
            float(reopened.loc[0, "\u540d\u4e49\u89c4\u6a21\uff08\u5428\uff09"]),
            7000.0,
        )

