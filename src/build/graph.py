"""The knowledge graph: reads content/graph/grafo.json (version 3), validates it and computes study trails.

A node is a topic. A strong dependency (strong_dependencies) means that studying a topic
without the earlier one can compromise the learning; a weak one (weak_dependencies) only
helps to understand it. The trail of a topic is its dependency closure in study order:
the strong closure is required, the rest of the closure is recommended.

parse_graph and the trail functions are pure. read_graph only reads the file and then
calls parse_graph. Keys the site does not read (domain, used by the AT system) are allowed.
"""

import heapq
import json
from dataclasses import dataclass
from pathlib import Path

from .content import BuildError

GRAPH_VERSION = 3
GRAPH_RELATIVE_PATH = "content/graph/grafo.json"
IGNORED_NODE_KEYS = frozenset({"domain"})
TOP_LEVEL_KEYS = frozenset({"version", "nodes"})
REQUIRED_NODE_KEYS = frozenset({"id", "title", "description", "status", "refs", "strong_dependencies", "weak_dependencies"})
NODE_KEYS = REQUIRED_NODE_KEYS | IGNORED_NODE_KEYS
REF_KEYS = frozenset({"title", "link", "type"})
# Internal links of refs use the short-link kinds of the articles and pages (see site.py).
# They are repeated here so that this module does not depend on the site builder.
INTERNAL_ARTICLE_KIND = "artigo"
INTERNAL_PAGE_KIND = "pagina"
EXTERNAL_LINK_PREFIX = "https://"


class GraphError(BuildError):
    """The graph has problems; `problems` lists each one."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("\n".join(problems))


@dataclass(frozen=True)
class Ref:
    title: str
    link: str
    type: str


@dataclass(frozen=True)
class Node:
    id: int
    title: str
    description: str
    status: str
    refs: tuple[Ref, ...]
    strong_dependencies: tuple[int, ...]
    weak_dependencies: tuple[int, ...]


@dataclass(frozen=True)
class Graph:
    nodes: dict[int, Node]  # sorted by id


@dataclass(frozen=True)
class Trail:
    target: int
    order: tuple[int, ...]  # the closure of the target in study order, the target last
    required: tuple[int, ...]  # the nodes of `order` reached by strong dependencies only

    @property
    def recommended(self) -> tuple[int, ...]:
        """The nodes of `order` that are not required, still in study order."""
        return tuple(node_id for node_id in self.order if node_id not in self.required)


def read_graph(path: Path, article_ids: set[str], page_keys: set[str]) -> Graph:
    """The graph of the file at `path`; raises GraphError with every problem found."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GraphError([f"{path.name}: {exc}"]) from None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GraphError([f"{path.name}: invalid JSON: {exc}"]) from None
    try:
        return parse_graph(data, article_ids, page_keys)
    except GraphError as exc:
        raise GraphError([f"{path.name}: {problem}" for problem in exc.problems]) from None


def parse_graph(data: object, article_ids: set[str], page_keys: set[str]) -> Graph:
    """Validates the decoded JSON of grafo.json and returns the graph.

    `article_ids` are the ids of the articles and `page_keys` the keys of the pages: the
    internal refs must point to one of them. Raises GraphError with every problem found.
    """
    problems: list[str] = []
    if not isinstance(data, dict):
        raise GraphError(["the file must hold a JSON object"])
    check_keys(data, TOP_LEVEL_KEYS, TOP_LEVEL_KEYS, "top level", problems)
    version = data.get("version")
    if type(version) is not int or version != GRAPH_VERSION:
        problems.append(f"version must be {GRAPH_VERSION}, got {version!r}")
    raw_nodes = data.get("nodes", [])
    if not isinstance(raw_nodes, list):
        raise GraphError(problems + ["nodes must be a list"])

    nodes: dict[int, Node] = {}
    for index, raw in enumerate(raw_nodes):
        node = parse_node(raw, index, article_ids, page_keys, problems)
        if node is None:
            continue
        if node.id in nodes:
            problems.append(f"duplicate id {node.id}")
            continue
        nodes[node.id] = node

    for node in nodes.values():
        check_edges(node, nodes, problems)
    adjacency = {
        node.id: sorted(set(dependencies(node)) & (set(nodes) - {node.id})) for node in nodes.values()
    }
    for cycle in find_cycles(adjacency):
        problems.append("cycle: " + " -> ".join(str(node_id) for node_id in cycle))

    if problems:
        raise GraphError(problems)
    return Graph(dict(sorted(nodes.items())))


