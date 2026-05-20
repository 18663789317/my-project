from __future__ import annotations

import os
import socket
import sys

from streamlit.web import cli as stcli


def _base_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _is_port_available(port: int, host: str = "127.0.0.1") -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            sock.close()
        except Exception:
            pass


def _pick_port(preferred: int = 8501, host: str = "127.0.0.1", max_tries: int = 30) -> int:
    start_port = max(int(preferred), 1024)
    for port in range(start_port, start_port + max(int(max_tries), 1)):
        if _is_port_available(port, host=host):
            return port
    return start_port


def main() -> int:
    root = _base_dir()
    os.chdir(root)
    app_path = os.path.join(root, "app.py")
    if not os.path.exists(app_path):
        print(f"[ERROR] app.py not found: {app_path}")
        return 2
    host = "127.0.0.1"
    port = _pick_port(preferred=8501, host=host, max_tries=40)
    print(f"[INFO] Launching app.py on http://{host}:{port}")

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--global.developmentMode=false",
        "--server.fileWatcherType=none",
        f"--server.port={port}",
        f"--server.address={host}",
        "--server.headless=false",
        "--server.runOnSave=false",
        "--browser.gatherUsageStats=false",
    ]
    return stcli.main()


if __name__ == "__main__":
    raise SystemExit(main())
