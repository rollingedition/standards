"""The spoken script: the words narration reads, built by code from the parsed book, never by a model.

A chapter's script is a list of Lines, one per recorded clip: its opening, then its headings, paragraphs and list
items word for word, with every binding filled in, then its ending. Code, output and tables aren't read. Each
example, fenced block and table is read as the description the book gives it in `narration/{chapter_id}.toml`, or
announced where it has none. Then every Line goes through the shared rules in `data/narration.toml` and the book's
`narration/lexicon.toml`: terms first, then symbols and numbers as words. The same book always gives the same script.

    narration/lexicon.toml        [terms] exact replacements, [words] case-insensitive whole words
    narration/{chapter_id}.toml   [examples.{example_id}] say = "…"
                                  [[blocks]] section = "…"  starts = "its first line"  say = "…"
                                  [[tables]] section = "…"  starts = "| its first | row"  say = "…"

`re-check narration` lists what the rules don't cover, so a writer can read the script before a voice does.
"""
from __future__ import annotations

import json
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from markdown_it.token import Token

from . import data_path, style
from .bookfmt import BINDING, SECTION_LEVELS, Book, Chapter, _embed_id, _strip_heading_id, new_markdown

KINDS = ("opening", "heading", "prose", "item", "working-rule", "quote", "example", "block", "table", "ending", "credits")

# Private-use characters mark spans while a Line is built, and never reach its text: a value a binding filled in
# (a count, never a year); a lexicon's reading of inline code (never read through the lexicon again); a number that
# opens a sentence (its words get a capital); and a binding that didn't resolve, held as written through every rule.
BOUND = ("\ue000", "\ue001")
KEPT = ("\ue002", "\ue003")
CAPITAL = "\ue004"
HELD = "\ue005"
MARKS = re.compile("[\ue000-\ue007]")
# A link to a part of the book is marked while its words are read, so a parenthesis holding nothing but such links
# (a cross-reference such as "(Score one ranking)") can be left out: it helps a reader find a section, not a listener.
XREF_OPEN, XREF_CLOSE = "\ue006", "\ue007"
XREF_ONLY = re.compile(r"\s*\((?:\s*\ue006[^\ue007]*\ue007\s*(?:,|;|and)?)+\s*\)")


@dataclass
class Line:
    """One recorded clip: its number in the script, what it is, the unit it belongs to (a section ID, or the chapter's
    ID for its opening and the text before its first section) and the words a voice reads."""
    n: int
    kind: str
    unit: str
    text: str
    line: int = 0               # 1-based line in the chapter file it comes from; 0 for a template's Line


# ---------------------------------------------------------------- the rules and the book's narration files


def load_rules(path: Path | None = None) -> dict:
    with open(path or data_path("narration.toml"), "rb") as f:
        return tomllib.load(f)


def rules_version(rules: dict | None = None) -> int:
    """The rules' version, which a recorded clip's key includes."""
    return int((rules or load_rules())["rules_version"])


@dataclass
class Narration:
    """A book's narration files: its lexicon, and each chapter's descriptions."""
    terms: dict[str, str] = field(default_factory=dict)
    words: dict[str, str] = field(default_factory=dict)
    chapters: dict[str, dict] = field(default_factory=dict)    # chapter ID -> {"examples": {id: say}, "blocks": [...], "tables": [...]}
    problems: list[str] = field(default_factory=list)          # files that don't parse or hold what they shouldn't


def _strings(table, where: str, problems: list[str]) -> dict[str, str]:
    if not isinstance(table, dict):
        problems.append(f"{where} must be a table of strings")
        return {}
    bad = [k for k, v in table.items() if not isinstance(v, str)]
    problems += [f"{where}: {k!r} must be a string" for k in bad]
    return {k: v for k, v in table.items() if isinstance(v, str)}


def load_narration(book_root: Path) -> Narration:
    """The book's narration/ folder. Every file is optional; problems are collected for the check, never raised."""
    out = Narration()
    folder = Path(book_root) / "narration"
    for path in sorted(folder.glob("*.toml")) if folder.is_dir() else []:
        rel = f"narration/{path.name}"
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, UnicodeDecodeError) as e:
            out.problems.append(f"{rel} doesn't parse: {e}")
            continue
        if path.stem == "lexicon":
            for key in sorted(set(data) - {"terms", "words"}):
                out.problems.append(f"{rel}: unknown table [{key}]; a lexicon has [terms] and [words]")
            out.terms = _strings(data.get("terms", {}), f"{rel} [terms]", out.problems)
            out.words = {k.lower(): v for k, v in _strings(data.get("words", {}), f"{rel} [words]", out.problems).items()}
            continue
        chapter: dict = {"examples": {}, "blocks": [], "tables": []}
        for key in sorted(set(data) - {"examples", "blocks", "tables"}):
            out.problems.append(f"{rel}: unknown key {key!r}; a chapter's narration has [examples.ID], [[blocks]] and [[tables]]")
        examples = data.get("examples", {})
        if not isinstance(examples, dict):
            out.problems.append(f"{rel}: examples must be tables, as [examples.example-id]")
            examples = {}
        for eid, entry in examples.items():
            if not isinstance(entry, dict) or not isinstance(entry.get("say"), str) or set(entry) - {"say"}:
                out.problems.append(f"{rel}: [examples.{eid}] holds one key, say, a string")
            else:
                chapter["examples"][eid] = entry["say"]
        for kind in ("blocks", "tables"):
            entries = data.get(kind, [])
            if not isinstance(entries, list):
                out.problems.append(f"{rel}: {kind} must be an array of tables, as [[{kind}]]")
                continue
            for n, entry in enumerate(entries, 1):
                ok = isinstance(entry, dict) and all(isinstance(entry.get(k), str) and entry.get(k).strip()
                                                     for k in ("section", "starts", "say"))
                if not ok or set(entry) - {"section", "starts", "say"}:
                    out.problems.append(f"{rel}: [[{kind}]] {n} needs section, starts and say, each a string, and nothing else")
                    continue
                chapter[kind].append({"n": n, **entry})
        out.chapters[path.stem] = chapter
    return out


