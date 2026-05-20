import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest
from typing import Any, Dict, List

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PhoenixAccMonitorStatsTests(unittest.TestCase):
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
            ("G1", "PhoenixMonitor", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def trading_dates(self) -> List[str]:
        return ["2026-03-16", "2026-03-17", "2026-03-18", "2026-03-19"]

    def structure_row(
        self,
        structure_id: str,
        *,
        kind: str = "ACC",
        group_id: str = "G1",
        underlying: str = "I.TEST",
        daily_qty: float = 10.0,
        participation_rate: float = 2.0,
        knock_in_qty_mode: str = "all",
        subsidy_per_ton: float = 5.0,
    ) -> Dict[str, Any]:
        strategy_code = self.app.phoenix_acc_strategy_code_for_kind(kind)
        if kind == "DEC":
            barrier_in = 105.0
            knock_in_exercise_price = 104.0
            knock_out_price = 90.0
        else:
            barrier_in = 95.0
            knock_in_exercise_price = 96.0
            knock_out_price = 110.0
        params = {
            "participation_rate": participation_rate,
            "knock_in_qty_mode": knock_in_qty_mode,
            "knock_out_settlement_mode": "subsidy",
            "knock_in_exercise_price": knock_in_exercise_price,
            "subsidy_per_ton": subsidy_per_ton,
        }
        dates = self.trading_dates()
        return {
            "structure_id": structure_id,
            "group_id": group_id,
            "name": structure_id,
            "underlying": underlying,
            "risk_party": "RP",
            "kind": kind,
            "strategy": strategy_code,
            "strategy_code": strategy_code,
            "start_date": dates[0],
            "end_date": dates[-1],
            "base_qty_per_day": daily_qty,
            "entry_price": 100.0,
            "strike_price": knock_in_exercise_price,
            "barrier_in": barrier_in,
            "barrier_out": knock_out_price,
            "knock_out_price": knock_out_price,
            "ko_strike_price": None,
            "multiple": participation_rate,
            "params_json": json.dumps(params, ensure_ascii=False),
            "meta_json": "{}",
        }

    def price_df(self, underlying: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"dt": "2026-03-16", "underlying": underlying, "settle": 100.0},
                {"dt": "2026-03-17", "underlying": underlying, "settle": 101.0},
            ]
        )

    def insert_structure(self, row: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_in,
                barrier_out, knock_out_price, ko_strike_price, multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                row["structure_id"],
                row["group_id"],
                row["name"],
                row["underlying"],
                row["risk_party"],
                row["kind"],
                row["strategy"],
                row["strategy_code"],
                row["start_date"],
                row["end_date"],
                row["base_qty_per_day"],
                row["entry_price"],
                row["strike_price"],
                row["barrier_in"],
                row["barrier_out"],
                row["knock_out_price"],
                row["ko_strike_price"],
                row["multiple"],
                row["params_json"],
                row["meta_json"],
            ),
        )

    def insert_prices(self, underlying: str) -> None:
        for rec in self.price_df(underlying).to_dict("records"):
            self.conn.execute(
                "INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)",
                (rec["dt"], rec["underlying"], rec["settle"]),
            )

    def test_compute_price_gap_table_all_and_remaining_modes(self) -> None:
        structs = pd.DataFrame(
            [
                self.structure_row("ACC_ALL", knock_in_qty_mode="all"),
                self.structure_row("ACC_REM", knock_in_qty_mode="remaining", underlying="J.TEST"),
            ]
        )
        prices = pd.concat([self.price_df("I.TEST"), self.price_df("J.TEST")], ignore_index=True)
        gap_df = self.app.compute_price_gap_table(
            structs,
            prices,
            pd.DataFrame(),
            as_of_date="2026-03-17",
        )
        row_all = gap_df[gap_df["结构ID"].astype(str) == "ACC_ALL"].iloc[0]
        row_rem = gap_df[gap_df["结构ID"].astype(str) == "ACC_REM"].iloc[0]

        self.assertEqual(int(row_all["剩余观察交易日"]), 2)
        self.assertAlmostEqual(float(row_all["剩余震荡最大头寸规模"]), 80.0)
        self.assertAlmostEqual(float(row_all["剩余震荡最小头寸规模"]), 0.0)
        self.assertAlmostEqual(float(row_all["剩余震荡最大补贴规模"]), 100.0)

        self.assertEqual(int(row_rem["剩余观察交易日"]), 2)
        self.assertAlmostEqual(float(row_rem["剩余震荡最大头寸规模"]), 40.0)
        self.assertAlmostEqual(float(row_rem["剩余震荡最小头寸规模"]), 0.0)
        self.assertAlmostEqual(float(row_rem["剩余震荡最大补贴规模"]), 100.0)

    def test_compute_price_gap_table_put_mirror_and_subsidy_stable(self) -> None:
        structs = pd.DataFrame(
            [
                self.structure_row("PUT_REM", kind="DEC", knock_in_qty_mode="remaining"),
                self.structure_row("PUT_ALL", kind="DEC", knock_in_qty_mode="all", underlying="P.TEST"),
            ]
        )
        prices = pd.concat([self.price_df("I.TEST"), self.price_df("P.TEST")], ignore_index=True)
        gap_df = self.app.compute_price_gap_table(
            structs,
            prices,
            pd.DataFrame(),
            as_of_date="2026-03-17",
        )
        row_rem = gap_df[gap_df["结构ID"].astype(str) == "PUT_REM"].iloc[0]
        row_all = gap_df[gap_df["结构ID"].astype(str) == "PUT_ALL"].iloc[0]

        self.assertAlmostEqual(float(row_rem["剩余震荡最大头寸规模"]), -40.0)
        self.assertAlmostEqual(float(row_rem["剩余震荡最小头寸规模"]), 0.0)
        self.assertAlmostEqual(float(row_rem["剩余震荡最大补贴规模"]), 100.0)

        self.assertAlmostEqual(float(row_all["剩余震荡最大头寸规模"]), -80.0)
        self.assertAlmostEqual(float(row_all["剩余震荡最小头寸规模"]), 0.0)
        self.assertAlmostEqual(float(row_all["剩余震荡最大补贴规模"]), 100.0)

    def test_compute_ledgers_bounds_group_sum_all_mode(self) -> None:
        row_a = self.structure_row("G_ALL_A", daily_qty=10.0, participation_rate=2.0, knock_in_qty_mode="all")
        row_b = self.structure_row(
            "G_ALL_B",
            daily_qty=5.0,
            participation_rate=3.0,
            knock_in_qty_mode="all",
            underlying="I.TEST",
        )
        self.insert_structure(row_a)
        self.insert_structure(row_b)
        self.insert_prices("I.TEST")
        self.conn.commit()

        _, _, bounds_df = self.app.compute_ledgers(self.conn, as_of_date="2026-03-17")
        struct_rows = bounds_df[bounds_df["level"].astype(str) == "STRUCTURE"].copy()
        group_row = bounds_df[bounds_df["level"].astype(str) == "GROUP"].iloc[0]

        row_a_bounds = struct_rows[struct_rows["structure_id"].astype(str) == "G_ALL_A"].iloc[0]
        row_b_bounds = struct_rows[struct_rows["structure_id"].astype(str) == "G_ALL_B"].iloc[0]

        self.assertAlmostEqual(float(row_a_bounds["remaining_max_qty"]), 80.0)
        self.assertAlmostEqual(float(row_b_bounds["remaining_max_qty"]), 60.0)
        self.assertAlmostEqual(float(row_a_bounds["remaining_min_qty"]), 0.0)
        self.assertAlmostEqual(float(row_b_bounds["remaining_min_qty"]), 0.0)
        self.assertAlmostEqual(float(group_row["remaining_max_qty"]), 140.0)
        self.assertAlmostEqual(float(group_row["remaining_min_qty"]), 0.0)

    def test_compute_ledgers_bounds_group_sum_remaining_mode(self) -> None:
        row_a = self.structure_row("G_REM_A", daily_qty=10.0, participation_rate=2.0, knock_in_qty_mode="remaining")
        row_b = self.structure_row(
            "G_REM_B",
            daily_qty=5.0,
            participation_rate=3.0,
            knock_in_qty_mode="remaining",
            underlying="I.TEST",
        )
        self.insert_structure(row_a)
        self.insert_structure(row_b)
        self.insert_prices("I.TEST")
        self.conn.commit()

        _, _, bounds_df = self.app.compute_ledgers(self.conn, as_of_date="2026-03-17")
        struct_rows = bounds_df[bounds_df["level"].astype(str) == "STRUCTURE"].copy()
        group_row = bounds_df[bounds_df["level"].astype(str) == "GROUP"].iloc[0]

        row_a_bounds = struct_rows[struct_rows["structure_id"].astype(str) == "G_REM_A"].iloc[0]
        row_b_bounds = struct_rows[struct_rows["structure_id"].astype(str) == "G_REM_B"].iloc[0]

        self.assertAlmostEqual(float(row_a_bounds["remaining_max_qty"]), 40.0)
        self.assertAlmostEqual(float(row_b_bounds["remaining_max_qty"]), 30.0)
        self.assertAlmostEqual(float(row_a_bounds["remaining_min_qty"]), 0.0)
        self.assertAlmostEqual(float(row_b_bounds["remaining_min_qty"]), 0.0)
        self.assertAlmostEqual(float(group_row["remaining_max_qty"]), 70.0)
        self.assertAlmostEqual(float(group_row["remaining_min_qty"]), 0.0)


if __name__ == "__main__":
    unittest.main()
