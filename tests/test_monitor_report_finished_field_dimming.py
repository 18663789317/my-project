import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_report_finished_field_dimming_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorReportFinishedFieldDimmingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def _build_cumulative_row(self, *, status_cn: str, remaining_days: int, report_finished: bool) -> dict:
        return {
            "structure_id": "S012",
            "structure_display_id": "S012",
            "structure_line1": "S012 monitor row",
            "structure_line2": "entry 815.5 strike 795.5",
            "structure_rich_lines": [
                [{"text": "S012 monitor row", "color": "#123456", "weight": "bold"}],
                [{"text": "entry 815.5 strike 795.5", "color": "#d7e9ff", "weight": "normal"}],
            ],
            "status_cn": status_cn,
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
            "remaining_trading_days": remaining_days,
            "remaining_natural_days": max(remaining_days, 0),
            "snowball_total_natural_days": max(remaining_days, 0),
            "end_date": "04-15",
            "report_finished": report_finished,
        }

    def _build_summary(self, *, row: dict, test_id: str) -> dict:
        return {
            "group_id": "G001",
            "group_name": "G001 - finished field dimming",
            "underlying": "I2609",
            "date": "2026-04-16",
            "gen_total_qty": 0.0,
            "net_gen_qty": 0.0,
            "gen_long_qty": 0.0,
            "gen_short_qty": 0.0,
            "remaining_max_signed": 0.0,
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
            "cumulative_rows": [row],
            "snowball_rows": [],
            "vanilla_rows": [],
            "airbag_rows": [],
            "report_layout": {},
            "_test_id": test_id,
        }

    def test_monitor_report_finished_row_should_dim_requires_terminal_status_with_zero_days(self) -> None:
        self.assertTrue(
            self.app.monitor_report_finished_row_should_dim(
                {
                    "status_cn": "\u5df2\u7ed3\u675f",
                    "remaining_trading_days": 0,
                }
            )
        )
        self.assertTrue(
            self.app.monitor_report_finished_row_should_dim(
                {
                    "status_cn": "\u5df2\u7ec8\u6b62(\u6709\u5934\u5bf8)",
                    "remaining_trading_days": 0,
                }
            )
        )
        self.assertTrue(
            self.app.monitor_report_finished_row_should_dim(
                {
                    "status_cn": "\u9707\u8361",
                    "remaining_trading_days": 3,
                    "report_finished": True,
                }
            )
        )
        self.assertFalse(
            self.app.monitor_report_finished_row_should_dim(
                {
                    "status_cn": "\u9707\u8361",
                    "remaining_trading_days": 0,
                }
            )
        )
        self.assertFalse(
            self.app.monitor_report_finished_row_should_dim(
                {
                    "status_cn": "\u5df2\u7ed3\u675f",
                    "remaining_trading_days": 2,
                }
            )
        )

    def test_render_report_image_dims_finished_cumulative_fields_only(self) -> None:
        original_dim = self.app.monitor_report_dimmed_text_color

        active_calls: list[tuple[object, object, float]] = []

        def active_spy(color, bg_color, *, fg_weight=0.42):
            active_calls.append((color, bg_color, fg_weight))
            return original_dim(color, bg_color, fg_weight=fg_weight)

        active_summary = self._build_summary(
            row=self._build_cumulative_row(
                status_cn="\u9707\u8361(1\u500d)",
                remaining_days=2,
                report_finished=False,
            ),
            test_id="active-cumulative-row-no-dimming",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "active.png"
            with mock.patch.object(self.app, "monitor_report_dimmed_text_color", side_effect=active_spy):
                png_bytes = self.app.render_report_image(active_summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        self.assertEqual(active_calls, [])

        finished_calls: list[tuple[object, object, float]] = []

        def finished_spy(color, bg_color, *, fg_weight=0.42):
            finished_calls.append((color, bg_color, fg_weight))
            return original_dim(color, bg_color, fg_weight=fg_weight)

        finished_summary = self._build_summary(
            row=self._build_cumulative_row(
                status_cn="\u5df2\u7ed3\u675f",
                remaining_days=0,
                report_finished=True,
            ),
            test_id="finished-cumulative-row-dimming",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_path = pathlib.Path(tmp_dir) / "finished.png"
            with mock.patch.object(self.app, "monitor_report_dimmed_text_color", side_effect=finished_spy):
                png_bytes = self.app.render_report_image(finished_summary, str(out_path))

        self.assertGreater(len(png_bytes), 0)
        self.assertGreaterEqual(len(finished_calls), 5)
        self.assertIn("#123456", [str(call[0]).lower() for call in finished_calls])


if __name__ == "__main__":
    unittest.main()
