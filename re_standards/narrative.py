"""Section 14 of the writing standards, "Narrative" (W-61 to W-68): its lint half, run by `re-check style`.

A linter can't tell a natural paragraph from a stiff one, so these checks look only for the habits a review of the
released books measured (Nov 13, 2026), each the mark of a rule followed to the letter rather than written to: a
sentence built to hold a bound yes or no, a paragraph that reads out a ledger of numbers, documentation quoted into
the prose, an opener that marks a step instead of making a sentence, a sentence or an opening repeated across the
book, and an example with no word on what it's for. Whether a paragraph reads well stays the critic's to judge.

`problems` fail the check. `warnings` name what a writer should read again, and never fail it. Limits and word lists
are in data/writing.toml, under [narrative].
"""
from __future__ import annotations

import ast
import io
import re
import tokenize
from collections import defaultdict

from .bookfmt import BINDING, Book

FENCE = re.compile(r"^(```|~~~)")
EMBED_LINE = re.compile(r"^\s*\[Example:[^\]]*\]\([^)]*\)\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
CODE_SPAN = re.compile(r"`[^`]*`")
LINK = re.compile(r"(?<!!)\[([^\]]*)\]\([^)\s]*\)")
QUOTED = re.compile(r'"([^"]*)"|“([^”]*)”')
LEAD = re.compile(r"^\*\*[^*]+:\*\*\s*")          # a paragraph's bold label, as "**Working rule:**"
BOLD_LEAD = re.compile(r"^\*\*([^*]+)\*\*\s*")      # a list item's bold lead, as "**Cost grows with the square.**"
SENTENCE_END = re.compile(r"(?<=[.?!])[\"”’)]*\s+(?=[\"“‘(\[`*]?[A-Z0-9])")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")
NOTE = " (a warning: read it again)"


def blocks(body: str, offset: int) -> list[tuple[str, int, str]]:
    """Every block of a chapter's body, its opening included, as (kind, first line, text). A block's kind is
    "heading", "paragraph", "list", "table", "quote" or "embed"; fenced code is left out."""
    out: list[tuple[str, int, str]] = []
    fenced, open_block = False, False
    for n, line in enumerate(body.split("\n"), offset + 1):
        stripped = line.strip()
        if FENCE.match(stripped):
            fenced, open_block = not fenced, False
            continue
        if fenced:
            continue
        if not stripped:
            open_block = False
        elif stripped.startswith("#"):
            out.append(("heading", n, stripped))
            open_block = False
        elif open_block:
            kind, start, text = out[-1]
            out[-1] = (kind, start, text + "\n" + line)
        else:
            kind = ("embed" if EMBED_LINE.match(line) else "list" if LIST_ITEM.match(line)
                    else "table" if stripped.startswith("|") else "quote" if stripped.startswith(">") else "paragraph")
            out.append((kind, n, line))
            open_block = True
    return out


def units(block: tuple[str, int, str]) -> list[tuple[int, str]]:
    """The prose a block holds, as (first line, text): a paragraph whole, a list item by item."""
    kind, start, text = block
    if kind == "paragraph":
        return [(start, " ".join(line.strip() for line in text.split("\n")))]
    if kind != "list":
        return []
    items: list[tuple[int, str]] = []
    for i, line in enumerate(text.split("\n")):
        if LIST_ITEM.match(line):
            items.append((start + i, LIST_ITEM.sub("", line, count=1).strip()))
        elif items:
            items[-1] = (items[-1][0], items[-1][1] + " " + line.strip())
    return items


def plain(text: str) -> str:
    """A unit's text as its words read: a bold label left off, each binding a placeholder, each link its text."""
    text = BOLD_LEAD.sub("", LEAD.sub("", text.strip()))
    text = LINK.sub(lambda m: m.group(1), BINDING.sub("N", text))
    return re.sub(r"\s+", " ", text).strip()


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENTENCE_END.split(text) if s.strip()]


def _words(text: str) -> int:
    return len(WORD.findall(text))


