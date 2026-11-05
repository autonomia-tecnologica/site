"""Reads locales, articles and pages from the repository and checks them.

Articles live in content/articles/<locale>/<id>.md and pages in
content/pages/<locale>/<name>.md. Each file starts with a YAML front matter
block between --- lines.
"""

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

PENDING_MARKER = "[a escrever]"
TEXT_SCAN_DIRS = ["content", "i18n"]
# The home page body: it is shown on the locale index (/<locale>/) and has no URL segment of its own.
HOME_PAGE_KEY = "home"

LOCALE_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}$")
ARTICLE_ID_RE = re.compile(r"^[0-9]+$")
PAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9-]*$")
FRONT_MATTER_RE = re.compile(r"\A---\n(.*?\n)?---\n?(.*)\Z", re.DOTALL)

FIELD_TYPES = {
    "title": str,
    "date": date,
    "updated": date,
    "summary": str,
    "substack_url": str,
    "graph_id": str,
}
REQUIRED_FIELDS = {
    "article": ("title", "date", "updated", "summary"),
    "page": ("title", "summary"),  # pages carry no publication dates
}


class BuildError(Exception):
    """A problem the author must fix before the site can be built."""


@dataclass(frozen=True)
class Entry:
    kind: str  # "article" or "page"
    locale: str  # "pt_BR"
    key: str  # article id ("12") or page name ("home")
    meta: dict
    body: str  # Markdown source, without the front matter
    path: Path  # the original file, copied byte for byte for articles


def load_locales(root: Path, errors: list[str]) -> dict[str, dict]:
    """Every i18n/<locale>.json is one locale; its code is the file name."""
    locales: dict[str, dict] = {}
    for path in sorted((root / "i18n").glob("*.json")):
        code = path.stem
        if not LOCALE_RE.match(code):
            errors.append(f"i18n/{path.name}: locale code must look like pt_BR")
            continue
        try:
            strings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"i18n/{path.name}: {exc}")
            continue
        if not isinstance(strings, dict):
            errors.append(f"i18n/{path.name}: must hold a JSON object")
            continue
        locales[code] = strings
    if not locales:
        errors.append("i18n holds no locale file")
    return locales


def load_entries(root: Path, locales: dict[str, dict], errors: list[str]) -> list[Entry]:
    entries: list[Entry] = []
    for section, kind in (("articles", "article"), ("pages", "page")):
        for locale_dir in sorted((root / "content" / section).iterdir()):
            if not locale_dir.is_dir():
                continue
            locale = locale_dir.name
            if locale not in locales:
                errors.append(f"content/{section}/{locale}: no i18n/{locale}.json for this locale")
                continue
            for path in sorted(locale_dir.glob("*.md")):
                where = f"content/{section}/{locale}/{path.name}"
                key = path.stem
                if kind == "article" and not ARTICLE_ID_RE.match(key):
                    errors.append(f"{where}: article file name must be a numeric id, like 12.md")
                    continue
                if kind == "page":
                    if not PAGE_NAME_RE.match(key):
                        errors.append(f"{where}: page file name must be lowercase English, like home.md")
                        continue
                    if key != HOME_PAGE_KEY and key not in locales[locale].get("url", {}).get("pages", {}):
                        errors.append(f"{where}: i18n/{locale}.json has no url.pages.{key} segment")
                        continue
                parsed = read_entry(path, where, kind, errors)
                if parsed is not None:
                    meta, body = parsed
                    entries.append(Entry(kind, locale, key, meta, body, path))
    return entries


def read_entry(path: Path, where: str, kind: str, errors: list[str]) -> tuple[dict, str] | None:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = FRONT_MATTER_RE.match(text)
    if match is None:
        errors.append(f"{where}: missing front matter between --- lines")
        return None
    try:
        meta = yaml.safe_load(match.group(1) or "")
    except yaml.YAMLError as exc:
        errors.append(f"{where}: invalid front matter: {exc}")
        return None
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        errors.append(f"{where}: front matter must be a mapping of fields")
        return None

    problems = [f"unknown field {name!r}" for name in meta if name not in FIELD_TYPES]
    for name, expected in FIELD_TYPES.items():
        if name not in meta:
            if name in REQUIRED_FIELDS[kind]:
                problems.append(f"missing field {name!r}")
        elif not is_valid_value(meta[name], expected):
            wanted = "a date (YYYY-MM-DD)" if expected is date else "non-empty text"
            problems.append(f"field {name!r} must be {wanted}")
    for problem in problems:
        errors.append(f"{where}: {problem}")
    if problems:
        return None
    return meta, match.group(2)


def is_valid_value(value: object, expected: type) -> bool:
    if expected is date:
        return type(value) is date
    return isinstance(value, str) and value.strip() != ""


def find_pending_markers(root: Path) -> list[str]:
    found = []
    for scan_dir in TEXT_SCAN_DIRS:
        for path in sorted((root / scan_dir).rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if PENDING_MARKER in text:
                found.append(str(path.relative_to(root)))
    return found
