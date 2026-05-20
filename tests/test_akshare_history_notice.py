import importlib.util
import pathlib
import sys
import unittest
from datetime import date
from unittest import mock


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_akshare_history_notice_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AkshareHistoryNoticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_busy_history_fetch_notice_is_quiet(self) -> None:
        msg = "RuntimeError: 上一笔 AKShare 历史收盘价请求仍在执行，已跳过本次联网获取；页面可继续手工录入。"

        self.assertTrue(self.app.is_quiet_akshare_history_notice(msg))
        self.assertFalse(self.app.should_show_special_history_error(msg))

    def test_real_history_error_still_shows(self) -> None:
        msg = "RuntimeError: 历史样本不足：至少需要 60 个收盘价，当前仅 12 个"

        self.assertFalse(self.app.is_quiet_akshare_history_notice(msg))
        self.assertTrue(self.app.should_show_special_history_error(msg))

    def test_realtime_and_history_price_fetches_have_separate_locks(self) -> None:
        self.assertIsNot(
            self.app._AK_REALTIME_PRICE_TIMEOUT_SLOT,
            self.app._AK_HISTORY_PRICE_TIMEOUT_SLOT,
        )
        self.assertIsNot(
            self.app._AK_REALTIME_PRICE_TIMEOUT_EXECUTOR,
            self.app._AK_HISTORY_PRICE_TIMEOUT_EXECUTOR,
        )

    def test_busy_realtime_fetch_does_not_block_history_fetch(self) -> None:
        acquired = self.app._AK_REALTIME_PRICE_TIMEOUT_SLOT.acquire(blocking=False)
        self.assertTrue(acquired)
        try:
            data_df = self.app.pd.DataFrame(
                [{"交易日": "2026-04-20", "品种": "I.DCE", "收盘价(API)": 809.0}]
            )
            empty_err = self.app.pd.DataFrame(columns=["品种", "原因"])
            empty_info = self.app.pd.DataFrame(columns=["品种", "提示"])
            with mock.patch.object(
                self.app,
                "_fetch_akshare_close_candidates_payload",
                return_value={
                    "ok": True,
                    "data_df": data_df,
                    "err_df": empty_err,
                    "info_df": empty_info,
                },
            ) as mocked_fetch:
                got_data, got_err, _got_info = self.app.fetch_akshare_close_candidates_with_meta_timeout(
                    ["I.DCE"],
                    date(2026, 4, 20),
                    date(2026, 4, 20),
                    timeout_sec=1.0,
                )

            mocked_fetch.assert_called_once()
            self.assertFalse(got_data.empty)
            self.assertTrue(got_err.empty)
        finally:
            self.app._AK_REALTIME_PRICE_TIMEOUT_SLOT.release()


if __name__ == "__main__":
    unittest.main()
