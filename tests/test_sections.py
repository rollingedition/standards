from re_standards import bookfmt, sections
from bookkit import CHAPTER, make_book

RESULTS = {"hello": {"passing": True, "versions": {"python": "3.12.15"}, "direct": []}}


def test_first_edition_marks_everything_changed(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path))
    m = sections.build_manifest(book, "2026.10.1", "main", None, RESULTS)
    assert m["prev_edition"] is None and m["book"] == "tiny-book"
    assert [s["section_id"] for s in m["sections"]] == ["load-data", "a-detail", "summarize"]
    assert set(m["sections"][0]) >= {"section_id", "chapter_id", "title", "order", "sha256", "changed", "example_ids"}
    assert all(s["changed"] for s in m["sections"]) and sections.examples_changed(m) == 1
    assert sections.manifest_ids(m) == {"first-steps", "load-data", "a-detail", "summarize", "hello"}


def test_rename_marks_only_that_section_changed(tmp_path):
    prev = sections.build_manifest(bookfmt.load_book(make_book(tmp_path / "a")), "2026.10.1", "main", None, RESULTS)
    renamed = CHAPTER.replace("## Load the data {#load-data}", "## Read the data {#load-data}")
    m = sections.build_manifest(bookfmt.load_book(make_book(tmp_path / "b", chapter=renamed)), "2026.10.2", "main", prev, RESULTS)
    assert [(s["section_id"], s["title"], s["changed"]) for s in m["sections"]] == [
        ("load-data", "Read the data", True), ("a-detail", "A detail", False), ("summarize", "Summarize", False)]
    assert m["chapters"][0]["changed"] is False and m["prev_edition"] == "2026.10.1"
    assert sections.examples_changed(m) == 0


def test_an_example_changes_with_its_code_or_its_versions(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path))
    prev = sections.build_manifest(book, "2026.10.1", "main", None, RESULTS)
    bumped = {"hello": {"passing": True, "versions": {"python": "3.12.16"}, "direct": []}}
    assert sections.examples_changed(sections.build_manifest(book, "2026.10.2", "main", prev, RESULTS)) == 0
    assert sections.examples_changed(sections.build_manifest(book, "2026.10.2", "main", prev, bumped)) == 1
    edited = bookfmt.load_book(make_book(tmp_path / "b", examples={"hello": ('print("hi")\n', "hi\n")}))
    assert sections.examples_changed(sections.build_manifest(edited, "2026.10.2", "main", prev, RESULTS)) == 1


def test_manifest_round_trips(tmp_path):
    m = sections.build_manifest(bookfmt.load_book(make_book(tmp_path / "b")), "2026.10.1", "main", None, RESULTS)
    sections.write(m, tmp_path / "out" / "sections.json")
    assert sections.read(tmp_path / "out" / "sections.json") == m
