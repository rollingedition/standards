"""Authored books' book.toml: [[authors]] and [authorship], what they credit, and the gate's levels."""
import tomllib

import pytest

from bookkit import AUTHORS, MANIFEST, make_book
from re_standards import authorship, bookfmt, catalog


def manifest(extra: str = AUTHORS) -> dict:
    return tomllib.loads(MANIFEST + extra)


def test_a_house_book_names_no_authors_and_has_no_problems():
    m = manifest("")
    assert not authorship.is_authored(m) and authorship.authors(m) == [] and authorship.problems(m) == []
    assert authorship.state(m) is None and authorship.credited(m) == []


def test_an_authored_book_reads_its_authors_in_order():
    jane, kestrel = authorship.authors(manifest())
    assert (jane.name, jane.github, jane.github_id, jane.lead, jane.chapters) == ("Jane Doe", "jane-doe-example", 1000001,
                                                                                  True, ("first-steps",))
    assert (kestrel.literal, kestrel.role, kestrel.chapters, kestrel.lead) == ("kestrel", "author", (), False)
    assert jane.record() == {"name": "Jane Doe", "github": "jane-doe-example", "github_id": 1000001, "role": "lead",
                             "given": "Jane", "family": "Doe"}
    assert kestrel.record() == {"name": "kestrel", "github": "kestrel-example", "github_id": 1000002, "role": "author",
                                "literal": "kestrel"}
    assert authorship.gate(manifest()) == "meaning" and authorship.state(manifest()) == "active"
    assert catalog.validate_book(manifest(), catalog.load_taxonomy()) == []


def test_only_an_active_or_returned_book_credits_its_authors():
    """A book still being adopted keeps Rolling Edition's byline until its author has verified it."""
    for state, credited in (("adopting", 0), ("active", 2), ("returned", 2)):
        m = manifest(AUTHORS.replace('state = "active"', f'state = "{state}"'))
        assert len(authorship.credited(m)) == credited, state


@pytest.mark.parametrize("change, problem", [
    (('github_id = 1000001', 'github_id = "1000001"'), "github_id is their numeric GitHub user ID"),
    (('github_id = 1000001', 'github_id = true'), "github_id is their numeric GitHub user ID"),
    (('github = "jane-doe-example"', 'github = "jane doe"'), "github is their GitHub login"),
    (('role = "lead"', 'role = "author"'), 'exactly one author has role = "lead" (found 0)'),
    (('github_id = 1000002', 'github_id = 1000002\nrole = "lead"'), 'exactly one author has role = "lead" (found 2)'),
    (('github_id = 1000002', 'github_id = 1000001'), "an author is listed twice (github_id)"),
    (('literal = "kestrel"', 'literal = "kestrel"\nfamily = "Kestrel"'), "either literal"),
    (('family = "Doe"\n', ''), "needs family (and given), or literal"),
    (('gate = "meaning"', 'gate = "everything"'), "gate must be one of meaning, standard, all"),
    (('state = "active"', 'state = "gone"'), "state must be one of adopting, active, returned"),
    (('interests = "Maintains a library this book teaches."', 'twitter = "x"'), "unknown field(s) twitter"),
    (('chapters = ["first-steps"]', 'chapters = "first-steps"'), "chapters is a list"),
    (('name = "Jane Doe"', 'name = "Jane Doe 李"'), "a character the cover can't draw: 李"),
])
def test_authorship_problems_say_what_to_fix(change, problem):
    old, new = change
    assert old in AUTHORS
    found = authorship.problems(manifest(AUTHORS.replace(old, new)))
    assert any(problem in p for p in found), found
    assert any(problem in p for p in catalog.validate_book(manifest(AUTHORS.replace(old, new)), catalog.load_taxonomy()))
    with pytest.raises(authorship.AuthorshipError):
        authorship.authors(manifest(AUTHORS.replace(old, new)))


def test_authors_are_tables_and_authorship_needs_them():
    assert authorship.problems(manifest('authors = ["Jane Doe"]\n')) == [
        "tiny-book: authors are [[authors]] tables, each with a name, github and github_id"]
    assert authorship.problems(manifest('\n[authorship]\nstate = "active"\n')) == [
        "tiny-book: [authorship] is only for a book that names its authors in [[authors]]"]
    no_table = AUTHORS.split("[authorship]")[0]
    assert authorship.problems(manifest(no_table)) == [
        "tiny-book: an authored book needs [authorship], with its state and, if not meaning, its gate"]


def test_the_gate_defaults_to_meaning_and_each_level_says_what_waits():
    m = manifest(AUTHORS.replace('gate = "meaning"\n', ""))
    assert authorship.gate(m) == "meaning" and authorship.problems(m) == []
    levels = authorship.settings()["levels"]
    assert list(levels) == ["meaning", "standard", "all"]
    assert levels["meaning"]["tiers"] == ["expert"] and levels["standard"]["tiers"] == ["expert", "auto"]
    assert levels["all"]["rides_along"] and levels["all"]["major"] and not levels["meaning"].get("major")
    words = authorship.level(manifest(AUTHORS.replace('gate = "meaning"', 'gate = "all"')))
    assert "72 hours" in words["reader"] and "{hours}" not in words["what"]


def test_an_owned_chapter_must_be_one_of_the_books(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path / "ok", manifest=MANIFEST + AUTHORS))
    assert book.problems == []
    book = bookfmt.load_book(make_book(tmp_path / "bad", manifest=MANIFEST + AUTHORS.replace('["first-steps"]', '["later"]')))
    assert book.problems == ["tiny-book: Jane Doe owns chapter 'later', which the book doesn't have"]


def test_names_join_as_a_byline_says_them():
    assert authorship.names_and([]) == "" and authorship.names_and(["Jane Doe"]) == "Jane Doe"
    assert authorship.names_and(["Jane Doe", "Sam Lee"]) == "Jane Doe and Sam Lee"
    assert authorship.names_and(["Jane Doe", "Sam Lee", "Priya Rao"]) == "Jane Doe, Sam Lee and Priya Rao"
    assert authorship.names_and(["Jane Doe", "Sam Lee"], "or") == "Jane Doe or Sam Lee"
