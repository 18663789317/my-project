import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_finished_state_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorFinishedStateRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_override_finished_status_display_preserves_manual_and_melt_labels(self) -> None:
        self.assertEqual(
            self.app.override_finished_status_display("敲出熔断-给量", 0, strategy_value="PHOENIX_ACC_CALL_FIXED"),
            "熔断结束",
        )
        self.assertEqual(
            self.app.override_finished_status_display("已手动终结", 0),
            "已手动终结",
        )

    def test_override_finished_status_display_keeps_basic_accumulator_as_finished_only(self) -> None:
        self.assertEqual(
            self.app.override_finished_status_display("敲出熔断", 0, strategy_value="BASIC_RANGE"),
            "已结束",
        )
        self.assertEqual(
            self.app.override_finished_status_display("熔断结束", 0, strategy_value="BASIC_RANGE"),
            "已结束",
        )

    def test_sort_status_rows_finished_last_pushes_finished_rows_to_bottom(self) -> None:
        df = pd.DataFrame(
            [
                {"日期": "2026-04-09", "结构ID": "S_FIN_A", "状态": "熔断结束", "剩余交易日": 0},
                {"日期": "2026-04-09", "结构ID": "S_ACTIVE", "状态": "敲入（2倍）", "剩余交易日": 6},
                {"日期": "2026-04-09", "结构ID": "S_FIN_B", "状态": "已结束", "剩余交易日": 0},
            ]
        )

        ordered = self.app.sort_status_rows_finished_last(df, leading_sort_cols=["日期"])

        self.assertEqual(
            ordered["结构ID"].astype(str).tolist(),
            ["S_ACTIVE", "S_FIN_A", "S_FIN_B"],
        )

    def test_build_monitor_bounds_frame_cached_zeroes_finished_remaining_fields_and_group_rollup(self) -> None:
        bounds_df = pd.DataFrame(
            [
                {
                    "level": "STRUCTURE",
                    "group_id": "G1",
                    "structure_id": "S_ACTIVE",
                    "name": "A",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "strategy_code": "BASIC_RANGE",
                    "total_trading_days": 5,
                    "observed_trading_days": 1,
                    "remaining_trading_days": 4,
                    "observed_generated_qty": 1000.0,
                    "remaining_min_qty": 0.0,
                    "remaining_max_qty": 4000.0,
                    "exposure_min_qty": 1000.0,
                    "exposure_max_qty": 5000.0,
                },
                {
                    "level": "STRUCTURE",
                    "group_id": "G1",
                    "structure_id": "S_FIN",
                    "name": "B",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "strategy_code": "BASIC_RANGE",
                    "total_trading_days": 5,
                    "observed_trading_days": 5,
                    "remaining_trading_days": 0,
                    "observed_generated_qty": 2000.0,
                    "remaining_min_qty": 0.0,
                    "remaining_max_qty": 5000.0,
                    "exposure_min_qty": 2000.0,
                    "exposure_max_qty": 7000.0,
                },
                {
                    "level": "GROUP",
                    "group_id": "G1",
                    "structure_id": "",
                    "name": "G1",
                    "underlying": "I2605",
                    "kind": "",
                    "strategy_code": "",
                    "total_trading_days": 5,
                    "observed_trading_days": 5,
                    "remaining_trading_days": 0,
                    "observed_generated_qty": 0.0,
                    "remaining_min_qty": 0.0,
                    "remaining_max_qty": 0.0,
                    "exposure_min_qty": 0.0,
                    "exposure_max_qty": 0.0,
                },
            ]
        )

        out = self.app.build_monitor_bounds_frame_cached(
            bounds_df,
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-04-09",
            trs_sid_set_rep=set(),
            rep_open_qty_map={},
            gap_scope_min_map={},
            gap_scope_max_map={},
            gap_scope_days_map={},
            sid_direction_display_map={"S_ACTIVE": "看涨", "S_FIN": "看涨"},
            sid_structure_name_display_map={"S_ACTIVE": "普通累购", "S_FIN": "普通累购"},
            sid_risk_party_map={"S_ACTIVE": "海证资本", "S_FIN": "海证资本"},
            sid_structure_detail_label_map={"S_ACTIVE": "S_ACTIVE-A", "S_FIN": "S_FIN-B"},
            structure_code_map={"S_ACTIVE": "S_ACTIVE", "S_FIN": "S_FIN"},
            terminal_sid_set={"S_FIN"},
        )

        finished_row = out[(out["层级"].astype(str) == "STRUCTURE") & (out["结构ID"].astype(str) == "S_FIN")].iloc[0]
        group_row = out[out["层级"].astype(str) == "GROUP"].iloc[0]

        self.assertEqual(int(finished_row["剩余交易日"]), 0)
        self.assertEqual(float(finished_row["剩余最小"]), 0.0)
        self.assertEqual(float(finished_row["剩余最大"]), 0.0)
        self.assertEqual(float(group_row["剩余最大"]), 4000.0)


if __name__ == "__main__":
    unittest.main()
