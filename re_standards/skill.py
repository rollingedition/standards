"""`re-check skill`: skill.md, the agent skill a book ships with every edition (writing standards W-57 to W-59).

A book's agent skill is the book in the open Agent Skills format: a folder with a SKILL.md that a coding agent loads
and follows, its chapters as references and its examples as scripts. Every part but two is built from the edition:
the stamp, the pins, the chapters and the examples. The two parts written by hand, by the agents who write the book,
live in skill.md beside book.toml:

- **Front matter:** one field, `description`: what the book teaches and when a coding agent should use it.
- **Body:** the procedures, one `##` heading each. Every step cites the section it comes from as a link to the
  section's ID, `[BM25 from scratch](#bm25-from-scratch)`, and every script as a link to its example,
  `[the example](examples/bm25-from-scratch.py)`. Versions and printed values are bound as in the chapters
  (`{{version:…}}`, `{{out:…}}`).

The check keeps the procedures to what the book teaches, within the format's limits, and free of anything that would
act on someone's agent beyond them: the only links are the book's own sections and examples, rollingedition.com and
.ai, and sources the chapters themselves cite. `re-check addressed` reads skill.md as it reads a chapter.
Limits and the statuses that must have one are [skill] in data/writing.toml.

Readers' agents run a skill on macOS, Linux and Windows (W-81), so the check reads its commands, never its output, for
what one system or one machine has: a path on one machine, `sudo` and an install only one system has fail; what a
Windows shell lacks, such as `source .venv/bin/activate`, `export` or a line continued with `\\`, is listed to read
again, unless its procedure gives the Windows form too. The rules are [skill.os] in data/writing.toml.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from . import style
from .bookfmt import BINDING, Book, split_front_matter

FILE = "skill.md"
LINK = re.compile(r"(?<!!)\[([^\]\n]+)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
URL = re.compile(r"https?://[^\s)<>\"'`]+")
EXAMPLE = re.compile(r"^(?:\.\./)?examples/([a-z0-9]+(?:-[a-z0-9]+)*)\.py$")
FENCE = re.compile(r"^(```+|~~~+)")
WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


@dataclass
class Skill:
    description: str
    body: str
    offset: int                 # lines before the body, for reporting line numbers
    front: dict


def settings(cfg: dict | None = None) -> dict:
    return (cfg or style.load_config())["skill"]


def read(root: Path) -> tuple[Skill | None, list[str]]:
    """The book's skill.md, or None when it has none; with problems that stop it being read."""
    path = Path(root) / FILE
    if not path.is_file():
        return None, []
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    front, body, offset, error = split_front_matter(text)
    if error and error.startswith("missing front matter"):
        return None, [f"{FILE}: start with front matter holding the description, between --- lines"]
    if error:
        return None, [f"{FILE}: {error}"]
    front = front or {}
    return Skill(str(front.get("description") or "").strip(), body, offset, front), []


def _lines_outside_code(body: str, offset: int) -> list[tuple[int, str]]:
    out, fence = [], None
    for n, line in enumerate(body.split("\n"), offset + 1):
        m = FENCE.match(line.strip())
        if m:
            fence = None if fence and line.strip().startswith(fence) else (fence or m.group(1))
            continue
        if fence is None:
            out.append((n, line))
    return out


def _cited_urls(book: Book) -> set[str]:
    """Every URL the chapters cite, without a trailing slash or punctuation."""
    return {u.rstrip(".,;:/") for c in book.chapters for u in URL.findall(c.body)}


def section_of(book: Book) -> dict[str, str]:
    """Each live chapter and section ID, with the chapter it belongs to."""
    ids = {}
    for c in book.chapters:
        ids[c.chapter_id] = c.chapter_id
        for s in c.sections:
            ids[s.section_id] = c.chapter_id
    return ids


