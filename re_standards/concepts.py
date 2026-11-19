"""Concepts: the terms a book defines, each in the book's own sentence, connected as a graph (writing standards W-77 to
W-80, `re-check concepts`).

A book may hold a concepts.toml beside its book.toml: an index of what it defines. A concept is one term with one
meaning in one context, and its definition is the book's own sentence, quoted exactly, never a second copy that can
drift. The checks hold the index to the text.

    context = "search-and-recommendation"      # the context of every concept that names none of its own

    [[contexts]]                               # a narrower context of the book's own, only where two meanings meet
    id = "graded-relevance"
    broader = "search-evaluation"              # a taxonomy area or skill, or another context declared here
    label = "Graded relevance"
    description = "Where a judgment is a grade, and a gain is what the grade is worth."

    [[concepts]]
    id = "recall-at-k"                         # frozen once released: it's part of the concept's address
    term = "Recall at k"
    aliases = ["recall@k"]
    definition = "Recall at k, recall@k, is the share of all relevant products that appear in the top k."
    section = "precision-and-recall"           # a section's ID, or a chapter's for its opening
    example = "precision-and-recall"           # an example that shows it, run on every release
    applies_to = ["scikit-learn"]              # packages or tools the definition depends on: their pins give its version
    wikidata = "Q..."

    [concepts.relations]                       # this concept's, by type: data/concepts.toml's [relations]
    measured-from = ["relevance-judgment"]
    contrasts-with = ["precision-at-k"]
    implemented-by = [{ to = "scikit-learn", versions = ">=1.5" }]

Contexts are namespaces. Ours are the taxonomy's areas and skills (data/taxonomy.json), and the narrower contexts books
declare; a concept's permanent address is `{base}/{context}/{id}`, and its version in one edition `…/{id}@{edition}`
(data/concepts.toml, [addresses]). An organization's file has the same format with a [namespace] table naming its own
`id` and `base`: its contexts are the ones it declares, its concepts never live in ours, and it points at ours by their
addresses. `load` reads such a file on its own, with no book; a book's is `Book.concepts`.

A relation is written by its type, from the fixed set in data/concepts.toml ([relations]), each with its plain meaning
and its SKOS mapping. Its target is a concept of this file by ID (or `context/id`, where an ID is in two contexts), a
concept of another context by `context/id` or its address, `wikidata:Q…` for same-as and close-to, or a package's name
for implemented-by, as a string or as `{ to = "…", versions = "…" }`.

The checks, each a function a later check composes with:
1. quote_problems (W-77): every definition and formula is in its section's text, word for word, after the
   normalization the book's renderer implies (emphasis, links, line breaks and entities are what a reader never sees);
   the section exists; what applies_to names is pinned.
2. once_problems (W-78): a concept is defined once; IDs, terms and aliases are unique within a context.
3. link_problems (W-79): a chapter that uses a term before its defining section links its first use to that section.
4. Across books, later: two books' concepts at one address agree, or sit in different contexts. It takes several
   books' `served` records, grouped by `address`, and each declared context's `broader`, which must agree too.
5. On an update's failing example, later: the concepts whose `example` failed, or whose `applies_to` or
   implemented-by names a package whose pin moved, go into the update's pull request.
6. relation_problems (W-80): every relation's type is in the set and names a concept that exists here, or a
   well-formed address in another context, and no acyclic type goes round in a circle.

`served` gives each concept in the shape it's served in, with its generated fields.
"""
from __future__ import annotations

import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterator, Mapping

from markdown_it.token import Token
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from . import catalog, data_path
from . import stack as stack_pins
from .bookfmt import BINDING, Book, Chapter, new_markdown, valid_id

FILE = "concepts.toml"
FILE_KEYS = {"context", "namespace", "contexts", "concepts"}
NAMESPACE_KEYS = {"id", "base"}
CONTEXT_KEYS = {"id", "broader", "label", "description"}
CONCEPT_KEYS = {"id", "term", "aliases", "definition", "formula", "section", "context", "relations", "applies_to",
                "example", "wikidata"}
TARGET_KEYS = {"to", "versions"}
PACKAGE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
WIKIDATA = re.compile(r"^wikidata:(Q[1-9][0-9]*)$")
HEADER = re.compile(r"^\s*\[\[\s*(contexts|concepts)\s*\]\]")
SPACE = re.compile(r"\s+")
BLANK_LINE = re.compile(r"\n\s*\n")


@lru_cache(maxsize=4)
def _settings_cached(path: str, mtime: float) -> dict:
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))


def settings() -> dict:
    """data/concepts.toml: the addresses, the relation types and how a term's use is found."""
    path = data_path("concepts.toml")
    return _settings_cached(str(path), path.stat().st_mtime)


def relation_types() -> dict[str, dict]:
    return settings()["relations"]


def package_key(name: str) -> str:
    """A package's name as Book.pins keys it."""
    return name.strip().lower().replace("_", "-")


# ---------------------------------------------------------------- the format


@dataclass(frozen=True)
class Relation:
    type: str
    to: str                     # as written: a concept's ID, context/ID or address, wikidata:Q…, or a package's name
    versions: str = ""          # implemented-by's version range, as ">=0.3"


@dataclass
class Context:
    """A narrower context a file declares, under one of the taxonomy's areas or skills or another it declares; in an
    organization's file, under another of its own, or under none."""
    id: str
    broader: str
    label: str = ""
    description: str = ""
    line: int = 0


