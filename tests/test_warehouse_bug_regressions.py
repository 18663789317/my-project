import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_warehouse_bug_regression_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WarehouseBugRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        for cache_name in [
            "_FETCH_SQL_MEMO_CACHE",
            "_LEDGER_MEMO_CACHE",
            "_OPEN_LOT_MEMO_CACHE",
            "_STRUCT_DERIVED_MEMO_CACHE",
        ]:
            cache_obj = getattr(self.app, cache_name, None)
            if hasattr(cache_obj, "clear"):
                cache_obj.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "仓库回归测试组", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def insert_acc_structure(
        self,
        structure_id: str,
        *,
        strategy_code: str = "BASIC_RANGE",
        base_qty: float = 100.0,
        subsidy_per_ton: float = 0.0,
        end_date: str = "2026-04-01",
    ) -> None:
        params = {"subsidy_per_ton": subsidy_per_ton}
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, structure_code, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_out, knock_out_price,
                multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                "G1",
                structure_id,
                structure_id,
                "I.TEST",
                "海证资本",
                "ACC",
                strategy_code,
                strategy_code,
                "2026-04-01",
                end_date,
                base_qty,
                100.0,
                90.0,
                120.0,
                120.0,
                2.0,
                json.dumps(params, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )

    def insert_price(self, dt_s: str = "2026-04-01", settle: float = 100.0) -> None:
        self.conn.execute(
            "INSERT INTO price(dt, underlying, settle) VALUES(?,?,?)",
            (dt_s, "I.TEST", float(settle)),
        )
        self.conn.commit()

    def test_close_trade2_over_close_clips_position_instead_of_reversing(self) -> None:
        self.insert_acc_structure("S_OVER", base_qty=100.0)
        self.insert_price()
        self.conn.execute(
            """
            INSERT INTO close_trade2(
                close_id, dt, group_id, structure_id, underlying, side, qty,
                open_price, close_price, pnl, close_category, is_external
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "C_OVER",
                "2026-04-01",
                "G1",
                "S_OVER",
                "I.TEST",
                "SELL",
                150.0,
                100.0,
                100.0,
                0.0,
                self.app.STRUCT_CLOSE_CATEGORY,
                0,
            ),
        )
        self.conn.commit()

        _, group_df, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-01")

        self.assertAlmostEqual(float(group_df.iloc[-1]["net_pos_qty"]), 0.0)

    def test_legacy_close_trade_is_not_double_counted_when_close_trade2_matches(self) -> None:
        self.insert_acc_structure("S_DUP", base_qty=100.0)
        self.insert_price()
        self.conn.execute(
            "INSERT INTO close_trade(dt, group_id, underlying, side, qty) VALUES(?,?,?,?,?)",
            ("2026-04-01", "G1", "I.TEST", "SELL", 50.0),
        )
        self.conn.execute(
            """
            INSERT INTO close_trade2(
                close_id, dt, group_id, structure_id, underlying, side, qty,
                open_price, close_price, pnl, close_category, is_external
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "C_DUP",
                "2026-04-01",
                "G1",
                "S_DUP",
                "I.TEST",
                "SELL",
                50.0,
                100.0,
                100.0,
                0.0,
                self.app.STRUCT_CLOSE_CATEGORY,
                0,
            ),
        )
        self.conn.commit()

        _, group_df, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-01")

        self.assertAlmostEqual(float(group_df.iloc[-1]["net_pos_qty"]), 50.0)

    def test_auto_subsidy_uses_position_adjusted_qty(self) -> None:
        self.insert_acc_structure(
            "S_SUB",
            strategy_code="PREMIUM_SUBSIDY",
            base_qty=500.0,
            subsidy_per_ton=10.0,
        )
        self.insert_price(settle=100.0)
        self.app.insert_structure_position_adjustment_rows(
            self.conn,
            [
                {
                    "adjustment_id": "ADJ_SUB",
                    "adjust_batch_id": "BATCH_SUB",
                    "group_id": "G1",
                    "structure_id": "S_SUB",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-01",
                    "delta_qty": -200.0,
                    "before_qty": 500.0,
                    "after_qty": 300.0,
                    "basis_open_price": 100.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_DECREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-01 09:00:00",
                    "created_by": "tester",
                }
            ],
        )
        self.conn.commit()

        self.app.sync_fixed_subsidy_close_records(self.conn)
        row = self.conn.execute(
            """
            SELECT qty, pnl
            FROM close_trade2
            WHERE quick_batch_id=? AND structure_id=?
            """,
            (self.app.AUTO_SUBSIDY_BATCH_ID, "S_SUB"),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(float(row[0]), 300.0)
        self.assertAlmostEqual(float(row[1]), 3000.0)

    def test_fixed_subsidy_auto_close_qty_includes_knock_out_day(self) -> None:
        self.insert_acc_structure(
            "S_FIXED_KO",
            strategy_code="FIXED_SUBSIDY",
            base_qty=1000.0,
            subsidy_per_ton=0.0,
        )
        self.insert_price(settle=120.0)

        self.app.sync_fixed_subsidy_close_records(self.conn)
        row = self.conn.execute(
            """
            SELECT qty, pnl
            FROM close_trade2
            WHERE quick_batch_id=? AND structure_id=?
            """,
            (self.app.AUTO_SUBSIDY_BATCH_ID, "S_FIXED_KO"),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertAlmostEqual(float(row[0]), 1000.0)
        self.assertAlmostEqual(float(row[1]), 0.0)

    def test_melt_range_subsidy_auto_close_writes_range_days_and_melt_subsidy(self) -> None:
        self.insert_acc_structure(
            "S_MELT_RANGE",
            strategy_code="MELT_RANGE_SUBSIDY",
            base_qty=100.0,
            subsidy_per_ton=5.0,
            end_date="2026-04-03",
        )
        self.insert_price(dt_s="2026-04-01", settle=100.0)
        self.insert_price(dt_s="2026-04-02", settle=121.0)

        self.app.sync_fixed_subsidy_close_records(self.conn)
        rows = self.conn.execute(
            """
            SELECT close_id, qty, pnl, close_category
            FROM close_trade2
            WHERE quick_batch_id=? AND structure_id=?
            ORDER BY dt, close_id
            """,
            (self.app.AUTO_SUBSIDY_BATCH_ID, "S_MELT_RANGE"),
        ).fetchall()

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "MELT_RANGE_SUBSIDY::S_MELT_RANGE::2026-04-01")
        self.assertAlmostEqual(float(rows[0][1]), 100.0)
        self.assertAlmostEqual(float(rows[0][2]), 500.0)
        self.assertEqual(rows[0][3], self.app.PREMIUM_SUBSIDY_CLOSE_CATEGORY)
        self.assertEqual(rows[1][0], "SUBSIDY::S_MELT_RANGE::2026-04-02")
        self.assertAlmostEqual(float(rows[1][1]), 200.0)
        self.assertAlmostEqual(float(rows[1][2]), 1000.0)
        self.assertEqual(rows[1][3], self.app.SUBSIDY_CLOSE_CATEGORY)


if __name__ == "__main__":
    unittest.main()
