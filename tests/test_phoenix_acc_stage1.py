import ast
import copy
import pathlib
import unittest
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

TARGET_SYMBOLS = {
    "PHOENIX_ACC_CALL_FIXED_CODE",
    "PHOENIX_ACC_PUT_FIXED_CODE",
    "PHOENIX_ACC_BASE_NAME",
    "PHOENIX_ACC_KIND_TO_CODE",
    "PHOENIX_ACC_STRATEGY_CODES",
    "PHOENIX_ACC_KNOCK_IN_QTY_MODES",
    "PHOENIX_ACC_KNOCK_OUT_SETTLEMENT_MODES",
    "PHOENIX_ACC_DELIVERED_SIDE_BY_KIND",
    "PHOENIX_ACC_EVENT_TYPES",
    "PHOENIX_ACC_TERMINATE_REASONS",
    "STRATEGY_ALIAS_TO_CODE",
    "KIND_ALIAS_TO_CODE",
    "to_float",
    "pick_first",
    "_int_from_any",
    "normalize_strategy_code",
    "resolve_strategy_code_for_display",
    "normalize_kind_code",
    "_normalize_phoenix_acc_knock_in_qty_mode",
    "_normalize_phoenix_acc_knock_out_settlement_mode",
    "is_phoenix_acc_strategy_value",
    "phoenix_acc_strategy_code_for_kind",
    "resolve_directional_strategy_code",
    "validate_phoenix_acc_terms",
    "phoenix_acc_close_event_type",
    "phoenix_acc_fixed_day_event",
    "simulate_phoenix_acc_fixed_ledger",
}


def load_symbols() -> Dict[str, Any]:
    source = APP_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(APP_PATH))
    body = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(name in TARGET_SYMBOLS for name in target_names):
                body.append(copy.deepcopy(node))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id in TARGET_SYMBOLS:
                body.append(copy.deepcopy(node))
        elif isinstance(node, ast.FunctionDef) and node.name in TARGET_SYMBOLS:
            body.append(copy.deepcopy(node))
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    env: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "Any": Any,
        "Dict": Dict,
        "Iterable": Iterable,
        "List": List,
        "Mapping": Mapping,
        "Optional": Optional,
        "Sequence": Sequence,
        "Tuple": Tuple,
        "pd": pd,
        "CN_TO_STRATEGY_CODE": {},
    }
    exec(compile(module, str(APP_PATH), "exec"), env)
    return env


