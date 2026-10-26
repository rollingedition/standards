"""Read a book's pins with a resolver before building the examples' runtime.

When the pins can't be installed together, as when an update needs a newer version of a library that another pin
forbids, building the runtime fails with whatever the installer's last lines were. This asks a resolver first, and
reports the conflict it names in plain words:

    The pins can't be installed together: presidio-anonymizer 2.2.364 requires cryptography>=48.0.1,<49.0.0, and the
    pins say cryptography==50.0.0.

The resolver is uv, pinned exactly with this package, running `uv pip compile` for the runtime the examples run in: the
book's exact Python version, on the platform in data/examples.toml. It reads the package index's metadata and installs
nothing. Its answer is one of:

    ok              the pins install together
    unsatisfiable   they can't: the resolver's message, the conflict it names, and that conflict in words
    unavailable     the resolver couldn't run or couldn't reach the index. The runtime is then built as before, and
                    reports whatever goes wrong itself, so a resolver's own problem never fails a book's check
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from . import data_path

NO_SOLUTION = "No solution found when resolving dependencies"
NAME = r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?"
VERSION = r"[A-Za-z0-9*](?:[A-Za-z0-9.*+!_-]*[A-Za-z0-9*])?"
OP = r"(?:===|==|!=|<=|>=|~=|<|>)"
SPEC = rf"{OP}{VERSION}(?:,\s?{OP}{VERSION})*"
DEPENDS = re.compile(rf"(?<![\w.-])(?:all versions of )?(?P<a>{NAME})(?:\[[^\]]*\])?(?P<aspec>{SPEC})? depends? on "
                     rf"(?P<b>{NAME})(?:\[[^\]]*\])?(?:\{{[^}}]*\}})?(?P<bspec>{SPEC})")
NO_VERSION = re.compile(rf"there is no version of (?P<a>{NAME})(?:\[[^\]]*\])?==(?P<v>{VERSION})")
NOT_FOUND = re.compile(rf"(?<![\w.-])(?P<a>{NAME}) was not found in the (?:package registry|provided package locations)")
NO_WHEELS = re.compile(rf"(?<![\w.-])(?P<a>{NAME})==(?P<v>{VERSION}) has no (?:usable )?wheels")


def norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def settings() -> dict:
    with open(data_path("examples.toml"), "rb") as f:
        return tomllib.load(f)["resolver"]


def uv_command() -> list[str] | None:
    """uv, from PATH or beside this Python, or None when it isn't installed."""
    found = shutil.which("uv")
    if found:
        return [found]
    beside = Path(sys.executable).with_name("uv")
    return [str(beside)] if beside.exists() else None


