"""Layered layout of the knowledge graph, computed at build time.

The input is a Graph already validated by graph.py. This module only computes positions.

Layers: the layer of a topic is the longest path from the roots (topics with no dependency),
counting strong and weak dependencies alike. So every edge goes from a smaller layer to a larger
one, and the study direction runs left to right: fundamentals first.

Long edges: an edge that spans several layers gets one dummy node in each layer it crosses.
A dummy node takes a slot in its layer like a topic does, so the edge bends around the topics
of the layers in between.

Crossings: the order inside each layer comes from barycenter sweeps, with ties broken by id, and
the order with the fewest crossings found is kept. Topics with no edge are not layered: they come
in a separate block (the "independent" one) below the graph.

Everything is deterministic: the same graph always gives the same Layout.
"""

from dataclasses import dataclass

from .graph import Graph, dependencies, study_order

STRONG = "strong"
WEAK = "weak"
TITLE_LINE_LENGTH = 18
TITLE_MAX_LINES = 3
ELLIPSIS = "…"
NODE_WIDTH = 180.0
LINE_HEIGHT = 20.0
TITLE_PADDING = 16.0
NODE_HEIGHT = TITLE_MAX_LINES * LINE_HEIGHT + TITLE_PADDING
COLUMN_GAP = 120.0
ROW_GAP = 24.0
BLOCK_GAP = 48.0
MARGIN = 24.0
DEFAULT_SWEEPS = 24

# A key of a layer is a topic id (int) or a dummy node: (source id, target id, layer) of one edge.
Key = int | tuple[int, int, int]
Point = tuple[float, float]


@dataclass(frozen=True)
class PlacedNode:
    id: int
    title: str  # the full title, as in the graph
    lines: tuple[str, ...]  # the title in at most TITLE_MAX_LINES lines
    x: float  # top left corner
    y: float
    layer: int | None  # None for independent topics
    width: float = NODE_WIDTH
    height: float = NODE_HEIGHT


@dataclass(frozen=True)
class PlacedEdge:
    source: int  # the dependency, the topic studied first
    target: int  # the topic that depends on it
    strength: str  # STRONG or WEAK
    points: tuple[Point, ...]  # from the right of the source to the left of the target, bends included


@dataclass(frozen=True)
class Layout:
    nodes: tuple[PlacedNode, ...]  # the layered topics, by id
    independent: tuple[PlacedNode, ...]  # the topics with no edge, by id, in a block below the graph
    edges: tuple[PlacedEdge, ...]  # by (source, target)
    view_box: tuple[float, float, float, float]  # min x, min y, width, height
    crossings: int  # crossings between edges in the order chosen


