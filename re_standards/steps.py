"""Command steps, checks and files: the parts of a terminal book's chapters a reader runs or edits.

A step is a shell file at the top of examples/, embedded by a paragraph that is only a link to it, and its recorded
output is examples/{id}.out, as a Python example's is:

    [Step: apply-web](../examples/apply-web.sh)
    [Check: web-has-three-replicas](../examples/web-has-three-replicas.sh)
    [File: web-deployment](../examples/manifests/web-deployment.yaml)

A step's first lines may be directives, `#| name: value` (data/commands.toml, [directives]): what to wait for, which
masks its output needs, how it's compared, its tab, its time limit, and whether the file is a check, with a hint.
Copy and Run leave them out: `Step.command` is what a reader pastes. A check runs out of band, never in the reader's
terminal, and says Passed or Not yet. A file is something the steps read, such as a manifest, which a reader opens in
the editor; its ID is its name without the extension.

A chapter's front matter may name `setup`: the earlier chapters' steps that bring a fresh start to this chapter's,
so every chapter can run alone, and a reader can start anywhere.

`Book.examples` stays the Python examples alone, and a book with no step, check or file parses and renders as it
did. This module is the format; commands.py runs it.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from . import data_path

KINDS = ("step", "check", "file")
STEP_HREF = re.compile(r"^(?:\.\./)?examples/([^/]+)\.sh$")
FILE_HREF = re.compile(r"^(?:\.\./)?examples/((?:[^/]+/)*[^/]+)$")
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
CHAPTER_SCHEMA = 1                  # steps.json's, per chapter


@lru_cache(maxsize=1)
def _settings_cached(path: str, mtime: float) -> dict:
    return tomllib.loads(Path(path).read_text(encoding="utf-8"))


def settings() -> dict:
    """data/commands.toml."""
    path = data_path("commands.toml")
    return _settings_cached(str(path), path.stat().st_mtime)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Directives:
    wait: tuple[str, ...] = ()
    mask: tuple[str, ...] = ()
    compare: str = "exact"
    tab: str = "main"
    background: bool = False
    timeout: float = 120.0
    check: bool = False
    hint: str = ""
    expect_exit: int = 0

    def as_json(self) -> dict:
        return {"wait": list(self.wait), "mask": list(self.mask), "compare": self.compare, "tab": self.tab,
                "background": self.background, "timeout": self.timeout, "check": self.check, "hint": self.hint,
                "expect_exit": self.expect_exit}


@dataclass
class Step:
    """A step or a check: examples/{step_id}.sh."""
    step_id: str
    file: str                   # relative to the book root
    source: str                 # the file as written, directives included
    command: str                # without its directives: what Copy and Run paste
    sha256: str                 # of the source
    directives: Directives
    expected: str | None        # examples/{step_id}.out
    chapter_id: str | None = None
    section_id: str | None = None

    @property
    def kind(self) -> str:
        return "check" if self.directives.check else "step"


@dataclass
class FileRef:
    """A file the steps read, embedded with a File: link, such as a manifest a reader opens in the editor."""
    file_id: str
    file: str                   # relative to the book root
    text: str
    sha256: str
    chapter_id: str | None = None
    section_id: str | None = None


def label_kind(text: str) -> str | None:
    """The kind a link's text names by its label, "Step: apply-web" -> "step", or None."""
    label = text.split(":", 1)[0].strip() if ":" in text else ""
    for kind, word in settings()["format"]["labels"].items():
        if label == word:
            return kind
    return None


def embed_ref(href: str, text: str) -> tuple[str, str] | None:
    """(kind, ID) when a paragraph that is only a link embeds a step, a check or a file: a link to examples/{id}.sh, or
    a link labelled File: to a file under examples/ that isn't a Python example. None for anything else, so a Python
    book's links are never taken for one."""
    m = STEP_HREF.match(href)
    if m:
        return ("check" if label_kind(text) == "check" else "step"), m.group(1)
    m = FILE_HREF.match(href)
    if m and label_kind(text) == "file" and not href.endswith((".py", ".sh")):
        return "file", Path(m.group(1)).stem
    return None


