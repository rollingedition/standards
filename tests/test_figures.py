"""Figures drawn by examples (figures.py): the format and its binding, the shared style, the SVG compared and
cleaned, the checks, figures checked and recorded as outputs, and figures in the spoken script."""
import ast
import json
import subprocess

import pytest

from re_standards import affected, bookfmt, checks, cli, examples, figures, spoken, style
from bookkit import DRAWS, FIGURE_CHAPTER as CHAPTER, OUT, SECOND, SVG, make_book, make_figure_book as figure_book

# ---------------------------------------------------------------- the format and its binding


def test_a_figure_is_numbered_by_its_chapter_and_its_order_and_bound_across_chapters(tmp_path):
    book = bookfmt.load_book(figure_book(tmp_path / "b", second=True))
    assert book.problems == []
    a, b = book.figures["a-line"], book.figures["b-curve"]
    assert (a.number, a.chapter_id, a.section_id, a.caption) == ("1.1", "first-steps", "load-data", "One line, rising then falling")
    assert (b.number, b.chapter_id, b.section_id) == ("2.1", "second-steps", "again")
    assert a.alt == "A line that rises to its peak, then falls back" and a.file == "examples/figures/a-line.svg"
    assert book.bind("{{fig:a-line}} and {{ fig : b-curve }}") == "Figure 1.1 and Figure 2.1"
    assert book.bind("{{fig:b-curve}}", figure=book.figure_link()) == "[Figure 2.1](#figure--b-curve)"
    assert book.bind("{{fig:b-curve}}", figure=book.figure_link("Figura")) == "[Figura 2.1](#figure--b-curve)"
    assert book.figure_at("figure--b-curve") is b and book.figure_at("b-curve") is None
    assert book.binding_problems() == []


def test_an_unknown_figure_is_a_binding_problem_like_an_output(tmp_path):
    book = bookfmt.load_book(figure_book(tmp_path / "b", chapter=CHAPTER.replace("as {{fig:a-line}}", "as {{fig:no-such}}")))
    [problem] = book.binding_problems()
    assert problem.startswith("chapters/01-first-steps.md:") and "there is no figure 'no-such'" in problem
    assert book.bind("{{fig:no-such}}") == "{{fig:no-such}}"                       # stays visible, as {{out:}}'s do
    assert "W-82: chapters/01-first-steps.md" in "\n".join(style.check_style(book))


def test_the_rendered_hash_covers_a_figure_s_number(tmp_path):
    one = bookfmt.load_book(figure_book(tmp_path / "one", second=True))
    moved = figure_book(tmp_path / "moved", second=True)
    text = (moved / "chapters" / "02-second-steps.md").read_text()
    (moved / "chapters" / "02-second-steps.md").write_text(text.replace("## Again {#again}", "## Again {#again}\n\n"
                                                                        "![A line drawn first](../examples/figures/z.svg \"Z\")"))
    two = bookfmt.load_book(moved)
    assert two.figures["b-curve"].number == "2.2"                                 # a figure before it moves its number
    assert one.rendered_hashes()["again"] != two.rendered_hashes()["again"]
    assert one.content_hashes()["load-data"] == two.content_hashes()["load-data"]


def test_a_renderer_turns_each_figure_into_its_own_html_and_without_one_it_stays_an_image(tmp_path):
    book = bookfmt.load_book(figure_book(tmp_path / "b"))
    c = book.chapters[0]
    seen = []

    def figure_html(name, alt, caption):
        seen.append((name, alt, caption))
        return f'<figure id="{figures.anchor(name)}">{caption}</figure>'
    html = bookfmt.render_chapter(c, lambda eid: "", bind=lambda t: book.bind(t, figure=book.figure_link()),
                                  figure_html=figure_html)
    assert seen == [("a-line", "A line that rises to its peak, then falls back", "One line, rising then falling")]
    assert '<figure id="figure--a-line">One line, rising then falling</figure>' in html
    assert '<a href="#figure--a-line">Figure 1.1</a> draws one line' in html
    plain = bookfmt.render_chapter(c, lambda eid: "", bind=book.bind)
    assert '<img src="../examples/figures/a-line.svg"' in plain and "Figure 1.1 draws one line" in plain