@dataclass
class Concept:
    id: str
    term: str
    definition: str
    section: str
    context: str
    aliases: list[str] = field(default_factory=list)
    formula: str = ""
    relations: list[Relation] = field(default_factory=list)
    applies_to: list[str] = field(default_factory=list)
    example: str = ""
    wikidata: str = ""
    line: int = 0               # its [[concepts]] header's line in the file, for messages

    @property
    def key(self) -> tuple[str, str]:
        return self.context, self.id

    @property
    def names(self) -> list[str]:
        return [self.term, *self.aliases]


@dataclass
class ConceptSet:
    """A concepts.toml as read: empty, with `present` false, for a book that has none."""
    file: str = FILE
    present: bool = False
    namespace: str = ""
    base: str = ""
    context: str = ""                                          # the file's own default context, if it gives one
    contexts: dict[str, Context] = field(default_factory=dict)
    concepts: list[Concept] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)          # the format's problems: what stopped a part being read

    def __iter__(self) -> Iterator[Concept]:
        return iter(self.concepts)

    def __len__(self) -> int:
        return len(self.concepts)

    @property
    def ours(self) -> bool:
        """Whether this is our namespace, as every book's is, rather than an organization's."""
        return self.namespace == settings()["addresses"]["namespace"]

    def where(self, line: int) -> str:
        return f"{self.file}:{line}" if line else self.file

    def get(self, context: str, concept_id: str) -> Concept | None:
        return next((c for c in self.concepts if c.key == (context, concept_id)), None)

    def address(self, context: str, concept_id: str, edition: str | None = None) -> str:
        """A concept's permanent address, or its version in one edition, in this file's namespace."""
        cfg = settings()["addresses"]
        template = cfg["edition"] if edition else cfg["concept"]
        return template.format(base=self.base, context=context, id=concept_id, edition=edition or "")

    def context_address(self, context: str) -> str:
        return settings()["addresses"]["context"].format(base=self.base, context=context)


