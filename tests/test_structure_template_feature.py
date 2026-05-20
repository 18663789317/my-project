import importlib.util
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_structure_template_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StructureTemplateFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.app._FETCH_SQL_MEMO_CACHE.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_template_payload_omits_entry_price_and_keeps_price_deltas(self) -> None:
        source_payload = {
            "strategy_code": "BASIC_RANGE",
            "kind_code": "DEC",
            "underlying": "I2609",
            "base_qty": 1000.0,
            "start_date_s": "2026-05-04",
            "end_date_s": "2026-06-02",
            "entry_price": 100.0,
            "strike_price": 100.0,
            "barrier_out": 105.0,
            "knock_out_price": 105.0,
            "multiple": 3.0,
            "params_json": {"n_days": 20, "multiplier": 3.0},
            "meta_json": {},
        }

        template_payload = self.app.build_structure_template_payload_from_structure_payload(
            source_payload,
            template_name="",
            template_note="note",
            underlying_name="iron ore",
        )

        self.assertNotIn("entry_price", template_payload)
        self.assertEqual(template_payload["template_name"], "")
        self.assertEqual(template_payload["underlying_name"], "iron ore")
        self.assertEqual(template_payload["n_days"], 20)
        self.assertEqual(template_payload["price_rules"]["strike_price"]["delta"], 0.0)
        self.assertEqual(template_payload["price_rules"]["barrier_out"]["delta"], 5.0)
        self.assertEqual(
            self.app.resolve_structure_template_price_rule_value(
                template_payload["price_rules"]["barrier_out"],
                810.0,
            ),
            815.0,
        )
        self.assertEqual(
            self.app.format_structure_template_price_rule(template_payload["price_rules"]["strike_price"]),
            "同入场价",
        )

    def test_template_upsert_and_duplicate_are_global(self) -> None:
        template_payload = {
            "version": 1,
            "template_name": "",
            "underlying_name": "iron ore",
            "underlying": "I2609",
            "strategy_code": "BASIC_RANGE",
            "kind_code": "DEC",
            "n_days": 20,
            "base_qty": 1000.0,
            "params_json": {"n_days": 20},
            "meta_json": {},
            "price_rules": {"strike_price": {"base": "entry_price", "mode": "same_entry", "delta": 0.0}},
        }

        template_id = self.app.upsert_structure_template(self.conn, template_payload)
        copied_id = self.app.duplicate_structure_template(self.conn, template_id)
        rows = self.app.fetch_structure_templates(self.conn)

        self.assertTrue(template_id)
        self.assertTrue(copied_id)
        self.assertNotEqual(template_id, copied_id)
        self.assertEqual(len(rows), 2)
        self.assertNotIn("group_id", rows.columns)
        self.assertEqual(set(rows["underlying"].astype(str)), {"I2609"})

    def test_template_picker_sort_groups_same_structure_type(self) -> None:
        rows = self.app.pd.DataFrame(
            [
                {
                    "template_id": "basic-1",
                    "strategy_code": "BASIC_RANGE",
                    "payload_json": self.app.json.dumps({"strategy_code": "BASIC_RANGE"}),
                },
                {
                    "template_id": "fixed-1",
                    "strategy_code": "FIXED_SUBSIDY",
                    "payload_json": self.app.json.dumps({"strategy_code": "FIXED_SUBSIDY"}),
                },
                {
                    "template_id": "basic-2",
                    "strategy_code": "BASIC_RANGE",
                    "payload_json": self.app.json.dumps({"strategy_code": "BASIC_RANGE"}),
                },
                {
                    "template_id": "fixed-2",
                    "strategy_code": "FIXED_SUBSIDY",
                    "payload_json": self.app.json.dumps({"strategy_code": "FIXED_SUBSIDY"}),
                },
            ]
        )

        sorted_rows = self.app.sort_structure_templates_for_picker(rows)

        self.assertEqual(
            sorted_rows["template_id"].astype(str).tolist(),
            ["basic-1", "basic-2", "fixed-1", "fixed-2"],
        )


if __name__ == "__main__":
    unittest.main()
