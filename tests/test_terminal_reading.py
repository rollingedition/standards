"""A terminal book's steps, checks and files, as narration and the style lint read them: by their names and
descriptions, never their links as prose. A Python book reads exactly as before."""
import shutil
from pathlib import Path

from re_standards import bookfmt, narrative, spoken, style

SAMPLER = Path(__file__).parent / "fixtures" / "terminal-sampler"


def script(book, chapter_id):
    return [(line.kind, line.text) for line in spoken.chapter_script(book, chapter_id)]


def test_narration_reads_a_step_a_check_and_a_file_by_their_templates():
    lines = script(bookfmt.load_book(SAMPLER), "files-and-folders")
    kinds = [k for k, _ in lines]
    assert ("step", "Step: make project. Its command and output are on the page.") in lines
    assert ("check", "Check your work: project has readme. Its command is on the page.") in lines
    assert ("file", "File: inventory. It's on the page.") in lines
    assert kinds.count("step") == 3 and kinds.count("check") == 1 and kinds.count("file") == 1
    assert not any("sh" in t.split() or "examples" in t for k, t in lines if k == "prose")


def test_a_steps_description_is_read_after_its_name_and_a_missing_one_is_warned(tmp_path):
    root = tmp_path / "book"
    shutil.copytree(SAMPLER, root)
    (root / "narration").mkdir()
    (root / "narration" / "files-and-folders.toml").write_text(
        '[examples.make-project]\nsay = "It makes the project folder and its README, then lists the folder."\n')
    book = bookfmt.load_book(root)
    assert any(k == "step" and t.startswith("Step: make project. It makes the project folder and its")
               for k, t in script(book, "files-and-folders"))
    warnings = spoken.check_narration(book, chapter_id="files-and-folders")
    assert any("step 'copy-inventory' has no description" in w for w in warnings)
    assert any("check 'project-has-readme' has no description" in w for w in warnings)
    assert not any("make-project" in w for w in warnings) and not any("'inventory'" in w for w in warnings)


def test_the_style_lint_and_the_narrative_checks_count_no_link_as_prose():
    book = bookfmt.load_book(SAMPLER)
    chapter = book.chapter("files-and-folders")
    prose = [t for _, t in style._prose_lines(chapter.body, chapter.body_offset)]
    assert not any(t.lstrip().startswith(("[Step:", "[Check:", "[File:")) for t in prose)
    kinds = [b[0] for _, blocks in style._section_parts(chapter.body, chapter.body_offset) for b in blocks]
    assert kinds.count("embed") == 5
    assert style.is_embed("[Step: make-project](../examples/make-project.sh)")
    assert not style.is_embed("[a link](https://example.org/)") and not style.is_embed("[Data](../examples/data/x.csv)")
    assert narrative._step_line("[File: inventory](../examples/data/inventory.csv)")
