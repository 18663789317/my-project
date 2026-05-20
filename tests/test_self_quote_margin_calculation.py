import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_self_quote_margin_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    with contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


class SelfQuoteMarginCalculationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def _vanilla_scenario(self):
        resolved = self.app.volval_self_quote_manual_resolved(
            self.app.VANILLA_OPTION_CODE,
            start_date_v="2026-05-13",
        )
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "spot_price": 800.0,
                "strike_price": 800.0,
                "iv_pct": 20.0,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "notional_qty": 2000.0,
            }
        )
        return resolved, scenario

    def test_trs_is_explicitly_skipped(self) -> None:
        result = self.app.volval_self_quote_compute_margin_estimate(
            {"strategy_code": "TRS"},
            {"strategy_code": "TRS"},
        )

        self.assertFalse(result["ok"])
        self.assertTrue(result["skipped"])
        self.assertIn("TRS", result["message"])

    def test_vanilla_buy_margin_uses_premium_only(self) -> None:
        resolved, scenario = self._vanilla_scenario()
        scenario.update({"side": "buy", "option_type": "call", "premium": 80.0})

        result = self.app.volval_self_quote_compute_margin_estimate(resolved, scenario)

        self.assertTrue(result["ok"], result.get("message"))
        self.assertEqual(result["method"], "买入期权权利金口径")
        self.assertAlmostEqual(float(result["margin_per_ton"]), 80.0, places=8)
        self.assertAlmostEqual(float(result["margin_wan"]), 16.0, places=8)

    def test_vanilla_sell_margin_has_minimum_floor(self) -> None:
        resolved, scenario = self._vanilla_scenario()
        scenario.update({"side": "sell", "option_type": "put", "premium": 0.0})

        result = self.app.volval_self_quote_compute_margin_estimate(resolved, scenario)

        self.assertTrue(result["ok"], result.get("message"))
        self.assertEqual(result["method"], "Black-76压力重估")
        self.assertGreaterEqual(
            float(result["margin_per_ton"]),
            800.0 * self.app.VOLVAL_SELF_QUOTE_MARGIN_MIN_RATE_PCT / 100.0,
        )
        self.assertGreater(float(result["margin_wan"]), 0.0)

    def test_accumulator_margin_rate_scales_with_participation_multiple(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-13")
        for multiple, expected_rate in [(1.0, 5.0), (2.0, 10.0), (3.0, 15.0)]:
            scenario = self.app.volval_self_quote_base_scenario(resolved)
            scenario["spot_price"] = 800.0
            scenario["multiple"] = multiple

            result = self.app.volval_self_quote_compute_margin_estimate(resolved, scenario)

            self.assertTrue(result["ok"], result.get("message"))
            self.assertEqual(result["method"], "业务保证金比例口径")
            self.assertAlmostEqual(float(result["margin_per_ton"]), 800.0 * expected_rate / 100.0, places=8)
            self.assertAlmostEqual(float(result["margin_rate_pct"]), expected_rate, places=8)


if __name__ == "__main__":
    unittest.main()
