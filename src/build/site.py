"""Renders the checked content to static HTML in dist/.

URLs: /<locale>/ (locale index), /<locale>/<articles>/ (article list),
/<locale>/<articles>/<id>/ (article), /<locale>/<page segment>/ (page), and / (site address:
a redirect to the home page when there is one locale, else a list of the locales).
Every segment comes from i18n/<locale>.json.

Besides the pages, the build writes sitemap.xml, robots.txt, llms.txt, one RSS
feed per locale with articles, and the original Markdown file of every article
next to its page. Canonical URLs, sitemap entries and feeds are absolute and use
the site address given to build_site.

The About page (templates/pages/about.html) shows the private photo, when the build has it, and
the author's profile links. The photo is copied to dist/ only when it is given.
"""

import re
import shutil
import unicodedata
from datetime import UTC, date, datetime, time
from email.utils import format_datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markdown_it import MarkdownIt
from markdown_it.common.utils import escapeHtml
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin

from .config import (
    CHANNEL_PROFILES,
    PAGES,
    IDENTITY_AUTHOR_URL,
    PERSON_PROFILES,
    PERSON_SAME_AS,
    PHOTO_FILE_NAME,
    SCRIPTS,
    STYLESHEETS,
)
from .content import BuildError, Entry
from .graph import EXTERNAL_LINK_PREFIX, GRAPH_RELATIVE_PATH, Graph, compute_trail, dependencies, read_graph
from .graph_layout import LINE_HEIGHT, Layout, layout_graph

OUTPUT_DIR = "dist"
# Text in a graph box: inset from the left edge, and the baseline of a line inside its line height.
TEXT_INSET = 12.0
TEXT_BASELINE = 0.7
SCHEMA_CONTEXT = "https://schema.org"
STYLES_DIR = "src/styles"
SCRIPTS_DIR = "src/scripts"
FONTS_DIR = "src/assets/fonts"
LOGO_DIR = "src/assets/logo"
LOGO_SUFFIXES = (".svg", ".png")
WIKI_LINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")
MANIFESTO_PAGE = "manifesto"
# Short links of the text, [text](kind:id). Each kind is the route kind of the page it points to.
# grafo:<id> points to the entry of a node in the knowledge graph page.
CONTENT_LINK_KINDS = {"artigo": "article", "pagina": "page", "grafo": "graph"}
# Kinds that are reserved but do not exist yet: the text stays, without a link, and the build warns.
CONTENT_LINK_PENDING: set[str] = set()
EXTERNAL_SCHEMES = {"http", "https", "mailto", "tel"}
SCHEME_RE = re.compile(r"^([a-z][a-z0-9+.-]*):(.*)$")
FOOTNOTE_CLASS_RE = re.compile(r' class="footnote[\w-]*"')
FOOTNOTE_ID_RE = re.compile(r"fn(?:ref)?[0-9]+")
INDEX_HEADING_TAGS = ("h2", "h3")
DEFAULT_HEADING_ID = "section"


def make_markdown() -> MarkdownIt:
    """CommonMark with tables and footnotes, no raw HTML, and Obsidian [[links]] shown as plain text.

    The site allows only the class names of its vocabulary, so the footnote markup has none.
    """
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.use(footnote_plugin)
    for name in ("footnote_ref", "footnote_block_open", "footnote_open"):
        md.add_render_rule(name, without_footnote_classes(md.renderer.rules[name]))
    md.add_render_rule("footnote_anchor", render_footnote_anchor)
    md.add_render_rule("link_open", open_links_in_new_tab)
    md.add_render_rule("link_close", close_link)
    md.core.ruler.push("content_links", resolve_content_links)
    md.core.ruler.push("obsidian_wiki_links", unlink_wiki_links)
    md.core.ruler.push("image_captions", add_image_captions)
    md.core.ruler.push("heading_anchors", add_heading_anchors)
    return md


def open_links_in_new_tab(self, tokens, idx, options, env) -> str:
    """Links of the text open in a new tab; links to a place in the same page (#...) stay.

    A link marked as unlinked (see resolve_content_links) keeps its text and loses the tag.
    """
    token = tokens[idx]
    if token.meta.get("unlinked"):
        return ""
    href = token.attrGet("href") or ""
    new_tab = not href.startswith("#")
    if new_tab:
        token.attrSet("target", "_blank")
        token.attrSet("rel", "noopener")
    env.setdefault("open_links", []).append(new_tab)  # read back by close_link, in document order
    return self.renderToken(tokens, idx, options, env)


