import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_manual_close_scale_picker_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ManualCloseStructureScalePickerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_build_resolved_structure_scale_maps_uses_structure_scale_instead_of_open_position_qty(self) -> None:
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "S060",
                    "group_id": "G1",
                    "name": "普通累沽",
                    "underlying": "I2605",
                    "risk_party": "华泰长城",
                    "kind": "DEC",
                    "strategy": "BASIC_RANGE",
                    "strategy_code": "BASIC_RANGE",
                    "start_date": "2026-04-13",
                    "end_date": "2026-04-17",
                    "base_qty_per_day": 5200.0,
                    "entry_price": 776.0,
                    "strike_price": 796.0,
                    "params_json": "{}",
                    "meta_json": "{}",
                },
                {
                    "structure_id": "S058",
                    "group_id": "G1",
                    "name": "普通累沽",
                    "underlying": "I2605",
                    "risk_party": "东海资本",
                    "kind": "DEC",
                    "strategy": "BASIC_RANGE",
                    "strategy_code": "BASIC_RANGE",
                    "start_date": "2026-04-13",
                    "end_date": "2026-04-17",
                    "base_qty_per_day": 7800.0,
                    "entry_price": 776.0,
                    "strike_price": 797.0,
                    "params_json": "{}",
                    "meta_json": "{}",
                },
            ]
        )

        resolved_map, scale_text_map, scale_sort_map = self.app.build_resolved_structure_scale_maps(structs_df)

        self.assertEqual(set(resolved_map.keys()), {"S060", "S058"})
        self.assertEqual(scale_text_map["S060"], "26,000.00 吨")
        self.assertEqual(scale_text_map["S058"], "39,000.00 吨")
        self.assertAlmostEqual(float(scale_sort_map["S060"]), 26000.0)
        self.assertAlmostEqual(float(scale_sort_map["S058"]), 39000.0)
        ordered = sorted(
            ["S060", "S058"],
            key=lambda sid: (-float(scale_sort_map.get(str(sid), 0.0)), str(sid)),
        )
        self.assertEqual(ordered, ["S058", "S060"])

    def test_build_resolved_structure_scale_maps_supports_manual_structure_reduction(self) -> None:
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "S058",
                    "group_id": "G1",
                    "name": "普通累沽",
                    "underlying": "I2605",
                    "risk_party": "东海资本",
                    "kind": "DEC",
                    "strategy": "BASIC_RANGE",
                    "strategy_code": "BASIC_RANGE",
                    "start_date": "2026-04-13",
                    "end_date": "2026-04-17",
                    "base_qty_per_day": 7800.0,
                    "entry_price": 776.0,
                    "strike_price": 797.0,
                    "params_json": "{}",
                    "meta_json": "{}",
                }
            ]
        )

        resolved_map, scale_text_map, scale_sort_map = self.app.build_resolved_structure_scale_maps(
            structs_df,
            reduction_qty_map={"S058": 10000.0},
        )

        self.assertEqual(set(resolved_map.keys()), {"S058"})
        self.assertEqual(scale_text_map["S058"], "29,000.00 吨")
        self.assertAlmostEqual(float(scale_sort_map["S058"]), 29000.0)
        self.assertAlmostEqual(float(resolved_map["S058"]["base_qty_per_day"]), 5800.0)

    def test_build_structure_latest_status_display_map_marks_finished_rows(self) -> None:
        struct_df = pd.DataFrame(
            [
                {
                    "structure_id": "S060",
                    "group_id": "G1",
                    "date": "2026-04-14",
                    "status": "震荡",
                    "remaining_trading_days": 2,
                },
                {
                    "structure_id": "S081",
                    "group_id": "G1",
                    "date": "2026-04-14",
                    "status": "到期结束-虚值卖出",
                    "remaining_trading_days": 0,
                },
                {
                    "structure_id": "S999",
                    "group_id": "G2",
                    "date": "2026-04-14",
                    "status": "震荡",
                    "remaining_trading_days": 3,
                },
            ]
        )

        status_map = self.app.build_structure_latest_status_display_map(struct_df, group_id="G1")

        self.assertIn("震荡", status_map["S060"])
        self.assertEqual(status_map["S081"], "已结束")
        self.assertNotIn("S999", status_map)

    def test_build_structure_latest_status_display_map_respects_asof_date(self) -> None:
        struct_df = pd.DataFrame(
            [
                {
                    "structure_id": "S060",
                    "group_id": "G1",
                    "date": "2026-04-14",
                    "status": "闇囪崱",
                    "remaining_trading_days": 2,
                },
                {
                    "structure_id": "S060",
                    "group_id": "G1",
                    "date": "2026-04-15",
                    "status": "鍒版湡缁撴潫-铏氬€煎崠鍑?",
                    "remaining_trading_days": 0,
                },
            ]
        )

        status_map = self.app.build_structure_latest_status_display_map(
            struct_df,
            group_id="G1",
            as_of_date="2026-04-14",
        )
        latest_status_map = self.app.build_structure_latest_status_display_map(
            struct_df,
            group_id="G1",
        )

        self.assertIn("S060", status_map)
        self.assertNotEqual(status_map["S060"], "已结束")
        self.assertEqual(latest_status_map["S060"], "已结束")

    def test_manual_close_structure_option_label_uses_structure_scale_wording(self) -> None:
        resolved_row = {
            "structure_id": "S060",
            "name": "普通累沽",
            "risk_party": "华泰长城",
            "kind": "DEC",
            "underlying": "I2605",
            "strategy_code": "BASIC_RANGE",
            "entry_price": 776.0,
            "strike_price": 796.0,
            "barrier_in": None,
            "barrier_out": None,
        }

        label = self.app.manual_close_structure_option_label(
            "S060",
            resolved_row,
            scale_text="26,000.00 吨",
            terminated=True,
        )

        self.assertIn("结构规模 26,000.00 吨", label)
        self.assertIn("状态 已结束", label)
        self.assertNotIn("当前吨数", label)

    def test_manual_close_structure_option_label_shows_remaining_scale_when_partially_reduced(self) -> None:
        resolved_row = {
            "structure_id": "S081",
            "name": "看跌安全气囊",
            "risk_party": "海证资本",
            "kind": "DEC",
            "underlying": "I2605",
            "strategy_code": "SAFETY_AIRBAG",
            "entry_price": 780.0,
            "strike_price": 840.0,
            "barrier_in": None,
            "barrier_out": 840.0,
        }

        label = self.app.manual_close_structure_option_label(
            "S081",
            resolved_row,
            scale_text="20,000.00 吨",
            status_text="存续中",
            remaining_scale_text="19,000.00 吨",
        )

        scale_pos = label.find("结构规模 20,000.00 吨")
        status_pos = label.find("状态 存续中")
        remaining_pos = label.find("剩余 19,000.00 吨")
        self.assertGreaterEqual(scale_pos, 0)
        self.assertGreaterEqual(status_pos, 0)
        self.assertGreaterEqual(remaining_pos, 0)
        self.assertLess(scale_pos, status_pos)
        self.assertLess(status_pos, remaining_pos)

    def test_manual_close_structure_option_label_supports_custom_termination_label(self) -> None:
        resolved_row = {
            "structure_id": "S060",
            "name": "demo",
            "risk_party": "party",
            "kind": "DEC",
            "underlying": "I2605",
            "strategy_code": "BASIC_RANGE",
            "entry_price": 776.0,
            "strike_price": 796.0,
            "barrier_in": None,
            "barrier_out": None,
        }

        label = self.app.manual_close_structure_option_label(
            "S060",
            resolved_row,
            terminated=True,
            termination_label="\u5df2\u7194\u65ad\u6572\u51fa",
        )

        self.assertIn("\u72b6\u6001 \u5df2\u7194\u65ad\u6572\u51fa", label)
        self.assertNotIn("\u5df2\u7ec8\u6b62", label)


if __name__ == "__main__":
    unittest.main()
