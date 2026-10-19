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


def test_render_cover():
    svg = cover.render_cover("Building Reliable Data Pipelines with Apache Airflow", "2028.02.1", "DKF3-R7TH", 30)
    assert svg.startswith("<svg") and 'viewBox="0 0 300 480"' in svg and 'width="1600"' in svg
    assert ">+6</text>" in svg                       # 24 ticks shown, 6 more counted
    assert "Cover of Building Reliable Data Pipelines with Apache Airflow, edition 2028.02.1, code DKF3-R7TH" in svg
    with pytest.raises(ValueError):
        cover.render_cover("A title", "2028.02.1", "DKF3-R7TH", 0)


def test_a_new_edition_changes_only_the_fingerprint_ticks_and_number():
    a = cover.render_cover("Pipeline Demo", "2026.10.1", "DKF3-R7TH", 1).splitlines()
    b = cover.render_cover("Pipeline Demo", "2026.10.2", "483B-Z9SS", 2).splitlines()
    title_tape = [line for line in a if 'fill="#fbf5e6"/>' in line and line.startswith("<polygon")]
    assert title_tape and all(line in b for line in title_tape)   # the title strip is unchanged
    assert sum('<rect x=' in line and 'height="12"' in line for line in b) == 2
