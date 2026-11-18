"""Authored books: the authors book.toml names, and how much of a change waits for them.

A house book names no authors: Rolling Edition drafts it, is its author and publishes it, and nothing here applies to
it. An authored book names its authors in book.toml, and its [authorship] table says the level of its gate and where
the book stands:

    [[authors]]                     # empty or absent: a house book
    name = "Jane Doe"
    given = "Jane"
    family = "Doe"                  # or literal = "jdoe", a name used as it is
    github = "janedoe"
    github_id = 1234567             # numeric: what the gate and the credit check, since a login can change
    role = "lead"                   # lead | author; exactly one lead
    chapters = ["ch-ingest"]        # the chapters this author owns; empty means they share the rest
    interests = "Maintains polars." # disclosed on the book page

    [authorship]
    gate = "meaning"                # meaning | standard | all: which changes wait for an author
    state = "active"                # adopting | active | returned

The levels, who approves and what's always automatic are data/review-tiers.toml's [authors]. Each author keeps their
copyright, and the text and the code keep the licences every book has (data/readme.toml's [licences]). Standard
library only.
"""
from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from functools import cache

from . import cover, data_path

GITHUB_LOGIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}$")
FIELDS = {"name", "given", "family", "literal", "github", "github_id", "role", "chapters", "interests"}
LEAD = "lead"


class AuthorshipError(ValueError):
    pass


@cache
def settings() -> dict:
    """data/review-tiers.toml's [authors]: the gate's levels, states, roles and what only the lead approves."""
    with open(data_path("review-tiers.toml"), "rb") as f:
        return tomllib.load(f)["authors"]


@dataclass(frozen=True)
class BookAuthor:
    """One author as book.toml names them."""
    name: str
    github: str
    github_id: int
    role: str = "author"
    given: str = ""
    family: str = ""
    literal: str = ""
    chapters: tuple[str, ...] = ()
    interests: str = ""

    @property
    def lead(self) -> bool:
        return self.role == LEAD

    def record(self) -> dict:
        """What an edition's release record keeps of the author: their name as it's credited, and their GitHub account."""
        out = {"name": self.name, "github": self.github, "github_id": self.github_id, "role": self.role}
        if self.literal:
            out["literal"] = self.literal
        else:
            out.update(given=self.given, family=self.family)
        return out


def is_authored(manifest: dict) -> bool:
    """Whether book.toml names any authors. An `authors` key that doesn't validate still counts, so a gate that can't
    read it waits rather than letting everything through."""
    return bool(manifest.get("authors"))


def authors(manifest: dict) -> list[BookAuthor]:
    """The book's authors, in book.toml's order; none for a house book. Raises AuthorshipError when they don't
    validate (problems says what's wrong)."""
    if not is_authored(manifest):
        return []
    found = problems(manifest)
    if found:
        raise AuthorshipError("; ".join(found))
    return [BookAuthor(name=a["name"].strip(), github=a["github"], github_id=a["github_id"], role=a.get("role", "author"),
                       given=a.get("given", ""), family=a.get("family", ""), literal=a.get("literal", ""),
                       chapters=tuple(a.get("chapters") or ()), interests=a.get("interests", "").strip())
            for a in manifest["authors"]]


def state(manifest: dict) -> str | None:
    """Where an authored book stands: adopting, active or returned. None for a house book."""
    return (manifest.get("authorship") or {}).get("state") if is_authored(manifest) else None


def gate(manifest: dict) -> str:
    """The gate's level: [authorship] gate, or the default."""
    return (manifest.get("authorship") or {}).get("gate") or settings()["default"]


def credited(manifest: dict) -> list[BookAuthor]:
    """The authors an edition credits: an active or returned book's. A book still being adopted keeps Rolling Edition's
    byline until its author has verified it and it's active."""
    return authors(manifest) if state(manifest) in ("active", "returned") else []


def names_and(names: list[str], word: str = "and") -> str:
    """"Jane Doe", "Jane Doe and Sam Lee", "Jane Doe, Sam Lee and Priya Rao"; with `word`, "Jane Doe or Sam Lee"."""
    if len(names) < 2:
        return "".join(names)
    return f"{', '.join(names[:-1])} {word} {names[-1]}"


