#!/usr/bin/env python3
"""Compare two capture runs and write an HTML report with the before and after images.

The report lists every page and component whose image changed, with the exact
viewport and scheme where it changed, and shows the before and after images
side by side. It also lists the custom properties that compute to nothing in
the after run. The same list is printed to stdout.

Usage:
  python3 scripts/diff_report.py --before tests/visual/out/before \
      --after tests/visual/out/after --report tests/visual/out/report.html

Exit status: 0 when the report is written (changes or not), 2 on bad input.
"""

import argparse
import html
import json
import os
import sys
from pathlib import Path


def load_run(run_dir):
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"{manifest_path}: not found; run scripts/capture.py first")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shots = {}
    for shot in manifest["shots"]:
        key = (shot["page"], shot["viewport"], shot["scheme"], shot["shot"])
        shots[key] = shot
    return shots, manifest.get("unresolved", [])


def compare(before, after):
    """Return {key: status} for every shot whose image was added, removed or changed."""
    changes = {}
    for key in sorted(set(before) | set(after)):
        old = before.get(key, {}).get("sha256")
        new = after.get(key, {}).get("sha256")
        if old == new:
            continue
        if old is None:
            changes[key] = "added"
        elif new is None:
            changes[key] = "removed"
        else:
            changes[key] = "changed"
    return changes


def group_by_page(changes):
    pages = {}
    for (page, viewport, scheme, shot), status in changes.items():
        pages.setdefault(page, []).append((viewport, scheme, shot, status))
    return pages


def describe(entries):
    """Compact text: 'mobile/light, mobile/dark' for the (viewport, scheme) pairs."""
    return ", ".join(sorted({f"{viewport}/{scheme}" for viewport, scheme, _, _ in entries}))


def print_summary(pages, after_unresolved):
    if not pages:
        print("no visual changes")
    else:
        print(f"changed pages: {len(pages)}")
        for page in sorted(pages):
            entries = pages[page]
            full = [e for e in entries if e[2] == "full"]
            components = sorted({e[2] for e in entries if e[2] != "full"})
            print(f"- {page}")
            if full:
                print(f"    full page: {describe(full)}")
            for component in components:
                selected = [e for e in entries if e[2] == component]
                print(f"    component {component}: {describe(selected)}")
    if after_unresolved:
        print(f"custom properties that compute to nothing in the after run: {len(after_unresolved)}")
        for item in after_unresolved:
            print(
                f"- {item['page']} {item['viewport']}/{item['scheme']}: "
                f"{item['name']} on {item['tag']} via {item['selector']}"
            )


def image_cell(run_dir, shot, report_dir):
    if shot is None or shot.get("file") is None:
        return "<p>not captured</p>"
    relative = os.path.relpath(run_dir / shot["file"], report_dir).replace(os.sep, "/")
    return f'<img src="{html.escape(relative)}" alt="" loading="lazy">'


def render_report(before_dir, after_dir, report, before, after, pages, after_unresolved):
    report_dir = report.parent
    parts = [
        "<!doctype html>",
        '<html lang="en">',
        '<head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Visual changes</title>",
        "<style>",
        "body { font-family: system-ui, sans-serif; margin: 16px; background: #fff; color: #111; }",
        "section { margin-block: 32px; border-top: 1px solid #999; padding-top: 16px; }",
        "table { border-collapse: collapse; width: 100%; }",
        "td, th { vertical-align: top; padding: 8px; border: 1px solid #ccc; text-align: left; }",
        "img { max-width: 100%; height: auto; }",
        "</style>",
        "</head>",
        "<body>",
        "<h1>Visual changes</h1>",
        f"<p>Before: <code>{html.escape(str(before_dir))}</code><br>"
        f"After: <code>{html.escape(str(after_dir))}</code></p>",
    ]
    if not pages:
        parts.append("<p>No visual changes.</p>")
    else:
        parts.append(f"<p>Changed pages: {len(pages)}</p>")
    for page in sorted(pages):
        entries = pages[page]
        components = sorted({e[2] for e in entries if e[2] != "full"})
        parts.append(f"<section><h2>{html.escape(page)}</h2>")
        parts.append("<ul>")
        full = [e for e in entries if e[2] == "full"]
        if full:
            parts.append(f"<li>Full page: {html.escape(describe(full))}</li>")
        for component in components:
            selected = [e for e in entries if e[2] == component]
            parts.append(
                f"<li>Component <code>{html.escape(component)}</code>: "
                f"{html.escape(describe(selected))}</li>"
            )
        parts.append("</ul>")
        parts.append("<table><thead><tr><th>Viewport / scheme</th><th>Shot</th>"
                     "<th>Before</th><th>After</th></tr></thead><tbody>")
        for viewport, scheme, shot, _status in sorted(entries):
            key = (page, viewport, scheme, shot)
            parts.append(
                f"<tr><td>{html.escape(viewport)} / {html.escape(scheme)}</td>"
                f"<td>{html.escape(shot)}</td>"
                f"<td>{image_cell(before_dir, before.get(key), report_dir)}</td>"
                f"<td>{image_cell(after_dir, after.get(key), report_dir)}</td></tr>"
            )
        parts.append("</tbody></table></section>")
    if after_unresolved:
        parts.append("<section><h2>Custom properties that compute to nothing</h2><ul>")
        for item in after_unresolved:
            parts.append(
                f"<li>{html.escape(item['page'])} {html.escape(item['viewport'])}/"
                f"{html.escape(item['scheme'])}: <code>{html.escape(item['name'])}</code> "
                f"on <code>{html.escape(item['tag'])}</code> via "
                f"<code>{html.escape(item['selector'])}</code></li>"
            )
        parts.append("</ul></section>")
    parts.append("</body></html>")
    report.write_text("\n".join(parts) + "\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)

    before_dir = args.before.resolve()
    after_dir = args.after.resolve()
    report = args.report.resolve()
    before, _ = load_run(before_dir)
    after, after_unresolved = load_run(after_dir)
    changes = compare(before, after)
    pages = group_by_page(changes)

    report.parent.mkdir(parents=True, exist_ok=True)
    render_report(before_dir, after_dir, report, before, after, pages, after_unresolved)
    print_summary(pages, after_unresolved)
    print(f"report: {report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