# ---------------------------------------------------------------- numbers as words

ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = ("", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety")
SCALES = ((10**9, "billion"), (10**6, "million"), (1000, "thousand"))
ORDINAL = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
           "twelve": "twelfth"}


def _under_100(n: int) -> str:
    if n < 20:
        return ONES[n]
    tens, ones = divmod(n, 10)
    return TENS[tens] + (f"-{ONES[ones]}" if ones else "")


def _under_1000(n: int, and_: bool) -> str:
    hundreds, rest = divmod(n, 100)
    if not hundreds:
        return _under_100(rest)
    words = f"{ONES[hundreds]} hundred"
    return words + ((" and " if and_ else " ") + _under_100(rest) if rest else "")


def cardinal(n: int, and_: bool = True) -> str:
    """An integer in words, to the billions: 13077 is "thirteen thousand and seventy-seven" ("thirteen thousand
    seventy-seven" without and_). Anything larger is read digit by digit."""
    if n < 0:
        return "minus " + cardinal(-n, and_)
    if n >= 10**12:
        return " ".join(ONES[int(d)] for d in str(n))
    parts: list[str] = []
    for scale, name in SCALES:
        count, n = divmod(n, scale)
        if count:
            parts.append(f"{_under_1000(count, and_) if count < 1000 else cardinal(count, and_)} {name}")
    if n or not parts:
        if parts and n < 100 and and_:
            parts.append("and")
        parts.append(_under_1000(n, and_))
    return " ".join(parts)


