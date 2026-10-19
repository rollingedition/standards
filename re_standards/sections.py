"""The section manifest, `sections.json`: one per edition, written by the release job.

Per section, as the spec lists: section_id, chapter_id, title, order, sha256, changed and example_ids,
plus level and parent_id. Top-level chapters, examples and redirects arrays carry the rest of what
"what changed" lists, permanent links and the assistant server need.
"""
from __future__ import annotations

import json
from pathlib import Path

from .bookfmt import Book

SCHEMA_VERSION = 1


def build_manifest(book: Book, edition: str, line: str, prev: dict | None,
                   example_results: dict[str, dict] | None = None) -> dict:
    """`prev` is the previous edition's manifest on the same line, or None for a line's first edition.

    example_results maps example_id -> {"passing": bool, "versions": {...}, "direct": [...]}, from the
    release run of every example.
    """
    results = example_results or {}
    prev_sections = {s["section_id"]: s for s in (prev or {}).get("sections", [])}
    prev_chapters = {c["chapter_id"]: c for c in (prev or {}).get("chapters", [])}
    prev_examples = {e["example_id"]: e for e in (prev or {}).get("examples", [])}

    def changed(old: dict | None, sha: str) -> bool:
        return old is None or old["sha256"] != sha

    chapters = [{
        "chapter_id": c.chapter_id, "title": c.title, "order": c.order, "file": c.file,
        "sha256": c.sha256, "changed": prev is None or changed(prev_chapters.get(c.chapter_id), c.sha256),
    } for c in book.chapters]
    sections = [{
        "section_id": s.section_id, "chapter_id": s.chapter_id, "title": s.title, "order": s.order,
        "level": s.level, "parent_id": s.parent_id, "sha256": s.sha256,
        "changed": prev is None or changed(prev_sections.get(s.section_id), s.sha256),
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
