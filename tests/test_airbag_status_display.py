import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_airbag_status_display_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AirbagStatusDisplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_build_airbag_status_display_lines_only_appends_participation_for_pending_observation(self) -> None:
        self.assertEqual(
            self.app.build_airbag_status_display_lines(
                "\u672a\u6572\u5165\u89c2\u5bdf",
                35,
            ),
            [
                "\u672a\u6572\u5165\u89c2\u5bdf",
                "\u53c2\u4e0e\u7387\uff1a35%",
            ],
        )
        self.assertEqual(
            self.app.build_airbag_status_display_lines(
                "\u5df2\u7ed3\u675f",
                35,
            ),
            [
                "\u5df2\u7ed3\u675f",
            ],
        )

    def test_apply_airbag_status_display_to_monitor_table_merges_participation_into_status_column(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "\u7b56\u7565\u7c7b\u578b": "\u5b89\u5168\u6c14\u56ca",
                    "\u65b9\u5411": "\u770b\u8dcc",
                    "\u72b6\u6001": "\u672a\u6572\u5165\u89c2\u5bdf",
                    "\u53c2\u4e0e\u7387\uff08%\uff09": 30,
                },
                {
                    "\u7b56\u7565\u7c7b\u578b": "\u5b89\u5168\u6c14\u56ca",
                    "\u65b9\u5411": "\u770b\u6da8",
                    "\u72b6\u6001": "\u5df2\u7ed3\u675f",
                    "\u53c2\u4e0e\u7387\uff08%\uff09": 35,
                },
                {
                    "\u7b56\u7565\u7c7b\u578b": "\u666e\u901a\u7d2f\u8ba1",
                    "\u65b9\u5411": "\u770b\u6da8",
                    "\u72b6\u6001": "\u6572\u5165\uff082\u500d\uff09",
                    "\u53c2\u4e0e\u7387\uff08%\uff09": 88,
                },
            ]
        )

        out = self.app.apply_airbag_status_display_to_monitor_table(df)

        self.assertIn("\u53c2\u4e0e\u7387\uff08%\uff09", out.columns)
        self.assertEqual(
            out.loc[0, "\u72b6\u6001"],
            "\u672a\u6572\u5165\u89c2\u5bdf\n\u53c2\u4e0e\u7387\uff1a30%",
        )
        self.assertEqual(
            out.loc[1, "\u72b6\u6001"],
            "\u5df2\u7ed3\u675f",
        )
        self.assertEqual(
            out.loc[2, "\u72b6\u6001"],
            "\u6572\u5165\uff082\u500d\uff09",
        )
        self.assertEqual(out.loc[0, "\u53c2\u4e0e\u7387\uff08%\uff09"], "")
        self.assertEqual(out.loc[2, "\u53c2\u4e0e\u7387\uff08%\uff09"], 88)

    def test_apply_airbag_status_display_drops_participation_when_all_rows_are_airbag(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "\u7b56\u7565\u7c7b\u578b": "\u5b89\u5168\u6c14\u56ca",
                    "\u72b6\u6001": "\u672a\u6572\u5165\u89c2\u5bdf",
                    "\u53c2\u4e0e\u7387\uff08%\uff09": 30,
                }
            ]
        )

        out = self.app.apply_airbag_status_display_to_monitor_table(df)

        self.assertNotIn("\u53c2\u4e0e\u7387\uff08%\uff09", out.columns)
        self.assertEqual(
            out.loc[0, "\u72b6\u6001"],
            "\u672a\u6572\u5165\u89c2\u5bdf\n\u53c2\u4e0e\u7387\uff1a30%",
        )

    def test_airbag_participation_color_follows_direction(self) -> None:
        self.assertEqual(
            self.app.airbag_participation_color("\u770b\u6da8"),
            "#ff7f79",
        )
        self.assertEqual(
            self.app.airbag_participation_color("ACC"),
            "#ff7f79",
        )
        self.assertEqual(
            self.app.airbag_participation_color("\u770b\u8dcc"),
            "#67d67d",
        )
        self.assertEqual(
            self.app.airbag_participation_color("DEC"),
            "#67d67d",
        )


if __name__ == "__main__":
    unittest.main()
