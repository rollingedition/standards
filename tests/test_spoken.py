"""The spoken script and `re-check narration`.

tests/fixtures/primer-chapter holds a released chapter, "What relevance means" from A Primer on Search Relevance
(CC BY 4.0, Rolling Edition), with the recorded outputs its bindings read; its examples' code isn't needed.
"""
import shutil
from pathlib import Path

import pytest

from re_standards import bookfmt, cli, spoken
from bookkit import make_book

FIXTURE = Path(__file__).parent / "fixtures" / "primer-chapter"

CHAPTER = '''---
chapter_id: first-steps
---

# First steps with `lib.store`

Opening text: the store has 13,077 judgments (Chen et al., 2022).

## Score one ranking {#score-one-ranking}

BM25 scores an nDCG@10 of {{out:ndcg-for-one-query:ndcg@10}} on [the test queries](#score-one-ranking), and p = 0.013.
The gap runs to -0.138, 99% of the time, e.g. for `lib.store.product_text` and `ndcg_at_k`.

[Example: ndcg-for-one-query](../examples/ndcg-for-one-query.py)

```text
DCG@10  = sum over positions i from 1 to 10 of  grade(i) / log2(i + 1)
```

**Working rule:** Report nDCG@10 with every *score*.

### Compare two runs {#compare-two-runs}

| Measure | BM25 | Semantic |
| --- | --- | --- |
| nDCG@10 | 0.725 | 0.830 |

- First item, with [a link](#score-one-ranking).
- Second item, in **bold**.

1. Count the pairs.
2. Divide them.

> A quoted line (Saracevic, 2007).

[Example: count-labels](../examples/count-labels.py)

```python
print("unread")
```
'''

LEXICON = '''[terms]
"nDCG@10" = "N D C G at ten"
"BM25" = "B M twenty-five"

[words]
ndcg = "N D C G"
'''

DESCRIBED = '''[examples.ndcg-for-one-query]
say = "The code scores one ranking and prints its N D C G at ten: {{out:ndcg-for-one-query:ndcg@10}}."

[[blocks]]
section = "score-one-ranking"
starts = "DCG@10  = sum over positions"
say = "D C G at ten is the sum, over positions one to ten, of each grade divided by log base two of the position plus one."

[[tables]]
section = "compare-two-runs"
starts = "| Measure |"
say = "A table of each run's N D C G at ten."
'''

EXAMPLES = {"ndcg-for-one-query": ("print('ndcg@10: 0.615')\n", "ndcg@10: 0.615\n"),
            "count-labels": ("print('labels: 3')\n", "labels: 3\n")}


def tiny(root: Path, chapter: str = CHAPTER, lexicon: str | None = LEXICON, described: str | None = None, **files):
    make_book(root, chapter=chapter, examples=EXAMPLES)
    folder = root / "narration"
    folder.mkdir()
    if lexicon is not None:
        (folder / "lexicon.toml").write_text(lexicon)
    if described is not None:
        (folder / "first-steps.toml").write_text(described)
    for name, text in files.items():
        (folder / name).write_text(text)
    book = bookfmt.load_book(root)
    assert book.problems == []
    return book


def texts(lines, kind=None):
    return [line.text for line in lines if kind is None or line.kind == kind]


# ---------------------------------------------------------------- numbers as words


def test_numbers_years_decimals_and_ordinals():
    assert spoken.cardinal(0) == "zero"
    assert spoken.cardinal(13077) == "thirteen thousand and seventy-seven"
    assert spoken.cardinal(1177) == "one thousand one hundred and seventy-seven"
    assert spoken.cardinal(1177, and_=False) == "one thousand one hundred seventy-seven"
    assert spoken.cardinal(2_500_000_000) == "two billion five hundred million"
    assert spoken.cardinal(-40) == "minus forty"
    assert [spoken.year(y) for y in (1998, 2004, 2000, 2022, 1905, 1900, 2010)] == [
        "nineteen ninety-eight", "two thousand four", "two thousand", "twenty twenty-two", "nineteen oh five",
        "nineteen hundred", "twenty ten"]
    assert spoken.decimal("0.615") == "zero point six one five"
    assert spoken.decimal("1,234.05") == "one thousand two hundred and thirty-four point zero five"
    assert [spoken.ordinal(n) for n in (1, 2, 3, 12, 21, 30)] == ["first", "second", "third", "twelfth", "twenty-first",
                                                                  "thirtieth"]
    assert spoken.plural("ten") == "tens" and spoken.plural("nineteen ninety") == "nineteen nineties"