def parse_node(raw: object, index: int, article_ids: set[str], page_keys: set[str], problems: list[str]) -> Node | None:
    """One node, or None when its id is not usable. Other problems are added to `problems`."""
    if not isinstance(raw, dict):
        problems.append(f"node at index {index} must be an object")
        return None
    node_id = raw.get("id")
    if not is_id(node_id):
        problems.append(f"node at index {index}: id must be a positive integer, got {node_id!r}")
        return None
    where = f"node {node_id}"
    check_keys(raw, NODE_KEYS, REQUIRED_NODE_KEYS, where, problems)
    refs = parse_refs(raw, where, article_ids, page_keys, problems)
    return Node(
        id=node_id,
        title=text_field(raw, "title", where, problems),
        description=text_field(raw, "description", where, problems),
        status=text_field(raw, "status", where, problems),
        refs=refs,
        strong_dependencies=parse_ids(raw, "strong_dependencies", where, problems),
        weak_dependencies=parse_ids(raw, "weak_dependencies", where, problems),
    )


def parse_refs(raw: dict, where: str, article_ids: set[str], page_keys: set[str], problems: list[str]) -> tuple[Ref, ...]:
    if "refs" not in raw:
        return ()
    if not isinstance(raw["refs"], list):
        problems.append(f"{where}: refs must be a list")
        return ()
    refs = []
    for position, item in enumerate(raw["refs"], start=1):
        ref_where = f"{where}, ref {position}"
        if not isinstance(item, dict):
            problems.append(f"{ref_where} must be an object")
            continue
        check_keys(item, REF_KEYS, REF_KEYS, ref_where, problems)
        title = text_field(item, "title", ref_where, problems)
        ref_type = text_field(item, "type", ref_where, problems)
        link = text_field(item, "link", ref_where, problems)
        if link:
            check_link(link, ref_where, article_ids, page_keys, problems)
        refs.append(Ref(title=title, link=link, type=ref_type))
    return tuple(refs)


def check_link(link: str, where: str, article_ids: set[str], page_keys: set[str], problems: list[str]) -> None:
    """A ref link is an external https:// address or an internal artigo:<id> / pagina:<key> that exists."""
    if link.startswith(EXTERNAL_LINK_PREFIX):
        return
    kind, separator, rest = link.partition(":")
    target = rest.partition("#")[0]
    if separator and kind == INTERNAL_ARTICLE_KIND:
        if target not in article_ids:
            problems.append(f"{where}: link {link!r} points to an article that does not exist")
        return
    if separator and kind == INTERNAL_PAGE_KIND:
        if target not in page_keys:
            problems.append(f"{where}: link {link!r} points to a page that does not exist")
        return
    problems.append(
        f"{where}: link {link!r} must be artigo:<id>, pagina:<key> or an address starting with {EXTERNAL_LINK_PREFIX}"
    )


def check_edges(node: Node, nodes: dict[int, Node], problems: list[str]) -> None:
    where = f"node {node.id}"
    for dependency in set(node.strong_dependencies) & set(node.weak_dependencies):
        problems.append(f"{where} lists {dependency} as both strong and weak dependency")
    for dependency in dependencies(node):
        if dependency == node.id:
            problems.append(f"{where} depends on itself")
        elif dependency not in nodes:
            problems.append(f"{where} depends on {dependency}, which does not exist")


