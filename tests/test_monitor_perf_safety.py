import importlib.util
import pathlib
import sys
import tempfile
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_perf_safety_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorPerfSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def _build_render_summary(self) -> dict:
        return {
            "group_id": "G001",
            "group_name": "G001 - perf safety",
            "underlying": "I2609",
            "date": "2026-04-16",
            "gen_total_qty": 0.0,
            "net_gen_qty": 0.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 0.0,
            "remaining_max_signed": 12000.0,
            "gen_avg_price": None,
            "today_long_avg": None,
            "today_short_avg": None,
            "day_close_price": 780.0,
            "day_close_price_map": {"I2609": 780.0},
            "lock_qty": 0.0,
            "lock_pnl": 0.0,
            "has_snowball": False,
            "has_vanilla": False,
            "has_airbag": False,
            "cumulative_rows": [
                {
                    "structure_id": "S001",
                    "structure_display_id": "S001",
                    "structure_line1": "S001 perf safety row",
                    "structure_line2": "entry 780 strike 760",
                    "structure_rich_lines": [
                        [{"text": "S001 perf safety row", "color": "#eef6ff", "weight": "bold"}],
                        [{"text": "entry 780 strike 760", "color": "#d7e9ff", "weight": "normal"}],
                    ],
                    "status_cn": "震荡",
                    "kind": "ACC",
                    "remaining_max_qty": 12000.0,
                    "remaining_max_qty_signed": 12000.0,
                    "remaining_min_qty": 6000.0,
                    "remaining_min_qty_signed": 6000.0,
                    "today_generated_qty": 3000.0,
                    "today_generated_qty_signed": 3000.0,
                    "open_position_qty": 18000.0,
                    "open_position_qty_signed": 18000.0,
                    "daily_scale_qty": 2000.0,
                    "daily_scale_qty_signed": 2000.0,
                    "remaining_trading_days": 5,
                    "remaining_natural_days": 5,
                    "snowball_total_natural_days": 5,
                    "end_date": "04-21",
                    "report_finished": False,
                }
            ],
            "snowball_rows": [],
            "vanilla_rows": [],
            "airbag_rows": [],
            "report_layout": {},
            "_test_id": "monitor-perf-safety",
        }

    def test_render_report_image_written_file_matches_returned_bytes(self) -> None:
        summary = self._build_render_summary()
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "report.png"
            png_bytes = self.app.render_report_image(summary, str(out_path))

            self.assertTrue(out_path.exists())
            self.assertGreater(len(png_bytes), 0)
            self.assertEqual(out_path.read_bytes(), png_bytes)

    def test_render_report_image_same_summary_is_stable_across_equal_copies(self) -> None:
        summary = self._build_render_summary()
        summary_copy = {
            k: (v.copy() if isinstance(v, dict) else list(v) if isinstance(v, list) else v)
            for k, v in summary.items()
        }
        summary_copy["cumulative_rows"] = [dict(row) for row in summary["cumulative_rows"]]

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path_1 = pathlib.Path(tmp_dir) / "report_1.png"
            out_path_2 = pathlib.Path(tmp_dir) / "report_2.png"

            png_bytes_1 = self.app.render_report_image(summary, str(out_path_1))
            png_bytes_2 = self.app.render_report_image(summary_copy, str(out_path_2))

        self.assertEqual(png_bytes_1, png_bytes_2)

    def test_copy_cached_runtime_value_preserves_dataframes(self) -> None:
        payload = {
            "frame": pd.DataFrame([{"a": 1, "b": 2.0}]),
            "items": [{"x": 1}, {"y": 2}],
        }
        copied = self.app._copy_cached_runtime_value(payload)
        self.assertIsNot(copied, payload)
        self.assertIsNot(copied["frame"], payload["frame"])
        assert_frame_equal(copied["frame"], payload["frame"], check_dtype=False)


if __name__ == "__main__":
    unittest.main()
