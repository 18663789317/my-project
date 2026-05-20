import importlib.util
import pathlib
import sqlite3
import sys
import threading
import unittest
from unittest import mock

import numpy as np


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_review_fix_regressions_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ReviewFixRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_get_session_conn_reuses_connection_per_state_only(self) -> None:
        conn_one = sqlite3.connect(":memory:")
        conn_two = sqlite3.connect(":memory:")
        self.addCleanup(conn_one.close)
        self.addCleanup(conn_two.close)
        state_one = {}
        state_two = {}

        with mock.patch.object(self.app, "get_conn", side_effect=[conn_one, conn_two]):
            first = self.app.get_session_conn(state_one)
            first_again = self.app.get_session_conn(state_one)
            second = self.app.get_session_conn(state_two)

        self.assertIs(first, conn_one)
        self.assertIs(first_again, conn_one)
        self.assertIs(second, conn_two)
        self.assertIsNot(first, second)

    def test_sync_discount_floor_checkbox_state_turns_floor_off_in_state(self) -> None:
        state = {
            "floor_key": True,
            "discount_key": True,
        }

        forced = self.app.sync_discount_floor_checkbox_state(
            "floor_key",
            "discount_key",
            "notice_key",
            state,
        )

        self.assertTrue(forced)
        self.assertFalse(state["floor_key"])
        self.assertTrue(state["notice_key"])

    def test_save_strategy_group_record_rejects_stale_create_conflict(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        self.app.init_db(conn)
        conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G001", "Original", "I.TEST"),
        )
        conn.commit()

        result = self.app.save_strategy_group_record(
            conn,
            "G001",
            "Overwritten",
            "RB.TEST",
            allow_update=False,
        )
        row = conn.execute(
            "SELECT group_name, underlying FROM strategy_group WHERE group_id=?",
            ("G001",),
        ).fetchone()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "group_id_conflict")
        self.assertEqual(tuple(row or ()), ("Original", "I.TEST"))

    def test_save_strategy_group_record_updates_existing_when_allowed(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        self.app.init_db(conn)
        conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G001", "Original", "I.TEST"),
        )
        conn.commit()

        result = self.app.save_strategy_group_record(
            conn,
            "G001",
            "Updated",
            "RB.TEST",
            allow_update=True,
        )
        row = conn.execute(
            "SELECT group_name, underlying FROM strategy_group WHERE group_id=?",
            ("G001",),
        ).fetchone()

        self.assertTrue(result["ok"])
        self.assertEqual(tuple(row or ()), ("Updated", "RB.TEST"))

    def test_save_existing_strategy_group_rows_rejects_missing_snapshot_rows(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        self.app.init_db(conn)
        conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G001", "Original", "I.TEST"),
        )
        conn.commit()

        result = self.app.save_existing_strategy_group_rows(
            conn,
            [
                {"group_id": "G001", "group_name": "Updated", "underlying": "RB.TEST"},
                {"group_id": "G002", "group_name": "Missing", "underlying": "CU.TEST"},
            ],
        )
        row = conn.execute(
            "SELECT group_name, underlying FROM strategy_group WHERE group_id=?",
            ("G001",),
        ).fetchone()

        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "group_missing")
        self.assertEqual(tuple(row or ()), ("Original", "I.TEST"))

    def test_build_structure_schedule_state_keys_are_scoped(self) -> None:
        snowball_keys = self.app.build_structure_schedule_state_keys("G001", "SNOWBALL")
        trs_keys = self.app.build_structure_schedule_state_keys("G001", "TRS")
        other_group_keys = self.app.build_structure_schedule_state_keys("G002", "SNOWBALL")

        self.assertNotEqual(snowball_keys["start"], trs_keys["start"])
        self.assertNotEqual(snowball_keys["start"], other_group_keys["start"])
        self.assertIn("G001", snowball_keys["start"])
        self.assertIn("SNOWBALL", snowball_keys["start"])

    def test_build_manual_close_form_keys_are_scoped(self) -> None:
        sid_one_keys = self.app.build_manual_close_form_keys("G001", "SB001")
        sid_two_keys = self.app.build_manual_close_form_keys("G001", "SB002")

        self.assertNotEqual(sid_one_keys["struct_close_px"], sid_two_keys["struct_close_px"])
        self.assertNotEqual(sid_one_keys["single_qty"], sid_two_keys["single_qty"])
        self.assertIn("SB001", sid_one_keys["struct_close_px"])

    def test_build_manual_close_form_keys_scope_every_editable_field(self) -> None:
        sid_one_keys = self.app.build_manual_close_form_keys("G001", "SB001")
        sid_two_keys = self.app.build_manual_close_form_keys("G001", "SB002")
        other_group_keys = self.app.build_manual_close_form_keys("G002", "SB001")

        editable_fields = [
            "struct_close_dt",
            "struct_close_px",
            "struct_close_pnl",
            "struct_close_qty",
            "single_close_dt",
            "single_qty",
            "single_manual_pnl",
        ]

        for field_name in editable_fields:
            self.assertNotEqual(sid_one_keys[field_name], sid_two_keys[field_name])
            self.assertNotEqual(sid_one_keys[field_name], other_group_keys[field_name])
            self.assertIn("G001", sid_one_keys[field_name])
            self.assertIn("SB001", sid_one_keys[field_name])

    def test_build_external_close_form_keys_are_scoped_by_group(self) -> None:
        group_one_keys = self.app.build_external_close_form_keys("G001")
        group_two_keys = self.app.build_external_close_form_keys("G002")

        for field_name in ["dt", "category", "qty", "pnl", "underlying"]:
            self.assertNotEqual(group_one_keys[field_name], group_two_keys[field_name])
            self.assertIn("G001", group_one_keys[field_name])

    def test_build_price_quick_form_keys_are_scoped_by_group(self) -> None:
        group_one_keys = self.app.build_price_quick_form_keys("G001")
        group_two_keys = self.app.build_price_quick_form_keys("G002")

        for field_name in ["underlying", "dt", "px"]:
            self.assertNotEqual(group_one_keys[field_name], group_two_keys[field_name])
            self.assertIn("G001", group_one_keys[field_name])

    def test_sql_identifier_helpers_reject_untrusted_names_and_types(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        self.app.init_db(conn)

        with self.assertRaises(ValueError):
            self.app._quote_sqlite_table("strategy_group; DROP TABLE structure")
        with self.assertRaises(ValueError):
            self.app._quote_existing_sqlite_column(conn, "strategy_group", "missing_column")
        with self.assertRaises(ValueError):
            self.app._ensure_column(conn, "strategy_group", "unsafe_col", "TEXT); DROP TABLE structure;--")

    def test_apply_close_keyword_filter_treats_regex_chars_literally(self) -> None:
        df = self.app.pd.DataFrame(
            [
                {"策略组": "G(1)", "结构": "Alpha", "结构状态": "运行中", "品种": "I.TEST", "方向": "ACC", "平仓批次号": "B1", "记录类型": "普通"},
                {"策略组": "G2", "结构": "Beta", "结构状态": "运行中", "品种": "RB.TEST", "方向": "DEC", "平仓批次号": "B2", "记录类型": "普通"},
            ]
        )

        filtered = self.app.apply_close_keyword_filter(df, "(")

        self.assertEqual(filtered["策略组"].tolist(), ["G(1)"])

    def test_report_lock_pnl_color_uses_neutral_for_zero(self) -> None:
        self.assertEqual(self.app.report_lock_pnl_color(10.0, "warn", "neg", "neutral"), "warn")
        self.assertEqual(self.app.report_lock_pnl_color(-0.01, "warn", "neg", "neutral"), "neg")
        self.assertEqual(self.app.report_lock_pnl_color(0.0, "warn", "neg", "neutral"), "neutral")

    def test_runtime_memo_cache_put_eviction_uses_shared_cache_api(self) -> None:
        cache = self.app._RuntimeMemoCache()

        self.app._memo_cache_put(cache, "a", 1, limit=2)
        self.app._memo_cache_put(cache, "b", 2, limit=2)
        self.app._memo_cache_put(cache, "c", 3, limit=2)

        self.assertNotIn("a", cache)
        self.assertEqual(cache.get("b"), 2)
        self.assertEqual(cache.get("c"), 3)

    def test_resolve_manual_structure_remaining_scale_qty_uses_latest_remaining_scale(self) -> None:
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        structures_df = self.app.pd.DataFrame(
            [{"group_id": "G001", "structure_id": "SB001", "start_date": "2026-04-01"}]
        )
        closes2_df = self.app.pd.DataFrame([{"group_id": "G001", "structure_id": "SB001"}])

        with (
            mock.patch.object(self.app, "fetch_structures", return_value=structures_df),
            mock.patch.object(self.app, "fetch_closes2", return_value=closes2_df),
            mock.patch.object(self.app, "resolve_structure_row", return_value={"structure_id": "SB001"}),
            mock.patch.object(self.app, "build_manual_structure_reduction_qty_map", return_value={"SB001": 500.0}) as reduction_mock,
            mock.patch.object(
                self.app,
                "apply_manual_structure_reduction_to_resolved_row",
                return_value={"_manual_remaining_scale_qty": 1500.0},
            ),
        ):
            result = self.app.resolve_manual_structure_remaining_scale_qty(
                conn,
                group_id="G001",
                structure_id="SB001",
                as_of_date="2026-04-18",
            )

        self.assertTrue(result["ok"])
        self.assertEqual(result["remaining_qty"], 1500.0)
        reduction_mock.assert_called_once()

    def test_probexp_fetch_openvlab_atm_iv_with_timeout_passes_http_timeout(self) -> None:
        expected = {"ok": True, "atm_iv": 12.3}

        with mock.patch.object(self.app, "probexp_fetch_openvlab_atm_iv", return_value=expected) as fetch_mock:
            result = self.app.probexp_fetch_openvlab_atm_iv_with_timeout(
                underlying="I.TEST",
                rep_date="2026-04-18",
                current_close=100.0,
                timeout_sec=1.5,
            )

        self.assertEqual(result, expected)
        fetch_mock.assert_called_once_with(
            underlying="I.TEST",
            rep_date="2026-04-18",
            current_close=100.0,
            http_timeout_sec=1.5,
        )

    def test_single_flight_dict_call_rejects_busy_duplicates(self) -> None:
        slot = threading.BoundedSemaphore(value=1)
        self.assertTrue(slot.acquire(blocking=False))
        executor = mock.Mock()

        result = self.app._run_single_flight_dict_call(
            executor=executor,
            slot=slot,
            func=lambda: {"ok": True},
            timeout_sec=1.0,
            busy_result={"ok": False, "reason": "busy"},
            timeout_result={"ok": False, "reason": "timeout"},
            invalid_result={"ok": False, "reason": "invalid"},
            error_builder=lambda exc: {"ok": False, "reason": str(exc)},
        )

        self.assertEqual(result, {"ok": False, "reason": "busy"})
        executor.submit.assert_not_called()
        slot.release()

    def test_mc_path_generators_keep_extreme_paths_finite_and_float64(self) -> None:
        common = {
            "start_price": 8000.0,
            "n_days": 3,
            "atm_iv_pct": 1_000_000.0,
            "paths": 1000,
            "trading_days_per_year": 1,
            "seed": 42,
        }

        standard = self.app.winrate_simulate_price_paths(
            **common,
            skew=500.0,
            seed_hint="finite-standard",
        )
        risk_neutral = self.app.winrate_simulate_bs_risk_neutral_price_paths(
            **common,
            seed_hint="finite-bs",
        )

        for sim in (standard, risk_neutral):
            paths = sim["price_paths"]
            self.assertEqual(paths.dtype, np.dtype("float64"))
            self.assertTrue(np.isfinite(paths).all())
            self.assertGreaterEqual(float(np.min(paths)), self.app.WINRATE_MC_PRICE_FLOOR)
            self.assertLessEqual(float(np.max(paths)), self.app.WINRATE_MC_PRICE_CAP)

    def test_snowball_runtime_rejects_invalid_dates_instead_of_today_fallback(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "日期无效"):
            self.app._snowball_runtime(
                {
                    "start_date": "not-a-date",
                    "end_date": "2026-06-10",
                    "entry_price": 800.0,
                    "barrier_in": 860.0,
                    "knock_out_price": 790.0,
                    "params": {},
                },
                {},
            )

    def test_snowball_zero_a_observations_use_stage_b_coupon_and_phase(self) -> None:
        runtime = {
            "early_mode": True,
            "a_obs": 0,
            "coupon_a_pct": 12.0,
            "coupon_b_pct": 8.0,
        }

        self.assertEqual(self.app._snowball_coupon_pct(runtime, 0), 8.0)
        self.assertEqual(self.app._snowball_coupon_pct(runtime, 1), 8.0)
        self.assertEqual(self.app._snowball_phase(runtime, 0), "B阶段")

    def test_roll_spread_rejects_unknown_kind(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown kind"):
            self.app.calc_roll_spread_pnl("BAD", 1.0, 800.0, 810.0)

    def test_snowball_template_requires_knock_in_barrier(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-06")
        resolved["barrier_in"] = None

        with self.assertRaisesRegex(RuntimeError, "敲入价"):
            self.app.winrate_prepare_structure_template(resolved)


    def test_snowball_maturity_loss_floor_caps_loss_at_knock_in_line(self) -> None:
        capped_loss = self.app._snowball_maturity_loss_from_strike(
            "DEC",
            900.0,
            800.0,
            10_000.0,
            floor_enabled=True,
            knock_in_price=864.0,
        )
        uncapped_loss = self.app._snowball_maturity_loss_from_strike(
            "DEC",
            900.0,
            800.0,
            10_000.0,
            floor_enabled=False,
            knock_in_price=864.0,
        )

        self.assertAlmostEqual(float(capped_loss), -800.0)
        self.assertAlmostEqual(float(uncapped_loss), -1250.0)


if __name__ == "__main__":
    unittest.main()
