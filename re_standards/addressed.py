"""`re-check addressed`: book text that is written to an AI system rather than to readers.

Agents read every book: critics, fixers and readers' assistants. Text that tells them what to do, whether hidden
from people or written in plain view, is an attack on them, so a book never carries it. Three things are checked:
characters that hide text from a reviewer (in every text file of the book, code included); model-addressed phrases
in hidden places of a chapter (HTML comments, tags, link titles and image alt text); and those phrases in plain
prose. Fenced code and inline code are exempt from the phrases, since books about language models show prompts as
code, and inline code is how prose quotes an attack. Limits and word lists live in data/addressed.toml.
"""
from __future__ import annotations

import fnmatch
import re
import subprocess
import tomllib
from pathlib import Path

from . import data_path
from .bookfmt import Book

FENCE = re.compile(r"^(```+|~~~+)")
CODE_SPAN = re.compile(r"(?<!`)(`+)(?!`).+?(?<!`)\1(?!`)", re.DOTALL)
COMMENT_OPEN, COMMENT_CLOSE = "<!--", "-->"
TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9-]*(?:\s[^<>]*)?/?>")
IMAGE_ALT = re.compile(r"!\[([^\]]*)\]")
LINK_TITLE = re.compile(r"""\]\(\s*<?[^)\s"'<>]*>?\s+(?:"([^"]*)"|'([^']*)')\s*\)""")
REF_TITLE = re.compile(r"""^ {0,3}\[[^\]]+\]:\s*\S+\s+(?:"([^"]*)"|'([^']*)'|\(([^)]*)\))""", re.MULTILINE)
LINK_TARGET = re.compile(r"(?<=\])\([^)]*\)")
EXCERPT = 70
IN_PROSE = "to quote an attack, put it in inline code, where a reviewer sees it is a quotation"
IN_HIDING = "this is hidden from readers; say it in visible text, in inline code if it quotes an attack"


def load_config(path: Path | None = None) -> dict:
    with open(path or data_path("addressed.toml"), "rb") as f:
        return tomllib.load(f)


class Rules:
    def __init__(self, cfg: dict):
        self.ranges = [(int(lo, 16), int(hi, 16)) for lo, hi in cfg["hidden"]["ranges"]]
        self.first_ok = int(cfg["hidden"]["first_character_ok"], 16)
        data = cfg["hidden"]["datasets"]
        self.dataset_paths = data["paths"]
        self.dataset_allowed = [(int(lo, 16), int(hi, 16)) for lo, hi in data["allow"]]
        self.skip_dirs = set(cfg["files"]["skip_dirs"])
        self.skip_suffixes = set(cfg["files"]["skip_suffixes"])
        self.phrases = [(g["id"], [re.compile(p, re.MULTILINE | (0 if g.get("case_sensitive") else re.IGNORECASE))
                                   for p in g["patterns"]])
                        for g in cfg["phrases"]]

    def hidden(self, ch: str, allowed: list[tuple[int, int]] = ()) -> bool:
        return (any(lo <= ord(ch) <= hi for lo, hi in self.ranges)
                and not any(lo <= ord(ch) <= hi for lo, hi in allowed))

    def hits(self, text: str) -> list[tuple[int, str, str]]:
        """(offset, rule id, matched text) for each model-addressed phrase in text, in order."""
        return sorted((m.start(), rid, m.group()) for rid, rxs in self.phrases for rx in rxs for m in rx.finditer(text))


