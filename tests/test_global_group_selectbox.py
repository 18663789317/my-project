import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("app_global_group_selectbox_test_mod", APP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class GlobalGroupSelectboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = load_app()

    def tearDown(self) -> None:
        self.app.st.session_state.pop(self.app.GLOBAL_GROUP_SELECT_KEY, None)
        self.app.st.session_state.pop(self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY, None)

    def test_ensure_global_group_selection_syncs_widget_state(self) -> None:
        self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_KEY] = "G003"
        self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY] = "G001"

        current_gid = self.app.ensure_global_group_selection(["G001", "G003", "G005"])

        self.assertEqual(current_gid, "G003")
        self.assertEqual(self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_KEY], "G003")
        self.assertEqual(self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY], "G003")

    def test_ensure_global_group_selection_can_reset_to_preferred_gid(self) -> None:
        self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_KEY] = "G003"
        self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY] = "G003"

        current_gid = self.app.ensure_global_group_selection(
            ["G001", "G003", "G005"],
            preferred_gid="G001",
            reset_to_preferred=True,
        )

        self.assertEqual(current_gid, "G001")
        self.assertEqual(self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_KEY], "G001")
        self.assertEqual(self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY], "G001")

    def test_render_global_group_selectbox_uses_widget_key_and_syncs_on_change(self) -> None:
        self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_KEY] = "G001"
        self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY] = "G001"
        captured_kwargs: dict = {}

        def fake_selectbox(label, options, **kwargs):
            captured_kwargs["label"] = label
            captured_kwargs["options"] = list(options)
            captured_kwargs["kwargs"] = dict(kwargs)
            widget_key = str(kwargs.get("key"))
            self.app.st.session_state[widget_key] = "G002"
            on_change = kwargs.get("on_change")
            if callable(on_change):
                on_change()
            return self.app.st.session_state[widget_key]

        with mock.patch.object(self.app.st, "selectbox", side_effect=fake_selectbox):
            gid = self.app.render_global_group_selectbox(
                "策略组",
                ["G001", "G002"],
                group_name_map={"G001": "一组", "G002": "二组"},
            )

        self.assertEqual(gid, "G002")
        self.assertEqual(self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_KEY], "G002")
        self.assertEqual(self.app.st.session_state[self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY], "G002")
        self.assertEqual(captured_kwargs["label"], "策略组")
        self.assertEqual(captured_kwargs["options"], ["G001", "G002"])
        self.assertEqual(captured_kwargs["kwargs"].get("key"), self.app.GLOBAL_GROUP_SELECT_WIDGET_KEY)
        self.assertNotIn("index", captured_kwargs["kwargs"])
        self.assertTrue(callable(captured_kwargs["kwargs"].get("on_change")))


if __name__ == "__main__":
    unittest.main()