def test_the_machine_markdown_writes_each_figure_as_its_block_with_bindings_filled_in(tmp_path):
    book = bookfmt.load_book(figure_book(tmp_path / "b"))
    md = bookfmt.machine_markdown(book.chapters[0], lambda eid: f"EXAMPLE {eid}", bind=book.bind,
                                  figure_block=lambda f: f"FIGURE {f.name}: {f.caption} / {f.alt}")
    assert "FIGURE a-line: One line, rising then falling / A line that rises" in md and "![" not in md
    assert "Figure 1.1 draws one line, which peaks at 3." in md
    assert "![A line" in bookfmt.machine_markdown(book.chapters[0], lambda eid: "")   # no figure_block: the image


def test_an_image_no_example_draws_is_refused_wherever_it_is(tmp_path):
    chapter = CHAPTER.replace("**Working rule:** Draw it.", "A photo: ![a photo](https://example.invalid/p.png)\n\n"
                                                            "![A drawing by hand, no example's](../images/hand.png \"Hand\")"
                                                            "\n\n**Working rule:** Draw it.")
    book = bookfmt.load_book(figure_book(tmp_path / "b", chapter=chapter))
    found = figures.problems(book)
    assert len([p for p in found if "an image no example draws" in p]) == 2
    assert any("(https://example.invalid/p.png)" in p for p in found) and any("(../images/hand.png)" in p for p in found)
    assert "hand" not in book.figures


# ---------------------------------------------------------------- the shared style


def test_the_shared_style_is_generated_from_the_standards_settings():
    text = figures.helper()
    ast.parse(text)                                                    # Python, as every book's runtime runs it
    s = figures.settings()
    for name, colour in s["palette"].items():
        assert f'{name} = "{colour["value"]}"' in text
    assert f'"svg.hashsalt": "{s["style"]["hash_salt"]}"' in text and '"svg.fonttype": "none"' in text
    assert 'metadata={"Date": None, "Creator": None}' in text and 'matplotlib.use("svg")' in text
    assert '"font.sans-serif": ["IBM Plex Sans", "DejaVu Sans"]' in text
    assert "SERIES = (ACCENT, INK, MUTED)" in text and 'linestyle=["-", "-", "--"]' in text
    assert 'print(f"figure: figures/{name}.svg")' in text and figures.MARK in text[:200]
    assert "_manager.ttflist = [f for f in _manager.ttflist if os.path.realpath(f.fname).startswith(_SHIPPED)]" in text


def test_a_book_with_figures_needs_the_shared_style_as_generated_and_gets_it_written(tmp_path, capsys):
    root = figure_book(tmp_path / "b", helper=False)
    problems = figures.problems(bookfmt.load_book(root))
    assert any("examples/lib/figures.py is missing" in p for p in problems)
    assert cli.main(["figures", "--book", str(root), "--write"]) == 0
    assert "wrote  examples/lib/figures.py" in capsys.readouterr().out
    assert figures.problems(bookfmt.load_book(root)) == []
    assert figures.write_helper(root) == []                                    # nothing to write the second time
    (root / "examples" / "lib" / "figures.py").write_text(figures.helper() + "\nINK = 'red'\n")
    assert any("isn't the standards' shared style" in p for p in checks.check_section_ids(bookfmt.load_book(root)))
    assert figures.helper_problems(make_book(tmp_path / "plain")) == []        # a book without figures needs none


# ---------------------------------------------------------------- the SVG


def jittered(svg: str) -> str:
    """The same figure as another machine draws it: a coordinate a last bit off, so the clip path's hash moved too."""
    return svg.replace("58.899401", "58.899402").replace("p14e344082f", "p0d9e1c2b3a")


