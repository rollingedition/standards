"""The step format (steps.py): a terminal book's steps, checks and files, their directives, and what a Python book keeps
exactly as it was."""
import shutil
from pathlib import Path

import pytest

from re_standards import bookfmt, sections, steps
from bookkit import make_book

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLER = FIXTURES / "terminal-sampler"
PRIMER = FIXTURES / "primer-chapter"


def sampler(tmp_path: Path) -> Path:
    root = tmp_path / "sampler"
    shutil.copytree(SAMPLER, root)
    return root


def render(book: bookfmt.Book, chapter: bookfmt.Chapter, **extra) -> str:
    return bookfmt.render_chapter(chapter, lambda eid: f"<EX {eid}>", bind=book.bind,
                                  code_block=lambda code, lang: f"<CODE {lang}>{code}</CODE>",
                                  link=lambda i: f"#L-{i}", heading_after=lambda s: f"<A {s.section_id}>", **extra)


# ---------------------------------------------------------------- a Python book is as it was


@pytest.mark.parametrize("root", [PRIMER, None], ids=["primer-chapter", "tiny-book"])
def test_a_python_book_parses_and_renders_as_it_did(root, tmp_path):
    """Nothing of the step format reaches a book with no step: no step, check, file or setup; the same IDs; and its
    chapters render and print for machines the same whether or not the caller passes the steps' renderers, which are
    never called. (Checked once across every released book on this machine against the parser before the step
    format: the parse, the hashes, sections.json and each chapter's HTML and Markdown were byte-identical.)"""
    book = bookfmt.load_book(root or make_book(tmp_path))
    assert book.steps == {} and book.files == {}
    assert all(c.step_embeds == [] and c.setup == [] for c in book.chapters)
    assert all(s.step_ids == [] for s in book.sections)
    assert all(e.kind == "python" for c in book.chapters for e in c.embeds)
    assert set(book.ids().values()) <= {"chapter", "section", "example"}
    assert steps.steps_json(book) == {}

    def never(*args):
        raise AssertionError("a Python book has no step to render")
    for c in book.chapters:
        assert render(book, c) == render(book, c, step_html=never)
        plain = bookfmt.machine_markdown(c, lambda eid: f"EX {eid}", bind=book.bind)
        assert plain == bookfmt.machine_markdown(c, lambda eid: f"EX {eid}", bind=book.bind, step_block=never)
    manifest = sections.build_manifest(book, "2026.11.1", "main", None)
    assert all(set(s) == set(manifest["sections"][0]) for s in manifest["sections"])


def test_a_link_to_a_data_file_in_a_python_book_stays_a_link(tmp_path):
    chapter = bookfmt.load_book(make_book(tmp_path)).chapters[0]
    text = open(tmp_path / "chapters" / "01-first-steps.md").read().replace(
        "Read the file.", "Read the file.\n\n[orders.csv](../examples/data/orders.csv)")
    (tmp_path / "chapters" / "01-first-steps.md").write_text(text)
    book = bookfmt.load_book(tmp_path)
    assert book.problems == [] and book.chapters[0].step_embeds == [] and len(chapter.embeds) == 1
    assert 'href="../examples/data/orders.csv"' in render(book, book.chapters[0], step_html=lambda k, i: "STEP")


def test_book_is_still_built_from_its_six_positional_fields(tmp_path):
    english = bookfmt.load_book(make_book(tmp_path))
    copy = bookfmt.Book(english.root, english.manifest, english.chapters, english.examples, english.redirects, [])
    assert copy.steps == {} and copy.files == {} and copy.ids() == english.ids()


# ---------------------------------------------------------------- a terminal book


