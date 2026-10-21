"""`re-check style`: the mechanical half of the writing standards (standards/writing/README.md).

Each problem names the rule it breaks, as "W-24", so a writer or an agent can look it up. Limits and word
lists live in data/writing.toml. Rules a linter can't judge go to critic agents and reviewers instead.
Prose is checked with code spans, fenced code and example embeds removed; examples are checked as code.
"""
from __future__ import annotations

import json
import re
import tomllib
import unicodedata
from pathlib import Path

from . import data_path
from .bookfmt import BINDING, HEADING_ID, Book

WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")
FENCE = re.compile(r"^(```|~~~)")
CODE_SPAN = re.compile(r"`[^`]*`")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]*)\)")
EMBED_LINE = re.compile(r"^\s*\[Example:[^\]]*\]\([^)]*\)\s*$")
ID_LINK = re.compile(r"\]\(#([^)\s]+)\)")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")   # the line under a table's header
FILE_LINK = re.compile(r"\]\((?:\.\./chapters/|\./)?\d\d-[^)\s]*\.md(?:#[^)\s]*)?\)")
VERSION_NUMBER = r"v?\d+(?:\.\d+)+"
# Quoted text is the source's wording, not ours, so W-24 and W-35 skip it. "As soon as" means "when".
QUOTED = re.compile(r'"[^"]*"|“[^”]*”')
NOT_TIME = re.compile(r"\bas\s+soon\s+as\b", re.IGNORECASE)
LEAD = re.compile(r"^\*\*([^*]+):\*\*")       # a paragraph's bold label, as in "**Working rule:**"
SECTION_HEADING = re.compile(r"^#{2,3} ")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s")


def load_config(path: Path | None = None) -> dict:
    with open(path or data_path("writing.toml"), "rb") as f:
        return tomllib.load(f)


def _prose_lines(body: str, offset: int, raw: bool = False) -> list[tuple[int, str]]:
    """(line number in the file, text) for prose lines: no fenced code or embeds. Code spans, bindings and
    link targets are blanked unless raw is set."""
    out, fenced = [], False
    for n, line in enumerate(body.split("\n"), offset + 1):
        if FENCE.match(line.strip()):
            fenced = not fenced
            continue
        if fenced or EMBED_LINE.match(line):
            continue
        out.append((n, line if raw else LINK_TARGET.sub("]", CODE_SPAN.sub(" ", BINDING.sub(" ", line)))))
    return out


def _section_parts(body: str, offset: int) -> list[tuple[int, list[tuple[str, int, str]]]]:
    """Each ## or ### heading's own text, up to the next heading of either level, as (level, blocks). A block is
    (kind, first line, text), and its kind is "paragraph", "list", "table", "code", "embed", "figure" or "quote"."""
    parts: list[tuple[int, list[tuple[str, int, str]]]] = []
    blocks: list[tuple[str, int, str]] | None = None
    fenced, open_block = False, False
    for n, line in enumerate(body.split("\n"), offset + 1):
        stripped = line.strip()
        if FENCE.match(stripped):
            if not fenced and blocks is not None:
                blocks.append(("code", n, ""))
            fenced, open_block = not fenced, False
            continue
        if fenced:
            continue
        if SECTION_HEADING.match(line):
            blocks = []
            parts.append((len(line) - len(line.lstrip("#")), blocks))
            open_block = False
        elif blocks is None or line.startswith("# "):
            continue
        elif not stripped:
            open_block = False
        elif open_block:
            kind, start, text = blocks[-1]
            blocks[-1] = (kind, start, text + "\n" + line)
        else:
            kind = ("embed" if EMBED_LINE.match(line) else "figure" if IMAGE.match(stripped) else "list" if LIST_ITEM.match(line)
                    else "table" if stripped.startswith("|") else "quote" if stripped.startswith(">") else "paragraph")
            blocks.append((kind, n, line))
            open_block = True
    return parts