def layout_graph(graph: Graph, sweeps: int = DEFAULT_SWEEPS) -> Layout:
    """The layout of `graph`. `sweeps` is the number of barycenter sweeps; 0 keeps the id order."""
    edges = dependency_edges(graph)
    linked = {node_id for source, target, _ in edges for node_id in (source, target)}
    layer_of = assign_layers(graph, linked)
    chains = {(source, target): edge_chain(source, target, layer_of) for source, target, _ in edges}
    layers = group_by_layer(chains.values(), layer_of)
    left_of, right_of = neighbours(chains.values())
    ordered, crossings = order_layers(layers, left_of, right_of, sweeps)

    pitch = NODE_HEIGHT + ROW_GAP
    block_height = max((len(layer) * pitch - ROW_GAP for layer in ordered), default=0.0)
    top_of: dict[Key, float] = {}
    for layer in ordered:
        offset = (block_height - (len(layer) * pitch - ROW_GAP)) / 2
        for slot, key in enumerate(layer):
            top_of[key] = MARGIN + offset + slot * pitch

    placed_nodes = tuple(
        place_node(graph, node_id, column_x(layer_of[node_id]), top_of[node_id], layer_of[node_id])
        for node_id in sorted(linked)
    )
    placed_edges = tuple(
        PlacedEdge(source, target, strength, edge_points(chains[(source, target)], layer_of, top_of))
        for source, target, strength in edges
    )

    block_top = MARGIN + block_height + BLOCK_GAP if ordered else MARGIN
    columns = max(1, len(ordered))
    loose = sorted(set(graph.nodes) - linked)
    independent = tuple(
        place_node(
            graph,
            node_id,
            MARGIN + (index % columns) * (NODE_WIDTH + COLUMN_GAP),
            block_top + (index // columns) * pitch,
            None,
        )
        for index, node_id in enumerate(loose)
    )

    return Layout(
        nodes=placed_nodes,
        independent=independent,
        edges=placed_edges,
        view_box=view_box_of(placed_nodes + independent, placed_edges),
        crossings=crossings,
    )


def wrap_title(title: str) -> tuple[str, ...]:
    """The title in at most TITLE_MAX_LINES lines of TITLE_LINE_LENGTH characters.

    Words are kept whole when they fit; a word longer than a line is cut. When the title needs
    more lines, the last one is cut and ends with an ellipsis.
    """
    lines: list[str] = []
    current = ""
    for word in title.split():
        while len(word) > TITLE_LINE_LENGTH:
            if current:
                lines.append(current)
                current = ""
            lines.append(word[:TITLE_LINE_LENGTH])
            word = word[TITLE_LINE_LENGTH:]
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= TITLE_LINE_LENGTH:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) <= TITLE_MAX_LINES:
        return tuple(lines)
    kept = lines[:TITLE_MAX_LINES]
    kept[-1] = kept[-1][: TITLE_LINE_LENGTH - len(ELLIPSIS)].rstrip() + ELLIPSIS
    return tuple(kept)


def dependency_edges(graph: Graph) -> list[tuple[int, int, str]]:
    """(source, target, strength) for every dependency, sorted by source and target."""
    edges = []
    for node in graph.nodes.values():
        for dependency in set(dependencies(node)):
            strength = STRONG if dependency in node.strong_dependencies else WEAK
            edges.append((dependency, node.id, strength))
    return sorted(edges)


def assign_layers(graph: Graph, linked: set[int]) -> dict[int, int]:
    """The longest path from the roots to each linked topic."""
    order = study_order(graph, linked)
    if len(order) != len(linked):
        raise ValueError("the graph has a cycle")
    layer_of: dict[int, int] = {}
    for node_id in order:
        layer_of[node_id] = 1 + max((layer_of[dependency] for dependency in dependencies(graph.nodes[node_id])), default=-1)
    return layer_of


def edge_chain(source: int, target: int, layer_of: dict[int, int]) -> tuple[Key, ...]:
    """The keys an edge passes through: the source, one dummy node per layer in between, the target."""
    dummies = tuple((source, target, layer) for layer in range(layer_of[source] + 1, layer_of[target]))
    return (source, *dummies, target)


def group_by_layer(chains, layer_of: dict[int, int]) -> list[list[Key]]:
    """The keys of each layer in their initial order: by id, topics before dummy nodes."""
    keys = {key for chain in chains for key in chain}
    layer_count = max((key_layer(key, layer_of) for key in keys), default=-1) + 1
    layers: list[list[Key]] = [[] for _ in range(layer_count)]
    for key in keys:
        layers[key_layer(key, layer_of)].append(key)
    for layer in layers:
        layer.sort(key=sort_key)
    return layers


def key_layer(key: Key, layer_of: dict[int, int]) -> int:
    return key[2] if isinstance(key, tuple) else layer_of[key]


def sort_key(key: Key) -> tuple:
    return (0, key) if isinstance(key, int) else (1, key)


def neighbours(chains) -> tuple[dict[Key, list[Key]], dict[Key, list[Key]]]:
    """The keys right before (left_of) and right after (right_of) each key, through the edges."""
    left_of: dict[Key, list[Key]] = {}
    right_of: dict[Key, list[Key]] = {}
    for chain in chains:
        for key in chain:
            left_of.setdefault(key, [])
            right_of.setdefault(key, [])
        for left, right in zip(chain, chain[1:]):
            right_of[left].append(right)
            left_of[right].append(left)
    return left_of, right_of


