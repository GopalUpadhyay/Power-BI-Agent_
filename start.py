"""Single-command project launcher.

Usage:
  python start.py
  python start.py ui --port 8501
  python start.py cli -- --demo
"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
from pathlib import Path


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _find_free_port(start_port: int, max_tries: int = 20) -> int:
    candidate = start_port
    for _ in range(max_tries):
        if _port_available(candidate):
            return candidate
        candidate += 1
    return start_port


def _run_ui(port: int) -> int:
    project_root = Path(__file__).resolve().parent
    selected_port = _find_free_port(port)
    if selected_port != port:
        print(f"Port {port} is busy. Using port {selected_port}.")
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(project_root / "run_ui.py"),
        "--server.port",
        str(selected_port),
    ]
    return subprocess.call(cmd, cwd=str(project_root))


def _run_cli(cli_args: list[str]) -> int:
    project_root = Path(__file__).resolve().parent
    cmd = [sys.executable, str(project_root / "run_app.py"), *cli_args]
    return subprocess.call(cmd, cwd=str(project_root))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run AI_Bot_MAQ with one command."
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="ui",
        choices=["ui", "cli"],
        help="Launch mode: ui (default) or cli",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8501,
        help="Port for UI mode (default: 8501)",
    )
    parsed, extra_args = parser.parse_known_args()

    if parsed.mode == "ui":
        return _run_ui(parsed.port)

    cli_args = extra_args
    if cli_args and cli_args[0] == "--":
        cli_args = cli_args[1:]
    return _run_cli(cli_args)


if __name__ == "__main__":
    raise SystemExit(main())
