"""The layered layout of the knowledge graph: layers, edges, independent topics, titles and crossings.

Run from the repository root, with the interpreter of `.venv/`:

    .venv/bin/python -m unittest discover -s tests/build -t tests/build -p "test_graph_layout.py"
"""

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.build.graph import parse_graph  # noqa: E402
from src.build.graph_layout import (  # noqa: E402
    ELLIPSIS,
    NODE_HEIGHT,
    NODE_WIDTH,
    STRONG,
    TITLE_LINE_LENGTH,
    TITLE_MAX_LINES,
    WEAK,
    layout_graph,
    wrap_title,
)

ARTICLE_IDS = set()
PAGE_KEYS = set()


def node(node_id, title=None, strong=(), weak=()):
    """A valid graph node with the given dependencies."""
    return {
        "id": node_id,
        "title": title or f"Topic {node_id}",
        "description": "Description.",
        "status": "registrado",
        "refs": [],
        "strong_dependencies": list(strong),
        "weak_dependencies": list(weak),
    }


def graph_of(*nodes):
    return parse_graph({"version": 3, "nodes": list(nodes)}, ARTICLE_IDS, PAGE_KEYS)


def by_id(nodes):
    return {placed.id: placed for placed in nodes}


def edge_of(layout, source, target):
    return next(edge for edge in layout.edges if (edge.source, edge.target) == (source, target))


def chain_graph():
    """1 -> 2 -> 3 strong, and 1 -> 3 weak: the edge 1 -> 3 spans two layers."""
    return graph_of(
        node(1),
        node(2, strong=[1]),
        node(3, strong=[2], weak=[1]),
    )


def mixed_graph():
    """Twelve topics: a few chains, a long edge, shared fundamentals and two independent topics."""
    return graph_of(
        node(1, "Fundamentos da computação"),
        node(2, "Lógica", strong=[1]),
        node(3, "Álgebra linear", weak=[1]),
        node(4, "Cálculo diferencial e integral", strong=[2]),
        node(5, "Probabilidade", strong=[2, 3]),
        node(6, "Estatística", strong=[5], weak=[1]),
        node(7, "Otimização", strong=[3, 4]),
        node(8, "Aprendizado de máquina", strong=[6, 7]),
        node(9, "Redes neurais", weak=[8]),
        node(10, "Geometria"),
        node(11, "Teoria dos grafos"),
        node(12, "Teoria dos grafos aplicada", weak=[11]),
    )


class LayerTest(unittest.TestCase):
    def test_layer_is_the_longest_path_from_the_roots(self):
        layout = layout_graph(chain_graph())
        layers = by_id(layout.nodes)
        self.assertEqual({node_id: placed.layer for node_id, placed in layers.items()}, {1: 0, 2: 1, 3: 2})

    def test_every_edge_goes_from_a_smaller_layer_to_a_larger_one(self):
        layout = layout_graph(mixed_graph())
        layers = by_id(layout.nodes)
        self.assertTrue(layout.edges)
        for edge in layout.edges:
            self.assertLess(layers[edge.source].layer, layers[edge.target].layer, (edge.source, edge.target))

    def test_layers_increase_from_left_to_right(self):
        layout = layout_graph(mixed_graph())
        layers = by_id(layout.nodes)
        for placed in layout.nodes:
            self.assertEqual(placed.x, layers[placed.id].x)
        columns = sorted({placed.x for placed in layout.nodes})
        for left, right in zip(columns, columns[1:]):
            self.assertLess(left, right)


class EdgeTest(unittest.TestCase):
    def test_long_edge_bends_once_per_layer_it_crosses(self):
        layout = layout_graph(chain_graph())
        self.assertEqual(len(edge_of(layout, 1, 2).points), 2)
        self.assertEqual(len(edge_of(layout, 1, 3).points), 3)

    def test_edge_starts_at_the_source_and_ends_at_the_target(self):
        layout = layout_graph(chain_graph())
        layers = by_id(layout.nodes)
        for edge in layout.edges:
            source, target = layers[edge.source], layers[edge.target]
            self.assertEqual(edge.points[0], (source.x + NODE_WIDTH, source.y + NODE_HEIGHT / 2))
            self.assertEqual(edge.points[-1], (target.x, target.y + NODE_HEIGHT / 2))

    def test_edges_keep_their_strength(self):
        layout = layout_graph(chain_graph())
        self.assertEqual(edge_of(layout, 1, 2).strength, STRONG)
        self.assertEqual(edge_of(layout, 2, 3).strength, STRONG)
        self.assertEqual(edge_of(layout, 1, 3).strength, WEAK)

    def test_weak_dependencies_count_for_layers(self):
        layout = layout_graph(graph_of(node(1), node(2, weak=[1])))
        self.assertEqual({placed.id: placed.layer for placed in layout.nodes}, {1: 0, 2: 1})


