"""The catalog: validate the taxonomy and book manifests, and build the catalog the sites read.

The executable form of the catalog spec. Areas sit at the top, skills underneath; a book has 1 to 5
skills, the first being primary, and appears in every area its skills touch. Standard library only.
"""
from __future__ import annotations

import json
import re
import tomllib
from collections import Counter
from pathlib import Path

from . import cover, data_path

SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
QID = re.compile(r"^Q[1-9][0-9]*$")
STATUSES = ("draft", "live", "unmaintained", "retired")
LISTED = ("live", "unmaintained")          # statuses shown in the public catalog
LEVELS = {"foundations": "Foundations", "in-practice": "In practice"}   # the reader's level (writing standards W-1)
MAX_SKILLS = 5
MAX_ID_LENGTH = 64


class CatalogError(ValueError):
    pass


def load_taxonomy(path: Path | None = None) -> dict:
    return json.loads(Path(path or data_path("taxonomy.json")).read_text(encoding="utf-8"))


def load_book(path: Path) -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def validate_taxonomy(tax: dict) -> list[str]:
    errs: list[str] = []
    areas = {a["id"]: a for a in tax["areas"]}
    skills = {s["id"]: s for s in tax["skills"]}
    if len(areas) != len(tax["areas"]):
        errs.append("duplicate area id")
    if len(skills) != len(tax["skills"]):
        errs.append("duplicate skill id")
    for term_id in sorted(set(areas) & set(skills)):
        errs.append(f"{term_id}: used as both an area and a skill")
    for term in tax["areas"] + tax["skills"]:
        if not SLUG.match(term["id"]) or len(term["id"]) > MAX_ID_LENGTH:
            errs.append(f"{term['id']}: not a valid id")
        if not term.get("label"):
            errs.append(f"{term['id']}: missing label")
        if term.get("wikidata") is not None and not QID.match(term["wikidata"]):
            errs.append(f"{term['id']}: wikidata must be like Q2539")
    for a in tax["areas"]:
        if a.get("status") not in ("active", "planned"):
            errs.append(f"{a['id']}: status must be active or planned")
    for s in tax["skills"]:
        if not s.get("areas"):
            errs.append(f"{s['id']}: a skill needs at least one area")
        for a in s.get("areas", []):
            if a not in areas:
                errs.append(f"{s['id']}: unknown area {a}")
        for r in s.get("related", []):
            if r == s["id"]:
                errs.append(f"{s['id']}: related to itself")
            elif r not in skills:
                errs.append(f"{s['id']}: unknown related skill {r}")
            elif s["id"] not in skills[r].get("related", []):
                errs.append(f"{s['id']} lists {r} as related, but {r} doesn't list {s['id']}")
    return errs


def validate_anchors(tax: dict) -> list[str]:
    """Every term with a Wikipedia title needs its Wikidata ID before release (fill with `re-check wikidata`)."""
    return [f"{t['id']}: has a Wikipedia title but no Wikidata ID; run re-check wikidata --write"
            for t in tax["areas"] + tax["skills"] if t.get("wikipedia") and not t.get("wikidata")]


def validate_book(book: dict, tax: dict, released: bool = False) -> list[str]:
    """Problems with a book.toml. released=True reads a manifest from an edition already out, which may lack a
    field added after it was released (level); a new manifest must have it."""
    skills = {s["id"] for s in tax["skills"]}
    who = book.get("slug", "?")
    errs = []
    if not SLUG.match(str(book.get("slug", ""))):
        errs.append(f"{who}: slug must be lowercase words joined by hyphens")
    if not book.get("title"):
        errs.append(f"{who}: missing title")
    elif problem := cover.title_problem(book["title"]):
        errs.append(f"{who}: {problem}")
    if book.get("status") not in STATUSES:
        errs.append(f"{who}: status must be one of {', '.join(STATUSES)}")
    if book.get("level") not in LEVELS and not (released and "level" not in book):
        errs.append(f"{who}: level must be one of {', '.join(LEVELS)}")
    if "reader" in book and not (isinstance(book["reader"], str) and book["reader"].strip()):
        errs.append(f"{who}: reader, when given, is one sentence saying who the book is for")
    book_skills = book.get("skills", [])
    if not 1 <= len(book_skills) <= MAX_SKILLS:
        errs.append(f"{who}: needs 1 to {MAX_SKILLS} skills (the first is primary)")
    if len(set(book_skills)) != len(book_skills):
        errs.append(f"{who}: a skill is listed twice")
    for s in book_skills:
        if s not in skills:
            errs.append(f"{who}: unknown skill {s} (add it to the taxonomy first)")
    return errs


