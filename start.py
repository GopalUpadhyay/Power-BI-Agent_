"""Single-command project launcher.

Usage:
  python start.py
  python start.py ui --port 8501
  python start.py cli -- --demo
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run_ui(port: int) -> int:
    project_root = Path(__file__).resolve().parent
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(project_root / "run_ui.py"),
        "--server.port",
        str(port),
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
