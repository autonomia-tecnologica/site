"""Every article shows an estimated reading time, in minutes, in its metadata lines.

The count comes from the Markdown body at 200 words per minute, rounded up, at least one minute;
the front matter and the Markdown markup do not count. The label comes from ui.reading_time in
i18n/pt_BR.json and is filled in by the build, never written in the templates.

Run from the repository root:

    python3 -m unittest discover -s tests/build -t tests/build
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from src.build.content import read_entry, reading_minutes  # noqa: E402

DIST = REPO / "dist"
ARTICLE_ID = "1"
ARTICLE_SOURCE = REPO / "content" / "articles" / "pt_BR" / f"{ARTICLE_ID}.md"
I18N = REPO / "i18n" / "pt_BR.json"


def words(count: int) -> str:
    return " ".join(["palavra"] * count)


class ReadingMinutesTest(unittest.TestCase):
    def test_rounds_up_to_whole_minutes(self):
        self.assertEqual(reading_minutes(words(200)), 1)
        self.assertEqual(reading_minutes(words(201)), 2)
        self.assertEqual(reading_minutes(words(400)), 2)
        self.assertEqual(reading_minutes(words(401)), 3)

    def test_at_least_one_minute(self):
        self.assertEqual(reading_minutes(""), 1)
        self.assertEqual(reading_minutes("   \n\n"), 1)
        self.assertEqual(reading_minutes("uma palavra"), 1)

    def test_markdown_markup_does_not_count(self):
        # 197 words of text, one heading word and two list item words: exactly 200 words.
        # The 250 words of the image alt text are markup, not text read as prose.
        alt = " ".join(["extra"] * 250)
        body = "\n\n".join([
            "# Título",
            words(197),
            "- item\n- item",
            f"![{alt}](imagem.png)",
        ])
        self.assertEqual(reading_minutes(body), 1)

    def test_front_matter_is_not_counted(self):
        # The body has 195 words; if the front matter were counted the total would pass 200.
        front_matter = (
            "---\n"
            "title: Um exemplo de front matter com várias palavras\n"
            "date: 2026-11-08\n"
            "updated: 2026-11-08\n"
            "summary: Um resumo com mais algumas palavras para inflar a contagem\n"
            "author: Rafael Correia\n"
            "---\n"
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "1.md"
            path.write_text(front_matter + words(195), encoding="utf-8")
            errors: list[str] = []
            parsed = read_entry(path, "content/articles/pt_BR/1.md", errors)
        self.assertIsNotNone(parsed)
        self.assertEqual(errors, [])
        self.assertEqual(reading_minutes(parsed[1]), 1)


class ReadingTimePagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        result = subprocess.run(
            [sys.executable, "-m", "src.build"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"development build failed:\n{result.stderr}")
        errors: list[str] = []
        parsed = read_entry(ARTICLE_SOURCE, "content/articles/pt_BR/1.md", errors)
        if parsed is None or errors:
            raise RuntimeError(f"could not read article {ARTICLE_ID}: {errors}")
        strings = json.loads(I18N.read_text(encoding="utf-8"))
        cls.minutes = reading_minutes(parsed[1])
        cls.label = strings["ui"]["reading_time"].format(minutes=cls.minutes)
        cls.article = (DIST / "pt-br" / "artigos" / ARTICLE_ID / "index.html").read_text(encoding="utf-8")
        cls.article_list = (DIST / "pt-br" / "artigos" / "index.html").read_text(encoding="utf-8")

    def test_the_example_article_has_at_least_one_minute(self):
        self.assertGreaterEqual(self.minutes, 1)

    def test_article_page_shows_the_reading_time(self):
        self.assertIn(self.label, self.article)

    def test_article_list_shows_the_reading_time(self):
        self.assertIn(self.label, self.article_list)


if __name__ == "__main__":
    unittest.main()
