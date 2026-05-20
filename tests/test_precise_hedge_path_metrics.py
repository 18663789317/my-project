import importlib.util
import pathlib
import sys
import unittest

import numpy as np


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_precise_hedge_path_metric_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PreciseHedgePathMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_batch_metric_helpers_match_scalar_metrics(self) -> None:
        rng = np.random.default_rng(7)
        cum_exec_paths = np.cumsum(rng.uniform(0, 1500, size=(128, 12)), axis=1)
        future_qty = cum_exec_paths[:, -1]
        candidates = [-2500.0, 0.0, 2500.0, 5000.0]

        final_batch = self.app.precise_hedge_build_interval_metrics_batch(
            future_qty,
            candidate_positions=candidates,
            direction_sign=1.0,
            target_center=18000.0,
            target_lower=15000.0,
            target_upper=21000.0,
        )
        for idx, candidate in enumerate(candidates):
            final_single = self.app.precise_hedge_build_interval_metrics(
                future_qty + float(candidate),
                direction_sign=1.0,
                target_center=18000.0,
                target_lower=15000.0,
                target_upper=21000.0,
            )
            for key, value in final_single.items():
                self.assertAlmostEqual(float(final_batch[key][idx]), float(value), places=10, msg=f"final:{key}:{candidate}")

        path_batch = self.app.precise_hedge_build_path_interval_metrics_batch(
            cum_exec_paths,
            observed_qty=0.0,
            candidate_positions=candidates,
            direction_sign=1.0,
            target_center=18000.0,
            target_lower=15000.0,
            target_upper=21000.0,
        )
        for idx, candidate in enumerate(candidates):
            path_single = self.app.precise_hedge_build_path_interval_metrics(
                cum_exec_paths,
                observed_qty=0.0,
                candidate_position=float(candidate),
                direction_sign=1.0,
                target_center=18000.0,
                target_lower=15000.0,
                target_upper=21000.0,
            )
            for key, value in path_single.items():
                self.assertAlmostEqual(float(path_batch[key][idx]), float(value), places=10, msg=f"path:{key}:{candidate}")

    def test_scan_table_still_scores_by_path_not_only_terminal_state(self) -> None:
        future_qty = np.asarray([100.0, 100.0], dtype=float)
        cum_exec_paths = np.asarray([[100.0, 100.0], [0.0, 100.0]], dtype=float)

        with_path = self.app.precise_hedge_build_scan_table(
            future_qty_paths=future_qty,
            cum_exec_step_paths=cum_exec_paths,
            observed_qty=0.0,
            direction_sign=1.0,
            current_position=0.0,
            target_center=100.0,
            target_lower=90.0,
            target_upper=110.0,
            step_tons=100.0,
            scan_steps=1,
            named_positions={"当前持仓": 0.0},
        )
        with_path_row = with_path[with_path["候选仓位"].astype(float) == 0.0].iloc[0]
        self.assertEqual(str(with_path_row["评分口径"]), "全路径")
        self.assertAlmostEqual(float(with_path_row["终点命中率"]), 1.0, places=10)
        self.assertLess(float(with_path_row["近端覆盖率"]), float(with_path_row["终点命中率"]))

        terminal_only = self.app.precise_hedge_build_scan_table(
            future_qty_paths=future_qty,
            cum_exec_step_paths=None,
            observed_qty=0.0,
            direction_sign=1.0,
            current_position=0.0,
            target_center=100.0,
            target_lower=90.0,
            target_upper=110.0,
            step_tons=100.0,
            scan_steps=1,
            named_positions={"当前持仓": 0.0},
        )
        terminal_only_row = terminal_only[terminal_only["候选仓位"].astype(float) == 0.0].iloc[0]
        self.assertEqual(str(terminal_only_row["评分口径"]), "终点")
        self.assertAlmostEqual(float(terminal_only_row["区间命中率"]), 1.0, places=10)
        self.assertIn("path_scoring", str(self.app.PRECISE_HEDGE_MODEL_VERSION))

    def test_execution_distribution_summary_prefers_raw_mc_paths(self) -> None:
        mc_result = {
            "future_qty_paths": np.asarray([26000.0, 30000.0, 34000.0], dtype=float),
            "cum_exec_paths": np.asarray([30000.0, 34000.0, 38000.0], dtype=float),
            "runtime_state_seed": {"cum_qty": 4000.0},
        }

        distribution_summary, future_qty_summary, diagnostics = self.app.precise_hedge_build_execution_distribution_summaries(
            mc_result,
            observed_qty=4000.0,
        )

        self.assertAlmostEqual(float(distribution_summary["mean"]), 34000.0, places=10)
        self.assertAlmostEqual(float(distribution_summary["p50"]), 34000.0, places=10)
        self.assertGreater(float(distribution_summary["std"]), 0.0)
        self.assertAlmostEqual(float(future_qty_summary["mean"]), 30000.0, places=10)
        self.assertEqual(int(diagnostics["cum_exec_unique_count"]), 3)
        self.assertFalse(bool(diagnostics["is_degenerate"]))

    def test_execution_distribution_summary_falls_back_to_observed_plus_future_qty(self) -> None:
        mc_result = {
            "future_qty_paths": np.asarray([22000.0, 26000.0, 30000.0], dtype=float),
            "runtime_state_seed": {"cum_qty": 4000.0},
        }

        distribution_summary, future_qty_summary, diagnostics = self.app.precise_hedge_build_execution_distribution_summaries(
            mc_result,
            observed_qty=4000.0,
        )

        self.assertAlmostEqual(float(distribution_summary["mean"]), 30000.0, places=10)
        self.assertAlmostEqual(float(distribution_summary["min"]), 26000.0, places=10)
        self.assertAlmostEqual(float(distribution_summary["max"]), 34000.0, places=10)
        self.assertAlmostEqual(float(future_qty_summary["mean"]), 26000.0, places=10)
        self.assertFalse(bool(diagnostics["used_cum_exec_paths"]))

    def test_customer_qty_quantile_table_separates_future_and_final_qty(self) -> None:
        distribution_summary = {"p10": 26000.0, "p25": 28000.0, "p50": 30000.0, "p75": 32000.0, "p90": 34000.0}
        future_qty_summary = {"p10": 22000.0, "p25": 24000.0, "p50": 26000.0, "p75": 28000.0, "p90": 30000.0}

        table = self.app.precise_hedge_build_customer_qty_quantile_table(distribution_summary, future_qty_summary)

        self.assertEqual(list(table["分位线"]), ["P10", "P25", "P50", "P75", "P90"])
        p50 = table[table["分位线"].astype(str) == "P50"].iloc[0]
        self.assertEqual(str(p50["情景说明"]), "中性预估")
        self.assertAlmostEqual(float(p50["未来预计新增成交量"]), 26000.0, places=10)
        self.assertAlmostEqual(float(p50["预计最终累计成交量"]), 30000.0, places=10)

    def test_customer_metric_text_uses_plain_language_and_p50_qty(self) -> None:
        metrics = {
            "hit_rate": 0.297,
            "under_prob": 0.428,
            "over_prob": 0.276,
            "mean_abs_gap": 13689.0,
            "path_count": 1000.0,
        }
        qty_table = self.app.pd.DataFrame(
            [
                {"分位线": "P50", "情景说明": "中性预估", "未来预计新增成交量": 26000.0, "预计最终累计成交量": 30000.0},
            ]
        )
        state_rows = self.app.pd.DataFrame(
            [
                {"情景": "敲入情景", "当前路径数": 420},
                {"情景": "震荡/中性情景", "当前路径数": 330},
                {"情景": "敲出情景", "当前路径数": 250},
            ]
        )
        overview = self.app.precise_hedge_build_customer_path_state_overview(metrics, state_rows)

        text = self.app.precise_hedge_build_customer_path_metric_text(metrics, qty_table, overview, basis="逐日路径")

        self.assertIn("套少", text)
        self.assertIn("套多", text)
        self.assertIn("代表路径", text)
        self.assertIn("敲入状态", text)
        self.assertIn("敲出状态", text)
        self.assertEqual(int(overview["in_target_path_equiv"]), 297)
        self.assertEqual(int(overview["knock_in_paths"]), 420)
        self.assertEqual(int(overview["knock_out_paths"]), 250)
        self.assertIn("P50 中性预估", text)
        self.assertIn("未来还会新增成交", text)
        self.assertIn("最终累计成交", text)
        self.assertIn("不带方向", text)
        self.assertIn("不是多空正负号", text)
        self.assertNotIn("路径日点欠保", text)
        self.assertNotIn("平均绝对偏差", text)

    def test_validation_report_uses_path_day_points_not_only_terminal_state(self) -> None:
        sample_count = 20
        sample_df = self.app.pd.DataFrame(
            {
                "sample_index": np.arange(1, sample_count + 1, dtype=int),
                "future_qty": np.full(sample_count, 100.0, dtype=float),
                "scenario_id": np.full(sample_count, self.app.WINRATE_ACCUMULATOR_SCENARIO_NO_EVENT, dtype=int),
                "start_price": np.full(sample_count, 800.0, dtype=float),
                "start_dt": self.app.pd.date_range("2026-01-01", periods=sample_count, freq="D"),
            }
        )
        cum_exec_matrix = np.vstack(
            [
                np.asarray([0.0, 100.0], dtype=float) if idx % 2 == 0 else np.asarray([100.0, 100.0], dtype=float)
                for idx in range(sample_count)
            ]
        )

        report = self.app.precise_hedge_build_validation_report(
            history_result={"sample_df": sample_df, "cum_exec_path_matrix": cum_exec_matrix},
            template={"strategy_code": "BASIC_RANGE"},
            snapshot={"direction_sign": 1.0},
            target_center=100.0,
            target_lower=90.0,
            target_upper=110.0,
            scan_step_tons=100.0,
            scan_steps=2,
        )

        strategy_df = report["strategy_df"]
        self.assertIn("路径 P50 套保", set(strategy_df["策略"].astype(str)))
        detail_df = report["detail_df"]
        self.assertIn("路径日点", set(detail_df["验证口径"].astype(str)))
        precise_row = strategy_df[strategy_df["策略"].astype(str) == "当前精准套保策略"].iloc[0]
        self.assertLess(float(precise_row["目标区间命中率"]), 1.0)


if __name__ == "__main__":
    unittest.main()