def book_areas(book: dict, tax: dict) -> list[str]:
    """Areas come from skills, never tagged directly. The primary skill's areas come first."""
    by_id = {s["id"]: s for s in tax["skills"]}
    out: list[str] = []
    for s in book["skills"]:
        for a in by_id[s]["areas"]:
            if a not in out:
                out.append(a)
    return out


def build_catalog(tax: dict, books: list[dict], released: bool = False) -> dict:
    """The catalog the sites read. released=True when the manifests come from editions already released."""
    errs = validate_taxonomy(tax)
    for b in books:
        errs += validate_book(b, tax, released)
    if errs:
        raise CatalogError("\n".join(errs))
    listed = [b for b in books if b["status"] in LISTED]
    by_skill: dict[str, list[dict]] = {s["id"]: [] for s in tax["skills"]}
    for b in listed:
        for i, s in enumerate(b["skills"]):
            by_skill[s].append({"slug": b["slug"], "primary": i == 0})
    for entries in by_skill.values():            # primary books first, then by slug
        entries.sort(key=lambda x: (not x["primary"], x["slug"]))
    together: Counter = Counter()
    for b in listed:
        for x in b["skills"]:
            for y in b["skills"]:
                if x != y:
                    together[(x, y)] += 1
    skills_out = []
    for s in tax["skills"]:
        if not by_skill[s["id"]]:
            continue                             # no page until a listed book uses the skill
        also = sorted({y for (x, y) in together if x == s["id"]} - set(s.get("related", [])))
        skills_out.append({
            "id": s["id"], "label": s["label"], "areas": s["areas"], "description": s["description"],
            "wikipedia": s.get("wikipedia"), "wikidata": s.get("wikidata"),
            "books": [x["slug"] for x in by_skill[s["id"]]],
            "related": [r for r in s.get("related", []) if by_skill[r]],
            "also_covered_with": [y for y in also if by_skill[y]],
        })
    shown = {s["id"] for s in skills_out}
    areas_out = []
    for a in tax["areas"]:
        a_skills = [s["id"] for s in skills_out if a["id"] in s["areas"]]
        if a["status"] != "active" or not a_skills:
            continue                             # planned areas stay hidden; empty areas get no page
        a_books = sorted({slug for s in skills_out if s["id"] in a_skills for slug in s["books"]})
        areas_out.append({"id": a["id"], "label": a["label"], "description": a["description"],
                          "wikipedia": a.get("wikipedia"), "wikidata": a.get("wikidata"),
                          "skills": a_skills, "books": a_books})
    books_out = [{"slug": b["slug"], "title": b["title"], "status": b["status"], "level": b.get("level"),
                  "level_label": LEVELS.get(b.get("level"), ""), "primary_skill": b["skills"][0],
                  "skills": b["skills"], "areas": book_areas(b, tax)}
                 for b in sorted(listed, key=lambda b: b["slug"])]
    assert all(s in shown for b in books_out for s in b["skills"])
    return {"taxonomy_version": tax["version"], "areas": areas_out, "skills": skills_out, "books": books_out}


def wikipedia_url(title: str | None) -> str | None:
    return f"https://en.wikipedia.org/wiki/{title}" if title else None


def wikidata_url(qid: str | None) -> str | None:
    return f"https://www.wikidata.org/wiki/{qid}" if qid else None
