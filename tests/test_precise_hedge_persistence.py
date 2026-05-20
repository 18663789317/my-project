import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_precise_hedge_persistence_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PreciseHedgePersistenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.app._FETCH_SQL_MEMO_CACHE.clear()
        self.app._LEDGER_MEMO_CACHE.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "精准套保测试组", "I.TEST"),
        )
        self._insert_structure("S001", group_id="G1")
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _insert_structure(self, structure_id: str, *, group_id: str) -> None:
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, structure_code, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_out, knock_out_price,
                multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                group_id,
                structure_id,
                structure_id,
                "I.TEST",
                "海证资本",
                "ACC",
                "BASIC_RANGE",
                "BASIC_RANGE",
                "2026-01-05",
                "2026-01-30",
                1000.0,
                100.0,
                95.0,
                110.0,
                110.0,
                3.0,
                json.dumps({}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )

    def test_insert_precise_hedge_calc_log_versions_increment_and_fetch_sorted(self) -> None:
        v1 = self.app.insert_precise_hedge_calc_log(
            self.conn,
            dt="2026-04-03",
            group_id="G1",
            structure_id="S001",
            underlying="I.TEST",
            close_price=790.0,
            current_position_tons=0.0,
            target_center_tons=-20000.0,
            target_lower_tons=-16000.0,
            target_upper_tons=-30000.0,
            recommended_position_tons=-12000.0,
            suggested_adjust_tons=-12000.0,
            current_hit_rate=0.62,
            under_prob=0.24,
            over_prob=0.14,
            history_samples=72,
            mc_paths=390000,
            atm_iv=25.0,
            skew=0.10,
            current_zone="中性区",
            action_type="加仓",
            confidence_level="中",
            risk_focus="欠保",
            fusion_mode="平衡",
            frozen_reason="",
            state_weighted_optimal=-11800.0,
            history_suggestion=-11000.0,
            mc_suggestion=-12500.0,
            fused_position=-11750.0,
            model_version="precise_test_v1",
            payload_json='{"k":"v1"}',
        )
        v2 = self.app.insert_precise_hedge_calc_log(
            self.conn,
            dt="2026-04-03",
            group_id="G1",
            structure_id="S001",
            underlying="I.TEST",
            close_price=791.0,
            current_position_tons=0.0,
            target_center_tons=-20000.0,
            target_lower_tons=-16000.0,
            target_upper_tons=-30000.0,
            recommended_position_tons=-13000.0,
            suggested_adjust_tons=-13000.0,
            current_hit_rate=0.66,
            under_prob=0.20,
            over_prob=0.12,
            history_samples=72,
            mc_paths=390000,
            atm_iv=25.0,
            skew=0.10,
            current_zone="敲入敏感区",
            action_type="加仓",
            confidence_level="高",
            risk_focus="欠保",
            fusion_mode="平衡",
            frozen_reason="",
            state_weighted_optimal=-12800.0,
            history_suggestion=-12000.0,
            mc_suggestion=-13500.0,
            fused_position=-12750.0,
            model_version="precise_test_v1",
            payload_json='{"k":"v2"}',
        )
        self.conn.commit()

        self.assertEqual(v1, 1)
        self.assertEqual(v2, 2)
        hist_df = self.app.fetch_precise_hedge_calc_logs(self.conn)
        hist_df = hist_df[hist_df["structure_id"].astype(str) == "S001"].copy()

        self.assertEqual(hist_df["version_no"].astype(int).tolist()[:2], [2, 1])
        self.assertAlmostEqual(float(hist_df.iloc[0]["recommended_position_tons"]), -13000.0)
        self.assertAlmostEqual(float(hist_df.iloc[1]["recommended_position_tons"]), -12000.0)
        self.assertEqual(str(hist_df.iloc[0]["payload_json"]), '{"k":"v2"}')

    def test_migrate_structure_related_records_updates_precise_hedge_logs(self) -> None:
        self._insert_structure("S010", group_id="G1")
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G2", "迁移目标组", "I.TEST"),
        )
        self._insert_structure("S020", group_id="G2")
        self.app.insert_precise_hedge_calc_log(
            self.conn,
            dt="2026-04-03",
            group_id="G1",
            structure_id="S010",
            underlying="I.TEST",
            close_price=790.0,
            current_position_tons=0.0,
            target_center_tons=-20000.0,
            target_lower_tons=-16000.0,
            target_upper_tons=-30000.0,
            recommended_position_tons=-12000.0,
            suggested_adjust_tons=-12000.0,
            current_hit_rate=0.62,
            under_prob=0.24,
            over_prob=0.14,
            history_samples=72,
            mc_paths=390000,
            atm_iv=25.0,
            skew=0.10,
            current_zone="中性区",
            action_type="加仓",
            confidence_level="中",
            risk_focus="欠保",
            fusion_mode="平衡",
            frozen_reason="",
            state_weighted_optimal=-11800.0,
            history_suggestion=-11000.0,
            mc_suggestion=-12500.0,
            fused_position=-11750.0,
            model_version="precise_test_v1",
        )
        self.app.insert_structure_position_adjustment_rows(
            self.conn,
            [
                {
                    "adjustment_id": "ADJ_MIGRATE_1",
                    "adjust_batch_id": "BATCH_MIGRATE",
                    "group_id": "G1",
                    "structure_id": "S010",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 120.0,
                    "before_qty": 1000.0,
                    "after_qty": 1120.0,
                    "basis_open_price": 100.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 09:00:00",
                    "created_by": "tester",
                },
            ],
        )
        self.conn.commit()

        self.app.migrate_structure_related_records_to_target_id(
            self.conn,
            source_structure_id="S010",
            target_structure_id="S020",
            target_group_id="G2",
        )
        self.conn.commit()

        row = self.conn.execute(
            """
            SELECT structure_id, group_id
            FROM precise_hedge_calc_log
            WHERE dt=? AND version_no=1
            """,
            ("2026-04-03",),
        ).fetchone()
        self.assertEqual(row, ("S020", "G2"))

        adj_row = self.conn.execute(
            """
            SELECT structure_id, group_id
            FROM structure_position_adjustment
            WHERE adjustment_id=?
            """,
            ("ADJ_MIGRATE_1",),
        ).fetchone()
        self.assertEqual(adj_row, ("S020", "G2"))

    def test_precise_hedge_collect_param_scan_candidate_rows_ignores_blank_editor_row(self) -> None:
        candidate_df = pd.DataFrame(
            [
                {"入场价": 812.5, "时间(BD)": 20, "参与率K": 3.0, "行权价": 800.0, "障碍价": 825.0},
                {"入场价": None, "时间(BD)": None, "参与率K": None, "行权价": None, "障碍价": None},
            ]
        )

        rows, issues = self.app.precise_hedge_collect_param_scan_candidate_rows(candidate_df)

        self.assertEqual(len(rows), 1)
        self.assertEqual(len(issues), 0)
        self.assertEqual(int(rows[0]["时间"]), 20)

    def test_precise_hedge_change_attribution_report_highlights_primary_driver(self) -> None:
        reference_metrics = {
            "close_price": 790.0,
            "current_position": 0.0,
            "remaining_days": 20,
            "atm_iv": 25.0,
            "skew": 0.10,
            "target_center": -20000.0,
            "target_lower": -30000.0,
            "target_upper": -16000.0,
            "recommended_position": -12000.0,
            "suggested_adjust_tons": -12000.0,
            "current_hit_rate": 0.62,
        }
        current_metrics = {
            "close_price": 794.0,
            "current_position": -3000.0,
            "remaining_days": 19,
            "atm_iv": 25.5,
            "skew": 0.10,
            "target_center": -20000.0,
            "target_lower": -30000.0,
            "target_upper": -16000.0,
            "recommended_position": -14500.0,
            "suggested_adjust_tons": -11500.0,
            "current_hit_rate": 0.66,
        }

        report = self.app.precise_hedge_build_change_attribution_report(current_metrics, reference_metrics)
        driver_df = report["driver_df"]

        self.assertFalse(driver_df.empty)
        self.assertEqual(str(driver_df.iloc[0]["驱动因子"]), "当前持仓")
        self.assertIn("当前持仓", str(report["driver_summary"]))
        self.assertIn("推荐仓位", str(report["output_summary"]))

    def test_precise_hedge_build_design_day_summary_uses_daily_state_counts(self) -> None:
        design_history_result = {
            "sample_count": 5,
            "path_len": 20,
            "summary": {
                "knockin_prob": 0.624,
                "no_knockin_no_knockout_prob": 0.016,
                "knockout_prob": 0.36,
                "dominant_scenario": "发生敲入",
            },
            "sample_df": pd.DataFrame(
                [
                    {"scenario_id": 1, "oscillation_days": 4, "knockin_days": 11, "knockout_days": 0, "first_ki_step": 5, "first_ko_step": None, "observed_days": 15},
                    {"scenario_id": 1, "oscillation_days": 3, "knockin_days": 12, "knockout_days": 0, "first_ki_step": 4, "first_ko_step": None, "observed_days": 15},
                    {"scenario_id": 3, "oscillation_days": 2, "knockin_days": 0, "knockout_days": 1, "first_ki_step": None, "first_ko_step": 3, "observed_days": 3},
                    {"scenario_id": 3, "oscillation_days": 5, "knockin_days": 0, "knockout_days": 1, "first_ki_step": None, "first_ko_step": 6, "observed_days": 6},
                    {"scenario_id": 2, "oscillation_days": 15, "knockin_days": 0, "knockout_days": 0, "first_ki_step": None, "first_ko_step": None, "observed_days": 15},
                ]
            ),
        }

        summary = self.app.precise_hedge_build_design_day_summary(
            design_history_result,
            template={"ko_terminate": True},
        )

        self.assertAlmostEqual(float(summary["knockin_expected_days"]), 4.6, places=2)
        self.assertAlmostEqual(float(summary["stable_expected_days"]), 5.8, places=2)
        self.assertAlmostEqual(float(summary["knockout_expected_days"]), 0.4, places=2)
        self.assertAlmostEqual(float(summary["knockout_trigger_median_day"]), 4.5, places=2)
        joined_notes = " ".join(summary["notes"])
        self.assertIn("平均敲入 4.6 天", joined_notes)
        self.assertIn("平均震荡 5.8 天", joined_notes)
        self.assertIn("第 5 天", joined_notes)
        self.assertIn("熔断/终止类样本", joined_notes)


if __name__ == "__main__":
    unittest.main()