def _working_rules(file: str, body: str, offset: int, rule: dict) -> list[str]:
    """W-10, its mechanical half. A ## section, with its ### subsections, closes with a working rule labelled as
    config says, unless it ends in a list or table, as a chapter's summary does. A ### subsection, or the text
    before it, may close with a rule of its own; a rule anywhere else is out of place. Whether a rule is a good
    one is the critic's to judge."""
    label, retired = rule["label"], set(rule.get("retired", []))
    problems: list[str] = []

    def is_rule(block):
        lead = LEAD.match(block[2]) if block[0] == "paragraph" else None
        return lead is not None and (lead.group(1) == label or lead.group(1) in retired)

    sections: list[list[tuple[str, int, str]]] = []
    for level, blocks in _section_parts(body, offset):
        if level == 2 or not sections:
            sections.append([])
        sections[-1] += blocks
        rules = [b for b in blocks if is_rule(b)]
        for b in rules:
            lead = LEAD.match(b[2])
            if lead.group(1) != label:
                problems.append(f"{file}:{b[1]}: W-10: label the working rule \"**{label}:**\", not \"**{lead.group(1)}:**\"")
            elif b[2][lead.end():].lstrip()[:1].islower():
                problems.append(f"{file}:{b[1]}: W-10: start the working rule with a capital; the sites set its label "
                                "on a line of its own")
        closing = rules[-1] if rules and rules[-1] is blocks[-1] else None
        for b in (b for b in rules if b is not closing):
            problems.append(f"{file}:{b[1]}: W-10: a working rule closes its section; move what follows it above it, "
                            "or make it a rule of its own section")
    for blocks in sections:
        if blocks and blocks[-1][0] == "paragraph" and not is_rule(blocks[-1]):
            problems.append(f"{file}:{blocks[-1][1]}: W-10: close the section with its working rule, "
                            f"a paragraph that opens with \"**{label}:**\"")
    return problems


def _words(text: str) -> int:
    return len(WORD.findall(text))


def _phrase(term: str) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9\-])" + re.escape(term).replace(r"\ ", r"\s+") + r"(?![A-Za-z0-9\-])", re.IGNORECASE)


def _is_emoji(ch: str) -> bool:
    return unicodedata.category(ch) == "So" and ord(ch) > 0x2100


