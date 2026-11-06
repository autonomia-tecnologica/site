"""The published copy of the graph data, and its entry in llms.txt.

The build copies content/graph/grafo.json to /<lang>/grafo/grafo.json, next to the graph page, and
llms.txt lists the page and the copy. With no topics there is no graph page, so there is no copy
and no entry. The real graph is empty; these tests use the fixture.

Each test builds a small site in a temporary folder, so the repository's dist/ is never touched.

Run from the repository root, with the interpreter of `.venv/`:

    .venv/bin/python -m unittest discover -s tests/build -t tests/build -p "test_graph_publish.py"
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.build.content import load_entries, load_locales  # noqa: E402
from src.build.site import build_site  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "graph" / "examples.json"
SITE = "http://localhost"
EMPTY_GRAPH = json.dumps({"version": 3, "nodes": []})
PUBLISHED = "pt-br/grafo/grafo.json"
ARTICLE = """---
title: Artigo de teste
date: 2026-01-01
updated: 2026-01-01
summary: Resumo do artigo de teste.
author: Autor de teste
---
Texto.
"""


def build_dist(graph_text: str) -> dict[str, bytes]:
    """Builds the site with the given graph file; returns the files of dist/ by path, as bytes."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name in ("templates", "i18n", "src"):
            (root / name).symlink_to(REPO / name)
        (root / "content" / "graph").mkdir(parents=True)
        (root / "content" / "graph" / "grafo.json").write_text(graph_text, encoding="utf-8")
        (root / "content" / "articles" / "pt_BR").mkdir(parents=True)
        (root / "content" / "articles" / "pt_BR" / "1.md").write_text(ARTICLE, encoding="utf-8")
        errors: list[str] = []
        locales = load_locales(root, errors)
        entries = load_entries(root, locales, errors)
        assert not errors, errors
        build_site(root, locales, entries, SITE, [], None)
        out = root / "dist"
        return {
            path.relative_to(out).as_posix(): path.read_bytes()
            for path in out.rglob("*") if path.is_file()
        }


class PublishedGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = FIXTURE.read_text(encoding="utf-8")
        cls.files = build_dist(cls.source)

    def test_published_json_matches_the_content_file(self):
        self.assertIn(PUBLISHED, self.files, "grafo.json was not published")
        self.assertEqual(self.files[PUBLISHED], FIXTURE.read_bytes())
        self.assertEqual(json.loads(self.files[PUBLISHED].decode("utf-8")), json.loads(self.source))

    def test_llms_lists_the_graph_page_and_the_copy(self):
        llms = self.files["llms.txt"].decode("utf-8")
        self.assertIn(f"({SITE}/pt-br/grafo/)", llms)
        self.assertIn(f"({SITE}/pt-br/grafo/grafo.json)", llms)


class EmptyGraphTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = build_dist(EMPTY_GRAPH)

    def test_no_copy_without_topics(self):
        self.assertNotIn(PUBLISHED, self.files)

    def test_llms_has_no_graph_entry_without_topics(self):
        self.assertNotIn("grafo", self.files["llms.txt"].decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