def _strings(value, what: str, where: str, problems: list[str]) -> list[str]:
    """A string or a list of strings, as a list; a problem for anything else."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        problems.append(f"{where}: {what} is a name or a list of names")
        return []
    return [x.strip() for x in value]


def _text(raw: dict, key: str, where: str, problems: list[str], required: bool = False) -> str:
    value = raw.get(key)
    if value is None:
        if required:
            problems.append(f"{where}: needs {key}")
        return ""
    if not isinstance(value, str) or (required and not value.strip()):
        problems.append(f"{where}: {key} is text" + (", and can't be empty" if required else ""))
        return ""
    return value.strip()


def _relations(raw, where: str, problems: list[str]) -> list[Relation]:
    if raw is None:
        return []
    if not isinstance(raw, dict):
        problems.append(f"{where}: relations is a table of relation types, such as {{ broader = [\"ranking-metric\"] }}")
        return []
    out: list[Relation] = []
    for kind, targets in raw.items():
        for target in targets if isinstance(targets, list) else [targets]:
            if isinstance(target, str) and target.strip():
                out.append(Relation(kind, target.strip()))
            elif isinstance(target, dict) and set(target) <= TARGET_KEYS and isinstance(target.get("to"), str) \
                    and target["to"].strip() and isinstance(target.get("versions", ""), str):
                out.append(Relation(kind, target["to"].strip(), target.get("versions", "").strip()))
            else:
                problems.append(f"{where}: {kind}'s targets are names, or tables such as "
                                "{ to = \"bm25s\", versions = \">=0.3\" }")
    return out


def parse(text: str, file: str = FILE) -> ConceptSet:
    """A concepts.toml from its text. Problems are collected, not raised, so a check can report all of them."""
    cs = ConceptSet(file=file, present=True)
    addresses = settings()["addresses"]
    cs.namespace, cs.base = addresses["namespace"], addresses["base"]
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        cs.problems.append(f"{file} does not parse: {e}")
        return cs
    lines: dict[str, list[int]] = {"contexts": [], "concepts": []}
    for n, line in enumerate(text.splitlines(), 1):
        if m := HEADER.match(line):
            lines[m.group(1)].append(n)
    problems = cs.problems
    if unknown := sorted(set(data) - FILE_KEYS):
        problems.append(f"{file}: unknown keys: {', '.join(unknown)}; it holds context, [namespace], [[contexts]] and "
                        "[[concepts]]")

    ns = data.get("namespace")
    if ns is not None:
        if not isinstance(ns, dict) or set(ns) - NAMESPACE_KEYS:
            problems.append(f"{file}: [namespace] holds an organization's id and base, and nothing else")
        else:
            nid, base = str(ns.get("id") or addresses["namespace"]), str(ns.get("base") or "").rstrip("/")
            if nid == addresses["namespace"]:
                if base and base != addresses["base"]:
                    problems.append(f"{file}: our namespace's base is {addresses['base']}")
            elif not valid_id(nid):
                problems.append(f"{file}: a namespace's id is lowercase words joined by hyphens, not {nid!r}")
            elif not base.startswith("https://"):
                problems.append(f"{file}: an organization's namespace names its own base, an https:// address under "
                                "which its concepts' addresses go")
            else:
                cs.namespace, cs.base = nid, base

    default = data.get("context", "")
    if not isinstance(default, str):
        problems.append(f"{file}: context is the ID of the context every concept that names none is in")
        default = ""
    cs.context = default.strip()

    raw_contexts = data.get("contexts", [])
    if not isinstance(raw_contexts, list):
        problems.append(f"{file}: declare each narrower context as a [[contexts]] table")
        raw_contexts = []
    for i, raw in enumerate(raw_contexts):
        line = lines["contexts"][i] if i < len(lines["contexts"]) else 0
        where = cs.where(line)
        if not isinstance(raw, dict):
            problems.append(f"{where}: a context is a table, with id and broader")
            continue
        if extra := sorted(set(raw) - CONTEXT_KEYS):
            problems.append(f"{where}: unknown keys in a context: {', '.join(extra)}")
        # ours sit under the taxonomy; an organization's top context has nothing above it in its own namespace
        cid, broader = _text(raw, "id", where, problems, True), _text(raw, "broader", where, problems, cs.ours)
        if not cid:
            continue
        if not valid_id(cid):
            problems.append(f"{where}: a context's ID is lowercase words joined by hyphens, at most 64 characters, "
                            f"not {cid!r}")
        elif cid in cs.contexts:
            problems.append(f"{where}: W-78: the context {cid} is declared twice")
        else:
            cs.contexts[cid] = Context(cid, broader, _text(raw, "label", where, problems),
                                       _text(raw, "description", where, problems), line)

    raw_concepts = data.get("concepts", [])
    if not isinstance(raw_concepts, list):
        problems.append(f"{file}: write each concept as a [[concepts]] table")
        raw_concepts = []
    for i, raw in enumerate(raw_concepts):
        line = lines["concepts"][i] if i < len(lines["concepts"]) else 0
        where = cs.where(line)
        if not isinstance(raw, dict):
            problems.append(f"{where}: a concept is a table, with id, term, definition and section")
            continue
        cid = _text(raw, "id", where, problems, True)
        if cid:
            where = f"{where}: {cid}"
        if extra := sorted(set(raw) - CONCEPT_KEYS):
            problems.append(f"{where}: unknown keys: {', '.join(extra)}")
        if not cid:
            continue
        if not valid_id(cid):
            problems.append(f"{where}: a concept's ID is lowercase words joined by hyphens, at most 64 characters")
            continue
        concept = Concept(
            id=cid, term=_text(raw, "term", where, problems, True),
            definition=_text(raw, "definition", where, problems, True),
            section=_text(raw, "section", where, problems, True),
            context=_text(raw, "context", where, problems) or cs.context,
            aliases=_strings(raw.get("aliases"), "aliases", where, problems),
            formula=_text(raw, "formula", where, problems),
            relations=_relations(raw.get("relations"), where, problems),
            applies_to=_strings(raw.get("applies_to"), "applies_to", where, problems),
            example=_text(raw, "example", where, problems),
            wikidata=_text(raw, "wikidata", where, problems), line=line)
        if not concept.context:
            problems.append(f"{where}: name its context, or give the file one with context = \"…\" at its top")
        if BLANK_LINE.search(concept.definition) or BLANK_LINE.search(concept.formula):
            problems.append(f"{where}: W-77: a definition, and a formula, is one passage of its section: no blank line")
        if concept.wikidata and not catalog.QID.match(concept.wikidata):
            problems.append(f"{where}: wikidata is an item's ID, such as Q2539")
        cs.concepts.append(concept)
    return cs


def load(path: Path) -> ConceptSet:
    """A concepts.toml on its own, such as an organization's repository holds: empty, with `present` false, when
    there's no file."""
    path = Path(path)
    if not path.is_file():
        return ConceptSet(file=path.name)
    return parse(path.read_text(encoding="utf-8").replace("\r\n", "\n"), path.name)


def for_book(root: Path) -> ConceptSet:
    """The book's concepts.toml, beside its book.toml (Book.concepts)."""
    return load(Path(root) / FILE)


# ---------------------------------------------------------------- the text, as a reader reads it


@dataclass
class Block:
    """One block of a unit's text: a paragraph, a list item's paragraph, a table cell, a heading or a code block."""
    unit: str                   # the chapter's ID for its opening, or the section's ID
    line: int                   # 0-based line in the unit's source
    kind: str                   # prose, heading, embed or code
    text: str                   # what a reader reads: no emphasis or link targets, code as written, a line break as "\n"
    uses: str                   # where a term is a use: the text with inline code and bindings blanked
    links: frozenset[str]       # the IDs its internal links point at (its table row's, for a table cell)


def _inline(tok: Token) -> tuple[str, str, set[str]]:
    text, uses, links = [], [], set()
    for c in tok.children or []:
        if c.type == "text":
            text.append(c.content)
            uses.append(c.content)
        elif c.type == "code_inline":
            text.append(c.content)
            uses.append(" ")
        elif c.type in ("softbreak", "hardbreak"):
            text.append("\n")
            uses.append("\n")
        elif c.type == "link_open":
            href = str(c.attrGet("href") or "")
            if href.startswith("#") and len(href) > 1:
                links.add(href[1:])
    return "".join(text), BINDING.sub(" ", "".join(uses)), links


