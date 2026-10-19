from re_standards import bookfmt
from bookkit import CHAPTER, make_book


def test_parses_chapters_sections_and_examples(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path))
    assert book.problems == []
    c = book.chapters[0]
    assert (c.chapter_id, c.title, c.file) == ("first-steps", "First steps", "chapters/01-first-steps.md")
    assert [(s.section_id, s.level, s.parent_id, s.order) for s in c.sections] == [
        ("load-data", 2, None, 1), ("a-detail", 3, "load-data", 2), ("summarize", 2, None, 3)]
    assert c.sections[0].title == "Load the data"
    assert c.sections[0].line == 9                      # line numbers count the front matter
    assert c.sections[0].example_ids == ["hello"]
    assert book.examples["hello"].section_id == "load-data"
    assert book.ids() == {"first-steps": "chapter", "load-data": "section", "a-detail": "section",
                          "summarize": "section", "hello": "example"}


def test_headings_inside_code_fences_are_not_sections(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path))
    assert "nope" not in book.ids()


def test_renaming_a_heading_keeps_its_id_and_changes_its_hash(tmp_path):
    before = bookfmt.load_book(make_book(tmp_path / "a")).chapters[0].sections[0]
    renamed = CHAPTER.replace("## Load the data {#load-data}", "## Read the data {#load-data}")
    after = bookfmt.load_book(make_book(tmp_path / "b", chapter=renamed)).chapters[0].sections[0]
    assert after.section_id == before.section_id == "load-data"
    assert after.title == "Read the data" and after.sha256 != before.sha256


def test_hash_ignores_trailing_spaces_blank_runs_and_the_id(tmp_path):
    a = bookfmt.load_book(make_book(tmp_path / "a")).chapters[0].sections
    noisy = CHAPTER.replace("Read the file.\n", "Read the file.   \n\n\n").replace("{#summarize}", "  {#summarize}")
    b = bookfmt.load_book(make_book(tmp_path / "b", chapter=noisy)).chapters[0].sections
    assert [s.sha256 for s in a] == [s.sha256 for s in b]
    # a section's hash covers its own text only, not its subsections
    edited = CHAPTER.replace("More text.", "More words.")
    c = bookfmt.load_book(make_book(tmp_path / "c", chapter=edited)).chapters[0].sections
    assert c[0].sha256 == a[0].sha256 and c[1].sha256 != a[1].sha256


def test_missing_bad_and_duplicate_ids_are_reported(tmp_path):
    chapter = CHAPTER.replace(" {#a-detail}", "").replace("{#summarize}", "{#Bad_ID}") + "\n## Again {#load-data}\n"
    book = bookfmt.load_book(make_book(tmp_path, chapter=chapter))
    text = "\n".join(book.problems)
    assert "'A detail' needs an explicit ID, such as {#a-detail}" in text
    assert "'Bad_ID' must be lowercase" in text
    assert "'load-data' is used twice" in text


def test_ids_share_one_namespace(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path, examples={"summarize": ("print(1)\n", "1\n"), "hello": ('print("hello")\n', "hello\n")}))
    assert any("'summarize' is used twice" in p for p in book.problems)


def test_front_matter_and_title_problems(tmp_path):
    no_fm = CHAPTER.split("---\n", 2)[2]
    assert any("missing front matter" in p for p in bookfmt.load_book(make_book(tmp_path / "a", chapter=no_fm)).problems)
    no_title = CHAPTER.replace("# First steps\n", "")
    assert any("needs a # title" in p for p in bookfmt.load_book(make_book(tmp_path / "b", chapter=no_title)).problems)
    extra = CHAPTER.replace("chapter_id: first-steps", "chapter_id: first-steps\ntitel: x")
    assert any("unknown front matter keys: titel" in p for p in bookfmt.load_book(make_book(tmp_path / "c", chapter=extra)).problems)


def test_examples_must_be_embedded_once_and_exist(tmp_path):
    orphan = bookfmt.load_book(make_book(tmp_path / "a", examples={"hello": ('print("hello")\n', "hello\n"), "spare": ("print(2)\n", "2\n")}))
    assert any("spare.py: not embedded" in p for p in orphan.problems)
    missing = bookfmt.load_book(make_book(tmp_path / "b", examples={}))
    assert any("embeds examples/hello.py, which doesn't exist" in p for p in missing.problems)
    twice = CHAPTER + "\n[Example: hello](../examples/hello.py)\n"
    assert any("embedded more than once" in p for p in bookfmt.load_book(make_book(tmp_path / "c", chapter=twice)).problems)
    no_out = bookfmt.load_book(make_book(tmp_path / "d", examples={"hello": ('print("hello")\n', None)}))
    assert no_out.problems == [] and any("no expected output" in p for p in no_out.output_problems)


def test_a_link_inside_a_sentence_is_not_an_embed(tmp_path):
    chapter = CHAPTER.replace("[Example: hello](../examples/hello.py)", "See [the code](../examples/hello.py) for details.")
    book = bookfmt.load_book(make_book(tmp_path, chapter=chapter))
    assert any("hello.py: not embedded" in p for p in book.problems)


def test_redirects_resolve_and_retired_ids_stay_retired(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path / "a", redirects="old-load: load-data\nolder: old-load\n"))
    assert book.problems == []
    assert book.resolve("older") == "load-data" and book.resolve("gone") is None
    reused = bookfmt.load_book(make_book(tmp_path / "b", redirects="load-data: summarize\n"))
    assert any("'load-data' is retired" in p for p in reused.problems)
    dangling = bookfmt.load_book(make_book(tmp_path / "c", redirects="old: nowhere\n"))
    assert any("doesn't lead to a live ID" in p for p in dangling.problems)
    broken = bookfmt.load_book(make_book(tmp_path / "d", redirects="- a\n- b\n"))
    assert any("must map each retired ID" in p for p in broken.problems)


def test_render_gives_headings_their_ids_and_replaces_embeds(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path))
    html = bookfmt.render_chapter(book.chapters[0], lambda eid: f'<figure data-example="{eid}"></figure>',
                                  lambda s: f' <a href="/s/{s.section_id}">#</a>')
    assert "<h1" not in html
    assert '<h2 id="load-data">Load the data <a href="/s/load-data">#</a></h2>' in html
    assert '<h3 id="a-detail">A detail' in html
    assert '<figure data-example="hello"></figure>' in html and "examples/hello.py" not in html
    assert "{#" not in html.replace("{#nope}", "")       # the fenced example keeps its text


def test_raw_html_in_book_text_is_escaped(tmp_path):
    chapter = CHAPTER.replace("Opening text.", "<script>alert(1)</script>")
    html = bookfmt.render_chapter(bookfmt.load_book(make_book(tmp_path, chapter=chapter)).chapters[0], lambda e: "")
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_machine_markdown_keeps_ids_and_inlines_examples(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path))
    md = bookfmt.machine_markdown(book.chapters[0], lambda eid: f"```python\n# {eid}\n```")
    assert "## Load the data {#load-data}" in md and "```python\n# hello\n```" in md and "(../examples/" not in md


def test_slugify_suggests_ids():
    assert bookfmt.slugify("Why position matters!") == "why-position-matters"
    assert bookfmt.slugify("Café & ML 2.0") == "cafe-ml-2-0"
    assert len(bookfmt.slugify("word " * 40)) <= 64
