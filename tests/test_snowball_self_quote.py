import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
from datetime import date

import numpy as np


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_snowball_self_quote_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    # app.py is a Streamlit app; importing it under unittest otherwise emits
    # bare-mode ScriptRunContext warnings that obscure test failures.
    with contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


class SnowballSelfQuoteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def _manual_snowball(self, *, paths=None):
        resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-06")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        if paths is not None:
            scenario["paths"] = int(paths)
        scenario["seed"] = 24680
        scenario["risk_free_rate_pct"] = 0.0
        scenario["carry_yield_pct"] = 0.0
        return resolved, scenario

    def test_snowball_is_available_in_volval_and_self_quote(self) -> None:
        self.assertEqual(self.app.volval_structure_type_label("SNOWBALL"), self.app.VOLVAL_STRUCTURE_TYPE_SNOWBALL)
        self.assertEqual(self.app.volval_self_quote_supported_code("SNOWBALL"), "SNOWBALL")
        self.assertIn(self.app.VOLVAL_STRUCTURE_TYPE_SNOWBALL, self.app.VOLVAL_STRUCTURE_TYPE_OPTIONS)
        self.assertEqual(
            self.app.volval_self_quote_reverse_options("SNOWBALL"),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
                self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_KO_PRICE,
                self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_KI_PRICE,
                self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_DISCOUNT_PRICE,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )

    def test_manual_snowball_defaults_match_structure_entry_shape(self) -> None:
        resolved, scenario = self._manual_snowball()
        params = resolved["params"]

        self.assertEqual(resolved["strategy_code"], "SNOWBALL")
        self.assertEqual(resolved["kind"], "DEC")
        self.assertEqual(resolved["underlying"], "\u94c1\u77ff\u77f3")
        self.assertEqual(scenario["underlying"], "\u94c1\u77ff\u77f3")
        self.assertEqual(scenario["underlying_name"], "\u94c1\u77ff\u77f3")
        self.assertAlmostEqual(float(resolved["entry_price"]), 800.0)
        self.assertAlmostEqual(float(resolved["knock_out_price"]), 792.0)
        self.assertAlmostEqual(float(resolved["barrier_in"]), 864.0)
        self.assertEqual(resolved["base_qty_per_day"], 0.0)
        self.assertEqual(params["sb_term_unit"], "WEEK")
        self.assertEqual(params["sb_term_count"], 8)
        self.assertEqual(params["sb_ko_obs_freq"], "WEEKLY")
        self.assertEqual(scenario["snowball_ko_input_mode"], "\u767e\u5206\u6bd4(%)")
        self.assertEqual(scenario["snowball_ki_input_mode"], "\u767e\u5206\u6bd4(%)")
        self.assertAlmostEqual(float(scenario["snowball_ko_pct"]), 99.0)
        self.assertAlmostEqual(float(scenario["snowball_ki_pct"]), 108.0)
        self.assertAlmostEqual(float(params["sb_notional_wan"]), 1000.0)
        self.assertAlmostEqual(float(params["sb_coupon_pct"]), 10.0)
        self.assertTrue(bool(params["sb_floor_enabled"]))
        self.assertFalse(bool(params["sb_discount_enabled"]))
        self.assertAlmostEqual(float(params["sb_discount_price"]), 864.0)
        self.assertEqual(int(params["n_days"]), int(scenario["term_trading_days"]))
        self.assertEqual(int(scenario["paths"]), int(self.app.WINRATE_SELF_QUOTE_SNOWBALL_PATHS_DEFAULT))
        self.assertTrue(bool(scenario["futures_mode"]))

    def test_snowball_discount_turns_floor_off_when_both_are_set(self) -> None:
        resolved, scenario = self._manual_snowball()
        scenario.update(
            {
                "snowball_floor_enabled": True,
                "snowball_discount_enabled": True,
                "snowball_discount_price": 860.0,
            }
        )

        priced = self.app.volval_self_quote_apply_scenario(resolved, scenario)
        params = priced["params"]

        self.assertTrue(bool(params["sb_discount_enabled"]))
        self.assertFalse(bool(params["sb_floor_enabled"]))
        self.assertAlmostEqual(float(params["sb_discount_price"]), 860.0)

    def test_snowball_discount_spread_display_uses_directional_gap(self) -> None:
        self.assertEqual(
            self.app.format_snowball_discount_spread_text("DEC", 896.50, 863.82),
            "\u6298\u4ef7\uff1a32.68",
        )
        self.assertEqual(
            self.app.format_snowball_discount_spread_text("ACC", 896.50, 930.18),
            "\u6298\u4ef7\uff1a33.68",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_snowball_discount_price_with_spread(
                863.82,
                815.00,
                "DEC",
                896.50,
            ),
            "863.82\uff08+48.82\uff09 \u6298\u4ef7\uff1a32.68",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_snowball_discount_price_with_spread(
                863.82,
                815.00,
                "DEC",
                896.50,
                include_entry_ratio=True,
            ),
            "863.82\uff08+48.82,105.99%\uff09 \u6298\u4ef7\uff1a32.68",
        )
        self.assertEqual(
            self.app.append_snowball_discount_spread_text("863.82", "DEC", None, 863.82),
            "863.82",
        )

    def test_snowball_self_quote_mc_template_keeps_trade_date_for_knock_in(self) -> None:
        resolved, scenario = self._manual_snowball()
        priced = self.app.volval_self_quote_apply_scenario(resolved, scenario)
        template = self.app.volval_template_with_dates(
            self.app.winrate_prepare_structure_template(priced),
            start_date_v=scenario["start_date"],
            end_date_v=scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
        )

        self.assertEqual(template["template_dates"][0], self.app.parse_date_maybe(scenario["start_date"]))
        self.assertTrue(bool(template["mc_include_start_price"]))
        runtime = self.app._snowball_runtime(template["resolved"], {})
        first_obs = runtime["ko_observation_plan"][0]
        self.assertEqual(first_obs["serial"], 1)
        self.assertGreater(first_obs["obs_date"], self.app.parse_date_maybe(scenario["start_date"]))
        self.assertFalse(bool(first_obs["is_locked"]))
        self.assertEqual(first_obs["eligible_idx"], 1)

    def test_snowball_self_quote_mc_template_does_not_pin_weekend_start_to_s0(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-10")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        priced = self.app.volval_self_quote_apply_scenario(resolved, scenario)
        template = self.app.volval_template_with_dates(
            self.app.winrate_prepare_structure_template(priced),
            start_date_v=scenario["start_date"],
            end_date_v=scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
        )

        self.assertGreater(template["template_dates"][0], self.app.parse_date_maybe(scenario["start_date"]))
        self.assertFalse(bool(template["mc_include_start_price"]))

    def test_snowball_spot_drift_mode_makes_risk_free_rate_affect_coupon_quote(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario.update(
            {
                "iv_pct": 15.5,
                "risk_free_rate_pct": 2.0,
                "futures_mode": False,
                "snowball_term_count": 7,
            }
        )
        spot_drift = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            target_unit_value=0.0,
        )

        futures_mode = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            {**scenario, "futures_mode": True},
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            target_unit_value=0.0,
        )

        self.assertTrue(spot_drift["ok"], spot_drift.get("message"))
        self.assertTrue(futures_mode["ok"], futures_mode.get("message"))
        self.assertGreater(float(spot_drift["solution_value"]), float(futures_mode["solution_value"]))

    def test_snowball_batch_term_count_syncs_end_date_and_template(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)

        rows = []
        for term_count in (4, 6, 8):
            variant = dict(scenario)
            variant["snowball_term_count"] = term_count
            self.assertEqual(variant["end_date"], scenario["end_date"])
            applied = self.app.volval_self_quote_apply_scenario(resolved, variant)
            synced = self.app.volval_self_quote_sync_snowball_period(variant)
            template = self.app.volval_template_with_dates(
                self.app.winrate_prepare_structure_template(applied),
                start_date_v=applied["start_date"],
                end_date_v=applied["end_date"],
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
            rows.append(
                (
                    applied["end_date"],
                    int(synced["term_trading_days"]),
                    int(applied["params"]["n_days"]),
                    int(template["path_len"]),
                    len(template.get("ko_steps", [])),
                )
            )

        self.assertEqual([row[0] for row in rows], ["2026-06-03", "2026-06-17", "2026-07-01"])
        self.assertEqual([row[4] for row in rows], [4, 6, 8])
        self.assertEqual(len({row[1] for row in rows}), 3)
        self.assertEqual([row[1] for row in rows], [row[2] for row in rows])
        self.assertEqual([row[1] for row in rows], [row[3] for row in rows])

    def test_snowball_early_mode_stage_counts_include_locked_observations(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario.update(
            {
                "start_date": "2026-05-19",
                "snowball_term_unit": "WEEK",
                "snowball_term_count": 6,
                "snowball_ko_obs_freq": "WEEKLY",
                "snowball_lock_enabled": True,
                "snowball_lock_ko_obs": 1,
                "snowball_early_mode": True,
                "snowball_early_a": 3,
                "snowball_early_b": 3,
                "snowball_coupon_a_pct": 12.0,
                "snowball_coupon_b_pct": 8.0,
            }
        )
        scenario = self.app.volval_self_quote_sync_snowball_period(scenario)
        summary = self.app.volval_self_quote_snowball_observation_summary(scenario)

        self.assertEqual(int(summary["total_obs"]), 6)
        self.assertEqual(int(summary["effective_obs"]), 5)
        self.assertIsNone(
            self.app.volval_self_quote_validate_snowball_early_mode(
                scenario,
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            )
        )

        priced = self.app.volval_self_quote_apply_scenario(resolved, scenario)
        runtime = self.app._snowball_runtime(priced, {})
        plan = runtime["ko_observation_plan"]
        self.assertTrue(bool(plan[0]["is_locked"]))
        self.assertEqual([int(row["serial"]) for row in plan], [1, 2, 3, 4, 5, 6])
        self.assertEqual([int(row["eligible_idx"]) for row in plan], [0, 1, 2, 3, 4, 5])
        self.assertEqual(self.app._snowball_phase(runtime, 2), "A阶段")
        self.assertEqual(self.app._snowball_phase(runtime, 3), "A阶段")
        self.assertAlmostEqual(self.app._snowball_coupon_pct(runtime, 2), 12.0)
        self.assertAlmostEqual(self.app._snowball_coupon_pct(runtime, 3), 12.0)
        self.assertAlmostEqual(self.app._snowball_coupon_pct(runtime, 4), 8.0)

        schedule = self.app._snowball_all_ko_schedule(
            plan,
            start_date_value=scenario["start_date"],
            early_mode=True,
            early_a=3,
            coupon_a_pct=12.0,
            coupon_b_pct=8.0,
            notional_amount=10_000_000.0,
        )
        self.assertEqual([row["coupon_pct"] for row in schedule], [12.0, 12.0, 12.0, 8.0, 8.0, 8.0])
        self.assertIsNone(schedule[0]["profit_amt"])
        self.assertIsNotNone(schedule[2]["profit_amt"])

    def test_apply_scenario_maps_each_snowball_reverse_variable(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)

        coupon_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=13.5,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
        )
        coupon_params = coupon_resolved["params"]
        self.assertAlmostEqual(float(coupon_params["sb_coupon_pct"]), 13.5)
        self.assertAlmostEqual(float(coupon_params["sb_coupon_a_pct"]), 13.5)
        self.assertAlmostEqual(float(coupon_params["sb_coupon_b_pct"]), 13.5)

        ko_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=760.0,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_KO_PRICE,
        )
        self.assertAlmostEqual(float(ko_resolved["knock_out_price"]), 760.0)
        self.assertAlmostEqual(float(ko_resolved["params"]["sb_ko_price"]), 760.0)
        self.assertAlmostEqual(float(ko_resolved["params"]["sb_ko_pct"]), 95.0)

        ki_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=900.0,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_KI_PRICE,
        )
        self.assertAlmostEqual(float(ki_resolved["barrier_in"]), 900.0)
        self.assertAlmostEqual(float(ki_resolved["params"]["sb_ki_price"]), 900.0)
        self.assertAlmostEqual(float(ki_resolved["params"]["sb_ki_pct"]), 112.5)

        discount_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=880.0,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_DISCOUNT_PRICE,
        )
        discount_params = discount_resolved["params"]
        self.assertTrue(bool(discount_params["sb_discount_enabled"]))
        self.assertFalse(bool(discount_params["sb_floor_enabled"]))
        self.assertAlmostEqual(float(discount_params["sb_discount_price"]), 880.0)

    def test_snowball_early_mode_coupon_reverse_only_updates_stage_a_coupon(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario.update(
            {
                "snowball_early_mode": True,
                "snowball_early_a": 2,
                "snowball_early_b": 6,
                "snowball_coupon_a_pct": 12.0,
                "snowball_coupon_b_pct": 8.0,
            }
        )

        coupon_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=14.5,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
        )
        coupon_params = coupon_resolved["params"]

        self.assertAlmostEqual(float(coupon_params["sb_coupon_pct"]), 0.0)
        self.assertAlmostEqual(float(coupon_params["sb_coupon_a_pct"]), 14.5)
        self.assertAlmostEqual(float(coupon_params["sb_coupon_b_pct"]), 8.0)
        self.assertEqual(int(coupon_params["sb_early_a"]), 2)
        self.assertEqual(int(coupon_params["sb_early_b"]), 6)

    def test_snowball_early_mode_only_allows_stage_a_coupon_reverse(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario.update(
            {
                "snowball_early_mode": True,
                "snowball_early_a": 2,
                "snowball_early_b": 6,
                "snowball_coupon_b_pct": 8.0,
            }
        )

        options = self.app.volval_self_quote_effective_reverse_options("SNOWBALL", scenario)
        result = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            {**scenario, "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_KO_PRICE},
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_KO_PRICE,
            target_unit_value=0.0,
        )

        self.assertEqual(options, (self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,))
        self.assertFalse(result["ok"])
        self.assertIn("仅支持反解A阶段票息", result.get("message", ""))

    def test_snowball_early_mode_requires_phase_counts_match_total_observations(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario.update(
            {
                "snowball_early_mode": True,
                "snowball_early_a": 2,
                "snowball_early_b": 5,
                "snowball_coupon_b_pct": 8.0,
            }
        )

        result = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            target_unit_value=0.0,
        )

        self.assertFalse(result["ok"])
        self.assertIn("敲出观察日次数", result.get("message", ""))

    def test_percentage_snowball_levels_are_converted_to_prices(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario["spot_price"] = 1000.0
        scenario["snowball_ko_input_mode"] = "\u767e\u5206\u6bd4(%)"
        scenario["snowball_ko_pct"] = 97.0
        scenario["snowball_ki_input_mode"] = "\u767e\u5206\u6bd4(%)"
        scenario["snowball_ki_pct"] = 112.0

        converted = self.app.volval_self_quote_apply_scenario(resolved, scenario)

        self.assertAlmostEqual(float(converted["knock_out_price"]), 970.0)
        self.assertAlmostEqual(float(converted["barrier_in"]), 1120.0)
        self.assertAlmostEqual(float(converted["params"]["sb_ko_pct"]), 97.0)
        self.assertAlmostEqual(float(converted["params"]["sb_ki_pct"]), 112.0)

    def test_absolute_snowball_levels_refresh_percentages(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario["spot_price"] = 1000.0
        scenario["snowball_ko_input_mode"] = "\u7edd\u5bf9\u4ef7"
        scenario["snowball_ki_input_mode"] = "\u7edd\u5bf9\u4ef7"
        scenario["barrier_price"] = 960.0
        scenario["knock_in_price"] = 1090.0
        scenario["snowball_ko_pct"] = 99.0
        scenario["snowball_ki_pct"] = 108.0

        converted = self.app.volval_self_quote_apply_scenario(resolved, scenario)

        self.assertAlmostEqual(float(converted["knock_out_price"]), 960.0)
        self.assertAlmostEqual(float(converted["barrier_in"]), 1090.0)
        self.assertAlmostEqual(float(converted["params"]["sb_ko_pct"]), 96.0)
        self.assertAlmostEqual(float(converted["params"]["sb_ki_pct"]), 109.0)

    def test_snowball_knock_out_price_allows_entry_boundary(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        dec_scenario = dict(scenario)
        dec_scenario["barrier_price"] = float(dec_scenario["spot_price"])
        dec_scenario["reverse_variable"] = self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON
        self.assertIsNone(
            self.app.volval_self_quote_validate_directional_prices(
                resolved,
                dec_scenario,
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            )
        )

        acc_resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-06")
        acc_resolved["kind"] = "ACC"
        acc_scenario = self.app.volval_self_quote_base_scenario(acc_resolved)
        acc_scenario["barrier_price"] = float(acc_scenario["spot_price"])
        acc_scenario["knock_in_price"] = float(acc_scenario["spot_price"]) * 0.9
        acc_scenario["reverse_variable"] = self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON
        self.assertIsNone(
            self.app.volval_self_quote_validate_directional_prices(
                acc_resolved,
                acc_scenario,
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            )
        )

    def test_snowball_coupon_reverse_solver_recovers_model_target(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        target_coupon = 13.5
        priced = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=target_coupon,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
        )
        template = self.app.winrate_prepare_structure_template(priced)
        valuation_template = self.app.volval_template_with_dates(
            template,
            start_date_v=scenario["start_date"],
            end_date_v=scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
        )
        valuation = self.app.winrate_structure_model_value_for_iv(
            valuation_template,
            start_price=float(scenario["spot_price"]),
            atm_iv_pct=float(scenario["iv_pct"]),
            skew=0.0,
            paths=int(scenario["paths"]),
            trading_days_per_year=252,
            seed=int(scenario["seed"]),
            seed_hint="snowball-coupon-recovery",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
            carry_yield_pct=0.0,
            futures_mode=True,
        )
        target_unit = float(valuation["value"]) / float(valuation["initial_scale_qty"])

        progress_updates = []
        result = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            target_unit_value=target_unit,
            progress_callback=lambda pct, _label: progress_updates.append(float(pct)),
        )

        self.assertTrue(result["ok"], result.get("message"))
        self.assertAlmostEqual(float(result["solution_value"]), target_coupon, places=2)
        self.assertTrue(progress_updates)
        self.assertAlmostEqual(float(progress_updates[-1]), 1.0, places=8)
        self.assertTrue(all(0.0 <= float(x) <= 1.0 for x in progress_updates))
        self.assertLessEqual(len(result.get("sample_points", [])), 3)

    def test_snowball_early_mode_lower_b_coupon_requires_higher_a_coupon(self) -> None:
        resolved, scenario = self._manual_snowball(paths=3000)
        scenario = dict(scenario)
        scenario.update(
            {
                "snowball_early_mode": True,
                "snowball_early_a": 2,
                "snowball_early_b": 6,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            }
        )

        low_b_solutions = []
        for coupon_b in (0.0, 1.0, 2.0):
            result = self.app.volval_self_quote_solve_reverse_variable(
                resolved,
                {**scenario, "snowball_coupon_b_pct": coupon_b},
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
                target_unit_value=0.0,
            )
            self.assertTrue(result["ok"], result.get("message"))
            low_b_solutions.append(float(result["solution_value"]))

        self.assertGreater(low_b_solutions[0], low_b_solutions[1])
        self.assertGreater(low_b_solutions[1], low_b_solutions[2])

        higher_b = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            {**scenario, "snowball_coupon_b_pct": 10.0},
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            target_unit_value=0.0,
        )
        lower_b = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            {**scenario, "snowball_coupon_b_pct": 8.0},
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            target_unit_value=0.0,
        )

        self.assertTrue(higher_b["ok"], higher_b.get("message"))
        self.assertTrue(lower_b["ok"], lower_b.get("message"))
        self.assertGreater(float(lower_b["solution_value"]), float(higher_b["solution_value"]))

    def test_snowball_self_quote_result_builds_quote_image_payload(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        priced = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=11.25,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
        )

        payload = self.app.volval_self_quote_quote_payload(
            resolved,
            scenario,
            {
                "ok": True,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
                "solution_value": 11.25,
                "resolved_for_result": priced,
            },
            display_id="\u65b9\u68481",
            quote_date_value="2026-05-06",
            theme="midnight_biz",
        )

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["strategy_code"], "SNOWBALL")
        self.assertEqual(payload["underlying"], "\u94c1\u77ff\u77f3")
        self.assertEqual(payload["underlying_name"], "\u94c1\u77ff\u77f3")
        self.assertEqual(payload["quote_date"], "2026-05-06")
        self.assertAlmostEqual(float(payload["sb_coupon_pct"]), 11.25)
        self.assertAlmostEqual(float(payload["sb_ko_price"]), float(priced["params"]["sb_ko_price"]))
        self.assertGreater(float(payload["sb_notional_amount"]), 0.0)

    def test_self_quote_nearest_result_builds_quote_image_payload(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        priced = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=8.5,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
        )
        nearest_result = {
            "ok": False,
            "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            "solution_value": None,
            "nearest_value": 8.5,
            "nearest_unit_diff": 0.35,
            "resolved_for_result": priced,
            "message": "\u5df2\u8fd4\u56de\u6700\u63a5\u8fd1\u70b9\u3002",
        }

        payload = self.app.volval_self_quote_quote_payload(
            resolved,
            scenario,
            nearest_result,
            display_id="\u65b9\u68481",
            quote_date_value="2026-05-14",
            theme="midnight_biz",
        )

        self.assertTrue(self.app.volval_self_quote_result_has_quote_snapshot(nearest_result))
        self.assertIsInstance(payload, dict)
        self.assertAlmostEqual(float(payload["sb_coupon_pct"]), 8.5)
        self.assertEqual(payload["quote_date"], "2026-05-14")
        png_bytes = self.app.render_structure_quote_image(payload)
        self.assertTrue(bytes(png_bytes).startswith(b"\x89PNG\r\n\x1a\n"))

        failed_result = {
            "ok": False,
            "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            "message": "\u53cd\u89e3\u4f30\u503c\u5931\u8d25\u3002",
        }
        self.assertFalse(self.app.volval_self_quote_result_has_quote_snapshot(failed_result))
        self.assertIsNone(self.app.volval_self_quote_quote_payload(resolved, scenario, failed_result))

    def test_self_quote_quote_payload_controls_underlying_identity_display(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        priced = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=11.25,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
        )
        result = {
            "ok": True,
            "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            "solution_value": 11.25,
            "resolved_for_result": priced,
        }

        hidden_payload = self.app.volval_self_quote_quote_payload(resolved, scenario, result)
        visible_payload = self.app.volval_self_quote_quote_payload(
            resolved,
            scenario,
            result,
            show_underlying_code_name=True,
        )

        self.assertIsInstance(hidden_payload, dict)
        self.assertIsInstance(visible_payload, dict)
        self.assertFalse(hidden_payload["show_underlying_code_name"])
        self.assertTrue(visible_payload["show_underlying_code_name"])

        changed_hidden = dict(hidden_payload)
        changed_hidden["underlying"] = "CU2609"
        changed_hidden["underlying_name"] = "\u94dc"
        hidden_labels = self.app.volval_self_quote_quote_diff_labels([hidden_payload, changed_hidden])
        self.assertNotIn("\u6807\u7684\u4ee3\u7801", hidden_labels)
        self.assertNotIn("\u6807\u7684\u540d\u79f0", hidden_labels)

        changed_visible = dict(visible_payload)
        changed_visible["underlying"] = "CU2609"
        changed_visible["underlying_name"] = "\u94dc"
        visible_labels = self.app.volval_self_quote_quote_diff_labels([visible_payload, changed_visible])
        self.assertIn("\u6807\u7684\u4ee3\u7801", visible_labels)
        self.assertIn("\u6807\u7684\u540d\u79f0", visible_labels)

    def test_snowball_long_term_past_calendar_table_falls_back_to_weekdays(self) -> None:
        start_d = date(2026, 5, 6)
        maturity = self.app._snowball_add_period(start_d, "WEEK", 50)

        observations = self.app._snowball_build_observations(start_d, maturity, "WEEKLY")
        trading_days = self.app.trading_days_between(start_d, maturity)

        self.assertEqual(maturity.year, 2027)
        self.assertTrue(observations)
        self.assertTrue(trading_days)
        self.assertTrue(self.app.is_trading_day(date(2027, 1, 4)))

    def test_self_quote_quote_diff_labels_highlight_visible_changed_rows(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        payloads = []
        for coupon in (11.25, 12.50, 13.75):
            priced = self.app.volval_self_quote_apply_scenario(
                resolved,
                scenario,
                variable_value=coupon,
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            )
            payload = self.app.volval_self_quote_quote_payload(
                resolved,
                scenario,
                {
                    "ok": True,
                    "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
                    "solution_value": coupon,
                    "resolved_for_result": priced,
                },
                display_id="\u65b9\u68481",
            )
            self.assertIsInstance(payload, dict)
            payload["implied_vol_pct"] = coupon * 2.0
            payloads.append(payload)

        labels = self.app.volval_self_quote_quote_diff_labels(payloads)

        self.assertIn("\u7968\u606f", labels)
        self.assertNotIn("IV", labels)
        self.assertNotIn("\u6ce2\u52a8\u7387", labels)
        self.assertEqual(
            self.app.volval_self_quote_quote_highlight_labels_for_theme("midnight_biz", labels),
            labels,
        )
        self.assertEqual(
            self.app.volval_self_quote_quote_highlight_labels_for_theme("crimson_silver_business", labels),
            [],
        )

    def test_self_quote_combined_quote_image_renders_png(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario["snowball_term_unit"] = "MONTH"
        scenario["snowball_ko_obs_freq"] = "MONTHLY"
        payloads = []
        for idx, (term_count, coupon) in enumerate(((2, 13.90), (3, 13.56), (4, 11.82), (5, 10.20), (6, 8.55)), start=1):
            scenario_i = dict(scenario)
            scenario_i["snowball_term_count"] = term_count
            priced = self.app.volval_self_quote_apply_scenario(
                resolved,
                scenario_i,
                variable_value=coupon,
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            )
            payload = self.app.volval_self_quote_quote_payload(
                resolved,
                scenario_i,
                {
                    "ok": True,
                    "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
                    "solution_value": coupon,
                    "resolved_for_result": priced,
                },
                display_id=f"\u65b9\u68481-{idx}",
                theme="midnight_biz",
            )
            self.assertIsInstance(payload, dict)
            payload["column_label"] = f"\u65b9\u68481-{idx}"
            payloads.append(payload)

        combined_payload = dict(payloads[0])
        combined_payload["quote_columns"] = payloads
        combined_payload["highlight_labels"] = ["\u7968\u606f"]

        png_bytes = self.app.render_structure_quote_image(combined_payload)

        self.assertIsInstance(png_bytes, (bytes, bytearray))
        self.assertTrue(bytes(png_bytes).startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertGreater(len(png_bytes), 1000)

    def test_snowball_knock_in_maturity_loss_has_no_coupon_and_floor_caps_loss(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario.update(
            {
                "snowball_ko_pct": 99.0,
                "snowball_ki_pct": 105.0,
                "risk_free_rate_pct": 0.0,
                "futures_mode": True,
                "snowball_discount_enabled": False,
            }
        )

        floor_mild_values = []
        floor_severe_values = []
        no_floor_mild_values = []
        no_floor_severe_values = []
        rescue_values = []
        for floor_enabled in (True, False):
            for coupon in (0.0, 20.0):
                priced = self.app.volval_self_quote_apply_scenario(
                    resolved,
                    {**scenario, "snowball_floor_enabled": floor_enabled},
                    variable_value=coupon,
                    reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
                )
                template = self.app.volval_template_with_dates(
                    self.app.winrate_prepare_structure_template(priced),
                    start_date_v=scenario["start_date"],
                    end_date_v=scenario["end_date"],
                    day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
                )
                path_len = int(template["path_len"])
                mild_ki_no_ko_prices = np.full((8, path_len), float(scenario["spot_price"]) * 1.06, dtype=float)
                severe_ki_no_ko_prices = np.full((8, path_len), float(scenario["spot_price"]) * 1.20, dtype=float)
                ki_then_ko_prices = np.full((8, path_len), float(scenario["spot_price"]) * 0.98, dtype=float)
                ki_then_ko_prices[:, 0] = float(scenario["spot_price"]) * 1.06

                mild_vectorized = self.app.winrate_estimate_structure_path_values(
                    template,
                    mild_ki_no_ko_prices,
                    discount_rate_pct=0.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                )
                mild_state_loop = self.app.winrate_estimate_structure_path_values(
                    template,
                    mild_ki_no_ko_prices,
                    discount_rate_pct=0.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                    force_state_loop=True,
                )
                severe_vectorized = self.app.winrate_estimate_structure_path_values(
                    template,
                    severe_ki_no_ko_prices,
                    discount_rate_pct=0.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                )
                severe_state_loop = self.app.winrate_estimate_structure_path_values(
                    template,
                    severe_ki_no_ko_prices,
                    discount_rate_pct=0.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                    force_state_loop=True,
                )
                rescue_vectorized = self.app.winrate_estimate_structure_path_values(
                    template,
                    ki_then_ko_prices,
                    discount_rate_pct=0.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                )
                rescue_state_loop = self.app.winrate_estimate_structure_path_values(
                    template,
                    ki_then_ko_prices,
                    discount_rate_pct=0.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                    force_state_loop=True,
                )

                self.assertTrue(np.allclose(mild_vectorized, mild_state_loop, atol=1e-6, rtol=1e-10))
                self.assertTrue(np.allclose(severe_vectorized, severe_state_loop, atol=1e-6, rtol=1e-10))
                self.assertTrue(np.allclose(rescue_vectorized, rescue_state_loop, atol=1e-6, rtol=1e-10))

                mild_mean = float(np.mean(mild_vectorized))
                severe_mean = float(np.mean(severe_vectorized))
                if floor_enabled:
                    floor_mild_values.append(mild_mean)
                    floor_severe_values.append(severe_mean)
                    if coupon == 20.0:
                        rescue_values.append(float(np.mean(rescue_vectorized)))
                else:
                    no_floor_mild_values.append(mild_mean)
                    no_floor_severe_values.append(severe_mean)

        self.assertLess(floor_mild_values[0], 0.0)
        entry_price = float(scenario["spot_price"])
        floor_ki_price = entry_price * float(scenario["snowball_ki_pct"]) / 100.0
        notional = float(resolved["params"]["sb_notional_wan"]) * 10000.0
        expected_mild_loss = -notional * ((entry_price * 1.06) - entry_price) / entry_price
        expected_severe_loss = -notional * ((entry_price * 1.20) - entry_price) / entry_price
        expected_floor_cap_loss = -notional * (floor_ki_price - entry_price) / entry_price
        self.assertAlmostEqual(floor_mild_values[0], expected_floor_cap_loss, places=2)
        self.assertAlmostEqual(floor_severe_values[0], expected_floor_cap_loss, places=2)
        self.assertAlmostEqual(no_floor_mild_values[0], expected_mild_loss, places=2)
        self.assertAlmostEqual(no_floor_severe_values[0], expected_severe_loss, places=2)
        self.assertAlmostEqual(floor_mild_values[0], floor_mild_values[1], places=6)
        self.assertAlmostEqual(floor_severe_values[0], floor_severe_values[1], places=6)
        self.assertAlmostEqual(no_floor_mild_values[0], no_floor_mild_values[1], places=6)
        self.assertAlmostEqual(no_floor_severe_values[0], no_floor_severe_values[1], places=6)
        self.assertGreater(floor_mild_values[0], no_floor_mild_values[0])
        self.assertGreater(floor_severe_values[0], no_floor_severe_values[0])
        self.assertAlmostEqual(floor_severe_values[0], floor_mild_values[0], places=6)
        self.assertLess(no_floor_severe_values[0], no_floor_mild_values[0])
        self.assertGreater(rescue_values[0], floor_mild_values[0])

    def test_snowball_ki_then_ko_pays_coupon(self) -> None:
        resolved, scenario = self._manual_snowball(paths=1000)
        scenario = dict(scenario)
        scenario.update(
            {
                "snowball_ko_pct": 99.0,
                "snowball_ki_pct": 105.0,
                "risk_free_rate_pct": 0.0,
                "futures_mode": True,
                "snowball_floor_enabled": True,
                "snowball_discount_enabled": False,
            }
        )

        rescue_values = []
        for coupon in (0.0, 20.0):
            priced = self.app.volval_self_quote_apply_scenario(
                resolved,
                scenario,
                variable_value=coupon,
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
            )
            template = self.app.volval_template_with_dates(
                self.app.winrate_prepare_structure_template(priced),
                start_date_v=scenario["start_date"],
                end_date_v=scenario["end_date"],
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
            self.assertTrue(bool(priced["params"].get("sb_valuation_ki_then_ko_coupon")))
            self.assertFalse(bool(priced["params"].get("sb_valuation_ki_maturity_coupon")))
            ki_then_ko_prices = np.full((8, int(template["path_len"])), float(scenario["spot_price"]) * 0.98, dtype=float)
            ki_then_ko_prices[:, 0] = float(scenario["spot_price"]) * 1.06

            rescue_vectorized = self.app.winrate_estimate_structure_path_values(
                template,
                ki_then_ko_prices,
                discount_rate_pct=0.0,
                trading_days_per_year=252,
                discount_cashflows=True,
            )
            rescue_state_loop = self.app.winrate_estimate_structure_path_values(
                template,
                ki_then_ko_prices,
                discount_rate_pct=0.0,
                trading_days_per_year=252,
                discount_cashflows=True,
                force_state_loop=True,
            )

            self.assertTrue(np.allclose(rescue_vectorized, rescue_state_loop, atol=1e-6, rtol=1e-10))
            rescue_values.append(float(np.mean(rescue_vectorized)))

        self.assertGreater(rescue_values[1], rescue_values[0])

    def test_snowball_coupon_reverse_quote_increases_with_iv(self) -> None:
        resolved, scenario = self._manual_snowball(paths=5000)
        scenario = dict(scenario)
        scenario.update(
            {
                "snowball_ko_pct": 99.0,
                "snowball_ki_pct": 108.0,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "snowball_floor_enabled": True,
                "snowball_discount_enabled": False,
            }
        )

        coupons = []
        for iv_pct in (15.0, 20.0):
            result = self.app.volval_self_quote_solve_reverse_variable(
                resolved,
                {**scenario, "iv_pct": iv_pct},
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_COUPON,
                target_unit_value=0.0,
            )
            self.assertTrue(result["ok"], result.get("message"))
            coupons.append(float(result["solution_value"]))

        self.assertLess(coupons[0], coupons[1])
        self.assertLess(coupons[1], 45.0)

    def test_snowball_knock_in_reverse_quote_increases_with_coupon_at_fixed_iv(self) -> None:
        resolved, scenario = self._manual_snowball(paths=3000)
        scenario = dict(scenario)
        scenario.update(
            {
                "iv_pct": 17.0,
                "snowball_ko_pct": 99.0,
                "snowball_ki_pct": 108.0,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "snowball_floor_enabled": True,
                "snowball_discount_enabled": False,
            }
        )

        knock_in_prices = []
        for coupon in (5.0, 10.0, 15.0, 20.0):
            result = self.app.volval_self_quote_solve_reverse_variable(
                resolved,
                {
                    **scenario,
                    "snowball_coupon_pct": coupon,
                    "snowball_coupon_a_pct": coupon,
                    "snowball_coupon_b_pct": coupon,
                },
                reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SNOWBALL_KI_PRICE,
                target_unit_value=0.0,
            )
            self.assertTrue(result["ok"], result.get("message"))
            knock_in_prices.append(float(result["solution_value"]))

        self.assertTrue(
            all(left < right for left, right in zip(knock_in_prices, knock_in_prices[1:])),
            knock_in_prices,
        )

    def test_snowball_vectorized_valuation_matches_state_loop_variants(self) -> None:
        variants = [
            {},
            {"snowball_floor_enabled": False},
            {"snowball_discount_enabled": True, "snowball_discount_price": 860.0},
            {
                "snowball_early_mode": True,
                "snowball_early_a": 2,
                "snowball_coupon_a_pct": 12.0,
                "snowball_coupon_b_pct": 8.0,
            },
            {"snowball_auto_stepdown": True, "snowball_stepdown_pct": 1.0},
            {"snowball_lock_enabled": True, "snowball_lock_ko_obs": 2},
            {
                "snowball_early_mode": True,
                "snowball_early_a": 2,
                "snowball_coupon_a_pct": 12.0,
                "snowball_coupon_b_pct": 8.0,
                "snowball_auto_stepdown": True,
                "snowball_stepdown_pct": 1.0,
                "snowball_lock_enabled": True,
                "snowball_lock_ko_obs": 1,
                "snowball_discount_enabled": True,
                "snowball_discount_price": 860.0,
            },
        ]
        for idx, variant in enumerate(variants):
            with self.subTest(variant=idx):
                resolved, scenario = self._manual_snowball(paths=1000)
                scenario.update(variant)
                priced = self.app.volval_self_quote_apply_scenario(resolved, scenario)
                template = self.app.winrate_prepare_structure_template(priced)
                template = self.app.volval_template_with_dates(
                    template,
                    start_date_v=scenario["start_date"],
                    end_date_v=scenario["end_date"],
                    day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
                )
                sim = self.app.winrate_simulate_bs_risk_neutral_price_paths(
                    start_price=float(scenario["spot_price"]),
                    n_days=int(template["path_len"]),
                    atm_iv_pct=float(scenario["iv_pct"]),
                    paths=1000,
                    trading_days_per_year=252,
                    seed=13579,
                    seed_hint=f"snowball-vectorized-{idx}",
                    risk_free_rate_pct=2.0,
                    carry_yield_pct=0.0,
                    futures_mode=True,
                )
                prices = sim["price_paths"][:96]
                vectorized = self.app.winrate_estimate_structure_path_values(
                    template,
                    prices,
                    discount_rate_pct=2.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                )
                state_loop = self.app.winrate_estimate_structure_path_values(
                    template,
                    prices,
                    discount_rate_pct=2.0,
                    trading_days_per_year=252,
                    discount_cashflows=True,
                    force_state_loop=True,
                )

                self.assertTrue(np.allclose(vectorized, state_loop, atol=1e-6, rtol=1e-10))


if __name__ == "__main__":
    unittest.main()