def close_link(self, tokens, idx, options, env) -> str:
    """Closing tag of a link, or nothing when the link was unlinked.

    A link that opens in a new tab ends with a hidden note for screen readers.
    """
    if tokens[idx].meta.get("unlinked"):
        return ""
    new_tab = env["open_links"].pop() if env.get("open_links") else False
    note = f'<span data-sr-only>, {escapeHtml(env["new_tab_label"])}</span>' if new_tab else ""
    return f"{note}</a>"


def resolve_content_links(state) -> None:
    """Turns [text](kind:id) into a link to the page of that kind and id, in the language of the text.

    artigo:12 points to article 12; pagina:manifesto to the page with that key; grafo:3 to the entry of node 3
    in the graph page. A #fragment may follow the id. A missing target or an unknown kind stops the build;
    a kind that is reserved but not built yet keeps the text and logs a warning.
    """
    env = state.env
    routes, locale = env.get("routes"), env.get("locale")
    if routes is None:
        return
    for token in state.tokens:
        if token.type != "inline" or not token.children:
            continue
        opened = []
        for child in token.children:
            if child.type == "link_open":
                opened.append(child)
                match = SCHEME_RE.match(child.attrGet("href") or "")
                if match is None or match.group(1) in EXTERNAL_SCHEMES:
                    continue
                kind, ident = match.groups()
                if kind in CONTENT_LINK_PENDING:
                    child.meta["unlinked"] = True
                    env["warnings"].append(f"{env['where']}: link {kind}:{ident} has no page yet, shown as plain text")
                elif kind in CONTENT_LINK_KINDS:
                    key, _, fragment = ident.partition("#")
                    url = routes.get((CONTENT_LINK_KINDS[kind], locale, key))
                    if url is None:
                        raise BuildError(f"{env['where']}: link {kind}:{ident} points to a page that does not exist")
                    child.attrSet("href", f"{url}#{fragment}" if fragment else url)
                else:
                    raise BuildError(f"{env['where']}: unknown link kind {kind!r} in {kind}:{ident}")
            elif child.type == "link_close" and opened:
                child.meta["unlinked"] = bool(opened.pop().meta.get("unlinked"))


def without_footnote_classes(rule):
    """Wraps a footnote renderer so that its output has no class attribute of the plugin."""

    def render(self, tokens, idx, options, env) -> str:  # bound to the renderer by add_render_rule
        return FOOTNOTE_CLASS_RE.sub("", rule(tokens, idx, options, env))

    return render


def render_footnote_anchor(self, tokens, idx, options, env) -> str:
    """Back link of a note. The plugin's version has no name; this one is labelled from the site text."""
    ident = self.rules["footnote_anchor_name"](tokens, idx, options, env)
    if tokens[idx].meta["subId"] > 0:
        ident += ":" + str(tokens[idx].meta["subId"])
    label = escapeHtml(env["footnote_back_label"])
    return f' <a href="#fnref{ident}" aria-label="{label}">↩︎</a>'


def add_image_captions(state) -> None:
    """Turns a paragraph that holds only an image with a title into a figure with a caption.

    ![alt](src "caption") becomes <figure><img ...><figcaption>caption</figcaption></figure>.
    """
    tokens = state.tokens
    for i in range(len(tokens) - 2):
        opening, inline, closing = tokens[i : i + 3]
        if opening.type != "paragraph_open" or inline.type != "inline" or closing.type != "paragraph_close":
            continue
        children = inline.children or []
        if len(children) != 1 or children[0].type != "image" or "title" not in children[0].attrs:
            continue
        image = children[0]
        caption = image.attrs.pop("title")
        opening.type, opening.tag = "figure_open", "figure"
        closing.type, closing.tag = "figure_close", "figure"
        caption_text = Token("text", "", 0)
        caption_text.content = caption
        inline.children = [
            image,
            Token("figcaption_open", "figcaption", 1),
            caption_text,
            Token("figcaption_close", "figcaption", -1),
        ]