@pytest.mark.parametrize("text, said", [
    ("p = 0.013", "p equals zero point zero one three"),
    ("from -0.138 to −0.004", "from minus zero point one three eight to minus zero point zero zero four"),
    ("99% of 1,177 pairs", "Ninety-nine percent of one thousand one hundred and seventy-seven pairs"),
    ("(Chen et al., 2022, section 3.2.1)", "(Chen et al., twenty twenty-two, section three point two point one)"),
    ("(Järvelin and Kekäläinen, 2002)", "(Järvelin and Kekäläinen, two thousand two)"),
    ("Edition 2026.10.6", "Edition twenty twenty-six point ten point six"),
    ("in the 1990s, the top 10s", "in the nineteen nineties, the top tens"),
    ("on 2026-10-01 and Oct 23, 2026", "on October first, twenty twenty-six and October twenty-third, twenty twenty-six"),
    ("judged@10 and SPLADE v2", "judged at ten and SPLADE version two"),
    ("a 3×3 table, 6–10× faster", "a three by three table, six to ten times faster"),
    ("P(t | c) < 0.05", "P(t given c) less than zero point zero five"),
    ("10⁻⁵ and h², λ₃", "Ten to the minus five and h squared, lambda three"),
    ("e.g. a CSV, i.e. JSON", "for example a C S V, that is Jason"),
    ("so +0.005 and $3", "so plus zero point zero zero five and three dollars"),
    ("360M parameters, 3.00e-03", "Three hundred and sixty million parameters, three point zero zero times ten to the minus three"),
])
def test_shared_rules_read_symbols_and_numbers_as_words(text, said):
    assert spoken.Speaker(spoken.load_rules()).say(text) == said


def test_a_bound_number_is_a_count_never_a_year(tmp_path):
    chapter = CHAPTER.replace("the store has 13,077 judgments", "the store has {{out:count-labels:labels}} judgments (Zobel, 1998)")
    root = make_book(tmp_path, chapter=chapter, examples={**EXAMPLES, "count-labels": ("", "labels: 1937\n")})
    lines = spoken.chapter_script(bookfmt.load_book(root), "first-steps", narration=spoken.Narration())
    assert "the store has one thousand nine hundred and thirty-seven judgments (Zobel, nineteen ninety-eight)" in lines[1].text


def test_rules_are_versioned():
    assert isinstance(spoken.rules_version(), int) and spoken.rules_version() >= 1


# ---------------------------------------------------------------- the script


def test_the_opening_names_the_chapter_and_book_but_never_the_edition(tmp_path):
    book = tiny(tmp_path)
    lines = spoken.chapter_script(book, "first-steps", edition="2026.10.6")
    assert (lines[0].n, lines[0].kind, lines[0].unit) == (1, "opening", "first-steps")
    assert lines[0].text == ("Chapter one. First steps with lib dot store. Tiny Book. Read by an A I voice, word for word "
                             "from this edition's text. Code, output and tables are on the page.")
    assert (lines[-1].kind, lines[-1].unit, lines[-1].text) == ("ending", "first-steps", "End of chapter one.")
    assert [line.n for line in lines] == list(range(1, len(lines) + 1))
    # a chapter whose words didn't change keeps its recording across editions: the edition changes no line
    assert [line.text for line in spoken.chapter_script(book, "first-steps")] == [line.text for line in lines]


