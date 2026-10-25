"""The book format: chapters, sections, examples and their stable IDs.

A book repo holds:

    book.toml                  the manifest: how the book is cataloged
    chapters/NN-name.md        one chapter per file, in file-name order, with `chapter_id` in front matter
    examples/{example_id}.py   one runnable example per file; expected stdout in examples/{example_id}.out
    redirects.yml              retired ID -> successor ID

Inside a chapter, the first line after the front matter is the `# Title`. Every `##` and `###` heading is
a section and carries an explicit, frozen ID: `## Why position matters {#why-position-matters}`. An
example is embedded by a paragraph that is only a link to its file: `[Example: load-orders](../examples/load-orders.py)`.

Chapter, section and example IDs share one namespace per book, so a permanent link can't be ambiguous.
The same parser feeds the section-ID check, the release job and the sites, so they can never disagree.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

from .catalog import load_book as load_manifest

ID_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
MAX_ID_LENGTH = 64
HEADING_ID = re.compile(r"\s*\{#([^}]*)\}\s*$")
EMBED_HREF = re.compile(r"^(?:\.\./)?examples/([^/]+)\.py$")
# Bindings (writing standards W-25, W-26): values the build fills in, so prose never types them.
#   {{out:EXAMPLE_ID:LABEL}}  the value on the "LABEL: value" line of that example's recorded output
#   {{version:PACKAGE}}       the version examples/requirements.txt pins
BINDING = re.compile(r"\{\{\s*(out|version)\s*:\s*([^{}]+?)\s*\}\}")
PIN = re.compile(r"^\s*([A-Za-z0-9_.\-\[\]]+?)\s*==\s*([^\s;#]+)")
SECTION_LEVELS = (2, 3)


def valid_id(value: str) -> bool:
    return bool(ID_RE.match(value)) and len(value) <= MAX_ID_LENGTH


def new_markdown() -> MarkdownIt:
    # Raw HTML stays off: book text comes from open contributions, and HTML in it would reach the site.
    return MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])


def normalize_text(lines: list[str]) -> str:
    """The text a section hash covers: NFC, trailing spaces removed, blank-line runs collapsed, trimmed.
    Heading IDs are removed first, so the hash covers what readers see."""
    out: list[str] = []
    for line in lines:
        line = unicodedata.normalize("NFC", line).rstrip()
        if line == "" and (not out or out[-1] == ""):
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n" if out else ""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class Section:
    section_id: str
    chapter_id: str
    title: str
    level: int
    parent_id: str | None
    order: int                  # reading order across the whole book, from 1
    line: int                   # 1-based line of the heading in the chapter file
    sha256: str
    example_ids: list[str] = field(default_factory=list)


@dataclass
class Embed:
    example_id: str
    section_id: str | None      # None when embedded in the chapter's opening text
    start: int                  # 0-based body line range of the embedding paragraph
    end: int


@dataclass
class Chapter:
    chapter_id: str
    title: str
    file: str                   # path relative to the book root
    order: int
    body: str                   # the chapter without its front matter
    body_offset: int            # lines before the body (front matter), for reporting line numbers
    sha256: str                 # hash of the opening text: the title and everything before the first section
    sections: list[Section] = field(default_factory=list)
    embeds: list[Embed] = field(default_factory=list)


@dataclass
class Example:
    example_id: str
    file: str
    code: str
    sha256: str
    expected: str | None        # expected stdout, from examples/{id}.out
    chapter_id: str | None = None
    section_id: str | None = None


@dataclass
class Book:
    root: Path
    manifest: dict
    chapters: list[Chapter]
    examples: dict[str, Example]
    redirects: dict[str, str]
    problems: list[str]                                      # format and ID problems: the section-ID check
    output_problems: list[str] = field(default_factory=list)  # missing expected outputs: the examples check

    @property
    def slug(self) -> str:
        return self.manifest.get("slug", "")

    @property
    def title(self) -> str:
        return self.manifest.get("title", "")

    @property
    def sections(self) -> list[Section]:
        return [s for c in self.chapters for s in c.sections]

    def ids(self) -> dict[str, str]:
        """Every live ID and what it names: chapter, section or example."""
        out = {c.chapter_id: "chapter" for c in self.chapters}
        out.update({s.section_id: "section" for s in self.sections})
        out.update({e: "example" for e in self.examples})
        return out

    def chapter(self, chapter_id: str) -> Chapter:
        return next(c for c in self.chapters if c.chapter_id == chapter_id)

    def locate(self, any_id: str) -> tuple[str, str | None] | None:
        """(chapter_id, anchor) for a live ID; anchor is None for a chapter itself."""
        for c in self.chapters:
            if c.chapter_id == any_id:
                return c.chapter_id, None
            for s in c.sections:
                if s.section_id == any_id:
                    return c.chapter_id, s.section_id
        ex = self.examples.get(any_id)
        if ex and ex.chapter_id:
            return ex.chapter_id, ex.example_id
        return None

    @property
    def pins(self) -> dict[str, str]:
        """Exact versions from examples/requirements.txt, by lowercase package name."""
        req = self.root / "examples" / "requirements.txt"
        out: dict[str, str] = {}
        if req.exists():
            for line in req.read_text(encoding="utf-8").splitlines():
                m = PIN.match(line)
                if m:
                    out[m.group(1).split("[")[0].lower().replace("_", "-")] = m.group(2)
        py = self.root / "examples" / ".python-version"
        if py.exists() and py.read_text(encoding="utf-8").strip():
            out["python"] = py.read_text(encoding="utf-8").strip()
        return out

    def binding_value(self, kind: str, ref: str) -> tuple[str | None, str | None]:
        """(value, None) for a binding that resolves, or (None, why) for one that doesn't."""
        if kind == "version":
            name = ref.strip().lower().replace("_", "-")
            v = self.pins.get(name)
            return (v, None) if v else (None, f"{{{{version:{ref}}}}}: {ref} isn't pinned in examples/requirements.txt")
        eid, _, label = ref.partition(":")
        eid, label = eid.strip(), label.strip()
        ex = self.examples.get(eid)
        if not label:
            return None, f"{{{{out:{ref}}}}}: write {{{{out:EXAMPLE_ID:LABEL}}}}"
        if ex is None:
            return None, f"{{{{out:{ref}}}}}: there is no example {eid!r}"
        if ex.expected is None:
            return None, f"{{{{out:{ref}}}}}: example {eid!r} has no recorded output yet"
        hits = [line.split(":", 1)[1].strip() for line in ex.expected.splitlines()
                if ":" in line and line.split(":", 1)[0].strip() == label]
        if len(hits) != 1:
            return None, (f"{{{{out:{ref}}}}}: {eid}.out has {'no' if not hits else len(hits)} line(s) labelled "
                          f"{label!r}; print exactly one \"{label}: value\" line")
        return hits[0], None

    def bind(self, text: str) -> str:
        """The text with every binding filled in. Unresolved bindings stay visible; binding_problems reports them."""
        return BINDING.sub(lambda m: self.binding_value(m.group(1), m.group(2))[0] or m.group(0), text)

    def binding_problems(self) -> list[str]:
        problems = []
        for c in self.chapters:
            for n, line in enumerate(c.body.split("\n"), c.body_offset + 1):
                for m in BINDING.finditer(line):
                    _, why = self.binding_value(m.group(1), m.group(2))
                    if why:
                        problems.append(f"{c.file}:{n}: {why}")
        return problems

    def resolve(self, any_id: str, limit: int = 32) -> str | None:
        """Follow redirects.yml from a retired ID to the live ID that succeeds it."""
        seen = 0
        while any_id not in self.ids():
            if any_id not in self.redirects or seen >= limit:
                return None
            any_id = self.redirects[any_id]
            seen += 1
        return any_id


