"""The knowledge graph page: one entry per topic, the study trail, the topics that lead to it, the
refs, the list of topics for screen readers, and the grafo: links of the text.

Each test builds a small site in a temporary folder (the templates, the i18n files and the styles
are linked from the repository), so the repository's dist/ is never touched. A broken internal
link stops build_site, so a build that finishes also means that find_broken_links found nothing.

Run from the repository root, with the interpreter of `.venv/`:

    .venv/bin/python -m unittest discover -s tests/build -t tests/build -p "test_graph_page.py"
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.build.content import BuildError, load_entries, load_locales  # noqa: E402
from src.build.graph import parse_graph  # noqa: E402
from src.build.site import build_site, dependents_of  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "graph" / "examples.json"
SITE = "http://localhost"
EMPTY_GRAPH = json.dumps({"version": 3, "nodes": []})
ARTICLE = """---
title: Artigo de teste
date: 2026-01-01
updated: 2026-01-01
summary: Resumo do artigo de teste.
author: Autor de teste
---
{body}
"""


def build_dist(graph_text: str, article_body: str = "Texto.") -> dict[str, str]:
    """Builds the site with the graph file and one article; returns the HTML and XML files of dist/.

    Raises BuildError when the build stops.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("templates", "i18n", "src"):
            (root / name).symlink_to(REPO / name)
        (root / "content" / "graph").mkdir(parents=True)
        (root / "content" / "graph" / "grafo.json").write_text(graph_text, encoding="utf-8")
        (root / "content" / "articles" / "pt_BR").mkdir(parents=True)
        (root / "content" / "articles" / "pt_BR" / "1.md").write_text(
            ARTICLE.format(body=article_body), encoding="utf-8",
        )
        errors: list[str] = []
        locales = load_locales(root, errors)
        entries = load_entries(root, locales, errors)
        assert not errors, errors
        build_site(root, locales, entries, SITE, [], None)
        out = root / "dist"
        return {
            path.relative_to(out).as_posix(): path.read_text(encoding="utf-8")
            for path in out.rglob("*") if path.is_file() and path.suffix in (".html", ".xml")
        }


def article_of(html: str, node_id: int) -> str:
    """The HTML of the entry of one topic on the graph page."""
    match = re.search(rf'<article id="{node_id}" data-node>(.*?)</article>', html, re.S)
    if match is None:
        raise AssertionError(f"no entry for topic {node_id}")
    return match.group(1)


class GraphPageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dist = build_dist(FIXTURE.read_text(encoding="utf-8"))
        cls.page = cls.dist["pt-br/grafo/index.html"]
        cls.strings = json.loads((REPO / "i18n" / "pt_BR.json").read_text(encoding="utf-8"))

    def test_one_entry_per_topic(self):
        ids = re.findall(r'<article id="(\d+)" data-node>', self.page)
        self.assertEqual(ids, ["1", "2", "3", "4", "5", "6"])

    def test_page_is_in_the_sitemap(self):
        self.assertIn("<loc>http://localhost/pt-br/grafo/</loc>", self.dist["sitemap.xml"])

    def test_trail_has_the_dependencies_of_the_topic(self):
        # Topic 2 depends weakly on 3, and 3 strongly on 4: the trail of 2 is 3 and 4.
        entry = article_of(self.page, 2)
        self.assertIn('<a href="#3">Cálculo</a>', entry)
        self.assertIn('<a href="#4">Álgebra</a>', entry)
        self.assertNotIn('href="#6"', entry)

    def test_topics_that_lead_to_a_topic_are_listed(self):
        self.assertIn('<a href="#1">LLM</a>', article_of(self.page, 6))
        self.assertIn('<a href="#5">Sandbox de LLM</a>', article_of(self.page, 6))

    def test_refs_link_to_articles_and_to_outside_addresses(self):
        entry = article_of(self.page, 1)
        self.assertIn('<a href="/pt-br/artigos/1/">Verbete de LLM</a>', entry)
        self.assertIn('<a href="https://example.org/llm" target="_blank" rel="noopener">Vídeo sobre LLM', entry)

    def test_topic_without_refs_says_so(self):
        # The text is in a paragraph of its own; the same text may be a heading elsewhere.
        no_content = f"<p>{self.strings['graph']['no_content']}</p>"
        self.assertIn(no_content, article_of(self.page, 2))
        self.assertNotIn(no_content, article_of(self.page, 1))

    def test_list_has_every_topic_once_without_levels(self):
        # The list is for screen readers: one flat list of links, the independent topics included.
        list_html = self.page.split('<div data-list>')[1].split('</div>')[0]
        self.assertEqual(re.findall(r'<a href="#(\d+)">', list_html), ["1", "2", "3", "4", "5", "6"])
        self.assertEqual(list_html.count("<ul>"), 1)
        self.assertNotIn("<ol", list_html)
        self.assertNotIn("<h2", list_html)
        self.assertNotIn("data-independent", self.page)

    def test_dependents_are_the_inverse_of_the_dependencies(self):
        graph = parse_graph(json.loads(FIXTURE.read_text(encoding="utf-8")), {"1"}, {"manifesto"})
        dependents = dependents_of(graph)
        self.assertEqual(dependents[6], [1, 5])
        self.assertEqual(dependents[2], [1])
        self.assertEqual(dependents[4], [3])
        self.assertEqual(dependents[1], [5])

    def test_text_link_to_a_topic_points_to_its_entry(self):
        dist = build_dist(FIXTURE.read_text(encoding="utf-8"), "Veja [o cálculo](grafo:3).")
        self.assertIn('href="/pt-br/grafo/#3"', dist["pt-br/artigos/1/index.html"])

    def test_text_link_to_a_missing_topic_stops_the_build(self):
        with self.assertRaisesRegex(BuildError, "grafo:9"):
            build_dist(FIXTURE.read_text(encoding="utf-8"), "[x](grafo:9)")

    def test_empty_graph_makes_no_page(self):
        dist = build_dist(EMPTY_GRAPH)
        self.assertNotIn("pt-br/grafo/index.html", dist)
        self.assertNotIn("/pt-br/grafo/", dist["sitemap.xml"])

    def test_text_link_to_a_topic_of_an_empty_graph_stops_the_build(self):
        with self.assertRaisesRegex(BuildError, "grafo:1"):
            build_dist(EMPTY_GRAPH, "[x](grafo:1)")


if __name__ == "__main__":
    unittest.main()
