import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_structure_position_adjustment_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StructurePositionAdjustmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        for cache_name in [
            "_FETCH_SQL_MEMO_CACHE",
            "_LEDGER_MEMO_CACHE",
            "_OPEN_LOT_MEMO_CACHE",
            "_STRUCT_DERIVED_MEMO_CACHE",
            "_MONITOR_UI_MEMO_CACHE",
            "_MONITOR_REPORT_MEMO_CACHE",
        ]:
            cache_obj = getattr(self.app, cache_name, None)
            if hasattr(cache_obj, "clear"):
                cache_obj.clear()
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G1", "头寸调整测试组", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def insert_basic_range_structure(
        self,
        structure_id: str,
        *,
        start_date: str = "2026-04-01",
        end_date: str = "2026-04-03",
        underlying: str = "I.TEST",
        kind: str = "ACC",
        base_qty: float = 1000.0,
        entry_price: float = 100.0,
        strike_price: float = 95.0,
        knock_out_price: float = 110.0,
        multiple: float = 3.0,
    ) -> None:
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
                "G1",
                structure_id,
                structure_id,
                underlying,
                "海证资本",
                kind,
                "BASIC_RANGE",
                "BASIC_RANGE",
                start_date,
                end_date,
                base_qty,
                entry_price,
                strike_price,
                knock_out_price,
                knock_out_price,
                multiple,
                json.dumps({}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )
        self.conn.commit()

    def insert_trs_structure(
        self,
        structure_id: str,
        *,
        underlying: str = "I.TEST",
        kind: str = "ACC",
        entry_price: float = 800.0,
        qty: float = 100.0,
    ) -> None:
        self.app.upsert_trs_structure_row(
            self.conn,
            structure_id=structure_id,
            structure_code=structure_id,
            group_id="G1",
            underlying=underlying,
            risk_party="CP",
            kind_code=kind,
            start_date_s="2026-04-01",
            end_date_s="2026-04-03",
            entry_price=entry_price,
            trs_qty=qty,
        )
        self.conn.commit()

    def insert_prices(self, underlying: str, rows: list[tuple[str, float]]) -> None:
        self.conn.executemany(
            "INSERT INTO price(dt, underlying, settle) VALUES (?,?,?)",
            [(dt_s, underlying, float(settle)) for dt_s, settle in rows],
        )
        self.conn.commit()

    def test_build_open_lot_rows_keeps_manual_adjustment_increase_lot(self) -> None:
        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "S_ADJ",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 100.0,
                    "gen_price": 780.0,
                },
                {
                    "group_id": "G1",
                    "structure_id": "S_ADJ",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "date": "2026-04-02",
                    "generated_qty": 200.0,
                    "gen_price": 790.0,
                },
            ]
        )
        closes = pd.DataFrame(
            [
                {
                    "close_id": "C_ADJ",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_ADJ",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 120.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "source_gen_date": "2026-04-02",
                    "is_external": 0,
                }
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "A_INC_1",
                    "adjust_batch_id": "BATCH_INC_1",
                    "group_id": "G1",
                    "structure_id": "S_ADJ",
                    "underlying": "I2605",
                    "adjust_dt": "2026-04-02",
                    "delta_qty": 50.0,
                    "before_qty": 300.0,
                    "after_qty": 350.0,
                    "basis_open_price": 795.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-02 10:00:00",
                    "created_by": "tester",
                }
            ]
        )

        out = self.app.build_open_lot_rows(wh_cut, closes, "2026-04-03", adjustments)

        self.assertAlmostEqual(float(pd.to_numeric(out["open_qty"], errors="coerce").sum()), 230.0)
        manual_flag = (
            pd.to_numeric(out["__manual_position_adjustment__"], errors="coerce").fillna(0).astype(int)
            if "__manual_position_adjustment__" in out.columns
            else pd.Series(0, index=out.index, dtype=int)
        )
        manual_rows = out[manual_flag.eq(1)].copy().reset_index(drop=True)
        self.assertEqual(int(manual_rows.shape[0]), 1)
        self.assertEqual(str(manual_rows.iloc[0]["date"]), "2026-04-02")
        self.assertAlmostEqual(float(manual_rows.iloc[0]["open_qty"]), 50.0)
        self.assertAlmostEqual(float(manual_rows.iloc[0]["gen_price"]), 795.0)

    def test_build_position_qty_price_adjustment_rows_keeps_price_only_edit(self) -> None:
        rows = self.app.build_structure_position_qty_price_adjustment_rows(
            [
                {
                    "结构ID": "S_REPRICE",
                    "品种": "I2609",
                    "调整前头寸数量": 50000.0,
                    "调整后头寸数量": 50000.0,
                    "调整前在库均价": 808.0,
                    "调整后在库均价": 815.0,
                }
            ],
            group_id="G1",
            adjust_dt="2026-04-09",
            batch_id="BATCH_REPRICE",
            created_at_base=self.app.datetime(2026, 4, 9, 9, 0, 0),
            created_by="tester",
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(str(row["action_type"]), self.app.POSITION_ADJUST_ACTION_REPRICE)
        self.assertAlmostEqual(float(row["delta_qty"]), 0.0)
        self.assertAlmostEqual(float(row["before_qty"]), 50000.0)
        self.assertAlmostEqual(float(row["after_qty"]), 50000.0)
        self.assertAlmostEqual(float(row["previous_basis_open_price"]), 808.0)
        self.assertAlmostEqual(float(row["basis_open_price"]), 815.0)

    def test_build_position_qty_price_adjustment_rows_orders_reprice_before_qty_delta(self) -> None:
        rows = self.app.build_structure_position_qty_price_adjustment_rows(
            [
                {
                    "结构ID": "S_QTY_PRICE",
                    "品种": "I2609",
                    "调整前头寸数量": 50000.0,
                    "调整后头寸数量": 52000.0,
                    "调整前在库均价": 808.0,
                    "调整后在库均价": 815.0,
                }
            ],
            group_id="G1",
            adjust_dt="2026-04-09",
            batch_id="BATCH_QTY_PRICE",
            created_at_base=self.app.datetime(2026, 4, 9, 9, 0, 0),
            created_by="tester",
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(str(rows[0]["action_type"]), self.app.POSITION_ADJUST_ACTION_REPRICE)
        self.assertEqual(str(rows[1]["action_type"]), self.app.POSITION_ADJUST_ACTION_INCREASE)
        self.assertLess(str(rows[0]["created_at"]), str(rows[1]["created_at"]))
        self.assertAlmostEqual(float(rows[1]["delta_qty"]), 2000.0)
        self.assertAlmostEqual(float(rows[1]["basis_open_price"]), 815.0)

    def test_build_open_lot_rows_applies_and_rolls_back_price_only_adjustment(self) -> None:
        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "S_REPRICE_LOT",
                    "underlying": "I2609",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 100.0,
                    "gen_price": 808.0,
                }
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "RP_ORIG_1",
                    "adjust_batch_id": "BATCH_REPRICE_LOT",
                    "group_id": "G1",
                    "structure_id": "S_REPRICE_LOT",
                    "underlying": "I2609",
                    "adjust_dt": "2026-04-02",
                    "delta_qty": 0.0,
                    "before_qty": 100.0,
                    "after_qty": 100.0,
                    "basis_open_price": 815.0,
                    "previous_basis_open_price": 808.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_REPRICE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-02 09:00:00",
                    "created_by": "tester",
                }
            ]
        )

        repriced = self.app.build_open_lot_rows(wh_cut, pd.DataFrame(), "2026-04-02", adjustments)
        self.assertAlmostEqual(float(repriced.iloc[0]["gen_price"]), 815.0)

        rollback_adjustments = pd.concat(
            [
                adjustments,
                pd.DataFrame(
                    [
                        {
                            "adjustment_id": "RP_ROLLBACK_1",
                            "adjust_batch_id": "BATCH_REPRICE_ROLLBACK",
                            "group_id": "G1",
                            "structure_id": "S_REPRICE_LOT",
                            "underlying": "I2609",
                            "adjust_dt": "2026-04-03",
                            "delta_qty": 0.0,
                            "before_qty": 100.0,
                            "after_qty": 100.0,
                            "basis_open_price": 808.0,
                            "previous_basis_open_price": 815.0,
                            "action_type": self.app.POSITION_ADJUST_ACTION_ROLLBACK,
                            "revert_of_adjustment_id": "RP_ORIG_1",
                            "is_reverted": 0,
                            "created_at": "2026-04-03 09:00:00",
                            "created_by": "tester",
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        rolled_back = self.app.build_open_lot_rows(
            wh_cut,
            pd.DataFrame(),
            "2026-04-03",
            rollback_adjustments,
        )
        self.assertAlmostEqual(float(rolled_back.iloc[0]["gen_price"]), 808.0)

    def test_build_structure_position_timeline_frame_tracks_manual_adjust_columns(self) -> None:
        s_df = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "S_TL",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 100.0,
                    "gen_price": 780.0,
                },
                {
                    "group_id": "G1",
                    "structure_id": "S_TL",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "date": "2026-04-02",
                    "generated_qty": 100.0,
                    "gen_price": 790.0,
                },
            ]
        )
        adjustments = pd.DataFrame(
            [
                {
                    "adjustment_id": "A_INC_2",
                    "adjust_batch_id": "BATCH_TL",
                    "group_id": "G1",
                    "structure_id": "S_TL",
                    "underlying": "I2605",
                    "adjust_dt": "2026-04-02",
                    "delta_qty": 40.0,
                    "before_qty": 200.0,
                    "after_qty": 240.0,
                    "basis_open_price": 785.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-02 09:00:00",
                    "created_by": "tester",
                },
                {
                    "adjustment_id": "A_DEC_2",
                    "adjust_batch_id": "BATCH_TL",
                    "group_id": "G1",
                    "structure_id": "S_TL",
                    "underlying": "I2605",
                    "adjust_dt": "2026-04-02",
                    "delta_qty": -10.0,
                    "before_qty": 240.0,
                    "after_qty": 230.0,
                    "basis_open_price": 0.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_DECREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-02 09:05:00",
                    "created_by": "tester",
                },
            ]
        )

        timeline = self.app.build_structure_position_timeline_frame(
            s_df,
            close2_df=pd.DataFrame(),
            adjustment_df=adjustments,
            rep_gid="G1",
            rep_und="I2605",
            rep_date="2026-04-02",
        )

        row = timeline.sort_values(["date", "structure_id"]).iloc[-1]
        self.assertEqual(str(row["structure_id"]), "S_TL")
        self.assertEqual(str(row["date"]), "2026-04-02")
        self.assertAlmostEqual(float(row["current_open_qty"]), 230.0)
        self.assertAlmostEqual(float(row["manual_adjust_increase_qty"]), 40.0)
        self.assertAlmostEqual(float(row["manual_adjust_decrease_qty"]), 10.0)
        self.assertAlmostEqual(float(row["manual_adjust_net_qty"]), 30.0)
        self.assertAlmostEqual(float(row["manual_adjust_cum_qty"]), 30.0)

    def test_rollback_structure_position_adjustment_batches_creates_reverse_rows(self) -> None:
        self.insert_basic_range_structure("S_RB")
        rows = [
            {
                "adjustment_id": "RB_ORIG_1",
                "adjust_batch_id": "BATCH_RB",
                "group_id": "G1",
                "structure_id": "S_RB",
                "underlying": "I.TEST",
                "adjust_dt": "2026-04-02",
                "delta_qty": 500.0,
                "before_qty": 2000.0,
                "after_qty": 2500.0,
                "basis_open_price": 101.0,
                "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                "revert_of_adjustment_id": "",
                "is_reverted": 0,
                "created_at": "2026-04-02 09:00:00",
                "created_by": "tester",
            },
            {
                "adjustment_id": "RB_ORIG_2",
                "adjust_batch_id": "BATCH_RB",
                "group_id": "G1",
                "structure_id": "S_RB",
                "underlying": "I.TEST",
                "adjust_dt": "2026-04-03",
                "delta_qty": -200.0,
                "before_qty": 2500.0,
                "after_qty": 2300.0,
                "basis_open_price": 101.0,
                "action_type": self.app.POSITION_ADJUST_ACTION_DECREASE,
                "revert_of_adjustment_id": "",
                "is_reverted": 0,
                "created_at": "2026-04-03 09:00:00",
                "created_by": "tester",
            },
        ]
        self.app.insert_structure_position_adjustment_rows(self.conn, rows)
        self.conn.commit()

        result = self.app.rollback_structure_position_adjustment_batches(
            self.conn,
            batch_ids=["BATCH_RB"],
            operator="rollback_tester",
            rollback_dt="2026-04-05",
        )

        self.assertEqual(int(result["inserted_rows"]), 2)
        self.assertEqual(result["rolled_back_batches"], ["BATCH_RB"])
        self.assertTrue(str(result["rollback_batch_id"]).startswith("ADJ_RB_"))

        adjust_df = self.app.normalize_structure_position_adjustment_frame(
            self.app.fetch_structure_position_adjustments(self.conn)
        )
        orig = adjust_df[adjust_df["adjust_batch_id"].astype(str) == "BATCH_RB"].copy()
        rb = adjust_df[adjust_df["adjust_batch_id"].astype(str) == str(result["rollback_batch_id"])].copy()

        self.assertEqual(int(orig["is_reverted"].sum()), 2)
        self.assertEqual(int(rb.shape[0]), 2)
        self.assertEqual(
            set(rb["action_type"].astype(str).tolist()),
            {self.app.POSITION_ADJUST_ACTION_ROLLBACK},
        )
        self.assertAlmostEqual(float(pd.to_numeric(rb["delta_qty"], errors="coerce").sum()), -300.0)
        qty_map = self.app.build_structure_position_adjustment_qty_map(
            adjust_df,
            group_id="G1",
            structure_ids=["S_RB"],
            as_of_date=self.app.parse_date_maybe("2026-04-05"),
        )
        self.assertAlmostEqual(float(qty_map.get("S_RB", 0.0)), 0.0)

    def test_rollback_structure_position_adjustment_batches_reverts_price_only_adjustment(self) -> None:
        self.insert_basic_range_structure("S_RB_REPRICE")
        self.app.insert_structure_position_adjustment_rows(
            self.conn,
            [
                {
                    "adjustment_id": "RB_REPRICE_ORIG_1",
                    "adjust_batch_id": "BATCH_RB_REPRICE",
                    "group_id": "G1",
                    "structure_id": "S_RB_REPRICE",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-02",
                    "delta_qty": 0.0,
                    "before_qty": 3000.0,
                    "after_qty": 3000.0,
                    "basis_open_price": 108.0,
                    "previous_basis_open_price": 100.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_REPRICE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-02 09:00:00",
                    "created_by": "tester",
                }
            ],
        )
        self.conn.commit()

        result = self.app.rollback_structure_position_adjustment_batches(
            self.conn,
            batch_ids=["BATCH_RB_REPRICE"],
            operator="rollback_tester",
            rollback_dt="2026-04-03",
        )

        self.assertEqual(int(result["inserted_rows"]), 1)
        adjust_df = self.app.normalize_structure_position_adjustment_frame(
            self.app.fetch_structure_position_adjustments(self.conn)
        )
        rollback_rows = adjust_df[
            adjust_df["adjust_batch_id"].astype(str) == str(result["rollback_batch_id"])
        ].copy()
        self.assertEqual(int(rollback_rows.shape[0]), 1)
        self.assertEqual(str(rollback_rows.iloc[0]["action_type"]), self.app.POSITION_ADJUST_ACTION_ROLLBACK)
        self.assertAlmostEqual(float(rollback_rows.iloc[0]["delta_qty"]), 0.0)
        self.assertAlmostEqual(float(rollback_rows.iloc[0]["basis_open_price"]), 100.0)
        self.assertAlmostEqual(float(rollback_rows.iloc[0]["previous_basis_open_price"]), 108.0)

        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "S_RB_REPRICE",
                    "underlying": "I.TEST",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 100.0,
                    "gen_price": 100.0,
                }
            ]
        )
        rolled_back = self.app.build_open_lot_rows(
            wh_cut,
            pd.DataFrame(),
            "2026-04-03",
            self.app.fetch_structure_position_adjustments(self.conn),
        )
        self.assertAlmostEqual(float(rolled_back.iloc[0]["gen_price"]), 100.0)

    def test_trs_price_adjustment_updates_structure_price_fields_and_runtime(self) -> None:
        self.insert_trs_structure("S_TRS_REPRICE", entry_price=800.0, qty=100.0)
        self.insert_prices("I.TEST", [("2026-04-01", 810.0), ("2026-04-02", 820.0)])
        rows = self.app.build_structure_position_qty_price_adjustment_rows(
            [
                {
                    "structure_id": "S_TRS_REPRICE",
                    "underlying": "I.TEST",
                    "before_qty": 100.0,
                    "after_qty": 100.0,
                    "previous_basis_open_price": 800.0,
                    "basis_open_price": 815.0,
                }
            ],
            group_id="G1",
            adjust_dt="2026-04-02",
            batch_id="BATCH_TRS_REPRICE",
            created_at_base=self.app.datetime(2026, 4, 2, 9, 0, 0),
            created_by="tester",
        )
        self.assertEqual(len(rows), 1)

        self.conn.execute("BEGIN IMMEDIATE")
        self.app.insert_structure_position_adjustment_rows(self.conn, rows)
        updated = self.app.sync_trs_structure_price_from_position_adjustment_rows(self.conn, rows)
        self.conn.commit()
        self.app.clear_runtime_caches_after_db_write()

        self.assertEqual(updated, 1)
        stored = self.conn.execute(
            "SELECT name, entry_price, strike_price, gen_price FROM structure WHERE structure_id=?",
            ("S_TRS_REPRICE",),
        ).fetchone()
        self.assertIsNotNone(stored)
        self.assertIn("815", str(stored[0]))
        self.assertAlmostEqual(float(stored[1]), 815.0)
        self.assertAlmostEqual(float(stored[2]), 815.0)
        self.assertAlmostEqual(float(stored[3]), 815.0)

        struct_df_all, _, bounds_df = self.app.compute_ledgers_cached(self.conn, as_of_date="2026-04-02")
        close2_df = self.app.fetch_closes2(self.conn)
        adjustment_df = self.app.fetch_structure_position_adjustments(self.conn)
        timeline = self.app.build_structure_position_timeline_frame(
            struct_df_all,
            close2_df,
            adjustment_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
        )
        enriched = self.app.enrich_trs_daily_rows(
            struct_df_all,
            close2_df=close2_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
            position_timeline=timeline,
        )
        trs_row = (
            enriched[
                (enriched["structure_id"].astype(str) == "S_TRS_REPRICE")
                & (enriched["date"].astype(str) == "2026-04-02")
            ]
            .iloc[0]
        )
        self.assertAlmostEqual(float(trs_row["entry_price"]), 815.0)
        self.assertAlmostEqual(float(trs_row["strike_price"]), 815.0)
        self.assertAlmostEqual(float(trs_row["current_open_avg"]), 815.0)
        self.assertAlmostEqual(float(trs_row["current_open_qty"]), 100.0)
        self.assertAlmostEqual(float(trs_row["day_pnl"]), 500.0)

        runtime = self.app.build_monitor_report_runtime_cached(
            struct_df_all,
            struct_df_all,
            struct_df_all[struct_df_all["date"].astype(str) == "2026-04-02"].copy(),
            bounds_df,
            close2_df,
            adjustment_df,
            self.app.fetch_snowball_conversions(self.conn),
            self.app.fetch_structures(self.conn),
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
            rep_und_all=False,
            inactive_sid_block=[],
        )
        self.assertAlmostEqual(float(runtime["rep_open_avg_map"].get("S_TRS_REPRICE", 0.0)), 815.0)

    def test_trs_qty_and_price_adjustment_updates_structure_and_monitor_runtime(self) -> None:
        self.insert_trs_structure("S_TRS_QTY_PRICE", entry_price=800.0, qty=100.0)
        self.insert_prices("I.TEST", [("2026-04-01", 810.0), ("2026-04-02", 820.0)])
        rows = self.app.build_structure_position_qty_price_adjustment_rows(
            [
                {
                    "structure_id": "S_TRS_QTY_PRICE",
                    "underlying": "I.TEST",
                    "before_qty": 100.0,
                    "after_qty": 150.0,
                    "previous_basis_open_price": 800.0,
                    "basis_open_price": 815.0,
                }
            ],
            group_id="G1",
            adjust_dt="2026-04-02",
            batch_id="BATCH_TRS_QTY_PRICE",
            created_at_base=self.app.datetime(2026, 4, 2, 9, 0, 0),
            created_by="tester",
        )
        self.assertEqual(
            [str(r.get("action_type")) for r in rows],
            [self.app.POSITION_ADJUST_ACTION_REPRICE, self.app.POSITION_ADJUST_ACTION_INCREASE],
        )

        self.conn.execute("BEGIN IMMEDIATE")
        self.app.insert_structure_position_adjustment_rows(self.conn, rows)
        updated = self.app.sync_trs_structure_price_from_position_adjustment_rows(self.conn, rows)
        self.conn.commit()
        self.app.clear_runtime_caches_after_db_write()

        self.assertEqual(updated, 1)
        stored = self.conn.execute(
            "SELECT entry_price, strike_price, gen_price FROM structure WHERE structure_id=?",
            ("S_TRS_QTY_PRICE",),
        ).fetchone()
        self.assertIsNotNone(stored)
        self.assertAlmostEqual(float(stored[0]), 815.0)
        self.assertAlmostEqual(float(stored[1]), 815.0)
        self.assertAlmostEqual(float(stored[2]), 815.0)

        struct_df_all, _, bounds_df = self.app.compute_ledgers_cached(self.conn, as_of_date="2026-04-02")
        close2_df = self.app.fetch_closes2(self.conn)
        adjustment_df = self.app.fetch_structure_position_adjustments(self.conn)
        timeline = self.app.build_structure_position_timeline_frame(
            struct_df_all,
            close2_df,
            adjustment_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
        )
        enriched = self.app.enrich_trs_daily_rows(
            struct_df_all,
            close2_df=close2_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
            position_timeline=timeline,
        )
        trs_row = (
            enriched[
                (enriched["structure_id"].astype(str) == "S_TRS_QTY_PRICE")
                & (enriched["date"].astype(str) == "2026-04-02")
            ]
            .iloc[0]
        )
        self.assertAlmostEqual(float(trs_row["entry_price"]), 815.0)
        self.assertAlmostEqual(float(trs_row["strike_price"]), 815.0)
        self.assertAlmostEqual(float(trs_row["current_open_avg"]), 815.0)
        self.assertAlmostEqual(float(trs_row["current_open_qty"]), 150.0)
        self.assertAlmostEqual(float(trs_row["day_pnl"]), 750.0)

        runtime = self.app.build_monitor_report_runtime_cached(
            struct_df_all,
            struct_df_all,
            struct_df_all[struct_df_all["date"].astype(str) == "2026-04-02"].copy(),
            bounds_df,
            close2_df,
            adjustment_df,
            self.app.fetch_snowball_conversions(self.conn),
            self.app.fetch_structures(self.conn),
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
            rep_und_all=False,
            inactive_sid_block=[],
        )
        self.assertAlmostEqual(float(runtime["rep_open_qty_map"].get("S_TRS_QTY_PRICE", 0.0)), 150.0)
        self.assertAlmostEqual(float(runtime["rep_open_avg_map"].get("S_TRS_QTY_PRICE", 0.0)), 815.0)
        self.assertAlmostEqual(float(runtime["current_float_map"].get("S_TRS_QTY_PRICE", 0.0)), 750.0)

    def test_trs_dec_qty_price_adjustment_uses_signed_qty_for_float_pnl(self) -> None:
        self.insert_trs_structure("S_TRS_DEC_QTY_PRICE", kind="DEC", entry_price=800.0, qty=40000.0)
        self.insert_prices("I.TEST", [("2026-04-01", 810.0), ("2026-04-02", 803.0)])
        rows = self.app.build_structure_position_qty_price_adjustment_rows(
            [
                {
                    "structure_id": "S_TRS_DEC_QTY_PRICE",
                    "underlying": "I.TEST",
                    "before_qty": 40000.0,
                    "after_qty": 50000.0,
                    "previous_basis_open_price": 800.0,
                    "basis_open_price": 809.0,
                }
            ],
            group_id="G1",
            adjust_dt="2026-04-02",
            batch_id="BATCH_TRS_DEC_QTY_PRICE",
            created_at_base=self.app.datetime(2026, 4, 2, 9, 0, 0),
            created_by="tester",
        )
        self.assertEqual(
            [str(r.get("action_type")) for r in rows],
            [self.app.POSITION_ADJUST_ACTION_REPRICE, self.app.POSITION_ADJUST_ACTION_INCREASE],
        )

        self.conn.execute("BEGIN IMMEDIATE")
        self.app.insert_structure_position_adjustment_rows(self.conn, rows)
        self.app.sync_trs_structure_price_from_position_adjustment_rows(self.conn, rows)
        self.conn.commit()
        self.app.clear_runtime_caches_after_db_write()

        stored = self.conn.execute(
            "SELECT entry_price, strike_price, gen_price FROM structure WHERE structure_id=?",
            ("S_TRS_DEC_QTY_PRICE",),
        ).fetchone()
        self.assertIsNotNone(stored)
        self.assertAlmostEqual(float(stored[0]), 809.0)
        self.assertAlmostEqual(float(stored[1]), 809.0)
        self.assertAlmostEqual(float(stored[2]), 809.0)

        struct_df_all, _, bounds_df = self.app.compute_ledgers_cached(self.conn, as_of_date="2026-04-02")
        close2_df = self.app.fetch_closes2(self.conn)
        adjustment_df = self.app.fetch_structure_position_adjustments(self.conn)
        timeline = self.app.build_structure_position_timeline_frame(
            struct_df_all,
            close2_df,
            adjustment_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
        )
        enriched = self.app.enrich_trs_daily_rows(
            struct_df_all,
            close2_df=close2_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
            position_timeline=timeline,
        )
        trs_row = (
            enriched[
                (enriched["structure_id"].astype(str) == "S_TRS_DEC_QTY_PRICE")
                & (enriched["date"].astype(str) == "2026-04-02")
            ]
            .iloc[0]
        )
        self.assertAlmostEqual(float(trs_row["entry_price"]), 809.0)
        self.assertAlmostEqual(float(trs_row["strike_price"]), 809.0)
        self.assertAlmostEqual(float(trs_row["current_open_avg"]), 809.0)
        self.assertAlmostEqual(float(trs_row["current_open_qty"]), 50000.0)
        self.assertAlmostEqual(float(trs_row["day_pnl"]), 300000.0)

        runtime = self.app.build_monitor_report_runtime_cached(
            struct_df_all,
            struct_df_all,
            struct_df_all[struct_df_all["date"].astype(str) == "2026-04-02"].copy(),
            bounds_df,
            close2_df,
            adjustment_df,
            self.app.fetch_snowball_conversions(self.conn),
            self.app.fetch_structures(self.conn),
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-02",
            rep_und_all=False,
            inactive_sid_block=[],
        )
        self.assertAlmostEqual(float(runtime["rep_open_qty_map"].get("S_TRS_DEC_QTY_PRICE", 0.0)), 50000.0)
        self.assertAlmostEqual(float(runtime["rep_open_avg_map"].get("S_TRS_DEC_QTY_PRICE", 0.0)), 809.0)
        self.assertAlmostEqual(float(runtime["current_float_map"].get("S_TRS_DEC_QTY_PRICE", 0.0)), 300000.0)
        self.assertAlmostEqual(
            float(
                self.app.report_monitor_trs_float_pnl_value(
                    {
                        "kind": "DEC",
                        "open_position_qty": 50000.0,
                        "open_avg_price": 809.0,
                        "settle_price": 803.0,
                        "floating_pnl": 300000.0,
                    }
                )
            ),
            300000.0,
        )

    def test_trs_price_adjustment_rollback_restores_structure_price_fields(self) -> None:
        self.insert_trs_structure("S_TRS_RB_REPRICE", entry_price=800.0, qty=100.0)
        self.insert_prices("I.TEST", [("2026-04-01", 810.0), ("2026-04-02", 820.0), ("2026-04-03", 825.0)])
        rows = self.app.build_structure_position_qty_price_adjustment_rows(
            [
                {
                    "structure_id": "S_TRS_RB_REPRICE",
                    "underlying": "I.TEST",
                    "before_qty": 100.0,
                    "after_qty": 100.0,
                    "previous_basis_open_price": 800.0,
                    "basis_open_price": 815.0,
                }
            ],
            group_id="G1",
            adjust_dt="2026-04-02",
            batch_id="BATCH_TRS_RB_REPRICE",
            created_at_base=self.app.datetime(2026, 4, 2, 9, 0, 0),
            created_by="tester",
        )
        self.conn.execute("BEGIN IMMEDIATE")
        self.app.insert_structure_position_adjustment_rows(self.conn, rows)
        self.app.sync_trs_structure_price_from_position_adjustment_rows(self.conn, rows)
        self.conn.commit()
        self.app.clear_runtime_caches_after_db_write()

        rb_result = self.app.rollback_structure_position_adjustment_batches(
            self.conn,
            batch_ids=["BATCH_TRS_RB_REPRICE"],
            operator="rollback_tester",
            rollback_dt="2026-04-03",
        )

        self.assertEqual(int(rb_result["inserted_rows"]), 1)
        stored = self.conn.execute(
            "SELECT name, entry_price, strike_price, gen_price FROM structure WHERE structure_id=?",
            ("S_TRS_RB_REPRICE",),
        ).fetchone()
        self.assertIsNotNone(stored)
        self.assertIn("800", str(stored[0]))
        self.assertAlmostEqual(float(stored[1]), 800.0)
        self.assertAlmostEqual(float(stored[2]), 800.0)
        self.assertAlmostEqual(float(stored[3]), 800.0)

        struct_df_all, _, _ = self.app.compute_ledgers_cached(self.conn, as_of_date="2026-04-03")
        open_lots = self.app.build_open_lot_rows(
            struct_df_all,
            self.app.fetch_closes2(self.conn),
            "2026-04-03",
            self.app.fetch_structure_position_adjustments(self.conn),
        )
        trs_lots = open_lots[open_lots["structure_id"].astype(str) == "S_TRS_RB_REPRICE"].copy()
        self.assertFalse(trs_lots.empty)
        self.assertAlmostEqual(float(pd.to_numeric(trs_lots["gen_price"], errors="coerce").iloc[-1]), 800.0)

    def test_monitor_runtime_and_daily_frame_include_manual_adjustment_metrics(self) -> None:
        self.insert_basic_range_structure("S_MON")
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 100.0),
                ("2026-04-02", 101.0),
                ("2026-04-03", 102.0),
            ],
        )
        self.app.insert_structure_position_adjustment_rows(
            self.conn,
            [
                {
                    "adjustment_id": "MON_INC_1",
                    "adjust_batch_id": "BATCH_MON",
                    "group_id": "G1",
                    "structure_id": "S_MON",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 500.0,
                    "before_qty": 3000.0,
                    "after_qty": 3500.0,
                    "basis_open_price": 99.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 10:00:00",
                    "created_by": "tester",
                }
            ],
        )
        self.conn.commit()

        struct_df_all, group_df, bounds_df = self.app.compute_ledgers_cached(self.conn)
        self.assertFalse(group_df.empty)
        dsub = struct_df_all[struct_df_all["date"].astype(str) == "2026-04-03"].copy()
        close2_df = self.app.fetch_closes2(self.conn)
        adjustment_df = self.app.fetch_structure_position_adjustments(self.conn)
        snowball_conv_asof = self.app.fetch_snowball_conversions(self.conn)
        structs_df = self.app.fetch_structures(self.conn)

        runtime = self.app.build_monitor_report_runtime_cached(
            struct_df_all,
            struct_df_all,
            dsub,
            bounds_df,
            close2_df,
            adjustment_df,
            snowball_conv_asof,
            structs_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            rep_und_all=False,
            inactive_sid_block=[],
        )
        self.assertAlmostEqual(float(runtime["rep_open_qty_map"].get("S_MON", 0.0)), 3500.0)
        self.assertAlmostEqual(float(runtime["rep_manual_adjust_net_map"].get("S_MON", 0.0)), 500.0)
        self.assertAlmostEqual(float(runtime["rep_manual_adjust_today_map"].get("S_MON", 0.0)), 500.0)
        self.assertAlmostEqual(float(runtime["rep_manual_adjust_increase_today_map"].get("S_MON", 0.0)), 500.0)
        self.assertAlmostEqual(float(runtime["rep_manual_adjust_decrease_today_map"].get("S_MON", 0.0)), 0.0)

        monitor_daily = self.app.build_monitor_structure_daily_frame_cached(
            struct_df_all,
            close2_df,
            adjustment_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            sid_base_qty_per_day_map={},
            sid_structure_name_display_map={},
            sid_direction_display_map={},
            sid_buy_sell_direction_map={},
            sid_structure_detail_label_map={},
            structure_code_map=self.app.build_structure_code_map(structs_df),
        )
        row = (
            monitor_daily[monitor_daily["结构ID"].astype(str) == "S_MON"]
            .sort_values(["日期", "结构ID"])
            .iloc[-1]
        )
        self.assertAlmostEqual(float(row["当前持仓量"]), 3500.0)
        self.assertAlmostEqual(float(row["手动增仓量"]), 500.0)
        self.assertAlmostEqual(float(row["手动调整净额"]), 500.0)
        self.assertAlmostEqual(float(row["手动调整累计"]), 500.0)

    def test_monitor_cached_views_refresh_after_position_adjustment_write(self) -> None:
        self.insert_basic_range_structure("S_MON_CACHE")
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 100.0),
                ("2026-04-02", 101.0),
                ("2026-04-03", 102.0),
            ],
        )

        struct_df_all, _, bounds_df = self.app.compute_ledgers_cached(self.conn)
        dsub = struct_df_all[struct_df_all["date"].astype(str) == "2026-04-03"].copy()
        close2_df = self.app.fetch_closes2(self.conn)
        adjustment_df = self.app.fetch_structure_position_adjustments(self.conn)
        snowball_conv_asof = self.app.fetch_snowball_conversions(self.conn)
        structs_df = self.app.fetch_structures(self.conn)
        structure_code_map = self.app.build_structure_code_map(structs_df)

        runtime_before = self.app.build_monitor_report_runtime_cached(
            struct_df_all,
            struct_df_all,
            dsub,
            bounds_df,
            close2_df,
            adjustment_df,
            snowball_conv_asof,
            structs_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            rep_und_all=False,
            inactive_sid_block=[],
        )
        daily_before = self.app.build_monitor_structure_daily_frame_cached(
            struct_df_all,
            close2_df,
            adjustment_df,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            sid_base_qty_per_day_map={},
            sid_structure_name_display_map={},
            sid_direction_display_map={},
            sid_buy_sell_direction_map={},
            sid_structure_detail_label_map={},
            structure_code_map=structure_code_map,
        )
        sid_col = next(col for col in daily_before.columns if str(col).endswith("ID"))
        date_col = next(
            col
            for col in daily_before.columns
            if ("日期" in str(col)) or ("鏃ユ湡" in str(col))
        )
        row_before = (
            daily_before[daily_before[sid_col].astype(str) == "S_MON_CACHE"]
            .sort_values([date_col, sid_col])
            .iloc[-1]
        )
        self.assertAlmostEqual(float(runtime_before["rep_open_qty_map"].get("S_MON_CACHE", 0.0)), 3000.0)
        self.assertAlmostEqual(float(row_before["当前持仓量"]), 3000.0)

        self.app.insert_structure_position_adjustment_rows(
            self.conn,
            [
                {
                    "adjustment_id": "MON_CACHE_INC_1",
                    "adjust_batch_id": "BATCH_MON_CACHE",
                    "group_id": "G1",
                    "structure_id": "S_MON_CACHE",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": 500.0,
                    "before_qty": 3000.0,
                    "after_qty": 3500.0,
                    "basis_open_price": 99.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 11:00:00",
                    "created_by": "tester",
                }
            ],
        )
        self.conn.commit()

        struct_df_all_after, _, bounds_df_after = self.app.compute_ledgers_cached(self.conn)
        dsub_after = struct_df_all_after[struct_df_all_after["date"].astype(str) == "2026-04-03"].copy()
        close2_df_after = self.app.fetch_closes2(self.conn)
        adjustment_df_after = self.app.fetch_structure_position_adjustments(self.conn)
        snowball_conv_asof_after = self.app.fetch_snowball_conversions(self.conn)
        structs_df_after = self.app.fetch_structures(self.conn)
        structure_code_map_after = self.app.build_structure_code_map(structs_df_after)

        runtime_after = self.app.build_monitor_report_runtime_cached(
            struct_df_all_after,
            struct_df_all_after,
            dsub_after,
            bounds_df_after,
            close2_df_after,
            adjustment_df_after,
            snowball_conv_asof_after,
            structs_df_after,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            rep_und_all=False,
            inactive_sid_block=[],
        )
        daily_after = self.app.build_monitor_structure_daily_frame_cached(
            struct_df_all_after,
            close2_df_after,
            adjustment_df_after,
            rep_gid="G1",
            rep_und="I.TEST",
            rep_date="2026-04-03",
            sid_base_qty_per_day_map={},
            sid_structure_name_display_map={},
            sid_direction_display_map={},
            sid_buy_sell_direction_map={},
            sid_structure_detail_label_map={},
            structure_code_map=structure_code_map_after,
        )
        row_after = (
            daily_after[daily_after[sid_col].astype(str) == "S_MON_CACHE"]
            .sort_values([date_col, sid_col])
            .iloc[-1]
        )

        self.assertAlmostEqual(float(runtime_after["rep_open_qty_map"].get("S_MON_CACHE", 0.0)), 3500.0)
        self.assertAlmostEqual(float(runtime_after["rep_manual_adjust_net_map"].get("S_MON_CACHE", 0.0)), 500.0)
        self.assertAlmostEqual(float(row_after["当前持仓量"]), 3500.0)
        self.assertAlmostEqual(float(row_after["手动增仓量"]), 500.0)

    def test_special_runtime_seed_reflects_decrease_and_rollback(self) -> None:
        self.insert_basic_range_structure("S_SPEC")
        self.insert_prices(
            "I.TEST",
            [
                ("2026-04-01", 100.0),
                ("2026-04-02", 101.0),
                ("2026-04-03", 102.0),
            ],
        )
        structs_df = self.app.fetch_structures(self.conn)
        prices_df = self.app.fetch_prices(self.conn)
        struct_row = (
            structs_df[structs_df["structure_id"].astype(str) == "S_SPEC"]
            .iloc[0]
            .to_dict()
        )

        def build_seed() -> dict:
            struct_asof, _, bounds_asof = self.app.compute_ledgers_cached(self.conn, as_of_date="2026-04-03")
            return self.app.special_build_runtime_state_seed(
                struct_row=struct_row,
                rep_date="2026-04-03",
                current_price=102.0,
                prices_df=prices_df,
                struct_asof=struct_asof,
                bounds_asof=bounds_asof,
                close2_df=self.app.fetch_closes2(self.conn),
                adjustment_df=self.app.fetch_structure_position_adjustments(self.conn),
            )

        seed_before = build_seed()
        self.assertAlmostEqual(float(seed_before["current_open_qty"]), 3000.0)

        self.app.insert_structure_position_adjustment_rows(
            self.conn,
            [
                {
                    "adjustment_id": "SPEC_DEC_1",
                    "adjust_batch_id": "BATCH_SPEC_DEC",
                    "group_id": "G1",
                    "structure_id": "S_SPEC",
                    "underlying": "I.TEST",
                    "adjust_dt": "2026-04-03",
                    "delta_qty": -800.0,
                    "before_qty": 3000.0,
                    "after_qty": 2200.0,
                    "basis_open_price": 100.0,
                    "action_type": self.app.POSITION_ADJUST_ACTION_DECREASE,
                    "revert_of_adjustment_id": "",
                    "is_reverted": 0,
                    "created_at": "2026-04-03 11:00:00",
                    "created_by": "tester",
                }
            ],
        )
        self.conn.commit()

        seed_after_decrease = build_seed()
        self.assertAlmostEqual(float(seed_after_decrease["current_open_qty"]), 2200.0)

        rb_result = self.app.rollback_structure_position_adjustment_batches(
            self.conn,
            batch_ids=["BATCH_SPEC_DEC"],
            operator="rollback_tester",
            rollback_dt="2026-04-03",
        )
        self.assertEqual(int(rb_result["inserted_rows"]), 1)

        seed_after_rollback = build_seed()
        self.assertAlmostEqual(float(seed_after_rollback["current_open_qty"]), 3000.0)

    def test_normalize_structure_position_qty_edit_state_preserves_or_resets_by_current_qty(self) -> None:
        rows = pd.DataFrame(
            [
                {"结构ID": "S1", "头寸数量": 1000.0, "可平数量": 1000.0, "在库均价": 101.0},
                {"结构ID": "S2", "头寸数量": 800.0, "可平数量": 800.0, "在库均价": 99.0},
            ]
        )
        raw_state = {
            "S1": {"头寸数量": 1200.0, "当前数量": 1000.0, "在库均价": 101.0},
            "S2": {"头寸数量": 900.0, "当前数量": 700.0, "在库均价": 99.0},
        }

        out = self.app.normalize_structure_position_qty_edit_state(rows, raw_state)

        self.assertAlmostEqual(float(out["S1"]["头寸数量"]), 1200.0)
        self.assertAlmostEqual(float(out["S1"]["当前数量"]), 1000.0)
        self.assertAlmostEqual(float(out["S2"]["头寸数量"]), 800.0)
        self.assertAlmostEqual(float(out["S2"]["当前数量"]), 800.0)


    def test_init_db_backfills_legacy_structure_position_adjustment_columns(self) -> None:
        legacy_conn = sqlite3.connect(":memory:")
        try:
            legacy_conn.executescript(
                """
                CREATE TABLE strategy_group (
                    group_id TEXT PRIMARY KEY,
                    group_name TEXT NOT NULL,
                    underlying TEXT NOT NULL
                );
                CREATE TABLE structure (
                    structure_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    structure_code TEXT NOT NULL DEFAULT '',
                    name TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    risk_party TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    strategy_code TEXT NOT NULL DEFAULT '',
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    base_qty_per_day REAL NOT NULL,
                    entry_price REAL NOT NULL DEFAULT 0,
                    strike_price REAL NOT NULL,
                    barrier_out REAL,
                    knock_out_price REAL,
                    multiple REAL NOT NULL,
                    params_json TEXT NOT NULL,
                    meta_json TEXT NOT NULL
                );
                CREATE TABLE structure_position_adjustment (
                    adjustment_id TEXT PRIMARY KEY,
                    adjust_dt TEXT NOT NULL,
                    delta_qty REAL NOT NULL,
                    created_at TEXT NOT NULL
                );
                INSERT INTO strategy_group(group_id, group_name, underlying)
                VALUES ('G1', 'Legacy Group', 'I.TEST');
                INSERT INTO structure(
                    structure_id, group_id, structure_code, name, underlying, risk_party, kind, strategy,
                    strategy_code, start_date, end_date, base_qty_per_day, entry_price, strike_price,
                    barrier_out, knock_out_price, multiple, params_json, meta_json
                ) VALUES(
                    'S_LEGACY', 'G1', 'S001', 'Legacy Structure', 'I.TEST', 'TEST_RISK', 'ACC', 'BASIC_RANGE',
                    'BASIC_RANGE', '2026-04-01', '2026-04-03', 1000, 100, 95, 110, 110, 3, '{}', '{}'
                );
                INSERT INTO structure_position_adjustment(adjustment_id, adjust_dt, delta_qty, created_at)
                VALUES ('LEGACY_ADJ_1', '2026-04-02', 88, '2026-04-02 10:00:00');
                """
            )

            self.app.init_db(legacy_conn)

            cols = {
                str(row[1])
                for row in legacy_conn.execute("PRAGMA table_info(structure_position_adjustment)").fetchall()
            }
            for expected_col in [
                "adjust_batch_id",
                "group_id",
                "structure_id",
                "underlying",
                "before_qty",
                "after_qty",
                "basis_open_price",
                "action_type",
                "revert_of_adjustment_id",
                "is_reverted",
                "created_by",
            ]:
                self.assertIn(expected_col, cols)

            row = legacy_conn.execute(
                """
                SELECT adjust_batch_id, group_id, structure_id, underlying,
                       before_qty, after_qty, basis_open_price,
                       action_type, revert_of_adjustment_id, is_reverted, created_by
                FROM structure_position_adjustment
                WHERE adjustment_id='LEGACY_ADJ_1'
                """
            ).fetchone()
            self.assertEqual(
                row,
                ("", "", "", "", 0.0, 0.0, 0.0, self.app.POSITION_ADJUST_ACTION_INCREASE, "", 0, ""),
            )
        finally:
            legacy_conn.close()

    def test_structure_position_adjustment_trigger_rejects_missing_structure(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.app.insert_structure_position_adjustment_rows(
                self.conn,
                [
                    {
                        "adjustment_id": "TRG_MISS_1",
                        "adjust_batch_id": "BATCH_TRG_MISS",
                        "group_id": "G1",
                        "structure_id": "NO_SUCH_STRUCTURE",
                        "underlying": "I.TEST",
                        "adjust_dt": "2026-04-03",
                        "delta_qty": 100.0,
                        "before_qty": 0.0,
                        "after_qty": 100.0,
                        "basis_open_price": 99.0,
                        "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                        "created_at": "2026-04-03 10:00:00",
                        "created_by": "tester",
                    }
                ],
            )

        self.assertIn("structure_position_adjustment: structure_id not found", str(ctx.exception))
        self.assertIn(
            "结构编号不存在",
            self.app.format_db_write_error("保存头寸数量修改", ctx.exception),
        )

    def test_structure_position_adjustment_trigger_rejects_group_mismatch(self) -> None:
        self.insert_basic_range_structure("S_TRG_GID")
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G2", "Group 2", "I.TEST"),
        )
        self.conn.commit()

        with self.assertRaises(sqlite3.IntegrityError) as ctx:
            self.app.insert_structure_position_adjustment_rows(
                self.conn,
                [
                    {
                        "adjustment_id": "TRG_GID_1",
                        "adjust_batch_id": "BATCH_TRG_GID",
                        "group_id": "G2",
                        "structure_id": "S_TRG_GID",
                        "underlying": "I.TEST",
                        "adjust_dt": "2026-04-03",
                        "delta_qty": 100.0,
                        "before_qty": 0.0,
                        "after_qty": 100.0,
                        "basis_open_price": 99.0,
                        "action_type": self.app.POSITION_ADJUST_ACTION_INCREASE,
                        "created_at": "2026-04-03 10:00:00",
                        "created_by": "tester",
                    }
                ],
            )

        self.assertIn("structure_position_adjustment: group_id mismatch with structure", str(ctx.exception))
        self.assertIn(
            "策略组与结构所属策略组不一致",
            self.app.format_db_write_error("保存头寸数量修改", ctx.exception),
        )


if __name__ == "__main__":
    unittest.main()
