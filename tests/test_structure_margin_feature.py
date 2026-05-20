import importlib.util
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_structure_margin_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StructureMarginFeatureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.app._FETCH_SQL_MEMO_CACHE.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES(?,?,?)",
            ("G1", "Group 1", "I.DCE"),
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_margin_payload_links_initial_wan_and_per_ton(self) -> None:
        from_initial = self.app.normalize_structure_margin_payload(
            {
                self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY: 200.0,
                self.app.FUTURES_MARGIN_RATE_PCT_KEY: 9.0,
            },
            total_qty=20000.0,
            entry_price=800.0,
        )
        self.assertAlmostEqual(from_initial[self.app.STRUCTURE_MARGIN_PER_TON_KEY], 100.0)
        self.assertAlmostEqual(from_initial[self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY], 12.5)

        from_per_ton = self.app.normalize_structure_margin_payload(
            {
                self.app.STRUCTURE_MARGIN_PER_TON_KEY: 125.0,
                self.app.FUTURES_MARGIN_RATE_PCT_KEY: 9.0,
            },
            total_qty=16000.0,
            entry_price=800.0,
        )
        self.assertAlmostEqual(from_per_ton[self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY], 200.0)
        self.assertAlmostEqual(from_per_ton[self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY], 15.625)
        self.assertAlmostEqual(self.app.structure_margin_per_ton_rate_pct(164.0, 820.0), 20.0)
        self.assertAlmostEqual(self.app.structure_margin_per_ton_from_rate_pct(10.45, 803.5), 83.96575)

        from_rate_pct = self.app.normalize_structure_margin_payload(
            {self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY: 10.45},
            total_qty=50000.0,
            entry_price=803.5,
        )
        self.assertAlmostEqual(from_rate_pct[self.app.STRUCTURE_MARGIN_PER_TON_KEY], 83.96575)
        self.assertAlmostEqual(from_rate_pct[self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY], 419.82875)

        linked_from_rate_pct = self.app.resolve_structure_margin_linked_values(
            "rate_pct",
            per_ton_rate_pct=10.45,
            total_qty=50000.0,
            entry_price=803.5,
        )
        self.assertAlmostEqual(linked_from_rate_pct[self.app.STRUCTURE_MARGIN_PER_TON_KEY], 83.96575)
        self.assertAlmostEqual(linked_from_rate_pct[self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY], 419.82875)
        self.assertAlmostEqual(linked_from_rate_pct[self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY], 10.45)

        linked_from_initial = self.app.resolve_structure_margin_linked_values(
            "initial",
            initial_wan=200.0,
            total_qty=20000.0,
            entry_price=800.0,
        )
        self.assertAlmostEqual(linked_from_initial[self.app.STRUCTURE_MARGIN_PER_TON_KEY], 100.0)
        self.assertAlmostEqual(linked_from_initial[self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY], 12.5)

        linked_from_per_ton = self.app.resolve_structure_margin_linked_values(
            "per_ton",
            per_ton=125.0,
            total_qty=16000.0,
            entry_price=800.0,
        )
        self.assertAlmostEqual(linked_from_per_ton[self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY], 200.0)
        self.assertAlmostEqual(linked_from_per_ton[self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY], 15.625)

        merged = self.app.merge_structure_margin_payload({"n_days": 20}, from_per_ton, total_qty=16000.0, entry_price=800.0)
        self.assertIn(self.app.STRUCTURE_MARGIN_PARAM_KEY, merged)
        self.assertAlmostEqual(merged[self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY], 200.0)
        self.assertAlmostEqual(merged[self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY], 15.625)
        self.assertEqual(self.app.format_structure_margin_wan_text(200.0), "200.00\u4e07")
        self.assertEqual(self.app.format_structure_margin_yuan_text_from_wan(240.0), "2,400,000.00")

    def test_structure_save_resolve_and_table_expose_margin_fields(self) -> None:
        params = self.app.merge_structure_margin_payload(
            {"n_days": 20, "multiplier": 3.0},
            {
                self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY: 200.0,
                self.app.STRUCTURE_MARGIN_PER_TON_KEY: 100.0,
                self.app.FUTURES_MARGIN_RATE_PCT_KEY: 9.0,
            },
            total_qty=20000.0,
            entry_price=800.0,
        )
        payload = {
            "structure_id": "SID_MARGIN",
            "structure_code": "S001",
            "group_id": "G1",
            "name": "Margin Structure",
            "underlying": "I2609",
            "risk_party": "H",
            "kind_code": "DEC",
            "strategy_code": "BASIC_RANGE",
            "start_date_s": "2026-05-08",
            "end_date_s": "2026-06-04",
            "base_qty": 1000.0,
            "gen_price": 800.0,
            "entry_price": 800.0,
            "strike_price": 800.0,
            "barrier_in": None,
            "barrier_out": 760.0,
            "knock_out_price": 760.0,
            "ko_strike_price": None,
            "multiple": 3.0,
            "params_json": params,
            "meta_json": {},
        }

        self.app.upsert_structure_record_payload(self.conn, payload)
        df = self.app.fetch_structures(self.conn)
        resolved = self.app.resolve_structure_row(df.iloc[0])

        self.assertAlmostEqual(resolved[self.app.STRUCTURE_INITIAL_MARGIN_WAN_KEY], 200.0)
        self.assertAlmostEqual(resolved[self.app.STRUCTURE_MARGIN_PER_TON_KEY], 100.0)
        self.assertAlmostEqual(resolved[self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_KEY], 12.5)
        self.assertAlmostEqual(resolved[self.app.FUTURES_MARGIN_RATE_PCT_KEY], 9.0)

        table = self.app.build_structure_table_view(df)
        self.assertIn(self.app.STRUCTURE_MARGIN_INITIAL_WAN_DISPLAY_COL, table.columns)
        self.assertAlmostEqual(float(table.iloc[0][self.app.STRUCTURE_MARGIN_INITIAL_WAN_DISPLAY_COL]), 200.0)
        self.assertAlmostEqual(float(table.iloc[0][self.app.STRUCTURE_MARGIN_PER_TON_DISPLAY_COL]), 100.0)
        self.assertAlmostEqual(float(table.iloc[0][self.app.STRUCTURE_MARGIN_PER_TON_RATE_PCT_DISPLAY_COL]), 12.5)
        self.assertAlmostEqual(float(table.iloc[0][self.app.FUTURES_MARGIN_RATE_PCT_DISPLAY_COL]), 9.0)


if __name__ == "__main__":
    unittest.main()
