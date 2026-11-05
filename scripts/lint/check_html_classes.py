#!/usr/bin/env python3
"""Check the HTML of the templates against the class vocabulary and color rules.

Stylelint covers the CSS; this script covers `templates/`, which Stylelint does
not parse. It checks every `class` name against `src/styles/class-vocabulary`
and every literal color in a `style` attribute against the tokens rule.
Jinja tags are removed before the check, so class names built from variables
are not checked. Standard library only.

Usage: python3 scripts/project_python.py scripts/lint/check_html_classes.py [--root DIR]
Exit status: 0 when clean, 1 when a violation is found.
"""

import argparse
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VOCABULARY = Path("src/styles/class-vocabulary")
TEMPLATES = Path("templates")
JINJA_TAG = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
HEX_COLOR = re.compile(r"#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})(?![\w-])")
COLOR_FUNCTION = re.compile(r"\b(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(", re.I)


class _AttributeCollector(HTMLParser):
    """Collects (line, class name) and (line, style value) pairs from one document."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.classes = []
        self.styles = []

    def handle_starttag(self, tag, attrs):
        line, _ = self.getpos()
        for name, value in attrs:
            if not value:
                continue
            if name == "class":
                for class_name in JINJA_TAG.sub(" ", value).split():
                    self.classes.append((line, class_name))
            elif name == "style":
                self.styles.append((line, JINJA_TAG.sub(" ", value)))


def read_vocabulary(path):
    """Class names listed one per line; blank lines and `#` comments are skipped."""
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            names.add(line)
    return names


def check_file(path, root, vocabulary, problems):
    collector = _AttributeCollector()
    collector.feed(path.read_text(encoding="utf-8"))
    relative = path.relative_to(root)
    if vocabulary is not None:
        for line, class_name in collector.classes:
            if class_name not in vocabulary:
                problems.append(f'{relative}:{line}: class "{class_name}" is not in {VOCABULARY}')
    for line, style in collector.styles:
        literal = HEX_COLOR.search(style) or COLOR_FUNCTION.search(style)
        if literal:
            problems.append(
                f'{relative}:{line}: color literal "{literal.group(0)}" in a style attribute; '
                "use a token instead"
            )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args(argv)
    root = args.root.resolve()

    vocabulary_path = root / VOCABULARY
    vocabulary = None
    if vocabulary_path.exists():
        vocabulary = read_vocabulary(vocabulary_path)
    else:
        print(f"note: {VOCABULARY} not found; class names are not checked", file=sys.stderr)

    problems = []
    templates = root / TEMPLATES
    for path in sorted(templates.rglob("*.html")) if templates.is_dir() else []:
        check_file(path, root, vocabulary, problems)

    for problem in problems:
        print(problem)
    if problems:
        print(f"{len(problems)} problem(s) found")
        return 1
    print("templates: no class or color problems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
