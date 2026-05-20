import importlib.util
import pathlib
import sqlite3
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_strategy_group_visibility_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StrategyGroupVisibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.app.init_db(self.conn)
        self.conn.executemany(
            "INSERT INTO strategy_group(group_id, group_name, underlying, is_hidden) VALUES (?,?,?,?)",
            [
                ("G001", "Group 1", "I.TEST", 0),
                ("G002", "Group 2", "I.TEST", 1),
                ("G003", "Group 3", "I.TEST", None),
            ],
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_fetch_visible_groups_excludes_hidden_rows(self) -> None:
        visible = self.app.fetch_visible_groups(self.conn)

        self.assertEqual(visible["group_id"].astype(str).tolist(), ["G001", "G003"])

    def test_batch_save_can_hide_and_restore_groups(self) -> None:
        save_result = self.app.save_existing_strategy_group_rows(
            self.conn,
            [
                {"group_id": "G001", "group_name": "Group 1", "underlying": "I.TEST", "is_hidden": 1},
                {"group_id": "G002", "group_name": "Group 2", "underlying": "I.TEST", "is_hidden": 0},
            ],
        )
        visible = self.app.fetch_visible_groups(self.conn)

        self.assertTrue(save_result["ok"])
        self.assertEqual(visible["group_id"].astype(str).tolist(), ["G002", "G003"])


if __name__ == "__main__":
    unittest.main()