def check(book: Book, cfg: dict | None = None) -> tuple[list[str], list[str]]:
    """(problems, notes) for the book's skill.md."""
    conf = cfg or style.load_config()
    rules = settings(conf)
    skill, problems = read(book.root)
    status = book.manifest.get("status", "draft")
    if problems:
        return problems, []
    if skill is None:
        if status in rules["required_for"]:
            return [f"{FILE} is missing: every book ships an agent skill, its procedures written beside book.toml (W-57)"], []
        return [], [f"{FILE} is missing: this book has no agent skill yet (W-57)"]

    extra = sorted(set(skill.front) - {"description"})
    if extra:
        problems.append(f"{FILE}: the front matter holds only `description`; the release writes the rest ({', '.join(extra)})")
    if not skill.description:
        problems.append(f"{FILE}: W-58: write a `description`: what the book teaches and when an agent should use it")
    elif len(skill.description) > rules["description_max"]:
        problems.append(f"{FILE}: W-58: the description has {len(skill.description)} characters; the format allows "
                        f"{rules['description_max']}")

    prose = _lines_outside_code(skill.body, skill.offset)
    lines = [ln for ln in skill.body.split("\n") if ln.strip()]
    if len(lines) > rules["max_lines"]:
        problems.append(f"{FILE}: W-58: {len(lines)} lines of procedures; keep them to {rules['max_lines']}, so the whole "
                        "SKILL.md stays inside the format's 500")
    words = sum(len(WORD.findall(t)) for _, t in prose)
    if words > rules["max_words"]:
        problems.append(f"{FILE}: W-58: {words:,} words of procedures; keep them to {rules['max_words']:,}, so an agent "
                        "loads it whole")

    live = section_of(book)
    cited = _cited_urls(book)
    hosts = set(rules["link_hosts"])
    procedures: list[tuple[int, str, int]] = []         # (line, title, citations)
    for n, line in prose:
        if line.startswith("# "):
            problems.append(f"{FILE}:{n}: the release writes the title; start each procedure with `## `")
        if line.startswith("## "):
            procedures.append((n, line[3:].strip(), 0))
        for m in LINK.finditer(line):
            target = m.group(2)
            if target.startswith("#"):
                ref = target[1:]
                if ref in live:
                    if procedures:
                        n0, title, k = procedures[-1]
                        procedures[-1] = (n0, title, k + 1)
                elif book.resolve(ref):
                    problems.append(f"{FILE}:{n}: W-57: #{ref} is retired; cite #{book.resolve(ref)}")
                else:
                    problems.append(f"{FILE}:{n}: W-57: there is no section #{ref} in this book")
            elif EXAMPLE.match(target):
                if EXAMPLE.match(target).group(1) not in book.examples:
                    problems.append(f"{FILE}:{n}: W-57: there is no example {target}")
            elif target.startswith(("https://", "http://")):
                host = (urlsplit(target).hostname or "").removeprefix("www.")
                if host not in hosts and target.rstrip(".,;:/") not in cited:
                    problems.append(f"{FILE}:{n}: W-59: {target} isn't ours or a source the chapters cite; an agent "
                                    "follows every link here")
            else:
                problems.append(f"{FILE}:{n}: W-59: link only to the book's sections (#id), its examples "
                                f"(examples/ID.py) and full URLs, not {target!r}")
        for m in BINDING.finditer(line):
            _, why = book.binding_value(m.group(1), m.group(2))
            if why:
                problems.append(f"{FILE}:{n}: {why}")

    if len(procedures) < rules["min_procedures"]:
        problems.append(f"{FILE}: W-57: no procedures; give each method the book teaches a `## ` heading")
    for n, title, k in procedures:
        if not k:
            problems.append(f"{FILE}:{n}: W-57: \"{title}\" cites no section; every step comes from one, linked by its ID")

    names = {name: [name] + conf["words"].get("aliases", {}).get(name, []) for name in book.pins}
    typed = [(name, re.compile(r"(?<![A-Za-z0-9\-])" + re.escape(alias) + r"(?:\s+version)?\s*(?:==\s*)?"
                               + style.VERSION_NUMBER, re.IGNORECASE))
             for name, aliases in names.items() for alias in aliases]
    for n, line in prose:
        text = BINDING.sub("", re.sub(r"`[^`]*`", "", line))
        for name, rx in typed:
            if rx.search(text):
                problems.append(f"{FILE}:{n}: W-25: a typed version of {name}; write {{{{version:{name}}}}}")
    failing, notes = os_assumptions(skill.body, skill.offset, rules.get("os"))
    return problems + failing, notes


HEADING = re.compile(r"^#{1,6}\s")
SPAN = re.compile(r"(`+)(.+?)\1")
SHELL_COMMENT = re.compile(r"(?:^|\s)#.*$")


@dataclass
class _Procedure:
    text: list[str]                         # every line under its heading, output included, for `unless`
    read: list[tuple[int, str, str]]        # (line, what a rule reads, its kind: shell, inline, windows or code)
    windows: bool = False                   # it has a Windows block: its Windows form


def _os_procedures(body: str, offset: int, conf: dict) -> list[_Procedure]:
    """skill.md as W-81 reads it: everything under each heading, with the commands, inline code and code its rules read.
    A procedure is the unit, since it often gives each system's form in a step or a block of its own. Output is never
    read."""
    shells, sessions, windows, output = (set(conf[k]) for k in ("shells", "sessions", "windows", "output"))
    prompt = re.compile(conf["prompt"])
    procs, fence, lang = [_Procedure([], [])], None, ""
    for n, line in enumerate(body.split("\n"), offset + 1):
        stripped = line.strip()
        m = FENCE.match(stripped)
        if fence is None and m:                         # a block opens: known by its info string's first word
            fence = m.group(1)
            lang = (stripped[len(fence):].strip().split() or [""])[0].strip("{}.").lower()
            procs[-1].windows |= lang in windows
            procs[-1].text.append(line)
            continue
        if fence is not None:
            if stripped.startswith(fence):
                fence = None
            elif lang in shells:
                command = SHELL_COMMENT.sub("", stripped).rstrip()
                if command:
                    procs[-1].read.append((n, command, "shell"))
            elif lang in sessions:
                if p := prompt.match(stripped):
                    procs[-1].read.append((n, SHELL_COMMENT.sub("", stripped[p.end():]).rstrip(), "shell"))
            elif lang in windows:
                procs[-1].read.append((n, stripped, "windows"))
            elif lang and lang not in output:
                procs[-1].read.append((n, stripped, "code"))
            procs[-1].text.append(line)
            continue
        if HEADING.match(line):
            procs.append(_Procedure([], []))
        procs[-1].text.append(line)
        procs[-1].read += [(n, s.group(2).strip(), "inline") for s in SPAN.finditer(line)]
    return [p for p in procs if p.text]


