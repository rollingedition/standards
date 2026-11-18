"""Test vectors for an authored book's cover: its authors' names, generated from the edition's record. A house book's
cover names nobody (test_house.py holds it to what it was)."""
import re

import pytest

from re_standards import cover

ARGS = ("Search Relevance Engineering in Practice", "2027.05.2", "483B-Z9SS", 3, "2026-10-19T08:00:00Z")
FIVE = ["Jane Doe", "Sam Lee", "Priya Rao", "Ana Lima", "Wei Chen"]


def author_texts(svg: str) -> list[tuple[str, str]]:
    """(baseline y, text) of each author line on a live cover."""
    return re.findall(r'<text x="28" y="([\d.]+)" font-family="Literata, Georgia, serif" font-weight="600" '
                      r'font-size="13" fill="#fbf5e6">([^<]*)</text>', svg)


def test_author_lines_name_everyone_in_two_lines_at_most_breaking_between_names():
    assert cover.author_lines([]) == []
    assert cover.author_lines(["Jane Doe"]) == ["Jane Doe"]
    assert cover.author_lines(["Jane Doe", "Sam Lee"]) == ["Jane Doe and Sam Lee"]
    assert cover.author_lines(["Jane Doe", "Sam Lee", "Priya Rao"]) == ["Jane Doe, Sam Lee and Priya Rao"]
    assert cover.author_lines(FIVE) == ["Jane Doe, Sam Lee, Priya Rao,", "Ana Lima and Wei Chen"]
    assert cover.author_lines(["Bartholomew Montgomery-Fitzgerald Ashworth-Pemberton the Third"]) == [
        "Bartholomew Montgomery-Fitzgerald", "Ashworth-Pemberton the Third"]       # one name too long for a line


def test_too_many_names_for_two_lines_become_the_first_and_how_many_others():
    many = [f"Author Number {n} Of The Book" for n in range(1, 8)]
    assert cover.author_lines(many) == ["Author Number 1 Of The Book", "and 6 others"]
    assert cover.author_lines(["Jane Doe"] + many) == ["Jane Doe and 7 others"]


def test_a_name_too_long_for_two_lines_or_one_the_cover_cant_draw_is_a_manifest_problem():
    assert cover.authors_problem(["Jane Doe"]) is None and cover.authors_problem(FIVE) is None
    assert cover.authors_problem(["J" + "e" * 60]).startswith("the authors' names don't fit on the cover in 2 lines")
    assert cover.authors_problem(["李 小龍"]) == "an author's name has a character the cover can't draw: 小 李 龍"
    with pytest.raises(ValueError):
        cover.author_lines(["J" + "e" * 60])


def test_the_authors_sit_above_the_edition_line_and_clear_the_tape_field():
    assert author_texts(cover.render_cover(*ARGS, authors=("Jane Doe", "Sam Lee"))) == [("396", "Jane Doe and Sam Lee")]
    assert author_texts(cover.render_cover(*ARGS, authors=FIVE)) == [("380.4", "Jane Doe, Sam Lee, Priya Rao,"),
                                                                     ("396", "Ana Lima and Wei Chen")]
    edition_line = cover.COVER_H - cover.MARGIN_BOTTOM - cover.FOOT_H - cover.LINE_RISE
    assert edition_line - cover.AUTHOR_RISE == 396                         # 22 units above the edition line, at 418
    capitals = 396 - cover.AUTHOR_SIZE * cover.AUTHOR_LEADING - cover.AUTHOR_SIZE * 0.72
    assert capitals > cover.MARGIN_TOP + cover.TITLE_ZONE_H + cover.FIELD_GAP + cover.FIELD_H     # below the tape field


def test_an_authored_cover_names_them_in_its_alt_text_and_as_outlines_on_a_file():
    svg = cover.render_cover(*ARGS, authors=("Jane Doe",))
    assert 'aria-label="Cover of Search Relevance Engineering in Practice by Jane Doe, edition 2027.05.2, code 483B-Z9SS"' in svg
    outlined, house = cover.render_cover(*ARGS, outlined=True, authors=("Jane Doe",)), cover.render_cover(*ARGS, outlined=True)
    assert "<text" not in outlined and outlined.count('<g fill="#fbf5e6">') == house.count('<g fill="#fbf5e6">') + 1
    assert cover.cover_alt(*ARGS[:3], FIVE).endswith("by Jane Doe, Sam Lee, Priya Rao, Ana Lima and Wei Chen, edition 2027.05.2, "
                                                      "code 483B-Z9SS")
    assert cover.cover_alt(*ARGS[:3]) == "Cover of Search Relevance Engineering in Practice, edition 2027.05.2, code 483B-Z9SS"
