import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_over_close_validation_disabled_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OverCloseValidationDisabledTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def _conn_with_one_lot(self) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        self.app.init_db(conn)
        conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "G", "I2605"),
        )
        conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_in,
                barrier_out, knock_out_price, ko_strike_price, multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "S1",
                "G1",
                "S1",
                "I2605",
                "R",
                "ACC",
                "BASIC_RANGE",
                "BASIC_RANGE",
                "2026-04-01",
                "2026-04-01",
                100.0,
                100.0,
                100.0,
                90.0,
                110.0,
                110.0,
                110.0,
                1.0,
                json.dumps({}),
                json.dumps({}),
            ),
        )
        conn.execute("INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)", ("2026-04-01", "I2605", 100.0))
        conn.commit()
        return conn

    def test_validate_no_worse_over_close_blocks_new_over_close(self) -> None:
        conn = self._conn_with_one_lot()
        try:
            ok, msg = self.app.validate_no_worse_over_close(
                conn,
                touched_structure_ids=["S1"],
                pending_inserts=[
                    {
                        "close_id": "C_OVER",
                        "dt": "2026-04-01",
                        "group_id": "G1",
                        "structure_id": "S1",
                        "underlying": "I2605",
                        "side": "SELL",
                        "qty": 150.0,
                        "open_price": 100.0,
                        "close_price": 101.0,
                        "pnl": 150.0,
                        "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                        "is_external": 0,
                    }
                ],
            )
        finally:
            conn.close()

        self.assertFalse(ok)
        self.assertIn("超过当前可平仓数量", msg)

    def test_validate_no_worse_over_close_allows_available_close(self) -> None:
        conn = self._conn_with_one_lot()
        try:
            ok, msg = self.app.validate_no_worse_over_close(
                conn,
                touched_structure_ids=["S1"],
                pending_inserts=[
                    {
                        "close_id": "C_OK",
                        "dt": "2026-04-01",
                        "group_id": "G1",
                        "structure_id": "S1",
                        "underlying": "I2605",
                        "side": "SELL",
                        "qty": 100.0,
                        "open_price": 100.0,
                        "close_price": 101.0,
                        "pnl": 100.0,
                        "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                        "is_external": 0,
                    }
                ],
            )
        finally:
            conn.close()

        self.assertTrue(ok, msg)
        self.assertEqual(msg, "")

    def test_validate_no_worse_over_close_counts_position_adjustment_lots(self) -> None:
        conn = self._conn_with_one_lot()
        try:
            conn.execute(
                """
                INSERT INTO structure_position_adjustment(
                    adjustment_id, adjust_batch_id, group_id, structure_id, underlying,
                    adjust_dt, delta_qty, before_qty, after_qty, basis_open_price,
                    previous_basis_open_price, action_type, created_at, created_by
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    "ADJ_EXTRA_50",
                    "BATCH_EXTRA",
                    "G1",
                    "S1",
                    "I2605",
                    "2026-04-01",
                    50.0,
                    100.0,
                    150.0,
                    100.0,
                    100.0,
                    self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "2026-04-01 09:00:00",
                    "test",
                ),
            )
            conn.commit()

            ok, msg = self.app.validate_no_worse_over_close(
                conn,
                touched_structure_ids=["S1"],
                pending_inserts=[
                    {
                        "close_id": "C_ADJ_OK",
                        "dt": "2026-04-01",
                        "group_id": "G1",
                        "structure_id": "S1",
                        "underlying": "I2605",
                        "side": "SELL",
                        "qty": 150.0,
                        "open_price": 100.0,
                        "close_price": 101.0,
                        "pnl": 150.0,
                        "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                        "is_external": 0,
                    }
                ],
            )
        finally:
            conn.close()

        self.assertTrue(ok, msg)
        self.assertEqual(msg, "")


if __name__ == "__main__":
    unittest.main()
