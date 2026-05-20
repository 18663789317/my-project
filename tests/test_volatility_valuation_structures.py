import importlib.util
import inspect
import json
import pathlib
import sqlite3
import sys
import unittest

import numpy as np
import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_volval_structure_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class VolatilityValuationStructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def _basic_range_template(self):
        return {
            "strategy_code": "BASIC_RANGE",
            "kind": "DEC",
            "path_len": 8,
            "template_dates": [
                "2026-05-04",
                "2026-05-05",
                "2026-05-06",
                "2026-05-07",
                "2026-05-08",
                "2026-05-11",
                "2026-05-12",
                "2026-05-13",
            ],
            "resolved": {
                "structure_id": "ACC-1",
                "strategy_code": "BASIC_RANGE",
                "kind": "DEC",
                "base_qty_per_day": 100.0,
                "entry_price": 800.0,
                "strike_price": 800.0,
                "barrier_out": 760.0,
                "knock_out_price": 760.0,
                "multiple": 3.0,
                "params": {"n_days": 8},
                "meta": {"n_days": 8},
            },
        }

    def _airbag_template(self):
        return {
            "strategy_code": "SAFETY_AIRBAG",
            "kind": "ACC",
            "path_len": 8,
            "template_dates": [
                "2026-05-04",
                "2026-05-05",
                "2026-05-06",
                "2026-05-07",
                "2026-05-08",
                "2026-05-11",
                "2026-05-12",
                "2026-05-13",
            ],
            "resolved": {
                "structure_id": "AIRBAG-1",
                "strategy_code": "SAFETY_AIRBAG",
                "kind": "ACC",
                "base_qty_per_day": 100.0,
                "entry_price": 800.0,
                "strike_price": 780.0,
                "barrier_out": 720.0,
                "knock_out_price": 720.0,
                "multiple": 80.0,
                "params": {"n_days": 8},
                "meta": {"n_days": 8},
            },
        }

    def _assert_model_iv_recovers_target(self, template, target_iv: float) -> None:
        value_result = self.app.winrate_structure_model_value_for_iv(
            template,
            start_price=800.0,
            atm_iv_pct=target_iv,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=123,
            seed_hint="volval-structure-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
            carry_yield_pct=0.0,
            futures_mode=True,
        )

        implied = self.app.winrate_structure_model_implied_volatility(
            template,
            start_price=800.0,
            target_value=float(value_result["value"]),
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=123,
            seed_hint="volval-structure-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=0.0,
            carry_yield_pct=0.0,
            futures_mode=True,
        )

        self.assertTrue(implied["ok"], implied.get("message"))
        self.assertAlmostEqual(float(implied["implied_vol_pct"]), target_iv, places=8)
        self.assertAlmostEqual(float(implied["value"]), float(value_result["value"]), places=6)

    def test_bs_valuation_uses_known_start_price_when_template_starts_on_trade_date(self) -> None:
        cases = [
            ("BASIC_RANGE", {}),
            ("SAFETY_AIRBAG", {}),
            (
                "SNOWBALL",
                {
                    "snowball_term_unit": "WEEK",
                    "snowball_term_count": 8,
                    "snowball_ko_obs_freq": "WEEKLY",
                    "snowball_lock_enabled": False,
                    "snowball_lock_ko_obs": 0,
                },
            ),
        ]
        for code, overrides in cases:
            with self.subTest(code=code):
                resolved = self.app.volval_self_quote_manual_resolved(code, start_date_v="2026-05-06")
                scenario = self.app.volval_self_quote_base_scenario(resolved)
                scenario.update(overrides)
                if code == "SNOWBALL":
                    scenario = self.app.volval_self_quote_sync_snowball_period(scenario)
                applied = self.app.volval_self_quote_apply_scenario(resolved, scenario)
                template = self.app.volval_template_with_dates(
                    self.app.winrate_prepare_structure_template(applied),
                    start_date_v=scenario["start_date"],
                    end_date_v=scenario["end_date"],
                    day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
                )

                valuation = self.app.winrate_structure_model_value_for_iv(
                    template,
                    start_price=float(scenario["spot_price"]),
                    atm_iv_pct=20.0,
                    skew=0.0,
                    paths=1000,
                    trading_days_per_year=252,
                    seed=123,
                    seed_hint=f"known-start-{code}",
                    valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
                    risk_free_rate_pct=2.0,
                    carry_yield_pct=0.0,
                    futures_mode=True,
                )
                sample_paths = np.asarray(valuation["sample_price_paths"], dtype=float)

                self.assertTrue(bool(template["mc_include_start_price"]))
                self.assertGreater(sample_paths.shape[0], 0)
                self.assertTrue(np.allclose(sample_paths[:, 0], float(scenario["spot_price"])))

    def test_structure_type_labels_cover_vanilla_accumulator_and_airbag(self) -> None:
        self.assertEqual(self.app.volval_structure_type_label(self.app.VANILLA_OPTION_CODE), "香草")
        self.assertEqual(self.app.volval_structure_type_label("BASIC_RANGE"), "累计")
        self.assertEqual(self.app.volval_structure_type_label("SAFETY_AIRBAG"), "气囊")

    def test_structure_select_label_marks_active_and_orders_accumulator_prices(self) -> None:
        resolved = {
            "structure_id": "S001",
            "strategy_code": "BASIC_RANGE",
            "kind": "DEC",
            "name": "",
            "risk_party": "\u4e1c\u6d77\u8d44\u672c",
            "entry_price": 790.0,
            "strike_price": 825.0,
            "barrier_out": 760.0,
        }

        detail = self.app.volval_structure_select_detail_label(resolved, "S001")
        self.assertIn(
            "\u969c\u788d\u4ef7\uff08760.0\uff09-\u5165\u573a\u4ef7\uff08790.0\uff09-\u884c\u6743\u4ef7\uff08825.0\uff09",
            detail,
        )
        label = self.app.volval_structure_select_label(
            self.app.VOLVAL_STRUCTURE_TYPE_ACCUMULATOR,
            detail,
            is_active=True,
        )
        self.assertTrue(label.endswith(" | \u5b58\u7eed"))
        self.assertTrue(
            self.app.volval_structure_select_label_with_implied_iv(label, 18.5).endswith(" | \u5b58\u7eed 18.5%")
        )
        self.assertTrue(
            self.app.volval_structure_select_label_with_implied_iv("S001-detail", 16.54).endswith(" | \u5b58\u7eed 16.5%")
        )

    def test_model_iv_session_records_are_active_only(self) -> None:
        key = self.app.volval_bulk_model_iv_state_key("G1")
        self.app.st.session_state.pop(key, None)

        self.app.volval_store_model_iv_session_record("G1", "SID_A", 16.54, message="ok")

        active_row = {"structure_id": "SID_A", "is_active": True}
        inactive_row = {"structure_id": "SID_A", "is_active": False}
        self.assertAlmostEqual(
            float(self.app.volval_pick_model_iv_pct("G1", "SID_A", row=active_row)),
            16.54,
            places=8,
        )
        self.assertIsNone(self.app.volval_pick_model_iv_pct("G1", "SID_A", row=inactive_row))

        self.app.volval_prune_model_iv_session_map("G1", [inactive_row])
        self.assertIn("SID_A", self.app.st.session_state.get(key, {}))

        self.app.volval_prune_model_iv_session_map("G1", [])
        self.assertIn("SID_A", self.app.st.session_state.get(key, {}))

        self.app.st.session_state.pop(key, None)
        saved_active_row = {
            "structure_id": "SID_DB",
            "is_active": True,
            "resolved": {"implied_vol_pct": 22.25},
        }
        saved_inactive_row = {
            "structure_id": "SID_DB",
            "is_active": False,
            "resolved": {"implied_vol_pct": 22.25},
        }
        self.assertAlmostEqual(
            float(self.app.volval_pick_model_iv_pct("G1", "SID_DB", row=saved_active_row)),
            22.25,
            places=8,
        )
        self.assertIsNone(self.app.volval_pick_model_iv_pct("G1", "SID_DB", row=saved_inactive_row))

    def test_auto_seeded_price_input_replaces_stale_min_value(self) -> None:
        state_key = "unit_backtest_s0"
        seed_key = "unit_backtest_s0_seed"
        auto_key = "unit_backtest_s0_auto"
        for key in (state_key, seed_key, auto_key):
            self.app.st.session_state.pop(key, None)
        self.app.st.session_state[state_key] = 0.0
        self.app.st.session_state[seed_key] = "same-structure"
        self.app.st.session_state[auto_key] = 800.0

        resolved = self.app.probexp_sync_auto_seeded_number_input(
            state_key=state_key,
            seed_key=seed_key,
            auto_value_key=auto_key,
            seed="same-structure",
            auto_value=800.0,
            min_value=0.0001,
            reset_min_value_to_auto=True,
        )

        self.assertAlmostEqual(resolved, 800.0, places=8)
        self.assertAlmostEqual(float(self.app.st.session_state[state_key]), 800.0, places=8)
        for key in (state_key, seed_key, auto_key):
            self.app.st.session_state.pop(key, None)

    def test_auto_seeded_price_input_preserves_manual_nonzero_value(self) -> None:
        state_key = "unit_backtest_s0_manual"
        seed_key = "unit_backtest_s0_manual_seed"
        auto_key = "unit_backtest_s0_manual_auto"
        for key in (state_key, seed_key, auto_key):
            self.app.st.session_state.pop(key, None)
        self.app.st.session_state[state_key] = 805.0
        self.app.st.session_state[seed_key] = "same-structure"
        self.app.st.session_state[auto_key] = 800.0

        resolved = self.app.probexp_sync_auto_seeded_number_input(
            state_key=state_key,
            seed_key=seed_key,
            auto_value_key=auto_key,
            seed="same-structure",
            auto_value=800.0,
            min_value=0.0001,
            reset_min_value_to_auto=True,
        )

        self.assertAlmostEqual(resolved, 805.0, places=8)
        self.assertAlmostEqual(float(self.app.st.session_state[state_key]), 805.0, places=8)
        for key in (state_key, seed_key, auto_key):
            self.app.st.session_state.pop(key, None)

    def test_monitor_report_iv_badge_keeps_terminated_rows_displayable(self) -> None:
        key = self.app.volval_bulk_model_iv_state_key("G1")
        self.app.st.session_state.pop(key, None)

        self.app.volval_store_model_iv_session_record("G1", "SID_TERM", 16.54, message="ok")

        rows = [
            {
                "structure_id": "SID_TERM",
                "is_active": False,
                "structure": "S007-Name-Risk",
                "structure_line1": "S007-Name-Risk",
                "structure_line2": "entry-strike",
                "structure_rich_lines": [[{"text": "S007-Name-Risk", "weight": "bold"}]],
            },
            {
                "structure_id": "SID_NO_IV",
                "is_active": True,
                "structure_line1": "S008-Name-Risk",
            },
        ]

        out = self.app.monitor_report_attach_model_iv_badges(rows, rep_gid="G1")

        self.assertTrue(str(out[0]["structure_line1"]).endswith(" | 16.5%"))
        self.assertIn("16.5%", "".join(str(seg.get("text", "")) for seg in out[0]["structure_rich_lines"][0]))
        self.assertEqual(str(out[1]["structure_line1"]), "S008-Name-Risk")

        self.app.st.session_state.pop(key, None)
        saved_rows = [
            {
                "structure_id": "SID_SAVED",
                "implied_vol_pct": 21.2,
                "structure_line1": "S009-Name-Risk",
                "structure": "S009-Name-Risk",
                "structure_rich_lines": [[{"text": "S009-Name-Risk", "weight": "bold"}]],
            }
        ]
        saved_out = self.app.monitor_report_attach_model_iv_badges(saved_rows, rep_gid="G1")
        self.assertTrue(str(saved_out[0]["structure_line1"]).endswith(" | 21.2%"))

    def test_monitor_report_iv_badge_can_target_vanilla_maturity_trs_only(self) -> None:
        rows = [
            {
                "structure_id": "SID_VMAT",
                "__vanilla_maturity_trs__": 1,
                "implied_vol_pct": 18.23,
                "strategy_code": "TRS",
                "structure": "S003-TRS",
                "structure_line1": "S003-TRS",
                "structure_rich_lines": [[{"text": "S003-TRS", "weight": "bold"}]],
            },
            {
                "structure_id": "SID_TRS",
                "implied_vol_pct": 19.9,
                "strategy_code": "TRS",
                "structure": "S004-TRS",
                "structure_line1": "S004-TRS",
                "structure_rich_lines": [[{"text": "S004-TRS", "weight": "bold"}]],
            },
        ]

        out = self.app.monitor_report_attach_model_iv_badges(
            rows,
            rep_gid="G1",
            only_vanilla_maturity_trs=True,
        )

        self.assertTrue(str(out[0]["structure_line1"]).endswith(" | 18.2%"))
        self.assertIn("18.2%", "".join(str(seg.get("text", "")) for seg in out[0]["structure_rich_lines"][0]))
        self.assertEqual(str(out[1]["structure_line1"]), "S004-TRS")
        self.assertNotIn("model_implied_iv_pct", out[1])

    def test_monitor_report_vanilla_maturity_trs_iv_fallback_uses_original_terms(self) -> None:
        iv_pct = self.app.monitor_report_infer_vanilla_maturity_trs_iv_pct(
            row={"__vanilla_maturity_trs__": 1},
            entry_price=773.5,
            strike_price=785.0,
            premium=9.2,
            option_type="call",
            side="sell",
            start_date="2026-04-16",
            end_date="2026-05-15",
            notional_qty=10000.0,
        )

        self.assertIsNotNone(iv_pct)
        self.assertAlmostEqual(float(iv_pct), 16.655650499676778, places=6)
        self.assertIsNone(
            self.app.monitor_report_infer_vanilla_maturity_trs_iv_pct(
                row={"strategy_code": "TRS"},
                entry_price=773.5,
                strike_price=785.0,
                premium=9.2,
                option_type="call",
                side="sell",
                start_date="2026-04-16",
                end_date="2026-05-15",
                notional_qty=10000.0,
            )
        )

    def test_model_iv_session_store_persists_to_structure_params_json(self) -> None:
        conn = sqlite3.connect(":memory:")
        try:
            self.app.init_db(conn)
            conn.execute(
                "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?, ?, ?)",
                ("G1", "Group 1", "I.DCE"),
            )
            conn.execute(
                """
                INSERT INTO structure(
                    structure_id, group_id, structure_code, name, underlying, risk_party,
                    kind, strategy, strategy_code, start_date, end_date, base_qty_per_day,
                    entry_price, strike_price, barrier_out, multiple, gen_price, params_json, meta_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SID_A",
                    "G1",
                    "S001",
                    "basic range",
                    "I2609",
                    "test",
                    "DEC",
                    "BASIC_RANGE",
                    "BASIC_RANGE",
                    "2026-05-04",
                    "2026-05-13",
                    100.0,
                    800.0,
                    800.0,
                    760.0,
                    3.0,
                    800.0,
                    json.dumps({"multiplier": 3.0}, ensure_ascii=False),
                    "{}",
                ),
            )
            conn.commit()

            key = self.app.volval_bulk_model_iv_state_key("G1")
            self.app.st.session_state.pop(key, None)
            ok = self.app.volval_store_model_iv_session_record(
                "G1",
                "SID_A",
                16.54,
                message="ok",
                conn=conn,
                group_id="G1",
            )

            self.assertTrue(ok)
            params_text = conn.execute("SELECT params_json FROM structure WHERE structure_id=?", ("SID_A",)).fetchone()[0]
            params = self.app.parse_json_obj(params_text, {})
            self.assertAlmostEqual(float(params["implied_vol_pct"]), 16.54, places=8)
            self.assertAlmostEqual(float(params["multiplier"]), 3.0, places=8)

            row = self.app.pd.read_sql_query("SELECT * FROM structure WHERE structure_id='SID_A'", conn).iloc[0]
            resolved = self.app.resolve_structure_row(row)
            self.assertAlmostEqual(float(resolved["implied_vol_pct"]), 16.54, places=8)
        finally:
            conn.close()

    def test_structure_option_sort_key_places_inactive_rows_last(self) -> None:
        rows = [
            {
                "display_id": "S002",
                "type_label": self.app.VOLVAL_STRUCTURE_TYPE_ACCUMULATOR,
                "underlying": "I2609",
                "start_date": "2026-04-01",
                "is_active": False,
            },
            {
                "display_id": "S003",
                "type_label": self.app.VOLVAL_STRUCTURE_TYPE_VANILLA,
                "underlying": "I2609",
                "start_date": "2026-04-01",
                "is_active": True,
            },
            {
                "display_id": "S001",
                "type_label": self.app.VOLVAL_STRUCTURE_TYPE_ACCUMULATOR,
                "underlying": "I2609",
                "start_date": "2026-04-01",
                "is_active": True,
            },
        ]

        ordered = sorted(rows, key=self.app.volval_structure_option_sort_key)

        self.assertTrue(bool(ordered[0]["is_active"]))
        self.assertTrue(bool(ordered[1]["is_active"]))
        self.assertFalse(bool(ordered[-1]["is_active"]))

    def test_self_quote_manual_underlying_defaults_to_unique_group_code(self) -> None:
        rows = [
            {"resolved": {"underlying": "I2609"}},
            {"resolved": {"underlying": "i2609"}},
        ]
        self.assertEqual(
            self.app.volval_self_quote_default_manual_underlying(
                rows,
                rep_und="ALL",
                rep_und_all=True,
            ),
            "I2609",
        )

        mixed_rows = [
            {"resolved": {"underlying": "I2609"}},
            {"resolved": {"underlying": "RB2605"}},
        ]
        self.assertEqual(
            self.app.volval_self_quote_default_manual_underlying(
                mixed_rows,
                rep_und="ALL",
                rep_und_all=True,
                fallback="RB2605",
            ),
            "RB2605",
        )
        self.assertEqual(
            self.app.volval_self_quote_default_manual_underlying(
                mixed_rows,
                rep_und="rb2605",
                rep_und_all=False,
            ),
            "RB2605",
        )

    def test_self_quote_reverse_options_cover_accumulator_modes(self) -> None:
        self.assertEqual(
            self.app.volval_self_quote_reverse_options("BASIC_RANGE"),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                self.app.VOLVAL_SELF_QUOTE_REV_MULTIPLE,
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )
        self.assertEqual(
            self.app.volval_self_quote_reverse_options("FLOAT_KO"),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )
        self.assertEqual(
            self.app.volval_self_quote_reverse_options("FIXED_SUBSIDY"),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY,
                self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY_SPREAD,
                self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )
        self.assertEqual(
            self.app.volval_self_quote_reverse_options("RANGE_SUBSIDY"),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY,
                self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )
        self.assertEqual(
            self.app.volval_self_quote_reverse_options("MELT_RANGE_SUBSIDY"),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_SUBSIDY,
                self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )

    def test_self_quote_range_subsidy_manual_fields_use_business_labels(self) -> None:
        self.assertEqual(self.app.volval_self_quote_supported_code("RANGE_SUBSIDY"), "RANGE_SUBSIDY")
        self.assertEqual(self.app.volval_self_quote_manual_type_label_for_code("RANGE_SUBSIDY"), "区间补贴累计")
        self.assertEqual(self.app.volval_self_quote_field_label("RANGE_SUBSIDY", "subsidy_per_ton"), "区间补贴")
        self.assertEqual(self.app.volval_self_quote_field_label("RANGE_SUBSIDY", "strike_price"), "行权价")
        self.assertEqual(self.app.volval_self_quote_field_label("RANGE_SUBSIDY", "barrier_price"), "敲出价")
        self.assertEqual(
            self.app.volval_self_quote_reverse_variable_label(
                "RANGE_SUBSIDY",
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
            ),
            "对称区间",
        )
        self.assertIn("subsidy_per_ton", self.app.volval_self_quote_multi_value_fields_for_code("RANGE_SUBSIDY"))

    def test_self_quote_melt_range_subsidy_manual_fields_use_business_labels(self) -> None:
        self.assertEqual(self.app.volval_self_quote_supported_code("MELT_RANGE_SUBSIDY"), "MELT_RANGE_SUBSIDY")
        self.assertEqual(self.app.volval_self_quote_manual_type_label_for_code("MELT_RANGE_SUBSIDY"), "熔断区间补贴累计")
        self.assertEqual(self.app.volval_self_quote_field_label("MELT_RANGE_SUBSIDY", "subsidy_per_ton"), "区间补贴")
        self.assertEqual(self.app.volval_self_quote_field_label("MELT_RANGE_SUBSIDY", "strike_price"), "行权价")
        self.assertEqual(self.app.volval_self_quote_field_label("MELT_RANGE_SUBSIDY", "barrier_price"), "熔断价")
        self.assertEqual(
            self.app.volval_self_quote_reverse_variable_label(
                "MELT_RANGE_SUBSIDY",
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
            ),
            "对称区间",
        )
        self.assertIn("subsidy_per_ton", self.app.volval_self_quote_multi_value_fields_for_code("MELT_RANGE_SUBSIDY"))

    def test_self_quote_range_subsidy_symmetric_reverse_applies_strike_and_ko(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("RANGE_SUBSIDY", start_date_v="2026-05-12")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update({"spot_price": 800.0, "kind": "ACC"})

        out = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=25.0,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
        )

        self.assertEqual(out["strike_price"], 775.0)
        self.assertEqual(out["barrier_out"], 825.0)

    def test_self_quote_supports_airbag_and_vanilla_modes(self) -> None:
        self.assertEqual(self.app.volval_self_quote_supported_code("SAFETY_AIRBAG"), "SAFETY_AIRBAG")
        self.assertEqual(self.app.volval_self_quote_supported_code(self.app.VANILLA_OPTION_CODE), self.app.VANILLA_OPTION_CODE)
        self.assertEqual(
            self.app.volval_self_quote_reverse_options("SAFETY_AIRBAG"),
            (
                self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
                self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                self.app.VOLVAL_SELF_QUOTE_REV_IV,
            ),
        )

    def test_self_quote_mode_and_source_options_prefer_quote_flow(self) -> None:
        self.assertEqual(
            self.app.VOLVAL_SELF_QUOTE_MODE_OPTIONS,
            (self.app.VOLVAL_SELF_QUOTE_MODE_QUOTE, self.app.VOLVAL_SELF_QUOTE_MODE_MODEL),
        )
        self.assertEqual(
            self.app.VOLVAL_SELF_QUOTE_SOURCE_OPTIONS,
            (self.app.VOLVAL_SELF_QUOTE_SOURCE_MANUAL, self.app.VOLVAL_SELF_QUOTE_SOURCE_EXISTING),
        )

    def test_self_quote_manual_airbag_defaults_to_put_and_twenty_iv(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("SAFETY_AIRBAG", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)

        self.assertEqual(resolved["kind"], "DEC")
        self.assertEqual(scenario["kind"], "DEC")
        self.assertEqual(float(resolved["implied_vol_pct"]), 20.0)
        self.assertEqual(float(scenario["iv_pct"]), 20.0)

    def test_self_quote_quantity_defaults_match_structure_entry_scale(self) -> None:
        acc_resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-04")
        acc_scenario = self.app.volval_self_quote_base_scenario(acc_resolved)
        self.assertAlmostEqual(float(acc_scenario["base_qty_per_day"]), 1000.0)

        vanilla_resolved = self.app.volval_self_quote_manual_resolved(self.app.VANILLA_OPTION_CODE, start_date_v="2026-05-04")
        vanilla_scenario = self.app.volval_self_quote_base_scenario(vanilla_resolved)
        self.assertAlmostEqual(float(vanilla_scenario["notional_qty"]), 10000.0)

        airbag_resolved = self.app.volval_self_quote_manual_resolved("SAFETY_AIRBAG", start_date_v="2026-05-04")
        airbag_scenario = self.app.volval_self_quote_base_scenario(airbag_resolved)
        self.assertAlmostEqual(float(airbag_scenario["airbag_total_qty"]), 10000.0)
        priced_airbag = self.app.volval_self_quote_apply_scenario(airbag_resolved, airbag_scenario)
        expected_airbag_base = self.app.structure_storage_base_qty(
            "SAFETY_AIRBAG",
            10000.0,
            priced_airbag["start_date"],
            priced_airbag["end_date"],
        )
        self.assertAlmostEqual(float(priced_airbag["base_qty_per_day"]), float(expected_airbag_base))
        self.assertAlmostEqual(float(priced_airbag["total_qty"]), 10000.0)

        snowball_resolved = self.app.volval_self_quote_manual_resolved("SNOWBALL", start_date_v="2026-05-04")
        snowball_scenario = self.app.volval_self_quote_base_scenario(snowball_resolved)
        self.assertAlmostEqual(float(snowball_scenario["snowball_notional_wan"]), 1000.0)
        expected_scale = self.app.snowball_scale_qty_from_notional(1000.0 * 10000.0, snowball_scenario["spot_price"])
        self.assertAlmostEqual(float(snowball_scenario["snowball_scale_qty"]), float(expected_scale))
        priced_snowball = self.app.volval_self_quote_apply_scenario(snowball_resolved, snowball_scenario)
        self.assertAlmostEqual(float(priced_snowball["params"]["sb_scale_qty"]), float(expected_scale))

    def test_self_quote_missing_saved_iv_defaults_to_twenty(self) -> None:
        scenario = self.app.volval_self_quote_base_scenario(
            {
                "strategy_code": "BASIC_RANGE",
                "kind": "DEC",
                "entry_price": 800.0,
                "strike_price": 800.0,
                "barrier_out": 760.0,
                "params": {},
            }
        )

        self.assertEqual(float(scenario["iv_pct"]), 20.0)

    def test_self_quote_manual_iv_and_term_preserved_on_overwrite(self) -> None:
        iv_key = "volval_self_quote_unit__plan1__iv_pct"
        term_key = "volval_self_quote_unit__plan1__term_trading_days"
        strike_key = "volval_self_quote_unit__plan1__strike_price"
        state = {
            iv_key: "16",
            self.app.volval_self_quote_manual_preserve_key(iv_key): True,
            term_key: "45",
            self.app.volval_self_quote_manual_preserve_key(term_key): True,
            strike_key: "790",
        }

        self.assertEqual(
            self.app.volval_self_quote_preserve_manual_input_value(
                "iv_pct",
                iv_key,
                state,
                "20",
                overwrite=True,
            ),
            "16",
        )
        self.assertEqual(
            self.app.volval_self_quote_preserve_manual_input_value(
                "term_trading_days",
                term_key,
                state,
                "15",
                overwrite=True,
            ),
            "45",
        )
        self.assertEqual(
            self.app.volval_self_quote_preserve_manual_input_value(
                "strike_price",
                strike_key,
                state,
                "800",
                overwrite=True,
            ),
            "800",
        )
        self.assertEqual(
            self.app.volval_self_quote_preserve_manual_input_value(
                "iv_pct",
                iv_key,
                state,
                "20",
                overwrite=False,
            ),
            "20",
        )

    def test_self_quote_number_list_accepts_comma_batches(self) -> None:
        values, err = self.app.volval_self_quote_parse_number_list("20,25，30BD", integer=True)

        self.assertEqual(err, "")
        self.assertEqual(values, [20.0, 25.0, 30.0])

        values, err = self.app.volval_self_quote_parse_number_list("20 25 30", integer=True)
        self.assertEqual(err, "")
        self.assertEqual(values, [20.0, 25.0, 30.0])

        values, err = self.app.volval_self_quote_parse_number_list(
            "1,2,3",
            integer=True,
            min_value=1.0,
            max_value=None,
        )
        self.assertEqual(err, "")
        self.assertEqual(values, [1.0, 2.0, 3.0])

        values, err = self.app.volval_self_quote_parse_number_list(
            "1,4",
            integer=True,
            min_value=1.0,
            max_value=None,
        )
        self.assertEqual(err, "")
        self.assertEqual(values, [1.0, 4.0])

    def test_self_quote_price_fields_accept_relative_entry_offsets(self) -> None:
        spec = {"integer": False, "min_value": 0.0001, "max_value": None, "digits": 2}

        values, err, had_relative = self.app.volval_self_quote_parse_number_list_for_field(
            "+5",
            field="strike_price",
            entry_price=800.0,
            **spec,
        )

        self.assertEqual(err, "")
        self.assertTrue(had_relative)
        self.assertEqual(values, [805.0])

        values, err, had_relative = self.app.volval_self_quote_parse_number_list_for_field(
            "-5",
            field="barrier_price",
            entry_price=800.0,
            **spec,
        )
        self.assertEqual(err, "")
        self.assertTrue(had_relative)
        self.assertEqual(values, [795.0])

        values, err, had_relative = self.app.volval_self_quote_parse_number_list_for_field(
            "+5, -5",
            field="ko_strike_price",
            entry_price=800.0,
            **spec,
        )
        self.assertEqual(err, "")
        self.assertTrue(had_relative)
        self.assertEqual(values, [805.0, 795.0])

    def test_self_quote_non_price_fields_keep_signed_numeric_meaning(self) -> None:
        values, err, had_relative = self.app.volval_self_quote_parse_number_list_for_field(
            "+5",
            field="subsidy_per_ton",
            entry_price=800.0,
            integer=False,
            min_value=0.0,
            max_value=None,
            digits=2,
        )

        self.assertEqual(err, "")
        self.assertFalse(had_relative)
        self.assertEqual(values, [5.0])

    def test_self_quote_variant_labels_describe_single_changed_factor(self) -> None:
        self.assertEqual(
            self.app.volval_self_quote_variant_label("BASIC_RANGE", "term_trading_days", 30),
            "期限 30BD",
        )
        self.assertEqual(
            self.app.volval_self_quote_variant_label("BASIC_RANGE", "iv_pct", 18),
            "波动率 18%",
        )
        self.assertEqual(
            self.app.volval_self_quote_variant_label("FLOAT_KO", "strike_price", 800),
            "未敲出行权价 800",
        )
        self.assertEqual(
            self.app.volval_self_quote_variant_label("SNOWBALL", "snowball_early_mode", True),
            "早利模式 是",
        )
        self.assertEqual(
            self.app.volval_self_quote_variant_label("SNOWBALL", "snowball_early_a", 4.0),
            "A阶段观察次数 4",
        )
        self.assertEqual(
            self.app.volval_self_quote_variant_label("SNOWBALL", "snowball_early_b", 4.0),
            "B阶段观察次数 4",
        )
        self.assertNotIn(
            "snowball_",
            " | ".join(
                [
                    self.app.volval_self_quote_variant_label("SNOWBALL", "snowball_early_mode", True),
                    self.app.volval_self_quote_variant_label("SNOWBALL", "snowball_early_a", 4.0),
                    self.app.volval_self_quote_variant_label("SNOWBALL", "snowball_early_b", 4.0),
                ]
            ),
        )

    def test_self_quote_accumulator_multiple_defaults_to_three_and_accepts_above_three(self) -> None:
        self.assertEqual(self.app.VOLVAL_SELF_QUOTE_ACCUMULATOR_MULTIPLE_OPTIONS, (1, 2, 3))
        resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)

        self.assertEqual(float(resolved["multiple"]), 3.0)
        self.assertEqual(float(scenario["multiple"]), 3.0)
        self.assertEqual(float(scenario["iv_pct"]), 20.0)
        for multiple in (1.0, 2.0, 3.0, 4.0, 8.0):
            with self.subTest(multiple=multiple):
                self.assertEqual(self.app.volval_self_quote_accumulator_multiple_value(multiple), int(multiple))
        self.assertEqual(self.app.volval_self_quote_accumulator_multiple_value(2.5), 3)
        for code in self.app.VOLVAL_SELF_QUOTE_ACCUMULATOR_CODES:
            with self.subTest(code=code):
                resolved = self.app.volval_self_quote_manual_resolved(code, start_date_v="2026-05-04")
                resolved["multiple"] = 4.0
                scenario = self.app.volval_self_quote_base_scenario(resolved)
                self.assertEqual(float(scenario["multiple"]), 4.0)

    def test_float_ko_self_quote_ko_strike_links_to_entry_until_manual_override(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("FLOAT_KO", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)

        self.assertAlmostEqual(float(scenario["spot_price"]), 800.0)
        self.assertAlmostEqual(float(scenario["ko_strike_price"]), 800.0)

        linked = self.app.volval_self_quote_float_ko_link_state(
            820.0,
            800.0,
            previous_auto_value=800.0,
            manual_override=False,
        )
        self.assertFalse(bool(linked["manual_override"]))
        self.assertAlmostEqual(float(linked["value"]), 820.0)
        self.assertAlmostEqual(float(linked["auto_value"]), 820.0)

        manual = self.app.volval_self_quote_float_ko_link_state(
            820.0,
            815.0,
            previous_auto_value=800.0,
            manual_override=False,
        )
        self.assertTrue(bool(manual["manual_override"]))
        self.assertAlmostEqual(float(manual["value"]), 815.0)

        preserved = self.app.volval_self_quote_float_ko_link_state(
            830.0,
            815.0,
            previous_auto_value=800.0,
            manual_override=True,
        )
        self.assertTrue(bool(preserved["manual_override"]))
        self.assertAlmostEqual(float(preserved["value"]), 815.0)

        relinked = self.app.volval_self_quote_float_ko_link_state(
            830.0,
            830.0,
            previous_auto_value=800.0,
            manual_override=True,
        )
        self.assertFalse(bool(relinked["manual_override"]))
        self.assertAlmostEqual(float(relinked["value"]), 830.0)

    def test_float_ko_batch_spot_keeps_auto_ko_strike_link(self) -> None:
        linked = self.app.volval_self_quote_sync_float_ko_spot_link(
            {"spot_price": 820.0, "ko_strike_price": 800.0},
            previous_spot=800.0,
        )
        self.assertAlmostEqual(float(linked["ko_strike_price"]), 820.0)

        manual = self.app.volval_self_quote_sync_float_ko_spot_link(
            {"spot_price": 820.0, "ko_strike_price": 810.0},
            previous_spot=800.0,
        )
        self.assertAlmostEqual(float(manual["ko_strike_price"]), 810.0)

    def test_self_quote_result_signature_rejects_stale_payloads(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        sig1 = self.app.volval_self_quote_scenario_signature(
            code="BASIC_RANGE",
            selected_sid="MANUAL_BASIC_RANGE",
            record_key="方案1",
            scenario=scenario,
            resolved=resolved,
        )
        scenario2 = dict(scenario)
        scenario2["iv_pct"] = 25.0
        sig2 = self.app.volval_self_quote_scenario_signature(
            code="BASIC_RANGE",
            selected_sid="MANUAL_BASIC_RANGE",
            record_key="方案1",
            scenario=scenario2,
            resolved=resolved,
        )
        self.assertNotEqual(sig1, sig2)

        packed = self.app.volval_self_quote_pack_result({"ok": True, "solution_value": 800.0}, sig1)
        self.assertEqual(
            self.app.volval_self_quote_unpack_result(packed, sig1)["solution_value"],
            800.0,
        )
        self.assertIsNone(self.app.volval_self_quote_unpack_result(packed, sig2))
        self.assertIsNone(self.app.volval_self_quote_unpack_result({"ok": True}, sig1))

    def test_self_quote_symmetric_variable_sets_acc_and_dec_ranges(self) -> None:
        acc_resolved = {
            "strategy_code": "BASIC_RANGE",
            "kind": "ACC",
            "entry_price": 800.0,
            "strike_price": 790.0,
            "barrier_out": 830.0,
            "knock_out_price": 830.0,
            "multiple": 2.0,
            "params": {},
            "meta": {},
        }
        scenario = {"spot_price": 800.0, "reverse_variable": "对称区间(行权价格&障碍价格)"}
        acc_out = self.app.volval_self_quote_apply_scenario(
            acc_resolved,
            scenario,
            variable_value=25.0,
            reverse_variable="对称区间(行权价格&障碍价格)",
        )
        self.assertAlmostEqual(float(acc_out["strike_price"]), 775.0)
        self.assertAlmostEqual(float(acc_out["barrier_out"]), 825.0)

        dec_out = self.app.volval_self_quote_apply_scenario(
            {**acc_resolved, "kind": "DEC"},
            scenario,
            variable_value=25.0,
            reverse_variable="对称区间(行权价格&障碍价格)",
        )
        self.assertAlmostEqual(float(dec_out["strike_price"]), 825.0)
        self.assertAlmostEqual(float(dec_out["barrier_out"]), 775.0)

    def test_self_quote_term_days_can_drive_end_date(self) -> None:
        self.assertEqual(self.app.volval_self_quote_term_days("2026-04-01", "2026-05-15"), 29)
        end_d = self.app.volval_self_quote_end_date_from_term("2026-04-01", 29)
        self.assertEqual(end_d.isoformat(), "2026-05-15")

    def test_self_quote_vanilla_calculates_premium_per_ton(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved(self.app.VANILLA_OPTION_CODE, start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "spot_price": 800.0,
                "strike_price": 800.0,
                "iv_pct": 20.0,
                "option_type": "call",
                "start_date": "2026-05-04",
                "end_date": "2026-05-13",
                "term_trading_days": 8,
            }
        )

        result = self.app.volval_self_quote_calculate_vanilla_premium(scenario)

        self.assertTrue(result["ok"], result.get("message"))
        self.assertGreater(float(result["premium_per_ton"]), 0.0)

    def test_self_quote_airbag_apply_scenario_updates_barrier_and_participation(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("SAFETY_AIRBAG", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update({"spot_price": 800.0, "barrier_price": 720.0, "multiple": 80.0, "kind": "ACC"})

        out = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=95.0,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
        )

        self.assertAlmostEqual(float(out["entry_price"]), 800.0)
        self.assertAlmostEqual(float(out["strike_price"]), 800.0)
        self.assertAlmostEqual(float(out["barrier_out"]), 720.0)
        self.assertAlmostEqual(float(out["multiple"]), 95.0)

    def test_self_quote_directional_price_bounds_cover_supported_reverse_prices(self) -> None:
        spot = 800.0
        for code in ("BASIC_RANGE", "FLOAT_KO", "FIXED_SUBSIDY"):
            for kind in ("ACC", "DEC"):
                resolved = {"strategy_code": code, "kind": kind, "entry_price": spot}
                scenario = {"spot_price": spot, "kind": kind, "strike_price": spot, "barrier_price": spot}
                strike_low, strike_high, _ = self.app.volval_self_quote_variable_bounds(
                    resolved,
                    scenario,
                    self.app.VOLVAL_SELF_QUOTE_REV_STRIKE,
                )
                barrier_low, barrier_high, _ = self.app.volval_self_quote_variable_bounds(
                    resolved,
                    scenario,
                    self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                )
                if kind == "ACC":
                    self.assertLessEqual(strike_high, spot)
                    self.assertGreaterEqual(barrier_low, spot)
                else:
                    self.assertGreaterEqual(strike_low, spot)
                    self.assertLessEqual(barrier_high, spot)

        for kind in ("ACC", "DEC"):
            resolved = {"strategy_code": "SAFETY_AIRBAG", "kind": kind, "entry_price": spot}
            scenario = {"spot_price": spot, "kind": kind, "barrier_price": spot}
            barrier_low, barrier_high, _ = self.app.volval_self_quote_variable_bounds(
                resolved,
                scenario,
                self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
            )
            if kind == "ACC":
                self.assertLess(barrier_high, spot)
            else:
                self.assertGreater(barrier_low, spot)

    def test_self_quote_rejects_directionally_invalid_fixed_prices(self) -> None:
        airbag = self.app.volval_self_quote_manual_resolved("SAFETY_AIRBAG", start_date_v="2026-05-04")
        airbag_scenario = self.app.volval_self_quote_base_scenario(airbag)
        airbag_scenario.update({"kind": "DEC", "spot_price": 800.0, "barrier_price": 720.0, "iv_pct": 20.0})
        airbag_result = self.app.volval_self_quote_solve_reverse_variable(
            airbag,
            airbag_scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
        )
        self.assertFalse(airbag_result["ok"])
        self.assertIn("障碍价格", airbag_result["message"])

        accumulator = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-04")
        accumulator_scenario = self.app.volval_self_quote_base_scenario(accumulator)
        accumulator_scenario.update(
            {
                "kind": "DEC",
                "spot_price": 800.0,
                "strike_price": 820.0,
                "barrier_price": 840.0,
                "iv_pct": 20.0,
            }
        )
        accumulator_result = self.app.volval_self_quote_solve_reverse_variable(
            accumulator,
            accumulator_scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_MULTIPLE,
        )
        self.assertFalse(accumulator_result["ok"])
        self.assertIn("障碍价格", accumulator_result["message"])

    def test_self_quote_price_result_format_appends_entry_delta(self) -> None:
        self.assertEqual(
            self.app.volval_self_quote_format_price_with_entry_delta(108.0, 105.0),
            "108.00\uff08+3\uff09",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_price_with_entry_delta(107.72, 105.0),
            "107.72\uff08+2.72\uff09",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_price_with_entry_delta(102.28, 105.0),
            "102.28\uff08-2.72\uff09",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_price_with_entry_delta(
                108.0,
                105.0,
                include_entry_ratio=True,
            ),
            "108.00\uff08+3,102.86%\uff09",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_price_with_entry_delta(
                102.28,
                105.0,
                include_entry_ratio=True,
            ),
            "102.28\uff08-2.72,97.41%\uff09",
        )

    def test_self_quote_result_delta_formats_by_reverse_variable(self) -> None:
        self.assertEqual(
            self.app.volval_self_quote_format_result_delta(
                self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
                26.06,
                None,
            ),
            "0",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_result_delta(
                self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
                44.64,
                26.06,
            ),
            "18.58%",
        )
        self.assertEqual(
            self.app.volval_self_quote_format_result_delta(
                self.app.VOLVAL_SELF_QUOTE_REV_SYMMETRIC,
                40.0,
                30.0,
            ),
            "10.00",
        )

    def test_self_quote_reverse_result_value_ignores_failed_rows(self) -> None:
        failed = {
            "ok": False,
            "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
            "solution_value": 80.0,
        }
        ok = {
            "ok": True,
            "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
            "solution_value": 88.0,
        }

        self.assertIsNone(
            self.app.volval_self_quote_reverse_result_value(
                self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
                failed,
            )
        )
        self.assertEqual(
            self.app.volval_self_quote_format_result_delta(
                self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
                self.app.volval_self_quote_reverse_result_value(
                    self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
                    ok,
                ),
                None,
            ),
            "0",
        )

    def test_self_quote_result_table_hides_zero_optional_value_columns(self) -> None:
        rows = [
            {
                "方案": "方案1-1",
                "反解结果": "26.06%",
                "结果价差": "0",
                "估值/吨": "0.00",
                "差额/吨": "-0.00",
                self.app.VOLVAL_SELF_QUOTE_RESULT_UNIT_VALUE_META_COL: 0.0,
                self.app.VOLVAL_SELF_QUOTE_RESULT_UNIT_DIFF_META_COL: -0.0,
            }
        ]

        hidden_df = self.app.volval_self_quote_result_table_frame(rows)
        self.assertNotIn("估值/吨", hidden_df.columns)
        self.assertNotIn("差额/吨", hidden_df.columns)
        self.assertNotIn(self.app.VOLVAL_SELF_QUOTE_RESULT_UNIT_VALUE_META_COL, hidden_df.columns)

        rows[0][self.app.VOLVAL_SELF_QUOTE_RESULT_UNIT_VALUE_META_COL] = 1.25
        rows[0]["估值/吨"] = "1.25"
        visible_df = self.app.volval_self_quote_result_table_frame(rows)
        self.assertIn("估值/吨", visible_df.columns)
        self.assertNotIn("差额/吨", visible_df.columns)

        rows.append(
            {
                "方案": "方案1-2",
                "反解结果": "44.64%",
                "结果价差": "18.58%",
                "估值/吨": "0.00",
                "差额/吨": "-0.75",
                self.app.VOLVAL_SELF_QUOTE_RESULT_UNIT_VALUE_META_COL: 0.0,
                self.app.VOLVAL_SELF_QUOTE_RESULT_UNIT_DIFF_META_COL: -0.75,
            }
        )
        visible_df = self.app.volval_self_quote_result_table_frame(rows)
        self.assertIn("估值/吨", visible_df.columns)
        self.assertIn("差额/吨", visible_df.columns)

    def test_self_quote_airbag_reverse_participation_and_barrier_recover_grid_targets(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("SAFETY_AIRBAG", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "kind": "ACC",
                "spot_price": 800.0,
                "barrier_price": 720.0,
                "multiple": 80.0,
                "iv_pct": 20.0,
                "start_date": "2026-05-04",
                "end_date": "2026-05-13",
                "term_trading_days": 8,
                "paths": 1000,
                "seed": 123,
            }
        )

        def target_unit(reverse_variable: str, value: float) -> float:
            target_resolved = self.app.volval_self_quote_apply_scenario(
                resolved,
                scenario,
                variable_value=value,
                reverse_variable=reverse_variable,
            )
            template = self.app.volval_template_with_dates(
                self.app.winrate_prepare_structure_template(target_resolved),
                start_date_v="2026-05-04",
                end_date_v="2026-05-13",
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
            valuation = self.app.winrate_structure_model_value_for_iv(
                template,
                start_price=800.0,
                atm_iv_pct=20.0,
                paths=1000,
                trading_days_per_year=252,
                seed=123,
                seed_hint=f"airbag-self-quote-target-{reverse_variable}",
                valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
                risk_free_rate_pct=2.0,
                carry_yield_pct=0.0,
                futures_mode=True,
            )
            scale_qty = max(float(valuation["initial_scale_qty"]), 1e-12)
            return float(valuation["value"]) / scale_qty

        participation_target = target_unit(self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION, 80.0)
        participation_solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_PARTICIPATION,
            target_unit_value=participation_target,
        )
        self.assertTrue(participation_solved["ok"], participation_solved.get("message"))
        self.assertAlmostEqual(float(participation_solved["solution_value"]), 80.0, places=8)

        barrier_target = target_unit(self.app.VOLVAL_SELF_QUOTE_REV_BARRIER, 720.0)
        barrier_solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
            target_unit_value=barrier_target,
        )
        self.assertTrue(barrier_solved["ok"], barrier_solved.get("message"))
        self.assertAlmostEqual(float(barrier_solved["solution_value"]), 720.0, places=8)

    def test_self_quote_reverse_strike_recovers_grid_target(self) -> None:
        resolved = {
            "structure_id": "ACC-Q",
            "strategy_code": "BASIC_RANGE",
            "kind": "DEC",
            "start_date": "2026-05-04",
            "end_date": "2026-05-13",
            "base_qty_per_day": 100.0,
            "entry_price": 800.0,
            "strike_price": 800.0,
            "barrier_out": 760.0,
            "knock_out_price": 760.0,
            "multiple": 2.0,
            "params": {"n_days": 8},
            "meta": {"n_days": 8},
        }
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "strike_price": 800.0,
                "iv_pct": 20.0,
                "paths": 1000,
                "seed": 123,
                "reverse_variable": "行权价格",
            }
        )
        target_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=800.0,
            reverse_variable="行权价格",
        )
        template = self.app.volval_template_with_dates(
            self.app.winrate_prepare_structure_template(target_resolved),
            start_date_v="2026-05-04",
            end_date_v="2026-05-13",
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
        )
        target_value = self.app.winrate_structure_model_value_for_iv(
            template,
            start_price=800.0,
            atm_iv_pct=20.0,
            paths=1000,
            trading_days_per_year=252,
            seed=123,
            seed_hint="self-quote-target",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=2.0,
            carry_yield_pct=0.0,
            futures_mode=True,
        )
        scale_qty = max(float(target_value["initial_scale_qty"]), 1e-12)
        target_unit = float(target_value["value"]) / scale_qty

        solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable="行权价格",
            target_unit_value=target_unit,
        )

        self.assertTrue(solved["ok"], solved.get("message"))
        self.assertAlmostEqual(float(solved["solution_value"]), 800.0, places=8)

    def test_self_quote_fixed_subsidy_barrier_reverse_rejects_boundary_discontinuity(self) -> None:
        resolved = {
            "structure_id": "FIXED-Q",
            "strategy_code": "FIXED_SUBSIDY",
            "kind": "DEC",
            "start_date": "2026-05-14",
            "end_date": "2026-06-10",
            "base_qty_per_day": 100.0,
            "entry_price": 800.0,
            "strike_price": 810.0,
            "barrier_out": 760.0,
            "knock_out_price": 760.0,
            "multiple": 3.0,
            "subsidy_per_ton": 2.0,
            "params": {"n_days": 20, "multiplier": 3.0, "subsidy_per_ton": 2.0},
            "meta": {"n_days": 20},
        }
        base_scenario = self.app.volval_self_quote_base_scenario(resolved)

        for subsidy in (1.0, 2.0, 3.0, 4.0):
            with self.subTest(subsidy=subsidy):
                scenario = dict(base_scenario)
                scenario.update(
                    {
                        "spot_price": 800.0,
                        "strike_price": 810.0,
                        "barrier_price": 760.0,
                        "subsidy_per_ton": subsidy,
                        "multiple": 3.0,
                        "iv_pct": 20.0,
                        "risk_free_rate_pct": 2.0,
                        "futures_mode": True,
                        "paths": 1000,
                        "seed": 123,
                        "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                    }
                )

                solved = self.app.volval_self_quote_solve_reverse_variable(
                    resolved,
                    scenario,
                    reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_BARRIER,
                    target_unit_value=0.0,
                    max_iter=12,
                )

                self.assertFalse(solved["ok"], solved.get("message"))
                self.assertIsNone(solved.get("solution_value"))
                self.assertIn("未达到目标估值", solved.get("message", ""))
                self.assertGreater(abs(float(solved.get("nearest_unit_diff", 0.0))), 0.02)

    def test_self_quote_reverse_iv_reuses_model_implied_solver(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "kind": "DEC",
                "strike_price": 800.0,
                "barrier_price": 760.0,
                "paths": 1000,
                "seed": 123,
                "risk_free_rate_pct": 2.0,
                "futures_mode": True,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_IV,
            }
        )
        target_iv = 25.0
        target_resolved = self.app.volval_self_quote_apply_scenario(resolved, scenario)
        template = self.app.volval_template_with_dates(
            self.app.winrate_prepare_structure_template(target_resolved),
            start_date_v=scenario["start_date"],
            end_date_v=scenario["end_date"],
            day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
        )
        target_value = self.app.winrate_structure_model_value_for_iv(
            template,
            start_price=float(scenario["spot_price"]),
            atm_iv_pct=target_iv,
            paths=1000,
            trading_days_per_year=252,
            seed=123,
            seed_hint="self-quote-iv-target",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=2.0,
            carry_yield_pct=0.0,
            futures_mode=True,
        )
        scale_qty = max(float(target_value["initial_scale_qty"]), 1e-12)
        target_unit = float(target_value["value"]) / scale_qty

        solved = self.app.volval_self_quote_solve_reverse_variable(
            resolved,
            scenario,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_IV,
            target_unit_value=target_unit,
        )

        self.assertTrue(solved["ok"], solved.get("message"))
        self.assertAlmostEqual(float(solved["solution_value"]), target_iv, places=8)
        self.assertAlmostEqual(float(solved["implied_vol_pct"]), target_iv, places=8)
        self.assertAlmostEqual(float(solved["unit_diff"]), 0.0, places=6)
        self.assertAlmostEqual(float(solved["resolved_for_result"]["implied_vol_pct"]), target_iv, places=8)

    def test_self_quote_analysis_record_uses_result_price_and_iv(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "spot_price": 812.0,
                "strike_price": 790.0,
                "barrier_price": 850.0,
                "iv_pct": 18.0,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_IV,
            }
        )
        result_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=26.5,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_IV,
        )
        record = self.app.volval_self_quote_analysis_record(
            resolved,
            scenario,
            {
                "ok": True,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_IV,
                "solution_value": 26.5,
                "implied_vol_pct": 26.5,
                "resolved_for_result": result_resolved,
            },
            record_key="方案1",
            base_id="方案1",
            display_id="方案1",
            variant_text="--",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertAlmostEqual(float(record["center_price"]), 812.0)
        self.assertAlmostEqual(float(record["entry_price"]), 812.0)
        self.assertAlmostEqual(float(record["atm_iv_default"]), 26.5)
        template_resolved = record["template"]["resolved"]
        self.assertAlmostEqual(float(template_resolved["entry_price"]), 812.0)
        self.assertAlmostEqual(float(template_resolved["implied_vol_pct"]), 26.5)

    def test_self_quote_result_bridge_uses_lazy_module_selector(self) -> None:
        options = self.app.VOLVAL_SELF_QUOTE_RESULT_BRIDGE_MODULES

        self.assertEqual(options[0], "报价图片输出")
        self.assertIn("累计结构精准套保", options)
        self.assertEqual(
            self.app.volval_self_quote_normalize_result_bridge_module("累计结构精准套保"),
            "累计结构精准套保",
        )
        self.assertEqual(
            self.app.volval_self_quote_normalize_result_bridge_module(""),
            "报价图片输出",
        )

        source = inspect.getsource(self.app.render_volval_self_quote_result_bridge_tabs)
        self.assertIn("st.radio", source)
        self.assertNotIn("st.tabs", source)

    def test_self_quote_probexp_bridge_snapshot_keeps_temp_remaining_days(self) -> None:
        resolved = self.app.volval_self_quote_manual_resolved("BASIC_RANGE", start_date_v="2026-05-04")
        scenario = self.app.volval_self_quote_base_scenario(resolved)
        scenario.update(
            {
                "spot_price": 812.0,
                "strike_price": 790.0,
                "barrier_price": 850.0,
                "iv_pct": 18.0,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_IV,
            }
        )
        result_resolved = self.app.volval_self_quote_apply_scenario(
            resolved,
            scenario,
            variable_value=18.0,
            reverse_variable=self.app.VOLVAL_SELF_QUOTE_REV_IV,
        )
        record = self.app.volval_self_quote_analysis_record(
            resolved,
            scenario,
            {
                "ok": True,
                "reverse_variable": self.app.VOLVAL_SELF_QUOTE_REV_IV,
                "solution_value": 18.0,
                "implied_vol_pct": 18.0,
                "resolved_for_result": result_resolved,
            },
            record_key="case1",
            base_id="case1",
            display_id="case1",
            variant_text="--",
        )

        self.assertIsNotNone(record)
        bridge_payload = self.app.volval_self_quote_build_backtest_bridge_payload(
            prefix="unit_self_quote_probexp",
            analysis_records=[record],
        )
        candidate = bridge_payload["candidate_rows"][0]
        self.assertIsNone(candidate.get("raw_row"))
        self.assertGreater(int(candidate.get("remaining_days", 0)), 0)

        snapshot = self.app.probexp_build_structure_snapshot(
            candidate=candidate,
            struct_asof=pd.DataFrame(),
            prices_df=pd.DataFrame(columns=["dt", "underlying", "settle"]),
            close2_df=pd.DataFrame(),
            rep_date=bridge_payload["rep_date"],
        )

        self.assertEqual(int(snapshot["remaining_days"]), int(candidate["remaining_days"]))
        self.assertEqual(
            int(snapshot["gap_snapshot"]["remaining_observe_days"]),
            int(candidate["remaining_days"]),
        )

    def test_greeks_unit_snapshot_scales_total_curves_to_per_ton(self) -> None:
        snapshot = self.app.winrate_structure_greeks_unit_snapshot(
            {
                "s_grid": np.asarray([90.0, 100.0, 110.0]),
                "price": np.asarray([900.0, 1000.0, 1300.0]),
                "unit_price": np.asarray([0.9, 1.0, 1.3]),
                "delta": np.asarray([100.0, 300.0, 500.0]),
                "gamma": np.asarray([10.0, 20.0, 30.0]),
                "vega": np.asarray([4000.0, 5000.0, 6000.0]),
                "theta": np.asarray([-1000.0, -2000.0, -3000.0]),
                "initial_scale_qty": 1000.0,
                "center_price": 100.0,
            }
        )

        self.assertAlmostEqual(float(snapshot["unit_value"]), 1.0, places=8)
        self.assertAlmostEqual(float(snapshot["unit_delta"]), 0.3, places=8)
        self.assertAlmostEqual(float(snapshot["unit_gamma"]), 0.02, places=8)
        self.assertAlmostEqual(float(snapshot["unit_vega"]), 5.0, places=8)
        self.assertAlmostEqual(float(snapshot["unit_theta"]), -2.0, places=8)

        fallback_snapshot = self.app.winrate_structure_greeks_unit_snapshot(
            {
                "s_grid": np.asarray([90.0, 100.0, 110.0]),
                "price": np.asarray([900.0, 1000.0, 1300.0]),
                "delta": np.asarray([100.0, 300.0, 500.0]),
                "gamma": np.asarray([10.0, 20.0, 30.0]),
                "vega": np.asarray([4000.0, 5000.0, 6000.0]),
                "theta": np.asarray([-1000.0, -2000.0, -3000.0]),
                "initial_scale_qty": 1000.0,
                "center_price": 100.0,
            }
        )
        self.assertAlmostEqual(float(fallback_snapshot["unit_value"]), 1.0, places=8)

        scaled = self.app.winrate_structure_greeks_scaled_snapshot(snapshot, total_qty=1.0)
        self.assertAlmostEqual(float(scaled["structure_value"]), 1.0, places=8)
        self.assertAlmostEqual(float(scaled["structure_delta"]), 0.3, places=8)
        self.assertAlmostEqual(float(scaled["structure_gamma"]), 0.02, places=8)
        self.assertAlmostEqual(float(scaled["structure_vega"]), 5.0, places=8)
        self.assertAlmostEqual(float(scaled["structure_theta"]), -2.0, places=8)

    def test_non_vanilla_volval_dates_prefer_structure_period_fields(self) -> None:
        start_d, end_d = self.app.volval_resolve_structure_period_dates(
            {
                "strategy_code": "SAFETY_AIRBAG",
                "start_date": "2026-05-05",
                "end_date": "2026-05-26",
                "trade_date": "2026-05-05",
                "expiry_date": "2026-05-05",
            }
        )

        self.assertEqual(start_d.isoformat(), "2026-05-05")
        self.assertEqual(end_d.isoformat(), "2026-05-26")

    def test_vanilla_volval_dates_keep_trade_and_expiry_aliases(self) -> None:
        start_d, end_d = self.app.volval_resolve_structure_period_dates(
            {
                "strategy_code": self.app.VANILLA_OPTION_CODE,
                "start_date": "2026-05-01",
                "end_date": "2026-05-20",
                "trade_date": "2026-05-05",
                "expiry_date": "2026-05-26",
            }
        )

        self.assertEqual(start_d.isoformat(), "2026-05-05")
        self.assertEqual(end_d.isoformat(), "2026-05-26")

    def test_self_quote_date_term_sync_rolls_start_and_updates_end_from_term(self) -> None:
        synced = self.app.volval_self_quote_sync_date_term_link(
            {
                "start_date": "2026-05-17",
                "end_date": "2026-05-30",
                "term_trading_days": 3,
            },
            anchor="term_trading_days",
        )

        self.assertEqual(synced["start_date"], "2026-05-18")
        self.assertEqual(synced["end_date"], "2026-05-20")
        self.assertEqual(synced["term_trading_days"], 3)

    def test_self_quote_date_term_sync_rolls_end_and_counts_from_dates(self) -> None:
        synced = self.app.volval_self_quote_sync_date_term_link(
            {
                "start_date": "2026-05-18",
                "end_date": "2026-05-24",
                "term_trading_days": 3,
            },
            anchor="end_date",
        )

        self.assertEqual(synced["start_date"], "2026-05-18")
        self.assertEqual(synced["end_date"], "2026-05-25")
        self.assertEqual(synced["term_trading_days"], 6)

    def test_self_quote_date_term_sync_applies_to_all_non_snowball_manual_codes(self) -> None:
        codes = sorted(set(self.app.VOLVAL_SELF_QUOTE_CODES) - {"SNOWBALL"})

        for code in codes:
            with self.subTest(code=code):
                scenario = self.app.volval_self_quote_base_scenario(
                    self.app.volval_self_quote_manual_resolved(code, start_date_v="2026-05-12")
                )
                scenario.update({"start_date": "2026-05-12", "end_date": "2026-05-29", "term_trading_days": 20})

                synced = self.app.volval_self_quote_sync_date_term_link(scenario, anchor="end_date")

                self.assertEqual(synced["start_date"], "2026-05-12")
                self.assertEqual(synced["end_date"], "2026-05-29")
                self.assertEqual(synced["term_trading_days"], 14)

    def test_non_vanilla_default_reset_when_state_date_or_price_is_invalid(self) -> None:
        self.assertTrue(
            self.app.volval_non_vanilla_state_needs_default_reset(
                start_value="2026-05-09",
                end_value="2026-05-10",
                price_value=756.0,
                default_start=self.app.parse_date_maybe("2026-04-13"),
                default_end=self.app.parse_date_maybe("2026-04-24"),
                default_price=756.0,
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
        )
        self.assertTrue(
            self.app.volval_non_vanilla_state_needs_default_reset(
                start_value="2026-04-13",
                end_value="2026-04-24",
                price_value=0.0,
                default_start=self.app.parse_date_maybe("2026-04-13"),
                default_end=self.app.parse_date_maybe("2026-04-24"),
                default_price=756.0,
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
        )
        self.assertTrue(
            self.app.volval_non_vanilla_state_needs_default_reset(
                start_value="2026-05-06",
                end_value="2026-05-07",
                price_value=756.0,
                default_start=self.app.parse_date_maybe("2026-04-13"),
                default_end=self.app.parse_date_maybe("2026-04-24"),
                default_price=756.0,
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
        )
        self.assertFalse(
            self.app.volval_non_vanilla_state_needs_default_reset(
                start_value="2026-04-13",
                end_value="2026-04-24",
                price_value=756.0,
                default_start=self.app.parse_date_maybe("2026-04-13"),
                default_end=self.app.parse_date_maybe("2026-04-24"),
                default_price=756.0,
                day_count_mode=self.app.VANILLA_VOL_DAY_COUNT_TRADING,
            )
        )

    def test_accumulator_model_implied_vol_recovers_grid_iv(self) -> None:
        self._assert_model_iv_recovers_target(self._basic_range_template(), 20.0)

    def test_airbag_model_implied_vol_recovers_grid_iv(self) -> None:
        self._assert_model_iv_recovers_target(self._airbag_template(), 25.0)

    def test_model_implied_vol_no_solution_returns_nearest_snapshot(self) -> None:
        implied = self.app.winrate_structure_model_implied_volatility(
            self._basic_range_template(),
            start_price=800.0,
            target_value=1_000_000_000_000.0,
            skew=0.0,
            paths=1000,
            trading_days_per_year=252,
            seed=123,
            seed_hint="volval-structure-no-solution-test",
            valuation_model=self.app.WINRATE_STRUCTURE_VALUATION_MODEL_BS_RN,
            risk_free_rate_pct=2.0,
            carry_yield_pct=0.0,
            futures_mode=True,
        )

        self.assertFalse(implied["ok"])
        self.assertTrue(implied.get("no_solution"))
        self.assertIsNotNone(implied.get("nearest_iv_pct"))


if __name__ == "__main__":
    unittest.main()