def ordinal(n: int) -> str:
    """first, second, twenty-first: for days of the month and written ordinals such as 10th."""
    words = cardinal(n)
    head, sep, last = words.rpartition(" ") if "-" not in words.rsplit(" ", 1)[-1] else words.rpartition("-")
    if last in ORDINAL:
        last = ORDINAL[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return head + sep + last


def year(n: int) -> str:
    """A year as it's said: 1998 "nineteen ninety-eight", 2004 "two thousand four", 2022 "twenty twenty-two",
    1905 "nineteen oh five", 1900 "nineteen hundred"."""
    if 2000 <= n <= 2009:
        return cardinal(n, and_=False)
    century, rest = divmod(n, 100)
    if rest == 0:
        return f"{cardinal(century)} hundred"
    return f"{cardinal(century)} {'oh ' + ONES[rest] if rest < 10 else _under_100(rest)}"


def plural(words: str) -> str:
    """The plural of a number's words: "tens", "twenties", "nineteen nineties"."""
    if words.endswith("y"):
        return words[:-1] + "ies"
    return words + ("es" if words.endswith("x") else "s")


def decimal(text: str, point: str = "point", and_: bool = True) -> str:
    """A decimal digit by digit after the point: 0.615 is "zero point six one five"; commas group the whole part."""
    whole, _, frac = text.replace(",", "").partition(".")
    return cardinal(int(whole), and_) + (f" {point} " + " ".join(ONES[int(d)] for d in frac) if frac else "")


SUPERSCRIPT = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺ⁿⁱˢʳᵇᵀ", "0123456789−+nisrbT"))
SUBSCRIPT = dict(zip("₀₁₂₃₄₅₆₇₈₉₋₊ᵢⱼₙₖₜₓ", "0123456789−+ijnktx"))


# ---------------------------------------------------------------- the rules, compiled


def _boundary(term: str) -> str:
    """A term at word boundaries: no letter or digit right before it when it starts with one, or right after it when
    it ends with one. So "BM25" isn't read inside "bm25s", and "<sep>" is read inside "<sep>stools"."""
    return ((r"(?<![A-Za-z0-9])" if term[:1].isalnum() else "") + re.escape(term)
            + (r"(?![A-Za-z0-9])" if term[-1:].isalnum() else ""))


def _outside(text: str, marks: tuple[str, str], fn) -> str:
    """fn applied to the text outside the spans these marks enclose."""
    parts = re.split(f"({re.escape(marks[0])}.*?{re.escape(marks[1])})", text)
    return "".join(p if i % 2 else fn(p) for i, p in enumerate(parts))


class Speaker:
    """The shared rules and a book's lexicon, compiled: how any text becomes the words a voice reads."""

    def __init__(self, rules: dict, narration: Narration | None = None):
        narration = narration or Narration()
        self.rules = rules
        self.templates = rules["templates"]
        self.numbers = rules["numbers"]
        self.and_ = bool(self.numbers.get("and", True))
        self.year_range = tuple(self.numbers.get("years", (1900, 2099)))
        self.terms = {**rules.get("terms", {}), **narration.terms}
        self.words = {**{k.lower(): v for k, v in rules.get("words", {}).items()}, **narration.words}
        entries = sorted([(t, False) for t in self.terms] + [(w, True) for w in self.words], key=lambda e: -len(e[0]))
        self.lexicon = re.compile("|".join(f"(?i:{_boundary(t)})" if ci else _boundary(t) for t, ci in entries)) if entries else None
        self.symbols = rules.get("symbols", {})
        self.symbol_re = re.compile("|".join(re.escape(s) for s in sorted(self.symbols, key=len, reverse=True))) if self.symbols else None
        spaced = rules.get("spaced", {})
        self.spaced = spaced
        self.spaced_re = re.compile(r"(?<=\s)(" + "|".join(re.escape(s) for s in sorted(spaced, key=len, reverse=True)) + r")(?=\s)") if spaced else None
        check = rules.get("check", {})
        self.flag_chars = set(check.get("characters", ""))
        # what a lexicon reads aloud is covered, so its words never come back as uncovered
        self.allowed = set(check.get("allow", [])) | {w for v in [*self.terms.values(), *self.words.values()] for w in _tokens(v)}

    # -- lexicon

    def _replace(self, m: re.Match) -> str:
        found = m.group(0)
        return self.terms.get(found) or self.words.get(found.lower(), found)

    def lexicon_text(self, text: str) -> str:
        return self.lexicon.sub(self._replace, text) if self.lexicon else text

    def lookup(self, code: str) -> str | None:
        """A lexicon's reading of a whole code span, if it has one."""
        return self.terms.get(code) or self.words.get(code.lower())

    def code(self, content: str) -> str:
        """Inline code to words: through the lexicon, as a whole span or term by term, then its identifiers by their
        parts; the rest as written."""
        plain = MARKS.sub("", content).strip()
        said = self.lookup(plain)
        if said is not None:
            return f"{KEPT[0]}{said}{KEPT[1]}"
        text = self.lexicon.sub(lambda m: f"{KEPT[0]}{self._replace(m)}{KEPT[1]}", content) if self.lexicon else content
        return self._identifiers(text)

    def _identifiers(self, text: str) -> str:
        """Dots, slashes, underscores and calls in code read as words. A lexicon reading inside the code (KEPT) is held
        as a placeholder meanwhile, so a dot or slash beside it is read too (lib.bpe.train is "lib dot B P E dot
        train"), and nothing inside it changes."""
        dot, slash = self.rules["code"]["dot"], self.rules["code"]["slash"]
        held: list[str] = []

        def hold(m: re.Match) -> str:
            held.append(m.group(0))
            return f"{KEPT[0]}{len(held) - 1}{KEPT[1]}"

        o, c = KEPT
        text = re.sub(f"{re.escape(o)}.*?{re.escape(c)}", hold, text)
        text = re.sub(rf"(?<=[\w{c}])\(\)", "", text)                        # run_tests() -> run tests
        text = re.sub(rf"(?<=[\w)\]{c}])\.(?=[A-Za-z_{o}])", f" {dot} ", text)   # lib.store -> lib dot store; v1.5 stays
        text = re.sub(rf"(?<=[\w{c}])/$", "", text)                           # examples/data/ -> examples slash data
        text = re.sub(rf"(?<=\S)/(?=\S)|^/(?=[\w{o}])", f" {slash} ", text)
        text = re.sub(r"_+", " ", text)                                         # product_text -> product text
        return re.sub(f"{re.escape(o)}(\\d+){re.escape(c)}", lambda m: held[int(m.group(1))], text)

    # -- numbers and symbols

    def _say_year(self, m: re.Match) -> str:
        n, suffix = int(m.group(1)), m.group(2)
        if not self.year_range[0] <= n <= self.year_range[1]:
            return m.group(0)
        words = year(n)
        return plural(words) if suffix == "s" else f"{words} {suffix.upper()}" if suffix else words

    def _date(self, month: int, day: int, y: int) -> str | None:
        months = self.numbers["months"]
        if not (1 <= month <= 12 and 1 <= day <= 31 and self.year_range[0] <= y <= self.year_range[1]):
            return None
        return f"{months[month - 1]} {ordinal(day)}, {year(y)}"

    def numbers_and_symbols(self, text: str) -> str:
        num = self.numbers
        point, and_ = num.get("point", "point"), self.and_

        # dates: 2026-10-01, Oct 1, 2026 and 1 October 2026
        def iso(m):
            date = self._date(int(m.group(2)), int(m.group(3)), int(m.group(1)))
            if date is None:
                return m.group(0)
            if m.group(4) is None:
                return date
            hour, minute = int(m.group(4)), int(m.group(5))
            past = "o'clock" if minute == 0 else f"oh {ONES[minute]}" if minute < 10 else _under_100(minute)
            clock = f"{cardinal(hour)} {past}"
            zone = f" {num.get('utc', 'U T C')}" if m.group(7) in ("Z", "+00:00") else ""
            return f"{date}, at {clock}{zone}"
        text = re.sub(r"(?<![\w\-.])(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2})(:\d{2}(?:\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?(?![\w\-:])",
                      iso, text)
        names = {name[:3].lower(): i for i, name in enumerate(num["months"], 1)}
        month = (r"(January|February|March|April|May|June|July|August|September|October|November|December"
                 r"|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\.?")

        def mdy(m):
            return self._date(names[m.group(1)[:3].lower()], int(m.group(2)), int(m.group(3))) or m.group(0)

        def dmy(m):
            return self._date(names[m.group(2)[:3].lower()], int(m.group(1)), int(m.group(3))) or m.group(0)
        text = re.sub(rf"\b{month} (\d{{1,2}}),? (\d{{4}})(?![\w.]\d|\d)", mdy, text)
        text = re.sub(rf"(?<![\w.])(\d{{1,2}}) {month},? (\d{{4}})(?![\w.]\d|\d)", dmy, text)

        def day_only(m):                                 # Oct 31, with no year: "October thirty-first"
            day = int(m.group(2))
            return f"{num['months'][names[m.group(1)[:3].lower()] - 1]} {ordinal(day)}" if 1 <= day <= 31 else m.group(0)
        text = re.sub(rf"\b{month} (\d{{1,2}})(?![\w.:]\d|\d|\w)", day_only, text)

        # a plus between words, as in a version's 2.11.0+cpu; scientific notation, 3.00e-03
        text = re.sub(r"(?<=\w)\+(?=[A-Za-z])", f" {self.spaced.get('+', 'plus')} ", text)
        def scientific(m):
            sign = f"{num.get('minus', 'minus')} " if m.group(2) == "-" else ""
            return f"{m.group(1)} {num.get('times_ten', 'times ten to the')} {sign}{int(m.group(3))}"
        text = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)e([-+]?)(\d+)(?![\w.])", scientific, text)

        # edition codes and versions: 2026.10.6, 3.12.15, v1.5
        def dotted(m):
            parts = [int(p) for p in m.group(m.lastindex or 0).split(".")]
            first = (year(parts[0]) if m.lastindex is None and len(str(parts[0])) == 4
                     and self.year_range[0] <= parts[0] <= self.year_range[1] else cardinal(parts[0], and_))
            said = f" {point} ".join([first] + [cardinal(p, and_) for p in parts[1:]])
            return f"{num.get('version', 'version')} {said}" if m.lastindex else said
        text = re.sub(r"(?<![\w.])\d+(?:\.\d+){2,}(?![\w]|\.\d)", dotted, text)
        text = re.sub(r"(?<![\w.])v(\d+(?:\.\d+)*)(?![\w]|\.\d)", dotted, text)

        # years, except in a value a binding filled in
        text = _outside(text, BOUND, lambda t: re.sub(r"(?<![\w.,−])(?<!\d-)(\d{4})(s|[a-f](?=[),;\]]))?(?![\w%]|[.,]\d)",
                                                      self._say_year, t))
        text = text.replace(BOUND[0], "").replace(BOUND[1], "")

        # superscripts and subscripts: 10⁻⁵, h², λ₃
        def sup(m):
            run = "".join(SUPERSCRIPT[c] for c in m.group(0))
            if run == "2":
                return f" {num.get('squared', 'squared')}"
            if run == "3":
                return f" {num.get('cubed', 'cubed')}"
            return f" {num.get('power', 'to the')} {run}"
        text = re.sub(f"[{''.join(SUPERSCRIPT)}]+", sup, text)
        text = re.sub(f"[{''.join(SUBSCRIPT)}]+", lambda m: " " + "".join(SUBSCRIPT[c] for c in m.group(0)), text)

        # signs and symbols that depend on the numbers beside them
        text = re.sub(r"(?<=\d)\s?%", f" {num.get('percent', 'percent')}", text)
        text = re.sub(r"(?<=\d)\s?×\s?(?=\d)", f" {num.get('by', 'by')} ", text)
        text = re.sub(r"(?<=\d)\s?–\s?(?=[\d−-])", f" {num.get('range', 'to')} ", text)
        text = re.sub(r"(?<![\w.)\]])[-−](?=\d)", f"{num.get('minus', 'minus')} ", text)
        text = re.sub(r"(?<![\w.)\]])\+(?=\d)", f"{num.get('plus', 'plus')} ", text)
        text = re.sub(r"(?<=[\d)])/(?=[\w(])|(?<=(?<![\w.])[A-Za-z])/(?=[\d(])", f" {num.get('over', 'over')} ", text)
        text = re.sub(r"(?<![\w.])~(?=\d)", f"{num.get('about', 'about')} ", text)
        text = re.sub(r"(?<=\d)x(?![\w])", f" {num.get('times', 'times')}", text)
        currency = num.get("currency", {})
        if currency:
            text = re.sub("(" + "|".join(map(re.escape, currency)) + r")((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?)"   # "$30," keeps its comma out
                          r"((?: thousand| million| billion)?)",
                          lambda m: f"{m.group(2)}{m.group(3)} {currency[m.group(1)]}", text)
        suffixes = num.get("suffixes", {})
        if suffixes:
            text = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)(" + "|".join(map(re.escape, suffixes)) + r")(?![\w])",
                          lambda m: f"{m.group(1)} {suffixes[m.group(2)]}", text)
        # three or more numbers split by spaced slashes are a list, as in wins / losses / ties "9 / 14 / 7"; two are a
        # division, read by the spaced rule below ("x / y" is "x over y")
        text = re.sub(r"(?<![\w.])\d[\d.,]*(?:\s/\s\d[\d.,]*){2,}(?![\w])",
                      lambda m: re.sub(r"\s/\s", ", ", m.group(0)), text)
        if self.spaced_re:
            text = self.spaced_re.sub(lambda m: self.spaced[m.group(1)], text)
        if self.symbol_re:
            text = self.symbol_re.sub(lambda m: f" {self.symbols[m.group(0)]} ", text)

        # numbers: 10th, 10s, 13,077, 0.615
        text = re.sub(r"(?<![\w.])(\d+)(st|nd|rd|th)(?!\w)", lambda m: ordinal(int(m.group(1))), text)
        text = re.sub(r"(?<![\w.])(\d+)s(?!\w)", lambda m: plural(cardinal(int(m.group(1)), and_)), text)
        text = re.sub(r"(?<![\w.])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?![\w]|\.\d)",
                      lambda m: decimal(m.group(0), point, and_), text)
        return text

    def say(self, text: str) -> str:
        """Any text as the words a voice reads: the lexicon, then dates, versions, years, symbols and numbers. A
        binding that didn't resolve stays as written, for the check to list."""
        held: list[str] = []

        def hold(m: re.Match) -> str:
            held.append(m.group(0))
            return HELD + chr(0xE100 + len(held) - 1)
        text = BINDING.sub(hold, text)
        text = re.sub(r"(^\s*|[.!?]\s+)(?=[\ue000\ue002]?[−-]?\d)", lambda m: m.group(1) + CAPITAL, text)
        text = _outside(text, KEPT, self.lexicon_text)
        text = text.replace(KEPT[0], "").replace(KEPT[1], "")
        text = self.numbers_and_symbols(text)
        text = re.sub(CAPITAL + r"\s*(\w)", lambda m: m.group(1).upper(), text).replace(CAPITAL, "")
        text = re.sub(HELD + "(.)", lambda m: held[ord(m.group(1)) - 0xE100], text)
        text = re.sub(r"\s+", " ", text).strip()
        return re.sub(r" (?=[,.;:!?)\]])|(?<=[(\[]) ", "", text)

    # -- what the rules don't cover

    def uncovered(self, text: str) -> list[str]:
        """Words in spoken text that still hold a digit, a character the check lists or a symbol, or are written in
        capitals or camelCase, and that no lexicon reads and the check doesn't allow."""
        out = []
        for word in _tokens(text):
            if word in self.allowed or "{{" in word or "}}" in word:
                continue
            if self._flagged(word, symbols_only=True):
                out.append(word)
                continue
            parts = [p for p in re.split(r"[-‐–—]", word) if p]
            flagged = [p for p in parts if p not in self.allowed and self._flagged(p)]
            out += [word] if flagged and len(flagged) == len(parts) else flagged
        return out

    def _flagged(self, word: str, symbols_only: bool = False) -> bool:
        if any(c in self.flag_chars or unicodedata.category(c) in ("Sm", "So", "Sc") for c in word):
            return True
        if symbols_only:
            return False
        return (re.fullmatch(r"[A-Z][A-Z0-9&.']*[A-Z0-9](?:s|'s|’s)?", word) is not None    # capitals: TREC, LLMs
                or re.search(r"[a-z][A-Z]|[A-Z]{2,}[a-z]{2,}", word) is not None          # camelCase: nDCG, SciPy, SQLite
                or any(c.isdigit() for c in word))


