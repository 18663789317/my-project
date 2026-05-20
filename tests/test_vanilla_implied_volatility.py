import importlib.util
import json
import pathlib
import sys
import unittest
from datetime import date

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_vanilla_iv_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VanillaImpliedVolatilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_black76_implied_vol_recovers_input_iv(self) -> None:
        start = date(2026, 5, 11)
        end, _ = self.app.add_trading_days(start, 20)
        target_iv = 28.5
        t = self.app.vanilla_vol_time_to_expiry_years(
            start,
            end,
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            annual_days=252,
        )["time_to_expiry_years"]
        premium = self.app.winrate_black76_vanilla_unit_price_from_spot(
            spot_or_futures_price=800.0,
            strike_price=780.0,
            atm_iv_pct=target_iv,
            time_to_expiry_years=t,
            risk_free_rate_pct=0.0,
            futures_mode=True,
            option_type="put",
        )

        result = self.app.winrate_vanilla_implied_volatility_from_inputs(
            spot_or_futures_price=800.0,
            strike_price=780.0,
            target_premium=premium,
            option_type="put",
            side="sell",
            start_date=start,
            end_date=end,
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            annual_days=252,
            risk_free_rate_pct=0.0,
            carry_yield_pct=0.0,
            futures_mode=True,
            notional_qty=1000.0,
        )

        self.assertTrue(result["ok"], result.get("message"))
        self.assertAlmostEqual(float(result["implied_vol_pct"]), target_iv, places=4)
        self.assertAlmostEqual(float(result["model_price"]), float(premium), places=6)

    def test_implied_vol_rejects_price_below_intrinsic(self) -> None:
        result = self.app.winrate_vanilla_implied_volatility_from_inputs(
            spot_or_futures_price=800.0,
            strike_price=850.0,
            target_premium=1.0,
            option_type="put",
            side="sell",
            start_date=date(2026, 5, 11),
            end_date=date(2026, 6, 5),
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            annual_days=252,
            risk_free_rate_pct=0.0,
            carry_yield_pct=0.0,
            futures_mode=True,
            notional_qty=1000.0,
        )

        self.assertFalse(result["ok"])
        self.assertIn("最低理论价", result["message"])

    def test_day_count_modes_are_explicit(self) -> None:
        self.assertEqual(
            self.app.vanilla_vol_day_count(
                date(2026, 5, 11),
                date(2026, 5, 15),
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            ),
            5,
        )
        self.assertEqual(
            self.app.vanilla_vol_day_count(
                date(2026, 5, 11),
                date(2026, 5, 15),
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_NATURAL,
            ),
            5,
        )
        self.assertEqual(
            self.app.vanilla_vol_day_count(
                date(2026, 5, 11),
                date(2026, 5, 17),
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_NATURAL,
            ),
            7,
        )

    def test_resolve_structure_row_preserves_saved_implied_vol(self) -> None:
        row = pd.Series(
            {
                "structure_id": "sid-1",
                "structure_code": "S001",
                "group_id": "G001",
                "name": "sell put",
                "underlying": "I2609",
                "risk_party": "test",
                "kind": "DEC",
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "base_qty_per_day": 1000.0,
                "start_date": "2026-05-11",
                "end_date": "2026-06-05",
                "entry_price": 800.0,
                "strike_price": 780.0,
                "premium": 12.0,
                "option_type": "put",
                "side": "sell",
                "params_json": json.dumps({"implied_vol_pct": 31.25}),
                "meta_json": "{}",
            }
        )

        resolved = self.app.resolve_structure_row(row)
        self.assertAlmostEqual(float(resolved["implied_vol_pct"]), 31.25)
        self.assertAlmostEqual(float(resolved["params"]["implied_vol_pct"]), 31.25)

    def test_self_quote_vanilla_premium_uses_scenario_risk_free_rate(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved(
            self.app.VANILLA_OPTION_CODE,
            start_date_v="2026-05-11",
        )
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        self.assertAlmostEqual(float(scenario["risk_free_rate_pct"]), 2.0)

        low_rate = dict(scenario, risk_free_rate_pct=0.0)
        high_rate = dict(scenario, risk_free_rate_pct=10.0)

        low_result = self.app.volval_self_quote_calculate_vanilla_premium(low_rate)
        high_result = self.app.volval_self_quote_calculate_vanilla_premium(high_rate)

        self.assertTrue(low_result["ok"], low_result.get("message"))
        self.assertTrue(high_result["ok"], high_result.get("message"))
        self.assertNotAlmostEqual(
            float(low_result["premium_per_ton"]),
            float(high_result["premium_per_ton"]),
            places=8,
        )

    def test_self_quote_vanilla_reverse_options_cover_requested_targets(self) -> None:
        self.assertEqual(
            self.app.volval_self_quote_reverse_options(self.app.VANILLA_OPTION_CODE),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                self.app.VOLVAL_SELF_QUOTE_REV_PREMIUM,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )

    def test_self_quote_vanilla_reverse_premium_matches_existing_calculation(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved(
            self.app.VANILLA_OPTION_CODE,
            start_date_v="2026-05-11",
        )
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "spot_price": 800.0,
                "strike_price": 780.0,
                "iv_pct": 24.0,
                "option_type": "call",
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_PREMIUM,
            }
        )

        solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_PREMIUM,
        )
        legacy = self.app.volval_self_quote_calculate_vanilla_premium(scenario)

        self.assertTrue(solved["ok"], solved.get("message"))
        self.assertAlmostEqual(float(solved["premium_per_ton"]), float(legacy["premium_per_ton"]), places=8)
        self.assertAlmostEqual(float(solved["solution_value"]), float(legacy["premium_per_ton"]), places=8)
        self.assertAlmostEqual(float(solved["resolved_for_result"]["premium"]), float(legacy["premium_per_ton"]), places=8)

    def test_self_quote_vanilla_reverse_strike_recovers_target_premium(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved(
            self.app.VANILLA_OPTION_CODE,
            start_date_v="2026-05-11",
        )
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        target_strike = 780.0
        target_iv = 24.0
        t = self.app.vanilla_vol_time_to_expiry_years(
            scenario["start_date"],
            scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            annual_days=252,
        )["time_to_expiry_years"]
        target_premium = self.app.winrate_black76_vanilla_unit_price_from_spot(
            spot_or_futures_price=800.0,
            strike_price=target_strike,
            atm_iv_pct=target_iv,
            time_to_expiry_years=t,
            risk_free_rate_pct=2.0,
            carry_yield_pct=0.0,
            futures_mode=True,
            option_type="call",
        )
        scenario.update(
            {
                "spot_price": 800.0,
                "strike_price": 800.0,
                "premium": target_premium,
                "iv_pct": target_iv,
                "option_type": "call",
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
            }
        )

        solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
        )

        self.assertTrue(solved["ok"], solved.get("message"))
        self.assertAlmostEqual(float(solved["solution_value"]), target_strike, places=4)
        self.assertAlmostEqual(float(solved["model_price"]), float(target_premium), places=6)
        self.assertAlmostEqual(float(solved["resolved_for_result"]["strike_price"]), target_strike, places=4)

    def test_self_quote_vanilla_quote_payload_uses_result_resolved_strike(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved(
            self.app.VANILLA_OPTION_CODE,
            start_date_v="2026-05-11",
        )
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "spot_price": 825.0,
                "strike_price": 835.0,
                "premium": 10.0,
                "iv_pct": 16.5,
                "option_type": "call",
                "side": "sell",
                "notional_qty": 1000.0,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
            }
        )
        result_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=842.22,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
        )

        payload = self.app.volval_self_quote_quote_payload(
            resolved,
            scenario,
            {
                "ok": True,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                "solution_value": 842.22,
                "premium_per_ton": 10.0,
                "resolved_for_result": result_resolved,
            },
            display_id="case-1",
        )

        self.assertIsInstance(payload, dict)
        self.assertAlmostEqual(float(payload["strike_price"]), 842.22)
        self.assertAlmostEqual(float(payload["premium"]), 10.0)
        self.assertNotAlmostEqual(float(payload["strike_price"]), 835.0)

    def test_self_quote_vanilla_reverse_iv_recovers_target_premium(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved(
            self.app.VANILLA_OPTION_CODE,
            start_date_v="2026-05-11",
        )
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        target_iv = 28.5
        t = self.app.vanilla_vol_time_to_expiry_years(
            scenario["start_date"],
            scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            annual_days=252,
        )["time_to_expiry_years"]
        target_premium = self.app.winrate_black76_vanilla_unit_price_from_spot(
            spot_or_futures_price=800.0,
            strike_price=780.0,
            atm_iv_pct=target_iv,
            time_to_expiry_years=t,
            risk_free_rate_pct=2.0,
            carry_yield_pct=0.0,
            futures_mode=True,
            option_type="put",
        )
        scenario.update(
            {
                "spot_price": 800.0,
                "strike_price": 780.0,
                "premium": target_premium,
                "iv_pct": 16.0,
                "option_type": "put",
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_IV,
            }
        )

        solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_IV,
        )

        self.assertTrue(solved["ok"], solved.get("message"))
        self.assertAlmostEqual(float(solved["solution_value"]), target_iv, places=4)
        self.assertAlmostEqual(float(solved["implied_vol_pct"]), target_iv, places=4)
        self.assertAlmostEqual(float(solved["resolved_for_result"]["implied_vol_pct"]), target_iv, places=4)


if __name__ == "__main__":
    unittest.main()
