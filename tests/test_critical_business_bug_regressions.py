import importlib.util
import pathlib
import sqlite3
import sys
import unittest
from datetime import date
from unittest import mock

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_critical_business_bug_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CriticalBusinessBugRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_three_digit_contract_code_uses_two_digit_year_and_one_digit_month(self) -> None:
        self.assertEqual(self.app._parse_contract_year_month("I251"), (2025, 1))
        self.assertEqual(self.app._parse_contract_year_month("rb251"), (2025, 1))
        self.assertEqual(self.app._parse_contract_year_month("I2501"), (2025, 1))
        self.assertIsNone(self.app._parse_contract_year_month("I2513"))

    def test_upsert_structure_payload_keeps_price_fields_distinct_and_updates_caps(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        self.app.init_db(conn)
        conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "Group", "I.TEST"),
        )
        conn.commit()

        payload = {
            "structure_id": "S_CAP",
            "structure_code": "S001",
            "group_id": "G1",
            "name": "Caps",
            "underlying": "I.TEST",
            "risk_party": "Risk",
            "kind_code": "ACC",
            "strategy_code": "SNOWBALL",
            "start_date_s": "2026-04-01",
            "end_date_s": "2026-04-30",
            "base_qty": 100.0,
            "gen_price": 100.0,
            "entry_price": 100.0,
            "strike_price": 95.0,
            "barrier_in": 80.0,
            "barrier_out": 102.0,
            "knock_out_price": 108.0,
            "ko_strike_price": 101.0,
            "barrier_price": 81.0,
            "melt_price": 109.0,
            "melt_strike": 103.0,
            "multiple": 1.0,
            "total_cap_qty": 5000.0,
            "daily_cap_qty": 300.0,
            "params_json": {},
            "meta_json": {},
        }

        self.app.upsert_structure_record_payload(conn, payload)
        payload["barrier_price"] = 82.0
        payload["melt_price"] = 110.0
        payload["melt_strike"] = 104.0
        payload["total_cap_qty"] = 6000.0
        payload["daily_cap_qty"] = 350.0
        self.app.upsert_structure_record_payload(conn, payload)

        row = conn.execute(
            """
            SELECT barrier_out, knock_out_price, ko_strike_price,
                   barrier_price, melt_price, melt_strike,
                   total_cap_qty, daily_cap_qty
            FROM structure
            WHERE structure_id=?
            """,
            ("S_CAP",),
        ).fetchone()

        self.assertEqual(tuple(row), (102.0, 108.0, 101.0, 82.0, 110.0, 104.0, 6000.0, 350.0))

    def test_unknown_kind_or_side_makes_estimated_pnl_unavailable_instead_of_partial_sum(self) -> None:
        detail_rows = [
            {
                "risk_party": "Risk",
                "direction": "Long",
                "action_label": "Close long",
                "action_short_label": "Close long",
                "qty": 10.0,
                "structure_id": "S_OK",
                "structure_label": "S_OK",
                "kind_code": "ACC",
                "close_side_code": "SELL",
                "open_price": 100.0,
            },
            {
                "risk_party": "Risk",
                "direction": "Broken",
                "action_label": "Close broken",
                "action_short_label": "Close broken",
                "qty": 5.0,
                "structure_id": "S_BAD",
                "structure_label": "S_BAD",
                "kind_code": "BROKEN",
                "close_side_code": "SELL",
                "open_price": 100.0,
            },
        ]

        enriched = self.app.enrich_warehouse_close_command_detail_rows(detail_rows, close_price=110.0)
        summary = self.app.summarize_warehouse_close_command(enriched)
        text = self.app.build_warehouse_close_command_text("2026-04-03", enriched)

        self.assertAlmostEqual(float(enriched[0]["estimated_pnl"]), 100.0)
        self.assertIsNone(enriched[1]["estimated_pnl"])
        self.assertTrue(str(enriched[1]["pnl_error"]))
        self.assertEqual(int(summary["pnl_error_count"]), 1)
        self.assertIsNone(summary["estimated_pnl"])
        self.assertIn("计算异常", text)

    def test_calc_close_pnl_rejects_unknown_side(self) -> None:
        with self.assertRaises(ValueError):
            self.app.calc_close_pnl("ACC", "HOLD", 10.0, 100.0, 110.0)

    def test_natural_maturity_timeline_failure_marks_status_for_review(self) -> None:
        struct_daily = pd.DataFrame(
            [
                {
                    "date": "2026-04-23",
                    "group_id": "G1",
                    "structure_id": "S_NAT",
                    "name": "Natural",
                    "underlying": "I.TEST",
                    "kind": "ACC",
                    "strategy_code": "SAFETY_AIRBAG",
                    "status": "Maturity",
                    "raw_status": "Maturity",
                    "normalized_status": "airbag_maturity_protect",
                    "generated_qty": 0.0,
                    "cum_qty": 1000.0,
                    "current_open_qty": 1000.0,
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                    "gen_price": 100.0,
                    "settle": 100.0,
                    "day_pnl": 0.0,
                    "day_subsidy_pnl": 0.0,
                }
            ]
        )
        structs_df = pd.DataFrame(
            [
                {
                    "structure_id": "S_NAT",
                    "group_id": "G1",
                    "structure_code": "S001",
                    "name": "Natural",
                    "risk_party": "Risk",
                    "kind": "ACC",
                    "underlying": "I.TEST",
                    "entry_price": 100.0,
                    "strike_price": 100.0,
                    "strategy_code": "SAFETY_AIRBAG",
                }
            ]
        )
        groups_df = pd.DataFrame([{"group_id": "G1", "group_name": "Group", "underlying": "I.TEST"}])
        maps = self.app.build_close_detail_maps(structs_df, groups_df)

        with mock.patch.object(self.app, "build_structure_position_timeline_frame", side_effect=RuntimeError("boom")):
            detail = self.app.build_natural_maturity_close_detail_frame(
                struct_daily,
                pd.DataFrame(),
                "G1",
                "I.TEST",
                date(2026, 4, 23),
                {"G1": "Group"},
                maps,
                adjustment_df=pd.DataFrame(),
            )

        self.assertEqual(len(detail), 1)
        status_value = str(detail.iloc[0][self.app.CLOSE_DETAIL_COLUMNS[3]])
        self.assertIn("持仓回算异常", status_value)


if __name__ == "__main__":
    unittest.main()
