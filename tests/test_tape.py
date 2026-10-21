"""The reference test vectors for the tape encodings and the cover. Any implementation must reproduce these."""
import pytest

from re_standards import cover, tape


def test_letters_and_bits():
    assert tape.letter_value("a") == 1 and tape.letter_value("z") == 26
    assert tape.bits5(19) == [1, 0, 0, 1, 1]          # "s": the top hole is the highest bit
    assert tape.bits5(31) == [1, 1, 1, 1, 1]          # the fingerprint marker
    with pytest.raises(ValueError):
        tape.bits5(32)


def test_normalize():
    assert tape.normalize_title("Café-Ready ML 2.0!") == ["cafe", "ready", "ml"]
    assert tape.normalize_title("  Évaluer   l'IA ") == ["evaluer", "l", "ia"]


def test_title_strips_launch_title():
    strips = tape.title_strips("Search Relevance Engineering in Practice")
    assert strips == [
        [19, 5, 1, 18, 3, 8, 0, 18, 5, 12, 5, 22, 1, 14, 3, 5],
        [5, 14, 7, 9, 14, 5, 5, 18, 9, 14, 7, 0, 9, 14, 0, 16, 18, 1, 3, 20, 9, 3, 5],
    ]
    assert tape.decode_strips(strips) == "search relevance engineering in practice"


def test_hyphen_is_a_word_break():
    # "e-commerce" becomes two words; "e" still fits on the first strip
    assert tape.title_strips("Recommender Systems for E-commerce") == [
        [18, 5, 3, 15, 13, 13, 5, 14, 4, 5, 18, 0, 19, 25, 19, 20, 5, 13, 19, 0, 6, 15, 18, 0, 5],
        [3, 15, 13, 13, 5, 18, 3, 5],
    ]


def test_wrap_limit_and_hard_split():
    for strip in tape.title_strips("Building Reliable Data Pipelines with Apache Airflow"):
        assert len(strip) <= tape.MAX_COLS
    assert tape.title_strips("a" * 30) == [[1] * 27, [1] * 3]


def test_edition_code_vectors():
    assert tape.release_record_string("evaluating-llm-applications", "2027.03.1", "0123456789ABCDEF0123456789abcdef01234567") == \
        "evaluating-llm-applications@2027.03.1:0123456789abcdef0123456789abcdef01234567"
    assert tape.edition_code("search-relevance-engineering-in-practice", "2027.05.2", "4f2a9c1e7b3d5a6f8e0c2b4d6a8f0e1c3b5d7a9f") == "483B-Z9SS"
    assert tape.edition_code("recommender-systems-for-e-commerce", "2027.01.1", "9b8a7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b") == "93ZC-QCQC"
    assert tape.edition_code("evaluating-llm-applications", "2027.03.1", "0123456789abcdef0123456789abcdef01234567") == "DKF3-R7TH"
    # a salt is only added on a collision, and changes the code
    assert tape.edition_code("evaluating-llm-applications", "2027.03.1", "0123456789abcdef0123456789abcdef01234567", salt=1) != "DKF3-R7TH"
    assert tape.release_record_string("b", "2027.03.1", "AB", salt=2) == "b@2027.03.1:ab#2"


def test_parse_code():
    assert tape.parse_code("483b z9ss") == "483B-Z9SS"
    assert tape.parse_code("483B-Z9SS") == "483B-Z9SS"
    assert tape.parse_code("oiLl-0000") == "0111-0000"   # O reads as 0; I and L read as 1
    assert tape.parse_code("U000-0000") is None           # U is not a Crockford symbol
    assert tape.parse_code("483B-Z9S") is None
    assert tape.parse_code("483B-Z9SS-1") is None


def test_fingerprint_columns():
    assert tape.fingerprint_columns("483B-Z9SS") == [31, 4, 8, 3, 11, 31, 9, 25, 25]
    with pytest.raises(ValueError):
        tape.fingerprint_columns("U000-0000")


def test_tape_scale():
    assert cover.tape_scale(1) == 1.0
    assert cover.tape_scale(2) == 1.0
    assert cover.tape_scale(3) == 0.7777
    assert cover.tape_field_height(3, cover.tape_scale(3)) <= cover.FIELD_H + 1e-6
    with pytest.raises(ValueError):
        cover.tape_scale(4)


