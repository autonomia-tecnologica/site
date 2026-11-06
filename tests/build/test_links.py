"""Broken links fail the build: short links ([text](artigo:12)) and internal links of built pages.

Run from the repository root, with the interpreter of `.venv/`:

    .venv/bin/python -m unittest discover -s tests/build -t tests/build
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.build.content import BuildError  # noqa: E402
from src.build.site import find_broken_links, make_markdown  # noqa: E402

SITE = "http://localhost"
ROUTES = {
    ("page", "pt_BR", "manifesto"): "/pt-br/manifesto/",
    ("article", "pt_BR", "1"): "/pt-br/artigos/1/",
    ("article", "pt_BR", "2"): "/pt-br/artigos/2/",
    ("graph", "pt_BR", "1"): "/pt-br/grafo/#1",
    ("graph", "pt_BR", "3"): "/pt-br/grafo/#3",
}


def render(text: str):
    """HTML and warnings of one Markdown text, with the routes of two articles."""
    env = {
        "where": "content/test.md", "warnings": [], "routes": ROUTES, "locale": "pt_BR",
        "new_tab_label": "abre em nova aba",
    }
    return make_markdown().render(text, env), env["warnings"]


class ShortLinkTest(unittest.TestCase):
    def test_article_link_becomes_the_url_of_the_article(self):
        html, warnings = render("Veja [a introdução](artigo:2).")
        self.assertIn('href="/pt-br/artigos/2/"', html)
        self.assertIn(">a introdução<span data-sr-only>", html)
        self.assertEqual(warnings, [])

    def test_page_link_and_point_anchor(self):
        html, _ = render("[o manifesto](pagina:manifesto) e [o ponto 3](pagina:manifesto#ponto-3)")
        self.assertIn('href="/pt-br/manifesto/"', html)
        self.assertIn('href="/pt-br/manifesto/#ponto-3"', html)

    def test_missing_page_stops_the_build(self):
        with self.assertRaisesRegex(BuildError, "pagina:nada"):
            render("[x](pagina:nada)")

    def test_missing_article_stops_the_build(self):
        with self.assertRaisesRegex(BuildError, "artigo:99"):
            render("[x](artigo:99)")

    def test_unknown_kind_stops_the_build(self):
        with self.assertRaisesRegex(BuildError, "unknown link kind"):
            render("[x](foo:1)")

    def test_graph_link_points_to_the_topic_in_the_graph_page(self):
        html, warnings = render("Veja [o nó](grafo:3) depois.")
        self.assertIn('href="/pt-br/grafo/#3"', html)
        self.assertEqual(warnings, [])

    def test_graph_link_to_a_missing_topic_stops_the_build(self):
        with self.assertRaisesRegex(BuildError, "grafo:5"):
            render("[x](grafo:5)")

    def test_new_tab_links_end_with_a_note_for_screen_readers(self):
        html, _ = render("[site](https://example.com) e [ponto](#ponto-1) e [outro](artigo:1)")
        self.assertEqual(html.count("<span data-sr-only>, abre em nova aba</span></a>"), 2)
        self.assertNotIn('#ponto-1" target', html)

    def test_external_links_are_left_alone(self):
        html, _ = render("[site](https://example.com) e [mail](mailto:a@b.c)")
        self.assertIn('href="https://example.com"', html)
        self.assertIn('href="mailto:a@b.c"', html)


class BrokenLinkCheckTest(unittest.TestCase):
    PAGES = {
        "pt-br/index.html": '<a href="/pt-br/artigos/">a</a><a href="/pt-br/artigos/1/#intro">b</a><a href="#top">c</a><h1 id="top">',
        "pt-br/artigos/index.html": "<p>lista</p>",
        "pt-br/artigos/1/index.html": '<h2 id="intro">i</h2>',
    }

    def check(self, **extra):
        return find_broken_links({**self.PAGES, **extra}, {"styles/base.css"}, SITE)

    def test_good_links_pass(self):
        self.assertEqual(self.check(), [])

    def test_missing_page_is_reported(self):
        broken = self.check(**{"pt-br/x/index.html": '<a href="/pt-br/artigos/9/">z</a>'})
        self.assertEqual(len(broken), 1)
        self.assertIn("/pt-br/artigos/9/", broken[0])

    def test_missing_anchor_in_the_same_page_is_reported(self):
        broken = self.check(**{"pt-br/x/index.html": '<a href="#nada">z</a>'})
        self.assertEqual(len(broken), 1)

    def test_missing_id_in_another_page_is_reported(self):
        broken = self.check(**{"pt-br/x/index.html": '<a href="/pt-br/artigos/1/#nada">z</a>'})
        self.assertEqual(len(broken), 1)

    def test_site_address_links_are_checked_and_external_are_not(self):
        broken = self.check(**{
            "pt-br/x/index.html": f'<a href="{SITE}/pt-br/artigos/1/">ok</a><a href="https://example.com/zzz">out</a>'
                                  f'<a href="{SITE}/pt-br/nada/">bad</a>',
        })
        self.assertEqual(len(broken), 1)
        self.assertIn("nada", broken[0])

    def test_files_that_are_not_pages_count(self):
        self.assertEqual(self.check(**{"pt-br/x/index.html": '<a href="/styles/base.css">css</a>'}), [])


if __name__ == "__main__":
    unittest.main()
