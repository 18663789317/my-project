import ast
import copy
import pathlib
import unittest
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
from chinese_calendar import is_holiday


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

TARGET_SYMBOLS = {
    "is_trading_day",
    "previous_trading_day",
    "parse_date_maybe",
    "pick_recent_trading_date_option",
    "sort_cumulative_report_items",
}


def load_symbols() -> Dict[str, Any]:
    source = APP_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(APP_PATH))
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGET_SYMBOLS:
            body.append(copy.deepcopy(node))
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    env: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Mapping": Mapping,
        "Optional": Optional,
        "Sequence": Sequence,
        "Tuple": Tuple,
        "date": date,
        "datetime": datetime,
        "timedelta": timedelta,
        "pd": pd,
        "is_holiday": is_holiday,
        "DATE_FMT": "%Y-%m-%d",
    }
    exec(compile(module, str(APP_PATH), "exec"), env)
    return env


class SpecialPageDateAndReportSortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ns = load_symbols()

    def test_pick_recent_trading_date_option_uses_previous_trading_day_on_weekend(self) -> None:
        fn = self.ns["pick_recent_trading_date_option"]
        picked = fn(
            ["2026-04-02", "2026-04-03", "2026-04-07"],
            base_day_v=date(2026, 4, 4),
        )
        self.assertEqual(picked, "2026-04-03")

    def test_pick_recent_trading_date_option_falls_forward_when_only_future_dates_exist(self) -> None:
        fn = self.ns["pick_recent_trading_date_option"]
        picked = fn(
            ["2026-04-07", "2026-04-08"],
            base_day_v=date(2026, 4, 4),
        )
        self.assertEqual(picked, "2026-04-07")

    def test_sort_cumulative_report_items_groups_and_pushes_finished_to_bottom(self) -> None:
        fn = self.ns["sort_cumulative_report_items"]
        items = [
            {"structure_id": "S056", "kind": "DEC", "status_cn": "已结束", "remaining_trading_days": 0, "open_position_qty": 4000},
            {"structure_id": "S057", "kind": "DEC", "status_cn": "敲入（2倍）", "remaining_trading_days": 12, "open_position_qty": 9600},
            {"structure_id": "S062", "kind": "ACC", "status_cn": "震荡（1倍）", "remaining_trading_days": 4, "open_position_qty": 0},
            {"structure_id": "S059", "kind": "DEC", "status_cn": "震荡（1倍）", "remaining_trading_days": 3, "open_position_qty": 35000},
            {"structure_id": "S060", "kind": "DEC", "status_cn": "已结束", "remaining_trading_days": 0, "open_position_qty": 54400},
            {"structure_id": "S063", "kind": "ACC", "status_cn": "已结束", "remaining_trading_days": 0, "open_position_qty": 27000},
        ]

        ordered = fn(items)
        ordered_ids = [str(item.get("structure_id")) for item in ordered]

        self.assertEqual(
            ordered_ids,
            ["S057", "S059", "S060", "S056", "S062", "S063"],
        )


if __name__ == "__main__":
    unittest.main()
