import importlib.util
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_acc_status_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AccumulatorStatusRegressionTests(unittest.TestCase):
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
            ("G1", "累计测试", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_status_to_cn_formats_knock_in_multiplier_and_preserves_preformatted_labels(self) -> None:
        self.assertEqual(self.app.status_to_cn("敲入", 20.0, 2.0), "敲入（2倍）")
        self.assertEqual(self.app.status_to_cn("敲入", 15.0, 1.5), "敲入（1.5倍）")
        self.assertEqual(self.app.status_to_cn("敲入（2倍）", 0.0, 0.0), "敲入（2倍）")
        self.assertEqual(self.app.normalize_structure_status("敲入（2倍）"), "accumulator_knock_in")
        self.assertEqual(self.app.normalize_structure_status("震荡（1倍）"), "accumulator_active")

    def test_compute_ledgers_keeps_raw_knock_in_status_for_basic_range(self) -> None:
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_in,
                barrier_out, knock_out_price, ko_strike_price, multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "ACC_STATUS_1",
                "G1",
                "普通累计-状态回归",
                "I.TEST",
                "海证资本",
                "DEC",
                "BASIC_RANGE",
                "BASIC_RANGE",
                "2026-03-16",
                "2026-03-17",
                10.0,
                100.0,
                105.0,
                None,
                95.0,
                95.0,
                None,
                2.0,
                "{}",
                "{}",
            ),
        )
        self.conn.executemany(
            "INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)",
            [
                ("2026-03-16", "I.TEST", 104.0),
                ("2026-03-17", "I.TEST", 106.0),
            ],
        )
        self.conn.commit()

        struct_df, _, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-03-17")
        cut = (
            struct_df[struct_df["structure_id"].astype(str) == "ACC_STATUS_1"]
            .sort_values(["date", "structure_id"])
            .reset_index(drop=True)
        )

        self.assertEqual(cut.loc[0, "raw_status"], "震荡")
        self.assertEqual(cut.loc[0, "status"], "震荡（1倍）")
        self.assertEqual(cut.loc[1, "raw_status"], "敲入")
        self.assertEqual(cut.loc[1, "status"], "敲入（2倍）")
        self.assertEqual(cut.loc[1, "status_cn"], "敲入（2倍）")
        self.assertEqual(cut.loc[1, "normalized_status"], "accumulator_knock_in")
        self.assertAlmostEqual(float(cut.loc[1, "multiplier"]), 2.0)
        self.assertAlmostEqual(float(cut.loc[1, "generated_qty"]), 20.0)
        self.assertEqual(self.app.status_to_cn(cut.loc[1, "status"], 0.0, 0.0), "敲入（2倍）")


if __name__ == "__main__":
    unittest.main()