class PhoenixAccStage1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ns = load_symbols()

    def call_terms(self, **overrides: Any) -> Dict[str, Any]:
        data = {
            "kind_value": "ACC",
            "daily_qty": 10.0,
            "entry_price": 100.0,
            "knock_in_price": 95.0,
            "knock_in_exercise_price": 96.0,
            "subsidy_per_ton": 5.0,
            "knock_out_price": 110.0,
            "participation_rate": 2.0,
            "knock_in_qty_mode": "all",
            "knock_out_settlement_mode": "subsidy",
            "knock_out_exercise_price": None,
        }
        data.update(overrides)
        return data

    def put_terms(self, **overrides: Any) -> Dict[str, Any]:
        data = {
            "kind_value": "DEC",
            "daily_qty": 10.0,
            "entry_price": 100.0,
            "knock_in_price": 105.0,
            "knock_in_exercise_price": 104.0,
            "subsidy_per_ton": 5.0,
            "knock_out_price": 90.0,
            "participation_rate": 2.0,
            "knock_in_qty_mode": "all",
            "knock_out_settlement_mode": "subsidy",
            "knock_out_exercise_price": None,
        }
        data.update(overrides)
        return data

    def simulate(self, closes: Sequence[float], **terms: Any) -> List[Dict[str, Any]]:
        return self.ns["simulate_phoenix_acc_fixed_ledger"](closes, **terms)

    def test_strategy_code_mapping(self) -> None:
        normalize_strategy_code = self.ns["normalize_strategy_code"]
        resolve_directional_strategy_code = self.ns["resolve_directional_strategy_code"]
        call_code = self.ns["PHOENIX_ACC_CALL_FIXED_CODE"]
        put_code = self.ns["PHOENIX_ACC_PUT_FIXED_CODE"]

        self.assertEqual(normalize_strategy_code("phoenix_acc_call_fixed"), call_code)
        self.assertEqual(normalize_strategy_code("phoenix_acc_put_fixed"), put_code)
        self.assertEqual(resolve_directional_strategy_code(put_code, "ACC"), call_code)
        self.assertEqual(resolve_directional_strategy_code(call_code, "DEC"), put_code)

    def test_call_normal_subsidy_to_maturity(self) -> None:
        rows = self.simulate([100.0, 101.0, 102.0], **self.call_terms())
        self.assertEqual([r["event_type"] for r in rows], ["normal_subsidy", "normal_subsidy", "maturity_end"])
        self.assertAlmostEqual(rows[-1]["cumulative_subsidy"], 150.0)
        self.assertAlmostEqual(rows[-1]["cumulative_delivered_qty"], 0.0)
        self.assertTrue(rows[-1]["terminated_flag"])
        self.assertEqual(rows[-1]["terminate_reason"], "maturity")

    def test_call_first_day_knock_in(self) -> None:
        rows = self.simulate([95.0, 100.0], **self.call_terms())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_type"], "knock_in_terminate")
        self.assertAlmostEqual(rows[0]["delivered_qty"], 40.0)
        self.assertEqual(rows[0]["delivered_price"], 96.0)
        self.assertEqual(rows[0]["delivered_side"], "BUY")
        self.assertEqual(rows[0]["terminate_reason"], "knock_in")

    def test_call_mid_knock_out_subsidy(self) -> None:
        rows = self.simulate([100.0, 111.0, 105.0], **self.call_terms())
        self.assertEqual([r["event_type"] for r in rows], ["normal_subsidy", "knock_out_subsidy_terminate"])
        self.assertAlmostEqual(rows[1]["daily_subsidy"], 100.0)
        self.assertAlmostEqual(rows[1]["cumulative_subsidy"], 150.0)
        self.assertAlmostEqual(rows[1]["delivered_qty"], 0.0)
        self.assertEqual(rows[1]["terminate_reason"], "knock_out_subsidy")

    def test_call_mid_knock_out_delivery(self) -> None:
        rows = self.simulate(
            [100.0, 111.0, 105.0],
            **self.call_terms(
                knock_out_settlement_mode="delivery",
                knock_out_exercise_price=108.0,
            ),
        )
        self.assertEqual([r["event_type"] for r in rows], ["normal_subsidy", "knock_out_delivery_terminate"])
        self.assertAlmostEqual(rows[1]["delivered_qty"], 20.0)
        self.assertEqual(rows[1]["delivered_price"], 108.0)
        self.assertEqual(rows[1]["delivered_side"], "BUY")
        self.assertEqual(rows[1]["terminate_reason"], "knock_out_delivery")

    def test_call_knock_in_all_vs_remaining(self) -> None:
        rows_all = self.simulate([100.0, 94.0], **self.call_terms(participation_rate=1.5, knock_in_qty_mode="all"))
        rows_remaining = self.simulate([100.0, 94.0], **self.call_terms(participation_rate=1.5, knock_in_qty_mode="remaining"))
        self.assertAlmostEqual(rows_all[-1]["delivered_qty"], 30.0)
        self.assertAlmostEqual(rows_remaining[-1]["delivered_qty"], 15.0)

    def test_put_mirror_cases(self) -> None:
        rows_maturity = self.simulate([100.0, 100.0], **self.put_terms())
        rows_knock_in = self.simulate([105.0], **self.put_terms())
        rows_knock_out = self.simulate(
            [100.0, 90.0],
            **self.put_terms(knock_out_settlement_mode="delivery", knock_out_exercise_price=91.0),
        )
        self.assertEqual(rows_maturity[-1]["event_type"], "maturity_end")
        self.assertEqual(rows_knock_in[0]["event_type"], "knock_in_terminate")
        self.assertEqual(rows_knock_in[0]["delivered_side"], "SELL")
        self.assertEqual(rows_knock_out[-1]["event_type"], "knock_out_delivery_terminate")
        self.assertEqual(rows_knock_out[-1]["delivered_side"], "SELL")

    def test_boundary_events_are_hard_coded(self) -> None:
        call_knock_in = self.simulate([95.0], **self.call_terms())
        call_knock_out = self.simulate([110.0], **self.call_terms())
        put_knock_in = self.simulate([105.0], **self.put_terms())
        put_knock_out = self.simulate([90.0], **self.put_terms())
        self.assertEqual(call_knock_in[0]["event_type"], "knock_in_terminate")
        self.assertEqual(call_knock_out[0]["event_type"], "knock_out_subsidy_terminate")
        self.assertEqual(put_knock_in[0]["event_type"], "knock_in_terminate")
        self.assertEqual(put_knock_out[0]["event_type"], "knock_out_subsidy_terminate")

    def test_invalid_parameters(self) -> None:
        validate_terms = self.ns["validate_phoenix_acc_terms"]
        _, errors = validate_terms(
            kind_value="ACC",
            entry_price=100.0,
            knock_in_price=110.0,
            knock_in_exercise_price=100.0,
            subsidy_per_ton=-1.0,
            knock_out_price=100.0,
            participation_rate=0.0,
            knock_in_qty_mode="all",
            knock_out_settlement_mode="delivery",
            knock_out_exercise_price=None,
        )
        self.assertTrue(any("knock_in_price < knock_out_price" in msg for msg in errors))
        self.assertTrue(any("participation_rate" in msg for msg in errors))
        self.assertTrue(any("subsidy_per_ton" in msg for msg in errors))
        self.assertTrue(any("knock_out_exercise_price" in msg for msg in errors))
        with self.assertRaises(ValueError):
            self.simulate([100.0], **self.call_terms(participation_rate=0.0))


if __name__ == "__main__":
    unittest.main()