def test_a_parenthesis_holding_only_links_into_the_book_is_not_read(tmp_path):
    book = tiny(tmp_path)
    chapter = book.root / "chapters" / "01-first-steps.md"
    assert "Opening text: the store has 13,077 judgments (Chen et al., 2022)." in chapter.read_text()
    chapter.write_text(chapter.read_text().replace(
        "Opening text: the store has 13,077 judgments (Chen et al., 2022).",
        "Read the file ([Score one ranking](#score-one-ranking)), as [the next section](#compare-two-runs) says "
        "([Score one ranking](#score-one-ranking), [Compare two runs](#compare-two-runs)), not (see [Score one "
        "ranking](#score-one-ranking)) or ([a source](https://example.com/paper)).", 1))
    said = " ".join(texts(spoken.chapter_script(bookfmt.load_book(book.root), "first-steps")))
    assert ("Read the file, as the next section says, not (see Score one ranking) or (a source)." in said)


def test_headings_are_sentences_and_lines_carry_their_section(tmp_path):
    lines = spoken.chapter_script(tiny(tmp_path), "first-steps")
    assert texts(lines, "heading") == ["Score one ranking.", "Compare two runs."]
    assert {line.unit for line in lines if line.kind == "heading"} == {"score-one-ranking", "compare-two-runs"}
    assert lines[1].unit == "first-steps" and lines[1].kind == "prose"
    assert lines[1].text == "Opening text: the store has thirteen thousand and seventy-seven judgments (Chen et al., twenty twenty-two)."
    assert all("{#" not in line.text for line in lines)


def test_prose_reads_links_emphasis_inline_code_and_the_lexicon(tmp_path):
    lines = spoken.chapter_script(tiny(tmp_path), "first-steps")
    prose = [line for line in lines if line.unit == "score-one-ranking" and line.kind == "prose"]
    assert len(prose) == 1                                   # a paragraph is one clip, its soft break a space
    assert prose[0].text == ("B M twenty-five scores an N D C G at ten of zero point six one five on the test queries, and "
                             "p equals zero point zero one three. The gap runs to minus zero point one three eight, "
                             "ninety-nine percent of the time, for example for lib dot store dot product text and "
                             "N D C G at k.")
    assert prose[0].line == 11


def test_examples_are_announced_or_described_with_their_bindings_filled(tmp_path):
    bare = spoken.chapter_script(tiny(tmp_path / "a"), "first-steps")
    assert texts(bare, "example") == ["Example: N D C G for one query. Its code and output are on the page.",
                                      "Example: count labels. Its code and output are on the page."]
    described = spoken.chapter_script(tiny(tmp_path / "b", described=DESCRIBED), "first-steps")
    assert texts(described, "example")[0] == ("Example: N D C G for one query. The code scores one ranking and prints its "
                                              "N D C G at ten: zero point six one five.")


def test_blocks_and_tables_are_described_or_announced(tmp_path):
    bare = spoken.chapter_script(tiny(tmp_path / "a"), "first-steps")
    assert texts(bare, "block") == ["A formula is on the page.", "Code is on the page."]
    assert texts(bare, "table") == ["A table is on the page."]
    described = spoken.chapter_script(tiny(tmp_path / "b", described=DESCRIBED), "first-steps")
    assert texts(described, "block")[0].startswith("D C G at ten is the sum, over positions one to ten,")
    assert texts(described, "table") == ["A table of each run's N D C G at ten."]
    assert [line.unit for line in described if line.kind == "table"] == ["compare-two-runs"]


def test_lists_are_read_item_by_item_and_quotes_and_working_rules_as_written(tmp_path):
    lines = spoken.chapter_script(tiny(tmp_path), "first-steps")
    assert texts(lines, "item") == ["First item, with a link.", "Second item, in bold.", "One. Count the pairs.", "Two. Divide them."]
    assert texts(lines, "working-rule") == ["Working rule: Report N D C G at ten with every score."]
    assert texts(lines, "quote") == ["A quoted line (Saracevic, two thousand seven)."]


