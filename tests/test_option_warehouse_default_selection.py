import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_option_warehouse_default_selection_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OptionWarehouseDefaultSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_new_page_entry_defaults_to_current_visible_rows(self) -> None:
        selected_ids, should_apply = self.app.resolve_option_warehouse_default_selection_on_page_enter(
            ["S003", "S001", "S003", "", None],
            ["S999"],
            entry_token="entry-1",
            applied_token="",
        )

        self.assertTrue(should_apply)
        self.assertEqual(selected_ids, ["S003", "S001"])

    def test_same_page_entry_token_does_not_override_manual_selection(self) -> None:
        selected_ids, should_apply = self.app.resolve_option_warehouse_default_selection_on_page_enter(
            ["S003", "S001"],
            ["S001"],
            entry_token="entry-1",
            applied_token="entry-1",
        )

        self.assertFalse(should_apply)
        self.assertEqual(selected_ids, ["S001"])

    def test_missing_entry_token_keeps_existing_selection(self) -> None:
        selected_ids, should_apply = self.app.resolve_option_warehouse_default_selection_on_page_enter(
            ["S003", "S001"],
            ["S001", "S002"],
            entry_token="",
            applied_token="",
        )

        self.assertFalse(should_apply)
        self.assertEqual(selected_ids, ["S001", "S002"])

    def test_remove_visible_selection_only_clears_current_filtered_rows(self) -> None:
        selected_ids = self.app.remove_option_warehouse_visible_selection(
            ["S999", "S001", "S002", "S001", "", None, "null"],
            ["S001", "S002", "S003", "", None],
        )

        self.assertEqual(selected_ids, ["S999"])
