"""Lint rules: the bad fixture must fail on the three rules, the good one must pass.

Run from the repository root, after `npm ci`:

    python3 -m unittest discover -s tests/lint -t tests/lint
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "lint" / "fixtures"
STYLELINT = REPO / "node_modules" / ".bin" / "stylelint"
STYLELINT_CONFIG = REPO / "stylelint.config.mjs"
CHECK_HTML = REPO / "scripts" / "lint" / "check_html_classes.py"


def run_stylelint(site):
    """Lint the CSS of a fixture site, with the fixture as the working directory."""
    return subprocess.run(
        [
            str(STYLELINT),
            "src/styles/**/*.css",
            "--config",
            str(STYLELINT_CONFIG),
            "--allow-empty-input",
        ],
        cwd=FIXTURES / site,
        stdout=subprocess.PIPE,
        # Stylelint prints its report on stderr when stdout is not a terminal.
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )


def run_html_check(site):
    return subprocess.run(
        [sys.executable, str(CHECK_HTML), "--root", str(FIXTURES / site)],
        capture_output=True,
        text=True,
        check=False,
    )


class StylelintRulesTest(unittest.TestCase):
    def test_good_fixture_passes(self):
        result = run_stylelint("site-good")
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_literal_color_fails(self):
        result = run_stylelint("site-bad")
        self.assertIn("site/no-literal-color", result.stdout)
        self.assertIn("src/styles/literal.css", result.stdout)
        self.assertIn('"#fff"', result.stdout)

    def test_unknown_variable_fails(self):
        result = run_stylelint("site-bad")
        self.assertIn("site/no-unknown-var", result.stdout)
        self.assertIn("src/styles/wrong-var.css", result.stdout)
        self.assertIn('"--color-txt"', result.stdout)

    def test_new_class_fails(self):
        result = run_stylelint("site-bad")
        self.assertIn("site/no-unknown-class", result.stdout)
        self.assertIn("src/styles/new-class.css", result.stdout)
        self.assertIn('"nova"', result.stdout)

    def test_bad_fixture_exits_nonzero(self):
        self.assertNotEqual(run_stylelint("site-bad").returncode, 0)


class HtmlClassRulesTest(unittest.TestCase):
    def test_good_templates_pass(self):
        result = run_html_check("site-good")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_new_class_and_style_color_fail(self):
        result = run_html_check("site-bad")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('class "nova" is not in', result.stdout)
        self.assertIn('color literal "#123456"', result.stdout)


if __name__ == "__main__":
    unittest.main()
