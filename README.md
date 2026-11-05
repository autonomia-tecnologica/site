# Autonomia Tecnológica — site

Source of the static site of Autonomia Tecnológica. Content is written in Brazilian Portuguese (`pt_BR`),
the only language for now.

Status: skeleton. The build is a development stub that checks the repository layout and reports
pending text markers (`[a escrever]`).

## Layout

```
content/articles/pt_BR/   articles (Markdown)
content/pages/pt_BR/      pages (Markdown)
i18n/pt_BR.json           interface text and translated URL segments
src/build/                build (development stub for now)
```

## Development build

Requires Python 3.11 or newer. No dependencies.

```
python -m src.build          # development
python -m src.build --prod   # production: fails while any [a escrever] marker remains
```

## Licenses

- Code: [MIT](LICENSE).
- Content (articles, pages and `grafo.json`): [CC BY 4.0](LICENSE-CONTENT).
- Photo, logo, visual identity and the name "Autonomia Tecnológica" are **all rights reserved**.
  They are not covered by the licenses above and may not be reused without permission.