def slugify(text: str) -> str:
    """ASCII id from a heading: accents are dropped, other characters become single hyphens."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-") or DEFAULT_HEADING_ID


def unique_id(base: str, used: set[str]) -> str:
    """base, or base-2, base-3... when it is taken; ids that look like footnote ids are avoided too."""
    candidate, number = base, 1
    while candidate in used or FOOTNOTE_ID_RE.fullmatch(candidate):
        number += 1
        candidate = f"{base}-{number}"
    used.add(candidate)
    return candidate


def add_heading_anchors(state) -> None:
    """Gives an id to each top-level h2 and h3, and puts an index before the body when there are two.

    Only articles turn this on (env["index_label"] is set), so the other pages keep their headings as they are.
    """
    label = state.env.get("index_label")
    if label is None:
        return
    tokens = state.tokens
    used: set[str] = set()
    headings: list[tuple[str, str]] = []
    for i, token in enumerate(tokens):
        if token.type != "heading_open" or token.level != 0 or token.tag not in INDEX_HEADING_TAGS:
            continue
        children = tokens[i + 1].children or []
        text = "".join(child.content for child in children if child.type in ("text", "code_inline"))
        ident = unique_id(slugify(text), used)
        token.attrSet("id", ident)
        headings.append((ident, text))
    if len(headings) >= 2:
        tokens[0:0] = index_tokens(label, headings)


def index_tokens(label: str, headings: list[tuple[str, str]]) -> list[Token]:
    """The index of an article: a nav with one link per heading."""
    nav = Token("index_open", "nav", 1)
    nav.attrSet("aria-label", label)
    tokens = [nav, Token("index_list_open", "ul", 1)]
    for ident, text in headings:
        link = Token("index_link_open", "a", 1)
        link.attrSet("href", f"#{ident}")
        link_text = Token("text", "", 0)
        link_text.content = text
        tokens += [
            Token("index_item_open", "li", 1),
            link,
            link_text,
            Token("index_link_close", "a", -1),
            Token("index_item_close", "li", -1),
        ]
    tokens += [Token("index_list_close", "ul", -1), Token("index_close", "nav", -1)]
    return tokens


def unlink_wiki_links(state) -> None:
    """Obsidian links ([[Note]]) have no target on the site: keep the text, log each one.

    Runs after inline parsing, so code spans and code blocks are not touched.
    """
    for token in state.tokens:
        if token.type != "inline" or not token.children:
            continue
        for child in token.children:
            if child.type != "text" or "[[" not in child.content:
                continue

            def keep_text(match: re.Match) -> str:
                state.env["warnings"].append(
                    f"{state.env['where']}: Obsidian link [[{match.group(1)}]] shown as plain text"
                )
                return match.group(1)

            child.content = WIKI_LINK_RE.sub(keep_text, child.content)
PHOTO_DIR = "assets/photo"
ABOUT_PAGE = "about"


def lookup(strings: dict, dotted: str, locale: str) -> str:
    node: object = strings
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise BuildError(f"i18n/{locale}.json has no text key {dotted!r}")
        node = node[part]
    if not isinstance(node, str):
        raise BuildError(f"i18n/{locale}.json: text key {dotted!r} must be a string")
    return node


def lookup_list(strings: dict, dotted: str, locale: str) -> list[str]:
    """A list of texts of i18n/<locale>.json, like the points of the manifesto."""
    node: object = strings
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise BuildError(f"i18n/{locale}.json has no text key {dotted!r}")
        node = node[part]
    if not isinstance(node, list) or not all(isinstance(item, str) for item in node):
        raise BuildError(f"i18n/{locale}.json: text key {dotted!r} must be a list of strings")
    return node


def slug(locale: str) -> str:
    return locale.lower().replace("_", "-")


def tag(locale: str) -> str:
    return locale.replace("_", "-")


def html_path(url: str) -> str:
    """Output file of an HTML page: /pt-br/ is written to pt-br/index.html."""
    parts = [part for part in url.split("/") if part]
    return "/".join(parts + ["index.html"])


def md_path(url: str) -> str:
    """Output file of an article's original Markdown, next to its index.html."""
    return html_path(url).removesuffix("index.html") + "index.md"


def rfc822(value: date) -> str:
    return format_datetime(datetime.combine(value, time(0, 0), tzinfo=UTC), usegmt=True)


def identity_json_ld(strings: dict, locale: str, home: str) -> dict:
    """Organization and Person of the site, as one JSON-LD graph."""
    return {
        "@context": SCHEMA_CONTEXT,
        "@graph": [
            {
                "@type": "Organization",
                "name": lookup(strings, "site.name", locale),
                "description": lookup(strings, "site.description", locale),
                "url": home,
            },
            {
                "@type": "Person",
                "name": lookup(strings, "person.name", locale),
                "url": home,
                "sameAs": PERSON_SAME_AS,
            },
        ],
    }


