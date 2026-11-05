"""Development server: builds the site, serves dist/ and rebuilds when the sources change.

Usage (from the repository root, or through `npm run dev`):

    python3 scripts/dev.py              # serves http://localhost:8000
    python3 scripts/dev.py --port 8080

Only the Python standard library is used here. Every build runs as a separate process
with the interpreter of `.venv/` (`.venv/bin/python -m src.build`), so each rebuild loads
the current code. Without `.venv/`, the server does not start: run `npm run setup` first.
The build reads SITE_URL and SITE_PRIVATE_DIR from the environment, as it does everywhere
else. Stop with Ctrl+C.
"""

import argparse
import functools
import http.server
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from project_python import venv_python

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
WATCHED_DIRS = ["content", "templates", "src", "i18n"]
IGNORED_DIR_NAMES = {"__pycache__"}
IGNORED_SUFFIXES = (".pyc",)
DEFAULT_PORT = 8000
POLL_SECONDS = 0.5

FileState = dict[str, tuple[int, int]]


def snapshot() -> FileState:
    """Modification time and size of every watched file, keyed by path.

    Bytecode is skipped: the build writes it, and watching it would rebuild forever.
    """
    files: FileState = {}
    for folder in WATCHED_DIRS:
        for dirpath, dirnames, filenames in os.walk(ROOT / folder):
            dirnames[:] = [name for name in dirnames if name not in IGNORED_DIR_NAMES]
            for name in filenames:
                if name.endswith(IGNORED_SUFFIXES):
                    continue
                path = Path(dirpath) / name
                try:
                    stat = path.stat()
                except OSError:  # removed after the listing
                    continue
                files[str(path)] = (stat.st_mtime_ns, stat.st_size)
    return files


def build(python: Path) -> None:
    """Run the development build as a process with `python`; its output goes to the terminal."""
    print("building the site...", flush=True)
    result = subprocess.run([str(python), "-m", "src.build"], cwd=ROOT)
    if result.returncode == 0:
        print("build finished", flush=True)
    else:
        print(
            f"build failed with exit code {result.returncode}; the server keeps running, "
            "save a fix to rebuild",
            flush=True,
        )


def start_server(port: int) -> http.server.ThreadingHTTPServer:
    """Serve dist/ as the site root on localhost in a background thread."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DIST))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the site, serve it and rebuild on changes.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"port to serve on (default {DEFAULT_PORT})")
    args = parser.parse_args()
    python = venv_python()

    try:
        server = start_server(args.port)
    except OSError as exc:
        print(f"error: cannot serve on port {args.port}: {exc}; choose another with --port", file=sys.stderr)
        return 1

    print(f"serving {DIST} at http://localhost:{args.port}/ (Ctrl+C to stop)", flush=True)
    try:
        seen = snapshot()
        build(python)
        while True:
            time.sleep(POLL_SECONDS)
            current = snapshot()
            if current != seen:
                print("change detected", flush=True)
                seen = current
                build(python)
    except KeyboardInterrupt:
        print("\nstopping the server", flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
