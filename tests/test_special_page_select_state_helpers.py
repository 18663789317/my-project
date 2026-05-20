import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_special_page_select_state_helpers_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SpecialPageSelectStateHelperTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def tearDown(self) -> None:
        for key in ("page_gid", "page_gid_display", "page_date"):
            self.app.st.session_state.pop(key, None)

    def test_render_labeled_group_selectbox_applies_pending_widget_choice_before_render(self) -> None:
        labels = {"G001": "G001 - One", "G002": "G002 - Two"}
        self.app.st.session_state["page_gid"] = "G001"
        self.app.st.session_state["page_gid_display"] = "G002 - Two"

        def fake_selectbox(label, options, **kwargs):
            self.assertEqual(label, "策略组")
            self.assertEqual(list(options), ["G001 - One", "G002 - Two"])
            self.assertEqual(kwargs.get("key"), "page_gid_display")
            return self.app.st.session_state["page_gid_display"]

        with mock.patch.object(self.app.st, "selectbox", side_effect=fake_selectbox):
            resolved = self.app.render_labeled_group_selectbox(
                "策略组",
                "page_gid",
                "page_gid_display",
                ["G001", "G002"],
                labels,
                default_gid="G001",
            )

        self.assertEqual(resolved, "G002")
        self.assertEqual(self.app.st.session_state["page_gid"], "G002")
        self.assertEqual(self.app.st.session_state["page_gid_display"], "G002 - Two")

    def test_render_labeled_group_selectbox_reset_to_default_ignores_stale_widget_choice(self) -> None:
        labels = {"G001": "G001 - One", "G002": "G002 - Two"}
        self.app.st.session_state["page_gid"] = "G002"
        self.app.st.session_state["page_gid_display"] = "G002 - Two"

        with mock.patch.object(
            self.app.st,
            "selectbox",
            side_effect=lambda _label, _options, **_kwargs: self.app.st.session_state["page_gid_display"],
        ):
            resolved = self.app.render_labeled_group_selectbox(
                "策略组",
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

    def test_sync_selectbox_choice_state_replaces_invalid_selection(self) -> None:
        self.app.st.session_state["page_date"] = "2026-04-21"

        resolved = self.app.sync_selectbox_choice_state(
            "page_date",
            ["2026-04-22", "2026-04-23"],
            default_value="2026-04-23",
        )

        self.assertEqual(resolved, "2026-04-23")
        self.assertEqual(self.app.st.session_state["page_date"], "2026-04-23")

    def test_sync_selectbox_choice_state_can_reset_to_latest_default(self) -> None:
        self.app.st.session_state["page_date"] = "2026-04-22"

        resolved = self.app.sync_selectbox_choice_state(
            "page_date",
            ["2026-04-22", "2026-04-23"],
            default_value="2026-04-23",
            reset_to_default=True,
        )

        self.assertEqual(resolved, "2026-04-23")
        self.assertEqual(self.app.st.session_state["page_date"], "2026-04-23")


if __name__ == "__main__":
    unittest.main()
