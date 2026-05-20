import contextlib
import importlib.util
import io
import pathlib
import sqlite3
import sys
import unittest
from datetime import date
from unittest import mock


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_trading_calendar_override_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    with contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


class _FakeUpload:
    def __init__(self, name: str, payload: bytes) -> None:
        self.name = name
        self._payload = payload

    def getvalue(self) -> bytes:
        return self._payload


class TradingCalendarOverrideTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_build_template_covers_whole_year(self) -> None:
        df = self.app.build_trading_calendar_template_df(2027)
        self.assertEqual(list(df.columns), ["日期", "是否交易日", "备注"])
        self.assertEqual(len(df), 365)
        self.assertEqual(str(df.iloc[0]["日期"]), "2027-01-01")
        self.assertEqual(str(df.iloc[-1]["日期"]), "2027-12-31")

    def test_parse_upload_accepts_csv_template(self) -> None:
        payload = "日期,是否交易日,备注\n2027-01-04,0,停市\n2027-01-09,1,补班\n".encode("utf-8-sig")
        uploaded = _FakeUpload("trading_calendar_2027.csv", payload)

        df, err = self.app.parse_trading_calendar_upload(uploaded)

        self.assertFalse(err)
        self.assertEqual(df["日期"].tolist(), ["2027-01-04", "2027-01-09"])
        self.assertEqual(df["是否交易日"].tolist(), [0, 1])

    def test_imported_calendar_overrides_future_trading_day_judgement(self) -> None:
        df = self.app.pd.DataFrame(
            [
                {"日期": "2027-01-04", "是否交易日": 0, "备注": "手工休市"},
                {"日期": "2027-01-09", "是否交易日": 1, "备注": "手工开市"},
            ]
        )

        result = self.app.replace_trading_calendar_override_rows(self.conn, df, replace_same_years=True, source="unit-test")

        self.assertTrue(result["ok"])
        self.assertFalse(self.app.is_trading_day(date(2027, 1, 4)))
        self.assertTrue(self.app.is_trading_day(date(2027, 1, 9)))

    def test_coverage_status_prefers_local_calendar_after_import(self) -> None:
        df = self.app.pd.DataFrame(
            [
                {"日期": "2027-01-04", "是否交易日": 0, "备注": ""},
                {"日期": "2027-01-05", "是否交易日": 1, "备注": ""},
            ]
        )
        self.app.replace_trading_calendar_override_rows(self.conn, df, replace_same_years=True, source="unit-test")

        status = self.app.trading_calendar_coverage_status(date(2027, 1, 4))

        self.assertTrue(status["known"])
        self.assertFalse(status["is_provisional"])
        self.assertIn("本地", str(status["status_text"]))

    def test_year_summary_reports_partial_and_full_coverage(self) -> None:
        full_df = self.app.build_trading_calendar_template_df(2028)
        partial_df = self.app.pd.DataFrame(
            [
                {"日期": "2027-01-04", "是否交易日": 0, "备注": ""},
                {"日期": "2027-01-05", "是否交易日": 1, "备注": ""},
            ]
        )
        self.app.replace_trading_calendar_override_rows(self.conn, partial_df, replace_same_years=True, source="unit-test")
        self.app.replace_trading_calendar_override_rows(self.conn, full_df, replace_same_years=True, source="unit-test")

        summary = self.app.fetch_trading_calendar_override_year_summary(self.conn)
        summary_map = {int(row["年份"]): str(row["覆盖状态"]) for _, row in summary.iterrows()}

        self.assertEqual(summary_map[2027], "部分覆盖")
        self.assertEqual(summary_map[2028], "全年覆盖")

    def test_build_year_df_from_trade_dates_marks_missing_days_as_non_trading(self) -> None:
        df = self.app.build_trading_calendar_year_df_from_trade_dates(
            [date(2026, 1, 2), date(2026, 1, 5)],
            2026,
            note="online",
        )

        self.assertEqual(len(df), 365)
        first_days = df.head(5)
        self.assertEqual(first_days["是否交易日"].tolist(), [0, 1, 0, 0, 1])
        self.assertTrue((first_days["备注"] == "online").all())

    def test_online_fetch_rejects_years_beyond_source_coverage(self) -> None:
        class _FakeAk:
            @staticmethod
            def tool_trade_date_hist_sina():
                return self.app.pd.DataFrame(
                    {"trade_date": ["2026-12-30", "2026-12-31"]}
                )

        old_offline = self.app.price_offline_mode_active
        old_loader = self.app._ensure_akshare_imported
        try:
            self.app.price_offline_mode_active = lambda *args, **kwargs: False
            self.app._ensure_akshare_imported = lambda: _FakeAk()
            df, meta = self.app.fetch_online_trading_calendar_year_df(2027)
        finally:
            self.app.price_offline_mode_active = old_offline
            self.app._ensure_akshare_imported = old_loader

        self.assertTrue(df.empty)
        self.assertFalse(meta["ok"])
        self.assertIn("2026-12-31", str(meta["message"]))

    def test_online_fetch_builds_full_year_when_source_is_complete(self) -> None:
        class _FakeAk:
            @staticmethod
            def tool_trade_date_hist_sina():
                return self.app.pd.DataFrame(
                    {"trade_date": ["2026-01-02", "2026-01-05", "2026-12-31"]}
                )

        old_offline = self.app.price_offline_mode_active
        old_loader = self.app._ensure_akshare_imported
        try:
            self.app.price_offline_mode_active = lambda *args, **kwargs: False
            self.app._ensure_akshare_imported = lambda: _FakeAk()
            df, meta = self.app.fetch_online_trading_calendar_year_df(2026)
        finally:
            self.app.price_offline_mode_active = old_offline
            self.app._ensure_akshare_imported = old_loader

        self.assertTrue(meta["ok"])
        self.assertEqual(len(df), 365)
        self.assertEqual(int(df[df["日期"] == "2026-01-02"]["是否交易日"].iloc[0]), 1)
        self.assertEqual(int(df[df["日期"] == "2026-01-01"]["是否交易日"].iloc[0]), 0)


    def test_trading_day_search_helpers_stop_when_calendar_has_no_trading_days(self) -> None:
        with mock.patch.object(self.app, "is_trading_day", return_value=False):
            with self.assertRaises(RuntimeError):
                self.app.add_trading_days(date(2026, 1, 1), 1)
            with self.assertRaises(RuntimeError):
                self.app.previous_trading_day(date(2026, 1, 1))


if __name__ == "__main__":
    unittest.main()