def _only_link(tok: Token) -> bool:
    """A paragraph that is only a link: an example, step, check or file embedded, never prose."""
    kids = [c for c in tok.children or [] if not (c.type == "text" and not c.content.strip())]
    return (len(kids) >= 2 and kids[0].type == "link_open" and kids[-1].type == "link_close"
            and not any(c.type in ("link_open", "link_close") for c in kids[1:-1]))


def blocks(source: str, unit: str = "") -> list[Block]:
    """A unit's text as blocks, parsed as the book's renderer parses it."""
    tokens = new_markdown().parse(source)
    out: list[Block] = []
    row: list[Block] = []
    parent = ""
    for tok in tokens:
        if tok.type in ("paragraph_open", "heading_open"):
            parent = tok.type
        elif tok.type in ("th_open", "td_open"):
            parent = "cell"
        elif tok.type == "tr_close":
            shared = frozenset().union(*(b.links for b in row)) if row else frozenset()
            for b in row:
                b.links = shared
            row = []
        elif tok.type == "inline":
            text, uses, links = _inline(tok)
            kind = "heading" if parent == "heading_open" else "embed" if parent == "paragraph_open" and _only_link(tok) \
                else "prose"
            block = Block(unit, tok.map[0] if tok.map else 0, kind, text, uses, frozenset(links))
            out.append(block)
            if parent == "cell":
                row.append(block)
        elif tok.type in ("fence", "code_block"):
            out.append(Block(unit, tok.map[0] if tok.map else 0, "code", tok.content, "", frozenset()))
    return out


def squash(text: str) -> str:
    """Text compared as a reader reads it: NFC, every run of white space one space, trimmed."""
    return SPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def quoted_forms(quote: str) -> set[str]:
    """The forms a quote may match in: as written, and as its own Markdown reads, so a quote copied from the page and
    one copied from the chapter's source both match."""
    return {f for f in (squash(quote), squash(" ".join(b.text for b in blocks(quote)))) if f}


def _found(haystack: str, needle: str) -> bool:
    """Whether needle is in haystack, starting and ending at a word's edge."""
    start = 0
    while (i := haystack.find(needle, start)) >= 0:
        before, after = haystack[i - 1:i], haystack[i + len(needle):i + len(needle) + 1]
        if not (needle[0].isalnum() and before.isalnum()) and not (needle[-1].isalnum() and after.isalnum()):
            return True
        start = i + 1
    return False


def quoted_in(quote: str, source: str) -> bool:
    """Whether a quote is in a unit's text, word for word, within one block: emphasis, links, line breaks and entities
    aside, as the reader never sees them. Bindings are compared as written."""
    texts = [squash(b.text) for b in blocks(source)]
    return any(_found(t, form) for form in quoted_forms(quote) for t in texts)


# ---------------------------------------------------------------- the checks


def known_contexts(cs: ConceptSet, taxonomy: dict | None = None) -> set[str]:
    """The contexts a file's concepts may be in: ours are the taxonomy's areas and skills and the file's own; an
    organization's are the ones its file declares."""
    declared = set(cs.contexts)
    if not cs.ours:
        return declared
    tax = taxonomy or catalog.load_taxonomy()
    return declared | {t["id"] for t in tax["areas"] + tax["skills"]}


def context_problems(cs: ConceptSet, taxonomy: dict | None = None) -> list[str]:
    """Each declared context sits under a known one, in no circle and shadowing none of the taxonomy's; each concept
    is in a known context."""
    problems: list[str] = []
    tax = taxonomy or catalog.load_taxonomy()
    ours = {t["id"] for t in tax["areas"] + tax["skills"]} if cs.ours else set()
    known = ours | set(cs.contexts)
    for ctx in cs.contexts.values():
        where = cs.where(ctx.line)
        if ctx.id in ours:
            problems.append(f"{where}: {ctx.id} is already one of the taxonomy's areas and skills: use it, don't declare it")
        elif not ctx.broader and not cs.ours:
            continue
        elif ctx.broader not in known:
            problems.append(f"{where}: the context {ctx.id} is narrower than {ctx.broader!r}, which isn't a taxonomy "
                            "area or skill, or a context declared here")
        else:
            seen, at = {ctx.id}, ctx.broader
            while at in cs.contexts and at not in seen:
                seen.add(at)
                at = cs.contexts[at].broader
            if at in seen:
                problems.append(f"{where}: the context {ctx.id} is narrower than itself, through {ctx.broader}")
    for c in cs.concepts:
        if c.context and c.context not in known:
            problems.append(f"{cs.where(c.line)}: {c.id}: {c.context!r} isn't a context: use a taxonomy area or skill, "
                            "or declare a narrower one under [[contexts]]" if cs.ours else
                            f"{cs.where(c.line)}: {c.id}: {c.context!r} isn't a context declared under [[contexts]]")
    return problems