def os_assumptions(body: str, offset: int = 0, conf: dict | None = None,
                   file: str = FILE) -> tuple[list[str], list[str]]:
    """W-81: what in a skill's commands only one system or one machine has, as (problems, notes). Problems fail the
    check: a path on one machine, sudo, an install only one system has. Notes are what a Windows shell lacks, listed to
    read again. A procedure that gives the other systems' form, as a rule's `unless` or a Windows block says, passes.
    `conf` is [skill.os] in data/writing.toml; `file` names the file in each line found."""
    conf = conf if conf is not None else settings().get("os")
    if not conf:
        return [], []
    found: dict[str, list[tuple[int, int, str]]] = {"fail": [], "warn": []}
    rules = [(i, r, re.compile(r["pattern"].replace("{cmd}", conf["cmd"])),
              [re.compile(u) for u in r.get("unless", [])]) for i, r in enumerate(conf.get("rules", []))]
    installs = conf.get("installs")
    if installs:
        families = installs["families"]
        manager = {m: family for family, f in families.items() for m in f["managers"]}
        managers = "|".join(map(re.escape, sorted(manager, key=len, reverse=True)))     # apt-get before apt
        install = re.compile(r"(?<![\w./-])(?P<manager>" + managers + r")\s+" + installs["verbs"])
        anywhere = re.compile(installs["anywhere"])
        named = {family: [re.compile(x) for x in f["names"]]
                 + [re.compile(r"(?<![\w./-])" + re.escape(m) + r"(?![\w-])") for m in f["managers"]]
                 for family, f in families.items()}
    for proc in _os_procedures(body, offset, conf):
        text = "\n".join(proc.text)
        for i, rule, rx, unless in rules:
            if (rule.get("windows_form") and proc.windows) or any(u.search(text) for u in unless):
                continue
            seen = set()
            for n, what, kind in proc.read:
                if kind not in rule.get("in", ["shell", "inline"]) or n in seen or not (m := rx.search(what)):
                    continue
                seen.add(n)
                shown = (m.groupdict().get("found") or m.group(0)).strip()
                found[rule["level"]].append((n, i, rule["message"].replace("{found}", shown)))
        if not installs:
            continue
        for n, what, kind in proc.read:
            if kind not in installs["in"] or not (m := install.search(what)):
                continue
            family = manager[m.group("manager")]
            missing = [f for f in families if f != family and not any(x.search(text) for x in named[f])]
            if missing and not anywhere.search(text):
                message = (installs["message"].replace("{found}", m.group(0).strip()).replace("{family}", family)
                           .replace("{missing}", " or ".join(missing)))
                found[installs["level"]].append((n, len(rules), message))
    lines = {level: [f"{file}:{n}: W-81: {message}" for n, _, message in sorted(hits)] for level, hits in found.items()}
    return lines["fail"], lines["warn"]


def body_for_agents(book: Book, skill: Skill, reference: str = "references/{chapter}.md",
                    script="scripts/{example}.py") -> str:
    """The procedures as SKILL.md carries them: each section link pointed at its chapter's reference file, each
    example at its script, and every binding filled in from the pins and the recorded outputs. `reference` and `script`
    are templates, or functions (of the chapter and unit IDs, and of the example's ID) for a skill that carries neither
    and links to the book's pages instead."""
    live = section_of(book)
    to_script = script if callable(script) else (lambda example: script.format(example=example))
    to_ref = reference if callable(reference) else (lambda chapter, unit: f"{reference.format(chapter=chapter)}#{unit}")

    def link(m: re.Match) -> str:
        text, target = m.group(1), m.group(2)
        if target.startswith("#") and target[1:] in live:
            return f"[{text}]({to_ref(live[target[1:]], target[1:])})"
        ex = EXAMPLE.match(target)
        if ex:
            return f"[{text}]({to_script(ex.group(1))})"
        return m.group(0)

    out, fence = [], None
    for line in skill.body.split("\n"):
        f = FENCE.match(line.strip())
        if f:
            fence = None if fence and line.strip().startswith(fence) else (fence or f.group(1))
        out.append(line if fence or f else LINK.sub(link, line))
    return book.bind("\n".join(out)).strip("\n") + "\n"
