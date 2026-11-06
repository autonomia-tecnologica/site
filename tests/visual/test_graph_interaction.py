"""The knowledge graph page in a browser: a topic opens without a jump, the URL keeps the history,
the study trail is marked with its order, Esc gives the focus back to the topic's link, the arrow
keys move between the topics, and nothing is written to the browser storage. Without script the
fragment still opens a topic.

The site is built in a temporary folder from tests/build/fixtures/graph/examples.json, so the
repository's dist/ is never touched. Screenshots of the highlighted states go to
tests/visual/out/graph-interaction/ (not versioned) for the visual approval.

Run from the repository root, after `npm run setup`:

    python3 scripts/project_python.py -m unittest discover -s tests/visual -t tests/visual -p "test_graph_interaction.py"
"""

import functools
import sys
import tempfile
import threading
import unittest
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))
from project_python import relaunch_in_venv  # noqa: E402

relaunch_in_venv()

sys.path.insert(0, str(REPO))
from playwright.sync_api import sync_playwright  # noqa: E402

from src.build.content import load_entries, load_locales  # noqa: E402
from src.build.site import build_site  # noqa: E402

FIXTURE = REPO / "tests" / "build" / "fixtures" / "graph" / "examples.json"
OUT = REPO / "tests" / "visual" / "out" / "graph-interaction"
PAGE = "/pt-br/grafo/"
DESKTOP = {"width": 1280, "height": 800}
MOBILE = {"width": 390, "height": 844}
STORAGE_COUNT = "[window.localStorage.length, window.sessionStorage.length]"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def build_graph_site(root: Path) -> None:
    """Builds the site with the fixture graph; the templates, i18n and src are linked from the repository."""
    for name in ("templates", "i18n", "src"):
        (root / name).symlink_to(REPO / name)
    (root / "content" / "graph").mkdir(parents=True)
    (root / "content" / "graph" / "grafo.json").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    (root / "content" / "articles" / "pt_BR").mkdir(parents=True)
    # The fixture's refs point to article 1.
    (root / "content" / "articles" / "pt_BR" / "1.md").write_text(
        "---\ntitle: Artigo de teste\ndate: 2026-01-01\nupdated: 2026-01-01\n"
        "summary: Resumo do artigo de teste.\nauthor: Autor de teste\n---\nTexto.\n",
        encoding="utf-8",
    )
    errors: list[str] = []
    locales = load_locales(root, errors)
    entries = load_entries(root, locales, errors)
    assert not errors, errors
    build_site(root, locales, entries, "http://localhost", [], None)


class GraphInteractionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        build_graph_site(Path(cls.tmp.name))
        handler = functools.partial(_QuietHandler, directory=str(Path(cls.tmp.name) / "dist"))
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()
        OUT.mkdir(parents=True, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def open(self, path, viewport=DESKTOP, script=True, scheme="light"):
        context = self.browser.new_context(
            viewport=viewport, java_script_enabled=script, color_scheme=scheme,
        )
        self.addCleanup(context.close)
        page = context.new_page()
        page.goto(self.base + path)
        return page

    def visible_topics(self, page):
        return page.eval_on_selector_all(
            "article[data-node]", "els => els.filter(e => getComputedStyle(e).display !== 'none').map(e => e.id)",
        )

    def link(self, page, node_id):
        return page.locator(f"[data-node-link][href='#{node_id}']")

    def active_href(self, page):
        return page.evaluate("document.activeElement.getAttribute('href')")

    def assert_trail_marked(self, page, node_id, minimum):
        trail = page.eval_on_selector_all(
            f"article[id='{node_id}'] ol[data-trail] > li > a", "els => els.map(e => e.getAttribute('href'))",
        )
        self.assertGreaterEqual(len(trail), minimum)
        marked = page.eval_on_selector_all(
            "[data-node-link][data-trail]",
            "els => els.map(e => [e.getAttribute('href'), e.getAttribute('data-trail')])",
        )
        # Marks come back in canvas order; sorted by their number they must follow the list.
        marked.sort(key=lambda pair: int(pair[1]))
        self.assertEqual(marked, [[href, str(i + 1)] for i, href in enumerate(trail)])
        badges = page.eval_on_selector_all("[data-trail-badge='label']", "els => els.map(e => e.textContent)")
        self.assertEqual(sorted(badges, key=int), [str(i + 1) for i in range(len(trail))])

    def test_hash_opens_topic_and_marks_its_trail_with_order(self):
        page = self.open(PAGE + "#3")
        self.assertEqual(self.visible_topics(page), ["3"])
        self.assert_trail_marked(page, "3", minimum=1)
        page.screenshot(path=str(OUT / "desktop-light-topic-3.png"), full_page=True)

    def test_trail_with_several_steps_is_numbered_in_list_order(self):
        # Topic 1 has several steps (4, 3, 2, 6 in the fixture): the badges follow the list.
        page = self.open(PAGE + "#1")
        self.assertEqual(self.visible_topics(page), ["1"])
        self.assert_trail_marked(page, "1", minimum=3)

    def test_trail_filter_shows_only_required_steps_and_marks_them(self):
        # Topic 1 in the fixture: the trail is 4, 3 (recommended), 2, 6 (required), in that order.
        page = self.open(PAGE + "#1")
        self.assertTrue(page.locator("[data-trail-filter]").is_visible())
        steps = "article[id='1'] ol[data-trail] > li"
        self.assertEqual(
            page.eval_on_selector_all(steps, "els => els.map(e => e.getAttribute('data-strength'))"),
            ["weak", "weak", "strong", "strong"],
        )
        page.locator("[data-trail-filter] input[value='strong']").check()
        shown = page.eval_on_selector_all(
            steps, "els => els.filter(e => !e.hidden).map(e => e.querySelector('a').getAttribute('href'))",
        )
        self.assertEqual(shown, ["#2", "#6"])
        marked = page.eval_on_selector_all(
            "[data-node-link][data-trail]",
            "els => els.map(e => [e.getAttribute('href'), e.getAttribute('data-trail')])",
        )
        self.assertEqual(sorted(marked, key=lambda pair: int(pair[1])), [["#2", "1"], ["#6", "2"]])
        badges = page.eval_on_selector_all("[data-trail-badge='label']", "els => els.map(e => e.textContent)")
        self.assertEqual(sorted(badges, key=int), ["1", "2"])
        self.assertEqual(page.evaluate(STORAGE_COUNT), [0, 0])
        page.screenshot(path=str(OUT / "desktop-light-topic-1-strong.png"), full_page=True)

        page.locator("[data-trail-filter] input[value='all']").check()
        self.assertEqual(len(page.eval_on_selector_all(steps, "els => els.filter(e => !e.hidden)")), 4)
        self.assert_trail_marked(page, "1", minimum=4)
        self.assertEqual(page.evaluate(STORAGE_COUNT), [0, 0])

    def test_trail_filter_hides_the_trail_when_no_step_is_required(self):
        # Topic 2 only has recommended steps; topic 4 has no trail, so the filter is not offered.
        page = self.open(PAGE + "#2")
        page.locator("[data-trail-filter] input[value='strong']").check()
        self.assertTrue(page.eval_on_selector("article[id='2'] [data-trail-block]", "e => e.hidden"))
        self.assertEqual(page.eval_on_selector_all("[data-node-link][data-trail]", "els => els.length"), 0)
        page.locator("[data-trail-filter] input[value='all']").check()
        self.assertFalse(page.eval_on_selector("article[id='2'] [data-trail-block]", "e => e.hidden"))
        self.open(PAGE + "#4").locator("[data-trail-filter]").wait_for(state="hidden")

    def test_click_selects_without_jump_and_pushes_history(self):
        page = self.open(PAGE)
        self.assertEqual(self.visible_topics(page), [])
        link = self.link(page, 3)
        link.scroll_into_view_if_needed()
        scroll_before = page.evaluate("window.scrollY")
        history_before = page.evaluate("history.length")
        link.click()
        self.assertEqual(self.visible_topics(page), ["3"])
        self.assertTrue(page.url.endswith("#3"), page.url)
        self.assertEqual(page.evaluate("history.length"), history_before + 1)
        self.assertEqual(page.evaluate("window.scrollY"), scroll_before)
        self.assertEqual(page.evaluate("document.activeElement.tagName.toLowerCase()"), "h2")
        self.assertEqual(page.evaluate("document.activeElement.closest('article').id"), "3")
        self.assertEqual(page.evaluate(STORAGE_COUNT), [0, 0])

    def test_back_restores_the_previous_topic(self):
        page = self.open(PAGE)
        self.link(page, 3).click()
        self.link(page, 4).click()
        self.assertEqual(self.visible_topics(page), ["4"])
        page.go_back()
        self.assertTrue(page.url.endswith("#3"), page.url)
        self.assertEqual(self.visible_topics(page), ["3"])
        page.go_back()
        self.assertNotIn("#", page.url)
        self.assertEqual(self.visible_topics(page), [])
        page.go_forward()
        self.assertEqual(self.visible_topics(page), ["3"])

    def test_escape_closes_and_gives_the_focus_back_to_the_node(self):
        page = self.open(PAGE)
        self.link(page, 3).click()
        page.keyboard.press("Escape")
        self.assertEqual(self.visible_topics(page), [])
        self.assertNotIn("#", page.url)
        self.assertEqual(self.active_href(page), "#3")
        self.assertEqual(page.evaluate("document.activeElement.hasAttribute('data-node-link')"), True)
        self.assertEqual(page.evaluate(STORAGE_COUNT), [0, 0])

    def test_escape_does_not_reopen_a_topic_opened_by_the_hash(self):
        # The fragment still matches :target after Esc, so the script's state must win.
        page = self.open(PAGE + "#3")
        page.keyboard.press("Escape")
        self.assertEqual(self.visible_topics(page), [])
        self.assertEqual(page.eval_on_selector_all("[data-node-link][data-trail]", "els => els.length"), 0)

    def test_arrow_keys_move_focus_between_topics(self):
        page = self.open(PAGE)
        hrefs = page.eval_on_selector_all("[data-node-link]", "els => els.map(e => e.getAttribute('href'))")
        self.link(page, hrefs[0][1:]).focus()
        page.keyboard.press("ArrowRight")
        self.assertEqual(self.active_href(page), hrefs[1])
        page.keyboard.press("ArrowLeft")
        self.assertEqual(self.active_href(page), hrefs[0])
        self.assertEqual(self.visible_topics(page), [])

    def test_layout_puts_the_panel_beside_the_canvas_or_below_it(self):
        desktop = self.open(PAGE + "#3", viewport=DESKTOP)
        self.assertEqual(desktop.eval_on_selector("[data-panel]", "e => getComputedStyle(e).position"), "sticky")
        self.assertEqual(desktop.eval_on_selector("[data-canvas-wrap]", "e => getComputedStyle(e).display"), "block")
        mobile = self.open(PAGE + "#3", viewport=MOBILE)
        self.assertEqual(mobile.eval_on_selector("[data-panel]", "e => getComputedStyle(e).position"), "fixed")
        self.assertEqual(mobile.eval_on_selector("[data-canvas-wrap]", "e => getComputedStyle(e).display"), "block")
        mobile.screenshot(path=str(OUT / "mobile-light-topic-3.png"), full_page=True)
        self.open(PAGE + "#3", viewport=MOBILE, scheme="dark").screenshot(
            path=str(OUT / "mobile-dark-topic-3.png"), full_page=True,
        )
        self.open(PAGE, viewport=MOBILE).screenshot(path=str(OUT / "mobile-light-canvas.png"), full_page=True)
        self.open(PAGE, viewport=MOBILE, scheme="dark").screenshot(
            path=str(OUT / "mobile-dark-canvas.png"), full_page=True,
        )
        self.open(PAGE, viewport=DESKTOP, scheme="dark").screenshot(
            path=str(OUT / "desktop-dark-topic-3.png"), full_page=True,
        )

    def touch(self, page, kind, pointer_id, x, y):
        page.evaluate(
            """([kind, id, x, y]) => document.querySelector('[data-canvas-wrap]').dispatchEvent(
                new PointerEvent(kind, {pointerId: id, pointerType: 'touch', isPrimary: id === 1,
                    clientX: x, clientY: y, bubbles: true}))""",
            [kind, pointer_id, x, y],
        )

    def test_mobile_canvas_is_shown_at_natural_size_and_scrolls_sideways(self):
        page = self.open(PAGE, viewport=MOBILE)
        self.assertTrue(page.locator("[data-canvas-wrap]").is_visible())
        self.assertTrue(page.locator("[data-list]").is_visible())
        # Natural size: the canvas is drawn at its width attribute, wider than the phone.
        drawn = page.eval_on_selector("[data-canvas]", "e => [e.getAttribute('width'), e.getBoundingClientRect().width]")
        self.assertAlmostEqual(float(drawn[0]), drawn[1], delta=1)
        self.assertGreater(drawn[1], MOBILE["width"])
        self.assertGreater(page.eval_on_selector("[data-canvas-wrap]", "e => e.scrollWidth - e.clientWidth"), 0)
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), MOBILE["width"])
        self.assertEqual(page.eval_on_selector("[data-canvas-wrap]", "e => getComputedStyle(e).touchAction"), "none")

    def test_mobile_open_node_is_scrolled_above_the_sheet(self):
        page = self.open(PAGE, viewport=MOBILE)
        self.link(page, 3).click()
        self.assertEqual(self.visible_topics(page), ["3"])
        box = page.eval_on_selector(
            "[data-node-link][href='#3'] [data-node-box]",
            """e => {
                const r = e.getBoundingClientRect();
                const wrap = e.closest('[data-canvas-wrap]').getBoundingClientRect();
                return {top: r.top, bottom: r.bottom, left: r.left, right: r.right,
                    wrapLeft: wrap.left, wrapRight: wrap.right,
                    sheet: document.querySelector('[data-panel]').getBoundingClientRect().top};
            }""",
        )
        self.assertGreaterEqual(box["top"], 0)
        self.assertLessEqual(box["bottom"], box["sheet"])
        self.assertGreaterEqual(box["left"], box["wrapLeft"])
        self.assertLessEqual(box["right"], box["wrapRight"])
        self.assertEqual(page.evaluate("document.activeElement.tagName.toLowerCase()"), "h2")

    def test_mobile_one_finger_pans_the_canvas(self):
        page = self.open(PAGE, viewport=MOBILE)
        self.assertGreater(page.eval_on_selector("[data-canvas-wrap]", "e => e.scrollWidth - e.clientWidth"), 50)
        self.touch(page, "pointerdown", 1, 200, 300)
        self.touch(page, "pointermove", 1, 150, 200)
        self.touch(page, "pointerup", 1, 150, 200)
        self.assertEqual(page.eval_on_selector("[data-canvas-wrap]", "e => e.scrollLeft"), 50)
        self.assertEqual(page.evaluate("window.scrollY"), 100)
        self.assertEqual(page.evaluate(STORAGE_COUNT), [0, 0])

    def test_mobile_pinch_zooms_the_canvas_up_to_three_times(self):
        page = self.open(PAGE, viewport=MOBILE)
        base = float(page.eval_on_selector("[data-canvas]", "e => e.getAttribute('width')"))
        self.touch(page, "pointerdown", 1, 100, 300)
        self.touch(page, "pointerdown", 2, 200, 300)
        self.touch(page, "pointermove", 2, 250, 300)  # 100 px apart to 150 px: 1.5x
        self.assertAlmostEqual(float(page.eval_on_selector("[data-canvas]", "e => e.getAttribute('width')")), base * 1.5, delta=1)
        self.touch(page, "pointermove", 2, 300, 300)  # 200 px: 2x
        self.assertAlmostEqual(float(page.eval_on_selector("[data-canvas]", "e => e.getAttribute('width')")), base * 2, delta=1)
        self.touch(page, "pointermove", 2, 1000, 300)  # clamped at 3x
        self.assertAlmostEqual(float(page.eval_on_selector("[data-canvas]", "e => e.getAttribute('width')")), base * 3, delta=1)
        self.touch(page, "pointerup", 2, 1000, 300)
        self.touch(page, "pointerup", 1, 100, 300)
        self.assertEqual(page.evaluate(STORAGE_COUNT), [0, 0])

    def test_mobile_without_script_scrolls_without_zoom(self):
        page = self.open(PAGE, viewport=MOBILE, script=False)
        self.assertTrue(page.locator("[data-canvas-wrap]").is_visible())
        self.assertEqual(page.eval_on_selector("[data-canvas-wrap]", "e => getComputedStyle(e).touchAction"), "auto")
        self.assertGreater(page.eval_on_selector("[data-canvas-wrap]", "e => e.scrollWidth - e.clientWidth"), 0)

    def test_without_script_the_fragment_still_opens_a_topic(self):
        page = self.open(PAGE + "#3", script=False)
        self.assertEqual(self.visible_topics(page), ["3"])
        self.assertEqual(page.eval_on_selector("[data-panel]", "e => getComputedStyle(e).display"), "block")
        self.assertEqual(page.eval_on_selector_all("[data-node-link][data-trail]", "els => els.length"), 0)
        # The filter is script only: without it every step of the trail is shown.
        self.assertTrue(page.locator("[data-trail-filter]").is_hidden())
        self.assertEqual(page.eval_on_selector_all(
            "ol[data-trail] > li", "els => els.filter(e => e.hidden).length",
        ), 0)


if __name__ == "__main__":
    unittest.main()