def quote_problems(cs: ConceptSet, text_of: Callable[[str], str | None],
                   retired: Callable[[str], str | None] = lambda unit: None,
                   units: list[str] | None = None, bind: Callable[[str], str] | None = None) -> list[str]:
    """W-77: each definition and formula is in its section's text, word for word, and the section exists. text_of
    gives a unit's source (Book.unit_source for a book; an organization's file, later, its own documents'). retired
    says what a retired ID's successor is; units, every unit, to say where a quote is when it isn't in its own; bind
    (Book.bind), to say when a quote copied the text as read, its bindings filled in."""
    problems: list[str] = []
    for c in cs.concepts:
        if not c.section:
            continue
        where = f"{cs.where(c.line)}: {c.id}"
        source = text_of(c.section)
        if source is None:
            successor = retired(c.section)
            problems.append(f"{where}: W-77: #{c.section} is retired; its successor is #{successor}" if successor else
                            f"{where}: W-77: there is no section #{c.section} in this book")
            continue
        for what, quote in (("definition", c.definition), ("formula", c.formula)):
            if not quote or quoted_in(quote, source):
                continue
            elsewhere = [u for u in units or [] if u != c.section and quoted_in(quote, text_of(u) or "")]
            as_read = bind is not None and BINDING.search(source) and quoted_in(quote, bind(source))
            hint = (f"; it's in #{elsewhere[0]}, so give that section" if elsewhere else
                    "; it quotes the text as read: quote its bindings as written, such as {{out:…}}" if as_read else "")
            problems.append(f"{where}: W-77: its {what} isn't in #{c.section}'s text, word for word: quote the book's "
                            f"own {'sentence' if what == 'definition' else 'formula'}, as the section writes it "
                            f"(emphasis, links and line breaks aside){hint}")
    return problems


def once_problems(cs: ConceptSet) -> list[str]:
    """W-78: a concept is defined once; its ID, term and aliases each name one concept in its context; no two concepts
    quote the same definition."""
    problems: list[str] = []
    by_key: dict[tuple[str, str], Concept] = {}
    names: dict[tuple[str, str], Concept] = {}
    quotes: dict[str, Concept] = {}
    for c in cs.concepts:
        where = f"{cs.where(c.line)}: {c.id}"
        if c.key in by_key:
            problems.append(f"{where}: W-78: {c.id} is in {c.context} twice (see line {by_key[c.key].line}); a book "
                            "defines a concept once")
            continue
        by_key[c.key] = c
        own: set[str] = set()
        for name in c.names:
            folded = name.casefold()
            if folded in own:
                problems.append(f"{where}: W-78: {name!r} is listed twice for {c.id}")
                continue
            own.add(folded)
            other = names.get((c.context, folded))
            if other is not None:
                problems.append(f"{where}: W-78: {name!r} names both {other.id} and {c.id} in {c.context}: a term or "
                                "alias names one concept in a context, and a second meaning goes in a context of its own")
            else:
                names[(c.context, folded)] = c
        quote = squash(c.definition)
        if quote and quote in quotes:
            problems.append(f"{where}: W-78: {c.id} quotes the same definition as {quotes[quote].id}: one definition, "
                            "one concept")
        elif quote:
            quotes[quote] = c
    return problems


def pinned_problems(cs: ConceptSet, pins: Mapping[str, str], where_pinned: str) -> list[str]:
    """W-77: what applies_to names is pinned, so each edition says the version the definition is true for."""
    return [f"{cs.where(c.line)}: {c.id}: W-77: applies_to names {name}, which {where_pinned} doesn't pin: the version "
            "a definition is true for comes from the book's pins"
            for c in cs.concepts for name in c.applies_to if package_key(name) not in pins]


def example_problems(cs: ConceptSet, live: Mapping[str, str]) -> list[str]:
    """Each concept's example is an example, step or check the book has."""
    return [f"{cs.where(c.line)}: {c.id}: there is no example {c.example!r} in this book" for c in cs.concepts
            if c.example and live.get(c.example) not in ("example", "step", "check")]


# a reference to a concept, resolved: (namespace, context, id), or why it can't be
@dataclass(frozen=True)
class Target:
    namespace: str
    context: str
    id: str
    local: bool                 # in this file


def resolve(cs: ConceptSet, ref: str, context: str, known: set[str]) -> tuple[Target | None, str]:
    """A reference to a concept, from a concept in `context`: an ID in this file, `context/id`, or an address. (None,
    why) when it doesn't name one this file has, or a well-formed address in another context."""
    namespace = cs.namespace
    if ref.startswith(("https://", "http://")):
        ours = settings()["addresses"]
        bases = {cs.base: cs.namespace, ours["base"]: ours["namespace"]}
        base = next((b for b in bases if ref.startswith(b + "/")), None)
        if base is None:
            return None, f"{ref} isn't a concept's address: it starts {cs.base}/"
        namespace, ref = bases[base], ref[len(base) + 1:]
        if "@" in ref:
            return None, f"{ref}: point at a concept's address, never at one edition of it"
        if namespace != cs.namespace:
            parts = ref.split("/")
            if len(parts) != 2 or not all(valid_id(p) for p in parts):
                return None, f"{ref} isn't a concept's address: it ends /context/id"
            return Target(namespace, parts[0], parts[1], False), ""
    parts = ref.split("/")
    if len(parts) == 1:
        if not valid_id(ref):
            return None, f"{ref!r} isn't a concept's ID"
        found = [c for c in cs.concepts if c.id == ref]
        mine = [c for c in found if c.context == context]
        if mine or len(found) == 1:
            hit = (mine or found)[0]
            return Target(namespace, hit.context, hit.id, True), ""
        if found:
            return None, f"{ref} is in {' and '.join(sorted(c.context for c in found))}: write context/{ref}"
        return None, f"there's no concept {ref} in this book"
    if len(parts) != 2 or not all(valid_id(p) for p in parts):
        return None, f"{ref!r} isn't a concept's ID, context/ID or address"
    ctx, cid = parts
    if ctx not in known:
        return None, f"{ctx!r} isn't a context: a taxonomy area or skill, or one declared here"
    if cs.get(ctx, cid):
        return Target(namespace, ctx, cid, True), ""
    if ctx == context:
        return None, f"there's no concept {cid} in {ctx} in this book"
    return Target(namespace, ctx, cid, False), ""           # another context's: whether it exists is checked across books