def _tokens(text: str) -> list[str]:
    """Words, split at spaces and brackets, without the punctuation around them or a possessive "'s"."""
    out = []
    for raw in re.split(r"[\s()\[\]]+", text):
        word = re.sub(r"['’]s$", "", raw.strip(".,;:!?\"'“”‘’…"))
        if word:
            out.append(word)
    return out


# ---------------------------------------------------------------- building a chapter's script


def _bind_marked(book: Book, text: str) -> str:
    """Book.bind, with each filled-in value marked, so the rules read a bound number as a count, never as a year.
    A binding that doesn't resolve stays as written."""
    def fill(m: re.Match) -> str:
        value, _ = book.binding_value(m.group(1), m.group(2))
        return m.group(0) if value is None else f"{BOUND[0]}{value}{BOUND[1]}"
    return BINDING.sub(fill, text)


def _fill(template: str, **fields) -> str:
    return template.format_map(fields)


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


@dataclass
class _Element:
    """An example, fenced block or table in a chapter, and the description that reads it, for the check."""
    kind: str                   # example, block or table
    unit: str
    line: int
    ref: str                    # the example's ID, or the block's or table's first line as written
    lang: str = ""
    entry: dict | None = None   # the narration entry that describes it


@dataclass
class _Built:
    lines: list[Line]
    elements: list[_Element]
    used: set                   # (kind, n) of the [[blocks]] and [[tables]] entries some element matched
    descriptions: list[tuple[str, str]]   # (where, the description as written), for the check's bindings
    code: dict[int, list[tuple[str, list[str]]]]   # id(Line) -> inline code in it that the rules don't cover
    written: dict[int, str]     # id(Line) -> its text before the rules read it, for the check to name a term as written