def test_a_figure_from_another_machine_matches_within_the_tolerance_but_not_beyond_it():
    assert figures.compare(SVG, SVG) == []
    assert figures.compare(SVG, jittered(SVG)) == []                           # IDs read in the order they appear
    moved = figures.compare(SVG, SVG.replace("58.899401", "58.999401"))            # a path, a tick and its label
    assert len(moved) == 3 and all("moved by 0.1, more than the tolerance of 0.05" in m for m in moved)
    assert moved[0].startswith("/svg/g[1]/g[1]/path[1]: d moved")
    assert figures.compare(SVG, SVG.replace("58.899401", "58.999401"), tolerance=0.2) == []


@pytest.mark.parametrize("change,said", [
    (lambda s: s.replace(">0.20<", ">0.21<"), "the text is '0.21' where the committed figure has '0.20'"),
    (lambda s: s.replace("#9a4a06", "#9a4a07"), "style is"),
    (lambda s: s.replace('   <path d="M 40 100 L 400 20" clip-path="url(#p14e344082f)" style="fill: none; stroke: #9a4a06; '
                         'stroke-width: 1.4"/>\n', ""), "elements inside where the committed figure has"),
    (lambda s: s.replace('<use xlink:href', '<use opacity="0.5" xlink:href'), "attributes differ; with opacity"),
])
def test_a_change_of_text_colour_or_structure_never_matches(change, said):
    [found] = figures.compare(SVG, change(SVG))
    assert said in found


@pytest.mark.parametrize("bad,said", [
    ('<script>alert(1)</script>', "<script> element"),
    ('<foreignObject><p xmlns="http://www.w3.org/1999/xhtml">x</p></foreignObject>', "<foreignObject> element"),
    ('<rect onload="alert(1)" width="1" height="1"/>', "event handler (onload)"),
    ('<use xlink:href="https://example.invalid/a.svg#x"/>', "outside the figure"),
    ('<rect style="fill: url(https://example.invalid/x)" width="1" height="1"/>', "outside the figure"),
    ('<image xlink:href="data:image/png;base64,AAAA" width="1" height="1"/>', "draw it with paths"),
    ('<a xlink:href="#figure_1"><rect width="1" height="1"/></a>', "<a> element"),
])
def test_anything_active_in_a_figure_is_refused_by_the_check_and_by_every_renderer(bad, said, tmp_path):
    svg = SVG.replace(' <g id="figure_1">', f" {bad}\n <g id=\"figure_1\">")
    found = figures.active_problems(svg)
    assert found and said in "; ".join(found)
    with pytest.raises(figures.SvgError):
        figures.clean(svg)
    root = figure_book(tmp_path / "b", svg=svg)
    assert any(said in p for p in checks.check_section_ids(bookfmt.load_book(root)))


def test_an_entity_or_a_stylesheet_is_refused_too():
    assert "declares XML entities" in figures.active_problems(
        '<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg">&a;</svg>')[0]
    assert any("stylesheet" in p for p in figures.active_problems(
        '<?xml-stylesheet href="https://example.invalid/x.css"?>\n' + SVG[SVG.index("<svg"):]))
    assert any("more than the defaults" in p for p in figures.active_problems(
        SVG.replace("*{stroke-linejoin: round; stroke-linecap: butt}", "@import url(x.css);")))


