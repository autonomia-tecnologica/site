"""Renders the checked content to static HTML in dist/.

URLs: /<locale>/ (locale index), /<locale>/<articles>/ (article list),
/<locale>/<articles>/<id>/ (article), /<locale>/<page segment>/ (page), and / (site address:
a redirect to the home page when there is one locale, else a list of the locales).
Every segment comes from i18n/<locale>.json.

Besides the pages, the build writes sitemap.xml, robots.txt, llms.txt, one RSS
feed per locale with articles, and the original Markdown file of every article
next to its page. Canonical URLs, sitemap entries and feeds are absolute and use
the site address given to build_site.

The About page (key "about") shows the private photo, when the build has it, and
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
    IDENTITY_AUTHOR_URL,
    PERSON_PROFILES,
    PERSON_SAME_AS,
    PHOTO_FILE_NAME,
    STYLESHEETS,
)
from .content import HOME_PAGE_KEY, BuildError, Entry

OUTPUT_DIR = "dist"
SCHEMA_CONTEXT = "https://schema.org"
STYLES_DIR = "src/styles"
FONTS_DIR = "src/assets/fonts"
LOGO_DIR = "src/assets/logo"
LOGO_SUFFIXES = (".svg", ".png")
WIKI_LINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")
MANIFESTO_PAGE = "manifesto"
POINT_ANCHOR_PREFIX = "ponto-"
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
    md.core.ruler.push("obsidian_wiki_links", unlink_wiki_links)
    md.core.ruler.push("point_anchors", add_point_anchors)
    md.core.ruler.push("image_captions", add_image_captions)
    md.core.ruler.push("heading_anchors", add_heading_anchors)
    return md


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


def add_point_anchors(state) -> None:
    """Gives id="ponto-N" to each item of the top-level ordered list, when the env asks for it.

    Only the manifesto turns this on (env["point_anchors"]), so its points have fixed links.
    """
    if not state.env.get("point_anchors"):
        return
    number = 0
    in_list = False
    for token in state.tokens:
        if token.level == 0 and token.type == "ordered_list_open":
            in_list = True
        elif token.level == 0 and token.type == "ordered_list_close":
            in_list = False
        elif in_list and token.level == 1 and token.type == "list_item_open":
            number += 1
            token.attrSet("id", f"{POINT_ANCHOR_PREFIX}{number}")


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
        "author": {"@type": "Person", "name": lookup(strings, "person.name", locale), "url": home},
        "publisher": {"@type": "Organization", "name": lookup(strings, "site.name", locale), "url": home},
    }


def render_body(
    markdown: MarkdownIt,
    entry: Entry,
    root: Path,
    warnings: list[str],
    strings: dict,
    locale: str,
    point_anchors: bool = False,
    article: bool = False,
) -> str:
    """HTML of an entry's Markdown body; the warnings name the file they come from.

    An article gets an id on each heading and an index of them, labelled from the site text.
    """
    env: dict = {
        "where": entry.path.relative_to(root).as_posix(),
        "warnings": [],
        "point_anchors": point_anchors,
        "index_label": lookup(strings, "ui.index", locale) if article else None,
        "footnote_back_label": lookup(strings, "ui.footnote_back", locale),
    }
    html = markdown.render(entry.body, env)
    warnings.extend(env["warnings"])
    return html


def about_profiles(strings: dict, locale: str) -> list[dict]:
    """The author's profile links, in the order of PERSON_PROFILES."""
    return [
        {"label": lookup(strings, f"about.profiles.{name}", locale), "href": href}
        for name, href in PERSON_PROFILES.items()
    ]


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
    active = sorted({entry.locale for entry in entries})
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
        if any(e.locale == locale and e.kind == "article" for e in entries):
            segment = lookup(locales[locale], "url.articles", locale)
            add(("articles", locale, ""), f"/{slug(locale)}/{segment}/")
            add(("feed", locale, ""), f"/{slug(locale)}/feed.xml")
    for entry in entries:
        locale = entry.locale
        if entry.kind == "article":
            segment = lookup(locales[locale], "url.articles", locale)
            add(("article", locale, entry.key), f"/{slug(locale)}/{segment}/{entry.key}/")
        else:
            if entry.key == HOME_PAGE_KEY:  # shown on the locale index, no page of its own
                continue
            segment = lookup(locales[locale], f"url.pages.{entry.key}", locale)
            add(("page", locale, entry.key), f"/{slug(locale)}/{segment}/")

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
            ("nav.consulting", ("page", locale, "consulting")),
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
        locale_entries = [e for e in entries if e.locale == locale]
        articles = sorted(
            (e for e in locale_entries if e.kind == "article"),
            key=lambda e: (e.meta["date"], int(e.key)),
            reverse=True,
        )
        home_entry = next((e for e in locale_entries if e.kind == "page" and e.key == HOME_PAGE_KEY), None)
        feed = feed_href(locale)

        render(
            "index.html", locale, ("index", locale, ""), locale_tag,
            alternates=alternates("index", ""),
            channels=CHANNEL_PROFILES,
            seo=page_seo(
                title=site_name,
                description=description if home_entry is None else home_entry.meta["summary"],
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
                    {"title": e.meta["title"], "href": routes[("article", locale, e.key)], "date": e.meta["date"]}
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
        for entry in locale_entries:
            if entry.kind == "page" and entry.key == HOME_PAGE_KEY:
                continue
            url = routes[(entry.kind, locale, entry.key)]
            is_article = entry.kind == "article"
            title = entry.meta["title"]
            if is_article:
                lastmod = entry.meta["updated"].isoformat()
                json_ld = [article_json_ld(strings, locale, entry.meta, absolute(url), home)]
                copies[md_path(url)] = entry.path
            else:
                lastmod = None
                json_ld = []
            is_about = entry.kind == "page" and entry.key == ABOUT_PAGE
            render(
                "entry.html", locale, (entry.kind, locale, entry.key), locale_tag,
                lastmod=lastmod,
                alternates=alternates(entry.kind, entry.key),
                entry={
                    "kind": entry.kind,
                    "title": title,
                    "summary": entry.meta["summary"],
                    "date": entry.meta.get("date"),
                    "updated": entry.meta.get("updated"),
                    "body": render_body(
                        markdown, entry, root, warnings, strings, locale,
                        point_anchors=entry.kind == "page" and entry.key == MANIFESTO_PAGE,
                        article=is_article,
                    ),
                    "photo": (
                        {"href": f"/{PHOTO_DIR}/{PHOTO_FILE_NAME}", "alt": lookup(strings, "about.photo_alt", locale)}
                        if is_about and photo is not None else None
                    ),
                    "profiles": about_profiles(strings, locale) if is_about else [],
                },
                seo=page_seo(
                    title=title,
                    description=entry.meta["summary"],
                    url=url,
                    site_name=site_name,
                    og_type="article" if is_article else "website",
                    locale=locale,
                    hreflang=alternates(entry.kind, entry.key),
                    json_ld=json_ld,
                    feed=feed,
                ),
            )

    # Machine-readable files. llms.txt is built from the front matter only, without a model.
    llms_sections = []
    for locale in active:
        strings = locales[locale]
        locale_entries = [e for e in entries if e.locale == locale]
        articles = sorted(
            (e for e in locale_entries if e.kind == "article"),
            key=lambda e: (e.meta["date"], int(e.key)),
            reverse=True,
        )
        pages_in_lang = sorted(
            (e for e in locale_entries if e.kind == "page" and e.key != HOME_PAGE_KEY), key=lambda e: e.key
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
        if pages_in_lang:
            llms_sections.append({
                "heading": lookup(strings, "seo.llms.pages", locale),
                "entries": [
                    {
                        "title": e.meta["title"],
                        "href": absolute(routes[("page", locale, e.key)]),
                        "summary": e.meta["summary"],
                    }
                    for e in pages_in_lang
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
    for source in sorted((root / FONTS_DIR).iterdir()):
        if source.is_file():
            copies[f"assets/fonts/{source.name}"] = source
    # Logo files: the SVG logotypes, the symbol and the favicon PNG. Nothing else of the art is copied.
    for source in sorted((root / LOGO_DIR).iterdir()):
        if source.suffix in LOGO_SUFFIXES:
            copies[f"assets/logo/{source.name}"] = source
    if photo is not None:
        copies[f"{PHOTO_DIR}/{PHOTO_FILE_NAME}"] = photo
    for rel, source in copies.items():
        target = out_dir.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return html_count