@lru_cache(maxsize=None)
def uv_version(uv: tuple[str, ...]) -> str:
    try:
        r = subprocess.run([*uv, "--version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return "uv"
    return r.stdout.strip().split(" (")[0] or "uv"


@dataclass
class Resolution:
    outcome: str                         # ok, unsatisfiable or unavailable
    tool: str = ""
    message: str = ""                    # the resolver's own words, when it found no solution or couldn't run
    conflict: dict | None = None         # {package, version, requires, pinned}: the first conflict it names
    explanation: str = ""                # the conflict in plain words, for the check's output
    pins: dict = field(default_factory=dict)   # what it resolved to, when ok

    def as_json(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "pins"}


def the_cause(stderr: str) -> str:
    """The resolver's explanation: everything after "No solution found", without its own label, on one line per
    sentence, and its hints after it."""
    text = stderr.split(NO_SOLUTION, 1)[-1]
    lines = [re.sub(r"^\s*(cause:|╰─▶|×)\s*", "", line).rstrip() for line in text.splitlines()]
    return "\n".join(line.strip() for line in lines if line.strip())


def conflict(message: str, pins: dict[str, str], python: str) -> dict | None:
    """The first conflict the resolver's message names: a package at a version that requires a pinned library (or a
    Python) the pins don't give it. None when the message names none this can read."""
    for m in DEPENDS.finditer(message):
        a, aspec, b, bspec = m["a"], m["aspec"] or "", m["b"], m["bspec"].replace(" ", "")
        if b.lower() == "python":
            pinned, shown = python, f"Python {python}"
        elif norm(b) in pins:
            pinned, shown = pins[norm(b)], f"{b}=={pins[norm(b)]}"
        else:
            continue
        try:
            if Version(pinned) in SpecifierSet(bspec, prereleases=True):
                continue                                # this clause isn't where the pins disagree
        except (InvalidSpecifier, InvalidVersion):
            pass
        version = aspec[2:] if aspec.startswith("==") and not aspec.startswith("===") and "," not in aspec else pins.get(norm(a))
        requires = f"Python{bspec}" if b.lower() == "python" else f"{b}{bspec}"
        return {"package": a, "version": version, "requires": requires, "pinned": shown}
    return None


def explain(message: str, pins: dict[str, str], python: str) -> tuple[dict | None, str]:
    """(the conflict, the sentence the check prints)."""
    found = conflict(message, pins, python)
    if found:
        who = f"{found['package']} {found['version']}" if found["version"] else found["package"]
        if found["pinned"].startswith("Python "):
            return found, (f"The pins can't be installed together: {who} requires {found['requires']}, and the "
                           f"examples run on {found['pinned']}.")
        return found, f"The pins can't be installed together: {who} requires {found['requires']}, and the pins say {found['pinned']}."
    if m := NO_VERSION.search(message):
        return None, f"The pins can't be installed: the package index has no release {m['a']} {m['v']}."
    if m := NOT_FOUND.search(message):
        return None, f"The pins can't be installed: the package index has no package {m['a']}."
    if m := NO_WHEELS.search(message):
        return None, f"The pins can't be installed: {m['a']} {m['v']} has no files that install on Python {python} here."
    first = message.splitlines()[0] if message else "it found no solution"
    return None, f"The pins can't be installed together. The resolver says: {first}"


def check(python: str, requirements: str, pins: dict[str, str], *, uv: list[str] | None = None,
          extra_args: list[str] | None = None, env: dict | None = None) -> Resolution:
    """Whether these pins install together on Python `python`, by the resolver's reading of the package index."""
    cfg = settings()
    uv = uv or uv_command()
    if uv is None:
        return Resolution("unavailable", message="uv isn't installed, so the pins weren't read before the runtime was built")
    tool = uv_version(tuple(uv))
    cmd = [*uv, "pip", "compile", "-", "--python-version", python, "--python-platform", cfg["python_platform"],
           "--no-header", "--no-annotate", "--color", "never", *(extra_args or [])]
    run_env = dict(os.environ if env is None else env, NO_COLOR="1")
    run_env.setdefault("UV_PYTHON_DOWNLOADS", "never")       # the target Python is for reading markers; nothing runs on it
    try:
        r = subprocess.run(cmd, input=requirements, capture_output=True, text=True, env=run_env,
                           timeout=cfg["timeout_seconds"])
    except subprocess.TimeoutExpired:
        return Resolution("unavailable", tool, f"the resolver took longer than {cfg['timeout_seconds']} seconds")
    except OSError as e:
        return Resolution("unavailable", tool, f"the resolver couldn't run: {e}")
    if r.returncode == 0:
        resolved = {}
        for line in r.stdout.splitlines():
            m = re.match(rf"^({NAME})==({VERSION})", line.strip())
            if m:
                resolved[norm(m[1])] = m[2]
        return Resolution("ok", tool, pins=resolved)
    if NO_SOLUTION not in r.stderr:
        return Resolution("unavailable", tool, (r.stderr or r.stdout).strip()[-2000:])
    message = the_cause(r.stderr)
    found, sentence = explain(message, pins, python)
    return Resolution("unsatisfiable", tool, message, found, sentence)
