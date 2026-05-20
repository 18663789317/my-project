import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd
from pandas.testing import assert_frame_equal


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_ledger_asof_slice_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LedgerAsofSliceTests(unittest.TestCase):
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
            ("G1", "Ledger Slice", "I.TEST"),
        )
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_in,
                barrier_out, knock_out_price, ko_strike_price, multiple, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "S_LEDGER",
                "G1",
                "S_LEDGER",
                "I.TEST",
                "Risk-A",
                "ACC",
                "BASIC_RANGE",
                "BASIC_RANGE",
                "2026-04-01",
                "2026-04-03",
                1000.0,
                100.0,
                95.0,
                None,
                110.0,
                110.0,
                None,
                3.0,
                json.dumps({}, ensure_ascii=False),
                json.dumps({"ko_terminate": False}, ensure_ascii=False),
            ),
        )
        self.conn.executemany(
            "INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)",
            [
                ("2026-04-01", "I.TEST", 100.0),
                ("2026-04-02", "I.TEST", 101.0),
                ("2026-04-03", "I.TEST", 102.0),
            ],
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_filter_ledger_frames_asof_truncates_rows_by_cutoff_date(self) -> None:
        struct_full, group_full, bounds_full = self.app.compute_ledgers_cached(self.conn)
        struct_asof_slice, group_asof_slice, bounds_asof_slice = self.app.filter_ledger_frames_asof(
            struct_full,
            group_full,
            bounds_full,
            "2026-04-02",
        )

        self.assertFalse(struct_full.empty)
        self.assertLess(len(struct_asof_slice), len(struct_full))
        self.assertTrue((pd.to_datetime(struct_asof_slice["date"]).dt.date <= self.app.parse_date_maybe("2026-04-02")).all())
        self.assertTrue((pd.to_datetime(group_asof_slice["date"]).dt.date <= self.app.parse_date_maybe("2026-04-02")).all())
        if "date" in bounds_asof_slice.columns:
            self.assertTrue((pd.to_datetime(bounds_asof_slice["date"]).dt.date <= self.app.parse_date_maybe("2026-04-02")).all())
        else:
            self.assertEqual(list(bounds_asof_slice.columns), list(bounds_full.columns))
        assert_frame_equal(
            struct_asof_slice.reset_index(drop=True),
            struct_full[pd.to_datetime(struct_full["date"]).dt.date <= self.app.parse_date_maybe("2026-04-02")].reset_index(drop=True),
            check_dtype=False,
        )

    def test_build_melt_maps_respect_asof_even_with_full_history_rows(self) -> None:
        struct_rows = pd.DataFrame(
            [
                {
                    "structure_id": "S1",
                    "group_id": "G1",
                    "date": "2026-04-01",
                    "normalized_status": "vanilla_active",
                    "status": "存续中-买入",
                    "status_cn": "存续中",
                },
                {
                    "structure_id": "S1",
                    "group_id": "G1",
                    "date": "2026-04-02",
                    "normalized_status": "snowball_knock_out",
                    "status": "雪球敲出",
                    "status_cn": "雪球敲出",
                },
                {
                    "structure_id": "S1",
                    "group_id": "G1",
                    "date": "2026-04-03",
                    "normalized_status": "snowball_knock_out",
                    "status": "雪球敲出",
                    "status_cn": "雪球敲出",
                },
                {
                    "structure_id": "S2",
                    "group_id": "G1",
                    "date": "2026-04-03",
                    "normalized_status": "snowball_discount_convert",
                    "status": "雪球折价转期货",
                    "status_cn": "雪球折价转期货",
                },
            ]
        )
        asof_date = self.app.parse_date_maybe("2026-04-02")
        struct_rows_asof = self.app.filter_ledger_frame_asof(struct_rows, asof_date)

        melt_date_full = self.app.build_melt_date_map(struct_rows, group_id="G1", as_of_date=asof_date)
        melt_date_asof = self.app.build_melt_date_map(struct_rows_asof, group_id="G1", as_of_date=asof_date)
        melt_status_full = self.app.build_melt_status_map(struct_rows, group_id="G1", as_of_date=asof_date)
        melt_status_asof = self.app.build_melt_status_map(struct_rows_asof, group_id="G1", as_of_date=asof_date)

        self.assertEqual(melt_date_full, melt_date_asof)
        self.assertEqual(melt_status_full, melt_status_asof)
        self.assertEqual(melt_date_full, {"S1": self.app.parse_date_maybe("2026-04-02")})
        self.assertEqual(melt_status_full, {"S1": "雪球敲出"})


    def test_compute_ledgers_cached_asof_matches_direct_compute(self) -> None:
        direct_struct, direct_group, direct_bounds = self.app.compute_ledgers(self.conn, as_of_date="2026-04-02")
        cached_struct, cached_group, cached_bounds = self.app.compute_ledgers_cached(
            self.conn,
            as_of_date="2026-04-02",
            copy_out=False,
        )
        assert_frame_equal(
            cached_struct.reset_index(drop=True),
            direct_struct.reset_index(drop=True),
            check_dtype=False,
        )
        assert_frame_equal(
            cached_group.reset_index(drop=True),
            direct_group.reset_index(drop=True),
            check_dtype=False,
        )
        assert_frame_equal(
            cached_bounds.reset_index(drop=True),
            direct_bounds.reset_index(drop=True),
            check_dtype=False,
        )

    def test_df_runtime_fingerprint_is_stable_for_equal_copies(self) -> None:
        source = pd.DataFrame(
            [
                {"date": "2026-04-01", "structure_id": "S1", "generated_qty": 100.0},
                {"date": "2026-04-02", "structure_id": "S1", "generated_qty": 200.0},
            ]
        )
        self.assertEqual(
            self.app._df_runtime_fingerprint(source),
            self.app._df_runtime_fingerprint(source.copy()),
        )


if __name__ == "__main__":
    unittest.main()
