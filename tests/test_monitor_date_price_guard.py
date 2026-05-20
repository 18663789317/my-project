import ast
import copy
import pathlib
import unittest
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
from chinese_calendar import is_holiday


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

TARGET_SYMBOLS = {
    "is_trading_day",
    "previous_trading_day",
    "parse_date_maybe",
    "pick_recent_trading_date_option",
    "restrict_group_date_options_to_recorded_prices",
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


class MonitorDatePriceGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ns = load_symbols()

    def test_restrict_group_date_options_filters_out_dates_without_recorded_prices(self) -> None:
        fn = self.ns["restrict_group_date_options_to_recorded_prices"]
        prices_df = pd.DataFrame(
            {
                "dt": ["2026-04-14", "2026-04-15", "2026-04-16", "2026-04-15"],
                "underlying": ["I2609", "I2609", "I2609", "I2605"],
                "settle": [758.5, 764.0, 782.5, 800.0],
            }
        )
        structs_df = pd.DataFrame(
            {
                "group_id": ["G001", "G002"],
                "underlying": ["I2609", "I2605"],
            }
        )

        actual = fn(
            ["2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17", "2026-04-20"],
            prices_df,
            structs_df,
            "G001",
        )

        self.assertEqual(actual, ["2026-04-14", "2026-04-15", "2026-04-16"])

    def test_restrict_group_date_options_falls_back_to_group_price_dates_when_candidates_are_all_invalid(self) -> None:
        fn = self.ns["restrict_group_date_options_to_recorded_prices"]
        prices_df = pd.DataFrame(
            {
                "dt": ["2026-04-14", "2026-04-15", "2026-04-16"],
                "underlying": ["I2609", "I2609", "I2609"],
                "settle": [758.5, 764.0, 782.5],
            }
        )
        structs_df = pd.DataFrame(
            {
                "group_id": ["G001"],
                "underlying": ["I2609"],
            }
        )

        actual = fn(
            ["2026-04-17", "2026-04-20"],
            prices_df,
            structs_df,
            "G001",
        )

        self.assertEqual(actual, ["2026-04-14", "2026-04-15", "2026-04-16"])

    def test_default_monitor_date_rolls_back_to_latest_recorded_price_date(self) -> None:
        restrict_fn = self.ns["restrict_group_date_options_to_recorded_prices"]
        pick_fn = self.ns["pick_recent_trading_date_option"]
        prices_df = pd.DataFrame(
            {
                "dt": ["2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17"],
                "underlying": ["I2609", "I2609", "I2609", "I2609"],
                "settle": [758.5, 764.0, 782.5, None],
            }
        )
        structs_df = pd.DataFrame(
            {
                "group_id": ["G001"],
                "underlying": ["I2609"],
            }
        )

        options = restrict_fn(
            ["2026-04-14", "2026-04-15", "2026-04-16", "2026-04-17", "2026-04-20"],
            prices_df,
            structs_df,
            "G001",
        )

        self.assertEqual(
            pick_fn(options, base_day_v=date(2026, 4, 20)),
            "2026-04-16",
        )


if __name__ == "__main__":
    unittest.main()