# ---------------------------------------------------------------- parsing


def split_front_matter(text: str) -> tuple[dict, str, int, str | None]:
    """(front matter, body, body line offset, problem)."""
    if not text.startswith("---\n"):
        return {}, text, 0, "missing front matter with chapter_id"
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, text, 0, "front matter is not closed with ---"
    raw = text[4:end]
    try:
        meta = yaml.safe_load(raw) or {}
    except yaml.YAMLError as e:
        return {}, text, 0, f"front matter does not parse: {e}"
    if not isinstance(meta, dict):
        return {}, text, 0, "front matter must be key: value pairs"
    return meta, text[end + 5:], raw.count("\n") + 3, None


def _heading_text(inline: Token) -> tuple[str, str | None]:
    """Heading text without its {#id}, and the ID (None when absent)."""
    m = HEADING_ID.search(inline.content)
    if not m:
        return inline.content.strip(), None
    return inline.content[:m.start()].strip(), m.group(1)


def _embed_id(tokens: list[Token], i: int) -> str | None:
    """The example ID when tokens[i] opens a paragraph that is only a link to examples/{id}.py."""
    if tokens[i].type != "paragraph_open" or i + 2 >= len(tokens):
        return None
    inline = tokens[i + 1]
    children = [c for c in (inline.children or []) if not (c.type == "text" and not c.content.strip())]
    if len(children) < 2 or children[0].type != "link_open" or children[-1].type != "link_close":
        return None
    if any(c.type in ("link_open", "link_close") for c in children[1:-1]):
        return None
    m = EMBED_HREF.match(str(children[0].attrGet("href") or ""))
    return m.group(1) if m else None


