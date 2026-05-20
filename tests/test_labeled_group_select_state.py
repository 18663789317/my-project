import importlib.util
import pathlib
import sys
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_labeled_group_select_state_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class LabeledGroupSelectStateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def tearDown(self) -> None:
        self.app.st.session_state.pop("page_gid", None)
        self.app.st.session_state.pop("page_gid_display", None)

    def test_widget_choice_updates_hidden_gid(self) -> None:
        labels = {"G001": "G001 - One", "G002": "G002 - Two"}
        self.app.st.session_state["page_gid"] = "G001"
        self.app.st.session_state["page_gid_display"] = "G002 - Two"

        resolved = self.app.sync_labeled_group_selectbox_state(
            "page_gid",
            "page_gid_display",
            ["G001", "G002"],
            labels,
            default_gid="G001",
        )

        self.assertEqual(resolved, "G002")
        self.assertEqual(self.app.st.session_state["page_gid"], "G002")
        self.assertEqual(self.app.st.session_state["page_gid_display"], "G002 - Two")

    def test_reset_to_default_ignores_stale_widget_choice(self) -> None:
        labels = {"G001": "G001 - One", "G002": "G002 - Two"}
        self.app.st.session_state["page_gid"] = "G001"
        self.app.st.session_state["page_gid_display"] = "G002 - Two"

        resolved = self.app.sync_labeled_group_selectbox_state(
            "page_gid",
            "page_gid_display",
            ["G001", "G002"],
            labels,
            default_gid="G001",
            reset_to_default=True,
        )

        self.assertEqual(resolved, "G001")
        self.assertEqual(self.app.st.session_state["page_gid"], "G001")
        self.assertEqual(self.app.st.session_state["page_gid_display"], "G001 - One")


if __name__ == "__main__":
    unittest.main()
