import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_special_page_perf_summary_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SpecialPagePerfSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_perf_stage_summary_groups_key_steps(self) -> None:
        perf = self.app.special_page_perf_start("专项：累计结构精准套保")
        perf.record_duration("历史行情缓存读取", 0.10, category="data")
        perf.record_duration("API拉取历史行情", 0.20, category="data")
        perf.record_duration("历史回溯主计算", 0.30, category="compute")
        perf.record_duration("Monte Carlo 主计算", 0.40, category="compute")
        perf.record_duration("决策层-状态层构建", 0.50, category="compute")

        summary = self.app.special_page_build_perf_stage_summary(perf)
        text = self.app.special_page_format_perf_stage_summary(summary)

        stage_by_name = {row["阶段"]: row for row in summary["stage_rows"]}
        self.assertAlmostEqual(float(stage_by_name["历史行情"]["耗时(ms)"]), 300.0, places=6)
        self.assertAlmostEqual(float(stage_by_name["历史回溯"]["耗时(ms)"]), 300.0, places=6)
        self.assertAlmostEqual(float(stage_by_name["Monte Carlo"]["耗时(ms)"]), 400.0, places=6)
        self.assertAlmostEqual(float(stage_by_name["决策统计"]["耗时(ms)"]), 500.0, places=6)
        self.assertIn("阶段耗时", text)
        self.assertIn("最慢步骤：决策层-状态层构建", text)


if __name__ == "__main__":
    unittest.main()
