"""The knowledge graph: validation of grafo.json (version 3) and the study trail.

Run from the repository root, with the interpreter of `.venv/`:

    .venv/bin/python -m unittest discover -s tests/build -t tests/build -p "test_graph.py"
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.build.graph import (  # noqa: E402
    GRAPH_RELATIVE_PATH,
    GraphError,
    compute_trail,
    parse_graph,
    read_graph,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "graph"
ARTICLE_IDS = {"1"}
PAGE_KEYS = {"manifesto"}


def node(node_id, **changes):
    """A valid node with no refs and no dependencies, changed by the keyword arguments."""
    data = {
        "id": node_id,
        "title": f"Node {node_id}",
        "description": "Description.",
        "status": "registrado",
        "refs": [],
        "strong_dependencies": [],
        "weak_dependencies": [],
    }
    data.update(changes)
    return data


def graph_of(*nodes):
    return {"version": 3, "nodes": list(nodes)}


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ValidGraphTest(unittest.TestCase):
    def test_empty_graph_passes(self):
        graph = parse_graph(graph_of(), ARTICLE_IDS, PAGE_KEYS)
        self.assertEqual(graph.nodes, {})

    def test_repository_graph_is_valid_and_empty(self):
        graph = read_graph(REPO / GRAPH_RELATIVE_PATH, set(), set())
        self.assertEqual(graph.nodes, {})

    def test_domain_is_allowed_and_ignored(self):
        graph = parse_graph(graph_of(node(1, domain=["agent", 1])), ARTICLE_IDS, PAGE_KEYS)
        self.assertEqual(graph.nodes[1].title, "Node 1")

    def test_examples_fixture_is_valid(self):
        graph = parse_graph(load_fixture("examples.json"), ARTICLE_IDS, PAGE_KEYS)
        self.assertEqual(sorted(graph.nodes), [1, 2, 3, 4, 5, 6])

    def test_refs_accept_internal_links_that_exist_and_https_links(self):
        data = graph_of(node(1, refs=[
            {"title": "Artigo", "link": "artigo:1", "type": "artigo"},
            {"title": "Página", "link": "pagina:manifesto#ponto-3", "type": "página"},
            {"title": "Vídeo", "link": "https://example.org/v", "type": "vídeo"},
        ]))
        graph = parse_graph(data, ARTICLE_IDS, PAGE_KEYS)
        self.assertEqual([ref.link for ref in graph.nodes[1].refs], [
            "artigo:1", "pagina:manifesto#ponto-3", "https://example.org/v",
        ])


class InvalidGraphTest(unittest.TestCase):
    def problems(self, data, articles=ARTICLE_IDS, pages=PAGE_KEYS):
        with self.assertRaises(GraphError) as context:
            parse_graph(data, articles, pages)
        return context.exception.problems

    def assertProblem(self, data, fragment, articles=ARTICLE_IDS, pages=PAGE_KEYS):
        problems = self.problems(data, articles, pages)
        self.assertTrue(any(fragment in problem for problem in problems), problems)

    def test_duplicate_id(self):
        self.assertProblem(graph_of(node(1), node(1)), "duplicate id 1")

    def test_edge_to_missing_id(self):
        self.assertProblem(graph_of(node(1, strong_dependencies=[9])), "node 1 depends on 9, which does not exist")

    def test_self_edge(self):
        self.assertProblem(graph_of(node(1, weak_dependencies=[1])), "node 1 depends on itself")

    def test_same_id_strong_and_weak(self):
        self.assertProblem(
            graph_of(node(1, strong_dependencies=[2], weak_dependencies=[2]), node(2)),
            "node 1 lists 2 as both strong and weak dependency",
        )

    def test_cycle_shows_its_path(self):
        data = load_fixture("cycle.json")
        self.assertProblem(data, "cycle: 3 -> 5 -> 3")

    def test_cycle_of_length_three(self):
        data = graph_of(node(1, strong_dependencies=[2]), node(2, strong_dependencies=[3]), node(3, weak_dependencies=[1]))
        self.assertProblem(data, "cycle: 1 -> 2 -> 3 -> 1")

    def test_ref_to_missing_article(self):
        data = graph_of(node(1, refs=[{"title": "x", "link": "artigo:99", "type": "artigo"}]))
        self.assertProblem(data, "points to an article that does not exist")

    def test_ref_to_missing_page(self):
        data = graph_of(node(1, refs=[{"title": "x", "link": "pagina:nada", "type": "página"}]))
        self.assertProblem(data, "points to a page that does not exist")

    def test_external_ref_without_https(self):
        for link in ("http://example.org", "example.org", "ftp://example.org"):
            with self.subTest(link=link):
                data = graph_of(node(1, refs=[{"title": "x", "link": link, "type": "site"}]))
                self.assertProblem(data, "must be artigo:<id>, pagina:<key> or an address starting with https://")

    def test_unknown_key_is_an_error(self):
        self.assertProblem(graph_of(node(1, colour="red")), "unknown key 'colour'")

    def test_unknown_key_in_ref_is_an_error(self):
        data = graph_of(node(1, refs=[{"title": "x", "link": "https://example.org", "type": "site", "extra": 1}]))
        self.assertProblem(data, "unknown key 'extra'")

    def test_missing_key_is_an_error(self):
        broken = node(1)
        del broken["description"]
        self.assertProblem(graph_of(broken), "missing key 'description'")

    def test_wrong_version(self):
        self.assertProblem({"version": 2, "nodes": []}, "version must be 3")

    def test_unknown_top_level_key_is_an_error(self):
        self.assertProblem({"version": 3, "nodes": [], "extra": True}, "unknown key 'extra'")

    def test_dependency_that_is_not_an_id(self):
        self.assertProblem(graph_of(node(1, strong_dependencies=["2"])), "which is not an id")

    def test_problems_are_all_reported_together(self):
        data = graph_of(node(1, strong_dependencies=[9], weak_dependencies=[1]), node(1))
        problems = self.problems(data)
        self.assertGreaterEqual(len(problems), 3, problems)

    def test_invalid_json_file_is_reported_with_its_name(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "grafo.json"
            path.write_text("{nope", encoding="utf-8")
            with self.assertRaisesRegex(GraphError, "grafo.json: invalid JSON"):
                read_graph(path, ARTICLE_IDS, PAGE_KEYS)

    def test_cycle_file_problems_carry_the_file_name(self):
        with self.assertRaisesRegex(GraphError, r"cycle.json: cycle: 3 -> 5 -> 3"):
            read_graph(FIXTURES / "cycle.json", ARTICLE_IDS, PAGE_KEYS)


class StudyTrailTest(unittest.TestCase):
    """The two examples of the convention: LLM, and Sandbox de LLM."""

    @classmethod
    def setUpClass(cls):
        cls.graph = parse_graph(load_fixture("examples.json"), ARTICLE_IDS, PAGE_KEYS)

    def test_llm_required_are_the_strong_closure(self):
        # LLM -forte-> Matriz -fraca-> Cálculo -forte-> Álgebra: Matriz is required, the rest is recommended.
        trail = compute_trail(self.graph, 1)
        self.assertEqual(trail.required, (2, 6, 1))
        self.assertEqual(trail.recommended, (4, 3))

    def test_sandbox_takes_the_strongest_path_to_linux(self):
        # Sandbox -forte-> LLM -forte-> Linux, and Sandbox -fraca-> Linux: Linux counts as required.
        trail = compute_trail(self.graph, 5)
        self.assertEqual(trail.required, (2, 6, 1, 5))
        self.assertEqual(trail.recommended, (4, 3))

    def test_order_puts_dependencies_first_and_breaks_ties_by_id(self):
        # 4 and 6 have no dependencies: 4 comes first by id; 5 is the target, so it is last.
        self.assertEqual(compute_trail(self.graph, 5).order, (4, 3, 2, 6, 1, 5))
        self.assertEqual(compute_trail(self.graph, 1).order, (4, 3, 2, 6, 1))

    def test_node_without_dependencies_is_its_own_required_trail(self):
        trail = compute_trail(self.graph, 6)
        self.assertEqual(trail.order, (6,))
        self.assertEqual(trail.required, (6,))
        self.assertEqual(trail.recommended, ())

    def test_trail_of_unknown_node_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "node 42"):
            compute_trail(self.graph, 42)


if __name__ == "__main__":
    unittest.main()
