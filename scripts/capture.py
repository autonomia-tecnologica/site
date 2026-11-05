#!/usr/bin/env python3
"""Capture screenshots of a built site on phone and desktop, in light and dark.

For each page it saves a full-page image and one image per listed component
(a CSS selector). It also records the custom properties that compute to nothing
(see browser_checks.py). Everything goes into an output folder with a
manifest.json, which scripts/diff_report.py compares between two runs.

Usage:
  python3 scripts/capture.py --site dist --out tests/visual/out/before
  python3 scripts/capture.py --site dist --out tests/visual/out/after --pages tests/visual/pages.json

Pages file: a JSON list of {"path": "index.html", "components": ["header", "main"]}.
Playwright is required (requirements-dev.txt); the site build does not use this script.
"""

import argparse
import functools
import hashlib
import json
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from browser_checks import find_unresolved_custom_properties  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PAGES = REPO / "tests" / "visual" / "pages.json"
VIEWPORTS = {
    "mobile": {"width": 390, "height": 844},
    "desktop": {"width": 1280, "height": 800},
}
SCHEMES = ("light", "dark")
FULL_PAGE = "full"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def serve(site):
    """Serve the site folder on a free local port; return the running server."""
    handler = functools.partial(_QuietHandler, directory=str(site))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def sha256_of(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def page_slug(path):
    return path.replace("/", "__").replace(".", "_")


def load_pages(pages_file):
    pages = json.loads(pages_file.read_text(encoding="utf-8"))
    for page in pages:
        if "path" not in page:
            raise SystemExit(f"{pages_file}: every page needs a \"path\"")
        page.setdefault("components", [])
    return pages


def capture_shot(page, selector, file_path, out):
    """Save one shot; return its manifest record (file missing if the selector is absent)."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if selector == FULL_PAGE:
        page.screenshot(path=str(file_path), full_page=True, animations="disabled", caret="hide")
    else:
        element = page.query_selector(selector)
        if element is None:
            return {"shot": selector, "file": None, "sha256": None}
        element.screenshot(path=str(file_path), animations="disabled", caret="hide")
    return {
        "shot": selector,
        "file": file_path.relative_to(out).as_posix(),
        "sha256": sha256_of(file_path),
    }


def capture(site, out, pages):
    server = serve(site)
    base_url = f"http://127.0.0.1:{server.server_address[1]}"
    shots = []
    unresolved = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                for viewport_name, size in VIEWPORTS.items():
                    for scheme in SCHEMES:
                        context = browser.new_context(
                            viewport=size,
                            color_scheme=scheme,
                            device_scale_factor=1,
                            reduced_motion="reduce",
                        )
                        for spec in pages:
                            run_id = {"page": spec["path"], "viewport": viewport_name, "scheme": scheme}
                            page = context.new_page()
                            response = page.goto(f"{base_url}/{spec['path']}", wait_until="networkidle")
                            if response is None or response.status >= 400:
                                status = "no response" if response is None else response.status
                                raise SystemExit(f"{spec['path']}: cannot load the page ({status})")
                            page.evaluate("document.fonts.ready.then(() => true)")

                            folder = out / f"{viewport_name}-{scheme}" / page_slug(spec["path"])
                            record = capture_shot(page, FULL_PAGE, folder / "full.png", out)
                            shots.append({**run_id, **record})
                            for index, selector in enumerate(spec["components"]):
                                record = capture_shot(
                                    page, selector, folder / "components" / f"{index}.png", out
                                )
                                shots.append({**run_id, **record})
                            for problem in find_unresolved_custom_properties(page):
                                unresolved.append({**run_id, **problem})
                            page.close()
                        context.close()
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()
    return shots, unresolved


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--site", type=Path, default=REPO / "dist", help="built site folder")
    parser.add_argument("--out", type=Path, required=True, help="output folder for this run")
    parser.add_argument("--pages", type=Path, default=DEFAULT_PAGES, help="JSON list of pages")
    args = parser.parse_args(argv)

    site = args.site.resolve()
    if not (site / "index.html").exists() and not any(site.glob("*.html")):
        raise SystemExit(f"{site}: no HTML found; run the build first")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    shots, unresolved = capture(site, out, load_pages(args.pages))
    manifest = {"shots": shots, "unresolved": unresolved}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"captured {len(shots)} shots into {out}")
    if unresolved:
        print(f"{len(unresolved)} custom property use(s) compute to nothing (see manifest.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
