import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest
from typing import Any, Dict, List, Sequence, Tuple


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

STATUS_CN = {
    "normal_subsidy": "震荡获得补贴",
    "knock_in_terminate": "敲入熔断",
    "knock_out_subsidy_terminate": "敲出熔断-补贴",
    "knock_out_delivery_terminate": "敲出熔断-给量",
    "maturity_end": "到期结束",
}


def load_app():
    spec = importlib.util.spec_from_file_location("app_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PhoenixAccLedgerIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.app._FETCH_SQL_MEMO_CACHE.clear()
        self.app._LEDGER_MEMO_CACHE.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "PhoenixGroup", "I.DCE"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def call_terms(self, **overrides: Any) -> Dict[str, Any]:
        data = {
            "kind_value": "ACC",
            "daily_qty": 10.0,
            "entry_price": 100.0,
            "knock_in_price": 95.0,
            "knock_in_exercise_price": 96.0,
            "subsidy_per_ton": 5.0,
            "knock_out_price": 110.0,
            "participation_rate": 2.0,
            "knock_in_qty_mode": "all",
            "knock_out_settlement_mode": "subsidy",
            "knock_out_exercise_price": None,
        }
        data.update(overrides)
        return data

    def put_terms(self, **overrides: Any) -> Dict[str, Any]:
        data = {
            "kind_value": "DEC",
            "daily_qty": 10.0,
            "entry_price": 100.0,
            "knock_in_price": 105.0,
            "knock_in_exercise_price": 104.0,
            "subsidy_per_ton": 5.0,
            "knock_out_price": 90.0,
            "participation_rate": 2.0,
            "knock_in_qty_mode": "all",
            "knock_out_settlement_mode": "subsidy",
            "knock_out_exercise_price": None,
        }
        data.update(overrides)
        return data

    def trading_dates(self, count: int) -> List[str]:
        return ["2026-03-16", "2026-03-17", "2026-03-18", "2026-03-19", "2026-03-20"][:count]

    def insert_structure(self, structure_id: str, closes: Sequence[float], terms: Dict[str, Any]) -> None:
        strategy_code = self.app.phoenix_acc_strategy_code_for_kind(terms["kind_value"])
        underlying = f"{structure_id}.TEST"
        params = {
            "knock_in_exercise_price": terms["knock_in_exercise_price"],
            "knock_in_qty_mode": terms.get("knock_in_qty_mode", "all"),
            "knock_out_settlement_mode": terms.get("knock_out_settlement_mode", "subsidy"),
            "participation_rate": terms["participation_rate"],
            "subsidy_per_ton": terms["subsidy_per_ton"],
        }
        if terms.get("knock_out_exercise_price") is not None:
            params["knock_out_exercise_price"] = terms["knock_out_exercise_price"]
        dates = self.trading_dates(len(closes))
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_in,
                barrier_out, knock_out_price, ko_strike_price, multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                "G1",
                structure_id,
                underlying,
                "海证资本",
                terms["kind_value"],
                strategy_code,
                strategy_code,
                dates[0],
                dates[-1],
                terms["daily_qty"],
                terms["entry_price"],
                terms["knock_in_exercise_price"],
                terms["knock_in_price"],
                terms["knock_out_price"],
                terms["knock_out_price"],
                terms.get("knock_out_exercise_price"),
                terms["participation_rate"],
                json.dumps(params, ensure_ascii=False),
                "{}",
            ),
        )
        for dt_s, settle in zip(dates, closes):
            self.conn.execute(
                "INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)",
                (dt_s, underlying, float(settle)),
            )
        self.conn.commit()

    def run_case(self, structure_id: str, closes: Sequence[float], terms: Dict[str, Any]):
        self.insert_structure(structure_id, closes, terms)
        struct_df, _, _ = self.app.compute_ledgers(self.conn)
        actual = (
            struct_df[struct_df["structure_id"].astype(str) == structure_id]
            .sort_values(["date", "structure_id"])
            .reset_index(drop=True)
        )
        expected = self.app.simulate_phoenix_acc_fixed_ledger(closes, **terms)
        return actual, expected

    def assert_case_matches(self, actual, expected) -> None:
        self.assertEqual(len(actual), len(expected))
        for idx, exp in enumerate(expected):
            act = actual.iloc[idx]
            self.assertEqual(str(act["event_type"]), str(exp["event_type"]))
            self.assertEqual(str(act["terminate_reason"]), str(exp["terminate_reason"]))
            self.assertEqual(str(act["delivered_side"]), str(exp["delivered_side"]))
            self.assertEqual(str(act["status"]), STATUS_CN[str(exp["event_type"])])
            self.assertAlmostEqual(float(act["generated_qty"]), float(exp["delivered_qty"]))
            self.assertAlmostEqual(float(act["day_subsidy_pnl"]), float(exp["daily_subsidy"]))
            self.assertAlmostEqual(float(act["cum_subsidy_pnl"]), float(exp["cumulative_subsidy"]))
            self.assertAlmostEqual(float(act["cum_qty"]), float(exp["cumulative_delivered_qty"]))
            expected_price = 0.0 if exp["delivered_price"] is None else float(exp["delivered_price"])
            self.assertAlmostEqual(float(act["gen_price"]), expected_price)

    def test_call_normal_subsidy_to_maturity(self) -> None:
        actual, expected = self.run_case("ACC_MATURITY", [100.0, 101.0, 102.0], self.call_terms())
        self.assert_case_matches(actual, expected)
        self.assertEqual(actual["status"].tolist(), ["震荡获得补贴", "震荡获得补贴", "到期结束"])

    def test_call_mid_knock_out_subsidy(self) -> None:
        actual, expected = self.run_case("ACC_KO_SUBSIDY", [100.0, 111.0, 105.0], self.call_terms())
        self.assert_case_matches(actual, expected)
        self.assertEqual(actual["status"].tolist(), ["震荡获得补贴", "敲出熔断-补贴"])

    def test_call_mid_knock_out_delivery(self) -> None:
        actual, expected = self.run_case(
            "ACC_KO_DELIVERY",
            [100.0, 111.0, 105.0],
            self.call_terms(
                knock_out_settlement_mode="delivery",
                knock_out_exercise_price=108.0,
            ),
        )
        self.assert_case_matches(actual, expected)
        self.assertEqual(actual["status"].tolist(), ["震荡获得补贴", "敲出熔断-给量"])

    def test_call_knock_in_all_vs_remaining(self) -> None:
        cases: List[Tuple[str, Dict[str, Any], float]] = [
            ("ACC_KI_ALL", self.call_terms(participation_rate=1.5, knock_in_qty_mode="all"), 30.0),
            ("ACC_KI_REMAIN", self.call_terms(participation_rate=1.5, knock_in_qty_mode="remaining"), 15.0),
        ]
        for structure_id, terms, expected_qty in cases:
            with self.subTest(structure_id=structure_id):
                actual, expected = self.run_case(structure_id, [100.0, 94.0], terms)
                self.assert_case_matches(actual, expected)
                self.assertEqual(actual["status"].tolist(), ["震荡获得补贴", "敲入熔断"])
                self.assertAlmostEqual(float(actual.iloc[-1]["generated_qty"]), expected_qty)

    def test_put_mirror_cases(self) -> None:
        cases = [
            ("PUT_MATURITY", [100.0, 100.0], self.put_terms(), ["震荡获得补贴", "到期结束"]),
            ("PUT_KI", [105.0], self.put_terms(), ["敲入熔断"]),
            (
                "PUT_KO_DELIVERY",
                [100.0, 90.0],
                self.put_terms(knock_out_settlement_mode="delivery", knock_out_exercise_price=91.0),
                ["震荡获得补贴", "敲出熔断-给量"],
            ),
        ]
        for structure_id, closes, terms, expected_status in cases:
            with self.subTest(structure_id=structure_id):
                actual, expected = self.run_case(structure_id, closes, terms)
                self.assert_case_matches(actual, expected)
                self.assertEqual(actual["status"].tolist(), expected_status)


if __name__ == "__main__":
    unittest.main()
