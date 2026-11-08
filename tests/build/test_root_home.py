"""With one locale, the site address serves the home page of that locale directly.

Builds the site with the development build, then reads dist/index.html, the
sitemap and the home page. The test fails when the site address redirects, shows a
locale list, is in the sitemap, or when the navigation lists the home page.

Run from the repository root:

    python3 -m unittest discover -s tests/build -t tests/build -p "test_root_home.py"
"""

import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DIST = REPO / "dist"
HOME_HREF = "/pt-br/"
HOME_URL = "http://localhost/pt-br/"
LOCALE_NAME = "Português (Brasil)"
HOME_LABEL = "Início"


class RootHomeTest(unittest.TestCase):
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
        cls.root = (DIST / "index.html").read_text(encoding="utf-8")
        cls.sitemap = (DIST / "sitemap.xml").read_text(encoding="utf-8")
        cls.home = (DIST / "pt-br" / "index.html").read_text(encoding="utf-8")

    def test_site_address_serves_the_home(self):
        self.assertNotIn('http-equiv="refresh"', self.root)
        self.assertNotIn("Redirecionando", self.root)
        self.assertIn(f'<link rel="canonical" href="{HOME_URL}">', self.root)
        self.assertIn('<h1 class="hero__title">', self.root)

    def test_site_address_is_the_same_home(self):
        self.assertEqual(self.root, self.home)

    def test_site_address_shows_no_locale_list(self):
        self.assertNotIn(LOCALE_NAME, self.root)

    def test_site_address_is_not_in_the_sitemap(self):
        self.assertNotIn("<loc>http://localhost/</loc>", self.sitemap)
        self.assertIn(f"<loc>{HOME_URL}</loc>", self.sitemap)

    def test_navigation_has_no_home_item(self):
        self.assertNotIn(f'<a href="{HOME_HREF}">{HOME_LABEL}</a>', self.home)

    def test_header_name_links_to_the_locale_home(self):
        self.assertIn(f'<header class="site-header">\n<a href="{HOME_HREF}">', self.home)


if __name__ == "__main__":
    unittest.main()