def _excerpt(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= EXCERPT else text[:EXCERPT - 1] + "…"


def _blank(text: str, spans: list[tuple[int, int]]) -> str:
    """Spaces in place of the spans, newlines kept, so offsets and line numbers stay as they were."""
    chars = list(text)
    for start, end in spans:
        chars[start:end] = [c if c == "\n" else " " for c in chars[start:end]]
    return "".join(chars)


def book_files(root: Path) -> list[Path]:
    """The book's own files: what its git repository tracks, and new files it doesn't ignore, so a checkout of
    something else inside it (CI puts the standards in .standards/) isn't read as the book. Outside a repository,
    every file under the root."""
    r = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return sorted(root.rglob("*"))
    return sorted({root / rel for rel in r.stdout.split("\0") if rel})


def scan_hidden_characters(root: Path, rules: Rules) -> list[str]:
    problems: list[str] = []
    for path in book_files(root):
        rel = path.relative_to(root)
        if (not path.is_file() or path.is_symlink() or rules.skip_dirs & set(rel.parts[:-1])
                or path.suffix.lower() in rules.skip_suffixes):
            continue
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            continue
        allowed = rules.dataset_allowed if any(fnmatch.fnmatch(rel.as_posix(), g) for g in rules.dataset_paths) else []
        for n, line in enumerate(text.split("\n"), 1):
            found = [(i, ch) for i, ch in enumerate(line)
                     if rules.hidden(ch, allowed) and not (n == 1 and i == 0 and ord(ch) == rules.first_ok)]
            if not found:
                continue
            names = ", ".join(sorted({f"U+{ord(ch):04X}" for _, ch in found}))
            spelled = "".join(chr(ord(ch) - 0xE0000) for _, ch in found if 0xE0020 <= ord(ch) <= 0xE007E)
            decoded = f"; the tag characters spell \"{_excerpt(spelled)}\"" if spelled else ""
            shown = "".join("·" if rules.hidden(ch, allowed) else ch for ch in line)
            problems.append(f"{rel.as_posix()}: line {n}: hidden-character: {len(found)} invisible character(s) ({names}) in "
                            f"\"{_excerpt(shown)}\"{decoded}; they hide text from a reviewer, so take them out")
    return problems


def _paragraphs(body: str, offset: int) -> tuple[list[tuple[int, str]], list[tuple[int, str]]]:
    """A chapter's paragraphs and HTML comments, each as (first line number, text). Fenced code is left out, and
    so are comments from the paragraphs; the text of both keeps its newlines."""
    paras: list[tuple[int, str]] = []
    comments: list[tuple[int, str]] = []
    lines: list[str] = []
    start = comment_start = 0
    fence = ""
    comment: list[str] | None = None

    def flush():
        nonlocal lines
        if lines:
            paras.append((start, "\n".join(lines)))
        lines = []

    for n, line in enumerate(body.split("\n"), offset + 1):
        if comment is None:
            fenced = FENCE.match(line.strip())
            if fence:
                if fenced and fenced.group(1)[0] == fence[0] and len(fenced.group(1)) >= len(fence):
                    fence = ""
                continue
            if fenced:
                flush()
                fence = fenced.group(1)
                continue
        visible = ""
        while True:
            if comment is not None:
                end = line.find(COMMENT_CLOSE)
                if end < 0:
                    comment.append(line)
                    line = ""
                    break
                comment.append(line[:end])
                comments.append((comment_start, "\n".join(comment)))
                comment, line = None, line[end + len(COMMENT_CLOSE):]
                continue
            at = _blank(line, [m.span() for m in CODE_SPAN.finditer(line)]).find(COMMENT_OPEN)
            if at < 0:
                break
            visible += line[:at]
            comment, comment_start, line = [], n, line[at + len(COMMENT_OPEN):]
        visible += line
        if not visible.strip():
            if comment is None:
                flush()
            continue
        if not lines:
            start = n
        lines.append(visible)
    flush()
    if comment is not None:
        comments.append((comment_start, "\n".join(comment)))
    return paras, comments


def check_chapter(file: str, body: str, offset: int, rules: Rules) -> list[str]:
    problems: list[str] = []
    paras, comments = _paragraphs(body, offset)

    def add(first: int, text: str, at: int, rid: str, where: str, hit: str, hint: str):
        problems.append(f"{file}: line {first + text.count(chr(10), 0, at)}: {rid}: {where}\"{_excerpt(hit)}\"; {hint}")

    for first, text in comments:
        for at, rid, hit in rules.hits(text):
            add(first, text, at, rid, "in an HTML comment: ", hit, IN_HIDING)
    for first, text in paras:
        text = _blank(text, [m.span() for m in CODE_SPAN.finditer(text)])
        pieces = [(m.start(), m.group(), "in a tag: ") for m in TAG.finditer(text)]
        pieces += [(m.start(1), m.group(1), "in image alt text: ") for m in IMAGE_ALT.finditer(text)]
        for rx in (LINK_TITLE, REF_TITLE):
            pieces += [(m.start(g), m.group(g), "in a link title: ") for m in rx.finditer(text)
                       for g in range(1, rx.groups + 1) if m.group(g) is not None]
        for at, piece, where in sorted(pieces):
            for off, rid, hit in rules.hits(piece):
                add(first, text, at + off, rid, where, hit, IN_HIDING)
        spans = [m.span() for rx in (TAG, LINK_TARGET) for m in rx.finditer(text)] + [m.span(1) for m in IMAGE_ALT.finditer(text)]
        shown = _blank(text, spans)
        for at, rid, hit in rules.hits(shown):
            add(first, text, at, rid, "", hit, IN_PROSE)
    return problems


def check_addressed(book: Book, cfg: dict | None = None) -> list[str]:
    rules = Rules(cfg or load_config())
    problems = scan_hidden_characters(book.root, rules)
    for c in book.chapters:
        problems += check_chapter(c.file, c.body, c.body_offset, rules)
    manifest = book.root / "book.toml"
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8", errors="replace")
        for at, rid, hit in rules.hits(text):
            problems.append(f"book.toml: line {text.count(chr(10), 0, at) + 1}: {rid}: \"{_excerpt(hit)}\"; "
                            "a title or description is read by models and people alike")
    return problems
