"""A house book's generated files stay byte for byte what they were before authored books: its README, CITATION.cff and
LICENSE-CODE, live and as a draft, and its cover, live and outlined. Everything authored stays dormant until book.toml
names authors, so a change to how authored books read must leave these exactly as they are.

The fixtures in fixtures/house/ were generated before authorship was built. When a change to the front page or the
cover is meant to change every book, house books included, regenerate them in the same commit and say why."""
import hashlib
from pathlib import Path

import pytest

from bookkit import MANIFEST, make_book
from re_standards import bookfmt, cover, readme

FIXTURES = Path(__file__).parent / "fixtures" / "house"
LIVE = MANIFEST + 'reader = "For people who like small tests."\n'
DRAFT = MANIFEST.replace('status = "live"', 'status = "draft"')
COVERS = {    # sha256 of each house cover, drawn with the same inputs
    False: "730a9d7cc294115731a6e73043a5f3cd6a7e6c42870627d2703f456087cf2c4e",
    True: "d2e2674c2b25bc8f735e6bed608cfdd068154598fd70bc8bb5f6460984c9f096",
}


@pytest.mark.parametrize("name, manifest", [("live", LIVE), ("draft", DRAFT)])
def test_a_house_books_front_page_is_unchanged(tmp_path, name, manifest):
    files = readme.files(bookfmt.load_book(make_book(tmp_path, manifest=manifest)))
    assert files["README.md"] == (FIXTURES / f"{name}-README.md").read_text(encoding="utf-8")
    assert files["CITATION.cff"] == (FIXTURES / f"{name}-CITATION.cff").read_text(encoding="utf-8")
    assert files["LICENSE-CODE"] == (FIXTURES / "LICENSE-CODE").read_text(encoding="utf-8")


@pytest.mark.parametrize("outlined", [False, True])
def test_a_house_books_cover_is_unchanged(outlined):
    svg = cover.render_cover("Search Relevance Engineering in Practice", "2027.05.2", "483B-Z9SS", 1 if outlined else 3,
                             "2026-10-19T08:00:00Z", outlined=outlined)
    assert hashlib.sha256(svg.encode("utf-8")).hexdigest() == COVERS[outlined]


def test_a_house_books_byline_and_reuse_words_are_rolling_editions():
    cfg = readme.load_config()
    m = {"slug": "tiny-book"}
    assert readme.byline(m, cfg) == "By Rolling Edition, with AI"
    assert readme.code_copyright(cfg, m) == cfg["code_copyright"] == "Copyright (c) Rolling Edition and contributors"
    assert readme.reuse(cfg, "full", m) == readme.reuse(cfg, "full")
    assert readme.interests(m) == [] and readme.gate_words(m) == ""
