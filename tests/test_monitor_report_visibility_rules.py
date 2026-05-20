import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_report_visibility_rules_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorReportVisibilityRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_filter_finished_zero_monitor_report_items_hides_finished_zero_rows_only(self) -> None:
        rows = [
            {
                "structure_id": "S_FIN_ZERO",
                "remaining_trading_days": 0,
                "status_cn": "已结束",
                "open_position_qty": 0.0,
                "display_slot_qty": 0.0,
                "remaining_max_qty": 0.0,
                "remaining_min_qty": 0.0,
            },
            {
                "structure_id": "S_ACTIVE",
                "remaining_trading_days": 4,
                "status_cn": "震荡（1倍）",
                "open_position_qty": 0.0,
                "display_slot_qty": 0.0,
                "remaining_max_qty": 6000.0,
                "remaining_min_qty": 0.0,
            },
            {
                "structure_id": "S_TERM_WITH_POS",
                "remaining_trading_days": 0,
                "status_cn": "已终止(有头寸)",
                "open_position_qty": 3000.0,
                "display_slot_qty": 3000.0,
                "remaining_max_qty": 0.0,
                "remaining_min_qty": 0.0,
            },
            {
                "structure_id": "AB_KEEP",
                "remaining_trading_days": 0,
                "status_cn": "已结束",
                "open_position_qty": 0.0,
                "display_slot_qty": -8000.0,
                "remaining_max_qty": 8000.0,
                "remaining_min_qty": 0.0,
                "is_airbag": True,
            },
        ]

        visible = self.app.filter_finished_zero_monitor_report_items(rows)

        self.assertEqual(
            [str(row.get("structure_id")) for row in visible],
            ["S_ACTIVE", "S_TERM_WITH_POS", "AB_KEEP"],
        )

    def test_build_cumulative_monitor_detail_meta_prefixes_direction_badge_before_structure_id(self) -> None:
        acc_meta = self.app.build_cumulative_monitor_detail_meta(
            structure_id="S009",
            strategy_value="BASIC_RANGE",
            kind_value="ACC",
            fallback_name="普通累购",
            risk_party="海证资本",
            entry_price=814.5,
            strike_price=794.5,
        )
        dec_meta = self.app.build_cumulative_monitor_detail_meta(
            structure_id="S010",
            strategy_value="BASIC_RANGE",
            kind_value="DEC",
            fallback_name="普通累沽",
            risk_party="海证资本",
            entry_price=730.0,
            strike_price=793.0,
        )

        acc_line = acc_meta["rich_lines"][0]
        dec_line = dec_meta["rich_lines"][0]

        self.assertEqual(acc_line[0]["text"], "■ ")
        self.assertEqual(acc_line[0]["color"], "#ff7f79")
        self.assertTrue(str(acc_line[1]["text"]).startswith("S009"))

        self.assertEqual(dec_line[0]["text"], "■ ")
        self.assertEqual(dec_line[0]["color"], "#69d26b")
        self.assertTrue(str(dec_line[1]["text"]).startswith("S010"))


if __name__ == "__main__":
    unittest.main()