def relation_problems(cs: ConceptSet, known: set[str], pins: Mapping[str, str] | None = None) -> list[str]:
    """W-80: every relation's type is one of data/concepts.toml's, and its target is what that type points at: a
    concept this file has, or a well-formed address in another context; another context's concept or a Wikidata item;
    or a package, whose pin is within the range given. No acyclic type goes round in a circle."""
    types = relation_types()
    problems: list[str] = []
    edges: dict[str, list[tuple[tuple[str, str], tuple[str, str]]]] = {}
    for c in cs.concepts:
        where = f"{cs.where(c.line)}: {c.id}"
        for r in c.relations:
            spec = types.get(r.type)
            if spec is None:
                problems.append(f"{where}: W-80: {r.type!r} isn't a relation type; use one of {', '.join(types)}")
                continue
            if spec.get("reserved") == "organization" and cs.ours:
                problems.append(f"{where}: W-80: {r.type} is for an organization's own concepts, never a book's")
                continue
            if r.versions and spec["target"] != "package":
                problems.append(f"{where}: W-80: a version range goes with implemented-by, the package's; "
                                f"{r.type} {r.to} has one")
                continue
            if spec["target"] == "package":
                problems += _package_problems(where, r, pins or {})
                continue
            if spec["target"] == "organization":
                if not valid_id(r.to):
                    problems.append(f"{where}: W-80: {r.type} names an organization's namespace, not {r.to!r}")
                continue
            if spec["target"] == "match" and WIKIDATA.match(r.to):
                continue
            target, why = resolve(cs, r.to, c.context, known)
            if target is None:
                problems.append(f"{where}: W-80: {r.type} {r.to}: {why}")
                continue
            if target.local and (target.context, target.id) == c.key:
                problems.append(f"{where}: W-80: {c.id} is {r.type} itself")
            elif spec["target"] == "match" and target.context == c.context and target.namespace == cs.namespace:
                problems.append(f"{where}: W-80: {r.type} links to another context's concept, or to a Wikidata item "
                                f"(wikidata:Q…); in one context, two concepts that mean the same are one concept")
            elif spec.get("acyclic") and target.local:
                edges.setdefault(r.type, []).append((c.key, (target.context, target.id)))
    return problems + _circles(cs, edges, types)


def _package_problems(where: str, r: Relation, pins: Mapping[str, str]) -> list[str]:
    if not PACKAGE.match(r.to):
        return [f"{where}: W-80: {r.type} names a package or tool, not {r.to!r}"]
    if not r.versions:
        return []
    try:
        spec = SpecifierSet(r.versions)
    except InvalidSpecifier:
        return [f"{where}: W-80: {r.to}'s versions {r.versions!r} isn't a version range, such as \">=0.3,<0.4\""]
    pinned = pins.get(package_key(r.to))
    try:
        if pinned and not spec.contains(Version(pinned), prereleases=True):
            return [f"{where}: W-80: {r.type} {r.to} {r.versions}, and the book pins {r.to} {pinned}: say the range the "
                    "relation holds within, or the definition the new version needs"]
    except InvalidVersion:
        pass                                             # a pin that isn't a version number: nothing to compare
    return []


def _circles(cs: ConceptSet, edges: dict[str, list], types: dict[str, dict]) -> list[str]:
    """A circle in an acyclic type, with its inverse read the other way round, as one: broader and narrower are one
    hierarchy. Each circle is named once."""
    problems, seen = [], set()
    for kind in types:
        if not types[kind].get("acyclic") or kind not in edges and types[kind].get("inverse") not in edges:
            continue
        inverse = types[kind].get("inverse")
        graph: dict[tuple[str, str], set[tuple[str, str]]] = {}
        for a, b in edges.get(kind, []):
            graph.setdefault(a, set()).add(b)
        for a, b in edges.get(inverse, []) if inverse else []:
            graph.setdefault(b, set()).add(a)
        for loop in _find_circles(graph):
            name = min(kind, inverse or kind)
            if (name, frozenset(loop)) in seen:
                continue
            seen.add((name, frozenset(loop)))
            first = cs.get(*loop[0])
            path = " → ".join(k[1] for k in loop + [loop[0]])
            problems.append(f"{cs.where(first.line if first else 0)}: {loop[0][1]}: W-80: {kind} goes round in a circle: "
                            f"{path}" + (f" ({inverse} counted the other way round)" if inverse in edges else ""))
    return problems


