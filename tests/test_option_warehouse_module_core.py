import importlib.util
import inspect
import pathlib
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_option_warehouse_core_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OptionWarehouseModuleCoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_quick_close_confirm_saves_without_over_close_recheck(self) -> None:
        source = inspect.getsource(self.app.quick_close_confirm_dialog)

        self.assertIn("insert_close_rows(conn, rows_to_save)", source)
        self.assertNotIn("validate_no_worse_over_close(", source)

    def test_app_has_no_over_close_recheck_call_sites(self) -> None:
        source = APP_PATH.read_text(encoding="utf-8")
        call_lines = [
            line.strip()
            for line in source.splitlines()
            if "validate_no_worse_over_close(" in line and not line.lstrip().startswith("def ")
        ]

        self.assertEqual([], call_lines)

    def test_manual_structure_close_effective_price_respects_direction(self) -> None:
        self.assertAlmostEqual(
            self.app.manual_structure_close_effective_price("ACC", "SELL", 100.0, 780.0, 2000.0),
            800.0,
        )
        self.assertAlmostEqual(
            self.app.manual_structure_close_effective_price("DEC", "BUY", 100.0, 820.0, 1500.0),
            805.0,
        )

    def test_build_manual_structure_close_rows_splits_fifo_and_preserves_total_pnl(self) -> None:
        plan = self.app.build_manual_structure_close_rows(
            [
                {"date": "2026-04-01", "open_qty": 600.0, "gen_price": 780.0},
                {"date": "2026-04-02", "open_qty": 400.0, "gen_price": 790.0},
            ],
            kind="ACC",
            side="SELL",
            qty=700.0,
            total_pnl=14000.0,
            close_dt="2026-04-03",
            group_id="G1",
            structure_id="S060",
            underlying="I2605",
            quick_batch_id="MANUAL_TEST",
        )

        rows = plan["rows"]
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(float(plan["saved_qty"]), 700.0)
        self.assertAlmostEqual(float(plan["available_qty_before"]), 1000.0)
        self.assertAlmostEqual(float(plan["remaining_open_qty_after"]), 300.0)
        self.assertFalse(bool(plan["auto_manual_close"]))
        self.assertEqual([float(row["qty"]) for row in rows], [600.0, 100.0])
        self.assertEqual([float(row["open_price"]) for row in rows], [780.0, 790.0])
        self.assertEqual([str(row["source_gen_date"]) for row in rows], ["2026-04-01", "2026-04-02"])
        self.assertAlmostEqual(sum(float(row["pnl"]) for row in rows), 14000.0)
        self.assertAlmostEqual(float(rows[0]["close_price"]), 800.0)
        self.assertAlmostEqual(float(rows[1]["close_price"]), 810.0)

    def test_build_manual_structure_close_rows_rejects_over_close(self) -> None:
        with self.assertRaisesRegex(ValueError, "超过当前可平数量"):
            self.app.build_manual_structure_close_rows(
                [
                    {"date": "2026-04-01", "open_qty": 300.0, "gen_price": 780.0},
                ],
                kind="DEC",
                side="BUY",
                qty=500.0,
                total_pnl=1000.0,
                close_dt="2026-04-03",
                group_id="G1",
                structure_id="S058",
                underlying="I2605",
                quick_batch_id="MANUAL_TEST",
            )

    def test_build_open_lot_rows_reduces_only_matching_structure(self) -> None:
        wh_cut = pd.DataFrame(
            [
                {"group_id": "G1", "structure_id": "S_A", "underlying": "I2605", "kind": "ACC", "date": "2026-04-01", "generated_qty": 100.0, "gen_price": 780.0},
                {"group_id": "G1", "structure_id": "S_A", "underlying": "I2605", "kind": "ACC", "date": "2026-04-02", "generated_qty": 200.0, "gen_price": 790.0},
                {"group_id": "G1", "structure_id": "S_B", "underlying": "I2605", "kind": "ACC", "date": "2026-04-01", "generated_qty": 300.0, "gen_price": 781.0},
                {"group_id": "G1", "structure_id": "S_B", "underlying": "I2605", "kind": "ACC", "date": "2026-04-02", "generated_qty": 400.0, "gen_price": 791.0},
            ]
        )
        closes = pd.DataFrame(
            [
                {
                    "close_id": "C_A",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_A",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 150.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "source_gen_date": "2026-04-02",
                    "is_external": 0,
                },
                {
                    "close_id": "C_B",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S_B",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 350.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "source_gen_date": "",
                    "is_external": 0,
                },
            ]
        )

        out = self.app.build_open_lot_rows(wh_cut, closes, "2026-04-03")
        qty_by_sid = out.groupby(out["structure_id"].astype(str))["open_qty"].sum().astype(float).to_dict()
        qty_by_sid_date = {
            (str(row["structure_id"]), str(row["date"])): float(row["open_qty"])
            for _, row in out.iterrows()
        }

        self.assertAlmostEqual(qty_by_sid["S_A"], 150.0)
        self.assertAlmostEqual(qty_by_sid["S_B"], 350.0)
        self.assertAlmostEqual(qty_by_sid_date[("S_A", "2026-04-01")], 100.0)
        self.assertAlmostEqual(qty_by_sid_date[("S_A", "2026-04-02")], 50.0)
        self.assertNotIn(("S_B", "2026-04-01"), qty_by_sid_date)
        self.assertAlmostEqual(qty_by_sid_date[("S_B", "2026-04-02")], 350.0)

    def test_build_open_lot_rows_cache_tracks_in_place_close_frame_changes(self) -> None:
        self.app._OPEN_LOT_MEMO_CACHE.clear()
        wh_cut = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "S_CACHE",
                    "underlying": "I2605",
                    "kind": "ACC",
                    "date": "2026-04-01",
                    "generated_qty": 100.0,
                    "gen_price": 780.0,
                },
            ]
        )
        closes = pd.DataFrame(
            [
                {
                    "close_id": "C_CACHE",
                    "dt": "2026-04-02",
                    "group_id": "G1",
                    "structure_id": "S_CACHE",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 20.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "source_gen_date": "2026-04-01",
                    "is_external": 0,
                }
            ]
        )

        before = self.app.build_open_lot_rows(wh_cut, closes, "2026-04-02")
        closes.loc[0, "qty"] = 60.0
        after = self.app.build_open_lot_rows(wh_cut, closes, "2026-04-02")

        self.assertAlmostEqual(float(before["open_qty"].sum()), 80.0)
        self.assertAlmostEqual(float(after["open_qty"].sum()), 40.0)

    def test_symmetric_close_rows_reduce_only_paired_structures(self) -> None:
        open_lots = pd.DataFrame(
            [
                {"group_id": "G1", "structure_id": "L1", "underlying": "I2605", "kind": "ACC", "date": "2026-04-01", "generated_qty": 100.0, "open_qty": 100.0, "gen_price": 780.0},
                {"group_id": "G1", "structure_id": "L2", "underlying": "I2605", "kind": "ACC", "date": "2026-04-01", "generated_qty": 200.0, "open_qty": 200.0, "gen_price": 781.0},
                {"group_id": "G1", "structure_id": "S1", "underlying": "I2605", "kind": "DEC", "date": "2026-04-01", "generated_qty": 100.0, "open_qty": 100.0, "gen_price": 820.0},
                {"group_id": "G1", "structure_id": "S2", "underlying": "I2605", "kind": "DEC", "date": "2026-04-01", "generated_qty": 200.0, "open_qty": 200.0, "gen_price": 821.0},
            ]
        )
        lot_state = self.app.build_sym_close_lot_state(open_lots)

        long_rows, _ = self.app.consume_sym_close_lots(
            lot_state=lot_state,
            gid="G1",
            batch_id="SYM_TEST",
            pair_dt_s="2026-04-02",
            structure_id="L1",
            qty=60.0,
            kind="ACC",
            side="SELL",
            close_price=800.0,
            underlying_fallback="I2605",
        )
        short_rows, _ = self.app.consume_sym_close_lots(
            lot_state=lot_state,
            gid="G1",
            batch_id="SYM_TEST",
            pair_dt_s="2026-04-02",
            structure_id="S1",
            qty=60.0,
            kind="DEC",
            side="BUY",
            close_price=800.0,
            underlying_fallback="I2605",
        )

        close_rows = pd.DataFrame(long_rows + short_rows)
        replay = self.app.build_open_lot_rows(open_lots, close_rows, "2026-04-02")
        qty_by_sid = replay.groupby(replay["structure_id"].astype(str))["open_qty"].sum().astype(float).to_dict()

        self.assertEqual(set(close_rows["structure_id"].astype(str)), {"L1", "S1"})
        self.assertEqual(set(close_rows["source_gen_date"].astype(str)), {"2026-04-01"})
        self.assertAlmostEqual(qty_by_sid["L1"], 40.0)
        self.assertAlmostEqual(qty_by_sid["L2"], 200.0)
        self.assertAlmostEqual(qty_by_sid["S1"], 40.0)
        self.assertAlmostEqual(qty_by_sid["S2"], 200.0)

    def test_compute_spot_inventory_summary_calculates_available_qty_cost_and_avg(self) -> None:
        lots_df = pd.DataFrame(
            [
                {"group_id": "G1", "spot_name": "现货A", "buy_dt": "2026-04-01", "qty": 1000.0, "buy_price": 800.0},
                {"group_id": "G1", "spot_name": "现货A", "buy_dt": "2026-04-02", "qty": 500.0, "buy_price": 820.0},
                {"group_id": "G2", "spot_name": "现货A", "buy_dt": "2026-04-02", "qty": 999.0, "buy_price": 999.0},
            ]
        )
        logs_df = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "spot_name": "现货A",
                    "match_dt": "2026-04-03",
                    "matched_qty": 600.0,
                    "spot_cost_amount": 484000.0,
                    "spot_pnl": 12000.0,
                    "total_pnl": 18000.0,
                },
                {
                    "group_id": "G2",
                    "spot_name": "现货A",
                    "match_dt": "2026-04-03",
                    "matched_qty": 1.0,
                    "spot_cost_amount": 999.0,
                    "spot_pnl": 1.0,
                    "total_pnl": 1.0,
                },
            ]
        )

        out = self.app.compute_spot_inventory_summary(lots_df, logs_df, group_id="G1")

        self.assertEqual(out.shape[0], 1)
        row = out.iloc[0]
        self.assertEqual(str(row["group_id"]), "G1")
        self.assertEqual(str(row["spot_name"]), "现货A")
        self.assertAlmostEqual(float(row["买入总量"]), 1500.0)
        self.assertAlmostEqual(float(row["买入总成本"]), 1210000.0)
        self.assertAlmostEqual(float(row["已对冲数量"]), 600.0)
        self.assertAlmostEqual(float(row["已结转成本"]), 484000.0)
        self.assertAlmostEqual(float(row["可用数量"]), 900.0)
        self.assertAlmostEqual(float(row["可用成本"]), 726000.0)
        self.assertAlmostEqual(float(row["可用均价"]), 726000.0 / 900.0)
        self.assertAlmostEqual(float(row["现货已实现盈亏"]), 12000.0)
        self.assertAlmostEqual(float(row["对冲总盈亏"]), 18000.0)

    def test_compute_over_close_metrics_matches_expected_breach_summary(self) -> None:
        struct_df = pd.DataFrame(
            [
                {"structure_id": "S1", "date": "2026-04-01", "cum_qty": 100.0},
                {"structure_id": "S1", "date": "2026-04-02", "cum_qty": 200.0},
                {"structure_id": "S1", "date": "2026-04-03", "cum_qty": 300.0},
                {"structure_id": "S2", "date": "2026-04-01", "cum_qty": 100.0},
                {"structure_id": "S2", "date": "2026-04-02", "cum_qty": 200.0},
                {"structure_id": "S2", "date": "2026-04-03", "cum_qty": 300.0},
            ]
        )
        close2_df = pd.DataFrame(
            [
                {
                    "close_id": "C1",
                    "dt": "2026-04-01",
                    "group_id": "G1",
                    "structure_id": "S1",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 50.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "is_external": 0,
                },
                {
                    "close_id": "C2",
                    "dt": "2026-04-03",
                    "group_id": "G1",
                    "structure_id": "S1",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 100.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "is_external": 0,
                },
                {
                    "close_id": "C3",
                    "dt": "2026-04-01",
                    "group_id": "G1",
                    "structure_id": "S2",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 150.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "is_external": 0,
                },
                {
                    "close_id": "C4",
                    "dt": "2026-04-02",
                    "group_id": "G1",
                    "structure_id": "S2",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 100.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "is_external": 0,
                },
            ]
        )
        structure_defs = pd.DataFrame(
            [
                {"structure_id": "S1", "kind": "ACC"},
                {"structure_id": "S2", "kind": "ACC"},
            ]
        )

        metrics = self.app.compute_over_close_metrics(struct_df, close2_df, structure_defs)

        self.assertAlmostEqual(float(metrics["S1"]["max_over_qty"]), 0.0)
        self.assertAlmostEqual(float(metrics["S1"]["final_over_qty"]), 0.0)
        self.assertEqual(str(metrics["S1"]["first_breach_date"]), "")
        self.assertAlmostEqual(float(metrics["S1"]["final_generated_qty"]), 300.0)
        self.assertAlmostEqual(float(metrics["S1"]["final_reduce_qty"]), 150.0)
        self.assertAlmostEqual(float(metrics["S2"]["max_over_qty"]), 50.0)
        self.assertAlmostEqual(float(metrics["S2"]["final_over_qty"]), 0.0)
        self.assertEqual(str(metrics["S2"]["first_breach_date"]), "2026-04-01")
        self.assertAlmostEqual(float(metrics["S2"]["final_generated_qty"]), 300.0)
        self.assertAlmostEqual(float(metrics["S2"]["final_reduce_qty"]), 250.0)

    def test_compute_over_close_metrics_structure_filter_limits_scope(self) -> None:
        struct_df = pd.DataFrame(
            [
                {"structure_id": "S1", "date": "2026-04-01", "cum_qty": 100.0},
                {"structure_id": "S2", "date": "2026-04-01", "cum_qty": 100.0},
            ]
        )
        close2_df = pd.DataFrame(
            [
                {
                    "close_id": "C1",
                    "dt": "2026-04-01",
                    "group_id": "G1",
                    "structure_id": "S1",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 150.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "is_external": 0,
                },
                {
                    "close_id": "C2",
                    "dt": "2026-04-01",
                    "group_id": "G1",
                    "structure_id": "S2",
                    "underlying": "I2605",
                    "side": "SELL",
                    "qty": 20.0,
                    "close_category": self.app.STRUCT_CLOSE_CATEGORY,
                    "is_external": 0,
                },
            ]
        )
        structure_defs = pd.DataFrame(
            [
                {"structure_id": "S1", "kind": "ACC"},
                {"structure_id": "S2", "kind": "ACC"},
            ]
        )

        metrics = self.app.compute_over_close_metrics(
            struct_df,
            close2_df,
            structure_defs,
            structure_ids=["S2"],
        )

        self.assertEqual(set(metrics.keys()), {"S2"})
        self.assertAlmostEqual(float(metrics["S2"]["max_over_qty"]), 0.0)


if __name__ == "__main__":
    unittest.main()