def parse_chapter(path: Path, rel: str, order: int, first_section_order: int, md: MarkdownIt) -> tuple[Chapter | None, list[str]]:
    problems: list[str] = []
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    meta, body, offset, fm_problem = split_front_matter(text)
    if fm_problem:
        return None, [f"{rel}: {fm_problem}"]
    unknown = sorted(set(meta) - {"chapter_id"})
    if unknown:
        problems.append(f"{rel}: unknown front matter keys: {', '.join(unknown)}")
    chapter_id = str(meta.get("chapter_id") or "")
    if not chapter_id:
        return None, problems + [f"{rel}: front matter needs chapter_id"]
    if not valid_id(chapter_id):
        problems.append(f"{rel}: chapter_id {chapter_id!r} must be lowercase words joined by hyphens, at most {MAX_ID_LENGTH} characters")

    lines = body.split("\n")
    tokens = md.parse(body)
    headings: list[tuple[int, int, str, str | None]] = []    # (level, body line, text, id)
    embeds: list[tuple[int, int, str]] = []                   # (start, end, example id)
    for i, tok in enumerate(tokens):
        if tok.type == "heading_open":
            level = int(tok.tag[1])
            text_, hid = _heading_text(tokens[i + 1])
            headings.append((level, tok.map[0], text_, hid))
        else:
            eid = _embed_id(tokens, i)
            if eid is not None:
                embeds.append((tok.map[0], tok.map[1], eid))

    where = lambda body_line: f"{rel}:{body_line + offset + 1}"   # noqa: E731
    h1 = [h for h in headings if h[0] == 1]
    title = ""
    if not h1:
        problems.append(f"{rel}: needs a # title")
    else:
        title = h1[0][2]
        if len(h1) > 1:
            problems.append(f"{where(h1[1][1])}: a chapter has one # title")
        if headings[0][0] != 1:
            problems.append(f"{where(headings[0][1])}: the # title comes before any section")
        if h1[0][3]:
            problems.append(f"{where(h1[0][1])}: the chapter's ID goes in front matter, not on its title")

    boundaries = [h for h in headings if h[0] in (1, *SECTION_LEVELS)]
    sections: list[Section] = []
    parent: str | None = None
    for level, line, text_, hid in headings:
        if level > max(SECTION_LEVELS) and hid:
            problems.append(f"{where(line)}: only ## and ### headings are sections and carry IDs")
        if level not in SECTION_LEVELS:
            continue
        if not hid:
            problems.append(f"{where(line)}: section {text_!r} needs an explicit ID, such as {{#{slugify(text_)}}}")
            continue
        if not valid_id(hid):
            problems.append(f"{where(line)}: section ID {hid!r} must be lowercase words joined by hyphens, at most {MAX_ID_LENGTH} characters")
            continue
        nxt = next((b[1] for b in boundaries if b[1] > line), len(lines))
        section_lines = lines[line:nxt]
        section_lines[0] = HEADING_ID.sub("", section_lines[0])
        if level == 2:
            parent = hid
        sections.append(Section(
            section_id=hid, chapter_id=chapter_id, title=text_, level=level,
            parent_id=parent if level == 3 else None, order=first_section_order + len(sections),
            line=line + offset + 1, sha256=sha256_text(normalize_text(section_lines)),
        ))

    first_section_line = next((h[1] for h in headings if h[0] in SECTION_LEVELS), len(lines))
    intro = lines[:first_section_line]
    chapter = Chapter(chapter_id=chapter_id, title=title, file=rel, order=order, body=body, body_offset=offset,
                      sha256=sha256_text(normalize_text(intro)), sections=sections)
    for start, end, eid in embeds:
        owner = None
        for s in sections:
            if s.line - offset - 1 <= start:
                owner = s
        chapter.embeds.append(Embed(eid, owner.section_id if owner else None, start, end))
        if owner:
            owner.example_ids.append(eid)
    return chapter, problems