def _short(text: str, n: int = 90) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def problems(book: Book, cfg: dict) -> list[str]:
    """W-61's bound yes or no, W-63's stock openers and repeats, W-68's docstring: each fails the check."""
    rules = cfg.get("narrative")
    if not rules:
        return []
    found: list[str] = []
    yes_no = set(rules["yes_no"])
    openers = [re.compile(o) for o in rules["stock_openers"]]
    phrases = [re.compile(p, re.IGNORECASE) for p in rules["stock_phrases"]]
    uses = int(rules["stock_uses"])
    seen: dict[str, list[tuple[str, int]]] = defaultdict(list)          # a long sentence, where each copy is
    openings: dict[str, dict[str, int]] = defaultdict(dict)             # a sentence's opening words, by chapter
    allowed = tuple(rules.get("repeated_openings_allowed", []))

    for c in book.chapters:
        counts: dict[str, list[tuple[int, str]]] = defaultdict(list)     # each stock opener or phrase: where, as written
        for block in blocks(c.body, c.body_offset):
            kind, start, text = block
            if kind in ("paragraph", "list", "table", "quote"):
                for m in BINDING.finditer(text):                         # W-61: a yes or no is a fact, not a value
                    if m.group(1) != "out":
                        continue
                    value, _ = book.binding_value("out", m.group(2))
                    if value in yes_no:
                        n = start + text[: m.start()].count("\n")
                        found.append(f"{c.file}:{n}: W-61: {{{{out:{m.group(2).strip()}}}}} puts \"{value}\" in the "
                                     "prose; assert it in the example and state it as a fact, or print a word the "
                                     "sentence can use")
            for n, unit in units(block):
                words = plain(unit)
                for s in sentences(words):
                    for rx in openers:                                   # W-63: an opener that marks the step
                        if m := rx.match(s):
                            counts[rx.pattern].append((n, m.group(0).strip()))
                    own = QUOTED.sub("Q", s)                             # a source quoted twice is the source's words
                    if len({w.lower() for w in WORD.findall(own)}) < 4:
                        continue                                         # filler, such as a test's "word word word"
                    if _words(own) >= int(rules["repeated_sentence_words"]):
                        seen[own.rstrip(".?!:;")].append((c.file, n))
                    first = WORD.findall(own)[: int(rules["repeated_opening_words"])]
                    if len(first) == int(rules["repeated_opening_words"]) and not s.startswith(allowed):
                        openings[" ".join(first)].setdefault(c.file, n)
                for rx in phrases:
                    counts[rx.pattern] += [(n, m.group(0)) for m in rx.finditer(words)]
        for pattern, used in counts.items():
            if len(used) > uses:
                shown = " / ".join(dict.fromkeys(text for _, text in used))
                found.append(f"{c.file}:{used[uses][0]}: W-63: \"{shown}\" {len(used)} times in this chapter (lines "
                             f"{', '.join(str(n) for n, _ in used)}), {uses} at most; lead into each example with what "
                             "the reader will see and why, in words of its own")

    for sentence, places in seen.items():                                # W-63: the same sentence twice in the book
        for file, n in places[1:]:
            first_file, first_n = places[0]
            found.append(f"{file}:{n}: W-63: this sentence is also at {first_file}:{first_n}: \"{_short(sentence)}\"; "
                         "say it once, or in this place's own words")
    need = int(rules["repeated_opening_chapters"])
    for opening, chapters in openings.items():                           # W-63, W-64: a template across chapters
        if len(chapters) >= need:
            where = ", ".join(f"{f}:{n}" for f, n in sorted(chapters.items()))
            first_file = min(chapters)
            found.append(f"{first_file}:{chapters[first_file]}: W-64: {len(chapters)} chapters open a sentence with "
                         f"\"{opening}\" ({where}); write each in that chapter's own words")

    for eid, ex in sorted(book.examples.items()):                       # W-68: every example says what it's for
        tree = _parse(ex.code)
        if tree is not None and ast.get_docstring(tree) is None:
            found.append(f"{ex.file}: W-68: open the example with a docstring of one or two sentences: what it shows, "
                         "and which printed line the prose's point rests on")
    return found


