import contextlib
import importlib.util
import io
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_self_quote_multi_value_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    with contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


class SelfQuoteMultiValuePresetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_presets_are_persisted_and_deduplicated_by_structure_and_field(self) -> None:
        spec = {"integer": True, "min_value": 1.0, "max_value": 3660.0, "digits": 0}
        values, err, value_text, normalized_key = self.app.volval_self_quote_multi_value_prepare(
            "10 15 20 25",
            field="term_trading_days",
            spec=spec,
        )
        self.assertFalse(err)

        first_id = self.app.upsert_self_quote_multi_value_preset(
            self.conn,
            strategy_code="SAFETY_AIRBAG",
            field_key="term_trading_days",
            field_label="期限",
            value_text=value_text,
            values=values,
            normalized_key=normalized_key,
            created_by="tester",
        )
        second_id = self.app.upsert_self_quote_multi_value_preset(
            self.conn,
            strategy_code="SAFETY_AIRBAG",
            field_key="term_trading_days",
            field_label="期限",
            value_text=value_text,
            values=values,
            normalized_key=normalized_key,
            created_by="tester",
        )

        rows = self.app.fetch_self_quote_multi_value_presets(
            self.conn,
            "SAFETY_AIRBAG",
            "term_trading_days",
        )
        self.assertEqual(first_id, second_id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value_text"], "10 15 20 25")

    def test_quick_input_is_hidden_once_user_enters_multiple_values(self) -> None:
        spec = {"integer": True, "min_value": 1.0, "max_value": 3660.0, "digits": 0}

        self.assertTrue(
            self.app.volval_self_quote_multi_value_should_show_quick_input(
                "",
                field="term_trading_days",
                spec=spec,
            )
        )
        self.assertTrue(
            self.app.volval_self_quote_multi_value_should_show_quick_input(
                "20",
                field="term_trading_days",
                spec=spec,
            )
        )
        self.assertFalse(
            self.app.volval_self_quote_multi_value_should_show_quick_input(
                "20 24",
                field="term_trading_days",
                spec=spec,
            )
        )

    def test_supported_self_quote_structures_expose_multi_value_fields(self) -> None:
        for code in (
            "BASIC_RANGE",
            "FLOAT_KO",
            "FIXED_SUBSIDY",
            "RANGE_SUBSIDY",
            "SAFETY_AIRBAG",
            "SNOWBALL",
            self.app.VANILLA_OPTION_CODE,
        ):
            with self.subTest(code=code):
                fields = self.app.volval_self_quote_multi_value_fields_for_code(code)
                self.assertTrue(fields)
                self.assertIn("iv_pct", fields)

    def test_manual_type_options_cover_supported_self_quote_structures(self) -> None:
        options = self.app.volval_self_quote_manual_type_options()
        self.assertTrue(options)
        codes = {self.app.VOLVAL_SELF_QUOTE_MANUAL_TYPE_TO_CODE[label] for label in options}
        self.assertEqual(codes, set(self.app.VOLVAL_SELF_QUOTE_CODES))
        self.assertEqual(self.app.volval_self_quote_manual_type_label_for_code("BASIC_RANGE"), "普通累计")
        self.assertEqual(self.app.volval_self_quote_manual_type_label_for_code(self.app.VANILLA_OPTION_CODE), "香草期权")

    def test_quick_preset_popover_uses_icon_label_without_common_text(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertNotIn('st.popover("常用"', source)
        self.assertEqual(self.app.VOLVAL_SELF_QUOTE_QUICK_PRESET_POPOVER_LABEL, "\u200b")


    def test_self_quote_price_inputs_select_all_on_click(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("inject_volval_self_quote_numeric_input_polish()", source)
        self.assertIn("otcSelfQuoteSelectBound", source)
        self.assertIn('"行权价"', source)
        self.assertIn('"敲出价"', source)


if __name__ == "__main__":
    unittest.main()
