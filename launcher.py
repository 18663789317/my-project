from __future__ import annotations

import os
import sys

from streamlit.web import cli as stcli


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    root = _base_dir()
    os.chdir(root)
    app_path = os.path.join(root, "app.py")
    if not os.path.exists(app_path):
        print(f"[ERROR] app.py not found: {app_path}")
        return 2

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.port=8501",
        "--server.address=127.0.0.1",
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
    ]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
