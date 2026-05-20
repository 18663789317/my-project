import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_maturity_bug_regressions_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MaturityBugRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "Group", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def insert_vanilla_structure(
        self,
        structure_id: str,
        *,
        maturity_mode: str,
        maturity_roll_qty: float,
    ) -> None:
        params = {
            "multiplier": 1.0,
            "subsidy_per_ton": 0.0,
            "option_type": "call",
            "side": "sell",
            "premium": 5.0,
            "trade_date": "2026-04-01",
            "expiry_date": "2026-04-03",
            self.app.VANILLA_MATURITY_MODE_PARAM_KEY: maturity_mode,
            self.app.VANILLA_MATURITY_ROLL_QTY_PARAM_KEY: float(maturity_roll_qty),
        }
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, structure_code, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, multiple,
                trade_date, expiry_date, option_type, side, premium, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                "G1",
                structure_id,
                structure_id,
                "I.TEST",
                "risk",
                "DEC",
                self.app.VANILLA_OPTION_CODE,
                self.app.VANILLA_OPTION_CODE,
                "2026-04-01",
                "2026-04-03",
                10000.0,
                100.0,
                100.0,
                1.0,
                "2026-04-01",
                "2026-04-03",
                "call",
                "sell",
                5.0,
                json.dumps(params, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def update_vanilla_maturity_mode(
        self,
        structure_id: str,
        *,
        maturity_mode: str,
        maturity_roll_qty: float,
    ) -> None:
        raw = self.conn.execute(
            "SELECT params_json FROM structure WHERE structure_id=?",
            (structure_id,),
        ).fetchone()[0]
        params = json.loads(raw)
        params[self.app.VANILLA_MATURITY_MODE_PARAM_KEY] = maturity_mode
        params[self.app.VANILLA_MATURITY_ROLL_QTY_PARAM_KEY] = float(maturity_roll_qty)
        self.conn.execute(
            "UPDATE structure SET params_json=? WHERE structure_id=?",
            (json.dumps(params, ensure_ascii=False), structure_id),
        )
        self.conn.commit()

    def test_vanilla_maturity_cash_resync_removes_old_roll_records(self) -> None:
        self.insert_vanilla_structure(
            "V_SWITCH",
            maturity_mode=self.app.VANILLA_MATURITY_MODE_ROLL,
            maturity_roll_qty=6000.0,
        )
        self.conn.execute("INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)", ("2026-04-03", "I.TEST", 120.0))
        self.conn.commit()

        first = self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-04-03")
        self.assertEqual(first["close_rows"], 2)
        self.assertEqual(first["adjust_rows"], 1)

        self.update_vanilla_maturity_mode(
            "V_SWITCH",
            maturity_mode=self.app.VANILLA_MATURITY_MODE_CASH,
            maturity_roll_qty=0.0,
        )
        second = self.app.sync_vanilla_maturity_records(self.conn, as_of_date="2026-04-03")

        close2 = self.app.fetch_closes2(self.conn)
        close_v = close2[close2["structure_id"].astype(str).eq("V_SWITCH")].copy()
        self.assertEqual(len(close_v), 1)
        self.assertEqual(str(close_v.iloc[0]["close_category"]), self.app.VANILLA_MATURITY_CASH_CLOSE_CATEGORY)
        self.assertAlmostEqual(float(close_v.iloc[0]["qty"]), 10000.0)
        self.assertAlmostEqual(float(close_v.iloc[0]["pnl"]), -150000.0)
        self.assertEqual(int(second["stale_close_rows"]), 1)

        adjustments = self.app.fetch_structure_position_adjustments(self.conn)
        adj_v = adjustments[adjustments["structure_id"].astype(str).eq("V_SWITCH")].copy()
        self.assertTrue(adj_v.empty)
        self.assertEqual(int(second["stale_adjust_rows"]), 1)

    def test_natural_maturity_remaining_qty_does_not_use_cumulative_generated_qty(self) -> None:
        row = {
            "strategy_code": "FLOAT_KO",
            "cum_qty": 20000.0,
            "observed_generated_qty": 20000.0,
            "executed_qty": 20000.0,
        }

        self.assertAlmostEqual(float(self.app.natural_maturity_remaining_qty_from_row(row)), 0.0)

        row["current_open_qty"] = 5000.0
        self.assertAlmostEqual(float(self.app.natural_maturity_remaining_qty_from_row(row)), 5000.0)

    def test_natural_maturity_remaining_qty_prefers_current_open_over_notional(self) -> None:
        row = {
            "strategy_code": "SAFETY_AIRBAG",
            "base_qty_per_day": 100.0,
            "start_date": "2026-04-01",
            "end_date": "2026-04-30",
            "current_open_qty": 5000.0,
        }

        self.assertAlmostEqual(float(self.app.natural_maturity_remaining_qty_from_row(row)), 5000.0)


if __name__ == "__main__":
    unittest.main()
