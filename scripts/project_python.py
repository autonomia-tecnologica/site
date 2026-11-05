"""Run Python with the project environment, the interpreter inside `.venv/`.

Usage (from the repository root):

    python3 scripts/project_python.py scripts/lint/check_html_classes.py
    python3 scripts/project_python.py -m unittest discover -s tests/build -t tests/build

Scripts that need the project's packages call `relaunch_in_venv()` before importing them,
so they also work when started with a plain `python3`. Only the Python standard library is
used here, so this module works before the environment exists. If `.venv/` is missing, the
error asks to run `npm run setup`.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
SETUP_HINT = "run `npm run setup` to create it"


def venv_python() -> Path:
    """Path of the interpreter in `.venv/`; exits with a clear message if it is missing."""
    if not VENV_PYTHON.is_file():
        print(f"error: the project environment is missing ({VENV_DIR}); {SETUP_HINT}", file=sys.stderr)
        sys.exit(1)
    return VENV_PYTHON


def in_project_venv() -> bool:
    """True when this process runs with the interpreter of `.venv/`."""
    return Path(sys.prefix).resolve() == VENV_DIR.resolve()


def relaunch_in_venv() -> None:
    """Replace this process with the same script run by the `.venv/` interpreter.

    Does nothing when it already runs there. Exits with a clear message if `.venv/` is missing.
    """
    if in_project_venv():
        return
    python = venv_python()
    os.execv(str(python), [str(python), *sys.argv])


def main(argv: list[str]) -> int:
    """Run the given arguments (a script path or `-m module`) with the `.venv/` interpreter."""
    if not argv:
        print("usage: python3 scripts/project_python.py <script.py | -m module> [args...]", file=sys.stderr)
        return 2
    python = venv_python()
    return subprocess.run([str(python), *argv], cwd=ROOT).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
