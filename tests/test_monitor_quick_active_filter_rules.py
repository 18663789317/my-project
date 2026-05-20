import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_quick_active_filter_rules_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorQuickActiveFilterRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_active_monitor_keeps_airbag_terminal_statuses(self) -> None:
        kept_statuses = [
            "airbag_knock_in_linear",
            "airbag_maturity_up",
            "airbag_maturity_down",
            "airbag_maturity_protect",
        ]

        for status in kept_statuses:
            self.assertTrue(
                self.app.active_monitor_keeps_terminal_status("", normalized_status=status),
                msg=status,
            )
            self.assertFalse(
                self.app.structure_status_counts_as_inactive_for_active_monitor("", normalized_status=status),
                msg=status,
            )

    def test_active_monitor_still_excludes_non_airbag_terminal_statuses(self) -> None:
        excluded_statuses = [
            "accumulator_knock_out_terminate",
            "phoenix_maturity_end",
            "snowball_knock_out",
            "vanilla_expired_otm",
        ]

        for status in excluded_statuses:
            self.assertTrue(
                self.app.structure_status_counts_as_inactive_for_active_monitor("", normalized_status=status),
                msg=status,
            )

    def test_active_monitor_keeps_expired_airbag_strategy_only(self) -> None:
        self.assertTrue(self.app.active_monitor_keeps_expired_structure("SAFETY_AIRBAG"))
        self.assertFalse(self.app.active_monitor_keeps_expired_structure("BASIC_RANGE"))

    def test_build_monitor_inactive_sid_block_keeps_airbag_expiry_and_terminal_rows(self) -> None:
        inactive = self.app.build_monitor_inactive_sid_block(
            manual_closed_sids=["S_MANUAL"],
            melted_sids=["S_MELT"],
            expired_sids=["AB_EXP", "ACC_EXP"],
            sid_strategy_code_map={
                "AB_EXP": "SAFETY_AIRBAG",
                "ACC_EXP": "BASIC_RANGE",
            },
            normalized_status_map={
                "AB_LINEAR": "airbag_knock_in_linear",
                "AB_PROTECT": "airbag_maturity_protect",
                "SB_KO": "snowball_knock_out",
                "VAN_EX": "vanilla_expired_otm",
            },
        )

        self.assertEqual(
            inactive,
            {"S_MANUAL", "S_MELT", "ACC_EXP", "SB_KO", "VAN_EX"},
        )

    def test_build_monitor_inactive_sid_block_marks_zero_remaining_non_airbag_as_inactive(self) -> None:
        inactive = self.app.build_monitor_inactive_sid_block(
            sid_strategy_code_map={
                "AB_ZERO": "SAFETY_AIRBAG",
                "ACC_ZERO": "BASIC_RANGE",
                "SB_ZERO": "SNOWBALL",
            },
            remaining_days_map={
                "AB_ZERO": 0,
                "ACC_ZERO": 0,
                "SB_ZERO": -1,
                "ACC_LIVE": 2,
            },
        )

        self.assertEqual(inactive, {"ACC_ZERO", "SB_ZERO"})

    def test_finished_helpers_use_normalized_terminal_statuses(self) -> None:
        item = {
            "status_cn": "未敲入到期保护",
            "normalized_status": "airbag_maturity_protect",
        }
        self.assertTrue(self.app.report_monitor_item_is_finished(item))

        df = pd.DataFrame(
            [
                {
                    "结构ID": "AB_PROTECT",
                    "状态": "未敲入到期保护",
                    "normalized_status": "airbag_maturity_protect",
                    "剩余交易日": 3,
                },
                {
                    "结构ID": "AB_LIVE",
                    "状态": "未敲入观察",
                    "normalized_status": "airbag_observe",
                    "剩余交易日": 3,
                },
            ]
        )

        mask = self.app.build_finished_status_mask(df, status_col="状态", remaining_days_col="剩余交易日")
        self.assertEqual(mask.tolist(), [True, False])

    def test_filter_out_inactive_structures_prefers_internal_structure_id(self) -> None:
        df = pd.DataFrame(
            [
                {"结构ID": "S004", "__内部结构ID": "SID_FIN", "状态": "已结束"},
                {"结构ID": "S001", "__内部结构ID": "SID_LIVE", "状态": "震荡（1倍）"},
            ]
        )

        out = self.app.filter_out_inactive_structures(df, {"SID_FIN"}, sid_col="结构ID")

        self.assertEqual(out["结构ID"].tolist(), ["S001"])

    def test_build_active_risk_bounds_view_prefers_internal_structure_id(self) -> None:
        df = pd.DataFrame(
            [
                {"层级": "STRUCTURE", "结构ID": "S004", "__内部结构ID": "SID_FIN", "策略组编号": "G1", "品种": "I2605"},
                {"层级": "STRUCTURE", "结构ID": "S001", "__内部结构ID": "SID_LIVE", "策略组编号": "G1", "品种": "I2605"},
                {"层级": "GROUP", "结构ID": "GROUP_SUM", "策略组编号": "G1", "品种": "I2605"},
            ]
        )

        out = self.app.build_active_risk_bounds_view(df, {"SID_FIN"}, "G1", "I2605")

        struct_rows = out[out["层级"].astype(str) == "STRUCTURE"].copy()
        self.assertEqual(struct_rows["结构ID"].tolist(), ["S001"])


if __name__ == "__main__":
    unittest.main()
