import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_remaining_days_fallback_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorRemainingDaysFallbackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_prefers_bounds_remaining_days_over_report_date_fallback(self) -> None:
        remaining = self.app.resolve_monitor_remaining_trading_days(
            bounds_remaining_days=30,
            latest_remaining_days=None,
            total_trading_days=30,
            as_of_date="2026-04-22",
            start_date="2026-04-17",
            end_date="2026-06-02",
        )

        self.assertEqual(remaining, 30)

    def test_uses_total_days_for_new_structure_without_any_history(self) -> None:
        remaining = self.app.resolve_monitor_remaining_trading_days(
            bounds_remaining_days=None,
            latest_remaining_days=None,
            total_trading_days=30,
            as_of_date="2026-04-22",
            start_date="2026-04-17",
            end_date="2026-06-02",
        )

        self.assertEqual(remaining, 30)

    def test_finished_structure_forces_zero_remaining_days(self) -> None:
        remaining = self.app.resolve_monitor_remaining_trading_days(
            bounds_remaining_days=30,
            latest_remaining_days=29,
            total_trading_days=30,
            as_of_date="2026-04-22",
            start_date="2026-04-17",
            end_date="2026-06-02",
            finished=True,
        )

        self.assertEqual(remaining, 0)

    def test_average_remaining_days_ratio_ignores_non_positive_numerators(self) -> None:
        rows = [
            {"remaining_trading_days": 15, "total_trading_days": 25},
            {"remaining_trading_days": 16, "total_trading_days": 25},
            {"remaining_trading_days": 15, "total_trading_days": 25},
            {"remaining_trading_days": 22, "total_trading_days": 30},
            {"remaining_trading_days": 15, "total_trading_days": 25},
            {"remaining_trading_days": 20, "total_trading_days": 25},
            {"remaining_trading_days": 0, "total_trading_days": 25},
            {"remaining_trading_days": -3, "total_trading_days": 25},
        ]

        avg_vals = self.app.average_remaining_days_ratio_values(
            rows,
            "remaining_trading_days",
            "total_trading_days",
        )

        self.assertIsNotNone(avg_vals)
        assert avg_vals is not None
        self.assertAlmostEqual(avg_vals[0], 103 / 6)
        self.assertAlmostEqual(avg_vals[1], 155 / 6)
        self.assertEqual(
            self.app.format_average_remaining_days_ratio(
                rows,
                "remaining_trading_days",
                "total_trading_days",
            ),
            "17.2/25.8",
        )
        self.assertEqual(self.app.format_remaining_days_percentage(avg_vals[0], avg_vals[1]), "66.5%")

    def test_average_remaining_days_ratio_returns_none_without_positive_numerators(self) -> None:
        rows = [
            {"remaining_trading_days": 0, "total_trading_days": 25},
            {"remaining_trading_days": -3, "total_trading_days": 25},
        ]

        self.assertIsNone(
            self.app.average_remaining_days_ratio_values(
                rows,
                "remaining_trading_days",
                "total_trading_days",
            )
        )
        self.assertEqual(
            self.app.format_average_remaining_days_ratio(
                rows,
                "remaining_trading_days",
                "total_trading_days",
            ),
            "-",
        )


if __name__ == "__main__":
    unittest.main()
