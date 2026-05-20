import importlib.util
import pathlib
import sys
import tempfile
import unittest
from types import SimpleNamespace

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_history_cache_path_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HistoryCachePathTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_history_route_cache_path_uses_windows_safe_filename(self) -> None:
        route = SimpleNamespace(
            route="specific_contract",
            exchange="unknown",
            product_code="I",
            contract_code="I2605",
            akshare_symbol="i2605",
            display_label="I2605",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            old_dir = self.app.SPECIAL_HISTORY_DAILY_CACHE_DIR
            self.app.SPECIAL_HISTORY_DAILY_CACHE_DIR = pathlib.Path(tmpdir)
            try:
                cache_path = self.app._history_route_cache_path(route)
                self.assertNotIn("|", cache_path.name)
                self.assertTrue(cache_path.name.endswith(".pkl"))

                source_df = pd.DataFrame(
                    {
                        "dt": ["2026-04-03", "2026-04-06"],
                        "settle": [776.0, 780.0],
                    }
                )
                self.app._SPECIAL_HISTORY_FILE_MEMO_CACHE.clear()
                self.app._SPECIAL_HISTORY_META_FILE_MEMO_CACHE.clear()
                self.app._save_history_series_cache(route, source_df)
                self.assertTrue(cache_path.exists())

                self.app._SPECIAL_HISTORY_FILE_MEMO_CACHE.clear()
                loaded_df = self.app._load_history_series_cache(route)
                self.assertEqual(len(loaded_df), 2)
                self.assertAlmostEqual(float(loaded_df.iloc[-1]["settle"]), 780.0)

                meta_path = self.app._history_route_cache_meta_path(route)
                self.assertNotIn("|", meta_path.name)
                self.assertTrue(meta_path.exists())
            finally:
                self.app.SPECIAL_HISTORY_DAILY_CACHE_DIR = old_dir
                self.app._SPECIAL_HISTORY_FILE_MEMO_CACHE.clear()
                self.app._SPECIAL_HISTORY_META_FILE_MEMO_CACHE.clear()


if __name__ == "__main__":
    unittest.main()
