import importlib.util
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

SID_COL = "\u7ed3\u6784ID"
SELECT_COL = "\u9009\u62e9\u5e73\u4ed3"
SIDE_COL = "\u5e73\u4ed3\u65b9\u5411"
TARGET_QTY_COL = "\u62df\u5e73\u4ed3\u6570\u91cf"
EFFECTIVE_QTY_COL = "\u5e73\u4ed3\u6570\u91cf"
CAN_QTY_COL = "\u53ef\u5e73\u6570\u91cf"
AVG_COL = "\u5728\u5e93\u5747\u4ef7"
PRICE_COL = "\u5e73\u4ed3\u4ef7\u683c"
POS_QTY_COL = "\u5934\u5bf8\u6570\u91cf"
DIR_COL = "\u65b9\u5411"
RISK_COL = "\u98ce\u9669\u5b50"
STRUCT_COL = "\u7ed3\u6784"
ORIG_CAN_QTY_COL = "__\u539f\u59cb\u53ef\u5e73\u6570\u91cf"
ORIG_AVG_COL = "__\u539f\u59cb\u5728\u5e93\u5747\u4ef7"
CLOSE_PRICE_OVERRIDE_COL = "__\u62df\u5e73\u4ed3\u4ef7\u683c\u8986\u76d6"


