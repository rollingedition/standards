"""The reference catalog checks. Any implementation must pass these."""
import copy
from pathlib import Path

import pytest

from re_standards import catalog as c

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "manifests"


@pytest.fixture(scope="module")
def tax():
    return c.load_taxonomy()


@pytest.fixture(scope="module")
def books():
    return [c.load_book(p) for p in sorted(FIXTURES.glob("*.book.toml"))]


def test_the_taxonomy_is_valid(tax):
    assert c.validate_taxonomy(tax) == []


def test_every_wikipedia_title_has_its_wikidata_id(tax):
    assert c.validate_anchors(tax) == []
    broken = copy.deepcopy(tax)
    broken["skills"][0]["wikidata"] = None
    assert any("no Wikidata ID" in e for e in c.validate_anchors(broken))


def test_the_launch_title_manifests_are_valid(tax, books):
    assert len(books) == 3
    assert all(c.validate_book(b, tax) == [] for b in books)


def test_draft_books_stay_out_and_empty_terms_get_no_page(tax, books):
    cat = c.build_catalog(tax, books)
    assert cat["books"] == [] and cat["skills"] == [] and cat["areas"] == []


def _live(tax, books):
    live = copy.deepcopy(books)
    for b in live:
        b["status"] = "live"
    return c.build_catalog(tax, live)


def test_areas_come_from_skills_primary_first(tax, books):
    by_slug = {b["slug"]: b for b in _live(tax, books)["books"]}
    assert by_slug["search-relevance-engineering-in-practice"]["areas"] == ["search-and-recommendation", "machine-learning", "data-science"]
    assert by_slug["evaluating-llm-applications"]["primary_skill"] == "llm-evaluation"


def test_skill_pages_list_books_primary_first(tax, books):
    skills = {s["id"]: s for s in _live(tax, books)["skills"]}
    assert skills["learning-to-rank"]["books"] == ["recommender-systems-for-e-commerce", "search-relevance-engineering-in-practice"]
    assert skills["search-relevance"]["books"] == ["search-relevance-engineering-in-practice"]
    assert "learning-to-rank" in skills["recommender-systems"]["related"]
    assert "time-series-forecasting" not in skills


def test_also_covered_with_is_computed(tax, books):
    skills = {s["id"]: s for s in _live(tax, books)["skills"]}
    assert "experimentation" in skills["learning-to-rank"]["also_covered_with"]


def test_planned_areas_stay_hidden(tax, books):
    areas = {a["id"]: a for a in _live(tax, books)["areas"]}
    assert "software-engineering" not in areas and "search-and-recommendation" in areas


def test_bad_manifests_are_rejected(tax, books):
    bad = dict(books[0], skills=["search-relevance", "not-a-skill"], status="published")
    errs = c.validate_book(bad, tax)
    assert any("unknown skill" in e for e in errs) and any("status" in e for e in errs)
    assert any("1 to 5" in e for e in c.validate_book(dict(books[0], skills=[]), tax))
    assert any("listed twice" in e for e in c.validate_book(dict(books[0], skills=["search-relevance"] * 2), tax))
    with pytest.raises(c.CatalogError):
        c.build_catalog(tax, [bad])


def test_one_sided_related_links_are_rejected(tax):
    broken = copy.deepcopy(tax)
    next(s for s in broken["skills"] if s["id"] == "stream-processing")["related"].append("recommender-systems")
    assert any("doesn't list" in e for e in c.validate_taxonomy(broken))


def test_a_released_manifest_may_predate_the_level_field(tmp_path):
    tax = c.load_taxonomy()
    book = {"slug": "old-book", "title": "Old Book", "status": "live", "skills": ["data-pipelines"], "line": "main"}
    assert any("level must be" in e for e in c.validate_book(book, tax))
    assert c.validate_book(book, tax, released=True) == []
    out = c.build_catalog(tax, [book], released=True)
    assert out["books"][0]["level"] is None and out["books"][0]["level_label"] == ""
    assert any("level must be" in e for e in c.validate_book({**book, "level": "beginner"}, tax, released=True))
