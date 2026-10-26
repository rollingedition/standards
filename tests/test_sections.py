import json

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


from test_bookfmt import BOUND, bound_book  # noqa: E402


def test_a_bound_value_that_moves_changes_the_section_and_its_hash_of_the_text_as_read(tmp_path):
    first = sections.build_manifest(bound_book(tmp_path / "a"), "2026.10.1", "main", None, RESULTS)
    assert first["schema_version"] == 2
    assert all("rendered_sha256" in u for u in first["chapters"] + first["sections"])
    moved = sections.build_manifest(bound_book(tmp_path / "b", rows="4"), "2026.10.2", "main", first, RESULTS)
    by = {s["section_id"]: s for s in moved["sections"]}
    assert by["load-data"]["sha256"] == first["sections"][0]["sha256"]          # the source's hash: unchanged
    assert by["load-data"]["rendered_sha256"] != first["sections"][0]["rendered_sha256"]
    assert [(s["section_id"], s["changed"]) for s in moved["sections"]] == [
        ("load-data", True), ("a-detail", False), ("summarize", False)]
    assert moved["chapters"][0]["changed"] is False and sections.units_changed(moved) == ["load-data"]
    pinned = sections.build_manifest(bound_book(tmp_path / "c", rows="4", pandas="2.3.0"), "2026.10.3", "main", moved, RESULTS)
    assert sections.units_changed(pinned) == ["first-steps"]                    # a chapter's opening, by the chapter's ID
    assert sections.units_changed(first) == ["first-steps", "load-data", "a-detail", "summarize"]   # a first edition: all


def test_a_binding_that_gives_the_typed_value_changes_nothing_a_reader_sees(tmp_path):
    typed = bound_book(tmp_path / "a", chapter=BOUND.replace("{{out:hello:rows}}", "3"))
    prev = sections.build_manifest(typed, "2026.10.1", "main", None, RESULTS)
    m = sections.build_manifest(bound_book(tmp_path / "b"), "2026.10.2", "main", prev, RESULTS)
    assert m["sections"][0]["sha256"] != prev["sections"][0]["sha256"] and not m["sections"][0]["changed"]
    assert sections.units_changed(m) == []


def test_a_manifest_written_before_the_hash_is_filled_in_from_its_own_text(tmp_path):
    book = bound_book(tmp_path / "a")
    full = sections.build_manifest(book, "2026.10.1", "main", None, RESULTS)
    old = {**full, "schema_version": 1,
           "chapters": [{k: v for k, v in c.items() if k != "rendered_sha256"} for c in full["chapters"]],
           "sections": [{k: v for k, v in s.items() if k != "rendered_sha256"} for s in full["sections"]]}
    before = json.dumps(old, sort_keys=True)
    assert sections.fill_rendered(old, book) == {**full, "schema_version": 1}
    assert json.dumps(old, sort_keys=True) == before                             # the manifest given is left as it is
    # without the hash, a change is decided by sha256: a moved bound value isn't seen, nothing is invented
    moved = sections.build_manifest(bound_book(tmp_path / "b", rows="4"), "2026.10.2", "main", old, RESULTS)
    assert sections.units_changed(moved) == []
    filled = sections.build_manifest(bound_book(tmp_path / "c", rows="4"), "2026.10.2", "main",
                                     sections.fill_rendered(old, book), RESULTS)
    assert sections.units_changed(filled) == ["load-data"]
    # a text that isn't the edition's (its source hash differs) never gives a unit its hash
    other = bound_book(tmp_path / "d", chapter=BOUND.replace("Read the file", "Open the file"))
    partial = sections.fill_rendered(old, other)
    assert "rendered_sha256" not in partial["sections"][0] and "rendered_sha256" in partial["sections"][1]
    assert sections.text_hash(partial["sections"][0]) == old["sections"][0]["sha256"]