def test_an_examples_output_in_the_text_is_never_read(tmp_path):
    chapter = CHAPTER.replace("[Example: count-labels](../examples/count-labels.py)\n",
                              "[Example: count-labels](../examples/count-labels.py)\n\nOutput:\n\n```text\nlabels: 3\n```\n")
    lines = spoken.chapter_script(tiny(tmp_path, chapter=chapter), "first-steps")
    assert not any("Output" in t or "labels: 3" in t for t in texts(lines))
    assert texts(lines, "block") == ["A formula is on the page.", "Code is on the page."]


def test_the_whole_book_opens_and_closes_with_credits(tmp_path):
    book = tiny(tmp_path)
    lines = spoken.book_script(book, edition="2026.10.6", credits={"voice": "a voice's credit", "where": "rollingedition.com"})
    assert (lines[0].kind, lines[0].unit) == ("credits", "tiny-book")
    assert lines[0].text.startswith("Tiny Book. By Rolling Edition, with A I. Read by an A I voice, a voice's credit. "
                                    "Edition twenty twenty-six point ten point six.")
    assert lines[-1].text == ("This is the end of Tiny Book, edition twenty twenty-six point ten point six. The current "
                              "edition is at rolling edition dot com.")
    assert [line.n for line in lines] == list(range(1, len(lines) + 1))
    assert texts(lines)[1:-1] == texts(spoken.chapter_script(book, "first-steps", edition="2026.10.6"))
    unnamed = spoken.book_script(book)                       # a field nobody gives is left out
    assert unnamed[0].text.startswith("Tiny Book. By Rolling Edition, with A I. Read by an A I voice. Its text is under")
    assert unnamed[-1].text == "This is the end of Tiny Book."


# ---------------------------------------------------------------- the check


def test_the_check_lists_missing_descriptions_and_uncovered_terms(tmp_path):
    book = tiny(tmp_path, lexicon=None, chapter=CHAPTER.replace("`ndcg_at_k`", "`ndcg_at_k` at `k1=1.5`"))
    warnings = spoken.check_narration(book)
    text = "\n".join(warnings)
    assert "chapters/01-first-steps.md:14: example 'ndcg-for-one-query' has no description" in text
    assert "example 'count-labels' has no description" in text
    assert ('chapters/01-first-steps.md:16: a text block in \'score-one-ranking\' has no description; add [[blocks]] '
            'section = "score-one-ranking", starts = "DCG@10 = sum over positions i from 1 to", say = "…" to '
            'narration/first-steps.toml') in text
    assert 'a python block in \'compare-two-runs\' has no description; add [[blocks]] section = "compare-two-runs", starts = "print(\\"unread\\")"' in text
    assert "a table in 'compare-two-runs' has no description" in text
    # without the book's lexicon, its terms are listed once per chapter, with the line they first appear on
    assert "chapters/01-first-steps.md:11: no rule reads 'BM25'; add a reading to narration/lexicon.toml" in text
    assert "no rule reads 'nDCG' (2 times)" in text           # its @10 reads as "at ten" already
    # inline code is named whole, as a lexicon entry would match it, with the words no rule reads
    assert "chapters/01-first-steps.md:11: no rule reads 'k1' in the code 'k1=1.5'; add a reading to narration/lexicon.toml" in text
    assert "ndcg_at_k" not in text                            # a lowercase identifier reads by its parts


def test_the_check_is_quiet_once_everything_is_described(tmp_path):
    assert spoken.check_narration(tiny(tmp_path, described=DESCRIBED.replace(
        "[[blocks]]", '[examples.count-labels]\nsay = "The code counts labels."\n\n[[blocks]]')
        + '\n[[blocks]]\nsection = "compare-two-runs"\nstarts = "print("\nsay = "The code prints one word."\n')) == []


