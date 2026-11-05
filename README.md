# Autonomia Tecnológica — site

Source of the static site of Autonomia Tecnológica. Content is written in Brazilian Portuguese (`pt_BR`),
the only language for now.

Status: early. The build turns Markdown with YAML front matter into static HTML, with translated
URLs read from `i18n/<lang>.json`, and reports pending text markers (`[a escrever]`).

## Layout

```
content/articles/pt_BR/   articles (Markdown)
content/pages/pt_BR/      pages (Markdown)
i18n/pt_BR.json           interface text and translated URL segments
src/build/                static site builder
templates/                Jinja2 templates
```

## Development build

Requires Python 3.11 or newer and the dependencies in `pyproject.toml`
(`markdown-it-py`, `Jinja2`, `PyYAML`).

```
python -m src.build          # development
python -m src.build --prod   # production: fails while any [a escrever] marker remains
```

## Private photo

The site photo is not part of this repository and must never be committed to Git. It lives in a
private folder outside the repository, and the environment variable `SITE_PRIVATE_DIR` points to
that folder:

```
export SITE_PRIVATE_DIR="$HOME/Produtividade/Biblioteca/Autonomia Tecnológica/Foto"
```

The folder holds `busto-C.png`, the only approved photo. The development build does not require
`SITE_PRIVATE_DIR` or the folder. Because the folder is outside the repository, `.gitignore` needs
no entry for the photo; do not copy the photo into the repository.

## Licenses

- Code: [MIT](LICENSE).
- Content (articles, pages and `grafo.json`): [CC BY 4.0](LICENSE-CONTENT).
- Photo, logo, visual identity and the name "Autonomia Tecnológica" are **all rights reserved**.
  They are not covered by the licenses above and may not be reused without permission.
