"""Renders the checked content to static HTML in dist/.

URLs: /<lang>/ (language index), /<lang>/<articles>/ (article list),
/<lang>/<articles>/<id>/ (article), /<lang>/<page segment>/ (page), and / (site index).
Every segment comes from i18n/<lang>.json.
"""

import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markdown_it import MarkdownIt

from .content import BuildError, Entry

OUTPUT_DIR = "dist"


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


def build_site(root: Path, languages: dict[str, dict], entries: list[Entry]) -> int:
    """Writes the site to dist/ and returns the number of pages written."""
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
        autoescape=select_autoescape(["html"]),
        undefined=StrictUndefined,
    )
    markdown = MarkdownIt("commonmark", {"html": False})
    # The site index has no language of its own; it uses the first language's interface text.
    root_lang = sorted(languages)[0]
    pages: dict[str, str] = {}

    def alternates(kind: str, key: str) -> list[dict]:
        return [
            {"name": lookup(languages[lang], "language.name", lang), "href": routes[(kind, lang, key)]}
            for lang in active
            if (kind, lang, key) in routes
        ]

    def render(template: str, lang: str, route: tuple[str, str, str], lang_tag: str | None, **context) -> None:
        strings = languages[lang]
        html = env.get_template(template).render(
            t=lambda key: lookup(strings, key, lang),
            lang_tag=lang_tag,
            **context,
        )
        pages[routes[route]] = html

    render("root.html", root_lang, ("root", "", ""), None, alternates=alternates("index", ""))

    for lang in active:
        tag = lang.replace("_", "-")
        lang_entries = [e for e in entries if e.lang == lang]
        articles = sorted(
            (e for e in lang_entries if e.kind == "article"),
            key=lambda e: (e.meta["date"], int(e.key)),
            reverse=True,
        )
        page_entries = sorted((e for e in lang_entries if e.kind == "page"), key=lambda e: e.key)

        render(
            "index.html", lang, ("index", lang, ""), tag,
            alternates=alternates("index", ""),
            pages=[{"title": e.meta["title"], "href": routes[("page", lang, e.key)]} for e in page_entries],
            has_articles=bool(articles),
            articles_href=routes.get(("articles", lang, "")),
        )
        if articles:
            render(
                "articles.html", lang, ("articles", lang, ""), tag,
                alternates=alternates("articles", ""),
                articles=[
                    {"title": e.meta["title"], "href": routes[("article", lang, e.key)], "date": e.meta["date"]}
                    for e in articles
                ],
            )
        for entry in lang_entries:
            render(
                "entry.html", lang, (entry.kind, lang, entry.key), tag,
                alternates=alternates(entry.kind, entry.key),
                entry={
                    "kind": entry.kind,
                    "title": entry.meta["title"],
                    "summary": entry.meta["summary"],
                    "date": entry.meta.get("date"),
                    "updated": entry.meta.get("updated"),
                    "body": markdown.render(entry.body),
                },
            )

    out_dir = root / OUTPUT_DIR
    if out_dir.exists():
        shutil.rmtree(out_dir)
    for url, html in pages.items():
        target = out_dir.joinpath(*url.strip("/").split("/"), "index.html")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
    return len(pages)
