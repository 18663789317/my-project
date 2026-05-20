import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_date_column_width_defaults_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DateColumnWidthDefaultsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_dynamic_iso_date_headers_are_expanded_to_large_width(self) -> None:
        df = pd.DataFrame({"品种": ["I2605"], "2026-03-09": [784.5]})
        config = {
            "品种": self.app.st.column_config.TextColumn("品种", width="small"),
            "2026-03-09": self.app.st.column_config.NumberColumn("2026-03-09", format="%.2f", width="medium"),
        }

        out = self.app._column_config_for(df, config)

        self.assertEqual(out["2026-03-09"].get("width"), "medium")
        self.assertEqual(out["品种"].get("width"), "small")

    def test_auto_width_wrapper_preserves_full_iso_date_header_space(self) -> None:
        df = pd.DataFrame({"2026-03-09": [784.5]})
        config = {
            "2026-03-09": self.app.st.column_config.NumberColumn("2026-03-09", format="%.2f", width="medium"),
        }

        out = self.app._merge_table_auto_width_column_config(df, column_config=config, hide_index=True)

        self.assertGreaterEqual(int(out["2026-03-09"].get("width")), 118)
        self.assertLessEqual(int(out["2026-03-09"].get("width")), 124)

    def test_plain_date_columns_are_promoted_to_medium_width(self) -> None:
        df = pd.DataFrame({"日期": ["2026-04-14", "2026-04-15"], "收盘价": [800.0, 801.0]})
        config = {
            "日期": self.app.st.column_config.TextColumn("日期", width="small"),
            "收盘价": self.app.st.column_config.NumberColumn("收盘价", format="%.2f"),
        }

        out = self.app._column_config_for(df, config)

        self.assertEqual(out["日期"].get("width"), "medium")

    def test_trading_day_count_columns_are_not_mistaken_for_dates(self) -> None:
        df = pd.DataFrame({"总交易日": [12, 18], "剩余交易日": [4, 9]})
        config = {
            "总交易日": self.app.st.column_config.TextColumn("总交易日", width="small"),
            "剩余交易日": self.app.st.column_config.TextColumn("剩余交易日", width="small"),
        }

        out = self.app._column_config_for(df, config)

        self.assertEqual(out["总交易日"].get("width"), "small")
        self.assertEqual(out["剩余交易日"].get("width"), "small")


    def test_exact_numeric_width_is_preserved_without_auto_widening(self) -> None:
        df = pd.DataFrame({"detail": ["x" * 60]})
        config = {
            "detail": self.app.st.column_config.TextColumn("detail", width=90),
        }

        out = self.app._merge_table_auto_width_column_config(df, column_config=config, hide_index=True)

        self.assertEqual(int(out["detail"].get("width")), 90)


if __name__ == "__main__":
    unittest.main()