def warnings(book: Book, cfg: dict) -> list[str]:
    """W-61's ledger, W-62's quotations and links, W-68's offsets: what to read again. None fails the check."""
    rules = cfg.get("narrative")
    if not rules:
        return []
    found: list[str] = []
    most_bound, most_quotes = int(rules["paragraph_bindings"]), int(rules["quotes_per_paragraph"])
    quote_words, most_links = int(rules["quote_words"]), int(rules["links_per_sentence"])
    for c in book.chapters:
        for block in blocks(c.body, c.body_offset):
            kind, start, text = block
            if kind == "paragraph":                                      # W-61: a ledger instead of a point
                bound = sum(1 for m in BINDING.finditer(text) if m.group(1) == "out")
                if bound > most_bound:
                    found.append(f"{c.file}:{start}: W-61: {bound} bound numbers in one paragraph; lead with the "
                                 "sentence to keep and the numbers that show it, and put the rest in a table or "
                                 "leave them to the output" + NOTE)
            for n, unit in units(block):
                own = CODE_SPAN.sub(" ", BINDING.sub("N", unit))
                quotes = [q for q in QUOTED.findall(LINK.sub(lambda m: m.group(1), own))
                          if _words(q[0] or q[1]) >= quote_words]
                if len(quotes) > most_quotes:                            # W-62: a brief instead of an account
                    found.append(f"{c.file}:{n}: W-62: {len(quotes)} quotations in one paragraph; say what the source "
                                 "says in the book's words, and quote only where the words are the point" + NOTE)
                for s in sentences(own):
                    links = len(LINK.findall(s))
                    if links > most_links:
                        found.append(f"{c.file}:{n}: W-62: {links} links in one sentence (\"{_short(plain(s), 60)}\"); "
                                     "one on each claim, and the rest where the reader needs them" + NOTE)
    for eid, ex in sorted(book.examples.items()):                       # W-68: an offset with no word on why
        for n, snippet in offsets(ex.code):
            found.append(f"{ex.file}:{n}: W-68: an index with an offset, {snippet}; say why in a comment on its line, "
                         "in the prose's words" + NOTE)
    return found


def _parse(code: str) -> ast.Module | None:
    try:
        return ast.parse(code)
    except SyntaxError:
        return None


def _comment_lines(code: str) -> set[int]:
    try:
        return {tok.start[0] for tok in tokenize.generate_tokens(io.StringIO(code).readline) if tok.type == tokenize.COMMENT}
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return set()


def code_lines(code: str) -> int:
    """W-18's count, as W-68 sets it: non-blank lines, leaving out the module's docstring and lines that hold only a
    comment, so explaining an example never pushes it over the limit."""
    skip: set[int] = set()
    tree = _parse(code)
    if tree is not None and ast.get_docstring(tree) is not None:
        first = tree.body[0]
        skip = set(range(first.lineno, (first.end_lineno or first.lineno) + 1))
    return sum(1 for n, line in enumerate(code.split("\n"), 1)
               if line.strip() and not line.strip().startswith("#") and n not in skip)


def _has_offset(node: ast.AST) -> bool:
    """A subscript's index adds or takes away a literal number: ids[sep + 1:], context[3 - k:]."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.BinOp) and isinstance(sub.op, (ast.Add, ast.Sub)):
            for side in (sub.left, sub.right):
                if isinstance(side, ast.Constant) and type(side.value) is int:
                    return True
    return False


def offsets(code: str) -> list[tuple[int, str]]:
    """Each line where an index has a literal offset and no comment on its statement or the line above it."""
    tree = _parse(code)
    if tree is None:
        return []
    comments, lines = _comment_lines(code), code.split("\n")
    found: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _has_offset(node.slice):
            near = range(node.lineno - 1, (node.end_lineno or node.lineno) + 1)
            if node.lineno not in found and not comments.intersection(near):
                found[node.lineno] = ast.get_source_segment(code, node) or lines[node.lineno - 1].strip()
    return sorted((n, _short(s, 50)) for n, s in found.items())