# ---------------------------------------------------------------- directives


def split_directives(source: str) -> tuple[list[tuple[int, str, str]], str, list[str]]:
    """([(line, name, value)], the command without them, problems). Directives are the file's first lines; a `#|` line
    after the command starts is a problem, since Copy would paste it."""
    prefix = settings()["format"]["directive_prefix"]
    lines = source.replace("\r\n", "\n").split("\n")
    found: list[tuple[int, str, str]] = []
    problems: list[str] = []
    i = 0
    while i < len(lines) and lines[i].startswith(prefix):
        body = lines[i][len(prefix):].strip()
        name, sep, value = body.partition(":")
        found.append((i + 1, name.strip(), value.strip() if sep else ""))
        i += 1
    rest = lines[i:]
    for n, line in enumerate(rest, i + 1):
        if line.lstrip().startswith(prefix):
            problems.append(f"line {n}: directives go at the top of the file, before the command")
    command = "\n".join(rest).strip("\n")
    return found, command + "\n" if command else "", problems


def parse_directives(found: list[tuple[int, str, str]]) -> tuple[Directives, list[str]]:
    cfg = settings()
    kinds, defaults = cfg["directives"], cfg["defaults"]
    problems: list[str] = []
    values: dict = {}
    waits: list[str] = []
    for line, name, value in found:
        kind = kinds.get(name)
        where = f"line {line}: #| {name}"
        if kind is None:
            problems.append(f"line {line}: {name!r} isn't a directive; the directives are {', '.join(kinds)}")
            continue
        if kind == "commands":
            if not value:
                problems.append(f"{where} needs a command to poll")
            else:
                waits.append(value)
            continue
        if name in values:
            problems.append(f"{where} is given twice")
            continue
        if kind == "masks":
            names = [x.strip() for x in value.split(",") if x.strip()]
            unknown = [x for x in names if x not in cfg["masks"]]
            if unknown or not names:
                problems.append(f"{where}: {', '.join(unknown) or 'no mask'} isn't a mask; the masks are "
                                f"{', '.join(cfg['masks'])}")
            values[name] = tuple(names)
        elif kind == "choice":
            if value not in cfg["compare"]["modes"]:
                problems.append(f"{where}: {value!r} isn't one of {', '.join(cfg['compare']['modes'])}")
            values[name] = value
        elif kind == "name":
            if not NAME.match(value):
                problems.append(f"{where}: {value!r} isn't a name: lowercase letters, digits and hyphens")
            values[name] = value
        elif kind == "flag":
            if value not in ("", "true", "false"):
                problems.append(f"{where}: write it alone, or with true or false")
            values[name] = value != "false"
        elif kind == "seconds":
            try:
                seconds = float(value)
            except ValueError:
                seconds = -1
            if not 0 < seconds <= float(cfg["run"]["max_timeout_seconds"]):
                problems.append(f"{where}: {value!r} isn't a number of seconds above 0 and at most "
                                f"{cfg['run']['max_timeout_seconds']}")
            values[name] = seconds
        elif kind == "exit":
            if not value.isdigit() or not 0 <= int(value) <= 255:
                problems.append(f"{where}: {value!r} isn't an exit code, 0 to 255")
                values[name] = 0
            else:
                values[name] = int(value)
        elif kind == "text":
            if not value:
                problems.append(f"{where} needs its words")
            values[name] = value
    check = bool(values.get("check", False))
    if values.get("hint") and not check:
        problems.append("#| hint goes with #| check: only a check has a hint")
    if check and (values.get("tab") or values.get("background")):
        problems.append("a check runs out of band, never in a tab: leave out #| tab and #| background")
    if values.get("background") and values.get("compare", "none") != "none":
        problems.append("a background step runs until the chapter ends, so its output can't be compared: leave out "
                        "#| compare, or make it none")
    compare = values.get("compare") or (defaults["check_compare"] if check or values.get("background")
                                         else defaults["compare"])
    return Directives(wait=tuple(waits), mask=tuple(values.get("mask", ())), compare=compare,
                      tab=values.get("tab", defaults["tab"]), background=bool(values.get("background", False)),
                      timeout=float(values.get("timeout", defaults["timeout_seconds"])), check=check,
                      hint=values.get("hint", ""), expect_exit=int(values.get("expect-exit", 0))), problems