class IndependentTest(unittest.TestCase):
    def test_topics_without_edges_go_to_the_independent_block(self):
        layout = layout_graph(mixed_graph())
        layered = {placed.id for placed in layout.nodes}
        independent = [placed.id for placed in layout.independent]
        self.assertEqual(independent, [10])
        self.assertFalse(layered & set(independent))
        self.assertIsNone(layout.independent[0].layer)

    def test_independent_block_is_below_the_graph(self):
        layout = layout_graph(mixed_graph())
        graph_bottom = max(placed.y + placed.height for placed in layout.nodes)
        for placed in layout.independent:
            self.assertGreater(placed.y, graph_bottom)

    def test_graph_without_edges_has_only_the_independent_block(self):
        layout = layout_graph(graph_of(node(1), node(2)))
        self.assertEqual(layout.nodes, ())
        self.assertEqual([placed.id for placed in layout.independent], [1, 2])
        self.assertEqual(layout.edges, ())


class GeometryTest(unittest.TestCase):
    def test_no_two_topics_overlap(self):
        layout = layout_graph(mixed_graph())
        boxes = list(layout.nodes) + list(layout.independent)
        for index, first in enumerate(boxes):
            for second in boxes[index + 1 :]:
                overlap_x = first.x < second.x + second.width and second.x < first.x + first.width
                overlap_y = first.y < second.y + second.height and second.y < first.y + first.height
                self.assertFalse(overlap_x and overlap_y, (first.id, second.id))

    def test_view_box_contains_every_topic_and_bend(self):
        layout = layout_graph(mixed_graph())
        min_x, min_y, width, height = layout.view_box
        self.assertEqual((min_x, min_y), (0.0, 0.0))
        for placed in layout.nodes + layout.independent:
            self.assertLessEqual(placed.x + placed.width, width)
            self.assertLessEqual(placed.y + placed.height, height)
        for edge in layout.edges:
            for x, y in edge.points:
                self.assertLessEqual(x, width)
                self.assertLessEqual(y, height)


class DeterminismTest(unittest.TestCase):
    def test_two_runs_give_the_same_layout(self):
        graph = mixed_graph()
        self.assertEqual(layout_graph(graph), layout_graph(graph))


class CrossingTest(unittest.TestCase):
    def test_barycenter_sweeps_have_fewer_crossings_than_id_order(self):
        # Roots 1 and 2; 3 depends on 2 and 4 depends on 1. Id order crosses the two edges.
        graph = graph_of(node(1), node(2), node(3, strong=[2]), node(4, strong=[1]))
        by_id_order = layout_graph(graph, sweeps=0)
        swept = layout_graph(graph)
        self.assertEqual(by_id_order.crossings, 1)
        self.assertEqual(swept.crossings, 0)
        self.assertLess(swept.crossings, by_id_order.crossings)
        layers = by_id(swept.nodes)
        self.assertLess(layers[4].y, layers[3].y)


class TitleTest(unittest.TestCase):
    def test_short_title_is_one_line(self):
        self.assertEqual(wrap_title("Lógica"), ("Lógica",))

    def test_title_breaks_between_words_up_to_the_line_length(self):
        lines = wrap_title("Cálculo diferencial e integral")
        self.assertEqual(lines, ("Cálculo", "diferencial e", "integral"))
        for line in lines:
            self.assertLessEqual(len(line), TITLE_LINE_LENGTH)

    def test_title_longer_than_three_lines_ends_with_an_ellipsis(self):
        title = "Uma frase longa que não cabe em três linhas de dezoito caracteres por causa do tamanho dela"
        lines = wrap_title(title)
        self.assertEqual(len(lines), TITLE_MAX_LINES)
        self.assertTrue(lines[-1].endswith(ELLIPSIS))
        for line in lines:
            self.assertLessEqual(len(line), TITLE_LINE_LENGTH)

    def test_word_longer_than_a_line_is_cut(self):
        lines = wrap_title("Supercalifragilisticoexpialidocioso")
        self.assertEqual(lines[0], "Supercalifragilist")
        self.assertLessEqual(len(lines), TITLE_MAX_LINES)

    def test_placed_topic_keeps_the_full_title(self):
        title = "Uma frase longa que não cabe em três linhas de dezoito caracteres por causa do tamanho dela"
        layout = layout_graph(graph_of(node(1, title), node(2, strong=[1])))
        placed = by_id(layout.nodes)[1]
        self.assertEqual(placed.title, title)
        self.assertEqual(len(placed.lines), TITLE_MAX_LINES)


if __name__ == "__main__":
    unittest.main()
