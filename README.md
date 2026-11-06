# Autonomia Tecnológica — site

Source of the static site of Autonomia Tecnológica. Content is written in Brazilian Portuguese (`pt_BR`),
the only locale for now.

The philosophy of the work environment is in `~/Codes/ambiente-de-trabalho` (`docs/pt_BR/filosofia.md`).
The work environment philosophy lives in `ambiente-de-trabalho` and takes precedence over this repo.
The Autonomia Tecnológica manifesto lives primarily on this site (`i18n/pt_BR.json`, `pages.manifesto.points`).

Status: early. The build turns articles (Markdown with YAML front matter) and page templates into static HTML, with translated
URLs read from `i18n/<locale>.json`, and reports pending text markers (`[a escrever]`).

## Layout

```
content/articles/pt_BR/   articles (Markdown)
i18n/pt_BR.json           all text of pages and interface, and translated URL segments
src/build/                static site builder
templates/                Jinja2 templates (index.html is the home page)
templates/pages/          one template per page (manifesto, about)
```

## Setup

Requires Python 3.11 or newer, and Node.js with npm for the lint step. Python packages live
only in `.venv/`, inside the project; nothing is installed in the operating system.

```
npm run setup
```

The setup creates `.venv/`, installs `requirements.txt` (the build) and `requirements-dev.txt`
(Playwright, for the visual checks) with hash verification, and downloads the Chromium build
that Playwright uses. It can be run again. To remove the environment, delete the `.venv/` folder
and run the setup again. The lint step also needs the npm packages: run `npm ci` once.

Without `.venv/`, the commands below stop with a message that asks to run `npm run setup`.

## Development build

```
.venv/bin/python -m src.build          # development
.venv/bin/python -m src.build --prod   # production: fails while any [a escrever] marker remains
```

`python -m src.build` also works: it runs again with the `.venv/` interpreter.

## Development server

```
npm run dev                          # builds, serves dist/ at http://localhost:8000 and rebuilds on changes
npm run dev -- --port 8080           # same, on another port
```

## Lint and tests

```
npm run lint                         # stylelint and the HTML class check, with the .venv interpreter
python3 scripts/project_python.py -m unittest discover -s tests/build -t tests/build
python3 scripts/project_python.py -m unittest discover -s tests/lint -t tests/lint
python3 scripts/project_python.py -m unittest discover -s tests/visual -t tests/visual -p "test_report.py"
python3 scripts/project_python.py -m unittest discover -s tests/visual -t tests/visual -p "test_nested_token.py"
```

`scripts/project_python.py` runs its arguments with the `.venv/` interpreter. The visual tests
need the Chromium build from `npm run setup`.

The server watches `content/`, `templates/`, `src/` and `i18n/` (checked every half second) and runs
the development build again when a file there changes. A build error is printed in the terminal and
the server keeps running. The server listens on `127.0.0.1` only, uses only the Python standard
library, and stops with Ctrl+C. `SITE_URL` and `SITE_PRIVATE_DIR` are read from the environment, the
same as for the build.

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
  The build publishes a copy of `grafo.json` at `/<lang>/grafo/grafo.json` (for `pt-br`, at
  `/pt-br/grafo/grafo.json`), even while the graph has no topics. It is the same file, under the same
  license; `llms.txt` lists it.
- Photo, logo, visual identity and the name "Autonomia Tecnológica" are **all rights reserved**.
  They are not covered by the licenses above and may not be reused without permission. See [TRADEMARK.md](TRADEMARK.md).