def find_cycles(adjacency: dict[int, list[int]]) -> list[list[int]]:
    """Each cycle as a path that starts and ends with the same id, found by depth-first search."""
    cycles: list[list[int]] = []
    state: dict[int, int] = {}  # 1 while on the current path, 2 when finished
    for start in sorted(adjacency):
        if start in state:
            continue
        path = [start]
        iterators = [iter(adjacency[start])]
        state[start] = 1
        while iterators:
            child = next(iterators[-1], None)
            if child is None:
                state[path.pop()] = 2
                iterators.pop()
                continue
            if state.get(child) == 1:
                cycles.append(path[path.index(child):] + [child])
            elif child not in state:
                state[child] = 1
                path.append(child)
                iterators.append(iter(adjacency[child]))
    return cycles


def compute_trail(graph: Graph, target: int) -> Trail:
    """The study trail of `target`: its dependency closure, split into required and recommended."""
    if target not in graph.nodes:
        raise ValueError(f"node {target} is not in the graph")
    closure = reachable(graph, target, strong_only=False)
    strong_closure = reachable(graph, target, strong_only=True)
    order = study_order(graph, closure)
    return Trail(
        target=target,
        order=order,
        required=tuple(node_id for node_id in order if node_id in strong_closure),
    )


def reachable(graph: Graph, start: int, strong_only: bool) -> set[int]:
    """Nodes reached from `start` by following dependencies; with strong_only, only strong ones."""
    seen = {start}
    stack = [start]
    while stack:
        node = graph.nodes[stack.pop()]
        followed = node.strong_dependencies if strong_only else dependencies(node)
        for dependency in followed:
            if dependency not in seen:
                seen.add(dependency)
                stack.append(dependency)
    return seen


def study_order(graph: Graph, node_ids: set[int]) -> tuple[int, ...]:
    """Topological order of `node_ids`: dependencies first, ties broken by the smaller id."""
    remaining = {node_id: len(set(dependencies(graph.nodes[node_id])) & node_ids) for node_id in node_ids}
    dependents: dict[int, list[int]] = {node_id: [] for node_id in node_ids}
    for node_id in node_ids:
        for dependency in set(dependencies(graph.nodes[node_id])) & node_ids:
            dependents[dependency].append(node_id)
    ready = [node_id for node_id, count in remaining.items() if count == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        node_id = heapq.heappop(ready)
        order.append(node_id)
        for dependent in dependents[node_id]:
            remaining[dependent] -= 1
            if remaining[dependent] == 0:
                heapq.heappush(ready, dependent)
    return tuple(order)


def dependencies(node: Node) -> tuple[int, ...]:
    """Strong and weak dependencies of a node, together."""
    return node.strong_dependencies + node.weak_dependencies


def check_keys(raw: dict, allowed: frozenset[str], required: frozenset[str], where: str, problems: list[str]) -> None:
    for key in raw:
        if key not in allowed:
            problems.append(f"{where}: unknown key {key!r}")
    for key in sorted(required):
        if key not in raw:
            problems.append(f"{where}: missing key {key!r}")


def text_field(raw: dict, key: str, where: str, problems: list[str]) -> str:
    """The text of a key, or "" with a problem recorded when it is missing or not a non-empty text."""
    value = raw.get(key)
    if isinstance(value, str) and value.strip():
        return value
    if key in raw:
        problems.append(f"{where}: {key} must be non-empty text")
    return ""


def parse_ids(raw: dict, key: str, where: str, problems: list[str]) -> tuple[int, ...]:
    if key not in raw:
        return ()
    if not isinstance(raw[key], list):
        problems.append(f"{where}: {key} must be a list of ids")
        return ()
    ids = []
    for item in raw[key]:
        if is_id(item):
            ids.append(item)
        else:
            problems.append(f"{where}: {key} has {item!r}, which is not an id")
    return tuple(ids)


def is_id(value: object) -> bool:
    return type(value) is int and value >= 1
