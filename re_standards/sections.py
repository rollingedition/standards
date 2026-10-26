"""The section manifest, `sections.json`: one per edition, written by the release job.

Per section, as the spec lists: section_id, chapter_id, title, order, sha256, rendered_sha256, changed and example_ids,
plus level and parent_id. Top-level chapters, examples and redirects arrays carry the rest of what
"what changed" lists, permanent links and the assistant server need.

Two hashes per chapter opening and section. `sha256` covers the source text, where a number an example prints is still
a binding such as {{out:EXAMPLE_ID:LABEL}}; it names a version of the source, so checks and highlights are keyed by it.
`rendered_sha256` covers the text as read, after Book.bind fills in each binding with this edition's recorded outputs
and pins, normalized the same way, so it equals `sha256` for a unit with no binding. `changed` compares the text as
read: a library update that moves a bound number changes the section, and a binding put in place of the same typed
number doesn't.

Schema 2 adds `rendered_sha256`, and `changed` follows it. A manifest written before (schema 1) has no
`rendered_sha256`: `fill_rendered` works it out from that edition's own text, and compare `changed` with it.
"""
from __future__ import annotations

import json
from pathlib import Path

from .bookfmt import Book

SCHEMA_VERSION = 2              # 2: rendered_sha256 on every chapter and section, which `changed` compares


def text_hash(entry: dict) -> str:
    """A manifest entry's hash of its text as read: its rendered_sha256, or for a manifest written before the field and
    not filled in, its sha256, which misses only a change in a bound value."""
    return entry.get("rendered_sha256") or entry["sha256"]


def build_manifest(book: Book, edition: str, line: str, prev: dict | None,
                   example_results: dict[str, dict] | None = None) -> dict:
    """`prev` is the previous edition's manifest on the same line, or None for a line's first edition. A previous
    manifest written before rendered_sha256 should be filled in first (fill_rendered), so a change in a bound value
    alone is seen.

    example_results maps example_id -> {"passing": bool, "versions": {...}, "direct": [...]}, from the
    release run of every example.
    """
    results = example_results or {}
    rendered = book.rendered_hashes()
    prev_sections = {s["section_id"]: s for s in (prev or {}).get("sections", [])}
    prev_chapters = {c["chapter_id"]: c for c in (prev or {}).get("chapters", [])}
    prev_examples = {e["example_id"]: e for e in (prev or {}).get("examples", [])}

    def changed(old: dict | None, sha: str, unit: str) -> bool:
        """Whether the text as read differs; compared by sha256 against an entry that has no rendered_sha256."""
        if old is None:
            return True
        return old["rendered_sha256"] != rendered[unit] if "rendered_sha256" in old else old["sha256"] != sha

    chapters = [{
        "chapter_id": c.chapter_id, "title": c.title, "order": c.order, "file": c.file,
        "sha256": c.sha256, "rendered_sha256": rendered[c.chapter_id],
        "changed": prev is None or changed(prev_chapters.get(c.chapter_id), c.sha256, c.chapter_id),
    } for c in book.chapters]
    sections = [{
        "section_id": s.section_id, "chapter_id": s.chapter_id, "title": s.title, "order": s.order,
        "level": s.level, "parent_id": s.parent_id, "sha256": s.sha256, "rendered_sha256": rendered[s.section_id],
        "changed": prev is None or changed(prev_sections.get(s.section_id), s.sha256, s.section_id),
        "example_ids": list(s.example_ids),
    } for s in book.sections]
    examples = []
    for eid in sorted(book.examples, key=lambda e: _example_order(book, e)):
        ex = book.examples[eid]
        result = results.get(eid, {})
        versions = result.get("versions", {})
        old = prev_examples.get(eid)
        examples.append({
            "example_id": eid, "chapter_id": ex.chapter_id, "section_id": ex.section_id, "file": ex.file,
            "sha256": ex.sha256, "versions": versions, "direct": result.get("direct", []),
            "passing": result.get("passing"),
            # changed: its code or the versions it ran against differ from the previous edition on the line
            "changed": prev is None or old is None or old["sha256"] != ex.sha256 or old.get("versions") != versions,
        })
    return {
        "schema_version": SCHEMA_VERSION, "book": book.slug, "edition": edition, "line": line,
        "prev_edition": (prev or {}).get("edition"),
        "chapters": chapters, "sections": sections, "examples": examples,
        "redirects": dict(sorted(book.redirects.items())),
    }


def _example_order(book: Book, eid: str) -> tuple:
    ex = book.examples[eid]
    for c in book.chapters:
        for e_i, e in enumerate(c.embeds):
            if e.example_id == eid:
                return (c.order, e.start, e_i)
    return (len(book.chapters) + 1, 0, eid)


def examples_changed(manifest: dict) -> int:
    return sum(1 for e in manifest["examples"] if e["changed"])


def units_changed(manifest: dict) -> list[str]:
    """The units whose text as read changed, in reading order: each chapter's opening, under the chapter's ID, then its
    sections. A chapter's opening is a section of its own, as it is for checks and change marks."""
    out = []
    for c in sorted(manifest.get("chapters", []), key=lambda c: c["order"]):
        if c["changed"]:
            out.append(c["chapter_id"])
        out += [s["section_id"] for s in manifest["sections"] if s["chapter_id"] == c["chapter_id"] and s["changed"]]
    return out


def fill_rendered(manifest: dict, book: Book) -> dict:
    """A manifest written before rendered_sha256 (schema 1), with each chapter's and section's rendered_sha256 worked
    out from `book`, the same edition's text: its chapters, its examples' recorded outputs and its pins, as its bundle
    keeps them. Nothing else changes, and the manifest given is left as it is. A unit is filled in only when the book's
    own sha256 for it is the manifest's, so a text that isn't the edition's never gives it a hash; an entry that already
    has one keeps it."""
    rendered, source = book.rendered_hashes(), {c.chapter_id: c.sha256 for c in book.chapters}
    source.update({s.section_id: s.sha256 for s in book.sections})

    def fill(entry: dict, unit: str) -> dict:
        if "rendered_sha256" in entry or source.get(unit) != entry["sha256"]:
            return entry
        return dict(entry, rendered_sha256=rendered[unit])
    return dict(manifest, chapters=[fill(c, c["chapter_id"]) for c in manifest.get("chapters", [])],
                sections=[fill(s, s["section_id"]) for s in manifest.get("sections", [])])


def manifest_ids(manifest: dict) -> set[str]:
    """Every live ID a manifest names: chapters, sections and examples."""
    return ({c["chapter_id"] for c in manifest.get("chapters", [])}
            | {s["section_id"] for s in manifest.get("sections", [])}
            | {e["example_id"] for e in manifest.get("examples", [])})


def write(manifest: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def read(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))
