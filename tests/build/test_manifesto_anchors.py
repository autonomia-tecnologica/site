"""The manifesto page has one fixed anchor per point, ponto-1 to ponto-14, in the built HTML.

Builds the site with the development build, then reads dist/pt-br/manifesto/index.html.
The test fails when a point loses its id or when the list stops having 14 points.

Run from the repository root:

    python3 -m unittest discover -s tests/build -t tests/build
"""

import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MANIFESTO_HTML = REPO / "dist" / "pt-br" / "manifesto" / "index.html"
POINT_COUNT = 14


class _PageCollector(HTMLParser):
    """Collects the id of every element and the items of the ordered lists."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ids = []
        self.ordered_items = 0
        self._list_depth = 0

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name == "id" and value:
                self.ids.append(value)
        if tag == "ol":
            self._list_depth += 1
        elif tag == "li" and self._list_depth == 1:
            self.ordered_items += 1

    def handle_endtag(self, tag):
        if tag == "ol":
            self._list_depth -= 1


class ManifestoAnchorsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [sys.executable, "-m", "src.build"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"development build failed:\n{result.stderr}")
        cls.html = MANIFESTO_HTML.read_text(encoding="utf-8")
        collector = _PageCollector()
        collector.feed(cls.html)
        cls.ids = set(collector.ids)
        cls.ordered_items = collector.ordered_items

    def test_every_point_has_its_anchor(self):
        missing = [f"ponto-{n}" for n in range(1, POINT_COUNT + 1) if f"ponto-{n}" not in self.ids]
        self.assertEqual(missing, [], "anchors missing from dist/pt-br/manifesto/index.html")

    def test_the_list_has_fourteen_points(self):
        self.assertEqual(self.ordered_items, POINT_COUNT)

    def test_no_anchor_beyond_the_last_point(self):
        extra = sorted(i for i in self.ids if i.startswith("ponto-") and i not in
                       {f"ponto-{n}" for n in range(1, POINT_COUNT + 1)})
        self.assertEqual(extra, [])


if __name__ == "__main__":
    unittest.main()