def test_the_check_lists_descriptions_whose_element_is_gone_or_changed(tmp_path):
    stale = DESCRIBED.replace('starts = "DCG@10  = sum over positions"', 'starts = "DCG@k = sum"') + '''
[examples.no-such-example]
say = "Gone."

[[tables]]
section = "no-such-section"
starts = "| Measure |"
say = "Gone too."
'''
    stale = stale.replace("{{out:ndcg-for-one-query:ndcg@10}}", "{{out:ndcg-for-one-query:recall}}")
    warnings = spoken.check_narration(tiny(tmp_path, described=stale, **{"old-chapter.toml": "", "broken.toml": "x = ["}))
    text = "\n".join(warnings)
    assert ("narration/first-steps.toml: [[blocks]] 1 (section 'score-one-ranking', starts 'DCG@k = sum'): no block in the "
            'section starts so; its blocks start: "DCG@10 = sum over positions i from 1 to 10 of grade(i) / log2(i + 1)"') in text
    assert "narration/first-steps.toml: [examples.no-such-example]: this chapter doesn't embed 'no-such-example'; there's no such example" in text
    assert "[[tables]] 2 (section 'no-such-section', starts '| Measure |'): there's no section 'no-such-section' in this chapter" in text
    assert "narration/first-steps.toml: [examples.ndcg-for-one-query]: {{out:ndcg-for-one-query:recall}}: ndcg-for-one-query.out has no line(s) labelled 'recall'" in text
    assert "narration/old-chapter.toml: there's no chapter 'old-chapter' in this book" in text
    assert any(w.startswith("narration/broken.toml doesn't parse") for w in warnings)
    # a block whose description went stale is announced again, never read from the stale entry
    assert texts(spoken.chapter_script(tiny(tmp_path / "again", described=stale), "first-steps"), "block")[0] == "A formula is on the page."


def test_an_unresolved_binding_stays_as_written_and_is_listed(tmp_path):
    chapter = CHAPTER.replace("{{out:ndcg-for-one-query:ndcg@10}}", "{{out:ndcg-for-one-query:recall}}")
    book = tiny(tmp_path, chapter=chapter)
    prose = [t for t in texts(spoken.chapter_script(book, "first-steps")) if t.startswith("B M twenty-five")]
    assert "an N D C G at ten of {{out:ndcg-for-one-query:recall}} on" in prose[0]
    assert any("chapters/01-first-steps.md:11: {{out:ndcg-for-one-query:recall}}" in w for w in spoken.check_narration(book))


def test_narration_files_are_checked_for_what_they_hold(tmp_path):
    narration = spoken.load_narration(tiny(tmp_path, lexicon='[terms]\n"x" = 1\n[extra]\n', described=(
        '[examples.ndcg-for-one-query]\nsay = "ok"\ntone = "warm"\n\n[[blocks]]\nsection = "score-one-ranking"\n')).root)
    text = "\n".join(narration.problems)
    assert "narration/lexicon.toml: unknown table [extra]" in text and "[terms]: 'x' must be a string" in text
    assert "[examples.ndcg-for-one-query] holds one key, say, a string" in text
    assert "[[blocks]] 1 needs section, starts and say" in text