def article_json_ld(strings: dict, locale: str, meta: dict, url: str, home: str) -> dict:
    return {
        "@context": SCHEMA_CONTEXT,
        "@type": "Article",
        "headline": meta["title"],
        "description": meta["summary"],
        "inLanguage": tag(locale),
        "datePublished": meta["date"].isoformat(),
        "dateModified": meta["updated"].isoformat(),
        "url": url,
        "mainEntityOfPage": url,
        "author": {"@type": "Person", "name": meta["author"], "url": PERSON_PROFILES["substack"]},
        "publisher": {"@type": "Organization", "name": lookup(strings, "site.name", locale), "url": home},
    }


def render_body(
    markdown: MarkdownIt,
    entry: Entry,
    root: Path,
    warnings: list[str],
    strings: dict,
    locale: str,
    article: bool = False,
    routes: dict | None = None,
) -> str:
    """HTML of an entry's Markdown body; the warnings name the file they come from.

    An article gets an id on each heading and an index of them, labelled from the site text.
    """
    env: dict = {
        "where": entry.path.relative_to(root).as_posix(),
        "warnings": [],
        "routes": routes,
        "locale": locale,
        "index_label": lookup(strings, "ui.index", locale) if article else None,
        "footnote_back_label": lookup(strings, "ui.footnote_back", locale),
        "new_tab_label": lookup(strings, "ui.new_tab", locale),
    }
    html = markdown.render(entry.body, env)
    warnings.extend(env["warnings"])
    return html


HREF_RE = re.compile(r'<a\b[^>]*?\shref="([^"]*)"')
ID_RE = re.compile(r'\sid="([^"]*)"')


def find_broken_links(texts: dict[str, str], files: set[str], site_url: str) -> list[str]:
    """Internal links and anchors of the built pages that lead nowhere.

    texts maps an output path to its page; files holds the other output paths. A link counts as
    internal when it starts with / or with the site address. External links are not checked here.
    """
    broken = []
    for path, html in sorted(texts.items()):
        if not path.endswith(".html"):
            continue
        own_ids = set(ID_RE.findall(html))
        for href in HREF_RE.findall(html):
            href = href.replace("&amp;", "&")
            if href.startswith(site_url):
                href = href[len(site_url):] or "/"
            if href.startswith("#"):
                if href[1:] and href[1:] not in own_ids:
                    broken.append(f"{path}: anchor {href} has no matching id")
                continue
            if not href.startswith("/") or href.startswith("//"):
                continue
            target, _, fragment = href.partition("#")
            target = target.partition("?")[0]
            rel = target.lstrip("/")
            if rel == "" or rel.endswith("/"):
                rel += "index.html"
            if rel not in texts and rel not in files:
                broken.append(f"{path}: link {href} points to {rel}, which is not in the build")
            elif fragment and rel in texts and fragment not in set(ID_RE.findall(texts[rel])):
                broken.append(f"{path}: link {href} points to an id that {rel} does not have")
    return broken


def about_people(strings: dict, locale: str, photo: Path | None) -> list[dict]:
    """The people of the About page: today only the author, with the photo when the build has it."""
    return [{
        "name": lookup(strings, "person.name", locale),
        "bio": lookup(strings, "about.people.rafael.bio", locale),
        "photo": (
            {"href": f"/{PHOTO_DIR}/{PHOTO_FILE_NAME}", "alt": lookup(strings, "about.photo_alt", locale)}
            if photo is not None else None
        ),
        "profiles": about_profiles(strings, locale),
    }]


def about_profiles(strings: dict, locale: str) -> list[dict]:
    """The author's profile links, in the order of PERSON_PROFILES."""
    return [
        {"label": lookup(strings, f"about.profiles.{name}", locale), "href": href}
        for name, href in PERSON_PROFILES.items()
    ]


def dependents_of(graph: Graph) -> dict[int, list[int]]:
    """For each node, the ids of the nodes that depend on it, strong or weak, in id order."""
    result: dict[int, list[int]] = {node_id: [] for node_id in graph.nodes}
    for node in graph.nodes.values():
        for dependency in dependencies(node):
            result[dependency].append(node.id)
    return result


