"""Regression test: a nested token that the browser drops without a message.

The fixture declares `--ink: var(--ink-tone)` on :root while `--ink-tone` exists
only on a child element. The browser computes --ink to nothing on :root, and the
text falls back to black on the dark background. No console error is printed.

The test reproduces that fallback and checks that the detector in
scripts/browser_checks.py reports it, then checks the fixed fixture is clean.

Run from the repository root, after `pip install --require-hashes -r requirements-dev.txt`
and `python -m playwright install chromium`:

    .venv/bin/python -m unittest discover -s tests/visual -t tests/visual -p "test_nested_token.py"
"""

import sys
import unittest
from pathlib import Path

from playwright.sync_api import sync_playwright

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "visual" / "fixtures" / "nested-token"
sys.path.insert(0, str(REPO / "scripts"))
from browser_checks import find_unresolved_custom_properties  # noqa: E402


class NestedTokenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._playwright = sync_playwright().start()
        cls._browser = cls._playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls._browser.close()
        cls._playwright.stop()

    def open_fixture(self, name):
        page = self._browser.new_page()
        page.goto((FIXTURES / name).as_uri())
        return page

    def test_browser_drops_nested_token_silently(self):
        page = self.open_fixture("bug.html")
        try:
            # The author wrote white text; the browser falls back to black.
            color = page.evaluate("getComputedStyle(document.body).color")
            self.assertEqual(color, "rgb(0, 0, 0)")
            self.assertEqual(page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--ink')"), "")
        finally:
            page.close()

    def test_detector_reports_the_dropped_token(self):
        page = self.open_fixture("bug.html")
        try:
            found = find_unresolved_custom_properties(page)
        finally:
            page.close()
        self.assertEqual(
            found,
            [{"selector": ":root", "name": "--ink", "tag": "html"}],
        )

    def test_fixed_fixture_is_clean(self):
        page = self.open_fixture("fixed.html")
        try:
            color = page.evaluate("getComputedStyle(document.body).color")
            found = find_unresolved_custom_properties(page)
        finally:
            page.close()
        self.assertEqual(color, "rgb(255, 255, 255)")
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