def test_the_sampler_parses_with_its_steps_checks_files_and_setup():
    book = bookfmt.load_book(SAMPLER)
    assert book.problems == [] and book.examples == {}
    first, second = book.chapters
    assert [(e.kind, e.example_id, e.section_id) for e in first.step_embeds] == [
        ("step", "make-project", "make-a-project"), ("check", "project-has-readme", "make-a-project"),
        ("file", "inventory", "count-the-lines"), ("step", "copy-inventory", "count-the-lines"),
        ("step", "count-items", "count-the-lines")]
    assert second.setup == ["make-project", "copy-inventory"]
    assert book.ids()["project-has-readme"] == "check" and book.ids()["inventory"] == "file"
    assert book.ids()["make-project"] == "step"
    assert book.locate("count-items") == ("files-and-folders", "count-items")
    assert book.files["inventory"].file == "examples/data/inventory.csv"
    check = book.steps["project-has-readme"]
    assert check.kind == "check" and check.directives.compare == "none"
    assert check.directives.hint == "Run the step above: it writes project/README.md."
    assert check.command == "test -f project/README.md\n"        # Copy and Run leave the directives out
    follow = book.steps["follow-log"].directives
    assert (follow.tab, follow.background, follow.compare) == ("log", True, "none")
    assert book.steps["write-low-stock"].directives.wait == ("grep -q restocked project/events.log",)
    assert book.steps["no-gadgets-low"].directives.expect_exit == 1
    assert book.steps["stamp-the-check"].directives.mask == ("time",)
    assert book.sections[0].step_ids == ["make-project", "project-has-readme"]


def test_steps_json_has_each_chapter_in_reading_order_and_the_hash_of_its_inputs(tmp_path):
    root = sampler(tmp_path)
    data = steps.steps_json(bookfmt.load_book(root))
    assert list(data) == ["files-and-folders", "sort-and-filter"]
    second = data["sort-and-filter"]
    assert [x["id"] for x in second["setup"]] == ["make-project", "copy-inventory"]
    assert [(x["kind"], x["id"]) for x in second["items"]][:2] == [("step", "sort-low-first"), ("step", "follow-log")]
    assert second["items"][0]["command"] == "tail -n +2 project/inventory.csv | sort -t, -k2,2n\n"
    (root / "examples" / "copy-inventory.sh").write_text("cp data/inventory.csv project/\n")
    again = steps.steps_json(bookfmt.load_book(root))
    assert again["sort-and-filter"]["inputs_sha256"] != second["inputs_sha256"]     # a setup step changed
    assert again["files-and-folders"]["inputs_sha256"] != data["files-and-folders"]["inputs_sha256"]


def test_a_python_example_and_a_step_share_one_id_namespace(tmp_path):
    root = sampler(tmp_path)
    shutil.copy(root / "examples" / "make-project.sh", root / "examples" / "make-a-project.sh")
    text = (root / "chapters" / "01-files-and-folders.md").read_text()
    (root / "chapters" / "01-files-and-folders.md").write_text(
        text.replace("[Step: make-project]", "[Step: make-a-project](../examples/make-a-project.sh)\n\n[Step: make-project]"))
    problems = bookfmt.load_book(root).problems
    assert any("'make-a-project' is used twice" in p for p in problems)


@pytest.mark.parametrize("edit, problem", [
    (lambda c: c.replace("[Check: project-has-readme]", "[Step: project-has-readme]"),
     "is a check, so its link reads [Check: project-has-readme]"),
    (lambda c: c.replace("examples/make-project.sh)", "examples/make-projects.sh)"),
     "embeds examples/make-projects.sh, which doesn't exist"),
    (lambda c: c.replace("examples/data/inventory.csv", "examples/data/missing.csv"),
     "embeds examples/data/missing.csv, which doesn't exist"),
    (lambda c: c + "\n[Step: make-project](../examples/make-project.sh)\n", "is embedded more than once"),
])
def test_what_a_chapter_gets_wrong_about_its_steps(tmp_path, edit, problem):
    root = sampler(tmp_path)
    path = root / "chapters" / "01-files-and-folders.md"
    path.write_text(edit(path.read_text()))
    assert any(problem in p for p in bookfmt.load_book(root).problems), bookfmt.load_book(root).problems


@pytest.mark.parametrize("setup, problem", [
    ("[make-project, project-has-readme]", "setup names 'project-has-readme', which isn't a step"),
    ("[make-project, sort-low-first]", "setup names 'sort-low-first', which isn't in an earlier chapter"),
    ("make-project", "setup lists the IDs of earlier chapters' steps"),
])
def test_setup_names_earlier_chapters_steps(tmp_path, setup, problem):
    root = sampler(tmp_path)
    path = root / "chapters" / "02-sort-and-filter.md"
    path.write_text(path.read_text().replace("setup: [make-project, copy-inventory]", f"setup: {setup}"))
    assert any(problem in p for p in bookfmt.load_book(root).problems)