def graph_levels(layout: Layout) -> tuple[list[list[dict]], list[dict]]:
    """The topics that have an edge, by level (the layer of the layout), then the independent ones.

    Each topic is {"id", "title"}. The levels are in study order, and the topics of a level in layout order.
    """
    levels: dict[int, list[dict]] = {}
    for placed in sorted(layout.nodes, key=lambda node: (node.layer, node.y)):
        levels.setdefault(placed.layer, []).append({"id": placed.id, "title": placed.title})
    independent = [{"id": placed.id, "title": placed.title} for placed in layout.independent]
    return [levels[layer] for layer in sorted(levels)], independent


def graph_canvas(layout: Layout, graph: Graph) -> dict:
    """The SVG of the graph: canvas size, the topics that have an edge, and the edges.

    The independent topics are not drawn; they are listed below the canvas. Text is placed in lines
    of the layout, centred in the box. A topic with no refs gets a thin dashed border (has_refs False).
    """
    nodes = []
    for placed in layout.nodes:
        first_baseline = placed.y + (placed.height - len(placed.lines) * LINE_HEIGHT) / 2 + LINE_HEIGHT * TEXT_BASELINE
        nodes.append({
            "id": placed.id,
            "title": placed.title,
            "x": f"{placed.x:g}",
            "y": f"{placed.y:g}",
            "width": f"{placed.width:g}",
            "height": f"{placed.height:g}",
            "has_refs": bool(graph.nodes[placed.id].refs),
            "lines": [
                {"x": f"{placed.x + TEXT_INSET:g}", "y": f"{first_baseline + index * LINE_HEIGHT:g}", "text": line}
                for index, line in enumerate(placed.lines)
            ],
        })
    edges = [
        {"strength": edge.strength, "d": "M" + " L".join(f"{x:g} {y:g}" for x, y in edge.points)}
        for edge in layout.edges
    ]
    min_x, min_y, width, height = layout.view_box
    return {
        "view_box": f"{min_x:g} {min_y:g} {width:g} {height:g}",
        "width": f"{width:g}",
        "height": f"{height:g}",
        "nodes": nodes,
        "edges": edges,
    }


def graph_link(link: str, where: str, locale: str, routes: dict) -> tuple[str, bool]:
    """Where a ref of the graph leads, and whether it leaves the site. An internal target must exist."""
    if link.startswith(EXTERNAL_LINK_PREFIX):
        return link, True
    kind, _, rest = link.partition(":")
    key, _, fragment = rest.partition("#")
    url = routes.get((CONTENT_LINK_KINDS[kind], locale, key))
    if url is None:
        raise BuildError(f"{where}: link {link!r} points to a page that does not exist")
    return (f"{url}#{fragment}" if fragment else url), False


def graph_nodes(graph: Graph, locale: str, routes: dict) -> list[dict]:
    """The topics of the graph page, by id: text, study trail, topics that lead to it, and refs by type."""
    dependents = dependents_of(graph)
    nodes = []
    for node in graph.nodes.values():
        trail = compute_trail(graph, node.id)
        groups: dict[str, list[dict]] = {}
        for ref in node.refs:
            href, external = graph_link(ref.link, f"node {node.id}", locale, routes)
            groups.setdefault(ref.type, []).append({"title": ref.title, "href": href, "external": external})
        nodes.append({
            "id": node.id,
            "title": node.title,
            "description": node.description,
            "trail": [
                {"id": step, "title": graph.nodes[step].title, "required": step in trail.required}
                for step in trail.order if step != node.id
            ],
            "leads_to": [{"id": target, "title": graph.nodes[target].title} for target in dependents[node.id]],
            "refs_by_type": [{"type": ref_type, "refs": refs} for ref_type, refs in groups.items()],
        })
    return nodes