class _ChapterScript:
    def __init__(self, book: Book, chapter: Chapter, speaker: Speaker, narration: Narration, edition: str | None,
                 labels: tuple[str, ...]):
        self.book, self.chapter, self.speaker, self.edition, self.labels = book, chapter, speaker, edition, labels
        self.own = narration.chapters.get(chapter.chapter_id, {"examples": {}, "blocks": [], "tables": []})
        self.source = chapter.body.split("\n")
        self.sections = {s.line - chapter.body_offset - 1: s.section_id for s in chapter.sections}
        self.unit = chapter.chapter_id
        self.lines: list[Line] = []
        self.elements: list[_Element] = []
        self.used: set = set()
        self.descriptions: list[tuple[str, str]] = []
        self.title = ""
        self.title_code: list[tuple[str, list[str]]] = []
        self.item: dict | None = None          # the list item being read: its number and the text so far
        self.pending: list[tuple[str, list[str]]] = []   # inline code read so far that the rules don't cover
        self.code: dict[int, list[tuple[str, list[str]]]] = {}   # id(Line) -> that code, for the check
        self.written: dict[int, str] = {}

    def add(self, kind: str, text: str, line: int = 0) -> None:
        said = self.speaker.say(text)
        if said:
            self.lines.append(Line(0, kind, self.unit, said, line))
            self.written[id(self.lines[-1])] = text
            if self.pending:
                self.code[id(self.lines[-1])] = self.pending
        self.pending = []

    def where(self, tok: Token) -> int:
        return (tok.map[0] if tok.map else 0) + self.chapter.body_offset + 1

    # -- inline text

    def inline(self, tok: Token) -> str:
        out: list[str] = []
        link: list[tuple[int, Token]] = []           # open links: where their text starts, and the link
        for child in tok.children or []:
            t = child.type
            if t == "text":
                out.append(child.content)
            elif t in ("softbreak", "hardbreak"):
                out.append(" ")
            elif t == "code_inline":
                said = self.speaker.code(child.content)
                missed = self.speaker.uncovered(self.speaker.say(said))
                if missed:
                    self.pending.append((MARKS.sub("", child.content), missed))
                out.append(said)
            elif t == "image":
                out.append(self.inline(child) if child.children else child.content)
            elif t == "link_open":
                link.append((len(out), child))
            elif t == "link_close" and link:
                start, opened = link.pop()
                text = MARKS.sub("", "".join(out[start:])).strip()
                if opened.markup == "autolink" or re.match(r"(https?://|www\.)\S+$", text):
                    out[start:] = [self.speaker.templates["link_url"]]
                elif str(opened.attrGet("href") or "").startswith("#"):
                    out.insert(start, XREF_OPEN)
                    out.append(XREF_CLOSE)
        said = XREF_ONLY.sub("", "".join(out))
        return said.replace(XREF_OPEN, "").replace(XREF_CLOSE, "")

    def is_rule(self, inline: Token) -> bool:
        kids = [c for c in inline.children or [] if not (c.type == "text" and not c.content)]
        return (len(kids) >= 3 and kids[0].type == "strong_open" and kids[1].type == "text" and kids[2].type == "strong_close"
                and kids[1].content.endswith(":") and kids[1].content[:-1] in self.labels)

    # -- descriptions

    def described(self, kind: str, entry_text: str, where: str) -> str:
        self.descriptions.append((where, entry_text))
        return _bind_marked(self.book, entry_text)

    def match(self, kind: str, first: str) -> dict | None:
        first = _squash(first)
        hits = [e for e in self.own[kind] if e["section"] == self.unit and first.startswith(_squash(e["starts"]))]
        for e in hits:
            self.used.add((kind, e["n"]))
        return hits[0] if hits else None

    # -- the walk

    def flush_item(self) -> None:
        if self.item and self.item["parts"]:
            text = " ".join(p.strip() for p in self.item["parts"] if p.strip())
            if self.item["number"] is not None and not self.item["read"]:
                text = _fill(self.speaker.templates["ordered_item"], number=self.item["number"], text=text)
            self.add("item", text, self.item["line"])
            self.item["parts"], self.item["read"] = [], True

    def example(self, eid: str, tok: Token) -> None:
        name = eid.replace("-", " ")
        say = self.own["examples"].get(eid)
        self.elements.append(_Element("example", self.unit, self.where(tok), eid, entry={"say": say} if say else None))
        templates = self.speaker.templates
        if say is None:
            text = _fill(templates["fallback"]["example"], name=name)
        else:
            text = _fill(templates["example"], name=name, description=self.described("example", say, f"[examples.{eid}]"))
        self.add("example", text, self.where(tok))

    def block(self, tok: Token) -> None:
        lang = (tok.info or "").strip().split(" ")[0] if tok.type == "fence" else ""
        first_line = tok.map[0] + (1 if tok.type == "fence" else 0)
        first = self.source[first_line] if first_line < len(self.source) else ""
        entry = self.match("blocks", first)
        self.elements.append(_Element("block", self.unit, self.where(tok), first, lang, entry))
        if entry:
            text = self.described("blocks", entry["say"], f"[[blocks]] {entry['n']}")
        else:
            fallback = self.speaker.templates["fallback"]["block"]
            text = fallback.get(lang, fallback["default"])
        self.add("block", text, self.where(tok))

    def table(self, tok: Token) -> None:
        first = self.source[tok.map[0]] if tok.map else ""
        entry = self.match("tables", first)
        self.elements.append(_Element("table", self.unit, self.where(tok), first, entry=entry))
        text = (self.described("tables", entry["say"], f"[[tables]] {entry['n']}") if entry
                else self.speaker.templates["fallback"]["table"])
        self.add("table", text, self.where(tok))

    def build(self) -> _Built:
        tokens = new_markdown().parse(_bind_marked(self.book, self.chapter.body))
        lists: list[dict] = []
        quote = 0
        after_example = False
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            t = tok.type
            follows_example, after_example = after_example, False
            if t == "heading_open":
                self.flush_item()
                inline = tokens[i + 1]
                _strip_heading_id(inline)
                if tok.tag == "h1":
                    if not self.title:
                        self.title, self.title_code, self.pending = self.inline(inline), self.pending, []
                else:
                    if int(tok.tag[1]) in SECTION_LEVELS and tok.map and tok.map[0] in self.sections:
                        self.unit = self.sections[tok.map[0]]
                    text = self.inline(inline).strip()
                    self.add("heading", text if text and text[-1] in ".?!" else _fill(self.speaker.templates["heading"], text=text),
                             self.where(tok))
                i += 3
                continue
            if t == "paragraph_open":
                eid = _embed_id(tokens, i)
                if eid is not None:
                    self.flush_item()
                    self.example(eid, tok)
                    after_example = True
                    i += 3
                    continue
                inline = tokens[i + 1]
                if (follows_example and MARKS.sub("", inline.content).strip() == "Output:" and i + 3 < len(tokens)
                        and tokens[i + 3].type in ("fence", "code_block")):
                    i += 4                       # an example's output, where the text carries it: never read
                    continue
                text = self.inline(inline)
                if lists and self.item is not None:
                    self.item["parts"].append(text)
                    self.item["line"] = self.item["line"] or self.where(tok)
                elif quote:
                    self.add("quote", _fill(self.speaker.templates["quote"], text=text), self.where(tok))
                else:
                    self.add("working-rule" if self.is_rule(inline) else "prose", text, self.where(tok))
                i += 3
                continue
            if t in ("bullet_list_open", "ordered_list_open"):
                self.flush_item()
                lists.append({"ordered": t == "ordered_list_open", "next": int(tok.attrGet("start") or 1),
                              "parent": self.item})
            elif t == "list_item_open" and lists:
                current = lists[-1]
                number = current["next"] if current["ordered"] else None
                current["next"] += 1
                self.item = {"number": number, "parts": [], "read": False, "line": 0}
            elif t == "list_item_close":
                self.flush_item()
            elif t in ("bullet_list_close", "ordered_list_close") and lists:
                self.flush_item()
                self.item = lists.pop()["parent"]
            elif t == "blockquote_open":
                self.flush_item()
                quote += 1
            elif t == "blockquote_close":
                quote -= 1
            elif t in ("fence", "code_block"):
                self.flush_item()
                self.block(tok)
            elif t == "table_open":
                self.flush_item()
                self.table(tok)
                while i < len(tokens) and tokens[i].type != "table_close":
                    i += 1
            i += 1

        # the opening and the ending, from the templates
        templates, number = self.speaker.templates, self.chapter.order
        # No edition here: a chapter whose words didn't change keeps the same recording, and the same file, from edition
        # to edition. The edition is named in the whole book's credits.
        opening = [_fill(templates["opening"], number=number, title=self.title or self.chapter.title, book_title=self.book.title),
                   templates["disclosure"]]
        body, self.lines, self.unit = self.lines, [], self.chapter.chapter_id
        self.pending = self.title_code
        self.add("opening", " ".join(opening))
        self.lines += body
        self.add("ending", _fill(templates["ending"], number=number))
        for n, line in enumerate(self.lines, 1):
            line.n = n
        return _Built(self.lines, self.elements, self.used, self.descriptions, self.code, self.written)


