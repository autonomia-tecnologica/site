"""Visual diff: a changed spacing must produce a report that names the affected page.

Captures two fixture sites (the second one changes the `main` padding of
about.html only), compares the runs with scripts/diff_report.py, and checks the
changed pages and components exactly. Outputs go to tests/visual/out/test-report/,
which is not versioned.

Run from the repository root, after `pip install --require-hashes -r requirements-dev.txt`
and `python -m playwright install chromium`:

    .venv/bin/python -m unittest discover -s tests/visual -t tests/visual -p "test_report.py"
"""

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
VISUAL = REPO / "tests" / "visual"
FIXTURES = VISUAL / "fixtures"
OUT = VISUAL / "out" / "test-report"
CAPTURE = REPO / "scripts" / "capture.py"
DIFF = REPO / "scripts" / "diff_report.py"


def run(*args):
    result = subprocess.run(
        [sys.executable, *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"{args[0]} failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


class SpacingChangeReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pages = FIXTURES / "pages.json"
        run(CAPTURE, "--site", FIXTURES / "site-before", "--out", OUT / "before", "--pages", pages)
        run(CAPTURE, "--site", FIXTURES / "site-after", "--out", OUT / "after", "--pages", pages)
        cls.report_path = OUT / "report.html"
        cls.stdout = run(
            DIFF,
            "--before", OUT / "before",
            "--after", OUT / "after",
            "--report", cls.report_path,
        )

    def test_changed_page_and_component_are_listed(self):
        self.assertIn("changed pages: 1", self.stdout)
        self.assertIn("- about.html", self.stdout)
        self.assertIn("component main: desktop/dark, desktop/light, mobile/dark, mobile/light", self.stdout)
        self.assertNotIn("index.html", self.stdout)

    def test_unchanged_components_are_not_listed(self):
        about_block = self.stdout.split("- about.html", 1)[1]
        self.assertNotIn("component header", about_block)
        self.assertNotIn("component footer", about_block)

    def test_full_page_change_covers_all_viewports_and_schemes(self):
        about_block = self.stdout.split("- about.html", 1)[1]
        self.assertIn("full page: desktop/dark, desktop/light, mobile/dark, mobile/light", about_block)

    def test_report_file_shows_before_and_after_images(self):
        html = self.report_path.read_text(encoding="utf-8")
        self.assertIn("<h2>about.html</h2>", html)
        self.assertNotIn("<h2>index.html</h2>", html)
        self.assertIn("before/mobile-light/about_html/full.png", html)
        self.assertIn("after/mobile-light/about_html/full.png", html)

    def test_manifest_covers_four_combinations(self):
        manifest = json.loads((OUT / "after" / "manifest.json").read_text(encoding="utf-8"))
        combos = {(s["viewport"], s["scheme"]) for s in manifest["shots"]}
        self.assertEqual(
            combos,
            {("mobile", "light"), ("mobile", "dark"), ("desktop", "light"), ("desktop", "dark")},
        )


if __name__ == "__main__":
    unittest.main()