def build_site(
    root: Path,
    locales: dict[str, dict],
    entries: list[Entry],
    site_url: str,
    warnings: list[str],
    photo: Path | None,
) -> int:
    """Writes the site to dist/ and returns the number of HTML pages written.

    Problems that do not stop the build (such as Obsidian links) are appended to warnings.
    photo is the file of the About page photo, or None when the build goes on without it.
    """
    active = sorted(locales)
    routes: dict[tuple[str, str, str], str] = {}
    used_urls: set[str] = set()

    def add(route: tuple[str, str, str], url: str) -> None:
        if url in used_urls:
            raise BuildError(f"two pages would be written to {url}")
        used_urls.add(url)
        routes[route] = url

    add(("root", "", ""), "/")
    for locale in active:
        add(("index", locale, ""), f"/{slug(locale)}/")
        if any(e.locale == locale for e in entries):
            segment = lookup(locales[locale], "url.articles", locale)
            add(("articles", locale, ""), f"/{slug(locale)}/{segment}/")
            add(("feed", locale, ""), f"/{slug(locale)}/feed.xml")
    for entry in entries:
        locale = entry.locale
        segment = lookup(locales[locale], "url.articles", locale)
        add(("article", locale, entry.key), f"/{slug(locale)}/{segment}/{entry.key}/")
    for locale in active:
        for key in PAGES:
            segment = lookup(locales[locale], f"url.pages.{key}", locale)
            add(("page", locale, key), f"/{slug(locale)}/{segment}/")
    # The knowledge graph: no page when it has no topics. Each topic has its own route, a fragment of the page.
    graph = read_graph(root / GRAPH_RELATIVE_PATH, {e.key for e in entries}, set(PAGES))
    if graph.nodes:
        for locale in active:
            segment = lookup(locales[locale], "url.graph", locale)
            add(("graph", locale, ""), f"/{slug(locale)}/{segment}/")
            for node_id in graph.nodes:
                routes[("graph", locale, str(node_id))] = f"{routes[('graph', locale, '')]}#{node_id}"
        layout = layout_graph(graph)
        graph_by_level, graph_independent = graph_levels(layout)
        graph_svg = graph_canvas(layout, graph)

    env = Environment(
        loader=FileSystemLoader(root / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
    )
    env.globals["stylesheets"] = [f"/styles/{name}" for name in STYLESHEETS]
    env.globals["identity_author_url"] = IDENTITY_AUTHOR_URL
    markdown = make_markdown()
    # The site index has no locale of its own; it uses the first locale's interface text.
    root_locale = sorted(locales)[0]
    home = site_url + "/"
    texts: dict[str, str] = {}  # output path under dist/ -> file text
    copies: dict[str, Path] = {}  # output path under dist/ -> file copied byte for byte
    sitemap: list[dict] = []
    html_count = 0

    def absolute(url: str) -> str:
        return site_url + url

    def alternates(kind: str, key: str) -> list[dict]:
        return [
            {
                "name": lookup(locales[locale], "locale.name", locale),
                "tag": tag(locale),
                "href": routes[(kind, locale, key)],
            }
            for locale in active
            if (kind, locale, key) in routes
        ]

    def feed_href(locale: str) -> str | None:
        return routes.get(("feed", locale, ""))

    def page_seo(
        *,
        title: str,
        description: str,
        url: str,
        site_name: str,
        og_type: str = "website",
        locale: str | None = None,
        hreflang: list[dict] | None = None,
        json_ld: list[dict] | None = None,
        feed: str | None = None,
    ) -> dict:
        return {
            "title": title,
            "description": description,
            "canonical": absolute(url),
            "site_name": site_name,
            "og_type": og_type,
            "og_locale": locale,
            "hreflang": [{"tag": alt["tag"], "href": absolute(alt["href"])} for alt in hreflang or []],
            "json_ld": json_ld or [],
            "feed_href": absolute(feed) if feed else None,
        }

    def nav_items(locale: str) -> list[dict]:
        """Main navigation of a locale: only the pages that exist are listed, in this order."""
        strings = locales[locale]
        candidates = (
            ("nav.manifesto", ("page", locale, "manifesto")),
            ("nav.articles", ("articles", locale, "")),
            ("nav.graph", ("graph", locale, "")),
            ("nav.about", ("page", locale, "about")),
        )
        return [
            {"label": lookup(strings, key, locale), "href": routes[route]}
            for key, route in candidates
            if route in routes
        ]

    def render(
        template: str,
        locale: str,
        route: tuple[str, str, str],
        locale_tag: str | None,
        lastmod: str | None = None,
        in_sitemap: bool = True,
        **context,
    ) -> None:
        nonlocal html_count
        strings = locales[locale]
        url = routes[route]
        html = env.get_template(template).render(
            t=lambda key: lookup(strings, key, locale),
            locale_tag=locale_tag,
            nav=nav_items(locale),
            current_href=url,
            home_href=routes.get(("index", locale, ""), "/"),
            **context,
        )
        texts[html_path(url)] = html
        if in_sitemap:
            sitemap.append({"loc": absolute(url), "lastmod": lastmod})
        html_count += 1

    root_strings = locales[root_locale]
    root_name = lookup(root_strings, "site.name", root_locale)
    root_description = lookup(root_strings, "site.description", root_locale)
    if active == [root_locale]:
        # One locale: the site address only redirects to its home page, which is kept out of the sitemap.
        home_url = routes[("index", root_locale, "")]
        render(
            "redirect.html", root_locale, ("root", "", ""), tag(root_locale), in_sitemap=False,
            href=home_url,
            seo=page_seo(title=root_name, description=root_description, url=home_url, site_name=root_name),
        )
    else:
        render(
            "root.html", root_locale, ("root", "", ""), tag(root_locale), in_sitemap=False,
            alternates=alternates("index", ""),
            seo=page_seo(
                title=root_name,
                description=root_description,
                url="/",
                site_name=root_name,
                json_ld=[identity_json_ld(root_strings, root_locale, home)],
            ),
        )

    for locale in active:
        strings = locales[locale]
        site_name = lookup(strings, "site.name", locale)
        description = lookup(strings, "site.description", locale)
        locale_tag = tag(locale)
        articles = sorted(
            (e for e in entries if e.locale == locale),
            key=lambda e: (e.meta["date"], int(e.key)),
            reverse=True,
        )
        feed = feed_href(locale)

        render(
            "index.html", locale, ("index", locale, ""), locale_tag,
            alternates=alternates("index", ""),
            channels=CHANNEL_PROFILES,
            manifesto_href=routes.get(("page", locale, MANIFESTO_PAGE)),
            seo=page_seo(
                title=site_name,
                description=lookup(strings, "pages.home.summary", locale),
                url=routes[("index", locale, "")],
                site_name=site_name,
                locale=locale,
                hreflang=alternates("index", ""),
                json_ld=[identity_json_ld(strings, locale, home)],
                feed=feed,
            ),
        )
        if articles:
            render(
                "articles.html", locale, ("articles", locale, ""), locale_tag,
                alternates=alternates("articles", ""),
                articles=[
                    {
                        "title": e.meta["title"],
                        "href": routes[("article", locale, e.key)],
                        "date": e.meta["date"],
                        "date_label": e.meta["date"].strftime(lookup(strings, "format.date", locale)),
                        "author": {"name": e.meta["author"], "href": routes[("page", locale, ABOUT_PAGE)]},
                        "body": render_body(markdown, e, root, warnings, strings, locale, routes=routes),
                    }
                    for e in articles
                ],
                seo=page_seo(
                    title=lookup(strings, "nav.articles", locale),
                    description=description,
                    url=routes[("articles", locale, "")],
                    site_name=site_name,
                    locale=locale,
                    hreflang=alternates("articles", ""),
                    feed=feed,
                ),
            )
            feed_items = [
                {
                    "title": e.meta["title"],
                    "link": absolute(routes[("article", locale, e.key)]),
                    "description": e.meta["summary"],
                    "pub_date": rfc822(e.meta["date"]),
                }
                for e in articles
            ]
            texts[f"{slug(locale)}/feed.xml"] = env.get_template("feed.xml").render(
                feed={
                    "title": site_name,
                    "link": absolute(routes[("index", locale, "")]),
                    "description": description,
                    "language": slug(locale),
                    "entries": feed_items,
                },
            )
        for entry in articles:
            url = routes[("article", locale, entry.key)]
            copies[md_path(url)] = entry.path
            render(
                "article.html", locale, ("article", locale, entry.key), locale_tag,
                lastmod=entry.meta["updated"].isoformat(),
                alternates=alternates("article", entry.key),
                entry={
                    "title": entry.meta["title"],
                    "summary": entry.meta["summary"],
                    "date": entry.meta["date"],
                    "updated": entry.meta["updated"],
                    "date_label": entry.meta["date"].strftime(lookup(strings, "format.date", locale)),
                    "updated_label": entry.meta["updated"].strftime(lookup(strings, "format.date", locale)),
                    "author": {"name": entry.meta["author"], "href": routes[("page", locale, ABOUT_PAGE)]},
                    "body": render_body(
                        markdown, entry, root, warnings, strings, locale, article=True, routes=routes
                    ),
                },
                seo=page_seo(
                    title=entry.meta["title"],
                    description=entry.meta["summary"],
                    url=url,
                    site_name=site_name,
                    og_type="article",
                    locale=locale,
                    hreflang=alternates("article", entry.key),
                    json_ld=[article_json_ld(strings, locale, entry.meta, absolute(url), home)],
                    feed=feed,
                ),
            )
        for key in PAGES:
            url = routes[("page", locale, key)]
            title = lookup(strings, f"pages.{key}.title", locale)
            extra = {}
            if key == MANIFESTO_PAGE:
                extra["points"] = lookup_list(strings, "pages.manifesto.points", locale)
            elif key == ABOUT_PAGE:
                extra["people"] = about_people(strings, locale, photo)
            render(
                f"pages/{key}.html", locale, ("page", locale, key), locale_tag,
                alternates=alternates("page", key),
                title=title,
                **extra,
                seo=page_seo(
                    title=title,
                    description=lookup(strings, f"pages.{key}.summary", locale),
                    url=url,
                    site_name=site_name,
                    locale=locale,
                    hreflang=alternates("page", key),
                    feed=feed,
                ),
            )
        if graph.nodes:
            title = lookup(strings, "pages.graph.title", locale)
            render(
                "graph.html", locale, ("graph", locale, ""), locale_tag,
                alternates=alternates("graph", ""),
                title=title,
                levels=graph_by_level,
                independent=graph_independent,
                canvas=graph_svg,
                nodes=graph_nodes(graph, locale, routes),
                seo=page_seo(
                    title=title,
                    description=lookup(strings, "pages.graph.summary", locale),
                    url=routes[("graph", locale, "")],
                    site_name=site_name,
                    locale=locale,
                    hreflang=alternates("graph", ""),
                    feed=feed,
                ),
            )

    # Machine-readable files. llms.txt is built from the front matter only, without a model.
    llms_sections = []
    for locale in active:
        strings = locales[locale]
        articles = sorted(
            (e for e in entries if e.locale == locale),
            key=lambda e: (e.meta["date"], int(e.key)),
            reverse=True,
        )
        if articles:
            llms_sections.append({
                "heading": lookup(strings, "nav.articles", locale),
                "entries": [
                    {
                        "title": e.meta["title"],
                        "href": absolute("/" + md_path(routes[("article", locale, e.key)])),
                        "summary": e.meta["summary"],
                    }
                    for e in articles
                ],
            })
        llms_sections.append({
            "heading": lookup(strings, "seo.llms.pages", locale),
            "entries": [
                {
                    "title": lookup(strings, f"pages.{key}.title", locale),
                    "href": absolute(routes[("page", locale, key)]),
                    "summary": lookup(strings, f"pages.{key}.summary", locale),
                }
                for key in PAGES
            ],
        })
    texts["llms.txt"] = env.get_template("llms.txt").render(
        site_name=root_name,
        description=lookup(root_strings, "site.description", root_locale),
        sections=llms_sections,
    )
    texts["robots.txt"] = env.get_template("robots.txt").render(sitemap_url=absolute("/sitemap.xml"))
    texts["sitemap.xml"] = env.get_template("sitemap.xml").render(urls=sitemap)

    out_dir = root / OUTPUT_DIR
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for rel, text in texts.items():
        target = out_dir.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    # Stylesheets and fonts are copied as they are; tokens.css reads the fonts from ../assets/.
    for name in STYLESHEETS:
        source = root / STYLES_DIR / name
        if not source.is_file():
            raise BuildError(f"{STYLES_DIR}/{name} is listed in STYLESHEETS but does not exist")
        copies[f"styles/{name}"] = source
    for name in SCRIPTS:
        source = root / SCRIPTS_DIR / name
        if not source.is_file():
            raise BuildError(f"{SCRIPTS_DIR}/{name} is listed in SCRIPTS but does not exist")
        copies[f"scripts/{name}"] = source
    for source in sorted((root / FONTS_DIR).iterdir()):
        if source.is_file():
            copies[f"assets/fonts/{source.name}"] = source
    # Logo files: the SVG logotypes, the symbol and the favicon PNG. Nothing else of the art is copied.
    for source in sorted((root / LOGO_DIR).iterdir()):
        if source.suffix in LOGO_SUFFIXES:
            copies[f"assets/logo/{source.name}"] = source
    if photo is not None:
        copies[f"{PHOTO_DIR}/{PHOTO_FILE_NAME}"] = photo
    broken = find_broken_links(texts, set(copies), site_url)
    if broken:
        raise BuildError("broken internal links:\n  " + "\n  ".join(broken))
    for rel, source in copies.items():
        target = out_dir.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return html_count
