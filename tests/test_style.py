import json
import tomllib

from re_standards import bookfmt, data_path, standards_root, style
from bookkit import make_book

LONG = " ".join(["word"] * 240)

CHAPTER = f'''---
chapter_id: first-steps
---

# First steps

{LONG}

## Count the bad rows {{#count-bad-rows}}

{LONG}

[Example: count](../examples/count.py)

The export has {{{{out:count:unreadable amounts}}}} unreadable amounts, checked with pandas {{{{version:pandas}}}}.
'''

COUNT = ('print("unreadable amounts:", 1)\nprint("rows:", 9)\n', "unreadable amounts: 1\nrows: 9\n")


def book_with(tmp_path, chapter=CHAPTER, examples=None, pins="pandas==2.2.2\n"):
    root = make_book(tmp_path, chapter=chapter, examples=examples or {"count": COUNT})
    (root / "examples" / "requirements.txt").write_text(pins)
    (root / "examples" / ".python-version").write_text("3.12.15\n")
    return bookfmt.load_book(root)


def lint(book, **length):
    cfg = style.load_config()
    cfg["length"] = {**cfg["length"], "chapter_words": [1, 100_000], "section_words": [1, 100_000], "book_chapters": [1, 12], **length}
    return style.check_style(book, cfg)


def test_bindings_fill_in_output_values_and_pinned_versions(tmp_path):
    book = book_with(tmp_path)
    assert book.binding_problems() == []
    assert "has 1 unreadable amounts, checked with pandas 2.2.2" in book.bind(book.chapters[0].body)
    assert book.bind("{{version:python}}") == "3.12.15"
    html = bookfmt.render_chapter(book.chapters[0], lambda eid: "<pre></pre>", bind=book.bind)
    assert "has 1 unreadable amounts" in html and "{{" not in html


def test_unresolved_bindings_are_reported_with_their_line(tmp_path):
    chapter = CHAPTER.replace("{{out:count:unreadable amounts}}", "{{out:count:missing label}} {{out:nope:x}}") \
                     .replace("{{version:pandas}}", "{{version:numpy}}")
    problems = book_with(tmp_path, chapter=chapter).binding_problems()
    assert len(problems) == 3
    assert all(p.startswith("chapters/01-first-steps.md:15:") for p in problems)
    assert any("no line(s) labelled 'missing label'" in p for p in problems)
    assert any("there is no example 'nope'" in p for p in problems)
    assert any("numpy isn't pinned" in p for p in problems)


def test_a_clean_chapter_passes(tmp_path):
    assert lint(book_with(tmp_path)) == []


def test_time_words_banned_words_and_exclamations_name_their_rule(tmp_path):
    chapter = CHAPTER.replace(LONG + "\n\n[Example", "Recently, BM25 simply became the latest default!\n\n[Example")
    problems = lint(book_with(tmp_path, chapter=chapter))
    assert any("W-24" in p and '"recently"' in p for p in problems)
    assert any("W-24" in p and '"the latest"' in p for p in problems)
    assert any("W-35" in p and '"simply"' in p for p in problems)
    assert any("W-35: no exclamation marks" in p for p in problems)


def test_words_inside_code_are_not_prose(tmp_path):
    chapter = CHAPTER.replace(LONG + "\n\n[Example", "Call `just_do_it()` here.\n\n```python\nsimply = 'latest!'\n```\n\n[Example")
    assert lint(book_with(tmp_path, chapter=chapter)) == []


def test_a_typed_version_must_be_a_binding(tmp_path):
    chapter = CHAPTER.replace("{{version:pandas}}", "2.2.2").replace("pandas 2.2.2", "pandas 2.2.2")
    problems = lint(book_with(tmp_path, chapter=chapter))
    assert any("W-25" in p and "{{version:pandas}}" in p for p in problems)


def test_title_case_headings_and_missing_alt_text(tmp_path):
    chapter = CHAPTER.replace("## Count the bad rows", "## Count The Bad Rows") + "\n![](figure.png)\n"
    problems = lint(book_with(tmp_path, chapter=chapter))
    assert any("W-36" in p for p in problems)
    assert any("W-39" in p for p in problems)