def parse_step(text: str, step_id: str, rel: str, expected: str | None = None) -> tuple[Step, list[str]]:
    """A step or a check from its file's text; its problems are reported as `rel`'s."""
    source = text.replace("\r\n", "\n")
    found, command, problems = split_directives(source)
    directives, more = parse_directives(found)
    problems += more
    if not command.strip():
        problems.append("there's no command after the directives")
    sleep = re.compile(settings()["rules"]["sleep"])
    for n, line in enumerate(command.split("\n"), len(found) + 1):
        if not line.lstrip().startswith("#") and sleep.search(line):
            problems.append(f"line {n}: waits, never sleep: poll for what it waits for with #| wait: COMMAND")
    for w in directives.wait:
        if sleep.search(w):
            problems.append(f"#| wait: {w}: a wait polls; it never sleeps")
    problems += rule_problems(command, directives, len(found) + 1)
    for w in directives.wait:
        problems += [f"#| wait: {w}: {p.split(': ', 1)[1]}" for p in rule_problems(w + "\n", Directives(), 0)
                     if "W-70" not in p]
    step = Step(step_id, rel, source, command, sha256_text(source), directives, expected)
    return step, [f"{rel}: {p}" for p in problems]


def _local(host: str) -> bool:
    """Whether a URL's host is this machine or the cluster: W-74 allows nothing else."""
    rules = settings()["rules"]
    host = host.lower().strip("[]")
    if host in [h.strip("[]") for h in rules["local_hosts"]] or host.endswith(tuple(rules["local_suffixes"])):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or any(ip in ipaddress.ip_network(n) for n in rules["local_networks"])


def rule_problems(command: str, d: Directives, first_line: int) -> list[str]:
    """What a step's command breaks of the writing standards' section 15, line by line (data/commands.toml [rules]):
    W-70, what prints differently every run without its mask; W-74, a download or an address beyond this machine and
    the cluster; W-76, what bash 3.2 can't run."""
    rules = settings()["rules"]
    random, clock, job = (re.compile(rules[k]) for k in ("random", "clock", "job"))
    fetches, url = re.compile(rules["fetches"]), re.compile(rules["url"])
    bash32 = [(what, re.compile(rx)) for what, rx in rules["bash32"].items()]
    out = []
    for n, line in enumerate(command.split("\n"), first_line):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"line {n}" if first_line else "it"
        if random.search(line):
            out.append(f"{where}: W-70: $RANDOM, uuidgen and /dev/urandom print something new every run: name it yourself")
        compared = d.compare != "none" and not d.background
        if clock.search(line) and compared and "time" not in d.mask:
            out.append(f"{where}: W-70: date prints the time, which changes every run: add #| mask: time, or leave it out")
        if job.search(line) and compared and "job" not in d.mask:
            out.append(f"{where}: W-70: a job started with & prints its process ID, which changes every run: add "
                       "#| mask: job, or run it in a tab of its own with #| tab and #| background")
        if m := fetches.search(line):
            out.append(f"{where}: W-74: {m.group(0)} downloads from beyond the cluster: pin what it fetches in "
                       "examples/stack.in.toml, or ship it in examples/")
        for m in url.finditer(line):
            if not _local(m.group(1)):
                out.append(f"{where}: W-74: {m.group(1)} is beyond this machine and the cluster, which nothing in a Lab "
                           "can reach")
        for what, rx in bash32:
            if rx.search(line):
                out.append(f"{where}: W-76: bash 3.2, which readers' Macs run the local lab with, has no {what}")
    return out


