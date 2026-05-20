import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_airbag_strike_summary_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AirbagStrikeSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_report_airbag_strike_breakdown_uses_absolute_display_qty_by_direction(self) -> None:
        items = [
            {
                "kind": "DEC",
                "strike_price": 760.0,
                "display_slot_qty": -30000.0,
            },
            {
                "side_cn": "\u770b\u8dcc",
                "strike_price": 780.0,
                "display_slot_qty": -10000.0,
            },
            {
                "kind": "ACC",
                "strike_price": 790.0,
                "display_slot_qty": 40000.0,
            },
            {
                "kind": "ACC",
                "strike_price": 770.0,
                "display_slot_qty": 10000.0,
            },
            {
                "kind": "ACC",
                "display_slot_qty": 20000.0,
            },
            {
                "kind": "DEC",
                "strike_price": 999.0,
                "display_slot_qty": 0.0,
            },
        ]

        out = self.app.report_airbag_strike_breakdown(items)

        self.assertAlmostEqual(float(out["DEC"]["qty"]), 40000.0)
        self.assertAlmostEqual(float(out["DEC"]["avg_strike"]), 765.0)
        self.assertAlmostEqual(float(out["ACC"]["qty"]), 50000.0)
        self.assertAlmostEqual(float(out["ACC"]["avg_strike"]), 786.0)

    def test_report_airbag_strike_summary_rows_formats_missing_side_as_dash(self) -> None:
        items = [
            {
                "kind": "DEC",
                "strike_price": 781.5,
                "display_slot_qty": -50000.0,
            },
            {
                "kind": "DEC",
                "strike_price": 773.0,
                "display_slot_qty": -30000.0,
            },
        ]

        rows = self.app.report_airbag_strike_summary_rows(items)

        self.assertEqual(
            rows[0]["label"],
            "\u770b\u8dcc\u6c14\u56ca\u884c\u6743\u4ef7\u5747\u4ef7\u53ca\u6570\u91cf\uff1a",
        )
        self.assertEqual(rows[0]["value"], "778.31 80,000\u5428")
        self.assertEqual(
            rows[1]["label"],
            "\u770b\u6da8\u6c14\u56ca\u884c\u6743\u4ef7\u5747\u4ef7\u53ca\u6570\u91cf\uff1a",
        )
        self.assertEqual(rows[1]["value"], "--")

    def test_report_format_compact_price_trims_trailing_zeroes(self) -> None:
        self.assertEqual(self.app.report_format_compact_price(760.0), "760")
        self.assertEqual(self.app.report_format_compact_price(781.5), "781.5")
        self.assertEqual(self.app.report_format_compact_price(None), "--")


if __name__ == "__main__":
    unittest.main()
