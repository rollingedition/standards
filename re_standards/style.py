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
