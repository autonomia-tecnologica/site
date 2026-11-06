# CLAUDE.md

Project rules for the Autonomia Tecnológica site. Global rules (`~/.claude/CLAUDE.md`) also apply.

The work environment philosophy is in `~/Codes/ambiente-de-trabalho` (`docs/pt_BR/filosofia.md`). The manifesto
lives primarily on this site, in `i18n/pt_BR.json` (`pages.manifesto.points`); other repos only cite it.

## Text

- Text for humans is never generated. No model writes articles, pages, bios, manifesto points or
  interface copy. Rafael writes it.
- No machine translation without Rafael's decision.
- Pending text is marked `[a escrever]`. The production build fails while any marker remains.
- All user-facing text lives in `i18n/<lang>.json`, never hard-coded in templates or code.
- `pt_BR` is the only language for now. Do not add `en_US` or any other language.
- Articles are files named by a numeric id (`12.md`); the same id across languages links the translations. There are no slugs.

## Layout and URLs

- Folders and file names are in English. Content lives in `content/articles/pt_BR/` and
  `content/pages/pt_BR/`.
- Public URLs use the language code in lowercase with a hyphen (`pt-br`), as `hreflang` expects:
  `/pt-br/artigos/<id>/`.
- Every supported language has its own translated URL (a future en_US would serve
  `/en-us/articles/<id>/`). Translated segments are read from `i18n/<lang>.json` at build time.

## Visual rules

- CSS is plain CSS with custom properties (variables) defined as tokens. No preprocessor, no
  framework.
- A new CSS class needs Rafael's approval.
- Every visual change goes through Rafael, with a list of what changed (pages and components).

## Licenses

- Code: MIT (`LICENSE`).
- Content (articles, pages, `grafo.json`): CC BY 4.0 (`LICENSE-CONTENT`).
- Photo, logo, visual identity and the name "Autonomia Tecnológica" are all rights reserved. They
  are not covered by either license.

## Backlog and commits

- The backlog is `BACKLOG.md` at the repository root, written in pt-BR. It is never committed
  (`/BACKLOG.md` in `.gitignore`).
- Code, comments, logs, documentation and commit messages are in en-US.
- Every commit message ends with the line `AI Generated`. Do not name the model, tool or any co-author.

## Build

- Development: `python -m src.build`. Reports pending markers and exits 0.
- Production: `python -m src.build --prod`. Exits 1 if any `[a escrever]` marker remains.
