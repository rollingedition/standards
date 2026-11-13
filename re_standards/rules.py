"""Rules with dates: a new rule warns on a released book until its next content edition, instead of failing its checks.

A rule of the checks that is listed in data/rules.toml took effect on a day, its `since`. It holds:

- a draft (book.toml's status is draft, or there's no book.toml) from the start, as every rule does;
- a change that alters the book's text or examples (a file in data/rules.toml's `content` classes of
  review-tiers.toml), since that change makes the book's next content edition, and every edition keeps every rule;
- a released book whose text or examples last changed after `since`, so every pull request after that edition.

Anywhere else, a problem it finds is a warning: the pull request merges, and the book takes the rule with its next
content edition, by the same agents and in the same change that make that edition. So a rule that a released book's
text doesn't meet yet never stops its dependency updates or a fix to something else, and nobody has to rework every
book on the day the rule arrives.

When the book's text last changed comes from its own history: the newest commit on the line checked (the pull
request's base, else HEAD), first parent only, so a merge counts once, that changed a content file. The commit that
starts a repository isn't read, since a working copy made from a tarball has one commit holding everything; a book
with no other content commit is taken as not changed since. A rule that isn't listed holds every book, whatever its
history. Problems name their rule first, as "W-61: ...".
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from . import data_path

RULE = re.compile(r"\b[A-Z]{1,3}-\d+(?=:)")         # the rule a problem names first, as "W-61: ..."
DRAFT = "draft"


def load(path: Path | None = None) -> dict:
    with open(path or data_path("rules.toml"), "rb") as f:
        return tomllib.load(f)


def rule_of(problem: str) -> str | None:
    m = RULE.search(problem)
    return m.group() if m else None


def dated(cfg: dict | None = None) -> dict[str, dt.date]:
    """Each listed rule's day, from [rules]."""
    cfg = cfg if cfg is not None else load()
    return {rid: dt.date.fromisoformat(str(entry["since"])) for rid, entry in (cfg.get("rules") or {}).items()}


def content_patterns(cfg: dict | None = None) -> list[str]:
    """The file patterns whose change is a change to the book's text or examples: review-tiers.toml's [files] classes
    that data/rules.toml's `content` names."""
    cfg = cfg if cfg is not None else load()
    with open(data_path("review-tiers.toml"), "rb") as f:
        files = tomllib.load(f)["files"]
    return [p for cls in cfg["content"] for p in files[cls]]


def is_content(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, p) for p in patterns)


@dataclass
class Standing:
    """Where a book stands for the dated rules."""
    released: bool                        # it has an edition: book.toml says live, unmaintained or retired
    content_change: bool = False          # the change checked alters its text or examples, so it makes the next edition
    content_on: dt.date | None = None     # the day its text or examples last changed on the line checked, if known
    notes: list[str] = field(default_factory=list)

    def holds(self, since: dt.date) -> bool:
        """Whether a rule that took effect on `since` holds this book now."""
        if not self.released or self.content_change:
            return True
        return self.content_on is not None and self.content_on > since

    def why_not(self, since: dt.date) -> str:
        last = (f"its text and examples last changed on {self.content_on:%b} {self.content_on.day}, "
                f"{self.content_on.year}") if self.content_on else "its history doesn't say when its text last changed"
        return (f"a rule since {since:%b} {since.day}, {since.year}, and {last}: it holds this book from its next "
                "content edition")


def _git(root: Path, *args: str) -> str | None:
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def changed_paths(root: Path, base_ref: str | None = None) -> list[str] | None:
    """What the change being checked touches: the files that differ from `base_ref` (a pull request's base), or with
    none from HEAD, in the working tree, untracked files included. None when git can't say."""
    if _git(root, "rev-parse", "--is-inside-work-tree") is None:
        return None
    diff = _git(root, "diff", "--name-only", "--no-renames", base_ref or "HEAD", "--")
    if diff is None:
        return None
    untracked = _git(root, "ls-files", "--others", "--exclude-standard") or ""
    return sorted({line for line in (diff + untracked).splitlines() if line.strip()})


def last_content_change(root: Path, ref: str, patterns: list[str]) -> dt.date | None:
    """The UTC day of the newest first-parent commit at `ref` that changed a content file, its root commit aside."""
    out = _git(root, "log", "--first-parent", "--diff-merges=first-parent", "--name-only", "--no-renames",
               "--format=%x00%P%x09%cI", ref, "--")
    if out is None:
        return None
    for record in out.split("\0")[1:]:
        head, _, names = record.partition("\n")
        parents, _, when = head.partition("\t")
        if not parents.strip():
            continue                      # the root commit: a tarball copy's only commit, or a book's first edition
        if any(is_content(n.strip(), patterns) for n in names.splitlines() if n.strip()):
            return dt.datetime.fromisoformat(when.strip()).astimezone(dt.timezone.utc).date()
    return None


def standing(root: Path, manifest: dict | None, base_ref: str | None = None, cfg: dict | None = None) -> Standing:
    """How the dated rules hold the book at `root`: a draft keeps them all; a released book from its next content
    edition, which a change to its text or examples makes."""
    status = (manifest or {}).get("status", DRAFT)
    if status == DRAFT:
        return Standing(released=False)
    cfg = cfg if cfg is not None else load()
    patterns = content_patterns(cfg)
    found = Standing(released=True)
    changed = changed_paths(root, base_ref)
    if changed is None:
        found.notes.append("git can't say what this change touches, so it's taken as no change to the text or examples")
    else:
        found.content_change = any(is_content(p, patterns) for p in changed)
    if not found.content_change:
        found.content_on = last_content_change(root, base_ref or "HEAD", patterns)
    return found


def split(problems: list[str], root: Path, manifest: dict | None, base_ref: str | None = None,
          cfg: dict | None = None) -> tuple[list[str], list[str]]:
    """(failures, warnings): a problem whose rule holds the book fails; one whose dated rule doesn't hold it yet is a
    warning, saying why. Git is read only when a problem names a dated rule."""
    cfg = cfg if cfg is not None else load()
    days = dated(cfg)
    if not any(rule_of(p) in days for p in problems):
        return list(problems), []
    where = standing(root, manifest, base_ref, cfg)
    failures, warnings = [], []
    for p in problems:
        since = days.get(rule_of(p) or "")
        if since is None or where.holds(since):
            failures.append(p)
        else:
            warnings.append(f"{p} ({where.why_not(since)})")
    if warnings:
        warnings += where.notes
    return failures, warnings
