import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_self_quote_fixed_subsidy_spread_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    with contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


class FixedSubsidySpreadReverseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_fixed_subsidy_reverse_options_include_spread_payout_only_for_fixed_subsidy(self) -> None:
        rev = self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD

        self.assertIn(rev, self.app.volval_self_quote_reverse_options("FIXED_SUBSIDY"))
        self.assertNotIn(rev, self.app.volval_self_quote_reverse_options("RANGE_SUBSIDY"))

    def test_fixed_subsidy_spread_apply_sets_non_negative_payout_from_configured_barrier_gap(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("FIXED_SUBSIDY", start_date_v="2026-05-14")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "kind": "DEC",
                "spot_price": 800.0,
                "strike_price": 800.0,
                "barrier_price": 760.0,
                "subsidy_per_ton": 0.0,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD,
            }
        )

        out = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD,
        )

        self.assertAlmostEqual(float(out["barrier_out"]), 760.0, places=8)
        self.assertAlmostEqual(float(out["knock_out_price"]), 760.0, places=8)
        self.assertAlmostEqual(float(out["subsidy_per_ton"]), 40.0, places=8)
        self.assertAlmostEqual(float(out["params"]["subsidy_per_ton"]), 40.0, places=8)

    def test_fixed_subsidy_spread_bounds_exclude_zero_gap_entry_price(self) -> None:
        rev = self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD
        resolved = self.app.volval_self_quote_manual_resolved("FIXED_SUBSIDY", start_date_v="2026-05-14")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "kind": "DEC",
                "spot_price": 800.0,
                "strike_price": 800.0,
                "barrier_price": 760.0,
                "subsidy_per_ton": 0.0,
                "iv_pct": 20.0,
                "paths": 1000,
                "seed": 123,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "reverse_variable": rev,
            }
        )

        low, high, grid = self.app.volval_self_quote_variable_bounds(resolved, scenario, rev)

        self.assertLess(high, 800.0)
        self.assertLess(low, high)
        self.assertNotIn(800.0, [round(float(x), 8) for x in grid])

    def test_fixed_subsidy_spread_reverse_target_zero_returns_nearest_not_zero_payout_success(self) -> None:
        rev = self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD
        resolved = self.app.volval_self_quote_manual_resolved("FIXED_SUBSIDY", start_date_v="2026-05-14")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "kind": "DEC",
                "spot_price": 800.0,
                "strike_price": 810.0,
                "barrier_price": 760.0,
                "subsidy_per_ton": 0.0,
                "iv_pct": 20.0,
                "paths": 1000,
                "seed": 123,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "reverse_variable": rev,
            }
        )

        solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=rev,
            target_unit_value=0.0,
        )

        self.assertFalse(bool(solved["ok"]))
        self.assertIsNone(solved.get("solution_value"))
        self.assertNotEqual(float(solved["nearest_value"]), 800.0)
        result_resolved = solved["resolved_for_result"]
        self.assertAlmostEqual(
            float(result_resolved["subsidy_per_ton"]),
            abs(float(result_resolved["barrier_out"]) - float(result_resolved["entry_price"])),
            places=8,
        )
        self.assertGreater(float(result_resolved["subsidy_per_ton"]), 0.0)

    def test_fixed_subsidy_zero_payout_barrier_reverse_skips_entry_boundary(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("FIXED_SUBSIDY", start_date_v="2026-05-19")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "kind": "ACC",
                "spot_price": 800.0,
                "strike_price": 790.0,
                "barrier_price": 760.0,
                "subsidy_per_ton": 0.0,
                "iv_pct": 15.5,
                "paths": 1000,
                "seed": 123,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "start_date": "2026-05-19",
                "end_date": "2026-06-08",
                "term_trading_days": 15,
            }
        )

        barrier_rev = self.app.VOLVAL_SELF_QUOTE_REV_BARRIER
        spread_rev = self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD
        low, _high, grid = self.app.volval_self_quote_variable_bounds(
            resolved,
            {**scenario, "reverse_variable": barrier_rev},
            barrier_rev,
        )
        self.assertGreater(float(low), 800.0)
        self.assertNotIn(800.0, [round(float(x), 8) for x in grid])

        barrier_result = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            {**scenario, "reverse_variable": barrier_rev},
            reverse_variable=barrier_rev,
            target_unit_value=0.0,
        )
        spread_result = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            {**scenario, "reverse_variable": spread_rev},
            reverse_variable=spread_rev,
            target_unit_value=0.0,
        )

        self.assertTrue(barrier_result["ok"], barrier_result.get("message"))
        self.assertTrue(spread_result["ok"], spread_result.get("message"))
        barrier_price = float(barrier_result["solution_value"])
        spread_barrier_price = float(spread_result["solution_value"])
        self.assertGreater(barrier_price, 800.0)
        self.assertGreater(barrier_price, spread_barrier_price)
        self.assertAlmostEqual(float(barrier_result["resolved_for_result"]["subsidy_per_ton"]), 0.0, places=8)

    def test_fixed_subsidy_spread_reverse_solves_model_generated_target_without_fixed_expected_price(self) -> None:
        rev = self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD
        resolved = self.app.volval_self_quote_manual_resolved("FIXED_SUBSIDY", start_date_v="2026-05-14")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "kind": "DEC",
                "spot_price": 800.0,
                "strike_price": 810.0,
                "barrier_price": 760.0,
                "subsidy_per_ton": 0.0,
                "iv_pct": 20.0,
                "paths": 1000,
                "seed": 123,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "reverse_variable": rev,
            }
        )

        start_d = self.app.parse_date_maybe(scenario["start_date"])
        end_d = self.app.parse_date_maybe(scenario["end_date"])

        def unit_value_for_barrier(barrier_value: float) -> float:
            scenario_resolved = self.app.volval_self_quote_apply_scenario(
                resolved,
                scenario,
                variable_value=barrier_value,
                reverse_variable=rev,
            )
            template = self.app.volval_template_with_dates(
                self.app.winrate_prepare_structure_template(scenario_resolved),
                start_date_v=start_d,
                end_date_v=end_d,
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
            valuation = self.app.winrate_structure_model_value_for_iv(
                template,
                start_price=float(scenario["spot_price"]),
                atm_iv_pct=float(scenario["iv_pct"]),
                paths=int(scenario["paths"]),
                trading_days_per_year=252,
                seed=int(scenario["seed"]),
                seed_hint=f"{scenario_resolved.get('structure_id', '')}|{rev}|self_quote",
                valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
                risk_free_rate_pct=float(scenario["risk_free_rate_pct"]),
                carry_yield_pct=0.0,
                futures_mode=True,
            )
            return float(valuation["value"]) / max(float(valuation["initial_scale_qty"]), 1e-12)

        low, high, _grid = self.app.volval_self_quote_variable_bounds(resolved, scenario, rev)
        target_unit = (unit_value_for_barrier(float(low)) + unit_value_for_barrier(float(high))) / 2.0

        solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=rev,
            target_unit_value=target_unit,
        )

        self.assertTrue(solved["ok"], solved.get("message"))
        self.assertLess(abs(float(solved["unit_diff"])), 1e-3)
        result_resolved = solved["resolved_for_result"]
        self.assertAlmostEqual(float(solved["solution_value"]), float(result_resolved["barrier_out"]), places=8)
        self.assertAlmostEqual(
            float(result_resolved["subsidy_per_ton"]),
            abs(float(result_resolved["barrier_out"]) - float(result_resolved["entry_price"])),
            places=8,
        )
        self.assertGreater(float(result_resolved["subsidy_per_ton"]), 0.0)

    def test_fixed_subsidy_spread_result_text_shows_barrier_and_payout(self) -> None:
        text = self.app.volval_self_quote_format_subsidy_spread_result(
            760.0,
            800.0,
            subsidy_value=40.0,
        )

        self.assertIn("敲出价", text)
        self.assertIn("760.00", text)
        self.assertIn("赔付 40.00", text)


if __name__ == "__main__":
    unittest.main()
