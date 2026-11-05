"""Renders the checked content to static HTML in dist/.

URLs: /<lang>/ (language index), /<lang>/<articles>/ (article list),
/<lang>/<articles>/<id>/ (article), /<lang>/<page segment>/ (page), and / (site index).
Every segment comes from i18n/<lang>.json.

Besides the pages, the build writes sitemap.xml, robots.txt, llms.txt, one RSS
feed per language with articles, and the original Markdown file of every article
next to its page. Canonical URLs, sitemap entries and feeds are absolute and use
the site address given to build_site.
"""

import re
import shutil
from datetime import UTC, date, datetime, time
from email.utils import format_datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markdown_it import MarkdownIt

from .config import IDENTITY_AUTHOR_URL, PERSON_SAME_AS, STYLESHEETS
from .content import BuildError, Entry

OUTPUT_DIR = "dist"
SCHEMA_CONTEXT = "https://schema.org"
STYLES_DIR = "src/styles"
FONTS_DIR = "src/assets/fonts"
WIKI_LINK_RE = re.compile(r"\[\[([^\[\]\n]+)\]\]")


def make_markdown() -> MarkdownIt:
    """CommonMark with tables, no raw HTML, and Obsidian [[links]] shown as plain text."""
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    md.core.ruler.push("obsidian_wiki_links", unlink_wiki_links)
    return md


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


def lookup(strings: dict, dotted: str, lang: str) -> str:
    node: object = strings
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            raise BuildError(f"i18n/{lang}.json has no text key {dotted!r}")
        node = node[part]
    if not isinstance(node, str):
        raise BuildError(f"i18n/{lang}.json: text key {dotted!r} must be a string")
    return node


def slug(lang: str) -> str:
    return lang.lower().replace("_", "-")


def tag(lang: str) -> str:
    return lang.replace("_", "-")


def html_path(url: str) -> str:
    """Output file of an HTML page: /pt-br/ is written to pt-br/index.html."""
    parts = [part for part in url.split("/") if part]
    return "/".join(parts + ["index.html"])


def md_path(url: str) -> str:
    """Output file of an article's original Markdown, next to its index.html."""
    return html_path(url).removesuffix("index.html") + "index.md"


def rfc822(value: date) -> str:
    return format_datetime(datetime.combine(value, time(0, 0), tzinfo=UTC), usegmt=True)


def identity_json_ld(strings: dict, lang: str, home: str) -> dict:
    """Organization and Person of the site, as one JSON-LD graph."""
    return {
        "@context": SCHEMA_CONTEXT,
        "@graph": [
            {
                "@type": "Organization",
                "name": lookup(strings, "site.name", lang),
                "description": lookup(strings, "site.description", lang),
                "url": home,
            },
            {
                "@type": "Person",
                "name": lookup(strings, "person.name", lang),
                "url": home,
                "sameAs": PERSON_SAME_AS,
            },
        ],
    }


def article_json_ld(strings: dict, lang: str, meta: dict, url: str, home: str) -> dict:
    return {
        "@context": SCHEMA_CONTEXT,
        "@type": "Article",
        "headline": meta["title"],
        "description": meta["summary"],
        "inLanguage": tag(lang),
        "datePublished": meta["date"].isoformat(),
        "dateModified": meta["updated"].isoformat(),
        "url": url,
        "mainEntityOfPage": url,
        "author": {"@type": "Person", "name": lookup(strings, "person.name", lang), "url": home},
        "publisher": {"@type": "Organization", "name": lookup(strings, "site.name", lang), "url": home},
    }


def render_body(markdown: MarkdownIt, entry: Entry, root: Path, warnings: list[str]) -> str:
    """HTML of an entry's Markdown body; the warnings name the file they come from."""
    env: dict = {"where": entry.path.relative_to(root).as_posix(), "warnings": []}
    html = markdown.render(entry.body, env)
    warnings.extend(env["warnings"])
    return html


