import ast
import copy
import pathlib
import unittest
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

TARGET_SYMBOLS = {
    "probexp_clamp_probability",
    "probexp_estimate_generated_avg_price",
    "probexp_group_contribution_df",
    "probexp_group_current_price_for_view",
    "probexp_group_probability_band_df",
    "probexp_group_probability_segments",
    "probexp_group_position_price_view",
    "probexp_group_diagnostic_reason",
    "probexp_group_priority_action_label",
    "probexp_group_priority_diagnostics_df",
    "probexp_group_report_comparison_lines",
    "probexp_group_report_metric_delta_df",
    "probexp_group_profile",
    "probexp_group_profile_metric",
    "probexp_group_result_key_for_period",
    "probexp_group_risk_level",
    "probexp_group_risk_side",
    "probexp_group_risk_tags",
    "probexp_group_structure_delta_df",
    "probexp_group_structure_detail_text",
    "probexp_plain_signed_pp",
    "probexp_plain_signed_price",
    "probexp_group_weighted_avg",
    "probexp_group_weighted_avg_price",
    "probexp_plain_pct",
    "probexp_plain_price",
    "probexp_plain_tons",
    "probexp_summarize_group_period",
}


def load_symbols() -> Dict[str, Any]:
    source = APP_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(APP_PATH))
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGET_SYMBOLS:
            body.append(copy.deepcopy(node))
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)

    def pick_first(*vals: Any) -> Any:
        for val in vals:
            if val is not None:
                return val
        return None

    def to_float(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _int_from_any(value: Any, default: int = 0, **_: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return int(default)

    env: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "Any": Any,
        "Callable": Callable,
        "Dict": Dict,
        "List": List,
        "Mapping": Mapping,
        "Optional": Optional,
        "Sequence": Sequence,
        "Tuple": Tuple,
        "np": np,
        "pd": pd,
        "pick_first": pick_first,
        "to_float": to_float,
        "_int_from_any": _int_from_any,
        "PROBEXP_HIT_BAND_DEFAULT_LABEL": "标准",
    }
    exec(compile(module, str(APP_PATH), "exec"), env)
    return env


def profile(hit: float, under: float, over: float, before_hit: float = 0.0) -> Dict[str, Any]:
    return {
        "default_profile": {
            "label": "标准",
            "before": {"hit_rate": before_hit},
            "after": {"hit_rate": hit, "under_prob": under, "over_prob": over},
        },
        "profiles": [
            {"label": "精准", "after": {"hit_rate": max(hit - 0.05, 0.0)}},
            {"label": "标准", "before": {"hit_rate": before_hit}, "after": {"hit_rate": hit, "under_prob": under, "over_prob": over}},
            {"label": "宽口径", "after": {"hit_rate": min(hit + 0.15, 1.0)}},
        ],
    }


class ProbexpGroupRollupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ns = load_symbols()

    def test_summary_uses_weighted_probabilities_and_summed_tons(self) -> None:
        summarize = self.ns["probexp_summarize_group_period"]
        rows = [
            {
                "weight": 100.0,
                "live_result": {
                    "remaining_days": 10,
                    "target_hedge_qty": 1000.0,
                    "current_position": 100.0,
                    "target_position": 120.0,
                    "current_after": 120.0,
                    "adjust_tons_exec": 20.0,
                    "mean_future_position": 40.0,
                    "mean_future_qty": 40.0,
                    "expected_generated_avg_price": 100.0,
                    "mean_generated_total_position": 50.0,
                    "mean_final_total_after": 170.0,
                    "future_position_quantiles": {"P10": 4.0, "P20": 8.0, "P50": 10.0, "P80": 12.0, "P95": 16.0, "P97.5": 18.0},
                    "mc_paths": 10000,
                    "hedge_metrics": profile(0.20, 0.10, 0.40, before_hit=0.10),
                },
            },
            {
                "weight": 300.0,
                "live_result": {
                    "remaining_days": 20,
                    "target_hedge_qty": 3000.0,
                    "current_position": 300.0,
                    "target_position": 360.0,
                    "current_after": 360.0,
                    "adjust_tons_exec": 60.0,
                    "mean_future_position": 120.0,
                    "mean_future_qty": 120.0,
                    "expected_generated_avg_price": 200.0,
                    "mean_generated_total_position": 150.0,
                    "mean_final_total_after": 510.0,
                    "future_position_quantiles": {"P10": 12.0, "P20": 24.0, "P50": 30.0, "P80": 36.0, "P95": 48.0, "P97.5": 54.0},
                    "mc_paths": 20000,
                    "hedge_metrics": profile(0.80, 0.30, 0.20, before_hit=0.30),
                },
            },
        ]

        summary = summarize(rows, result_key="live_result", period_label="剩余周期")

        self.assertEqual(summary["structure_count"], 2)
        self.assertAlmostEqual(summary["hit_rate"], 0.65)
        self.assertAlmostEqual(summary["under_prob"], 0.25)
        self.assertAlmostEqual(summary["over_prob"], 0.25)
        self.assertAlmostEqual(summary["before_hit_rate"], 0.25)
        self.assertAlmostEqual(summary["precise_hit_rate"], 0.60)
        self.assertAlmostEqual(summary["wide_hit_rate"], 0.80)
        self.assertAlmostEqual(summary["remaining_days_avg"], 17.5)
        self.assertAlmostEqual(summary["expected_generated_avg_price"], 175.0)
        self.assertAlmostEqual(summary["target_hedge_qty"], 4000.0)
        self.assertAlmostEqual(summary["adjust_tons_exec"], 80.0)
        self.assertAlmostEqual(summary["p50_future_position"], 40.0)
        self.assertEqual(summary["mc_paths_total"], 30000)

    def test_contribution_df_explains_weighted_group_risk(self) -> None:
        contribution_df = self.ns["probexp_group_contribution_df"]
        report = {
            "structure_results": [
                {
                    "structure_id": "S1",
                    "structure_display_id": "S1",
                    "label": "alpha",
                    "underlying": "I2609",
                    "direction_cn": "看涨",
                    "status_cn": "存续",
                    "weight": 100.0,
                    "live_result": {
                        "remaining_days": 10,
                        "adjust_tons_exec": -20.0,
                        "mean_future_position": 40.0,
                        "expected_generated_avg_price": 100.0,
                        "future_position_quantiles": {"P50": 10.0},
                        "hedge_metrics": profile(0.20, 0.10, 0.40),
                    },
                },
                {
                    "structure_id": "S2",
                    "structure_display_id": "S2",
                    "label": "beta",
                    "underlying": "I2609",
                    "direction_cn": "看涨",
                    "status_cn": "存续",
                    "weight": 300.0,
                    "live_result": {
                        "remaining_days": 3,
                        "adjust_tons_exec": 60.0,
                        "mean_future_position": 120.0,
                        "expected_generated_avg_price": 200.0,
                        "future_position_quantiles": {"P50": 30.0},
                        "hedge_metrics": profile(0.80, 0.30, 0.20),
                    },
                },
            ]
        }

        df = contribution_df(report, period_label="剩余周期")

        self.assertEqual(len(df), 2)
        self.assertAlmostEqual(float(df["欠保贡献"].sum()), 0.25)
        self.assertAlmostEqual(float(df["超保贡献"].sum()), 0.25)
        self.assertEqual(str(df.iloc[0]["结构"]), "S2")
        self.assertEqual(str(df.iloc[0]["风险方向"]), "欠保")
        self.assertIn("中欠保", str(df.iloc[0]["风险标签"]))
        self.assertIn("临近到期", str(df.iloc[0]["风险标签"]))

    def test_probability_band_normalizes_display_when_raw_sum_exceeds_one(self) -> None:
        band_df = self.ns["probexp_group_probability_band_df"]
        report = {
            "build_summary": {"hit_rate": 0.55, "under_prob": 0.25, "over_prob": 0.30},
            "live_summary": {"hit_rate": 0.30, "under_prob": 0.20, "over_prob": 0.40},
        }

        df = band_df(report)
        build_row = df[df["分析口径"].eq("完整周期")].iloc[0]
        live_row = df[df["分析口径"].eq("剩余周期")].iloc[0]

        self.assertEqual(str(df.iloc[0]["分析口径"]), "剩余周期")
        self.assertEqual(str(live_row["主风险"]), "超保")
        self.assertAlmostEqual(float(live_row["主风险概率"]), 0.40)
        self.assertAlmostEqual(float(build_row["原始合计"]), 1.10)
        self.assertAlmostEqual(
            float(build_row["显示欠保概率"] + build_row["显示命中率"] + build_row["显示超保概率"]),
            1.0,
        )
        self.assertAlmostEqual(float(live_row["未归类概率"]), 0.10)

    def test_priority_diagnostics_picks_top_structures(self) -> None:
        diagnostics_df = self.ns["probexp_group_priority_diagnostics_df"]
        contribution_df = pd.DataFrame(
            [
                {
                    "结构": "S1",
                    "品种": "I2609",
                    "方向": "看涨",
                    "风险方向": "超保",
                    "风险等级": "观察",
                    "权重占比": 0.10,
                    "主风险概率": 0.28,
                    "主风险贡献": 0.028,
                    "欠保贡献": 0.005,
                    "超保贡献": 0.028,
                    "剩余交易日": 12,
                    "建议净变动(吨)": 0.0,
                },
                {
                    "结构": "S2",
                    "品种": "I2609",
                    "方向": "看涨",
                    "风险方向": "欠保",
                    "风险等级": "高",
                    "权重占比": 0.24,
                    "主风险概率": 0.52,
                    "主风险贡献": 0.125,
                    "欠保贡献": 0.125,
                    "超保贡献": 0.010,
                    "剩余交易日": 3,
                    "建议净变动(吨)": 600.0,
                },
                {
                    "结构": "S3",
                    "品种": "I2609",
                    "方向": "看涨",
                    "风险方向": "超保",
                    "风险等级": "中",
                    "权重占比": 0.18,
                    "主风险概率": 0.35,
                    "主风险贡献": 0.063,
                    "欠保贡献": 0.015,
                    "超保贡献": 0.063,
                    "剩余交易日": 9,
                    "建议净变动(吨)": -200.0,
                },
            ]
        )

        df = diagnostics_df(contribution_df, top_n=2)

        self.assertEqual(len(df), 2)
        self.assertEqual(str(df.iloc[0]["结构编号"]), "S2")
        detail_text = str(df.iloc[0]["结构详情"])
        self.assertIn("S2", detail_text)
        self.assertNotIn("I2609", detail_text)
        self.assertNotIn(" / ", detail_text)
        self.assertEqual(str(df.iloc[0]["关注动作"]), "优先处理")
        self.assertAlmostEqual(float(df.iloc[0]["主风险贡献"]), 0.125)
        self.assertIn("主风险概率", str(df.iloc[0]["诊断"]))

    def test_group_report_comparison_builds_metric_and_structure_deltas(self) -> None:
        metric_delta_df = self.ns["probexp_group_report_metric_delta_df"]
        structure_delta_df = self.ns["probexp_group_structure_delta_df"]
        comparison_lines = self.ns["probexp_group_report_comparison_lines"]
        previous_report = {
            "group_id": "G001",
            "rep_date": "2026-04-28",
            "live_summary": {
                "under_prob": 0.20,
                "over_prob": 0.30,
                "hit_rate": 0.50,
                "mean_future_position": -100.0,
                "expected_generated_avg_price": 780.0,
                "adjust_tons_exec": -8000.0,
            },
            "structure_results": [
                {
                    "structure_id": "S1",
                    "structure_display_id": "S1",
                    "label": "alpha",
                    "underlying": "I2609",
                    "direction_cn": "看跌",
                    "weight": 100.0,
                    "live_result": {
                        "remaining_days": 10,
                        "adjust_tons_exec": 0.0,
                        "mean_future_position": -40.0,
                        "hedge_metrics": profile(0.50, 0.10, 0.30),
                    },
                },
                {
                    "structure_id": "S2",
                    "structure_display_id": "S2",
                    "label": "beta",
                    "underlying": "I2609",
                    "direction_cn": "看跌",
                    "weight": 100.0,
                    "live_result": {
                        "remaining_days": 10,
                        "adjust_tons_exec": 0.0,
                        "mean_future_position": -60.0,
                        "hedge_metrics": profile(0.50, 0.10, 0.20),
                    },
                },
            ],
        }
        current_report = {
            "group_id": "G001",
            "rep_date": "2026-04-29",
            "live_summary": {
                "under_prob": 0.15,
                "over_prob": 0.42,
                "hit_rate": 0.43,
                "mean_future_position": -160.0,
                "expected_generated_avg_price": 792.0,
                "adjust_tons_exec": 37800.0,
            },
            "structure_results": [
                {
                    "structure_id": "S1",
                    "structure_display_id": "S1",
                    "label": "alpha",
                    "underlying": "I2609",
                    "direction_cn": "看跌",
                    "weight": 100.0,
                    "live_result": {
                        "remaining_days": 10,
                        "adjust_tons_exec": 0.0,
                        "mean_future_position": -40.0,
                        "hedge_metrics": profile(0.50, 0.10, 0.35),
                    },
                },
                {
                    "structure_id": "S2",
                    "structure_display_id": "S2",
                    "label": "beta",
                    "underlying": "I2609",
                    "direction_cn": "看跌",
                    "weight": 100.0,
                    "live_result": {
                        "remaining_days": 10,
                        "adjust_tons_exec": 0.0,
                        "mean_future_position": -60.0,
                        "hedge_metrics": profile(0.50, 0.10, 0.50),
                    },
                },
            ],
        }

        metric_df = metric_delta_df(current_report, previous_report)
        structure_df = structure_delta_df(current_report, previous_report, top_n=1)
        lines = comparison_lines(current_report, previous_report)

        over_row = metric_df[metric_df["指标"].eq("剩余超保概率")].iloc[0]
        adjust_row = metric_df[metric_df["指标"].eq("建议净变动")].iloc[0]
        self.assertAlmostEqual(float(over_row["变化原始值"]), 0.12)
        self.assertEqual(str(over_row["变化"]), "+12.0pp")
        self.assertAlmostEqual(float(adjust_row["变化原始值"]), 45800.0)
        self.assertEqual(str(structure_df.iloc[0]["结构"]), "S2")
        self.assertGreater(float(structure_df.iloc[0]["贡献变化"]), 0.0)
        self.assertIn("较 2026-04-28", lines[0])
        self.assertIn("建议净变动变化", lines[0])

    def test_position_price_view_collects_group_level_visual_values(self) -> None:
        build_view = self.ns["probexp_group_position_price_view"]
        report = {
            "underlyings": ["I2609"],
            "build_summary": {"expected_generated_avg_price": 785.62},
            "live_summary": {
                "current_position": 1000.0,
                "current_after": 950.0,
                "mean_future_position": 300.0,
                "mean_final_total_after": 1250.0,
                "target_position": 1400.0,
                "adjust_tons_exec": -50.0,
                "p10_future_position": 120.0,
                "p50_future_position": 260.0,
                "p95_future_position": 520.0,
                "expected_generated_avg_price": 792.18,
            },
            "structure_results": [
                {"weight": 100.0, "live_result": {"current_close": 800.0}},
                {"weight": 300.0, "live_result": {"current_close": 820.0}},
            ],
        }

        view = build_view(report)

        self.assertAlmostEqual(float(view["current_position"]), 1000.0)
        self.assertAlmostEqual(float(view["mean_future_position"]), 300.0)
        self.assertAlmostEqual(float(view["expected_final_position"]), 1250.0)
        self.assertAlmostEqual(float(view["target_position"]), 1400.0)
        self.assertAlmostEqual(float(view["adjust_tons_exec"]), -50.0)
        self.assertAlmostEqual(float(view["current_price"]), 815.0)
        self.assertAlmostEqual(float(view["live_avg_price"]), 792.18)

    def test_estimate_generated_avg_price_uses_generated_tons_as_weight(self) -> None:
        estimate = self.ns["probexp_estimate_generated_avg_price"]
        rec = estimate(
            {
                "sample_daily_exec_paths": np.asarray([[1.0, 3.0], [0.0, 2.0]], dtype=float),
                "sample_price_paths": np.asarray([[100.0, 110.0], [120.0, 130.0]], dtype=float),
            }
        )

        self.assertAlmostEqual(rec["avg_price"], (1 * 100 + 3 * 110 + 2 * 130) / 6)
        self.assertAlmostEqual(rec["sample_generated_qty"], 6.0)
        self.assertEqual(rec["sample_points"], 3)


if __name__ == "__main__":
    unittest.main()