def test_lengths_long_examples_and_chapter_count(tmp_path):
    long_example = ("\n".join(f"x{i} = {i}" for i in range(45)) + '\nprint("unreadable amounts:", 1)\n', "unreadable amounts: 1\n")
    book = book_with(tmp_path, examples={"count": long_example})
    problems = lint(book, chapter_words=[3000, 6000], section_words=[200, 900], book_chapters=[5, 12])
    assert any("W-7: a chapter runs" in p for p in problems)
    assert any("W-18" in p for p in problems)
    assert any("W-7: a book has 5 to 12 chapters" in p for p in problems)   # the test book is live with 1 chapter


def test_recorded_outputs_need_a_complete_manifest(tmp_path):
    book = book_with(tmp_path)
    folder = book.root / "examples" / "data" / "recorded" / "judgments"
    folder.mkdir(parents=True)
    assert any("need a manifest.json" in p for p in style.check_recordings(book.root))
    (folder / "manifest.json").write_text(json.dumps({"script": "recordings/judge.py", "model": "m", "outputs": ["j.jsonl"]}))
    problems = style.check_recordings(book.root)
    assert any("missing model_version, prompt_sha256, created" in p for p in problems)
    assert any("recordings/judge.py doesn't exist" in p for p in problems)
    assert any("lists j.jsonl, which doesn't exist" in p for p in problems)


def test_the_model_bar_is_configured_and_the_writer_prompt_names_it():
    """Books are drafted with Claude Opus 5.5 or an equivalent or better model, listed in config."""
    with open(data_path("drafting.toml"), "rb") as f:
        models = tomllib.load(f)["drafting"]["models"]
    assert "claude-opus-5-5" in models and len(models) == len(set(models))
    writer = (standards_root() / "prompts" / "writer.md").read_text()
    assert "`data/drafting.toml`" in writer and "Claude Opus 5.5" in writer


def test_quoted_text_and_as_soon_as_are_not_ours(tmp_path):
    chapter = CHAPTER.replace(LONG + "\n\n[Example",
                              'The paper says "users click as soon as a result looks relevant" and “the latest run was simply better”. '
                              "Judge each result as soon as it loads.\n\n[Example")
    assert lint(book_with(tmp_path, chapter=chapter)) == []


def test_internal_links_must_name_live_ids(tmp_path):
    chapter = CHAPTER.replace(LONG + "\n\n[Example",
                              "See [counting](#count-bad-rows), [the chapter](#first-steps), [gone](#no-such-id) "
                              "and [chapter 2](02-other.md#x).\n\n[Example")
    problems = lint(book_with(tmp_path, chapter=chapter))
    assert any("#no-such-id" in p for p in problems)
    assert any("not by file name" in p for p in problems)
    assert not any("#count-bad-rows" in p or "#first-steps" in p for p in problems)


def test_internal_links_are_rewritten_by_the_renderer(tmp_path):
    book = book_with(tmp_path)
    chapter = book.chapters[0]
    chapter.body += "\nSee [elsewhere](#somewhere-else) and [here](#count-bad-rows).\n"
    html = bookfmt.render_chapter(chapter, lambda eid: "", bind=book.bind,
                                  link=lambda i: "/other/page#somewhere-else" if i == "somewhere-else" else None)
    assert 'href="/other/page#somewhere-else"' in html and 'href="#count-bad-rows"' in html


def test_a_table_wider_than_a_phone_names_w53(tmp_path):
    wide = "| " + " | ".join(f"c{i}" for i in range(7)) + " |\n|" + "---|" * 7 + "\n| " + " | ".join("1" * 7) + " |\n"
    narrow = "| a | b |\n| :--- | ---: |\n| 1 | 2 |\n"
    problems = lint(book_with(tmp_path, chapter=CHAPTER + "\n" + wide + "\n" + narrow))
    w53 = [p for p in problems if "W-53" in p]
    assert len(w53) == 1 and "7 columns" in w53[0]


def test_the_renderer_wraps_tables_only_when_asked(tmp_path):
    book = book_with(tmp_path)
    chapter = book.chapters[0]
    chapter.body += "\n| Run | nDCG@10 |\n| --- | ---: |\n| BM25 | 0.412 |\n"
    plain = bookfmt.render_chapter(chapter, lambda eid: "", bind=book.bind)
    wrapped = bookfmt.render_chapter(chapter, lambda eid: "", bind=book.bind, table_wrap=("<div class=\"frame\">", "</div>"))
    assert "<table>" in plain and "frame" not in plain
    assert wrapped.count('<div class="frame">') == 1 and "</table>\n</div>" in wrapped
    assert wrapped.index('<div class="frame">') < wrapped.index("<table>")