def load_app():
    spec = importlib.util.spec_from_file_location("app_option_warehouse_target_qty_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OptionWarehouseTargetQtyFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_normalize_preserves_explicit_target_qty_equal_to_available_qty(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        rows = pd.DataFrame(
            [
                {
                    SID_COL: "S001",
                    "kind": "ACC",
                    SIDE_COL: close_side,
                    CAN_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                }
            ]
        )

        state = self.app.normalize_option_warehouse_edit_state(
            rows,
            {
                "S001": {
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: 3000.0,
                    EFFECTIVE_QTY_COL: 3000.0,
                    PRICE_COL: 790.0,
                    CAN_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                }
            },
        )

        self.assertAlmostEqual(float(state["S001"][TARGET_QTY_COL]), 3000.0)
        self.assertAlmostEqual(float(state["S001"][EFFECTIVE_QTY_COL]), 3000.0)

    def test_normalize_preserves_explicit_zero_target_qty(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        rows = pd.DataFrame(
            [
                {
                    SID_COL: "S001_ZERO",
                    "kind": "ACC",
                    SIDE_COL: close_side,
                    CAN_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                }
            ]
        )

        state = self.app.normalize_option_warehouse_edit_state(
            rows,
            {
                "S001_ZERO": {
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: 0.0,
                    EFFECTIVE_QTY_COL: 0.0,
                    PRICE_COL: 790.0,
                    CAN_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                }
            },
        )

        self.assertAlmostEqual(float(state["S001_ZERO"][TARGET_QTY_COL]), 0.0)
        self.assertAlmostEqual(float(state["S001_ZERO"][EFFECTIVE_QTY_COL]), 0.0)

    def test_apply_submission_auto_selects_rows_with_target_qty(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        edited_rows = pd.DataFrame(
            [
                {
                    SID_COL: "S002",
                    SELECT_COL: False,
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: 1200.0,
                    CAN_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                    PRICE_COL: 792.0,
                    POS_QTY_COL: 3000.0,
                }
            ]
        )

        next_edit_state, next_pos_state, next_selected_ids = self.app.apply_option_warehouse_editor_submission(
            edited_rows,
            current_edit_state={},
            current_pos_qty_state={},
            current_selected_ids=[],
            visible_ids=["S002"],
        )

        self.assertEqual(next_selected_ids, ["S002"])
        self.assertAlmostEqual(float(next_edit_state["S002"][TARGET_QTY_COL]), 1200.0)
        self.assertAlmostEqual(float(next_edit_state["S002"][EFFECTIVE_QTY_COL]), 1200.0)
        self.assertAlmostEqual(float(next_pos_state["S002"][POS_QTY_COL]), 3000.0)

    def test_apply_submission_uses_edited_avg_price_without_changing_strike(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        edited_rows = pd.DataFrame(
            [
                {
                    SID_COL: "S_TRS",
                    SELECT_COL: True,
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: None,
                    CAN_QTY_COL: 4200.0,
                    AVG_COL: 812.0,
                    PRICE_COL: 790.0,
                    POS_QTY_COL: 4200.0,
                    ORIG_CAN_QTY_COL: 3000.0,
                    ORIG_AVG_COL: 790.0,
                    CLOSE_PRICE_OVERRIDE_COL: False,
                }
            ]
        )

        next_edit_state, next_pos_state, next_selected_ids = self.app.apply_option_warehouse_editor_submission(
            edited_rows,
            current_edit_state={},
            current_pos_qty_state={},
            current_selected_ids=[],
            visible_ids=["S_TRS"],
        )

        self.assertEqual(next_selected_ids, ["S_TRS"])
        self.assertAlmostEqual(float(next_edit_state["S_TRS"][AVG_COL]), 812.0)
        self.assertAlmostEqual(float(next_edit_state["S_TRS"][PRICE_COL]), 812.0)
        self.assertAlmostEqual(float(next_edit_state["S_TRS"][CAN_QTY_COL]), 4200.0)
        self.assertAlmostEqual(float(next_pos_state["S_TRS"][POS_QTY_COL]), 4200.0)
        self.assertAlmostEqual(float(next_pos_state["S_TRS"]["\u5f53\u524d\u6570\u91cf"]), 3000.0)
        self.assertAlmostEqual(float(next_pos_state["S_TRS"]["\u5f53\u524d\u5728\u5e93\u5747\u4ef7"]), 790.0)

        selected_rows = self.app.build_option_warehouse_selected_rows(
            edited_rows,
            ["S_TRS"],
            next_edit_state,
        )
        detail_rows = self.app.build_warehouse_close_command_detail_rows(
            selected_rows,
            {"S_TRS": {"kind": "ACC", "strike_price": 780.0, "entry_price": 790.0}},
        )

        self.assertEqual(len(detail_rows), 1)
        self.assertAlmostEqual(float(detail_rows[0]["qty"]), 4200.0)
        self.assertAlmostEqual(float(detail_rows[0]["open_price"]), 812.0)
        self.assertAlmostEqual(float(detail_rows[0]["strike_price"]), 780.0)

    def test_position_edit_state_applies_effective_qty_and_avg_price(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    SID_COL: "S_EFFECTIVE",
                    CAN_QTY_COL: 3000.0,
                    POS_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                }
            ]
        )
        raw_state = {
            "S_EFFECTIVE": {
                POS_QTY_COL: 4200.0,
                "\u5f53\u524d\u6570\u91cf": 3000.0,
                AVG_COL: 812.0,
                "\u5f53\u524d\u5728\u5e93\u5747\u4ef7": 790.0,
            }
        }

        normalized_state = self.app.normalize_structure_position_qty_edit_state(rows, raw_state)
        effective_rows = self.app.apply_structure_position_qty_edit_state(rows, normalized_state)

        self.assertAlmostEqual(float(normalized_state["S_EFFECTIVE"][POS_QTY_COL]), 4200.0)
        self.assertAlmostEqual(float(normalized_state["S_EFFECTIVE"][AVG_COL]), 812.0)
        self.assertAlmostEqual(float(effective_rows.iloc[0][CAN_QTY_COL]), 4200.0)
        self.assertAlmostEqual(float(effective_rows.iloc[0][POS_QTY_COL]), 4200.0)
        self.assertAlmostEqual(float(effective_rows.iloc[0][AVG_COL]), 812.0)
        self.assertAlmostEqual(float(effective_rows.iloc[0][ORIG_CAN_QTY_COL]), 3000.0)
        self.assertAlmostEqual(float(effective_rows.iloc[0][ORIG_AVG_COL]), 790.0)

    def test_apply_submission_preserves_explicit_zero_target_qty(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        edited_rows = pd.DataFrame(
            [
                {
                    SID_COL: "S002_ZERO",
                    SELECT_COL: True,
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: 0.0,
                    CAN_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                    PRICE_COL: 792.0,
                    POS_QTY_COL: 3000.0,
                }
            ]
        )

        next_edit_state, _, next_selected_ids = self.app.apply_option_warehouse_editor_submission(
            edited_rows,
            current_edit_state={},
            current_pos_qty_state={},
            current_selected_ids=["S002_ZERO"],
            visible_ids=["S002_ZERO"],
        )

        self.assertEqual(next_selected_ids, ["S002_ZERO"])
        self.assertAlmostEqual(float(next_edit_state["S002_ZERO"][TARGET_QTY_COL]), 0.0)
        self.assertAlmostEqual(float(next_edit_state["S002_ZERO"][EFFECTIVE_QTY_COL]), 0.0)

    def test_apply_submission_replaces_default_full_selection_with_target_qty_rows(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        edited_rows = pd.DataFrame(
            [
                {
                    SID_COL: "S010",
                    SELECT_COL: True,
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: 8000.0,
                    CAN_QTY_COL: 23000.0,
                    AVG_COL: 795.5,
                    PRICE_COL: 795.5,
                    POS_QTY_COL: 23000.0,
                },
                {
                    SID_COL: "S011",
                    SELECT_COL: True,
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: None,
                    CAN_QTY_COL: 20000.0,
                    AVG_COL: 795.0,
                    PRICE_COL: 795.0,
                    POS_QTY_COL: 20000.0,
                },
                {
                    SID_COL: "S012",
                    SELECT_COL: True,
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: None,
                    CAN_QTY_COL: 18000.0,
                    AVG_COL: 793.0,
                    PRICE_COL: 793.0,
                    POS_QTY_COL: 18000.0,
                },
            ]
        )

        _, _, next_selected_ids = self.app.apply_option_warehouse_editor_submission(
            edited_rows,
            current_edit_state={},
            current_pos_qty_state={},
            current_selected_ids=["S010", "S011", "S012"],
            visible_ids=["S010", "S011", "S012"],
            replace_default_selection_with_target_qty=True,
        )

        self.assertEqual(next_selected_ids, ["S010"])

    def test_apply_submission_clearing_explicit_target_qty_drops_legacy_effective_qty(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        edited_rows = pd.DataFrame(
            [
                {
                    SID_COL: "S010",
                    SELECT_COL: True,
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: None,
                    EFFECTIVE_QTY_COL: 1000.0,
                    CAN_QTY_COL: 23000.0,
                    AVG_COL: 795.5,
                    PRICE_COL: 795.5,
                    POS_QTY_COL: 23000.0,
                }
            ]
        )

        next_edit_state, _, _ = self.app.apply_option_warehouse_editor_submission(
            edited_rows,
            current_edit_state={
                "S010": {
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: 1000.0,
                    EFFECTIVE_QTY_COL: 1000.0,
                    PRICE_COL: 795.5,
                    CAN_QTY_COL: 23000.0,
                    AVG_COL: 795.5,
                }
            },
            current_pos_qty_state={},
            current_selected_ids=["S010"],
            visible_ids=["S010"],
        )

        self.assertIsNone(next_edit_state["S010"][TARGET_QTY_COL])
        self.assertAlmostEqual(float(next_edit_state["S010"][EFFECTIVE_QTY_COL]), 23000.0)

    def test_resolve_selection_restores_default_full_selection_when_last_target_qty_cleared(self) -> None:
        selected_ids, default_select_mode, target_qty_select_mode = self.app.resolve_option_warehouse_selection_after_target_qty_edit(
            current_selected_ids=["S010"],
            tentative_selected_ids=["S010"],
            visible_ids=["S010", "S011", "S012"],
            valid_ids=["S010", "S011", "S012"],
            edit_state={
                "S010": {TARGET_QTY_COL: None},
                "S011": {TARGET_QTY_COL: None},
                "S012": {TARGET_QTY_COL: None},
            },
            default_select_mode=False,
            target_qty_select_mode=True,
        )

        self.assertEqual(selected_ids, ["S010", "S011", "S012"])
        self.assertTrue(default_select_mode)
        self.assertFalse(target_qty_select_mode)

    def test_resolve_selection_keeps_only_target_qty_rows_while_target_mode_active(self) -> None:
        selected_ids, default_select_mode, target_qty_select_mode = self.app.resolve_option_warehouse_selection_after_target_qty_edit(
            current_selected_ids=["S010"],
            tentative_selected_ids=["S010", "S011"],
            visible_ids=["S010", "S011", "S012"],
            valid_ids=["S010", "S011", "S012"],
            edit_state={
                "S010": {TARGET_QTY_COL: 8000.0},
                "S011": {TARGET_QTY_COL: None},
                "S012": {TARGET_QTY_COL: 6000.0},
            },
            default_select_mode=False,
            target_qty_select_mode=True,
        )

        self.assertEqual(selected_ids, ["S010", "S012"])
        self.assertFalse(default_select_mode)
        self.assertTrue(target_qty_select_mode)

    def test_close_command_detail_rows_carry_outer_close_price(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        selected_rows = pd.DataFrame(
            [
                {
                    SID_COL: "S003",
                    STRUCT_COL: "Struct-3",
                    RISK_COL: "Risk-A",
                    DIR_COL: "\u770b\u6da8",
                    SIDE_COL: close_side,
                    EFFECTIVE_QTY_COL: 1500.0,
                    AVG_COL: 790.0,
                    PRICE_COL: 795.5,
                }
            ]
        )

        detail_rows = self.app.build_warehouse_close_command_detail_rows(
            selected_rows,
            {
                "S003": {
                    "kind": "ACC",
                    "strike_price": 780.0,
                    "entry_price": 790.0,
                    "risk_party": "Risk-A",
                }
            },
        )

        self.assertEqual(len(detail_rows), 1)
        self.assertAlmostEqual(float(detail_rows[0]["close_price"]), 795.5)
        self.assertAlmostEqual(float(detail_rows[0]["qty"]), 1500.0)

    def test_target_qty_overrides_full_close_qty_in_followup_flows(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    SID_COL: "S004",
                    TARGET_QTY_COL: 200.0,
                    EFFECTIVE_QTY_COL: 3000.0,
                    CAN_QTY_COL: 3000.0,
                }
            ]
        )

        normalized_rows = self.app.apply_option_warehouse_target_qty_overrides(rows)

        self.assertAlmostEqual(float(normalized_rows.iloc[0][EFFECTIVE_QTY_COL]), 200.0)

    def test_zero_target_qty_overrides_full_close_qty_in_followup_flows(self) -> None:
        rows = pd.DataFrame(
            [
                {
                    SID_COL: "S004_ZERO",
                    TARGET_QTY_COL: 0.0,
                    EFFECTIVE_QTY_COL: 3000.0,
                    CAN_QTY_COL: 3000.0,
                }
            ]
        )

        normalized_rows = self.app.apply_option_warehouse_target_qty_overrides(rows)

        self.assertAlmostEqual(float(normalized_rows.iloc[0][EFFECTIVE_QTY_COL]), 0.0)

    def test_close_command_detail_rows_prefer_target_qty_when_present(self) -> None:
        close_side = self.app.close_side_to_cn("SELL")
        selected_rows = pd.DataFrame(
            [
                {
                    SID_COL: "S005",
                    STRUCT_COL: "Struct-5",
                    RISK_COL: "Risk-B",
                    DIR_COL: "\u770b\u6da8",
                    SIDE_COL: close_side,
                    TARGET_QTY_COL: 200.0,
                    EFFECTIVE_QTY_COL: 3000.0,
                    CAN_QTY_COL: 3000.0,
                    AVG_COL: 790.0,
                    PRICE_COL: 795.5,
                }
            ]
        )

        detail_rows = self.app.build_warehouse_close_command_detail_rows(
            selected_rows,
            {
                "S005": {
                    "kind": "ACC",
                    "strike_price": 780.0,
                    "entry_price": 790.0,
                    "risk_party": "Risk-B",
                }
            },
        )

        self.assertEqual(len(detail_rows), 1)
        self.assertAlmostEqual(float(detail_rows[0]["qty"]), 200.0)


if __name__ == "__main__":
    unittest.main()