def load_steps(root: Path, valid_id) -> tuple[dict[str, Step], list[str]]:
    """Every examples/*.sh in a book checkout, by ID, and their problems."""
    out: dict[str, Step] = {}
    problems: list[str] = []
    ex = Path(root) / "examples"
    for path in sorted(ex.glob("*.sh")) if ex.is_dir() else []:
        rel = path.relative_to(root).as_posix()
        if not valid_id(path.stem):
            problems.append(f"{rel}: step file names are their IDs: lowercase words joined by hyphens")
            continue
        out_file = path.with_suffix(".out")
        expected = out_file.read_text(encoding="utf-8").replace("\r\n", "\n") if out_file.exists() else None
        step, found = parse_step(path.read_text(encoding="utf-8"), path.stem, rel, expected)
        out[path.stem] = step
        problems += found
    return out, problems


def load_file(root: Path, href: str, file_id: str) -> tuple[FileRef | None, str | None]:
    m = FILE_HREF.match(href)
    rel = f"examples/{m.group(1)}" if m else href
    path = Path(root) / rel
    if not m or ".." in Path(rel).parts or not path.is_file():
        return None, f"embeds {rel}, which doesn't exist"
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return FileRef(file_id, rel, text, sha256_text(text)), None


# ---------------------------------------------------------------- output: masks and comparison


def mask(text: str, names: tuple[str, ...] | list[str]) -> str:
    """The text with each named mask's matches replaced, and, after any mask, runs of spaces as one."""
    cfg = settings()
    for name in names:
        m = cfg["masks"][name]
        text = re.sub(m["pattern"], m["replace"], text)
    if names and cfg["compare"]["collapse_spaces"]:
        text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def normalize(text: str) -> str:
    """Output as it's recorded and compared: newlines as \\n, trailing spaces and trailing blank lines gone."""
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def compare(expected: str | None, actual: str, how: str, masks: tuple[str, ...] = ()) -> tuple[bool, str]:
    """(same, diff): `exact`, every line after masks; `lines`, the expected lines in order among the actual ones;
    `none`, always the same."""
    import difflib
    if how == "none":
        return True, ""
    if expected is None:
        return False, "no recorded output"
    a, b = mask(normalize(expected), masks), mask(normalize(actual), masks)
    if how == "lines":
        want, got = [x for x in a.splitlines() if x.strip()], iter(b.splitlines())
        missing = [line for line in want if not any(line == g for g in got)]
        return (not missing), ("" if not missing else "expected, in this order, and not found:\n" +
                               "\n".join(f"  {line}" for line in missing))
    if a == b:
        return True, ""
    return False, "\n".join(difflib.unified_diff(a.splitlines(), b.splitlines(), "recorded", "this run", lineterm=""))


# ---------------------------------------------------------------- what the Lab and the page read


def chapter_view(book, chapter) -> dict:
    """A chapter's steps.json: its setup, then each step, check and file in reading order, with what the Lab and the
    free page need of it, and the hash of everything that decides its run (inputs_sha256), so a chapter runs again
    only when one of them changes."""
    items = []
    for e in chapter.step_embeds:
        if e.kind == "file":
            f = book.files.get(e.example_id)
            if f:
                items.append({"kind": "file", "id": f.file_id, "section": e.section_id, "file": f.file,
                              "sha256": f.sha256})
            continue
        s = book.steps.get(e.example_id)
        if s:
            items.append({"kind": s.kind, "id": s.step_id, "section": e.section_id, "file": s.file,
                          "command": s.command, "directives": s.directives.as_json(), "expected": s.expected,
                          "sha256": s.sha256})
    setup = [{"id": sid, "file": book.steps[sid].file, "command": book.steps[sid].command,
              "directives": book.steps[sid].directives.as_json(), "sha256": book.steps[sid].sha256}
             for sid in chapter.setup if sid in book.steps]
    inputs = json.dumps({"setup": [(x["id"], x["sha256"]) for x in setup],
                         "items": [(x["id"], x["sha256"]) for x in items]}, sort_keys=True)
    return {"schema": CHAPTER_SCHEMA, "book": book.slug, "chapter": chapter.chapter_id, "setup": setup,
            "items": items, "inputs_sha256": sha256_text(inputs)}


def steps_json(book) -> dict[str, dict]:
    """Every chapter with a step, check or file: its chapter_view, by chapter ID. Empty for a Python book."""
    return {c.chapter_id: chapter_view(book, c) for c in book.chapters if c.step_embeds}
