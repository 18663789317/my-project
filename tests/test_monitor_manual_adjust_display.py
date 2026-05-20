import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_manual_adjust_display_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorManualAdjustDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_manual_adjust_trace_is_hidden_by_default_in_monitor_report(self) -> None:
        trace = self.app.build_monitor_manual_adjust_trace_text(
            {
                "manual_adjust_today_qty": 3000.0,
                "manual_adjust_net_qty": 12000.0,
            }
        )

        self.assertEqual(trace, "")

    def test_manual_adjust_trace_can_still_be_built_when_explicitly_enabled(self) -> None:
        today_trace = self.app.build_monitor_manual_adjust_trace_text(
            {
                "manual_adjust_today_qty": 3000.0,
                "manual_adjust_net_qty": 12000.0,
            },
            show_in_report=True,
        )
        net_trace = self.app.build_monitor_manual_adjust_trace_text(
            {
                "manual_adjust_today_qty": 0.0,
                "manual_adjust_net_qty": 12000.0,
            },
            show_in_report=True,
        )

        self.assertEqual(today_trace, "手调当日 +3,000吨")
        self.assertEqual(net_trace, "手调存量 +12,000吨")


if __name__ == "__main__":
    unittest.main()
