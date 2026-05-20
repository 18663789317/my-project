import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_self_quote_multi_structure_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    with contextlib.redirect_stderr(io.StringIO()):
        spec.loader.exec_module(module)
    return module


class SelfQuoteMultiStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_manual_base_scenarios_keep_their_own_strategy_code(self) -> None:
        for code in ("BASIC_RANGE", "SNOWBALL", "SAFETY_AIRBAG", self.app.VANILLA_OPTION_CODE):
            with self.subTest(code=code):
                resolved = self.app.volval_self_quote_manual_resolved(code, start_date_v="2026-05-14")
                scenario = self.app.volval_self_quote_base_scenario(resolved, scenario_id=f"{code}_case")

                self.assertEqual(scenario["strategy_code"], code)
                self.assertIn(scenario["reverse_variable"], self.app.volval_self_quote_reverse_options(code))

    def test_multi_structure_result_signatures_are_independent(self) -> None:
        basic_resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-14")
        snowball_resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-14")
        basic_scenario = self.app.volval_self_quote_base_scenario(basic_resolved, scenario_id="scheme_1")
        snowball_scenario = self.app.volval_self_quote_base_scenario(snowball_resolved, scenario_id="scheme_2")

        basic_sig = self.app.volval_self_quote_scenario_signature(
            code=basic_scenario["strategy_code"],
            selected_sid="MANUAL_BASIC_RANGE",
            record_key="scheme_1",
            scenario=basic_scenario,
            resolved=basic_resolved,
        )
        snowball_sig = self.app.volval_self_quote_scenario_signature(
            code=snowball_scenario["strategy_code"],
            selected_sid="MANUAL_SNOWBALL",
            record_key="scheme_2",
            scenario=snowball_scenario,
            resolved=snowball_resolved,
        )

        self.assertNotEqual(basic_sig, snowball_sig)

    def test_result_table_keeps_structure_type_column(self) -> None:
        frame = self.app.volval_self_quote_result_table_frame(
            [
                {
                    "方案": "方案1",
                    "结构类型": "普通累计",
                    "状态": "成功",
                    "反解变量": "行权价格",
                    "反解结果": "780.00",
                },
                {
                    "方案": "方案2",
                    "结构类型": "雪球结构",
                    "状态": "成功",
                    "反解变量": "票息",
                    "反解结果": "12.00%",
                },
            ]
        )

        self.assertIn("结构类型", frame.columns)
        self.assertEqual(frame["结构类型"].tolist(), ["普通累计", "雪球结构"])


if __name__ == "__main__":
    unittest.main()
