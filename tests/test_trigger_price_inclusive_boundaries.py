import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_trigger_boundary_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TriggerPriceInclusiveBoundaryTests(unittest.TestCase):
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
            ("G1", "boundary-tests", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _insert_structure(self, **overrides):
        row = {
            "structure_id": "T1",
            "group_id": "G1",
            "name": "test-structure",
            "underlying": "I.TEST",
            "risk_party": "TestRisk",
            "kind": "DEC",
            "strategy": "FIXED_SUBSIDY",
            "strategy_code": "FIXED_SUBSIDY",
            "start_date": "2026-04-01",
            "end_date": "2026-04-02",
            "base_qty_per_day": 10.0,
            "entry_price": 100.0,
            "strike_price": 110.0,
            "barrier_in": None,
            "barrier_out": 90.0,
            "knock_out_price": None,
            "ko_strike_price": 100.0,
            "multiple": 3.0,
            "params_json": json.dumps({"multiplier": 3.0, "subsidy_per_ton": 0.0}, ensure_ascii=False),
            "meta_json": json.dumps({"ko_terminate": True}, ensure_ascii=False),
        }
        row.update(overrides)
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

    def _insert_prices(self, prices):
        self.conn.executemany("INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)", prices)
        self.conn.commit()

    def _latest_struct_rows(self, sid: str):
        struct_df, _, _ = self.app.compute_ledgers(self.conn, as_of_date="2026-04-02")
        cut = struct_df[struct_df["structure_id"].astype(str) == sid].sort_values(["date", "structure_id"]).reset_index(drop=True)
        return cut

    def _day_ctx(self, dt_text: str, *, total_days: int = 2, observed_days: int = 0, base_qty: float = 10.0):
        return {
            "dt": self.app.parse_date_maybe(dt_text),
            "total_days": total_days,
            "observed_days": observed_days,
            "remaining_days": max(total_days - observed_days, 0),
            "base_qty": base_qty,
        }

    def _snowball_day_ctx(self, struct, dt_text: str):
        start_d = self.app.parse_date_maybe(struct["start_date"])
        end_d = self.app.parse_date_maybe(struct["end_date"])
        dt = self.app.parse_date_maybe(dt_text)
        trading_days = self.app.trading_days_between(start_d, end_d)
        observed_days = len([d for d in trading_days if d < dt])
        return {
            "dt": dt,
            "total_days": len(trading_days),
            "observed_days": observed_days,
            "remaining_days": max(len(trading_days) - observed_days, 0),
            "base_qty": 0.0,
        }

    def test_fixed_subsidy_compute_ledgers_treats_micro_noise_as_equal_barrier(self) -> None:
        self._insert_structure(structure_id="FIX_EQ", name="fixed-subsidy-eq")
        self._insert_prices(
            [
                ("2026-04-01", "I.TEST", 100.0),
                ("2026-04-02", "I.TEST", 90.0000004),
            ]
        )

        cut = self._latest_struct_rows("FIX_EQ")

        self.assertEqual(cut.loc[1, "raw_status"], "敲出熔断")
        self.assertEqual(cut.loc[1, "normalized_status"], "accumulator_knock_out_terminate")

    def test_float_ko_compute_ledgers_treats_micro_noise_as_equal_melt_price(self) -> None:
        self._insert_structure(
            structure_id="FLOAT_EQ",
            name="float-ko-eq",
            strategy="FLOAT_KO",
            strategy_code="FLOAT_KO",
            barrier_out=90.0,
            knock_out_price=90.0,
            ko_strike_price=95.0,
        )
        self._insert_prices(
            [
                ("2026-04-01", "I.TEST", 100.0),
                ("2026-04-02", "I.TEST", 90.0000004),
            ]
        )

        cut = self._latest_struct_rows("FLOAT_EQ")

        self.assertEqual(cut.loc[1, "raw_status"], "敲出熔断")
        self.assertEqual(cut.loc[1, "normalized_status"], "accumulator_knock_out_terminate")

    def test_safety_airbag_equal_barrier_enters_knock_in_state(self) -> None:
        struct = {
            "kind": "DEC",
            "entry_price": 100.0,
            "strike_price": 95.0,
            "barrier_out": 105.0,
            "multiple": 80.0,
        }
        res = self.app._sm_safety_airbag(
            struct,
            104.9999996,
            self._day_ctx("2026-04-01", total_days=10, observed_days=0, base_qty=10.0),
            {},
        )

        self.assertEqual(res["status"], "敲入转线性")
        self.assertTrue(res["terminate"])
        self.assertAlmostEqual(float(res["qty"]), 100.0)
        self.assertAlmostEqual(float(res["gen_price"]), 95.0)

    def test_safety_airbag_maturity_sets_explicit_terminate(self) -> None:
        struct = {
            "kind": "ACC",
            "entry_price": 100.0,
            "strike_price": 95.0,
            "barrier_out": 80.0,
            "multiple": 80.0,
        }
        state = {}
        res = self.app._sm_safety_airbag(
            struct,
            110.0,
            self._day_ctx("2026-04-02", total_days=10, observed_days=9, base_qty=10.0),
            state,
        )

        self.assertEqual(res["status"], "未敲入到期上涨")
        self.assertTrue(res["terminate"])
        self.assertTrue(state["terminated"])

    def test_range_subsidy_equal_boundaries_follow_priority_rules(self) -> None:
        struct = {
            "kind": "ACC",
            "entry_price": 100.0,
            "strike_price": 100.0,
            "barrier_out": 110.0,
            "multiple": 3.0,
            "subsidy_per_ton": 5.0,
        }

        hit_strike = self.app._sm_range_subsidy(
            struct,
            100.0000004,
            self._day_ctx("2026-04-01"),
            {},
        )
        hit_barrier = self.app._sm_range_subsidy(
            struct,
            109.9999996,
            self._day_ctx("2026-04-01"),
            {},
        )

        self.assertEqual(hit_strike["status"], "敲入")
        self.assertEqual(hit_barrier["status"], "敲出不熔断")

    def test_fixed_subsidy_knock_out_subsidy_qty_includes_knock_out_day(self) -> None:
        struct = {
            "kind": "DEC",
            "entry_price": 815.0,
            "strike_price": 830.78,
            "barrier_out": 808.0,
            "multiple": 3.0,
            "subsidy_per_ton": 5.0,
        }

        res = self.app._sm_fixed_subsidy(
            struct,
            803.0,
            self._day_ctx("2026-05-18", total_days=10, observed_days=1, base_qty=1000.0),
            {},
        )

        self.assertEqual(res["status"], "\u6572\u51fa\u7194\u65ad")
        self.assertTrue(res["terminate"])
        self.assertAlmostEqual(float(res["qty"]), 0.0)
        self.assertAlmostEqual(float(res["subsidy_qty"]), 9000.0)
        self.assertAlmostEqual(float(res["subsidy_pnl"]), 45000.0)

    def test_melt_range_subsidy_keeps_range_logic_and_melts_on_knock_out(self) -> None:
        struct = {
            "kind": "ACC",
            "entry_price": 100.0,
            "strike_price": 100.0,
            "barrier_out": 110.0,
            "multiple": 3.0,
            "subsidy_per_ton": 5.0,
        }

        hit_strike = self.app._sm_melt_range_subsidy(
            struct,
            100.0,
            self._day_ctx("2026-04-01", total_days=5, observed_days=0, base_qty=1000.0),
            {},
        )
        range_day = self.app._sm_melt_range_subsidy(
            struct,
            105.0,
            self._day_ctx("2026-04-02", total_days=5, observed_days=1, base_qty=1000.0),
            {},
        )
        melt_state = {}
        melt_day = self.app._sm_melt_range_subsidy(
            struct,
            110.0,
            self._day_ctx("2026-04-03", total_days=5, observed_days=2, base_qty=1000.0),
            melt_state,
        )

        self.assertEqual(hit_strike["status"], "敲入")
        self.assertAlmostEqual(float(hit_strike["qty"]), 3000.0)
        self.assertEqual(range_day["status"], "区间补贴")
        self.assertAlmostEqual(float(range_day["qty"]), 0.0)
        self.assertAlmostEqual(float(range_day["subsidy_qty"]), 1000.0)
        self.assertAlmostEqual(float(range_day["subsidy_pnl"]), 5000.0)
        self.assertEqual(melt_day["status"], "敲出熔断")
        self.assertTrue(melt_day["terminate"])
        self.assertTrue(melt_state["terminated"])
        self.assertAlmostEqual(float(melt_day["qty"]), 0.0)
        self.assertAlmostEqual(float(melt_day["subsidy_qty"]), 3000.0)
        self.assertAlmostEqual(float(melt_day["subsidy_pnl"]), 15000.0)

    def test_melt_range_subsidy_compute_ledgers_terminates_after_melt(self) -> None:
        self._insert_structure(
            structure_id="MELT_LEDGER",
            name="melt-range-ledger",
            kind="ACC",
            strategy="MELT_RANGE_SUBSIDY",
            strategy_code="MELT_RANGE_SUBSIDY",
            start_date="2026-04-01",
            end_date="2026-04-03",
            base_qty_per_day=100.0,
            entry_price=100.0,
            strike_price=90.0,
            barrier_out=120.0,
            knock_out_price=120.0,
            params_json=json.dumps({"multiplier": 3.0, "subsidy_per_ton": 5.0}, ensure_ascii=False),
            meta_json=json.dumps({"ko_terminate": True}, ensure_ascii=False),
        )
        self._insert_prices(
            [
                ("2026-04-01", "I.TEST", 100.0),
                ("2026-04-02", "I.TEST", 121.0),
                ("2026-04-03", "I.TEST", 100.0),
            ]
        )

        struct_df, _, bounds_df = self.app.compute_ledgers(self.conn, as_of_date="2026-04-03")
        cut = struct_df[struct_df["structure_id"].astype(str) == "MELT_LEDGER"].sort_values("date").reset_index(drop=True)
        bcut = bounds_df[
            (bounds_df["level"].astype(str) == "STRUCTURE")
            & (bounds_df["structure_id"].astype(str) == "MELT_LEDGER")
        ].reset_index(drop=True)

        self.assertEqual(cut["raw_status"].tolist(), ["区间补贴", "敲出熔断"])
        self.assertAlmostEqual(float(cut.loc[0, "day_subsidy_pnl"]), 500.0)
        self.assertAlmostEqual(float(cut.loc[1, "day_subsidy_pnl"]), 1000.0)
        self.assertEqual(int(cut.loc[1, "remaining_trading_days"]), 1)
        self.assertFalse(bcut.empty)
        self.assertAlmostEqual(float(bcut.iloc[-1]["remaining_max_qty"]), 0.0)

    def test_snowball_equal_boundaries_trigger_knock_in_and_knock_out(self) -> None:
        struct = {
            "kind": "DEC",
            "start_date": "2026-04-01",
            "end_date": "2026-04-08",
            "entry_price": 100.0,
            "strike_price": 100.0,
            "barrier_in": 105.0,
            "barrier_out": 95.0,
            "knock_out_price": 95.0,
            "params": {
                "sb_term_unit": "WEEK",
                "sb_term_count": 1,
                "sb_ko_obs_freq": "WEEKLY",
                "sb_lock_ko_obs": 0,
                "sb_notional_amount": 100000.0,
                "sb_coupon_pct": 10.0,
                "sb_floor_enabled": True,
                "sb_discount_enabled": False,
            },
        }

        ki_state = {}
        ki_res = self.app._sm_snowball(
            struct,
            104.9999996,
            self._snowball_day_ctx(struct, "2026-04-01"),
            ki_state,
        )
        self.assertEqual(ki_res["status"], "雪球已敲入计息中")
        self.assertTrue(ki_res["snowball_knocked_in"])

        ko_runtime_state = {}
        runtime = self.app._snowball_runtime(struct, ko_runtime_state)
        obs_date = runtime["ko_observations"][0]["obs_date"].strftime("%Y-%m-%d")
        ko_res = self.app._sm_snowball(
            struct,
            95.0000004,
            self._snowball_day_ctx(struct, obs_date),
            ko_runtime_state,
        )
        self.assertEqual(ko_res["status"], "雪球敲出")
        self.assertTrue(ko_res["terminate"])

    def test_fixed_subsidy_trigger_price_is_reported_as_melt_price(self) -> None:
        self.assertIn("FIXED_SUBSIDY", self.app.MELT_TRIGGER_PRICE_STRATEGY_CODES)
        self.assertEqual(self.app.trigger_price_label_for_strategy("FIXED_SUBSIDY"), "\u7194\u65ad\u4ef7")
        self.assertEqual(self.app.split_trigger_price_value("FIXED_SUBSIDY", 90.0), (None, 90.0))
        self.assertTrue(self.app.is_monitor_melt_strategy("FIXED_SUBSIDY"))


if __name__ == "__main__":
    unittest.main()
