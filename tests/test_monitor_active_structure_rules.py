import importlib.util
import pathlib
import sys
import unittest
from datetime import date

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_active_structure_rules_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorActiveStructureRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_structure_has_expired_by_asof_uses_strictly_earlier_date_boundary(self) -> None:
        self.assertTrue(self.app.structure_has_expired_by_asof("2026-04-13", "2026-04-10"))
        self.assertFalse(self.app.structure_has_expired_by_asof("2026-04-13", "2026-04-13"))
        self.assertFalse(self.app.structure_has_expired_by_asof("2026-04-13", "2026-04-14"))

    def test_build_expired_structure_sid_date_map_only_marks_structures_before_report_date(self) -> None:
        expired_map = self.app.build_expired_structure_sid_date_map(
            {
                "S_EXPIRED": "2026-04-10",
                "S_SAME_DAY": "2026-04-13",
                "S_FUTURE": "2026-04-14",
                "": "2026-04-01",
            },
            "2026-04-13",
        )

        self.assertEqual(expired_map, {"S_EXPIRED": date(2026, 4, 10)})

    def test_get_termination_state_date_falls_back_to_expiry_end(self) -> None:
        status_text, status_date = self.app.get_termination_state_date(
            "S_EXPIRED",
            manual_map={},
            melt_map={},
            melt_status_map={},
            expired_date_map={"S_EXPIRED": date(2026, 4, 10)},
        )

        self.assertEqual(status_text, "到期结束")
        self.assertEqual(status_date, "2026-04-10")


    def test_created_today_start_tomorrow_counts_as_monitor_preobserve(self) -> None:
        self.assertTrue(
            self.app.structure_created_today_start_tomorrow_for_monitor(
                "2026-04-13 09:30:00",
                "2026-04-14",
                "2026-04-13",
            )
        )
        self.assertFalse(
            self.app.structure_created_today_start_tomorrow_for_monitor(
                "2026-04-12 09:30:00",
                "2026-04-14",
                "2026-04-13",
            )
        )
        self.assertFalse(
            self.app.structure_created_today_start_tomorrow_for_monitor(
                "2026-04-13 09:30:00",
                "2026-04-15",
                "2026-04-13",
            )
        )

    def test_build_monitor_preobserve_rows_are_unstarted_display_only(self) -> None:
        structs = pd.DataFrame(
            [
                {
                    "structure_id": "S_PRE",
                    "structure_code": "S001",
                    "group_id": "G1",
                    "name": "Preobserve",
                    "underlying": "I2605",
                    "risk_party": "desk",
                    "kind": "ACC",
                    "strategy": "BASIC_RANGE",
                    "strategy_code": "BASIC_RANGE",
                    "start_date": "2026-04-14",
                    "end_date": "2026-04-20",
                    "trade_date": "2026-04-13",
                    "expiry_date": "2026-04-20",
                    "base_qty_per_day": 100.0,
                    "gen_price": 800.0,
                    "entry_price": 800.0,
                    "strike_price": 790.0,
                    "barrier_in": 780.0,
                    "barrier_out": 820.0,
                    "knock_out_price": None,
                    "ko_strike_price": None,
                    "multiple": 1.0,
                    "option_type": "",
                    "side": "",
                    "premium": None,
                    "note": "",
                    "params_json": "{}",
                    "meta_json": "{}",
                    "created_at": "2026-04-13 09:30:00",
                }
            ]
        )

        rows = self.app.build_monitor_preobserve_structure_rows(
            structs,
            pd.DataFrame(),
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-04-13",
            rep_und_all=False,
        )

        self.assertEqual(len(rows), 1)
        row = rows.iloc[0]
        self.assertEqual(row["structure_id"], "S_PRE")
        self.assertEqual(row["status_cn"], "未开始")
        self.assertEqual(row["generated_qty"], 0.0)
        self.assertEqual(row["observed_trading_days"], 0)
        self.assertGreater(row["remaining_trading_days"], 0)
        self.assertEqual(self.app.status_to_cn("未开始", 0.0, 1.0), "未开始")


if __name__ == "__main__":
    unittest.main()
