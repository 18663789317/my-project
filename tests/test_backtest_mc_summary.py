import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_backtest_mc_summary_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class BacktestMonteCarloSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_winrate_bucket_match_summary_returns_exact_bucket(self) -> None:
        bucket_df = pd.DataFrame(
            [
                {"价格区间": "760.00 - 780.00", "胜率": 0.62},
                {"价格区间": "780.00 - 800.00", "胜率": 0.89},
            ]
        )
        summary = self.app.winrate_bucket_match_summary(
            bucket_df,
            787.31,
            exact_label="当前价格区间",
            fallback_label="最近价格区间",
        )
        self.assertTrue(bool(summary["matched"]))
        self.assertTrue(bool(summary["exact"]))
        self.assertEqual(summary["bucket_label"], "780.00 - 800.00")
        self.assertAlmostEqual(float(summary["metric_value"]), 0.89)
        self.assertEqual(summary["display_bucket_label"], "当前价格区间")

    def test_winrate_bucket_match_summary_falls_back_to_nearest_bucket(self) -> None:
        bucket_df = pd.DataFrame(
            [
                {"价格区间": "760.00 - 780.00", "胜率": 0.62},
                {"价格区间": "780.00 - 800.00", "胜率": 0.89},
            ]
        )
        summary = self.app.winrate_bucket_match_summary(
            bucket_df,
            820.00,
            exact_label="当前入场价格区间",
            fallback_label="最近入场价格区间",
        )
        self.assertTrue(bool(summary["matched"]))
        self.assertFalse(bool(summary["exact"]))
        self.assertEqual(summary["bucket_label"], "780.00 - 800.00")
        self.assertAlmostEqual(float(summary["metric_value"]), 0.89)
        self.assertEqual(summary["display_bucket_label"], "最近入场价格区间")

    def test_resolve_backtest_bucket_summaries_falls_back_to_build_bucket_for_current_price(self) -> None:
        build_history_result = {
            "bucket_df": pd.DataFrame(
                [
                    {"价格区间": "760.00 - 780.00", "胜率": 0.62},
                    {"价格区间": "780.00 - 800.00", "胜率": 0.89},
                ]
            )
        }
        live_history_result = {"bucket_df": pd.DataFrame()}

        summary_bundle = self.app.winrate_resolve_backtest_bucket_summaries(
            build_history_result=build_history_result,
            live_history_result=live_history_result,
            current_price=787.31,
            entry_price=775.00,
        )

        current_summary = summary_bundle["current_price_bucket_summary"]
        entry_summary = summary_bundle["entry_price_bucket_summary"]
        self.assertEqual(summary_bundle["current_price_bucket_basis"], "build")
        self.assertTrue(bool(current_summary["matched"]))
        self.assertEqual(current_summary["bucket_label"], "780.00 - 800.00")
        self.assertAlmostEqual(float(current_summary["metric_value"]), 0.89)
        self.assertTrue(bool(entry_summary["matched"]))
        self.assertEqual(entry_summary["bucket_label"], "760.00 - 780.00")
        self.assertAlmostEqual(float(entry_summary["metric_value"]), 0.62)

    def test_winrate_table_styles_reemit_when_session_flag_exists(self) -> None:
        class DummyStreamlit:
            def __init__(self) -> None:
                self.session_state = {"_winrate_table_styles_installed": True}
                self.markdown_calls = []

            def markdown(self, body, **kwargs) -> None:
                self.markdown_calls.append((body, kwargs))

        original_st = self.app.st
        dummy_st = DummyStreamlit()
        try:
            self.app.st = dummy_st
            self.app._winrate_install_table_styles()
        finally:
            self.app.st = original_st

        self.assertEqual(len(dummy_st.markdown_calls), 1)
        self.assertIn(".winrate-table", dummy_st.markdown_calls[0][0])
        self.assertTrue(bool(dummy_st.markdown_calls[0][1].get("unsafe_allow_html")))


if __name__ == "__main__":
    unittest.main()
