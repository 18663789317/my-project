import pathlib
import unittest


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"


class OptionWarehouseUnderlyingFilterRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = APP_PATH.read_text(encoding="utf-8-sig")

    def test_structure_table_no_longer_renders_secondary_underlying_filter(self) -> None:
        self.assertIn(
            'with st.popover(build_option_warehouse_quick_filter_button_text(warehouse_underlying_pick))',
            self.source,
        )
        self.assertNotIn('wh_filter_und_key = f"wh_struct_und_{gid}"', self.source)
        self.assertNotIn('with st.popover(build_option_warehouse_quick_filter_button_text(und_sel))', self.source)


if __name__ == "__main__":
    unittest.main()
