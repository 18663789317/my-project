import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


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
        self.assertEqual(detail_map["敲出行权价"], "108.00")
        self.assertEqual(detail_map["当前状态"], "敲出熔断-给量")
        self.assertEqual(detail_map["当前事件类型"], "knock_out_delivery_terminate")
        self.assertEqual(detail_map["当前给量方向"], "BUY")
        self.assertEqual(detail_map["当前终止原因"], "knock_out_delivery")

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

    def test_status_to_cn_for_phoenix_normal_subsidy(self) -> None:
        self.assertEqual(self.app.status_to_cn("normal_subsidy", 0.0, 1.0), "震荡获得补贴")
        self.assertEqual(self.app.status_to_cn("震荡获得补贴", 0.0, 0.0), "震荡获得补贴")


if __name__ == "__main__":
    unittest.main()
