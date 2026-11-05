"""Development build stub: validates the repository layout and pending text.

Usage (from the repository root):

    python -m src.build          # development: report pending markers, exit 0
    python -m src.build --prod   # production: fail if any pending marker remains
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PENDING_MARKER = "[a escrever]"
LANGUAGE = "pt_BR"
REQUIRED_DIRS = [
    "content/articles/" + LANGUAGE,
    "content/pages/" + LANGUAGE,
    "src",
    "i18n",
]
TEXT_SCAN_DIRS = ["content", "i18n"]


def check_layout(errors: list[str]) -> None:
    for relative in REQUIRED_DIRS:
        if not (ROOT / relative).is_dir():
            errors.append(f"missing directory: {relative}")

    i18n_files = sorted(p.name for p in (ROOT / "i18n").glob("*.json"))
    if i18n_files != [f"{LANGUAGE}.json"]:
        errors.append(f"i18n must contain only {LANGUAGE}.json, found: {i18n_files}")
    else:
        try:
            if not isinstance(json.loads((ROOT / "i18n" / f"{LANGUAGE}.json").read_text(encoding="utf-8")), dict):
                errors.append(f"i18n/{LANGUAGE}.json must hold a JSON object")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"i18n/{LANGUAGE}.json is not valid JSON: {exc}")

    for section in ["articles", "pages"]:
        languages = sorted(p.name for p in (ROOT / "content" / section).iterdir() if p.is_dir())
        if languages != [LANGUAGE]:
            errors.append(f"content/{section} must contain only {LANGUAGE}, found: {languages}")


def find_pending_markers() -> list[str]:
    found = []
    for scan_dir in TEXT_SCAN_DIRS:
        for path in sorted((ROOT / scan_dir).rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if PENDING_MARKER in text:
                found.append(str(path.relative_to(ROOT)))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Development build stub.")
    parser.add_argument("--prod", action="store_true", help="production build: fail on pending markers")
    args = parser.parse_args()

    errors: list[str] = []
    check_layout(errors)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    pending = find_pending_markers()
    mode = "production" if args.prod else "development"
    if pending and args.prod:
        for path in pending:
            print(f"error: pending marker {PENDING_MARKER!r} in {path}", file=sys.stderr)
        return 1
    for path in pending:
        print(f"warning: pending marker {PENDING_MARKER!r} in {path}")

    print(f"{mode} build: layout ok, {len(pending)} pending marker(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
