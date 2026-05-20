import importlib.util
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_price_offline_mode_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PriceOfflineModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_price_page_auto_fill_defaults_to_no_network(self) -> None:
        conn = sqlite3.connect(":memory:")
        old_is_installed = self.app._is_akshare_installed
        old_fetch = self.app.fetch_akshare_close_candidates
        try:
            self.app._is_akshare_installed = lambda: (_ for _ in ()).throw(
                AssertionError("network dependency should not be checked")
            )
            self.app.fetch_akshare_close_candidates = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("AKShare fetch should not run on page load")
            )

            res = self.app.auto_fill_group_blank_prices_hourly(
                conn,
                "G001",
                pd.DataFrame({"underlying": ["I2605"], "start_date": ["2026-04-01"]}),
                "I2605",
            )

            self.assertEqual(res.get("updated_count"), 0)
            self.assertTrue(str(res.get("skipped_reason", "")))
        finally:
            self.app._is_akshare_installed = old_is_installed
            self.app.fetch_akshare_close_candidates = old_fetch
            conn.close()

    def test_network_probe_sets_offline_mode_when_all_targets_fail(self) -> None:
        old_create_connection = self.app.socket.create_connection
        old_cache = dict(self.app._PRICE_NETWORK_STATUS_CACHE)
        try:
            def raise_offline(*args, **kwargs):
                raise OSError("offline")

            self.app.socket.create_connection = raise_offline
            self.app._PRICE_NETWORK_STATUS_CACHE["ts"] = 0.0
            self.app._PRICE_NETWORK_STATUS_CACHE["online"] = True

            self.assertFalse(self.app.price_internet_available(force_check=True, timeout_sec=0.1))
            self.assertTrue(self.app.price_offline_mode_active())
        finally:
            self.app.socket.create_connection = old_create_connection
            self.app._PRICE_NETWORK_STATUS_CACHE.clear()
            self.app._PRICE_NETWORK_STATUS_CACHE.update(old_cache)

    def test_offline_history_fetch_short_circuits_external_call(self) -> None:
        old_offline = self.app.price_offline_mode_active
        old_fetch = self.app.fetch_akshare_close_candidates_with_meta
        try:
            self.app.price_offline_mode_active = lambda **kwargs: True
            self.app.fetch_akshare_close_candidates_with_meta = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("external history fetch should not run offline")
            )

            data_df, err_df, info_df = self.app.fetch_akshare_close_candidates_with_meta_timeout(
                ["I2605"],
                self.app.date(2026, 4, 1),
                self.app.date(2026, 4, 2),
            )

            self.assertTrue(data_df.empty)
            self.assertFalse(err_df.empty)
            self.assertTrue(info_df.empty)
        finally:
            self.app.price_offline_mode_active = old_offline
            self.app.fetch_akshare_close_candidates_with_meta = old_fetch

    def test_offline_realtime_price_short_circuits_external_call(self) -> None:
        old_offline = self.app.price_offline_mode_active
        old_resolve = self.app._resolve_default_main_quote_route
        try:
            self.app.price_offline_mode_active = lambda **kwargs: True
            self.app._resolve_default_main_quote_route = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("route resolution / realtime fetch should not run offline")
            )

            rec = self.app.fetch_akshare_main_realtime_price_with_timeout(underlying="I2605")

            self.assertFalse(rec.get("ok"))
            self.assertIn("离线模式", str(rec.get("reason", "")))
        finally:
            self.app.price_offline_mode_active = old_offline
            self.app._resolve_default_main_quote_route = old_resolve

    def test_offline_auto_iv_short_circuits_external_call(self) -> None:
        old_offline = self.app.price_offline_mode_active
        old_fetch = self.app.probexp_fetch_auto_atm_iv
        try:
            self.app.price_offline_mode_active = lambda **kwargs: True
            self.app.probexp_fetch_auto_atm_iv = lambda *args, **kwargs: (_ for _ in ()).throw(
                AssertionError("auto IV fetch should not run offline")
            )

            rec = self.app.probexp_fetch_auto_atm_iv_with_timeout(
                underlying="I2605",
                rep_date="2026-04-20",
                current_close=800.0,
            )

            self.assertFalse(rec.get("ok"))
            self.assertIn("离线模式", str(rec.get("reason", "")))
        finally:
            self.app.price_offline_mode_active = old_offline
            self.app.probexp_fetch_auto_atm_iv = old_fetch


if __name__ == "__main__":
    unittest.main()
