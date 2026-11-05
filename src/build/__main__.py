"""Static site builder: checks the content and writes the site to dist/.

Usage (from the repository root):

    python -m src.build          # development: report pending markers, build anyway
    python -m src.build --prod   # production: fail if any pending marker remains
"""

import argparse
import sys
from pathlib import Path

from .content import BuildError, PENDING_MARKER, find_pending_markers, load_entries, load_languages
from .site import build_site

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_DIRS = ["content/articles", "content/pages", "i18n", "templates"]


def check_layout(errors: list[str]) -> None:
    for relative in REQUIRED_DIRS:
        if not (ROOT / relative).is_dir():
            errors.append(f"missing directory: {relative}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static site.")
    parser.add_argument("--prod", action="store_true", help="production build: fail on pending markers")
    args = parser.parse_args()

    errors: list[str] = []
    check_layout(errors)
    languages = load_languages(ROOT, errors) if not errors else {}
    entries = load_entries(ROOT, languages, errors) if not errors else []
    pending = find_pending_markers(ROOT)

    if errors or (pending and args.prod):
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        for path in pending if args.prod else []:
            print(f"error: pending marker {PENDING_MARKER!r} in {path}", file=sys.stderr)
        return 1
    for path in pending:
        print(f"warning: pending marker {PENDING_MARKER!r} in {path}")

    try:
        page_count = build_site(ROOT, languages, entries)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    mode = "production" if args.prod else "development"
    print(f"{mode} build: {page_count} page(s) in dist/, {len(pending)} pending marker(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
