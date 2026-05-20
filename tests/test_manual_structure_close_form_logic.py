import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_manual_structure_close_form_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class ManualStructureCloseFormLogicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_widget_state_defaults_to_full_remaining_scale(self) -> None:
        state = self.app.resolve_manual_structure_close_qty_widget_state(
            group_id="G1",
            structure_id="S_FULL",
            close_dt="2026-04-09",
            remaining_scale_qty=50000.0,
            prev_track_value="",
            current_input_qty=0.0,
        )

        self.assertAlmostEqual(float(state["remaining_qty"]), 50000.0)
        self.assertAlmostEqual(float(state["next_qty"]), 50000.0)

    def test_widget_state_and_submission_accept_rounded_remaining_scale_boundary(self) -> None:
        row = {
            "structure_id": "S_AIR_FORM",
            "strategy_code": "SAFETY_AIRBAG",
            "strategy": "SAFETY_AIRBAG",
            "start_date": "2026-04-01",
            "end_date": "2026-04-03",
            "base_qty_per_day": 100000.0 / 3.0,
            "entry_price": 100.0,
            "strike_price": 95.0,
            "barrier_out": 80.0,
            "params": {},
            "meta": {},
        }
        reduced = self.app.apply_manual_structure_reduction_to_resolved_row(row, 50000.0)
        raw_remaining = float(reduced["_manual_remaining_scale_qty"])

        self.assertLess(abs(raw_remaining - 50000.0), 1e-6)

        state = self.app.resolve_manual_structure_close_qty_widget_state(
            group_id="G1",
            structure_id="S_AIR_FORM",
            close_dt="2026-04-09",
            remaining_scale_qty=raw_remaining,
            prev_track_value="",
            current_input_qty=0.0,
        )
        submission = self.app.resolve_manual_structure_close_submission(50000.0, raw_remaining)

        self.assertAlmostEqual(float(state["remaining_qty"]), 50000.0)
        self.assertAlmostEqual(float(state["next_qty"]), 50000.0)
        self.assertTrue(bool(submission["is_full_close"]))
        self.assertAlmostEqual(float(submission["effective_qty"]), 50000.0)
        self.assertAlmostEqual(float(submission["remaining_after"]), 0.0)

    def test_manual_close_unknown_kind_reports_data_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "结构方向数据异常"):
            self.app.build_manual_structure_close_rows(
                [{"open_qty": 100.0, "gen_price": 90.0, "date": "2026-04-09"}],
                kind="UNKNOWN",
                side="SELL",
                qty=10.0,
                total_pnl=100.0,
                close_dt="2026-04-09",
                group_id="G1",
                structure_id="S_BAD",
                underlying="I2605",
                quick_batch_id="MANUAL_TEST",
            )


if __name__ == "__main__":
    unittest.main()