def _working_rule_labels() -> tuple[str, ...]:
    cfg = style.load_config()["working_rule"]
    return (cfg["label"], *cfg.get("retired", []))


def _build(book: Book, chapter_id: str, edition: str | None, narration: Narration | None, rules: dict | None,
           speaker: Speaker | None = None) -> _Built:
    rules = rules or load_rules()
    narration = narration if narration is not None else load_narration(book.root)
    speaker = speaker or Speaker(rules, narration)
    return _ChapterScript(book, book.chapter(chapter_id), speaker, narration, edition, _working_rule_labels()).build()


def chapter_script(book: Book, chapter_id: str, *, edition: str | None = None, narration: Narration | None = None,
                   rules: dict | None = None) -> list[Line]:
    """The chapter's spoken script, one Line per recorded clip. The edition, an edition code such as 2026.10.6, is read
    in the opening when it's given. narration defaults to the book's narration/ folder, and rules to data/narration.toml."""
    return _build(book, chapter_id, edition, narration, rules).lines


def _credits(pieces: list, fields: dict) -> str:
    """The sentences of a credits template whose fields are all given; a list is the first choice that can be read."""
    out = []
    for piece in pieces:
        for choice in piece if isinstance(piece, list) else [piece]:
            try:
                out.append(choice.format_map(fields))
                break
            except KeyError:
                continue
    return " ".join(out)