def _find_circles(graph: dict) -> list[list]:
    """One circle in each strongly connected part of a graph that has one, starting at its least node."""
    index, low, stack, on, parts, counter = {}, {}, [], set(), [], [0]

    def connect(v) -> None:                              # Tarjan's algorithm, recursive: the graphs are small
        index[v] = low[v] = counter[0]
        counter[0] += 1
        stack.append(v)
        on.add(v)
        for w in sorted(graph.get(v, ())):
            if w not in index:
                connect(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            part = []
            while True:
                w = stack.pop()
                on.discard(w)
                part.append(w)
                if w == v:
                    break
            if len(part) > 1:
                parts.append(set(part))

    for v in sorted(set(graph) | {w for ws in graph.values() for w in ws}):
        if v not in index:
            connect(v)
    circles = []
    for part in parts:
        start = min(part)
        path, at = [start], start
        prev: dict = {start: None}
        queue = [start]
        while queue:                                     # the shortest way round, from start back to start, in the part
            at = queue.pop(0)
            nxt = [w for w in sorted(graph.get(at, ())) if w in part]
            if start in nxt:
                break
            for w in nxt:
                if w not in prev:
                    prev[w] = at
                    queue.append(w)
        path = []
        while at is not None:
            path.append(at)
            at = prev[at]
        circles.append(list(reversed(path)))
    return circles


# ---------------------------------------------------------------- W-79: link before use


def _use_pattern(name: str) -> re.Pattern:
    """A term's or alias's use, matched conservatively ([uses] in data/concepts.toml): whole words, with its joining
    characters counted as part of a word; a term with a capital after its first letter only as written, any other with
    its first letter in either case."""
    joining = r"\w" + re.escape(settings()["uses"]["joining"])
    body = r"\s+".join(re.escape(w) for w in name.split())
    first = name[0]
    if first.isalpha() and not any(ch.isupper() for ch in name[1:]):
        body = f"[{re.escape(first.lower())}{re.escape(first.upper())}]" + body[len(re.escape(first)):]
    return re.compile(rf"(?<![{joining}]){body}(?![{joining}])")


@dataclass
class _Unit:
    chapter: Chapter
    unit: str
    first_line: int             # the 1-based file line of its source's first line
    blocks: list[Block]


def _reading_order(book: Book) -> list[_Unit]:
    out = []
    for c in book.chapters:
        out.append(_Unit(c, c.chapter_id, c.body_offset + 1, blocks(c.opening, c.chapter_id)))
        out += [_Unit(c, s.section_id, s.line, blocks(s.source, s.section_id)) for s in c.sections]
    return out


def _first_use(text: str, patterns: list[re.Pattern], longer: list[re.Pattern]) -> tuple[int, str] | None:
    """The first use of any of a concept's names in a block's text, as (position, the words as written): never one inside
    a longer name of another concept, as "reciprocal rank" inside "reciprocal rank fusion"."""
    covered = [m.span() for rx in longer for m in rx.finditer(text)]
    found = [(m.start(), m.group(0)) for rx in patterns for m in rx.finditer(text)
             if not any(a <= m.start() and m.end() <= b and b - a > m.end() - m.start() for a, b in covered)]
    return min(found, default=None)


def link_problems(book: Book, cs: ConceptSet) -> list[str]:
    """W-79: a chapter that uses a concept's term or alias before the section defining it links its first such use to
    that section (or the ## section it's under), in the same block or before it. Headings, code, inline code, bindings
    and embeds are never uses, nor is a name inside a longer name of another concept; and the defining chapter's
    opening, which promises what the chapter teaches, may name it before its section does."""
    order = _reading_order(book)
    position = {u.unit: i for i, u in enumerate(order)}
    parent = {s.section_id: s.parent_id for s in book.sections}
    names = {name: _use_pattern(name) for c in cs.concepts for name in c.names if name}
    problems: list[str] = []
    for concept in cs.concepts:
        at = position.get(concept.section)
        if at is None:
            continue                                     # W-77 says its section doesn't exist
        targets = {concept.section} | ({parent[concept.section]} if parent.get(concept.section) else set())
        own = {n.casefold() for n in concept.names if n}
        patterns = [names[n] for n in concept.names if n]
        longer = [rx for name, rx in names.items()
                  if name.casefold() not in own and any(n in name.casefold() and len(name) > len(n) for n in own)]
        defining = order[at].chapter
        done: set[str] = set()
        for unit in order[:at]:
            chapter = unit.chapter
            if chapter.chapter_id in done or (chapter is defining and unit.unit == chapter.chapter_id):
                continue
            for b in unit.blocks:
                if b.kind != "prose":
                    continue
                if b.links & targets:
                    done.add(chapter.chapter_id)
                    break
                hit = _first_use(b.uses, patterns, longer)
                if hit is None:
                    continue
                line = unit.first_line + b.line + b.uses[:hit[0]].count("\n")
                place = "later in this chapter" if chapter is defining else f"chapter {defining.order}"
                problems.append(f"{chapter.file}:{line}: W-79: \"{hit[1]}\" comes before its definition in "
                                f"#{concept.section} ({place}): link this first use, as [{hit[1]}](#{concept.section})")
                done.add(chapter.chapter_id)
                break
    return problems


# ---------------------------------------------------------------- the check


def check(book: Book, taxonomy: dict | None = None) -> tuple[list[str], list[str]]:
    """(problems, notes) for a book's concepts.toml: the format, then checks 1, 2, 6 and 3 (W-77 to W-80). A book
    without one has none of either. Notes are what [uses] lists rather than fails."""
    cs = book.concepts
    if not cs.present:
        return [], []
    if not cs.ours:
        return [f"{cs.file}: a book's concepts are in our namespace; only an organization's file names its own"], []
    problems = list(cs.problems)
    known = known_contexts(cs, taxonomy)
    live = book.ids()
    units = [u for c in book.chapters for u in [c.chapter_id, *(s.section_id for s in c.sections)]]
    where_pinned = "examples/requirements.txt" + (f" or {stack_pins.STACK}" if (book.root / stack_pins.STACK).exists()
                                                  else "")
    problems += context_problems(cs, taxonomy)
    problems += quote_problems(cs, book.unit_source, lambda u: book.resolve(u) if u in book.redirects else None, units,
                               book.bind)
    problems += once_problems(cs)
    problems += pinned_problems(cs, book.pins, where_pinned)
    problems += example_problems(cs, live)
    problems += relation_problems(cs, known, book.pins)
    linked = link_problems(book, cs)
    if settings()["uses"].get("fails", True):
        return problems + linked, []
    return problems, linked


# ---------------------------------------------------------------- served


def served(book: Book, edition: str, changed: Mapping[str, Mapping[str, str]] | None = None,
           commit: str | None = None) -> list[dict]:
    """Each concept of a book whose concepts pass `re-check concepts`, in the shape it's served in, with its generated
    fields: its addresses, the version each package it applies to is pinned at (Book.pins: examples/requirements.txt,
    or a terminal book's examples/stack.toml), the edition, and its provenance. Pure: the same book, edition and
    inputs give the same records. `changed` comes from the release records: each concept's first edition and the
    edition it last changed in, by address, as {"first": "2026.10.1", "changed": "2026.11.3"}; a concept it doesn't
    name is new in this edition. `commit` is the commit the edition was cut from, when given.

    How it maps onto JSON-LD, as a node typed both schema:DefinedTerm and skos:Concept:
    - address: the node's @id; edition_address, the @id of this edition's version of it, dct:isVersionOf address
    - term: schema:name and skos:prefLabel; aliases: schema:alternateName and skos:altLabel
    - definition: schema:description and skos:definition, the book's sentence as read, its bindings filled in
    - formula: the vocabulary's formula, a refinement of skos:note
    - id: schema:termCode and skos:notation
    - context, context_address: schema:inDefinedTermSet and skos:inScheme, a schema:DefinedTermSet that is also a
      skos:ConceptScheme, at context_address
    - section: schema:subjectOf, the section of the book that defines it
    - applies_to: the vocabulary's appliesTo, each a schema:SoftwareApplication with schema:name and
      schema:softwareVersion, the version the edition pins
    - example: the vocabulary's example, the book's example that shows it
    - wikidata: schema:sameAs and skos:exactMatch, the item's entity address
    - relations: each its type's `skos` property, refined by the vocabulary's `property` (data/concepts.toml); a
      package's (implemented-by) a schema:SoftwareApplication with its pinned version and the range it holds within
    - edition: schema:version; first_edition and changed_edition, the vocabulary's
    - provenance: prov:wasDerivedFrom the section in the edition, at the commit, and prov:wasGeneratedBy the check
    A relation's provenance is its concept's: the same file at the same edition and commit.
    """
    cs = book.concepts
    cfg = settings()
    types = relation_types()
    pins = book.pins
    known = known_contexts(cs)
    located = {s.section_id: (s.chapter_id, s.title) for s in book.sections}
    located.update({c.chapter_id: (c.chapter_id, c.title) for c in book.chapters})
    out = []
    for c in cs.concepts:
        address = cs.address(c.context, c.id)
        history = (changed or {}).get(address) or {}
        chapter_id, title = located.get(c.section, (None, None))
        relations = []
        for r in c.relations:
            spec = types.get(r.type)
            if spec is None:
                continue
            entry = {"type": r.type, "skos": spec["skos"] or None, "property": spec["property"]}
            if spec["target"] == "package":
                entry |= {"package": r.to, "versions": r.versions or None, "version": pins.get(package_key(r.to))}
            elif (m := WIKIDATA.match(r.to)) and spec["target"] == "match":
                entry |= {"target": cfg["addresses"]["wikidata"].format(qid=m.group(1))}
            else:
                target, _ = resolve(cs, r.to, c.context, known)
                if target is None:
                    continue
                base = cs.base if target.namespace == cs.namespace else cfg["addresses"]["base"]
                entry |= {"target": cfg["addresses"]["concept"].format(base=base, context=target.context, id=target.id)}
            relations.append(entry)
        out.append({
            "address": address,
            "edition_address": cs.address(c.context, c.id, edition),
            "namespace": cs.namespace,
            "context": c.context,
            "context_address": cs.context_address(c.context),
            "id": c.id,
            "term": c.term,
            "aliases": list(c.aliases),
            "definition": squash(" ".join(b.text for b in blocks(book.bind(c.definition)))),
            "formula": book.bind(c.formula) if c.formula else None,
            "section": {"id": c.section, "chapter": chapter_id, "title": title},
            "applies_to": [{"package": name, "version": pins.get(package_key(name))} for name in c.applies_to],
            "example": c.example or None,
            "wikidata": cfg["addresses"]["wikidata"].format(qid=c.wikidata) if c.wikidata else None,
            "relations": relations,
            "edition": edition,
            "first_edition": history.get("first", edition),
            "changed_edition": history.get("changed", history.get("first", edition)),
            "provenance": {"book": book.slug, "file": cs.file, "section": c.section, "edition": edition,
                           "commit": commit, "checked_by": "re-check concepts"},
        })
    return out