def test_history_column():
    kinds = tape.edition_kinds([["kind:deps", "breaking"], ["review:expert", "docs"]])
    assert tape.history_column(kinds) == [0, 1, 0, 1, 1]
    assert tape.KIND_LABELS == ["kind:prose", "kind:deps", "kind:content"]


FIRST = "2026-10-19T12:00:00Z"


def test_render_cover():
    svg = cover.render_cover("Building Reliable Data Pipelines with Apache Airflow", "2028.02.1", "DKF3-R7TH", 30, FIRST)
    assert svg.startswith("<svg") and 'viewBox="0 0 300 480"' in svg and 'width="1600"' in svg
    assert ">30 editions since Oct 2026</text>" in svg      # read at a glance, however many editions
    assert "Cover of Building Reliable Data Pipelines with Apache Airflow, edition 2028.02.1, code DKF3-R7TH" in svg
    with pytest.raises(ValueError):
        cover.render_cover("A title", "2028.02.1", "DKF3-R7TH", 0, FIRST)


def test_the_edition_line_says_how_many_editions_and_since_when():
    assert cover.edition_line(1, FIRST) == "First edition, Oct 2026"
    assert cover.edition_line(3, FIRST) == "3 editions since Oct 2026"
    assert cover.edition_line(124, "2026-09-30T23:59:00+00:00") == "124 editions since Sep 2026"


def test_a_new_edition_changes_only_the_fingerprint_line_and_number():
    a = cover.render_cover("Pipeline Demo", "2026.10.1", "DKF3-R7TH", 1, FIRST).splitlines()
    b = cover.render_cover("Pipeline Demo", "2026.10.2", "483B-Z9SS", 2, FIRST).splitlines()
    title_tape = [line for line in a if 'fill="#fbf5e6"/>' in line and line.startswith("<polygon")]
    assert title_tape and all(line in b for line in title_tape)   # the title strip is unchanged
    assert any(">First edition, Oct 2026</text>" in line for line in a)
    assert any(">2 editions since Oct 2026</text>" in line for line in b)


def test_an_outlined_cover_is_the_same_cover_with_its_text_as_outlines():
    args = ("Building Reliable Data Pipelines with Apache Airflow", "2028.02.1", "DKF3-R7TH", 30, FIRST)
    live, outlined = cover.render_cover(*args), cover.render_cover(*args, outlined=True)
    assert "<text" in live and "<text" not in outlined and "<tspan" not in outlined
    shapes = lambda svg: [line for line in svg.splitlines() if line.startswith(("<svg", "<title", "<rect", "<polygon", "<circle"))]
    assert shapes(outlined) == shapes(live)              # the frame, alt text, tape and icon are untouched
    assert outlined.count('<g fill="#e58f2a">') == 1     # the code under the fingerprint, in cover-tail
    assert outlined.count(f'<g fill="{cover.COVER_MUTED}">') == 2   # the edition line and the edition number


def test_glyph_runs_kern_and_ligate_as_live_text_does():
    t = cover.glyphs()["title"]
    run, advance = cover.glyph_run("AV", "title")
    assert run[1][0] == t["glyphs"]["A"][0] + t["kerning"]["AV"] < t["glyphs"]["A"][0]    # V tucks under A
    assert advance == run[1][0] + t["glyphs"]["V"][0]
    assert [ci for _, ci, _ in cover.glyph_run("fit", "title")[0]] == [0, 2]             # one glyph for "fi", then t
    mono, width = cover.glyph_run("1QS9-YKDZ", "mono")
    assert len(mono) == 9 and width == 9 * cover.glyphs()["mono"]["glyphs"]["0"][0]       # monospaced
    with pytest.raises(ValueError, match="no outline"):
        cover.glyph_run("検索", "title")


def test_a_title_must_be_drawable_on_its_cover():
    assert cover.title_problem("A Primer on Search Relevance") is None
    assert cover.title_problem("Café “Search” — Ångström Edition") is None
    assert "no outline for '検'" in cover.title_problem("Search 検")
    assert "three lines" in cover.title_problem(" ".join(["Relevance"] * 12))