def book_script(book: Book, *, edition: str | None = None, narration: Narration | None = None, rules: dict | None = None,
                credits: dict | None = None) -> list[Line]:
    """The whole-book file's script: opening credits, every chapter in order, closing credits. credits fills the
    templates' other fields, such as the voice's credit (voice) and where the current edition is (where)."""
    rules = rules or load_rules()
    narration = narration if narration is not None else load_narration(book.root)
    speaker = Speaker(rules, narration)
    fields = {k: v for k, v in {**(credits or {}), "title": book.title, "edition": edition}.items() if v}
    book_templates = rules["templates"]["book"]
    lines = [Line(0, "credits", book.slug, speaker.say(_credits(book_templates["opening"], fields)))]
    for c in book.chapters:
        lines += _build(book, c.chapter_id, edition, narration, rules, speaker).lines
    lines.append(Line(0, "credits", book.slug, speaker.say(_credits(book_templates["closing"], fields))))
    for n, line in enumerate(lines, 1):
        line.n = n
    return lines


def format_script(lines: list[Line]) -> str:
    """A script as a writer reads it: each Line's number, kind and unit, then its words."""
    return "\n".join(f"{line.n:>4}  {line.kind}  {line.unit}\n      {line.text}\n" for line in lines)


# ---------------------------------------------------------------- the check