def build_site(
    root: Path,
    languages: dict[str, dict],
    entries: list[Entry],
    site_url: str,
    warnings: list[str],
) -> int:
    """Writes the site to dist/ and returns the number of HTML pages written.

    Problems that do not stop the build (such as Obsidian links) are appended to warnings.
    """
    active = sorted({entry.lang for entry in entries})
    routes: dict[tuple[str, str, str], str] = {}
    used_urls: set[str] = set()

    def add(route: tuple[str, str, str], url: str) -> None:
        if url in used_urls:
            raise BuildError(f"two pages would be written to {url}")
        used_urls.add(url)
        routes[route] = url

    add(("root", "", ""), "/")
    for lang in active:
        add(("index", lang, ""), f"/{slug(lang)}/")
        if any(e.lang == lang and e.kind == "article" for e in entries):
            segment = lookup(languages[lang], "url.articles", lang)
            add(("articles", lang, ""), f"/{slug(lang)}/{segment}/")
            add(("feed", lang, ""), f"/{slug(lang)}/feed.xml")
    for entry in entries:
        lang = entry.lang
        if entry.kind == "article":
            segment = lookup(languages[lang], "url.articles", lang)
            add(("article", lang, entry.key), f"/{slug(lang)}/{segment}/{entry.key}/")
        else:
            segment = lookup(languages[lang], f"url.pages.{entry.key}", lang)
            add(("page", lang, entry.key), f"/{slug(lang)}/{segment}/")

    env = Environment(
        loader=FileSystemLoader(root / "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
    )
    env.globals["stylesheets"] = [f"/styles/{name}" for name in STYLESHEETS]
    env.globals["identity_author_url"] = IDENTITY_AUTHOR_URL
    markdown = make_markdown()
    # The site index has no language of its own; it uses the first language's interface text.
    root_lang = sorted(languages)[0]
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
                "name": lookup(languages[lang], "language.name", lang),
                "tag": tag(lang),
                "href": routes[(kind, lang, key)],
            }
            for lang in active
            if (kind, lang, key) in routes
        ]

    def feed_href(lang: str) -> str | None:
        return routes.get(("feed", lang, ""))

    def page_seo(
        *,
        title: str,
        description: str,
        url: str,
        site_name: str,
        og_type: str = "website",
        lang: str | None = None,
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
            "og_locale": lang,
            "hreflang": [{"tag": alt["tag"], "href": absolute(alt["href"])} for alt in hreflang or []],
            "json_ld": json_ld or [],
            "feed_href": absolute(feed) if feed else None,
        }

    def nav_items(lang: str) -> list[dict]:
        """Main navigation of a language: only the pages that exist are listed, in this order."""
        strings = languages[lang]
        candidates = (
            ("nav.home", ("index", lang, "")),
            ("nav.manifesto", ("page", lang, "manifesto")),
            ("nav.articles", ("articles", lang, "")),
            ("nav.consulting", ("page", lang, "consulting")),
            ("nav.about", ("page", lang, "about")),
        )
        return [
            {"label": lookup(strings, key, lang), "href": routes[route]}
            for key, route in candidates
            if route in routes
        ]

    def render(
        template: str,
        lang: str,
        route: tuple[str, str, str],
        lang_tag: str | None,
        lastmod: str | None = None,
        **context,
    ) -> None:
        nonlocal html_count
        strings = languages[lang]
        url = routes[route]
        html = env.get_template(template).render(
            t=lambda key: lookup(strings, key, lang),
            lang_tag=lang_tag,
            nav=nav_items(lang),
            current_href=url,
            **context,
        )
        texts[html_path(url)] = html
        sitemap.append({"loc": absolute(url), "lastmod": lastmod})
        html_count += 1

    root_strings = languages[root_lang]
    root_name = lookup(root_strings, "site.name", root_lang)
    render(
        "root.html", root_lang, ("root", "", ""), tag(root_lang),
        alternates=alternates("index", ""),
        seo=page_seo(
            title=root_name,
            description=lookup(root_strings, "site.description", root_lang),
            url="/",
            site_name=root_name,
            json_ld=[identity_json_ld(root_strings, root_lang, home)],
        ),
    )

    for lang in active:
        strings = languages[lang]
        site_name = lookup(strings, "site.name", lang)
        description = lookup(strings, "site.description", lang)
        lang_tag = tag(lang)
        lang_entries = [e for e in entries if e.lang == lang]
        articles = sorted(
            (e for e in lang_entries if e.kind == "article"),
            key=lambda e: (e.meta["date"], int(e.key)),
            reverse=True,
        )
        page_entries = sorted((e for e in lang_entries if e.kind == "page"), key=lambda e: e.key)
        feed = feed_href(lang)

        render(
            "index.html", lang, ("index", lang, ""), lang_tag,
            alternates=alternates("index", ""),
            pages=[{"title": e.meta["title"], "href": routes[("page", lang, e.key)]} for e in page_entries],
            has_articles=bool(articles),
            articles_href=routes.get(("articles", lang, "")),
            seo=page_seo(
                title=site_name,
                description=description,
                url=routes[("index", lang, "")],
                site_name=site_name,
                lang=lang,
                hreflang=alternates("index", ""),
                json_ld=[identity_json_ld(strings, lang, home)],
                feed=feed,
            ),
        )
        if articles:
            render(
                "articles.html", lang, ("articles", lang, ""), lang_tag,
                alternates=alternates("articles", ""),
                articles=[
                    {"title": e.meta["title"], "href": routes[("article", lang, e.key)], "date": e.meta["date"]}
                    for e in articles
                ],
                seo=page_seo(
                    title=lookup(strings, "nav.articles", lang),
                    description=description,
                    url=routes[("articles", lang, "")],
                    site_name=site_name,
                    lang=lang,
                    hreflang=alternates("articles", ""),
                    feed=feed,
                ),
            )
            feed_items = [
                {
                    "title": e.meta["title"],
                    "link": absolute(routes[("article", lang, e.key)]),
                    "description": e.meta["summary"],
                    "pub_date": rfc822(e.meta["date"]),
                }
                for e in articles
            ]
            texts[f"{slug(lang)}/feed.xml"] = env.get_template("feed.xml").render(
                feed={
                    "title": site_name,
                    "link": absolute(routes[("index", lang, "")]),
                    "description": description,
                    "language": slug(lang),
                    "entries": feed_items,
                },
            )
        for entry in lang_entries:
            url = routes[(entry.kind, lang, entry.key)]
            is_article = entry.kind == "article"
            title = entry.meta["title"]
            if is_article:
                lastmod = entry.meta["updated"].isoformat()
                json_ld = [article_json_ld(strings, lang, entry.meta, absolute(url), home)]
                copies[md_path(url)] = entry.path
            else:
                lastmod = None
                json_ld = []
            render(
                "entry.html", lang, (entry.kind, lang, entry.key), lang_tag,
                lastmod=lastmod,
                alternates=alternates(entry.kind, entry.key),
                entry={
                    "kind": entry.kind,
                    "title": title,
                    "summary": entry.meta["summary"],
                    "date": entry.meta.get("date"),
                    "updated": entry.meta.get("updated"),
                    "body": render_body(markdown, entry, root, warnings),
                },
                seo=page_seo(
                    title=title,
                    description=entry.meta["summary"],
                    url=url,
                    site_name=site_name,
                    og_type="article" if is_article else "website",
                    lang=lang,
                    hreflang=alternates(entry.kind, entry.key),
                    json_ld=json_ld,
                    feed=feed,
                ),
            )

    # Machine-readable files. llms.txt is built from the front matter only, without a model.
    llms_sections = []
    for lang in active:
        strings = languages[lang]
        lang_entries = [e for e in entries if e.lang == lang]
        articles = sorted(
            (e for e in lang_entries if e.kind == "article"),
            key=lambda e: (e.meta["date"], int(e.key)),
            reverse=True,
        )
        pages_in_lang = sorted((e for e in lang_entries if e.kind == "page"), key=lambda e: e.key)
        if articles:
            llms_sections.append({
                "heading": lookup(strings, "nav.articles", lang),
                "entries": [
                    {
                        "title": e.meta["title"],
                        "href": absolute("/" + md_path(routes[("article", lang, e.key)])),
                        "summary": e.meta["summary"],
                    }
                    for e in articles
                ],
            })
        if pages_in_lang:
            llms_sections.append({
                "heading": lookup(strings, "seo.llms.pages", lang),
                "entries": [
                    {
                        "title": e.meta["title"],
                        "href": absolute(routes[("page", lang, e.key)]),
                        "summary": e.meta["summary"],
                    }
                    for e in pages_in_lang
                ],
            })
    texts["llms.txt"] = env.get_template("llms.txt").render(
        site_name=root_name,
        description=lookup(root_strings, "site.description", root_lang),
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
    for rel, source in copies.items():
        target = out_dir.joinpath(*rel.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return html_count