def problems(manifest: dict) -> list[str]:
    """Problems with book.toml's [[authors]] and [authorship], in words. None for a house book."""
    who = manifest.get("slug", "?")
    raw, table = manifest.get("authors"), manifest.get("authorship")
    if not raw:
        return [f"{who}: [authorship] is only for a book that names its authors in [[authors]]"] if table is not None else []
    if not isinstance(raw, list) or not all(isinstance(a, dict) for a in raw):
        return [f"{who}: authors are [[authors]] tables, each with a name, github and github_id"]
    cfg, errs = settings(), []
    for i, a in enumerate(raw, 1):
        label = f"{who}: author {i}"
        name = a.get("name")
        if not isinstance(name, str) or not name.strip():
            errs.append(f"{label} needs a name, as it's credited")
        else:
            label = f"{who}: {name.strip()}"
        unknown = sorted(set(a) - FIELDS)
        if unknown:
            errs.append(f"{label}: unknown field(s) {', '.join(unknown)}")
        literal, given, family = a.get("literal"), a.get("given"), a.get("family")
        if literal is not None and (given is not None or family is not None):
            errs.append(f"{label}: give either literal, a name used as it is, or given and family, not both")
        elif literal is not None:
            if not (isinstance(literal, str) and literal.strip()):
                errs.append(f"{label}: literal is the name used as it is")
        elif not (isinstance(family, str) and family.strip()) or (given is not None and not isinstance(given, str)):
            errs.append(f"{label}: needs family (and given), or literal, for citations")
        if not (isinstance(a.get("github"), str) and GITHUB_LOGIN.match(a["github"])):
            errs.append(f"{label}: github is their GitHub login")
        gid = a.get("github_id")
        if not (isinstance(gid, int) and not isinstance(gid, bool) and gid > 0):
            errs.append(f"{label}: github_id is their numeric GitHub user ID, which stays when a login changes")
        if a.get("role", "author") not in cfg["roles"]:
            errs.append(f"{label}: role must be one of {', '.join(cfg['roles'])}")
        chapters = a.get("chapters", [])
        if not (isinstance(chapters, list) and all(isinstance(c, str) and c for c in chapters)):
            errs.append(f"{label}: chapters is a list of the chapter IDs they own")
        if not isinstance(a.get("interests", ""), str):
            errs.append(f"{label}: interests is one sentence, disclosed on the book page")
    names = [a["name"].strip() for a in raw if isinstance(a.get("name"), str) and a["name"].strip()]
    if names and (problem := cover.authors_problem(names)):
        errs.append(f"{who}: {problem}")
    leads = [a for a in raw if a.get("role", "author") == LEAD]
    if len(leads) != 1:
        errs.append(f"{who}: exactly one author has role = \"lead\" (found {len(leads)})")
    for key in ("github", "github_id"):
        seen = [a.get(key) for a in raw if a.get(key) is not None]
        if len(seen) != len(set(map(str, seen))):
            errs.append(f"{who}: an author is listed twice ({key})")
    owned = [c for a in raw if isinstance(a.get("chapters"), list) for c in a["chapters"]]
    if len(owned) != len(set(owned)):
        errs.append(f"{who}: a chapter is owned by more than one author")
    if not isinstance(table, dict):
        errs.append(f"{who}: an authored book needs [authorship], with its state and, if not {cfg['default']}, its gate")
    else:
        if table.get("state") not in cfg["states"]:
            errs.append(f"{who}: [authorship] state must be one of {', '.join(cfg['states'])}")
        if table.get("gate", cfg["default"]) not in cfg["levels"]:
            errs.append(f"{who}: [authorship] gate must be one of {', '.join(cfg['levels'])}")
        extra = sorted(set(table) - {"gate", "state"})
        if extra:
            errs.append(f"{who}: [authorship] has unknown field(s) {', '.join(extra)}")
    return errs


def chapter_problems(manifest: dict, chapter_ids: list[str]) -> list[str]:
    """An owned chapter that the book doesn't have."""
    raw = manifest.get("authors")
    if not isinstance(raw, list):
        return []
    known = set(chapter_ids)
    return [f"{manifest.get('slug', '?')}: {a.get('name', '?')} owns chapter {c!r}, which the book doesn't have"
            for a in raw if isinstance(a, dict) and isinstance(a.get("chapters"), list)
            for c in a["chapters"] if isinstance(c, str) and c not in known]


def level(manifest: dict) -> dict:
    """The gate level's table, with its words' {hours} filled in."""
    table = dict(settings()["levels"][gate(manifest)])
    hours = settings()["major_wait_hours"]
    return {k: v.format(hours=hours) if isinstance(v, str) else v for k, v in table.items()}