def test_re_check_narration_warns_without_failing_and_prints_the_script(tmp_path, capsys):
    root = tiny(tmp_path, lexicon=None).root
    assert cli.main(["narration", "--book", str(root)]) == 0
    err = capsys.readouterr().err
    assert "Narration:" in err and "warning(s)" in err and "has no description" in err
    assert cli.main(["narration", "--book", str(root), "--strict"]) == 1
    capsys.readouterr()
    assert cli.main(["narration", "--book", str(root), "--chapter", "first-steps", "--script", "--edition", "2026.10.6"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("   1  opening  first-steps\n      Chapter one. First steps with lib dot store. Tiny Book. Read by")
    assert "\n   3  heading  score-one-ranking\n      Score one ranking.\n" in out
    assert cli.main(["narration", "--book", str(root), "--chapter", "nope"]) == 1
    described = tiny(tmp_path / "quiet", described=DESCRIBED.replace("[[blocks]]", '[examples.count-labels]\nsay = "x"\n\n[[blocks]]')
                     + '\n[[blocks]]\nsection = "compare-two-runs"\nstarts = "print("\nsay = "x"\n').root
    capsys.readouterr()
    assert cli.main(["narration", "--book", str(described)]) == 0
    assert capsys.readouterr().out.startswith("ok  1 chapter(s): every term has a reading")


# ---------------------------------------------------------------- a released chapter


@pytest.fixture
def primer(tmp_path):
    root = tmp_path / "primer"
    shutil.copytree(FIXTURE, root)
    return bookfmt.load_book(root)


def test_a_released_chapter_reads_as_the_first_voice_samples_did(primer):
    lines = spoken.chapter_script(primer, "what-relevance-means", edition="2026.10.6")
    assert len(lines) == 88
    assert lines[0].text.startswith("Chapter two. What relevance means. A Primer on Search Relevance. Read by an A I voice")
    by_kind = {k: sum(line.kind == k for line in lines) for k in spoken.KINDS}
    assert by_kind == {"opening": 1, "heading": 11, "prose": 47, "item": 7, "working-rule": 10, "quote": 0,
                       "example": 10, "block": 1, "table": 0, "ending": 1, "credits": 0}
    said = "\n".join(texts(lines))
    for words in ("scores its rankers against thirteen thousand and seventy-seven judgments",
                  "Example: word match versus judgment. Its code and output are on the page.",
                  "Of the one thousand one hundred and seventy-seven pairs with a full word match, zero point seven seven seven are exact",
                  "(Chen et al., twenty twenty-two, section five)",
                  "(Chen et al., twenty twenty-two, Table three)",
                  "(Zobel, nineteen ninety-eight)",
                  "in the top tens",
                  "(Tsagkias et al., twenty twenty, section three point one point one)",
                  "the ninety-five percent bootstrap interval runs from minus zero point one three eight",
                  "Working rule: Keep one grade per pair and write down the rule that chose it."):
        assert words in said
    assert texts(lines, "block") == ["A formula is on the page."]


def test_a_released_chapter_lists_its_backfill(primer):
    warnings = spoken.check_narration(primer)
    assert sum("has no description" in w for w in warnings) == 11      # ten examples and a formula
    assert any("no rule reads 'BM25' (" in w for w in warnings)


def test_a_lexicon_reading_inside_a_code_path_keeps_the_dots_and_slashes_beside_it(tmp_path):
    book = tiny(tmp_path, lexicon='[terms]\n"bpe" = "B P E"\n"README" = "read me"\n')
    speaker = spoken.Speaker(spoken.load_rules(), spoken.load_narration(book.root))
    assert speaker.say(speaker.code("lib.bpe.train")) == "lib dot B P E dot train"
    assert speaker.say(speaker.code("wands/README.md")) == "wands slash read me dot md"
    assert speaker.say(speaker.code("lib.store.product_text")) == "lib dot store dot product text"


def test_a_price_keeps_a_comma_after_it_and_a_chain_of_numbers_split_by_slashes_is_a_list(tmp_path):
    speaker = spoken.Speaker(spoken.load_rules(), spoken.load_narration(tiny(tmp_path).root))
    assert speaker.say("It costs $30, about a dollar a day.").startswith("It costs thirty dollars, about")
    assert speaker.say("Wins, losses and ties: 9 / 14 / 7.") == "Wins, losses and ties: nine, fourteen, seven."
    assert speaker.say("The score is x / y here.") == "The score is x over y here."


def test_a_date_without_a_year_reads_as_the_month_and_its_day(tmp_path):
    speaker = spoken.Speaker(spoken.load_rules(), spoken.load_narration(tiny(tmp_path).root))
    assert speaker.say("The report is due Oct 31.") == "The report is due October thirty-first."
    assert speaker.say("From March 2 to Sept 30, every run.") == "From March second to September thirtieth, every run."
    assert speaker.say("It shipped Oct 1, 2026.") == "It shipped October first, twenty twenty-six."
    assert speaker.say("Version Oct 3.2 is odd.").startswith("Version Oct three point two")
