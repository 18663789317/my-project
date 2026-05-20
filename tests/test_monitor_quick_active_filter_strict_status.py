import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_quick_active_filter_strict_status_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorQuickActiveFilterStrictStatusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_build_monitor_quick_filter_inactive_sid_block_keeps_retained_airbag_terminal_rows(self) -> None:
        inactive = self.app.build_monitor_quick_filter_inactive_sid_block(
            expired_sids=["AB_EXP", "ACC_EXP"],
            sid_strategy_code_map={
                "AB_EXP": "SAFETY_AIRBAG",
                "ACC_EXP": "BASIC_RANGE",
                "AB_ZERO": "SAFETY_AIRBAG",
                "AB_LINEAR": "SAFETY_AIRBAG",
                "AB_TERM": "SAFETY_AIRBAG",
                "ACC_TERM": "BASIC_RANGE",
                "AB_LIVE": "SAFETY_AIRBAG",
            },
            normalized_status_map={
                "AB_LINEAR": "airbag_knock_in_linear",
                "AB_TERM": "airbag_maturity_protect",
                "ACC_TERM": "accumulator_knock_out_terminate",
                "AB_LIVE": "airbag_observe",
            },
            remaining_days_map={
                "AB_ZERO": 0,
                "AB_LIVE": 3,
            },
        )

        self.assertEqual(
            inactive,
            {"ACC_EXP", "ACC_TERM"},
        )

    def test_monitor_overview_quick_filter_uses_internal_sid_after_display_code_mapping(self) -> None:
        overview = pd.DataFrame(
            [
                {
                    "__内部结构ID": "SID_FIN",
                    "结构ID": "S001",
                    "结构": "S001-已结束结构",
                    "状态": "熔断结束",
                    "剩余交易日": 0,
                    "剩余最大": 0.0,
                    "敞口上界": 0.0,
                },
                {
                    "__内部结构ID": "SID_LIVE",
                    "结构ID": "S002",
                    "结构": "S002-存续结构",
                    "状态": "震荡（1倍）",
                    "剩余交易日": 12,
                    "剩余最大": 2000.0,
                    "敞口上界": 4000.0,
                },
            ]
        )

        finalized = self.app.finalize_monitor_overview_frame(
            overview,
            structure_code_map={"SID_FIN": "S001", "SID_LIVE": "S002"},
            finished_sid_set={"SID_FIN"},
        )

        self.assertIn("__内部结构ID", finalized.columns)

        filtered = self.app.apply_quick_active_structure_filter(
            finalized,
            "仅存续结构",
            {"SID_FIN"},
            sid_col="结构ID",
        )

        self.assertEqual(filtered["结构ID"].astype(str).tolist(), ["S002"])
        self.assertEqual(filtered["__内部结构ID"].astype(str).tolist(), ["SID_LIVE"])

    def test_monitor_overview_cached_frame_recovers_internal_sid_from_display_code(self) -> None:
        cache_key = self.app._monitor_scope_cache_key(
            "monitor_overview",
            rep_gid="G001",
            rep_und="I2609",
            rep_date="2026-04-17",
        )
        self.app._MONITOR_UI_MEMO_CACHE[cache_key] = pd.DataFrame(
            [
                {
                    "结构ID": "S001",
                    "结构": "S001-已结束结构",
                    "状态": "熔断结束",
                    "剩余交易日": 0,
                }
            ]
        )

        try:
            recovered = self.app.build_monitor_overview_frame_cached(
                pd.DataFrame(),
                rep_gid="G001",
                rep_und="I2609",
                rep_date="2026-04-17",
                manual_closed_sids=[],
                structure_code_map={"SID_FIN": "S001"},
                sid_direction_display_map={},
                sid_buy_sell_direction_map={},
                sid_risk_party_map={},
                sid_strategy_code_map={},
                sid_structure_detail_label_map={},
                sid_is_snowball_map={},
                sid_snowball_discount_enabled_map={},
                sid_snowball_next_ko_text_map={},
                struct_scale_map_overview={},
                struct_end_date_map_overview={},
                rep_state_map={},
                rep_snowball_coupon_pct_map={},
                sb_phase_map={},
                sb_ko_line_map={},
                current_float_map={},
                sb_knocked_in_map={},
                sb_first_ki_map={},
                sb_discount_map={},
                sb_convert_qty_map={},
                sb_convert_px_map={},
                sb_fut_float_map={},
                finished_sid_set=set(),
            )
        finally:
            self.app._MONITOR_UI_MEMO_CACHE.pop(cache_key, None)

        self.assertEqual(recovered["__内部结构ID"].astype(str).tolist(), ["SID_FIN"])


if __name__ == "__main__":
    unittest.main()