def _prefix(first: str, limit: int = 40) -> str:
    """A first line's opening words, enough for `starts` to tell one block or table from another."""
    first = _squash(first)
    if len(first) <= limit:
        return first
    cut = first[:limit]
    return cut[:cut.rfind(" ")] if " " in cut else cut


def _quoted(text: str) -> str:
    """A TOML string, to paste."""
    return json.dumps(text, ensure_ascii=False)


def _as_written(speaker: Speaker, written: str, words: list[str]) -> list[str]:
    """The terms, as the text writes them, that gave these uncovered words: what a lexicon entry would match. A word
    no single term gives is named as the rules read it."""
    if not words:
        return []
    written = MARKS.sub("", written)
    found: dict[str, str] = {}
    for term in _tokens(written):
        for word in speaker.uncovered(speaker.say(term)):
            found.setdefault(word, term)
    return [w if w in written else found.get(w, w) for w in words]


def check_narration(book: Book, *, narration: Narration | None = None, rules: dict | None = None,
                    chapter_id: str | None = None) -> list[str]:
    """Warnings, per chapter: terms no rule covers; examples, blocks and tables with no description; descriptions
    whose example, section or first line no longer matches; and bindings that don't resolve. Narration never
    blocks an edition, so these are warnings."""
    rules = rules or load_rules()
    narration = narration if narration is not None else load_narration(book.root)
    speaker = Speaker(rules, narration)
    chapters = [book.chapter(chapter_id)] if chapter_id else book.chapters
    known = {c.chapter_id for c in book.chapters}
    warnings: list[str] = []
    if not chapter_id:
        warnings += narration.problems
        warnings += [f"narration/{cid}.toml: there's no chapter {cid!r} in this book" for cid in sorted(set(narration.chapters) - known)]
    else:
        warnings += [p for p in narration.problems if p.startswith((f"narration/{chapter_id}.toml", "narration/lexicon.toml"))]
    unresolved = book.binding_problems()
    for c in chapters:
        built = _build(book, c.chapter_id, None, narration, rules, speaker)
        rel = f"narration/{c.chapter_id}.toml"
        sections = {c.chapter_id} | {s.section_id for s in c.sections}

        for e in built.elements:
            if e.entry:
                continue
            if e.kind == "example":
                warnings.append(f"{c.file}:{e.line}: example {e.ref!r} has no description; add [examples.{e.ref}] say = \"…\" to {rel}")
            else:
                what = f"a {e.lang} block" if e.kind == "block" and e.lang else "a block" if e.kind == "block" else "a table"
                warnings.append(f"{c.file}:{e.line}: {what} in {e.unit!r} has no description; add [[{e.kind}s]] "
                                f"section = \"{e.unit}\", starts = {_quoted(_prefix(e.ref))}, say = \"…\" to {rel}")

        own = narration.chapters.get(c.chapter_id, {"examples": {}, "blocks": [], "tables": []})
        embedded = {e.ref for e in built.elements if e.kind == "example"}
        for eid in own["examples"]:
            if eid not in embedded:
                elsewhere = book.examples.get(eid)
                hint = (f"; it's embedded in {elsewhere.chapter_id!r}" if elsewhere and elsewhere.chapter_id
                        else "" if elsewhere else "; there's no such example")
                warnings.append(f"{rel}: [examples.{eid}]: this chapter doesn't embed {eid!r}{hint}")
        for kind in ("blocks", "tables"):
            for entry in own[kind]:
                if (kind, entry["n"]) in built.used:
                    continue
                where = f"{rel}: [[{kind}]] {entry['n']} (section {entry['section']!r}, starts {entry['starts']!r})"
                if entry["section"] not in sections:
                    warnings.append(f"{where}: there's no section {entry['section']!r} in this chapter")
                else:
                    firsts = [_squash(e.ref) for e in built.elements if e.kind == kind[:-1] and e.unit == entry["section"]]
                    now = (f"; its {kind[:-1]}s start: " + ", ".join(_quoted(f) for f in firsts) if firsts
                           else f"; the section has no {kind[:-1]}")
                    warnings.append(f"{where}: no {kind[:-1]} in the section starts so{now}")
        for where, text in built.descriptions:
            for m in BINDING.finditer(text):
                _, why = book.binding_value(m.group(1), m.group(2))
                if why:
                    warnings.append(f"{rel}: {where}: {why}")
        warnings += [p for p in unresolved if p.startswith(f"{c.file}:")]

        seen: dict[tuple, list] = {}
        for line in built.lines:
            words = speaker.uncovered(line.text)
            for code, missed in built.code.get(id(line), []):
                seen.setdefault(("code", code, ", ".join(dict.fromkeys(missed))), [line.line, 0])[1] += 1
                for word in missed:
                    if word in words:
                        words.remove(word)
            for term in _as_written(speaker, built.written.get(id(line), ""), words):
                seen.setdefault(("word", term, ""), [line.line, 0])[1] += 1
        for (what, term, missed), (first, count) in seen.items():
            times = f" ({count} times)" if count > 1 else ""
            said = f"{missed!r} in the code {term!r}" if what == "code" and missed != term else repr(term)
            warnings.append(f"{c.file}:{first}: no rule reads {said}{times}; add a reading to narration/lexicon.toml")
    return warnings