def test_a_cleaned_figure_for_a_page_has_no_style_its_own_ids_and_a_class_for_each_palette_colour():
    out = figures.clean(SVG, prefix="figure--a-line-", inline=True,
                        classes={"#61574a": "fig-ink-muted", "#9a4a06": "fig-edition"},
                        root_attrs={"role": "img", "aria-label": "A line & a peak"})
    svg = out.svg
    assert "style=" not in svg and "<style" not in svg and "metadata" not in svg and "DOCTYPE" not in svg
    assert 'stroke-linejoin="round" stroke-linecap="butt"' in svg                 # the defaults, inherited from the root
    assert 'width="460.8pt"' not in svg and 'viewBox="0 0 460.8 187.2"' in svg
    assert 'role="img" aria-label="A line &amp; a peak"' in svg
    assert 'id="figure--a-line-p14e344082f"' in svg and 'clip-path="url(#figure--a-line-p14e344082f)"' in svg
    assert 'xlink:href="#figure--a-line-m85059689ef"' in svg and 'id="figure_1"' not in svg   # only IDs referred to
    assert 'stroke="#9a4a06" stroke-width="1.4" class="fig-edition-stroke"' in svg
    assert 'fill="#61574a" stroke="#61574a" class="fig-ink-muted-fill fig-ink-muted-stroke"' in svg
    assert 'fill="#e2d5b8"' not in svg and 'stroke="#e2d5b8"' in svg and "fig-rule" not in svg   # not given: no class
    assert out.texts == ["0.20"] and out.width == "460.8pt"
    assert '<text x="58.899401" y="167.796635" font-size="10px"' in svg
    assert "font-family=\"'IBM Plex Sans', 'DejaVu Sans', sans-serif\"" in svg
    figures.parse(svg)                                                          # still an SVG
    assert figures.active_problems(svg) == []


