import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_natural_maturity_close_detail_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NaturalMaturityCloseDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def _structs_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "structure_id": "S018",
                    "group_id": "G002",
                    "structure_code": "S018",
                    "name": "看跌安全气囊",
                    "risk_party": "华泰长城",
                    "note": "入场价（773.0）-障碍价（824.0）",
                    "kind": "DEC",
                    "underlying": "I2605",
                    "entry_price": 773.0,
                    "strike_price": 824.0,
                    "barrier_in": 824.0,
                    "barrier_out": None,
                    "strategy_code": "SAFETY_AIRBAG",
                    "strategy": "SAFETY_AIRBAG",
                }
            ]
        )

    def _groups_df(self) -> pd.DataFrame:
        return pd.DataFrame([{"group_id": "G002", "group_name": "铁矿05月份套保组", "underlying": "I2605"}])

    def test_natural_maturity_zero_pnl_is_added_to_close_detail(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-22",
                    "group_id": "G002",
                    "structure_id": "S018",
                    "name": "看跌安全气囊",
                    "underlying": "I2605",
                    "kind": "DEC",
                    "strategy_code": "SAFETY_AIRBAG",
                    "status": "未敲入观察",
                    "raw_status": "未敲入观察",
                    "normalized_status": "airbag_observe",
                    "generated_qty": 5000.0,
                    "cum_qty": 5000.0,
                    "entry_price": 773.0,
                    "strike_price": 824.0,
                    "gen_price": 773.0,
                    "settle": 805.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                },
                {
                    "date": "2026-04-23",
                    "group_id": "G002",
                    "structure_id": "S018",
                    "name": "看跌安全气囊",
                    "underlying": "I2605",
                    "kind": "DEC",
                    "strategy_code": "SAFETY_AIRBAG",
                    "status": "未敲入到期保护",
                    "raw_status": "未敲入到期保护",
                    "normalized_status": "airbag_maturity_protect",
                    "generated_qty": 0.0,
                    "cum_qty": 5000.0,
                    "entry_price": 773.0,
                    "strike_price": 824.0,
                    "gen_price": 773.0,
                    "settle": 807.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                }
            ]
        )

        detail = self.app.build_close_detail_table(
            close2_df=pd.DataFrame(),
            spot_match_df=pd.DataFrame(),
            rep_gid="G002",
            rep_und="I2605",
            rep_date="2026-04-23",
            group_name_map={"G002": "铁矿05月份套保组"},
            structs_df=self._structs_df(),
            groups_df=self._groups_df(),
            struct_daily_df=struct_daily,
        )

        self.assertEqual(len(detail), 1)
        row = detail.iloc[0]
        self.assertEqual(row["日期"], "2026-04-23")
        self.assertEqual(row["平仓类别"], self.app.NATURAL_MATURITY_CLOSE_CATEGORY)
        self.assertEqual(row["结构状态"], "未敲入到期保护")
        self.assertEqual(row["记录类型"], "自然到期记录")
        self.assertAlmostEqual(float(row["数量"]), 5000.0)
        self.assertAlmostEqual(float(row["平仓盈亏"]), 0.0)
        self.assertAlmostEqual(float(row["合计盈亏"]), 0.0)

        selected, metrics = self.app.build_close_selected_date_detail(detail, "2026-04-23")
        self.assertEqual(len(selected), 1)
        self.assertAlmostEqual(float(metrics["record_count"]), 1.0)
        self.assertAlmostEqual(float(metrics["qty_sum"]), 5000.0)

    def test_non_maturity_status_does_not_create_natural_close_detail(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-23",
                    "group_id": "G002",
                    "structure_id": "S018",
                    "underlying": "I2605",
                    "strategy_code": "SAFETY_AIRBAG",
                    "status": "未敲入观察",
                    "raw_status": "未敲入观察",
                    "normalized_status": "airbag_observe",
                }
            ]
        )

        detail = self.app.build_close_detail_table(
            close2_df=pd.DataFrame(),
            spot_match_df=pd.DataFrame(),
            rep_gid="G002",
            rep_und="I2605",
            rep_date="2026-04-23",
            group_name_map={"G002": "铁矿05月份套保组"},
            structs_df=self._structs_df(),
            groups_df=self._groups_df(),
            struct_daily_df=struct_daily,
        )

        self.assertTrue(detail.empty)

    def test_sold_call_vanilla_natural_maturity_uses_total_option_payoff(self) -> None:
        raw_status = "\u5230\u671f\u7ed3\u675f-\u5b9e\u503c\u5356\u51fa\u770b\u6da8"
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-05-11",
                    "group_id": "G003",
                    "structure_id": "V_CALL_SELL",
                    "structure_code": "S002",
                    "name": "\u5356\u51fa\u770b\u6da8",
                    "underlying": "I2609",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "status": "\u884c\u6743",
                    "status_cn": "\u884c\u6743",
                    "raw_status": raw_status,
                    "normalized_status": "vanilla_expired_itm",
                    "generated_qty": 0.0,
                    "entry_price": 775.0,
                    "strike_price": 800.0,
                    "premium": 3.8,
                    "option_type": "call",
                    "side": "sell",
                    "gen_price": 3.8,
                    "settle": 822.5,
                    "day_pnl": -400000.0,
                    "cum_pnl": -935000.0,
                    "day_subsidy_pnl": 0.0,
                }
            ]
        )
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "V_CALL_SELL",
                    "group_id": "G003",
                    "structure_code": "S002",
                    "name": "\u5356\u51fa\u770b\u6da8",
                    "risk_party": "\u6d77\u8bc1\u8d44\u672c",
                    "note": "",
                    "kind": "DEC",
                    "underlying": "I2609",
                    "start_date": "2026-04-16",
                    "end_date": "2026-05-11",
                    "base_qty_per_day": 50000.0,
                    "entry_price": 775.0,
                    "strike_price": 800.0,
                    "premium": 3.8,
                    "option_type": "call",
                    "side": "sell",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "strategy": self.app.VANILLA_OPTION_CODE,
                }
            ]
        )

        detail = self.app.build_close_detail_table(
            close2_df=pd.DataFrame(),
            spot_match_df=pd.DataFrame(),
            rep_gid="G003",
            rep_und="I2609",
            rep_date="2026-05-11",
            group_name_map={"G003": "Group"},
            structs_df=structs_df,
            groups_df=pd.DataFrame([{"group_id": "G003", "group_name": "Group", "underlying": "I2609"}]),
            struct_daily_df=struct_daily,
        )

        self.assertEqual(len(detail), 1)
        row = detail.iloc[0]
        self.assertEqual(row["\u65e5\u671f"], "2026-05-11")
        self.assertEqual(row["\u5e73\u4ed3\u7c7b\u522b"], self.app.NATURAL_MATURITY_CLOSE_CATEGORY)
        self.assertAlmostEqual(float(row["\u6570\u91cf"]), 50000.0)
        self.assertAlmostEqual(float(row["\u5e73\u4ed3\u4ef7"]), 822.5)
        self.assertAlmostEqual(float(row["\u5e73\u4ed3\u76c8\u4e8f"]), -935000.0)
        self.assertAlmostEqual(float(row["\u5408\u8ba1\u76c8\u4e8f"]), -935000.0)

    def test_close_type_filter_can_select_natural_maturity_rows(self) -> None:
        df = pd.DataFrame(
            [
                {"平仓类别": self.app.NATURAL_MATURITY_CLOSE_CATEGORY, "结构": "S018"},
                {"平仓类别": self.app.STRUCT_CLOSE_CATEGORY, "结构": "S019"},
            ]
        )

        filtered = self.app.apply_close_type_filter(df, "仅自然到期结束")

        self.assertEqual(filtered["结构"].astype(str).tolist(), ["S018"])

    def test_vanilla_auto_maturity_record_suppresses_natural_close_detail_row(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-05-11",
                    "group_id": "G003",
                    "structure_id": "V_CALL_SELL",
                    "structure_code": "S002",
                    "name": "卖出看涨",
                    "underlying": "I2609",
                    "kind": "DEC",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "status": "行权",
                    "status_cn": "行权",
                    "raw_status": "行权",
                    "normalized_status": "vanilla_expired_itm",
                    "generated_qty": 0.0,
                    "entry_price": 775.0,
                    "strike_price": 800.0,
                    "premium": 3.8,
                    "option_type": "call",
                    "side": "sell",
                    "gen_price": 3.8,
                    "settle": 822.5,
                    "day_pnl": -400000.0,
                    "cum_pnl": -935000.0,
                    "day_subsidy_pnl": 0.0,
                }
            ]
        )
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "V_CALL_SELL",
                    "group_id": "G003",
                    "structure_code": "S002",
                    "name": "卖出看涨",
                    "risk_party": "海证资本",
                    "note": "",
                    "kind": "DEC",
                    "underlying": "I2609",
                    "entry_price": 775.0,
                    "strike_price": 800.0,
                    "premium": 3.8,
                    "option_type": "call",
                    "side": "sell",
                    "strategy_code": self.app.VANILLA_OPTION_CODE,
                    "strategy": self.app.VANILLA_OPTION_CODE,
                }
            ]
        )
        close2_df = pd.DataFrame(
            [
                {
                    "close_id": "VMAT_V_CALL_SELL_20260511_CASH",
                    "dt": "2026-05-11",
                    "group_id": "G003",
                    "structure_id": "V_CALL_SELL",
                    "underlying": "I2609",
                    "side": "平仓",
                    "qty": 50000.0,
                    "open_price": 803.8,
                    "close_price": 822.5,
                    "pnl": -935000.0,
                    "close_category": self.app.VANILLA_MATURITY_CASH_CLOSE_CATEGORY,
                    "quick_batch_id": "VMAT_V_CALL_SELL_20260511",
                    "source_gen_date": "",
                    "is_external": 1,
                }
            ]
        )

        detail = self.app.build_close_detail_table(
            close2_df=close2_df,
            spot_match_df=pd.DataFrame(),
            rep_gid="G003",
            rep_und="I2609",
            rep_date="2026-05-11",
            group_name_map={"G003": "Group"},
            structs_df=structs_df,
            groups_df=pd.DataFrame([{"group_id": "G003", "group_name": "Group", "underlying": "I2609"}]),
            struct_daily_df=struct_daily,
        )

        self.assertEqual(len(detail), 1)
        self.assertEqual(detail.iloc[0]["平仓类别"], self.app.VANILLA_MATURITY_CASH_CLOSE_CATEGORY)


if __name__ == "__main__":
    unittest.main()