def test_a_step_no_chapter_embeds_is_a_problem(tmp_path):
    root = sampler(tmp_path)
    (root / "examples" / "spare.sh").write_text("echo spare\n")
    assert "examples/spare.sh: not embedded in any chapter" in bookfmt.load_book(root).problems


# ---------------------------------------------------------------- directives


def parse(text: str) -> tuple[steps.Step, list[str]]:
    return steps.parse_step(text, "a-step", "examples/a-step.sh")


def test_directives_and_their_defaults():
    step, problems = parse("#| wait: test -f a\n#| wait: test -f b\n#| mask: age, ip\n#| timeout: 30\n#| tab: other\n"
                           "echo hi\n")
    assert problems == []
    d = step.directives
    assert d.wait == ("test -f a", "test -f b") and d.mask == ("age", "ip") and d.timeout == 30
    assert (d.tab, d.compare, d.check, d.expect_exit) == ("other", "exact", False, 0)
    assert step.command == "echo hi\n" and step.kind == "step"
    default, _ = parse("echo hi\n")
    assert default.directives.timeout == steps.settings()["defaults"]["timeout_seconds"]


@pytest.mark.parametrize("text, problem", [
    ("#| retry: 3\necho hi\n", "'retry' isn't a directive"),
    ("echo hi\n#| wait: true\n", "directives go at the top of the file"),
    ("#| mask: colour\necho hi\n", "colour isn't a mask"),
    ("#| compare: fuzzy\necho hi\n", "'fuzzy' isn't one of exact, lines, none"),
    ("#| timeout: 0\necho hi\n", "isn't a number of seconds above 0"),
    ("#| timeout: 99999\necho hi\n", "isn't a number of seconds above 0"),
    ("#| expect-exit: 300\necho hi\n", "isn't an exit code"),
    ("#| hint: try again\necho hi\n", "only a check has a hint"),
    ("#| check\n#| tab: other\ntest -f a\n", "a check runs out of band"),
    ("#| background\n#| compare: exact\ntail -f log\n", "a background step runs until the chapter ends"),
    ("#| tab: Other Tab\necho hi\n", "isn't a name"),
    ("#| timeout: 5\n#| timeout: 6\necho hi\n", "is given twice"),
    ("#| check\n", "there's no command after the directives"),
    ("kubectl apply -f web.yaml && sleep 5\n", "waits, never sleep"),
    ("sleep 2\nls\n", "waits, never sleep"),
    ("#| wait: sleep 1\nls\n", "a wait polls; it never sleeps"),
])
def test_directive_problems(text, problem):
    _, problems = parse(text)
    assert any(problem in p for p in problems), problems
    assert all(p.startswith("examples/a-step.sh: ") for p in problems)


def test_sleep_as_a_word_in_a_command_is_allowed():
    _, problems = parse("kubectl run idle --image=busybox -- sleep 3600\n# then sleep 5 would be refused\n")
    assert problems == []


# ---------------------------------------------------------------- comparing output


def test_masks_replace_what_changes_from_run_to_run():
    a = "web-7d4b9c8f6d-x2k4z   1/1   Running   0   5m3s\n"
    b = "web-5c6f9d8b7c-q9wrt   1/1   Running   0   12s\n"
    assert steps.compare(a, b, "exact")[0] is False
    assert steps.compare(a, b, "exact", ("pod-suffix", "age")) == (True, "")
    assert steps.mask("at 2026-11-18T10:00:00Z from 10.42.0.7", ("time", "ip")) == "at <time> from <ip>"
    assert steps.mask('resourceVersion: "4512"', ("resource-version",)) == 'resourceVersion: "<resource-version>"'


def test_compare_lines_exact_and_none():
    assert steps.compare("b\nd\n", "a\nb\nc\nd\n", "lines") == (True, "")
    same, diff = steps.compare("d\nb\n", "a\nb\nc\nd\n", "lines")
    assert not same and "b" in diff
    assert steps.compare("x\n", "y\n", "none") == (True, "")
    assert steps.compare(None, "y\n", "exact") == (False, "no recorded output")
    same, diff = steps.compare("one\ntwo\n", "one\nthree\n", "exact")
    assert not same and "-two" in diff and "+three" in diff
    assert steps.compare("one  \n\n\n", "one\n", "exact") == (True, "")
