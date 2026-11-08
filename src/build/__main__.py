"""Static site builder: checks the content and writes the site to dist/.

Usage (from the repository root, after `npm run setup`):

    .venv/bin/python -m src.build          # development: report pending markers, build anyway
    .venv/bin/python -m src.build --prod   # production: fail if any pending marker remains

The build needs the packages installed in `.venv/`. Started with another interpreter, it
runs again with the `.venv/` one; without `.venv/`, it stops and asks to run `npm run setup`.
"""

import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
VENV_DIR = ROOT / ".venv"
VENV_PYTHON = VENV_DIR / "bin" / "python"

# Same rule as scripts/project_python.py, which the scripts use. Runs before the imports
# below, because they need the packages of .venv/.
if Path(sys.prefix).resolve() != VENV_DIR.resolve():
    if not VENV_PYTHON.is_file():
        print(f"error: the project environment is missing ({VENV_DIR}); run `npm run setup` to create it",
              file=sys.stderr)
        sys.exit(1)
    os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), "-m", "src.build", *sys.argv[1:]])

from .config import PHOTO_FILE_NAME, PROJECTS, PROJECTS_DIR
from .content import BuildError, PENDING_MARKER, find_pending_markers, load_entries, load_locales
from .site import build_site

REQUIRED_DIRS = ["content/articles", "i18n", "templates", "templates/pages"]
DEV_SITE_URL = "http://localhost"
PHOTO_ENV = "SITE_PRIVATE_DIR"


def load_dotenv() -> None:
    """Sets the variables of `.env` (KEY=VALUE lines) that the environment does not have yet.

    The file is not versioned. It lets `npm run dev` find the private photo on every rebuild,
    whatever shell started it.
    """
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def check_layout(errors: list[str]) -> None:
    for relative in REQUIRED_DIRS:
        if not (ROOT / relative).is_dir():
            errors.append(f"missing directory: {relative}")


def read_site_url(prod: bool, errors: list[str]) -> str:
    """The site address from SITE_URL, without a trailing slash."""
    raw = os.environ.get("SITE_URL", "").strip()
    if not raw:
        if prod:
            errors.append("SITE_URL is required for the production build, like https://example.org")
        return DEV_SITE_URL
    parts = urlsplit(raw)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/") \
            or parts.query or parts.fragment:
        errors.append(f"SITE_URL must be an absolute http(s) address with no path, got {raw!r}")
        return DEV_SITE_URL
    return f"{parts.scheme}://{parts.netloc}"


def find_photo(prod: bool, errors: list[str], warnings: list[str]) -> Path | None:
    """The About page photo, read from the private folder named by SITE_PRIVATE_DIR.

    The production build needs it (error); the development build goes on without it (warning).
    """
    raw = os.environ.get(PHOTO_ENV, "").strip()
    if not raw:
        problem = f"{PHOTO_ENV} is not set"
    else:
        photo = Path(raw).expanduser() / PHOTO_FILE_NAME
        if photo.is_file():
            return photo
        problem = f"photo not found at {photo}"
    if prod:
        errors.append(f"{problem}; the production build needs {PHOTO_FILE_NAME} in the folder of {PHOTO_ENV}")
    else:
        warnings.append(f"{problem}; the About page is built without the photo")
    return None


def find_images(prod: bool, errors: list[str], warnings: list[str]) -> dict[str, Path]:
    """Images of the Projects page, content/projects/<name>.png; every project needs one in production."""
    found = {}
    for name in PROJECTS:
        path = ROOT / PROJECTS_DIR / f"{name}.png"
        if path.is_file():
            found[name] = path
        else:
            (errors if prod else warnings).append(f"missing image {PROJECTS_DIR}/{name}.png")
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the static site.")
    parser.add_argument("--prod", action="store_true", help="production build: fail on pending markers")
    args = parser.parse_args()

    load_dotenv()
    errors: list[str] = []
    warnings: list[str] = []
    check_layout(errors)
    site_url = read_site_url(args.prod, errors)
    photo = find_photo(args.prod, errors, warnings)
    images = find_images(args.prod, errors, warnings)
    locales = load_locales(ROOT, errors) if not errors else {}
    entries = load_entries(ROOT, locales, errors) if not errors else []
    pending = find_pending_markers(ROOT)

    if errors or (pending and args.prod):
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        for path in pending if args.prod else []:
            print(f"error: pending marker {PENDING_MARKER!r} in {path}", file=sys.stderr)
        return 1
    for path in pending:
        print(f"warning: pending marker {PENDING_MARKER!r} in {path}")
    for warning in warnings:
        print(f"warning: {warning}")

    shown = len(warnings)
    try:
        page_count = build_site(ROOT, locales, entries, site_url, warnings, photo, images)
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for warning in warnings[shown:]:
        print(f"warning: {warning}")

    mode = "production" if args.prod else "development"
    print(f"{mode} build: {page_count} page(s) in dist/, {len(pending)} pending marker(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
