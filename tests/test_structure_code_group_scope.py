import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest

import pandas as pd


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_structure_code_scope_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StructureCodeGroupScopeTests(unittest.TestCase):
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
            ("G1", "Group 1", "I.TEST"),
        )
        self.conn.execute(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            ("G2", "Group 2", "I.TEST"),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def insert_structure(
        self,
        structure_id: str,
        *,
        group_id: str,
        structure_code: str,
        name: str | None = None,
        note: str = "",
        risk_party: str = "海证资本",
        kind: str = "ACC",
        strategy_code: str = "BASIC_RANGE",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO structure(
                structure_id, group_id, structure_code, name, underlying, risk_party, kind, strategy, strategy_code,
                start_date, end_date, base_qty_per_day, entry_price, strike_price, barrier_out, knock_out_price,
                multiple, note, params_json, meta_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                structure_id,
                group_id,
                structure_code,
                name or structure_code,
                "I.TEST",
                risk_party,
                kind,
                strategy_code,
                strategy_code,
                "2026-01-05",
                "2026-01-30",
                1000.0,
                100.0,
                95.0,
                110.0,
                110.0,
                3.0,
                note,
                json.dumps({}, ensure_ascii=False),
                json.dumps({}, ensure_ascii=False),
            ),
        )

    def test_merge_data_editor_session_edits_applies_position_patches(self) -> None:
        df = pd.DataFrame(
            [
                {"source_id": "SID_A", "code": "S001", "qty": 100.0},
                {"source_id": "SID_B", "code": "S002", "qty": 200.0},
            ]
        ).set_index("source_id", drop=False)

        merged = self.app.merge_data_editor_session_edits(
            df,
            {"edited_rows": {"1": {"code": "S020", "qty": 250.0}}},
        )

        self.assertEqual(str(merged.loc["SID_B", "code"]), "S020")
        self.assertEqual(float(merged.loc["SID_B", "qty"]), 250.0)
        self.assertEqual(str(merged.loc["SID_A", "code"]), "S001")

    def test_merge_data_editor_session_edits_applies_index_label_patches(self) -> None:
        df = pd.DataFrame(
            [
                {"source_id": "SID_A", "code": "S001", "qty": 100.0},
                {"source_id": "SID_B", "code": "S002", "qty": 200.0},
            ]
        ).set_index("source_id", drop=False)

        merged = self.app.merge_data_editor_session_edits(
            df,
            {"edited_rows": {"SID_A": {"code": "S099"}, "SID_B": {"2": 300.0}}},
        )

        self.assertEqual(str(merged.loc["SID_A", "code"]), "S099")
        self.assertEqual(float(merged.loc["SID_B", "qty"]), 300.0)

    def test_merge_data_editor_session_edits_supports_legacy_cells(self) -> None:
        df = pd.DataFrame(
            [
                {"source_id": "SID_A", "code": "S001", "qty": 100.0},
                {"source_id": "SID_B", "code": "S002", "qty": 200.0},
            ]
        ).set_index("source_id", drop=False)

        merged = self.app.merge_data_editor_session_edits(
            df,
            {"edited_cells": {"0:code": "S010", "1:2": 275.0}},
        )

        self.assertEqual(str(merged.loc["SID_A", "code"]), "S010")
        self.assertEqual(float(merged.loc["SID_B", "qty"]), 275.0)

    def test_merge_data_editor_snapshots_applies_submit_and_live_patches(self) -> None:
        df = pd.DataFrame(
            [
                {"source_id": "SID_A", "code": "S001", "qty": 100.0},
                {"source_id": "SID_B", "code": "S002", "qty": 200.0},
            ]
        ).set_index("source_id", drop=False)

        merged = self.app.merge_data_editor_snapshots(
            df,
            {"edited_rows": {"0": {"qty": 150.0}}},
            {"edited_rows": {"SID_B": {"code": "S200"}}},
        )

        self.assertEqual(float(merged.loc["SID_A", "qty"]), 150.0)
        self.assertEqual(str(merged.loc["SID_B", "code"]), "S200")

    def test_init_db_backfills_legacy_structure_code(self) -> None:
        legacy_conn = sqlite3.connect(":memory:")
        try:
            legacy_conn.executescript(
                """
                CREATE TABLE structure (
                    structure_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    underlying TEXT NOT NULL,
                    risk_party TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    strategy TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    base_qty_per_day REAL NOT NULL,
                    strike_price REAL NOT NULL,
                    barrier_price REAL,
                    multiple REAL NOT NULL,
                    params_json TEXT NOT NULL,
                    meta_json TEXT NOT NULL
                );
                INSERT INTO structure(
                    structure_id, group_id, name, underlying, risk_party, kind, strategy,
                    start_date, end_date, base_qty_per_day, strike_price, barrier_price,
                    multiple, params_json, meta_json
                ) VALUES(
                    'S050', 'G1', 'legacy', 'I.TEST', '海证资本', 'ACC', 'BASIC_RANGE',
                    '2026-01-05', '2026-01-30', 1000, 95, 110, 3, '{}', '{}'
                );
                """
            )
            self.app.init_db(legacy_conn)
            row = legacy_conn.execute(
                "SELECT structure_id, structure_code FROM structure WHERE structure_id='S050'"
            ).fetchone()
            self.assertEqual(row[0], "S050")
            self.assertEqual(row[1], "S050")
        finally:
            legacy_conn.close()

    def test_next_structure_code_for_group_reuses_smallest_gap_per_group(self) -> None:
        self.insert_structure("SID_A", group_id="G1", structure_code="S001")
        self.insert_structure("SID_B", group_id="G1", structure_code="S003")
        self.insert_structure("SID_C", group_id="G2", structure_code="S002")
        self.conn.commit()

        self.assertEqual(self.app.next_structure_code_for_group(self.conn, "G1"), "S002")
        self.assertEqual(self.app.next_structure_code_for_group(self.conn, "G2"), "S001")

    def test_save_structure_payload_with_group_move_reassigns_display_code_and_child_group(self) -> None:
        self.insert_structure("SID_KEEP", group_id="G1", structure_code="S005", name="待迁移结构")
        self.insert_structure("SID_OCCUPY", group_id="G2", structure_code="S001", name="目标组已有结构")
        self.conn.execute(
            """
            INSERT INTO close_trade2(
                close_id, dt, group_id, structure_id, underlying, side, qty, open_price, close_price, pnl, close_category
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("CLOSE_1", "2026-01-20", "G1", "SID_KEEP", "I.TEST", "SELL", 100.0, 100.0, 105.0, 500.0, "结构平仓"),
        )
        self.conn.commit()

        payload = {
            "structure_id": "SID_KEEP",
            "structure_code": "S005",
            "group_id": "G2",
            "name": "待迁移结构",
            "underlying": "I.TEST",
            "risk_party": "海证资本",
            "kind_code": "ACC",
            "strategy_code": "BASIC_RANGE",
            "base_qty": 1000.0,
            "start_date_s": "2026-01-05",
            "end_date_s": "2026-01-30",
            "gen_price": 100.0,
            "entry_price": 100.0,
            "strike_price": 95.0,
            "barrier_out": 110.0,
            "multiple": 3.0,
            "params": {},
            "meta": {},
        }
        self.app.save_structure_payload_with_optional_rename(
            self.conn,
            payload,
            source_structure_id="SID_KEEP",
            manage_tx=True,
        )

        struct_row = self.conn.execute(
            "SELECT group_id, structure_code FROM structure WHERE structure_id=?",
            ("SID_KEEP",),
        ).fetchone()
        close_row = self.conn.execute(
            "SELECT group_id, structure_id FROM close_trade2 WHERE close_id=?",
            ("CLOSE_1",),
        ).fetchone()
        self.assertEqual(struct_row, ("G2", "S002"))
        self.assertEqual(close_row, ("G2", "SID_KEEP"))

    def test_prepare_legacy_bundle_for_import_keeps_display_code_and_remaps_internal_ids(self) -> None:
        self.insert_structure("S001", group_id="G2", structure_code="S001", name="本地历史结构")
        self.conn.commit()

        raw_bundle = json.dumps(
            {
                "format": self.app.STRATEGY_GROUP_BUNDLE_FORMAT,
                "version": 4,
                "tables": {
                    "strategy_group": [{"group_id": "G1", "group_name": "Legacy Bundle", "underlying": "I.TEST"}],
                    "structure": [
                        {
                            "structure_id": "S001",
                            "group_id": "G1",
                            "name": "旧结构",
                            "underlying": "I.TEST",
                            "risk_party": "海证资本",
                            "kind": "ACC",
                            "strategy": "BASIC_RANGE",
                        }
                    ],
                    "close_trade": [],
                    "close_trade2": [{"close_id": "C1", "group_id": "G1", "structure_id": "S001"}],
                    "price": [],
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")

        parsed = self.app.parse_strategy_group_bundle(raw_bundle)
        prepared = self.app.prepare_strategy_group_bundle_for_import(self.conn, parsed)
        prepared_struct = prepared["tables"]["structure"][0]
        prepared_close = prepared["tables"]["close_trade2"][0]

        self.assertEqual(prepared_struct["structure_code"], "S001")
        self.assertTrue(str(prepared_struct["structure_id"]).startswith(self.app.STRUCTURE_INTERNAL_ID_PREFIX))
        self.assertNotEqual(prepared_struct["structure_id"], "S001")
        self.assertEqual(prepared_close["structure_id"], prepared_struct["structure_id"])

        conflicts = self.app.detect_strategy_group_bundle_conflicts(self.conn, prepared)
        self.assertEqual(conflicts.get("structure_id_conflicts"), [])

    def test_build_structure_table_view_shows_display_code_and_keeps_internal_source(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "structure_id": "SID_TABLE_1",
                    "structure_code": "S007",
                    "name": "表格结构",
                    "underlying": "I.TEST",
                    "risk_party": "海证资本",
                    "kind": "ACC",
                    "strategy": "BASIC_RANGE",
                    "strategy_code": "BASIC_RANGE",
                    "start_date": "2026-01-05",
                    "end_date": "2026-01-30",
                    "trade_date": "2026-01-05",
                    "expiry_date": "",
                    "base_qty_per_day": 1000.0,
                    "entry_price": 100.0,
                    "barrier_in": None,
                    "strike_price": 95.0,
                    "premium": None,
                    "barrier_out": 110.0,
                    "knock_out_price": 110.0,
                    "ko_strike_price": None,
                    "multiple": 3.0,
                    "params_json": "{}",
                    "meta_json": "{}",
                }
            ]
        )

        view = self.app.build_structure_table_view(df)
        self.assertEqual(str(view.loc[0, "结构编号"]), "S007")
        self.assertEqual(str(view.loc[0, "__源结构编号"]), "SID_TABLE_1")
        self.assertTrue(str(view.loc[0, "结构"]).startswith("S007-"))

    def test_build_structure_table_view_includes_note_in_label_and_column(self) -> None:
        df = pd.DataFrame(
            [
                {
                    "structure_id": "SID_TABLE_NOTE_1",
                    "structure_code": "S022",
                    "name": "普通累计",
                    "underlying": "I.TEST",
                    "risk_party": "海证资本",
                    "note": "测试期权",
                    "kind": "ACC",
                    "strategy": "BASIC_RANGE",
                    "strategy_code": "BASIC_RANGE",
                    "start_date": "2026-04-19",
                    "end_date": "2026-05-20",
                    "trade_date": "2026-04-19",
                    "expiry_date": "",
                    "base_qty_per_day": 1000.0,
                    "entry_price": 815.5,
                    "barrier_in": None,
                    "strike_price": 815.5,
                    "premium": None,
                    "barrier_out": 835.0,
                    "knock_out_price": 835.0,
                    "ko_strike_price": None,
                    "multiple": 3.0,
                    "params_json": "{}",
                    "meta_json": "{}",
                }
            ]
        )

        view = self.app.build_structure_table_view(df)

        self.assertEqual(str(view.loc[0, "\u5907\u6ce8"]), "测试期权")
        self.assertEqual(str(view.loc[0, "\u98ce\u9669\u5b50"]), "海证资本")
        self.assertIn("海证资本（测试期权）", str(view.loc[0, "\u7ed3\u6784"]))

    def test_build_close_detail_editor_view_uses_display_code_and_hides_empty_roll_column(self) -> None:
        self.insert_structure("SID_CLOSE_1", group_id="G1", structure_code="S014", name="普通累购")
        self.conn.execute(
            """
            INSERT INTO close_trade2(
                close_id, dt, group_id, structure_id, underlying, side, qty, open_price, close_price, pnl, close_category, quick_batch_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "CLOSE_VIEW_1",
                "2026-01-12",
                "G1",
                "SID_CLOSE_1",
                "I.TEST",
                "SELL",
                1200.0,
                None,
                102.0,
                2400.0,
                self.app.STRUCT_CLOSE_CATEGORY,
                "MANUAL_CLOSE_VIEW",
            ),
        )
        self.conn.commit()

        close2_df = pd.read_sql_query("SELECT * FROM close_trade2", self.conn)
        structs_df = pd.read_sql_query("SELECT * FROM structure WHERE group_id='G1'", self.conn)
        view = self.app.build_close_detail_editor_view(
            close2_df,
            group_id="G1",
            main_underlying="",
            structs_df=structs_df,
        )
        hidden_view = self.app.hide_empty_close_detail_editor_columns(view)

        self.assertEqual(str(view.loc[0, "结构编号"]), "S014")
        self.assertTrue(str(view.loc[0, "结构"]).startswith("S014-"))
        self.assertAlmostEqual(float(pd.to_numeric(view["头寸价格"], errors="coerce").iloc[0]), 100.0)
        self.assertNotIn("换月盈亏", hidden_view.columns)

    def test_build_close_detail_editor_view_labels_external_close_without_blank_risk(self) -> None:
        self.conn.execute(
            """
            INSERT INTO close_trade2(
                close_id, dt, group_id, structure_id, underlying, side, qty, open_price, close_price, pnl, close_category, is_external
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                "CLOSE_EXT_1",
                "2026-01-13",
                "G1",
                "外部",
                "I.TEST",
                "平仓",
                1000.0,
                0.0,
                0.0,
                5000.0,
                self.app.EXT_CLOSE_CATEGORY_OPTIONS[0],
                1,
            ),
        )
        self.conn.commit()

        close2_df = pd.read_sql_query("SELECT * FROM close_trade2", self.conn)
        structs_df = pd.read_sql_query("SELECT * FROM structure WHERE group_id='G1'", self.conn)
        view = self.app.build_close_detail_editor_view(
            close2_df,
            group_id="G1",
            main_underlying="",
            structs_df=structs_df,
        )

        self.assertEqual(str(view.loc[0, "结构编号"]), "外部")
        self.assertEqual(str(view.loc[0, "风险子"]), self.app.EXTERNAL_CLOSE_DISPLAY_LABEL)
        self.assertEqual(str(view.loc[0, "结构"]), f"外部-{self.app.EXTERNAL_CLOSE_DISPLAY_LABEL}")

    def test_renumber_group_structure_codes_resets_current_group_without_touching_internal_links(self) -> None:
        self.insert_structure("SID_ACTIVE_1", group_id="G1", structure_code="S051", name="存续一")
        self.insert_structure("SID_ACTIVE_2", group_id="G1", structure_code="S056", name="存续二")
        self.insert_structure("SID_TERM_1", group_id="G1", structure_code="S052", name="终止一")
        self.conn.execute(
            """
            INSERT INTO close_trade2(
                close_id, dt, group_id, structure_id, underlying, side, qty, open_price, close_price, pnl, close_category
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            """,
            ("CLOSE_RENUMBER", "2026-01-20", "G1", "SID_ACTIVE_1", "I.TEST", "SELL", 100.0, 100.0, 105.0, 500.0, "结构平仓"),
        )
        self.conn.commit()

        plan = self.app.renumber_group_structure_codes(
            self.conn,
            "G1",
            terminated_structure_ids={"SID_TERM_1"},
            manage_tx=True,
        )
        code_map = {
            row[0]: row[1]
            for row in self.conn.execute(
                "SELECT structure_id, structure_code FROM structure WHERE group_id='G1'"
            ).fetchall()
        }
        self.assertEqual(code_map["SID_ACTIVE_1"], "S001")
        self.assertEqual(code_map["SID_ACTIVE_2"], "S002")
        self.assertEqual(code_map["SID_TERM_1"], "S003")
        self.assertEqual(
            self.conn.execute(
                "SELECT structure_id FROM close_trade2 WHERE close_id='CLOSE_RENUMBER'"
            ).fetchone()[0],
            "SID_ACTIVE_1",
        )
        changed_cnt = sum(1 for item in plan if item["old_code"] != item["new_code"])
        self.assertEqual(changed_cnt, 3)

    def test_report_item_structure_label_prefers_display_code_over_internal_id(self) -> None:
        label = self.app.report_item_structure_label(
            {
                "structure_id": "SID_12DE6627994D434B9C3CB92079058408",
                "structure_display_id": "S004",
                "name": "普通累沽",
                "side_cn": "空单",
            }
        )
        self.assertEqual(label, "空单-S004-普通累沽")

    def test_apply_monitor_report_display_options_hides_risk_party_only_in_report_rows(self) -> None:
        rows = [
            {
                "structure_id": "SID_S008",
                "structure_display_id": "S008",
                "name": "普通累沽",
                "risk_party": "华泰长城",
                "strategy_code": "BASIC_RANGE",
                "kind": "DEC",
                "entry_price": 776.0,
                "strike_price": 796.0,
                "barrier_price": 757.0,
                "detail_barrier_price": 757.0,
                "melt_price": None,
                "structure": "S008-普通累沽-华泰长城-入场价（776.00）-行权价（796.00）",
                "structure_line1": "S008-普通累沽-华泰长城",
                "structure_line2": "入场价（776.00）-行权价（796.00）",
                "structure_rich_lines": [],
            }
        ]

        visible_rows = self.app.apply_monitor_report_display_options(rows, hide_risk_party_name=False)
        hidden_rows = self.app.apply_monitor_report_display_options(rows, hide_risk_party_name=True)

        self.assertIn("华泰长城", visible_rows[0]["structure_line1"])
        self.assertNotIn("华泰长城", hidden_rows[0]["structure_line1"])
        self.assertEqual(hidden_rows[0]["structure_line1"], "S008-普通累沽")
        self.assertEqual(hidden_rows[0]["structure_line2"], "入场价（776.00）-行权价（796.00）")

    def test_apply_monitor_report_display_options_preserves_existing_price_line_when_hiding_risk_party(self) -> None:
        rows = [
            {
                "structure_id": "SID_S008",
                "structure_display_id": "S008",
                "name": "普通累沽",
                "risk_party": "东海资本",
                "strategy_code": "BASIC_RANGE",
                "kind": "DEC",
                "entry_price": 761.0,
                "strike_price": 791.0,
                "barrier_price": 791.0,
                "structure": "S008-普通累沽-东海资本-障碍价（751.0）-入场价（761.0）-行权价（791.0）",
                "structure_line1": "S008-普通累沽-东海资本",
                "structure_line2": "障碍价（751.0）-入场价（761.0）-行权价（791.0）",
                "structure_rich_lines": [
                    [{"text": "S008-普通累沽-东海资本", "weight": "bold"}],
                    [
                        {"text": "障碍价（751.0）-入场价（761.0）-", "weight": "normal"},
                        {"text": "行权价（791.0）", "weight": "bold"},
                    ],
                ],
            }
        ]

        hidden_rows = self.app.apply_monitor_report_display_options(rows, hide_risk_party_name=True)

        self.assertEqual(hidden_rows[0]["structure_line1"], "S008-普通累沽")
        self.assertEqual(hidden_rows[0]["structure_line2"], "障碍价（751.0）-入场价（761.0）-行权价（791.0）")
        self.assertEqual(hidden_rows[0]["structure_rich_lines"][0][0]["text"], "S008-普通累沽")
        self.assertIn("障碍价（751.0）", hidden_rows[0]["structure"])
        self.assertNotIn("东海资本", hidden_rows[0]["structure"])

    def test_finalize_monitor_overview_frame_maps_display_code_and_keeps_finished_days_zero(self) -> None:
        overview = pd.DataFrame(
            [
                {
                    "__内部结构ID": "SID_B",
                    "结构ID": "SID_B",
                    "结构": "S002-结构B",
                    "风险子": "海证资本",
                    "品种": "I.TEST",
                    "方向": "看跌",
                    "买卖方向": "卖出",
                    "状态": "震荡",
                    "结构规模": "",
                    "阶段": "",
                    "当前票息(%)": None,
                    "当前敲出线": None,
                    "当前浮盈亏": 0.0,
                    "已敲入标记": "",
                    "首次敲入日": "",
                    "折价触发日": "",
                    "转期货数量": None,
                    "转期货开仓价": None,
                    "当前期货浮盈亏": None,
                    "已生成": 0.0,
                    "剩余最大": -12000.0,
                    "敞口上界": -12000.0,
                    "剩余交易日": 9,
                    "结构到期时间": "2026-04-17",
                },
                {
                    "__内部结构ID": "SID_A",
                    "结构ID": "SID_A",
                    "结构": "S001-结构A",
                    "风险子": "海证资本",
                    "品种": "I.TEST",
                    "方向": "看涨",
                    "买卖方向": "买入",
                    "状态": "已手动终结",
                    "结构规模": "",
                    "阶段": "",
                    "当前票息(%)": None,
                    "当前敲出线": None,
                    "当前浮盈亏": 0.0,
                    "已敲入标记": "",
                    "首次敲入日": "",
                    "折价触发日": "",
                    "转期货数量": None,
                    "转期货开仓价": None,
                    "当前期货浮盈亏": None,
                    "已生成": 0.0,
                    "剩余最大": 8000.0,
                    "敞口上界": 8000.0,
                    "剩余交易日": 5,
                    "结构到期时间": "2026-04-10",
                },
            ]
        )

        final_df = self.app.finalize_monitor_overview_frame(
            overview,
            structure_code_map={"SID_A": "S001", "SID_B": "S002"},
            finished_sid_set={"SID_B"},
        )

        self.assertIn("__内部结构ID", final_df.columns)
        self.assertEqual(final_df["结构ID"].astype(str).tolist(), ["S002", "S001"])
        row_map = {str(row["结构ID"]): row for _, row in final_df.iterrows()}
        self.assertEqual(row_map["S002"]["__内部结构ID"], "SID_B")
        self.assertEqual(row_map["S001"]["__内部结构ID"], "SID_A")
        self.assertEqual(int(row_map["S002"]["剩余交易日"]), 0)
        self.assertEqual(int(row_map["S001"]["剩余交易日"]), 0)
        self.assertEqual(float(row_map["S002"]["剩余最大"]), 0.0)
        self.assertEqual(float(row_map["S001"]["剩余最大"]), 0.0)

    def test_special_page_candidate_option_label_uses_display_code_without_legacy_prefix(self) -> None:
        label = self.app.special_page_candidate_option_label(
            {
                "structure_id": "S079",
                "structure_display_id": "S014",
                "detail_label": "S014-普通累购-东海资本-入场价（812.50）-行权价（787.50）",
                "status_cn": "震荡（1倍）",
                "remaining_days": 13,
            }
        )
        self.assertTrue(label.startswith("S014-普通累购-东海资本"))
        self.assertNotIn("S079 |", label)
        self.assertIn("震荡（1倍）", label)
        self.assertIn("13", label)
        self.assertIn("\u4ea4\u6613\u65e5", label)

    def test_special_snapshot_range_text_uses_trading_day_wording(self) -> None:
        text = self.app.special_snapshot_range_text(
            {
                "start_date": "2026-01-02",
                "end_date": "2026-01-10",
                "remaining_trading_days": 5,
            }
        )
        self.assertIn("5", text)
        self.assertIn("\u4ea4\u6613\u65e5", text)

    def test_special_frozen_reason_cn_uses_trading_day_wording(self) -> None:
        text = self.app.special_frozen_reason_to_cn("remaining_days_exhausted")
        self.assertIn("\u4ea4\u6613\u65e5", text)

    def test_precise_hedge_design_day_summary_notes_use_trading_day_wording(self) -> None:
        summary = self.app.precise_hedge_build_design_day_summary(
            {
                "path_len": 6,
                "sample_df": pd.DataFrame(
                    [
                        {
                            "oscillation_days": 2,
                            "knockin_days": 1,
                            "knockout_days": 3,
                            "observed_days": 6,
                            "first_ki_step": 2,
                            "first_ko_step": 4,
                        }
                    ]
                ),
            },
            template={"ko_terminate": True},
        )
        notes = "\n".join(summary.get("notes", []))
        self.assertIn("\u4ea4\u6613\u65e5", notes)

    def test_probexp_and_winrate_candidates_sort_by_display_code(self) -> None:
        self.insert_structure("S099", group_id="G1", structure_code="S002", name="后建先排")
        self.insert_structure("S001", group_id="G1", structure_code="S010", name="先建后排")
        self.conn.commit()

        structs_df = pd.read_sql_query("SELECT * FROM structure", self.conn)
        empty_struct_asof = pd.DataFrame(columns=["structure_id", "date"])
        empty_bounds = pd.DataFrame(columns=["structure_id", "level", "remaining_trading_days"])
        empty_prices = pd.DataFrame(columns=["dt", "underlying", "settle"])
        empty_closes = pd.DataFrame(columns=["group_id", "structure_id", "dt"])

        probexp_rows = self.app.probexp_build_structure_candidates(
            structs_df=structs_df,
            struct_asof=empty_struct_asof,
            bounds_asof=empty_bounds,
            prices_df=empty_prices,
            close2_df=empty_closes,
            rep_gid="G1",
            rep_date="2026-01-10",
            rep_und="全部",
            rep_und_all=True,
        )
        winrate_rows = self.app.winrate_build_structure_candidates(
            structs_df,
            rep_gid="G1",
            rep_date="2026-01-10",
        )

        self.assertEqual([row["structure_display_id"] for row in probexp_rows], ["S002", "S010"])
        self.assertEqual([row["structure_display_id"] for row in winrate_rows], ["S002", "S010"])
        self.assertTrue(str(probexp_rows[0]["label"]).startswith("S002-"))
        self.assertTrue(str(winrate_rows[0]["detail_label"]).startswith("S002-"))

    def test_special_candidates_include_vanilla_only_on_probexp_opt_in(self) -> None:
        self.app._SPECIAL_PAGE_UI_MEMO_CACHE.clear()
        self.insert_structure("SID_ACC", group_id="G1", structure_code="S001", name="Accumulator")
        self.insert_structure(
            "SID_VANILLA",
            group_id="G1",
            structure_code="S002",
            name="Vanilla",
            kind="DEC",
            strategy_code=self.app.VANILLA_OPTION_CODE,
        )
        self.conn.execute(
            """
            UPDATE structure
            SET option_type=?, side=?, premium=?, base_qty_per_day=?, barrier_out=NULL, knock_out_price=NULL, multiple=0
            WHERE structure_id=?
            """,
            ("call", "sell", 5.0, 50000.0, "SID_VANILLA"),
        )
        self.conn.commit()

        structs_df = pd.read_sql_query("SELECT * FROM structure", self.conn)
        empty_struct_asof = pd.DataFrame(columns=["structure_id", "date"])
        empty_bounds = pd.DataFrame(columns=["structure_id", "level", "remaining_trading_days"])
        empty_prices = pd.DataFrame(columns=["dt", "underlying", "settle"])
        empty_closes = pd.DataFrame(columns=["group_id", "structure_id", "dt"])

        probexp_default_rows = self.app.probexp_build_structure_candidates(
            structs_df=structs_df,
            struct_asof=empty_struct_asof,
            bounds_asof=empty_bounds,
            prices_df=empty_prices,
            close2_df=empty_closes,
            rep_gid="G1",
            rep_date="2026-01-10",
            rep_und="鍏ㄩ儴",
            rep_und_all=True,
        )
        probexp_with_vanilla_rows = self.app.probexp_build_structure_candidates(
            structs_df=structs_df,
            struct_asof=empty_struct_asof,
            bounds_asof=empty_bounds,
            prices_df=empty_prices,
            close2_df=empty_closes,
            rep_gid="G1",
            rep_date="2026-01-10",
            rep_und="鍏ㄩ儴",
            rep_und_all=True,
            include_vanilla=True,
        )
        winrate_rows = self.app.winrate_build_structure_candidates(
            structs_df,
            rep_gid="G1",
            rep_date="2026-01-10",
            struct_asof=empty_struct_asof,
            bounds_asof=empty_bounds,
            prices_df=empty_prices,
            close2_df=empty_closes,
        )

        self.assertEqual([row["structure_id"] for row in probexp_default_rows], ["SID_ACC"])
        self.assertEqual(
            [row["structure_id"] for row in probexp_with_vanilla_rows],
            ["SID_ACC", "SID_VANILLA"],
        )
        self.assertEqual([row["structure_id"] for row in winrate_rows], ["SID_ACC", "SID_VANILLA"])

    def test_winrate_candidates_prefer_ledger_remaining_days_for_dropdown_label(self) -> None:
        self.insert_structure(
            "SID_LEDGER",
            group_id="G1",
            structure_code="S001",
            name="Ledger scoped",
            kind="DEC",
            strategy_code="SAFETY_AIRBAG",
        )
        self.conn.execute(
            "UPDATE structure SET start_date=?, end_date=? WHERE structure_id=?",
            ("2026-01-02", "2026-01-06", "SID_LEDGER"),
        )
        self.conn.commit()

        structs_df = pd.read_sql_query("SELECT * FROM structure", self.conn)
        bounds_asof = pd.DataFrame(
            [
                {
                    "structure_id": "SID_LEDGER",
                    "level": "STRUCTURE",
                    "remaining_trading_days": 8,
                }
            ]
        )
        rows = self.app.winrate_build_structure_candidates(
            structs_df,
            rep_gid="G1",
            rep_date="2026-01-05",
            struct_asof=pd.DataFrame(columns=["structure_id", "date"]),
            bounds_asof=bounds_asof,
            prices_df=pd.DataFrame(columns=["dt", "underlying", "settle"]),
            close2_df=pd.DataFrame(columns=["group_id", "structure_id", "dt", "close_category"]),
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["remaining_trading_days"]), 8)
        label = self.app.special_page_candidate_option_label(rows[0])
        self.assertIn("8", label)
        self.assertIn("\u4ea4\u6613\u65e5", label)

    def test_winrate_candidates_respect_manual_close_status_and_remaining_days(self) -> None:
        self.insert_structure(
            "SID_MANUAL",
            group_id="G1",
            structure_code="S001",
            name="Manual closed",
            kind="DEC",
            strategy_code="SAFETY_AIRBAG",
        )
        self.conn.commit()

        structs_df = pd.read_sql_query("SELECT * FROM structure", self.conn)
        close2_df = pd.DataFrame(
            [
                {
                    "group_id": "G1",
                    "structure_id": "SID_MANUAL",
                    "dt": "2026-01-10",
                    "close_category": self.app.MANUAL_STRUCT_CLOSE_CATEGORY,
                }
            ]
        )
        rows = self.app.winrate_build_structure_candidates(
            structs_df,
            rep_gid="G1",
            rep_date="2026-01-15",
            struct_asof=pd.DataFrame(columns=["structure_id", "date"]),
            bounds_asof=pd.DataFrame(columns=["structure_id", "level", "remaining_trading_days"]),
            prices_df=pd.DataFrame(columns=["dt", "underlying", "settle"]),
            close2_df=close2_df,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(int(rows[0]["remaining_trading_days"]), 0)
        self.assertEqual(str(rows[0]["status_cn"]), "已手动终结")
        label = self.app.special_page_candidate_option_label(rows[0])
        self.assertIn("已手动终结", label)
        self.assertIn("0", label)
        self.assertIn("\u4ea4\u6613\u65e5", label)


if __name__ == "__main__":
    unittest.main()
