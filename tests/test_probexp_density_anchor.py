import ast
import copy
import pathlib
import unittest
from typing import Any, Dict, Optional, Tuple

import numpy as np


APP_PATH = pathlib.Path(__file__).resolve().parents[1] / "app.py"

TARGET_SYMBOLS = {
    "np_trapezoid_compat",
    "probexp_find_density_region_anchor",
}


def load_symbols() -> Dict[str, Any]:
    source = APP_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(source, filename=str(APP_PATH))
    body = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in TARGET_SYMBOLS:
            body.append(copy.deepcopy(node))
    module = ast.Module(body=body, type_ignores=[])
    ast.fix_missing_locations(module)
    env: Dict[str, Any] = {
        "__builtins__": __builtins__,
        "Any": Any,
        "Optional": Optional,
        "Tuple": Tuple,
        "np": np,
    }
    exec(compile(module, str(APP_PATH), "exec"), env)
    return env


class ProbexpDensityAnchorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.ns = load_symbols()

    def test_np_trapezoid_compat_falls_back_cleanly(self) -> None:
        fn = self.ns["np_trapezoid_compat"]
        x = np.asarray([0.0, 1.0, 2.0], dtype=float)
        y = np.asarray([0.0, 1.0, 0.0], dtype=float)
        self.assertAlmostEqual(fn(y, x), float(np.trapz(y, x)))

    def test_probexp_find_density_region_anchor_works_without_numpy_trapezoid(self) -> None:
        fn = self.ns["probexp_find_density_region_anchor"]
        x = np.asarray([0.0, 1.0, 2.0], dtype=float)
        y = np.asarray([0.0, 1.0, 0.0], dtype=float)
        mask = np.asarray([True, True, True], dtype=bool)
        anchor = fn(x, y, mask, y_upper=1.0)
        self.assertIsNotNone(anchor)
        x_anchor, y_anchor = anchor or (None, None)
        self.assertAlmostEqual(float(x_anchor), 1.0, places=6)
        self.assertGreater(float(y_anchor), 0.0)
        self.assertLessEqual(float(y_anchor), 0.62)


if __name__ == "__main__":
    unittest.main()