def check_style(book: Book, cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    problems: list[str] = []
    lengths, words = cfg["length"], cfg["words"]
    time_words = [(t, _phrase(t)) for t in words["time"]]
    banned = [(t, _phrase(t)) for t in words["banned"]]
    pins = book.pins
    names = {name: [name] + cfg["words"].get("aliases", {}).get(name, []) for name in pins}
    typed_version = [(name, re.compile(r"(?<![A-Za-z0-9\-])" + re.escape(alias) + r"(?:\s+version)?\s*(?:==\s*)?" + VERSION_NUMBER, re.IGNORECASE))
                     for name, aliases in names.items() for alias in aliases]
    proper = set(cfg["headings"]["proper_nouns"])

    status = book.manifest.get("status", "draft")
    lo, hi = lengths["book_chapters"]
    if status == "live" and not lo <= len(book.chapters) <= hi:
        problems.append(f"W-7: a book has {lo} to {hi} chapters; this one has {len(book.chapters)}")

    for c in book.chapters:
        prose = _prose_lines(c.body, c.body_offset)
        total = sum(_words(t) for _, t in prose)
        lo, hi = lengths["chapter_words"]
        if not lo <= total <= hi:
            problems.append(f"{c.file}: W-7: a chapter runs {lo:,} to {hi:,} words of prose; this one has {total:,}")

        # sections: each ## heading and everything under it until the next ## heading
        lo, hi = lengths["section_words"]
        current, count, start = None, 0, 0
        for n, text in prose + [(None, "## end")]:
            if text.startswith("## "):
                if current is not None and not lo <= count <= hi:
                    problems.append(f"{c.file}:{start}: W-7: a section runs {lo} to {hi} words; \"{current}\" has {count}")
                current, count, start = HEADING_ID.sub("", text[3:]).strip(), 0, n
            elif current is not None:
                count += _words(text)

        for n, text in prose:
            if text.lstrip().startswith("#"):
                heading = HEADING_ID.sub("", text.lstrip("# ").rstrip())
                tokens = heading.split()
                capped = [w for w in tokens[1:] if w[:1].isupper() and not w.isupper() and w.strip(",.:;()") not in proper
                          and not any(ch.isdigit() for ch in w) and not any(ch.isupper() for ch in w[1:])]
                if len(capped) >= 2:
                    problems.append(f"{c.file}:{n}: W-36: headings use sentence case (\"{heading}\"); "
                                    f"add proper nouns to data/writing.toml if these are names: {', '.join(capped)}")
                continue
            own = NOT_TIME.sub(" ", QUOTED.sub(" ", text))
            for term, rx in time_words:
                if rx.search(own):
                    problems.append(f"{c.file}:{n}: W-24: \"{term}\" dates the text; describe behaviour at the pinned version")
            for term, rx in banned:
                if rx.search(own):
                    problems.append(f"{c.file}:{n}: W-35: \"{term}\" is a banned word")
            if "!" in text.replace("![", "").replace("!=", ""):
                problems.append(f"{c.file}:{n}: W-35: no exclamation marks")
            if any(_is_emoji(ch) for ch in text):
                problems.append(f"{c.file}:{n}: W-35: no emoji")
            for name, rx in typed_version:
                if rx.search(text):
                    problems.append(f"{c.file}:{n}: W-25: a typed version of {name}; write {{{{version:{name}}}}}")

        for n, text in _prose_lines(c.body, c.body_offset, raw=True):
            plain = CODE_SPAN.sub(" ", text)
            for target in ID_LINK.findall(plain):
                if book.resolve(target) is None:
                    problems.append(f"{c.file}:{n}: W-40: links to #{target}, which isn't a chapter, section or example ID in this book")
            if FILE_LINK.search(plain):
                problems.append(f"{c.file}:{n}: W-40: link other chapters by ID, as [text](#chapter-or-section-id), not by file name")
            for alt, _ in IMAGE.findall(plain):
                if not alt.strip():
                    problems.append(f"{c.file}:{n}: W-39: every figure needs alt text that states its point")
            if TABLE_RULE.match(text):
                columns = len(text.strip().strip("|").split("|"))
                if columns > lengths["table_columns"]:
                    problems.append(f"{c.file}:{n - 1}: W-53: a table with {columns} columns; keep it to {lengths['table_columns']} "
                                    "so it fits a phone, by putting the things compared in columns or splitting it")

        problems += _working_rules(c.file, c.body, c.body_offset, cfg["working_rule"])

    problems += [f"W-26: {p}" for p in book.binding_problems()]

    limit = lengths["example_lines"]
    for eid, ex in book.examples.items():
        lines = [line for line in ex.code.split("\n") if line.strip()]
        if len(lines) > limit:
            problems.append(f"{ex.file}: W-18: {len(lines)} lines; keep an example to about 30 (limit {limit}) "
                            "and move setup into a shared module")

    problems += check_recordings(book.root, cfg)
    return problems


def check_recordings(root: Path, cfg: dict | None = None) -> list[str]:
    """W-48: every folder of recorded outputs carries a complete manifest whose script exists."""
    cfg = cfg or load_config()
    need = cfg["recordings"]["manifest"]
    problems = []
    base = root / "examples" / "data" / "recorded"
    for folder in sorted(p for p in base.iterdir() if p.is_dir()) if base.is_dir() else []:
        rel = folder.relative_to(root).as_posix()
        mf = folder / "manifest.json"
        if not mf.exists():
            problems.append(f"{rel}: W-48: recorded outputs need a manifest.json ({', '.join(need)})")
            continue
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"{rel}/manifest.json: W-48: doesn't parse: {e}")
            continue
        missing = [k for k in need if not manifest.get(k)]
        if missing:
            problems.append(f"{rel}/manifest.json: W-48: missing {', '.join(missing)}")
        script = manifest.get("script")
        if script and not (root / script).exists():
            problems.append(f"{rel}/manifest.json: W-48: its script {script} doesn't exist")
        for out in manifest.get("outputs", []):
            if not (folder / out).exists():
                problems.append(f"{rel}/manifest.json: W-48: lists {out}, which doesn't exist")
    return problems
