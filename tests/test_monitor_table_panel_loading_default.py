import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_monitor_table_panel_loading_default_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MonitorTablePanelLoadingDefaultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def test_detail_panels_default_to_loaded_when_state_missing(self) -> None:
        self.assertTrue(self.app.resolve_monitor_table_panels_loaded({}))

    def test_detail_panels_respect_explicitly_collapsed_state(self) -> None:
        self.assertFalse(
            self.app.resolve_monitor_table_panels_loaded({"_monitor_table_panels_loaded": False})
        )

    def test_detail_panels_respect_explicitly_expanded_state(self) -> None:
        self.assertTrue(
            self.app.resolve_monitor_table_panels_loaded({"_monitor_table_panels_loaded": True})
        )


if __name__ == "__main__":
    unittest.main()