def test_a_cleaned_figure_for_a_file_keeps_its_size_and_ids():
    svg = figures.clean(SVG).svg
    assert svg.startswith('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                          'width="460.8pt" height="187.2pt"')
    assert 'id="figure_1"' in svg and 'clip-path="url(#p14e344082f)"' in svg and "style=" not in svg


def test_a_style_svg_has_no_attribute_for_can_t_be_cleaned():
    with pytest.raises(figures.SvgError, match="the style font"):
        figures.clean(SVG.replace("font-size: 10px;", "font: 10px sans-serif;"))


# ---------------------------------------------------------------- the checks


def test_a_figure_book_passes_every_check(tmp_path):
    book = bookfmt.load_book(figure_book(tmp_path / "b", second=True))
    assert figures.problems(book) == [] and figures.writing_problems(book) == []
    assert checks.check_section_ids(book) == []


def test_a_figure_must_be_drawn_by_an_example_its_own_chapter_embeds(tmp_path):
    root = figure_book(tmp_path / "b", second=True)
    (root / "examples" / "curves.out").write_text("nothing drawn\n")
    (root / "examples" / "draws.out").write_text(OUT + "figure: figures/b-curve.svg\n")
    found = figures.problems(bookfmt.load_book(root))
    assert any("figure 'b-curve' isn't drawn by an example this chapter embeds (draws draws it, in another chapter)" in p
               for p in found)


def test_a_missing_file_a_figure_embedded_twice_and_a_figure_no_chapter_shows_are_refused(tmp_path):
    root = figure_book(tmp_path / "b", chapter=CHAPTER.replace("Done, as", "![Again, the line that rises](../examples/"
                                                                "figures/a-line.svg \"Again\")\n\nDone, as"))
    (root / "examples" / "figures" / "orphan.svg").write_text(SVG)
    (root / "examples" / "figures" / "notes.txt").write_text("x")
    found = "\n".join(figures.problems(bookfmt.load_book(root)))
    assert "figure 'a-line' is embedded more than once" in found
    assert "examples/figures/orphan.svg: not embedded in any chapter" in found
    assert "examples/figures/notes.txt: examples/figures/ holds only figures" in found
    (root / "examples" / "figures" / "a-line.svg").unlink()
    assert "embeds examples/figures/a-line.svg, which doesn't exist" in "\n".join(figures.problems(bookfmt.load_book(root)))


def test_a_figure_past_the_size_cap_is_refused(tmp_path, monkeypatch):
    monkeypatch.setitem(figures.settings()["format"], "max_bytes", 1000)
    found = figures.problems(bookfmt.load_book(figure_book(tmp_path / "b")))
    assert any("more than the 1,000 a figure may be" in p for p in found)


@pytest.mark.parametrize("old,new,said", [
    ("![A line that rises to its peak, then falls back]", "![]", "W-39: figure 'a-line' needs alt text"),
    ("![A line that rises to its peak, then falls back]", "![a-line]", "W-39: the alt text of figure 'a-line' names it"),
    ("![A line that rises to its peak, then falls back]", "![Chart of a-line.svg here]", "names it rather than"),
    (' "One line, rising then falling")', ")", "W-82: figure 'a-line' needs a caption"),
    ("{{fig:a-line}} draws", "It draws", None),
    ("Done, as {{fig:a-line}} shows.", "Done, as Figure 1.1 shows.", "W-82: a typed figure number ('Figure 1.1')"),
])
def test_the_writing_of_a_figure_is_held_to_w_39_and_w_82(old, new, said, tmp_path):
    book = bookfmt.load_book(figure_book(tmp_path / "b", chapter=CHAPTER.replace(old, new)))
    found = "\n".join(style.check_style(book))
    if said:
        assert said in found
    else:                                                       # still pointed to once, so still fine
        assert "W-82" not in found
    if old == "{{fig:a-line}} draws":
        both = CHAPTER.replace(old, new).replace("as {{fig:a-line}} shows", "as shown")
        again = bookfmt.load_book(figure_book(tmp_path / "c", chapter=both))
        assert "W-82: the prose never points to figure 'a-line'" in "\n".join(style.check_style(again))


def test_a_typed_figure_number_in_an_example_and_a_colour_outside_the_palette_are_w_82(tmp_path):
    root = figure_book(tmp_path / "b", svg=SVG.replace("#9a4a06", "#ff0000"))
    (root / "examples" / "draws.py").write_text(DRAWS.replace("Draws one line", "Draws Figure 1.1"))
    found = "\n".join(figures.writing_problems(bookfmt.load_book(root)))
    assert "examples/draws.py: W-82: a typed figure number ('Figure 1.1') in the example" in found
    assert "examples/figures/a-line.svg: W-82: draws in #ff0000" in found


def test_re_check_figures_says_what_it_found(tmp_path, capsys):
    root = figure_book(tmp_path / "b", second=True)
    assert cli.main(["figures", "--book", str(root)]) == 0
    out = capsys.readouterr().out
    assert "2 figure(s), each drawn by an example its chapter embeds, and the shared style is the standards'" in out
    assert cli.main(["section-ids", "--book", str(root)]) == 0
    assert "2 figure(s), each drawn by an example its chapter embeds" in capsys.readouterr().out
    assert cli.main(["figures", "--book", str(make_book(tmp_path / "plain"))]) == 0
    assert "ok  no figures" in capsys.readouterr().out


# ---------------------------------------------------------------- checked and recorded as outputs


def tree(root):
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_a_figure_is_checked_as_an_output_and_the_working_copy_stays_as_it_was(tmp_path):
    root = figure_book(tmp_path / "b")
    before = tree(root)
    results, _ = examples.run_examples(bookfmt.load_book(root), examples.HostBackend())
    [r] = results
    assert r.passing and r.figures == [{"name": "a-line", "file": "examples/figures/a-line.svg",
                                        "sha256": r.figures[0]["sha256"], "passing": True}]
    entry = examples.results_json(results, {})["examples"][0]
    assert entry["figures"][0]["file"] == "examples/figures/a-line.svg" and "svgs" not in entry
    json.dumps(entry)
    assert tree(root) == before                                              # nothing written into the book


def test_a_figure_drawn_on_another_machine_passes_and_one_that_moved_fails_until_recorded(tmp_path, capsys):
    root = figure_book(tmp_path / "b")
    (root / "examples" / "drawing.svg").write_text(jittered(SVG))
    [r], _ = examples.run_examples(bookfmt.load_book(root), examples.HostBackend())
    assert r.passing
    (root / "examples" / "drawing.svg").write_text(SVG.replace(">0.20<", ">0.25<"))
    [r], _ = examples.run_examples(bookfmt.load_book(root), examples.HostBackend())
    assert not r.passing and "examples/figures/a-line.svg: /svg/g[1]/g[1]/text[1]: the text is '0.25'" in r.diff
    assert r.figures[0]["passing"] is False and r.figures[0]["differences"]
    assert cli.main(["examples", "--book", str(root), "--backend", "host"]) == 1
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--record"]) == 0
    assert "recorded  draws  (Python" in capsys.readouterr().out
    assert ">0.25<" in (root / "examples" / "figures" / "a-line.svg").read_text()
    assert cli.main(["examples", "--book", str(root), "--backend", "host"]) == 0


def test_a_new_figure_fails_until_it_s_recorded_and_one_no_longer_drawn_is_removed(tmp_path):
    root = figure_book(tmp_path / "b")
    (root / "examples" / "figures" / "a-line.svg").unlink()
    book = bookfmt.load_book(root)
    [r], _ = examples.run_examples(book, examples.HostBackend())
    assert not r.passing and "a-line.svg isn't in the book yet" in r.diff
    assert examples.record_figures(book, r) == ["examples/figures/a-line.svg"]
    (root / "examples" / "draws.py").write_text('print("peak: 3")\n')               # it draws nothing now
    book = bookfmt.load_book(root)
    [r], _ = examples.run_examples(book, examples.HostBackend())
    assert examples.record_figures(book, r) == ["examples/figures/a-line.svg (removed)"]
    assert not (root / "examples" / "figures" / "a-line.svg").exists()


def test_a_figure_that_depends_on_the_hash_seed_fails(tmp_path):
    root = figure_book(tmp_path / "b")
    (root / "examples" / "draws.py").write_text(DRAWS.replace(
        'Path("figures/a-line.svg").write_text(Path("drawing.svg").read_text())',
        'import os\nPath("figures/a-line.svg").write_text(Path("drawing.svg").read_text().replace("0.20", '
        'os.environ["PYTHONHASHSEED"]))'))
    (root / "examples" / "figures" / "a-line.svg").write_text(SVG.replace("0.20", "0"))
    [r], _ = examples.run_examples(bookfmt.load_book(root), examples.HostBackend(), seeds=[0, 1])
    assert not r.passing and "the figure depends on the hash seed: figures/a-line.svg differs under seeds 0 and 1" in r.seed_diff


def test_an_example_without_figures_reports_what_it_always_did(tmp_path):
    root = make_book(tmp_path / "b")
    (root / "examples" / ".python-version").write_text("3.12.15\n")
    [r], runtime = examples.run_examples(bookfmt.load_book(root), examples.HostBackend())
    assert set(examples.results_json([r], runtime)["examples"][0]) == {
        "example_id", "passing", "exit_code", "stdout", "expected", "diff", "stderr_tail", "versions", "direct",
        "seconds", "seeds", "seed_diff"}


def test_a_changed_figure_runs_the_example_that_draws_it(tmp_path):
    root = figure_book(tmp_path / "b")
    git = ["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.invalid"]
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "base"], check=True)
    (root / "examples" / "figures" / "a-line.svg").write_text(jittered(SVG))
    change, why = affected.change_from_git(root, "HEAD")
    assert change is not None, why
    own, _, everything = affected._classify(bookfmt.load_book(root), change)
    assert own == {"draws": ["its recorded figure changed"]} and everything == []


# ---------------------------------------------------------------- narration


def test_narration_reads_a_figure_s_number_and_caption_never_its_alt_text(tmp_path):
    book = bookfmt.load_book(figure_book(tmp_path / "b"))
    lines = spoken.chapter_script(book, "first-steps")
    [fig] = [line for line in lines if line.kind == "figure"]
    assert fig.text == "Figure one point one. One line, rising then falling." and fig.unit == "load-data"
    said = " ".join(line.text for line in lines)
    assert "Figure one point one draws one line, which peaks at three." in said
    assert "rises to its peak" not in said and "a-line" not in said and "svg" not in said
    assert spoken.check_narration(book, chapter_id="first-steps") == [
        "chapters/01-first-steps.md:15: example 'draws' has no description; add [examples.draws] say = \"…\" to "
        "narration/first-steps.toml"]


def test_the_examples_check_looks_for_drawn_figures_where_the_settings_put_them():
    assert examples.drawn_folder() == "figures" and figures.folder() == "examples/figures"
