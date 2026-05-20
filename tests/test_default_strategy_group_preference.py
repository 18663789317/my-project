import importlib.util
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_default_strategy_group_pref_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class DefaultStrategyGroupPreferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.executemany(
            "INSERT INTO strategy_group(group_id, group_name, underlying) VALUES (?,?,?)",
            [
                ("G001", "Group 1", "I.TEST"),
                ("G002", "Group 2", "I.TEST"),
                ("G003", "Group 3", "I.TEST"),
            ],
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_resolve_strategy_group_default_prefers_saved_gid_when_valid(self) -> None:
        saved = self.app.save_default_strategy_group_id(self.conn, "G002")

        resolved = self.app.resolve_strategy_group_default(
            self.conn,
            ["G001", "G002", "G003"],
            fallback="G001",
        )

        self.assertTrue(saved)
        self.assertEqual(resolved, "G002")
        self.assertEqual(self.app.get_saved_default_strategy_group_id(self.conn), "G002")

    def test_resolve_strategy_group_default_falls_back_when_saved_gid_is_invalid(self) -> None:
        self.app.save_default_strategy_group_id(self.conn, "G999")

        resolved = self.app.resolve_strategy_group_default(
            self.conn,
            ["G001", "G002", "G003"],
            fallback="G003",
        )

        self.assertEqual(resolved, "G003")

    def test_delete_group_pref_kv_rows_clears_saved_default_gid(self) -> None:
        self.app.save_default_strategy_group_id(self.conn, "G002")
        self.conn.execute(
            "INSERT OR REPLACE INTO app_kv(k, v, updated_at) VALUES (?,?,datetime('now'))",
            (self.app._price_auto_underlyings_pref_key("G002"), "[]"),
        )
        self.conn.commit()

        pref_keys = self.app._strategy_group_pref_kv_keys(self.conn, ["G002"])
        deleted = self.app._delete_group_pref_kv_rows(self.conn, ["G002"])
        remaining_default = self.conn.execute(
            "SELECT COUNT(1) FROM app_kv WHERE k=?",
            (self.app.DEFAULT_STRATEGY_GROUP_KV_KEY,),
        ).fetchone()

        self.assertIn(self.app.DEFAULT_STRATEGY_GROUP_KV_KEY, pref_keys)
        self.assertEqual(deleted, 2)
        self.assertEqual(self.app.get_saved_default_strategy_group_id(self.conn), "")
        self.assertEqual(int(remaining_default[0] if remaining_default else 0), 0)


if __name__ == "__main__":
    unittest.main()
