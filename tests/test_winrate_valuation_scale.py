import importlib.util
import numpy as np
import pandas as pd
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_winrate_valuation_scale_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WinrateValuationScaleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_airbag_unit_value_uses_full_initial_scale_not_trs_fallback(self) -> None:
        resolved = {
            "strategy_code": "SAFETY_AIRBAG",
            "kind": "DEC",
            "base_qty_per_day": 6363.636363636364,
            "trs_position_qty": 6363.636363636364,
            "n_days": 11,
            "params": {"n_days": 11},
            "meta": {},
        }
        template = {"resolved": resolved, "strategy_code": "SAFETY_AIRBAG", "path_len": 3}

        meta = self.app.winrate_structure_initial_scale_meta(
            template,
            {"total_days": 3, "remaining_days": 3, "live_remaining_days": 3},
        )

        self.assertAlmostEqual(float(meta["initial_scale_qty"]), 70000.0, places=6)
        self.assertEqual(str(meta["initial_scale_source"]), "每日基准量×全周期交易日")

        valuation = self.app.winrate_attach_valuation_scale_fields(
            {"value": -1314741.55, "p05": -4490574.55, "distribution_stats": {"mean": -1314741.55}},
            template=template,
            runtime_state_seed={"total_days": 3, "remaining_days": 3, "live_remaining_days": 3},
        )
        self.assertAlmostEqual(float(valuation["unit_value"]), -1314741.55 / 70000.0, places=8)
        self.assertAlmostEqual(float(valuation["unit_p05"]), -4490574.55 / 70000.0, places=8)

    def test_single_notional_strategies_keep_single_scale(self) -> None:
        trs_template = {
            "resolved": {
                "strategy_code": "TRS",
                "base_qty_per_day": 3000.0,
                "trs_position_qty": 3000.0,
                "n_days": 37,
                "params": {"trs_position_qty": 3000.0},
                "meta": {},
            },
            "strategy_code": "TRS",
        }
        vanilla_template = {
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "base_qty_per_day": 50000.0,
                "n_days": 85,
                "params": {},
                "meta": {},
            },
            "strategy_code": self.app.VANILLA_OPTION_CODE,
        }

        trs_meta = self.app.winrate_structure_initial_scale_meta(trs_template, {"total_days": 37})
        vanilla_meta = self.app.winrate_structure_initial_scale_meta(vanilla_template, {"total_days": 85})

        self.assertAlmostEqual(float(trs_meta["initial_scale_qty"]), 3000.0, places=8)
        self.assertAlmostEqual(float(vanilla_meta["initial_scale_qty"]), 50000.0, places=8)

    def test_valuation_adjustment_moves_distribution_consistently(self) -> None:
        adjusted = self.app.winrate_apply_valuation_adjustment(
            {
                "path_values": [0.0, 100.0],
                "value": 50.0,
                "price": 50.0,
                "std": 50.0,
                "p05": 5.0,
                "p50": 50.0,
                "p95": 95.0,
                "distribution_stats": {"mean": 50.0, "std": 50.0, "p05": 5.0, "p50": 50.0, "p95": 95.0},
                "initial_scale_qty": 10.0,
                "initial_scale_value": 50.0,
                "unit_value": 5.0,
            },
            valuation_multiplier=0.8,
            unit_value_shift=-1.0,
        )

        self.assertAlmostEqual(float(adjusted["value"]), 30.0, places=8)
        self.assertAlmostEqual(float(adjusted["unit_value"]), 3.0, places=8)
        self.assertAlmostEqual(float(adjusted["std"]), 40.0, places=8)
        self.assertAlmostEqual(float(adjusted["unit_std"]), 4.0, places=8)
        self.assertAlmostEqual(float(adjusted["p05"]), -6.0, places=8)
        self.assertAlmostEqual(float(adjusted["p95"]), 66.0, places=8)

    def test_price_path_simulation_applies_optional_drift(self) -> None:
        no_drift = self.app.winrate_simulate_price_paths(
            start_price=100.0,
            n_days=252,
            atm_iv_pct=0.0001,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=11,
            seed_hint="drift-test",
        )
        with_drift = self.app.winrate_simulate_price_paths(
            start_price=100.0,
            n_days=252,
            atm_iv_pct=0.0001,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            drift_pct=5.0,
            seed=11,
            seed_hint="drift-test",
        )

        no_drift_mean = float(np.mean(np.asarray(no_drift["terminal_prices"], dtype=float)))
        with_drift_mean = float(np.mean(np.asarray(with_drift["terminal_prices"], dtype=float)))
        self.assertGreater(with_drift_mean, no_drift_mean + 4.0)

    def test_fixed_price_daily_valuation_multiplier_revalues_unit_rows(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 5,
            "template_dates": ["2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28"],
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }
        common_kwargs = dict(
            fixed_price=100.0,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=123,
            seed_hint="daily-valuation-multiplier-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
        )

        base = self.app.winrate_run_fixed_price_daily_valuation(
            template,
            valuation_multiplier=1.0,
            **common_kwargs,
        )
        scaled = self.app.winrate_run_fixed_price_daily_valuation(
            template,
            valuation_multiplier=1.04,
            **common_kwargs,
        )
        base_unit = base["daily_df"].iloc[:, 4].to_numpy(dtype=float)
        scaled_unit = scaled["daily_df"].iloc[:, 4].to_numpy(dtype=float)

        np.testing.assert_allclose(scaled_unit, base_unit * 1.04, rtol=0.0, atol=1e-10)
        self.assertAlmostEqual(float(scaled["valuation_multiplier"]), 1.04, places=12)

    def test_black76_vanilla_buy_value_uses_fair_value_minus_book_premium(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 252,
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }

        result = self.app.winrate_run_structure_valuation(
            template,
            start_price=100.0,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=10000,
            trading_days_per_year=252,
            seed=7,
            seed_hint="black76-test",
            n_days_override=252,
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
        )

        self.assertEqual(result["valuation_model"], self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN)
        self.assertAlmostEqual(float(result["black76_unit_fair_value"]), 7.965567455405804, places=8)
        self.assertAlmostEqual(float(result["initial_scale_value"]), (7.965567455405804 - 5.0) * 10.0, places=8)
        self.assertAlmostEqual(float(result["unit_value"]), 7.965567455405804 - 5.0, places=8)

    def test_vanilla_monte_carlo_summary_includes_payoff_distribution(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "kind": "ACC",
            "entry_price": 100.0,
            "strike_price": 100.0,
            "premium": 5.0,
            "notional_qty": 10.0,
            "option_type": "call",
            "side": "buy",
            "path_len": 5,
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }

        result = self.app.winrate_run_monte_carlo(
            template,
            start_price=100.0,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=23,
            seed_hint="vanilla-mc-summary-test",
        )
        terminal_prices = np.asarray(result["terminal_prices"], dtype=float)
        expected_summary = self.app.winrate_vanilla_payoff_summary(
            self.app.winrate_vanilla_payoff_for_terminal_prices(
                terminal_prices,
                template,
                start_price=100.0,
                scale_levels_by_history_start=True,
            )
        )
        summary = result["summary"]

        self.assertIn("vanilla_summary", summary)
        self.assertAlmostEqual(float(summary["vanilla_profit_prob"]), float(expected_summary["profit_prob"]), places=12)
        self.assertAlmostEqual(float(summary["vanilla_exercise_prob"]), float(expected_summary["exercise_prob"]), places=12)
        self.assertAlmostEqual(
            float(summary["vanilla_summary"]["expected_total_pnl"]),
            float(expected_summary["expected_total_pnl"]),
            places=8,
        )

    def test_vanilla_live_frozen_mc_uses_current_payoff_scenario(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "kind": "DEC",
            "entry_price": 110.0,
            "strike_price": 100.0,
            "premium": 5.0,
            "notional_qty": 10.0,
            "option_type": "call",
            "side": "sell",
            "path_len": 0,
            "evaluation_basis": "live",
            "runtime_state_seed": {
                "current_price": 110.0,
                "remaining_days": 0,
                "live_remaining_days": 0,
            },
            "live_trigger_lines": {
                "strike_level_abs": 100.0,
                "premium_abs": 5.0,
            },
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "DEC",
                "option_type": "call",
                "side": "sell",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }
        seed = {
            "current_price": 110.0,
            "remaining_days": 0,
            "live_remaining_days": 0,
        }

        result = self.app.winrate_run_monte_carlo(
            template,
            start_price=110.0,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=29,
            seed_hint="vanilla-live-frozen-mc-test",
            evaluation_basis="live",
            runtime_state_seed=seed,
        )
        summary = result["summary"]

        self.assertEqual(str(result["frozen_reason"]), "remaining_days_exhausted")
        self.assertAlmostEqual(float(summary["vanilla_loss_prob"]), 1.0, places=12)
        self.assertAlmostEqual(float(summary["fail_rate"]), 1.0, places=12)
        self.assertAlmostEqual(float(summary["vanilla_summary"]["expected_unit_pnl"]), -5.0, places=8)
        self.assertAlmostEqual(float(summary["vanilla_summary"]["expected_total_pnl"]), -50.0, places=8)

    def test_vanilla_live_frozen_history_uses_current_payoff_scenario(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "kind": "DEC",
            "entry_price": 110.0,
            "strike_price": 100.0,
            "premium": 5.0,
            "notional_qty": 10.0,
            "option_type": "call",
            "side": "sell",
            "path_len": 0,
            "evaluation_basis": "live",
            "runtime_state_seed": {
                "current_price": 110.0,
                "remaining_days": 0,
                "live_remaining_days": 0,
            },
            "live_trigger_lines": {
                "strike_level_abs": 100.0,
                "premium_abs": 5.0,
            },
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "DEC",
                "option_type": "call",
                "side": "sell",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }
        price_df = pd.DataFrame(
            [
                {"dt": "2026-04-24", "settle": 108.0},
                {"dt": "2026-04-27", "settle": 110.0},
            ]
        )

        result = self.app.winrate_run_history_backtest(
            template,
            price_df,
            bin_count=5,
            evaluation_basis="live",
            runtime_state_seed={
                "current_price": 110.0,
                "remaining_days": 0,
                "live_remaining_days": 0,
            },
            scale_levels_by_history_start=False,
        )
        summary = result["summary"]

        self.assertAlmostEqual(float(summary["vanilla_loss_prob"]), 1.0, places=12)
        self.assertAlmostEqual(float(summary["fail_rate"]), 1.0, places=12)
        self.assertAlmostEqual(float(summary["vanilla_summary"]["expected_total_pnl"]), -50.0, places=8)
        self.assertAlmostEqual(float(result["sample_df"].loc[0, "unit_pnl"]), -5.0, places=8)

    def test_structure_valuation_default_path_count_is_raised(self) -> None:
        self.assertEqual(int(self.app.WINRATE_STRUCTURE_VALUATION_PATHS_DEFAULT), 10000)
        self.assertGreaterEqual(int(self.app.WINRATE_STRUCTURE_VALUATION_PATHS_MAX), 200000)

    def test_structure_valuation_surface_builds_price_time_grid(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 5,
            "template_dates": ["2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28"],
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }

        result = self.app.winrate_run_structure_valuation_surface(
            template,
            center_price=100.0,
            price_range_pct=8.0,
            price_points=3,
            time_points=3,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=11,
            seed_hint="surface-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
        )

        self.assertEqual(tuple(result["unit_value_matrix"].shape), (3, 3))
        self.assertEqual(tuple(result["total_value_matrix"].shape), (3, 3))
        self.assertEqual(len(result["date_labels"]), 3)
        self.assertEqual(result["date_labels"][0], "2026-04-22")
        self.assertEqual(result["date_labels"][-1], "2026-04-28")
        self.assertEqual(result["time_axis_scope"], "full_structure")
        self.assertAlmostEqual(float(result["price_grid"][0]), 92.0, places=8)
        self.assertAlmostEqual(float(result["price_grid"][-1]), 108.0, places=8)
        self.assertEqual(int(result["path_count"]), 1000)

    def test_structure_valuation_surface_tracks_valuation_iv_and_skew_inputs(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 5,
            "template_dates": ["2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28"],
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }
        common_kwargs = dict(
            center_price=100.0,
            price_range_pct=8.0,
            price_points=5,
            time_points=3,
            paths=1000,
            trading_days_per_year=252,
            seed=123,
            seed_hint="surface-vol-link-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_CURRENT_MC,
        )

        low_iv = self.app.winrate_run_structure_valuation_surface(
            template,
            atm_iv_pct=10.0,
            skew=0.0,
            **common_kwargs,
        )
        high_iv = self.app.winrate_run_structure_valuation_surface(
            template,
            atm_iv_pct=50.0,
            skew=0.0,
            **common_kwargs,
        )
        skewed = self.app.winrate_run_structure_valuation_surface(
            template,
            atm_iv_pct=50.0,
            skew=1.0,
            **common_kwargs,
        )

        self.assertAlmostEqual(float(low_iv["atm_iv_pct"]), 10.0, places=8)
        self.assertAlmostEqual(float(high_iv["atm_iv_pct"]), 50.0, places=8)
        self.assertAlmostEqual(float(skewed["skew"]), 1.0, places=8)
        self.assertGreater(
            float(np.max(np.abs(np.asarray(low_iv["unit_value_matrix"]) - np.asarray(high_iv["unit_value_matrix"])))),
            1e-6,
        )
        self.assertGreater(
            float(np.max(np.abs(np.asarray(high_iv["unit_value_matrix"]) - np.asarray(skewed["unit_value_matrix"])))),
            1e-6,
        )

    def test_point_iv_scenario_parser_accepts_multiple_separators(self) -> None:
        values = self.app.winrate_parse_iv_scenario_values("20, 30；50 60% / 50、0", fallback_iv=25.0)

        self.assertEqual(values, [20.0, 30.0, 50.0, 60.0])

    def test_surface_point_iv_scenarios_revalue_same_point_by_iv(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 5,
            "template_dates": ["2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28"],
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }
        surface = self.app.winrate_run_structure_valuation_surface(
            template,
            center_price=100.0,
            price_range_pct=8.0,
            price_points=5,
            time_points=3,
            atm_iv_pct=50.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=456,
            seed_hint="surface-point-iv-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_CURRENT_MC,
        )
        tidx = 0
        pidx = 2
        selected_point = {
            "date_label": surface["date_labels"][tidx],
            "time_index": float(np.asarray(surface["time_indices"], dtype=float)[tidx]),
            "price": float(np.asarray(surface["price_grid"], dtype=float)[pidx]),
            "remaining_days": float(np.asarray(surface["remaining_days_matrix"], dtype=float)[tidx, pidx]),
        }

        scenario_df = self.app.winrate_run_surface_point_iv_scenarios(
            template,
            surface,
            selected_point,
            [10.0, 50.0],
        )

        self.assertEqual(list(scenario_df["IV(%)"]), [10.0, 50.0])
        self.assertTrue((scenario_df["估值日期"] == selected_point["date_label"]).all())
        self.assertTrue(np.allclose(scenario_df["估值价格"].to_numpy(dtype=float), selected_point["price"]))
        self.assertGreater(
            abs(float(scenario_df.loc[0, "每吨/每份估值"]) - float(scenario_df.loc[1, "每吨/每份估值"])),
            1e-6,
        )
        self.assertAlmostEqual(
            float(scenario_df.loc[1, "每吨/每份估值"]),
            float(np.asarray(surface["unit_value_matrix"], dtype=float)[tidx, pidx]),
            places=8,
        )

    def test_valuation_surface_cache_match_rejects_stale_volatility_meta(self) -> None:
        result = {
            "center_price": 796.0,
            "price_range_pct": 6.0,
            "price_points": 80,
            "requested_time_points": 20,
            "path_count": 10000,
            "atm_iv_pct": 20.0,
            "skew": 0.0,
            "trading_days_per_year": 252,
            "valuation_multiplier": 0.95,
            "unit_value_shift": 0.0,
            "valuation_model": self.app.WINRATE_STRUCTURE_VALUATION_MODEL_CURRENT_MC,
            "risk_free_rate_pct": 2.0,
            "carry_yield_pct": 0.0,
            "futures_mode": True,
        }

        self.assertTrue(
            self.app.winrate_valuation_surface_result_matches_request(
                result,
                center_price=796.0,
                price_range_pct=6.0,
                price_points=80,
                time_points=20,
                atm_iv_pct=20.0,
                skew=0.0,
                paths=10000,
                trading_days_per_year=252,
                valuation_multiplier=0.95,
                unit_value_shift=0.0,
                valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_CURRENT_MC,
                risk_free_rate_pct=2.0,
                carry_yield_pct=0.0,
                futures_mode=True,
            )
        )
        self.assertFalse(
            self.app.winrate_valuation_surface_result_matches_request(
                result,
                center_price=796.0,
                price_range_pct=6.0,
                price_points=80,
                time_points=20,
                atm_iv_pct=50.0,
                skew=0.0,
                paths=10000,
                trading_days_per_year=252,
                valuation_multiplier=0.95,
                unit_value_shift=0.0,
                valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_CURRENT_MC,
                risk_free_rate_pct=2.0,
                carry_yield_pct=0.0,
                futures_mode=True,
            )
        )

    def test_structure_valuation_surface_adds_linear_futures_overlay_and_spread(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 5,
            "template_dates": ["2026-04-22", "2026-04-23", "2026-04-24", "2026-04-27", "2026-04-28"],
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "DEC",
                "option_type": "put",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }

        result = self.app.winrate_run_structure_valuation_surface(
            template,
            center_price=100.0,
            price_range_pct=8.0,
            price_points=3,
            time_points=3,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=41,
            seed_hint="surface-futures-overlay-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
        )

        expected_unit_row = np.asarray([8.0, 0.0, -8.0], dtype=float)
        expected_unit = np.repeat(expected_unit_row.reshape(1, -1), 3, axis=0)
        np.testing.assert_allclose(result["futures_unit_value_matrix"], expected_unit, rtol=0.0, atol=1e-10)
        np.testing.assert_allclose(result["futures_total_value_matrix"], expected_unit * 10.0, rtol=0.0, atol=1e-10)
        np.testing.assert_allclose(
            result["option_futures_unit_spread_matrix"],
            np.asarray(result["unit_value_matrix"], dtype=float) - expected_unit,
            rtol=0.0,
            atol=1e-10,
        )
        np.testing.assert_allclose(
            result["option_futures_total_spread_matrix"],
            np.asarray(result["total_value_matrix"], dtype=float) - expected_unit * 10.0,
            rtol=0.0,
            atol=1e-10,
        )
        self.assertEqual(result["futures_overlay_meta"]["direction_sign"], -1)
        self.assertEqual(result["futures_overlay_meta"]["direction_label"], "看跌期货")

    def test_entry_price_axis_marker_includes_entry_tick(self) -> None:
        marker = self.app.winrate_entry_price_axis_marker_meta(
            np.asarray([92.0, 100.0, 108.0], dtype=float),
            100.0,
            max_base_ticks=4,
        )

        self.assertTrue(marker["visible"])
        self.assertIn(100.0, [round(float(x), 8) for x in marker["tickvals"]])
        self.assertTrue(any("入场价" in str(x) for x in marker["ticktext"]))

    def test_current_time_axis_marker_marks_first_date(self) -> None:
        marker = self.app.winrate_current_time_axis_marker_meta(
            np.asarray([1.0, 5.0, 10.0], dtype=float),
            ["2026-04-15", "2026-04-22", "2026-05-06"],
        )

        self.assertTrue(marker["visible"])
        self.assertAlmostEqual(float(marker["time_value"]), 1.0, places=8)
        self.assertEqual(str(marker["label"]), "2026-04-15")
        self.assertTrue(any("当前时间" in str(x) or "褰撳墠鏃堕棿" in str(x) for x in marker["ticktext"]))

    def test_current_time_axis_marker_uses_reference_date(self) -> None:
        marker = self.app.winrate_current_time_axis_marker_meta(
            np.asarray([1.0, 5.0, 10.0], dtype=float),
            ["2026-04-15", "2026-04-22", "2026-05-06"],
            reference_date="2026-04-30",
        )

        self.assertTrue(marker["visible"])
        self.assertEqual(str(marker["label"]), "2026-04-30")
        expected = 5.0 + (10.0 - 5.0) * (8.0 / 14.0)
        self.assertAlmostEqual(float(marker["time_value"]), expected, places=8)

    def test_daily_spread_boundary_points_interpolate_crossings(self) -> None:
        price_grid = np.asarray([90.0, 100.0, 110.0], dtype=float)
        time_indices = np.asarray([1.0, 2.0], dtype=float)
        unit_matrix = np.asarray([[-2.0, 2.0, -2.0], [3.0, 0.0, -2.0]], dtype=float)
        total_matrix = unit_matrix * 10.0
        zero_matrix = np.zeros_like(unit_matrix)

        rows = self.app._winrate_daily_spread_boundary_surface_points(
            price_grid=price_grid,
            time_indices=time_indices,
            date_labels=["2026-04-22", "2026-04-23"],
            unit_matrix=unit_matrix,
            total_matrix=total_matrix,
            remaining_matrix=np.ones_like(unit_matrix),
            futures_unit_matrix=zero_matrix,
            futures_total_matrix=zero_matrix,
            spread_unit_matrix=unit_matrix,
            spread_total_matrix=total_matrix,
            spread_matrix=unit_matrix,
            boundary_value_matrix=unit_matrix,
            z_title="期权-期货每吨/每份价差",
            spread_title="期权-期货每吨/每份价差",
        )

        self.assertEqual(len(rows), 3)
        self.assertEqual([row["date_label"] for row in rows], ["2026-04-22", "2026-04-22", "2026-04-23"])
        np.testing.assert_allclose([float(row["price"]) for row in rows], [95.0, 105.0, 100.0], rtol=0.0, atol=1e-10)
        self.assertEqual([int(row["boundary_rank_in_date"]) for row in rows], [1, 2, 1])
        self.assertEqual(str(rows[0]["boundary_direction"]), "进入期权超额区")
        self.assertEqual(str(rows[1]["boundary_direction"]), "离开期权超额区")
        self.assertEqual(str(rows[-1]["boundary_direction"]), "网格点相等")
        self.assertAlmostEqual(float(rows[0]["boundary_spread_value"]), 0.0, places=8)

    def test_best_excess_boundary_chart_splits_boundary_branches(self) -> None:
        rows = [
            {"tidx": 0, "date_label": "2026-04-20", "price": 760.0, "boundary_spread_value": 0.0, "boundary_value": -40.0, "unit_value": -40.0, "futures_unit_value": -40.0, "total_value": -400.0, "futures_total_value": -400.0, "boundary_rank_in_date": 1, "boundary_direction": "enter"},
            {"tidx": 0, "date_label": "2026-04-20", "price": 805.0, "boundary_spread_value": 0.0, "boundary_value": -20.0, "unit_value": -20.0, "futures_unit_value": -20.0, "total_value": -200.0, "futures_total_value": -200.0, "boundary_rank_in_date": 2, "boundary_direction": "leave"},
            {"tidx": 1, "date_label": "2026-04-21", "price": 762.0, "boundary_spread_value": 0.0, "boundary_value": -39.0, "unit_value": -39.0, "futures_unit_value": -39.0, "total_value": -390.0, "futures_total_value": -390.0, "boundary_rank_in_date": 1, "boundary_direction": "enter"},
            {"tidx": 1, "date_label": "2026-04-21", "price": 807.0, "boundary_spread_value": 0.0, "boundary_value": -19.0, "unit_value": -19.0, "futures_unit_value": -19.0, "total_value": -190.0, "futures_total_value": -190.0, "boundary_rank_in_date": 2, "boundary_direction": "leave"},
        ]

        fig = self.app.winrate_build_best_excess_boundary_plotly_chart(
            rows,
            spread_title="spread",
            value_title="value",
        )

        self.assertEqual(fig.layout.title.text, "\u671f\u6743-\u671f\u8d27\u8d85\u989d\u5206\u754c\u7ebf")
        self.assertEqual(len(fig.data), 2)
        self.assertEqual(list(fig.data[0].y), [760.0, 762.0])
        self.assertEqual(list(fig.data[1].y), [805.0, 807.0])

    def test_accumulator_vectorized_valuation_matches_state_loop(self) -> None:
        template = {
            "strategy_code": "FIXED_SUBSIDY",
            "path_len": 4,
            "resolved": {
                "strategy_code": "FIXED_SUBSIDY",
                "kind": "DEC",
                "base_qty_per_day": 100.0,
                "entry_price": 760.0,
                "strike_price": 790.0,
                "barrier_out": 752.0,
                "multiple": 3.0,
                "subsidy_per_ton": 5.0,
                "params": {},
                "meta": {"ko_terminate": True},
            },
        }
        prices = np.asarray(
            [
                [780.0, 795.0, 800.0, 805.0],
                [780.0, 751.0, 750.0, 749.0],
                [780.0, 785.0, 792.0, 788.0],
                [780.0, 755.0, 754.0, 753.0],
            ],
            dtype=float,
        )

        vectorized = self.app.winrate_estimate_structure_path_values(template, prices)
        state_loop = self.app.winrate_estimate_structure_path_values(template, prices, force_state_loop=True)

        np.testing.assert_allclose(vectorized, state_loop, rtol=1e-10, atol=1e-10)

    def test_self_quote_float_ko_counts_knockout_day_in_remaining_qty(self) -> None:
        template = {
            "strategy_code": "FLOAT_KO",
            "path_len": 3,
            "resolved": {
                "strategy_code": "FLOAT_KO",
                "kind": "DEC",
                "base_qty_per_day": 1000.0,
                "entry_price": 815.0,
                "strike_price": 830.0,
                "barrier_out": 808.0,
                "knock_out_price": 808.0,
                "ko_strike_price": 815.0,
                "multiple": 3.0,
                "params": {},
                "meta": {"ko_terminate": True},
            },
        }
        prices = np.asarray([[803.0, 803.0, 803.0]], dtype=float)

        vectorized = self.app.winrate_estimate_structure_path_values(template, prices)
        state_loop = self.app.winrate_estimate_structure_path_values(template, prices, force_state_loop=True)

        np.testing.assert_allclose(vectorized, state_loop, rtol=1e-10, atol=1e-10)
        self.assertAlmostEqual(float(vectorized[0]), 36000.0)

    def test_self_quote_fixed_subsidy_counts_knockout_day_in_subsidy_qty(self) -> None:
        template = {
            "strategy_code": "FIXED_SUBSIDY",
            "path_len": 3,
            "resolved": {
                "strategy_code": "FIXED_SUBSIDY",
                "kind": "DEC",
                "base_qty_per_day": 1000.0,
                "entry_price": 815.0,
                "strike_price": 830.0,
                "barrier_out": 808.0,
                "multiple": 3.0,
                "subsidy_per_ton": 5.0,
                "params": {},
                "meta": {"ko_terminate": True},
            },
        }
        prices = np.asarray([[803.0, 803.0, 803.0]], dtype=float)

        vectorized = self.app.winrate_estimate_structure_path_values(template, prices)
        state_loop = self.app.winrate_estimate_structure_path_values(template, prices, force_state_loop=True)

        np.testing.assert_allclose(vectorized, state_loop, rtol=1e-10, atol=1e-10)
        self.assertAlmostEqual(float(vectorized[0]), 15000.0)

    def test_structure_valuation_surface_uses_full_contract_dates_when_template_dates_are_truncated(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 11,
            "template_dates": ["2026-04-13"],
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "start_date": "2026-04-13",
                "end_date": "2026-04-27",
                "params": {},
                "meta": {},
            },
        }

        result = self.app.winrate_run_structure_valuation_surface(
            template,
            center_price=100.0,
            price_range_pct=8.0,
            price_points=3,
            time_points=12,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=12,
            seed_hint="surface-full-cycle-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
        )

        self.assertEqual(int(result["time_points"]), 11)
        self.assertEqual(tuple(result["unit_value_matrix"].shape), (11, 3))
        self.assertEqual(result["date_labels"][0], "2026-04-13")
        self.assertEqual(result["date_labels"][-1], "2026-04-27")
        self.assertEqual(result["time_axis_scope"], "full_structure")

    def test_structure_valuation_surface_treats_normalized_empty_seed_as_full_cycle(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 11,
            "template_dates": ["2026-04-13"],
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "start_date": "2026-04-13",
                "end_date": "2026-04-27",
                "params": {},
                "meta": {},
            },
        }
        normalized_empty_seed = self.app.runtime_state_seed_to_dict({})

        result = self.app.winrate_run_structure_valuation_surface(
            template,
            center_price=100.0,
            price_range_pct=8.0,
            price_points=3,
            time_points=8,
            atm_iv_pct=20.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=13,
            seed_hint="surface-normalized-empty-seed-test",
            runtime_state_seed=normalized_empty_seed,
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
        )

        self.assertEqual(int(result["time_points"]), 8)
        self.assertEqual(tuple(result["unit_value_matrix"].shape), (8, 3))
        self.assertEqual(result["date_labels"][0], "2026-04-13")
        self.assertEqual(result["date_labels"][-1], "2026-04-27")
        self.assertEqual(result["time_axis_scope"], "full_structure")

    def test_surface_defaults_support_current_grid_without_work_unit_rejection(self) -> None:
        self.assertEqual(float(self.app.WINRATE_STRUCTURE_VALUATION_MULTIPLIER_PCT_DEFAULT), 100.0)
        self.assertEqual(float(self.app.WINRATE_STRUCTURE_VALUATION_SURFACE_RANGE_PCT_DEFAULT), 6.0)
        self.assertEqual(int(self.app.WINRATE_STRUCTURE_VALUATION_SURFACE_PRICE_POINTS_DEFAULT), 80)
        self.assertEqual(int(self.app.WINRATE_STRUCTURE_VALUATION_SURFACE_TIME_POINTS_DEFAULT), 20)
        self.assertEqual(int(self.app.WINRATE_STRUCTURE_VALUATION_SURFACE_PATHS_DEFAULT), 10000)
        self.assertGreaterEqual(int(self.app.WINRATE_STRUCTURE_VALUATION_SURFACE_MAX_WORK_UNITS), 80 * 20 * 10000)

    def test_nearest_zero_surface_points_are_returned_for_each_time_slice(self) -> None:
        price_grid = np.asarray([99.0, 100.0, 101.0, 102.0], dtype=float)
        time_indices = np.asarray([1.0, 2.0, 3.0], dtype=float)
        unit_matrix = np.asarray(
            [
                [3.0, -0.2, 0.4, 2.0],
                [1.0, 0.6, -0.1, -1.4],
                [-2.0, 0.3, 0.2, 1.0],
            ],
            dtype=float,
        )
        total_matrix = unit_matrix * 1000.0
        remaining_matrix = np.asarray([[3.0] * 4, [2.0] * 4, [1.0] * 4], dtype=float)

        rows = self.app._winrate_nearest_zero_surface_points(
            price_grid=price_grid,
            time_indices=time_indices,
            date_labels=["2026-04-10", "2026-04-17", "2026-04-24"],
            unit_matrix=unit_matrix,
            total_matrix=total_matrix,
            remaining_matrix=remaining_matrix,
            z_matrix=unit_matrix,
            z_title="每吨/每份估值",
            limit_per_time=2,
        )

        self.assertEqual(len(rows), 6)
        self.assertEqual([row["date_label"] for row in rows[0:2]], ["2026-04-10", "2026-04-10"])
        self.assertEqual([row["date_label"] for row in rows[2:4]], ["2026-04-17", "2026-04-17"])
        self.assertEqual([row["date_label"] for row in rows[4:6]], ["2026-04-24", "2026-04-24"])
        self.assertEqual([row["near_zero_rank"] for row in rows[0:2]], [1, 2])

    def test_vectorized_vanilla_path_values_match_state_loop(self) -> None:
        template = {
            "strategy_code": self.app.VANILLA_OPTION_CODE,
            "path_len": 3,
            "resolved": {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "kind": "ACC",
                "option_type": "call",
                "side": "buy",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 100.0,
                "premium": 5.0,
                "params": {},
                "meta": {},
            },
        }
        paths = np.asarray(
            [
                [100.0, 105.0, 110.0],
                [100.0, 99.0, 95.0],
                [103.0, 101.0, 108.0],
            ],
            dtype=float,
        )

        fast = self.app.winrate_estimate_structure_path_values(template, paths)
        loop = self.app.winrate_estimate_structure_path_values(template, paths, force_state_loop=True)

        np.testing.assert_allclose(fast, loop, rtol=0.0, atol=1e-10)

    def test_vectorized_trs_path_values_match_state_loop(self) -> None:
        template = {
            "strategy_code": "TRS",
            "path_len": 3,
            "resolved": {
                "strategy_code": "TRS",
                "kind": "DEC",
                "base_qty_per_day": 3000.0,
                "entry_price": 100.0,
                "trs_position_qty": 3000.0,
                "params": {"trs_position_qty": 3000.0},
                "meta": {},
            },
        }
        paths = np.asarray(
            [
                [100.0, 95.0, 90.0],
                [100.0, 104.0, 110.0],
                [98.0, 101.0, 99.0],
            ],
            dtype=float,
        )

        fast = self.app.winrate_estimate_structure_path_values(template, paths)
        loop = self.app.winrate_estimate_structure_path_values(template, paths, force_state_loop=True)

        np.testing.assert_allclose(fast, loop, rtol=0.0, atol=1e-10)

    def test_vectorized_airbag_path_values_match_state_loop(self) -> None:
        template = {
            "strategy_code": "SAFETY_AIRBAG",
            "path_len": 3,
            "resolved": {
                "strategy_code": "SAFETY_AIRBAG",
                "kind": "ACC",
                "base_qty_per_day": 10.0,
                "entry_price": 100.0,
                "strike_price": 95.0,
                "barrier_out": 90.0,
                "multiple": 80.0,
                "params": {},
                "meta": {},
            },
        }
        paths = np.asarray(
            [
                [100.0, 95.0, 80.0],
                [100.0, 101.0, 110.0],
                [100.0, 89.0, 95.0],
            ],
            dtype=float,
        )

        fast = self.app.winrate_estimate_structure_path_values(template, paths)
        loop = self.app.winrate_estimate_structure_path_values(template, paths, force_state_loop=True)

        np.testing.assert_allclose(fast, loop, rtol=0.0, atol=1e-10)

    def test_vectorized_snowball_midcycle_path_values_match_state_loop(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-06")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario["paths"] = 1000
        scenario["seed"] = 24680
        priced = self.app.volval_self_quote_apply_scenario(resolved, scenario)
        template = self.app.volval_template_with_dates(
            self.app.winrate_prepare_structure_template(priced),
            start_date_v=scenario["start_date"],
            end_date_v=scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
        )
        base_seed = self.app.winrate_default_runtime_seed_for_structure_valuation(
            template,
            fixed_price=float(scenario["spot_price"]),
        )
        base_remaining = self.app._winrate_structure_scan_n_days(template, base_seed)
        future_dates = self.app._winrate_structure_full_cycle_dates(template, base_remaining)
        day_idx = 3
        day_seed = self.app.winrate_advance_runtime_seed_fixed_price(
            template,
            base_seed,
            fixed_price=float(scenario["spot_price"]),
            steps=day_idx,
            future_dates=future_dates,
        )
        remaining = int(day_seed["remaining_days"])
        day_template = dict(template)
        day_template["path_len"] = remaining
        day_template["future_dates"] = [
            d.strftime(self.app.DATE_FMT) if hasattr(d, "strftime") else str(d)
            for d in future_dates[day_idx:]
        ]
        sim = self.app.winrate_simulate_bs_risk_neutral_price_paths(
            start_price=float(scenario["spot_price"]),
            n_days=remaining,
            atm_iv_pct=float(scenario["iv_pct"]),
            paths=1000,
            trading_days_per_year=252,
            risk_free_rate_pct=0.0,
            carry_yield_pct=0.0,
            futures_mode=True,
            seed=24680,
            seed_hint="snowball-midcycle-vectorized-test",
        )
        paths = sim["price_paths"]

        direct = self.app.winrate_estimate_structure_path_values_vectorized(
            day_template,
            paths,
            runtime_state_seed=day_seed,
            discount_rate_pct=0.0,
            trading_days_per_year=252,
            discount_cashflows=True,
        )
        fast = self.app.winrate_estimate_structure_path_values(
            day_template,
            paths,
            runtime_state_seed=day_seed,
            discount_rate_pct=0.0,
            trading_days_per_year=252,
            discount_cashflows=True,
        )
        loop = self.app.winrate_estimate_structure_path_values(
            day_template,
            paths,
            runtime_state_seed=day_seed,
            discount_rate_pct=0.0,
            trading_days_per_year=252,
            discount_cashflows=True,
            force_state_loop=True,
        )

        self.assertIsNotNone(direct)
        np.testing.assert_allclose(fast, loop, rtol=0.0, atol=1e-10)

    def test_vectorized_snowball_legacy_coupon_modes_match_state_loop(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-06")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario["paths"] = 1000
        scenario["seed"] = 24680
        scenario["spot_price"] = 815.0
        scenario["iv_pct"] = 16.0
        priced = self.app.volval_self_quote_apply_scenario(resolved, scenario)
        priced["params"]["sb_valuation_event_cashflow"] = False
        priced["params"]["sb_valuation_ki_then_ko_coupon"] = False
        priced["params"]["sb_valuation_ki_maturity_coupon"] = False
        template = self.app.volval_template_with_dates(
            self.app.winrate_prepare_structure_template(priced),
            start_date_v=scenario["start_date"],
            end_date_v=scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
        )
        base_seed = self.app.winrate_default_runtime_seed_for_structure_valuation(
            template,
            fixed_price=float(scenario["spot_price"]),
        )
        base_remaining = self.app._winrate_structure_scan_n_days(template, base_seed)
        future_dates = self.app._winrate_structure_full_cycle_dates(template, base_remaining)
        day_idx = 3
        day_seed = self.app.winrate_advance_runtime_seed_fixed_price(
            template,
            base_seed,
            fixed_price=900.0,
            steps=day_idx,
            future_dates=future_dates,
        )
        remaining = int(day_seed["remaining_days"])
        day_template = dict(template)
        day_template["path_len"] = remaining
        day_template["future_dates"] = [
            d.strftime(self.app.DATE_FMT) if hasattr(d, "strftime") else str(d)
            for d in future_dates[day_idx:]
        ]
        sim = self.app.winrate_simulate_bs_risk_neutral_price_paths(
            start_price=900.0,
            n_days=remaining,
            atm_iv_pct=float(scenario["iv_pct"]),
            paths=1000,
            trading_days_per_year=252,
            risk_free_rate_pct=2.0,
            carry_yield_pct=0.0,
            futures_mode=True,
            seed=24680,
            seed_hint="snowball-legacy-coupon-vectorized-test",
        )
        paths = sim["price_paths"]

        direct = self.app.winrate_estimate_structure_path_values_vectorized(
            day_template,
            paths,
            runtime_state_seed=day_seed,
            discount_rate_pct=2.0,
            trading_days_per_year=252,
            discount_cashflows=True,
        )
        loop = self.app.winrate_estimate_structure_path_values(
            day_template,
            paths,
            runtime_state_seed=day_seed,
            discount_rate_pct=2.0,
            trading_days_per_year=252,
            discount_cashflows=True,
            force_state_loop=True,
        )

        self.assertIsNotNone(direct)
        np.testing.assert_allclose(direct, loop, rtol=0.0, atol=1e-7)


if __name__ == "__main__":
    unittest.main()