def slugify(text: str) -> str:
    """A suggested ID for a new heading. Generated once when the section is created, then frozen."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    words = re.findall(r"[a-z0-9]+", plain)
    out = ""
    for w in words:
        trial = f"{out}-{w}" if out else w
        if len(trial) > MAX_ID_LENGTH:
            break
        out = trial
    return out or "section"


def load_redirects(root: Path) -> tuple[dict[str, str], list[str]]:
    path = root / "redirects.yml"
    if not path.exists():
        return {}, []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        return {}, [f"redirects.yml does not parse: {e}"]
    if data is None:
        return {}, []
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        return {}, ["redirects.yml must map each retired ID to its successor ID"]
    return dict(data), []


def load_book(root: Path) -> Book:
    """Parse a book checkout. Problems are collected, not raised, so a check can report all of them."""
    root = Path(root)
    problems: list[str] = []
    manifest: dict = {}
    try:
        manifest = load_manifest(root / "book.toml")
    except FileNotFoundError:
        problems.append("book.toml is missing")
    except Exception as e:
        problems.append(f"book.toml does not parse: {e}")

    md = new_markdown()
    chapters: list[Chapter] = []
    files = sorted((root / "chapters").glob("*.md")) if (root / "chapters").is_dir() else []
    if not files:
        problems.append("no chapters: add chapters/NN-name.md")
    next_order = 1
    for i, path in enumerate(files, 1):
        chapter, chapter_problems = parse_chapter(path, path.relative_to(root).as_posix(), i, next_order, md)
        problems += chapter_problems
        if chapter:
            chapters.append(chapter)
            next_order += len(chapter.sections)

    examples: dict[str, Example] = {}
    ex_dir = root / "examples"
    for path in sorted(ex_dir.glob("*.py")) if ex_dir.is_dir() else []:
        eid = path.stem
        rel = path.relative_to(root).as_posix()
        if not valid_id(eid):
            problems.append(f"{rel}: example file names are their IDs: lowercase words joined by hyphens")
            continue
        code = path.read_text(encoding="utf-8").replace("\r\n", "\n")
        out = path.with_suffix(".out")
        examples[eid] = Example(eid, rel, code, sha256_text(code),
                                out.read_text(encoding="utf-8").replace("\r\n", "\n") if out.exists() else None)

    seen: dict[str, str] = {}

    def claim(any_id: str, what: str) -> None:
        if any_id in seen:
            problems.append(f"ID {any_id!r} is used twice ({seen[any_id]} and {what}); IDs are unique within a book")
        else:
            seen[any_id] = what

    for c in chapters:
        claim(c.chapter_id, f"chapter in {c.file}")
        for s in c.sections:
            claim(s.section_id, f"section in {c.file}:{s.line}")
    for eid, ex in examples.items():
        claim(eid, f"example {ex.file}")

    for c in chapters:
        for e in c.embeds:
            ex = examples.get(e.example_id)
            if ex is None:
                problems.append(f"{c.file}:{e.start + c.body_offset + 1}: embeds examples/{e.example_id}.py, which doesn't exist")
            elif ex.chapter_id is not None:
                problems.append(f"{c.file}: example {e.example_id!r} is embedded more than once")
            else:
                ex.chapter_id, ex.section_id = c.chapter_id, e.section_id
    output_problems = []
    for eid, ex in examples.items():
        if ex.chapter_id is None:
            problems.append(f"{ex.file}: not embedded in any chapter")
        if ex.expected is None:
            output_problems.append(f"{ex.file}: no expected output; record it with re-check examples --record")

    redirects, redirect_problems = load_redirects(root)
    problems += redirect_problems
    book = Book(root, manifest, chapters, examples, redirects, problems, output_problems)
    live = book.ids()
    for old, new in redirects.items():
        if old in live:
            problems.append(f"ID {old!r} is retired in redirects.yml, so it can't be used again")
        elif book.resolve(old) is None:
            problems.append(f"redirects.yml: {old!r} -> {new!r} doesn't lead to a live ID")
    return book


# ---------------------------------------------------------------- rendering


def render_chapter(chapter: Chapter, example_html: Callable[[str], str],
                   heading_extra: Callable[[Section], str] = lambda s: "",
                   code_block: Callable[[str, str], str] | None = None,
                   bind: Callable[[str], str] | None = None,
                   link: Callable[[str], str | None] | None = None,
                   table_wrap: tuple[str, str] | None = None,
                   working_rule: tuple[str, ...] = (),
                   heading_after: Callable[[Section], str] = lambda s: "") -> str:
    """HTML for a chapter's body, without its # title. Section headings get their IDs; heading_extra's HTML goes
    inside a section's heading, and heading_after's right after it, so a heading can stay its title alone; embed
    paragraphs become whatever example_html returns; fenced code goes through code_block(code, language);
    bind (usually Book.bind) fills in output and version bindings first; link turns the ID in an
    internal link, [text](#any-id), into the href to use, so a link can reach another chapter; table_wrap is
    the HTML to open before each table and close after it. Inline code carries translate="no", so a browser's
    translation leaves it as it is. A paragraph that opens with one of the working_rule
    labels in bold, as "**Working rule:**", gets class "working-rule", and its label class "working-rule-label"
    with the colon kept for screen readers only."""
    md = new_markdown()
    if code_block is not None:
        md.options["highlight"] = lambda content, lang, attrs: code_block(content, lang)
    tokens = md.parse(bind(chapter.body) if bind else chapter.body)
    for tok in tokens:
        for child in tok.children or []:
            if child.type == "code_inline":
                child.attrSet("translate", "no")       # a browser's translation leaves code as it is
            href = child.attrGet("href") if link is not None and child.type == "link_open" else None
            if href and href.startswith("#") and len(href) > 1:
                target = link(href[1:])
                if target:
                    child.attrSet("href", target)
    by_line = {s.line - chapter.body_offset - 1: s for s in chapter.sections}
    out: list[Token] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.type == "heading_open" and tok.tag == "h1":
            i += 3
            continue
        if tok.type == "heading_open":
            inline = tokens[i + 1]
            text_, hid = _heading_text(inline)
            if hid:
                _strip_heading_id(inline)
            section = by_line.get(tok.map[0])
            if section:
                tok.attrSet("id", section.section_id)
                out += [tok, inline]
                extra = heading_extra(section)
                if extra:
                    raw = Token("html_inline", "", 0)
                    raw.content = extra
                    inline.children = (inline.children or []) + [raw]
                out.append(tokens[i + 2])
                after = heading_after(section)
                if after:
                    block = Token("html_block", "", 0)
                    block.content = after + "\n"
                    out.append(block)
                i += 3
                continue
        eid = _embed_id(tokens, i)
        if eid is not None:
            block = Token("html_block", "", 0)
            block.content = example_html(eid)
            out.append(block)
            i += 3
            continue
        if working_rule and tok.type == "paragraph_open":
            _mark_working_rule(tok, tokens[i + 1], working_rule)
        if table_wrap and tok.type in ("table_open", "table_close"):
            wrap = Token("html_block", "", 0)
            wrap.content = table_wrap[0] if tok.type == "table_open" else table_wrap[1]
            out += [wrap, tok] if tok.type == "table_open" else [tok, wrap]
            i += 1
            continue
        out.append(tok)
        i += 1
    return md.renderer.render(out, md.options, {})


def _mark_working_rule(paragraph: Token, inline: Token, labels: tuple[str, ...]) -> None:
    kids = inline.children or []
    lead = 1 if kids and kids[0].type == "text" and not kids[0].content else 0     # markdown-it opens with an empty text
    strong, label, close = (kids[lead:lead + 3] + [None] * 3)[:3]
    if (strong is not None and strong.type == "strong_open" and label.type == "text" and close is not None
            and close.type == "strong_close" and label.content.endswith(":") and label.content[:-1] in labels):
        paragraph.attrSet("class", "working-rule")
        strong.attrSet("class", "working-rule-label")
        label.content = label.content[:-1]
        colon = Token("html_inline", "", 0)
        colon.content = '<span class="visually-hidden">:</span>'
        kids.insert(lead + 2, colon)


def _strip_heading_id(inline: Token) -> None:
    inline.content = HEADING_ID.sub("", inline.content)
    for child in reversed(inline.children or []):
        if child.type == "text":
            child.content = HEADING_ID.sub("", child.content)
            break


def machine_markdown(chapter: Chapter, example_block: Callable[[str], str],
                     bind: Callable[[str], str] | None = None) -> str:
    """The chapter's Markdown for machines: IDs kept for citation, embeds replaced by the example itself,
    bindings filled in when bind is given."""
    lines = chapter.body.split("\n")
    for e in sorted(chapter.embeds, key=lambda e: e.start, reverse=True):
        lines[e.start:e.end] = example_block(e.example_id).rstrip("\n").split("\n")
    text = "\n".join(lines).strip("\n") + "\n"
    return bind(text) if bind else text