def order_layers(
    layers: list[list[Key]],
    left_of: dict[Key, list[Key]],
    right_of: dict[Key, list[Key]],
    sweeps: int,
) -> tuple[list[list[Key]], int]:
    """The order with the fewest crossings found by the sweeps, and its crossing count."""
    best = [list(layer) for layer in layers]
    best_count = count_crossings(best, right_of)
    current = [list(layer) for layer in layers]
    for sweep in range(sweeps):
        if sweep % 2 == 0:
            for index in range(1, len(current)):
                current[index] = sort_by_barycenter(current[index], current[index - 1], left_of)
        else:
            for index in range(len(current) - 2, -1, -1):
                current[index] = sort_by_barycenter(current[index], current[index + 1], right_of)
        count = count_crossings(current, right_of)
        if count < best_count:
            best = [list(layer) for layer in current]
            best_count = count
    return best, best_count


def sort_by_barycenter(layer: list[Key], reference: list[Key], neighbours_of: dict[Key, list[Key]]) -> list[Key]:
    """The layer sorted by the mean slot of its neighbours in `reference`; ties go by id."""
    reference_slot = {key: slot for slot, key in enumerate(reference)}
    current_slot = {key: slot for slot, key in enumerate(layer)}

    def barycenter(key: Key) -> float:
        slots = [reference_slot[neighbour] for neighbour in neighbours_of[key]]
        return sum(slots) / len(slots) if slots else float(current_slot[key])

    return sorted(layer, key=lambda key: (barycenter(key), sort_key(key)))


def count_crossings(layers: list[list[Key]], right_of: dict[Key, list[Key]]) -> int:
    """Pairs of edges between adjacent layers whose ends are in opposite order."""
    slot = {key: index for layer in layers for index, key in enumerate(layer)}
    total = 0
    for layer in layers:
        edges = [(slot[key], slot[right]) for key in layer for right in right_of[key]]
        for first in range(len(edges)):
            for second in range(first + 1, len(edges)):
                (a1, b1), (a2, b2) = edges[first], edges[second]
                if (a1 - a2) * (b1 - b2) < 0:
                    total += 1
    return total


def column_x(layer: int) -> float:
    return MARGIN + layer * (NODE_WIDTH + COLUMN_GAP)


def place_node(graph: Graph, node_id: int, x: float, y: float, layer: int | None) -> PlacedNode:
    title = graph.nodes[node_id].title
    return PlacedNode(id=node_id, title=title, lines=wrap_title(title), x=x, y=y, layer=layer)


def edge_points(chain: tuple[Key, ...], layer_of: dict[int, int], top_of: dict[Key, float]) -> tuple[Point, ...]:
    """Right middle of the source, the middle of each dummy node, left middle of the target."""
    first, *middle, last = chain
    points: list[Point] = [(column_x(layer_of[first]) + NODE_WIDTH, top_of[first] + NODE_HEIGHT / 2)]
    for key in middle:
        points.append((column_x(key[2]) + NODE_WIDTH / 2, top_of[key] + NODE_HEIGHT / 2))
    points.append((column_x(layer_of[last]), top_of[last] + NODE_HEIGHT / 2))
    return tuple(points)


def view_box_of(nodes: tuple[PlacedNode, ...], edges: tuple[PlacedEdge, ...]) -> tuple[float, float, float, float]:
    """The view box around everything placed, with the margin on the right and at the bottom."""
    right = max([node.x + node.width for node in nodes] + [x for edge in edges for x, _ in edge.points] + [0.0])
    bottom = max([node.y + node.height for node in nodes] + [y for edge in edges for _, y in edge.points] + [0.0])
    return (0.0, 0.0, right + MARGIN, bottom + MARGIN)
