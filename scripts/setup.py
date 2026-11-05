"""Create the project environment in `.venv/` and install the pinned dependencies.

Usage (from the repository root, or through `npm run setup`):

    python3 scripts/setup.py

Steps: create `.venv/` if it is missing, install requirements.txt and requirements-dev.txt
with --require-hashes, and install the Chromium build of Playwright. Only the Python
standard library is used. Python 3.11 or newer is required. Nothing is installed in the
operating system; the environment stays inside `.venv/`.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"
REQUIREMENTS = ["requirements.txt", "requirements-dev.txt"]
MIN_VERSION = (3, 11)


def run(command: list[str], what: str) -> None:
    """Run a step; exit with its status and a message if it fails."""
    print(f"==> {what}", flush=True)
    result = subprocess.run(command, cwd=ROOT)
    if result.returncode != 0:
        print(f"error: {what} failed with exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def main() -> int:
    if sys.version_info < MIN_VERSION:
        found = ".".join(str(part) for part in sys.version_info[:3])
        print(f"error: Python {MIN_VERSION[0]}.{MIN_VERSION[1]} or newer is required, found {found}", file=sys.stderr)
        return 1

    if not VENV_PYTHON.is_file():
        run([sys.executable, "-m", "venv", str(VENV_DIR)], f"create {VENV_DIR}")
    else:
        print(f"using the existing environment at {VENV_DIR}", flush=True)

    for name in REQUIREMENTS:
        run(
            [str(VENV_PYTHON), "-m", "pip", "install", "--require-hashes", "-r", name],
            f"install {name}",
        )

    run([str(VENV_PYTHON), "-m", "playwright", "install", "chromium"], "install the Chromium build of Playwright")

    print("setup finished: run `npm run dev` to start the development server", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
