"""The checks a book pull request must pass: section IDs and the kind label.

The book-manifest check is catalog.validate_book; the examples check is examples.run_examples. The
command line in cli.py wires all four to the reusable workflows.
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

from .bookfmt import Book, load_book
from .sections import manifest_ids
from .tape import KIND_LABELS


def check_section_ids(head: Book, base: Book | None = None, previous: dict | None = None) -> list[str]:
    """Every chapter, section and example has a valid, unique ID, and no ID that existed on the base
    branch or in the previous edition has disappeared without an entry in redirects.yml."""
    problems = list(head.problems)
    live, retired = set(head.ids()), set(head.redirects)
    gone: dict[str, str] = {}
    if base is not None:
        for any_id, what in base.ids().items():
            if any_id not in live and any_id not in retired:
                gone[any_id] = f"{what} ID {any_id!r} was removed or changed"
        for old in base.redirects:
            if old not in head.redirects:
                problems.append(f"redirects.yml: the entry for retired ID {old!r} was removed; retired IDs stay retired")
    if previous is not None:
        for any_id in sorted(manifest_ids(previous)):
            if any_id not in live and any_id not in retired and any_id not in gone:
                gone[any_id] = f"ID {any_id!r} from Edition {previous.get('edition')} was removed or changed"
    for any_id in sorted(gone):
        problems.append(f"{gone[any_id]}, with no entry in redirects.yml. IDs are frozen: keep it even if the "
                        f"heading is renamed, or retire it with `{any_id}: successor-id` in redirects.yml")
    return problems


NARRATION_DIR = "narration/"     # a book's spoken descriptions and lexicon, beside its chapters, never on the page


def narration_only(paths: list[str]) -> bool:
    """Whether a change touches nothing but the book's narration files. The page doesn't change, so such a change has no
    kind of change for an edition: it needs no kind label, cuts no edition of its own, and rides with the next one."""
    return bool(paths) and all(p.startswith(NARRATION_DIR) for p in paths)


def check_kind_label(labels: list[str], changed: list[str] | None = None) -> list[str]:
    """At least one kind: label, and no unknown ones. A pull request that changes only narration files (`changed`, the
    paths it touches) needs none, since it changes nothing a reader sees on the page; an unknown one is still refused."""
    kinds = [label for label in labels if label.startswith("kind:")]
    problems = [f"unknown label {label!r}; kind labels are {', '.join(KIND_LABELS)}" for label in kinds if label not in KIND_LABELS]
    if not any(label in KIND_LABELS for label in kinds) and not narration_only(changed or []):
        problems.append(f"needs at least one kind label ({', '.join(KIND_LABELS)}) before it can merge")
    return problems


def labels_from_event(path: Path) -> list[str]:
    event = json.loads(Path(path).read_text(encoding="utf-8"))
    return [label["name"] for label in event.get("pull_request", {}).get("labels", [])]


def changed_from_event(path: Path, book: Path) -> list[str] | None:
    """The paths a pull request changes, from its event's base and head commits and the book's checkout: what
    `git diff base...head` lists, the pull request's own changes whatever has merged since it branched. None when the
    event or the checkout can't say, so the check asks for a kind label as before."""
    pr = json.loads(Path(path).read_text(encoding="utf-8")).get("pull_request") or {}
    base, head = (pr.get("base") or {}).get("sha"), (pr.get("head") or {}).get("sha")
    if not base or not head:
        return None
    r = subprocess.run(["git", "-C", str(book), "diff", "--name-only", f"{base}...{head}"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return [line for line in r.stdout.splitlines() if line]


def book_at_ref(repo: Path, ref: str, into: Path) -> Book:
    """The book as it was at a git ref, unpacked with `git archive` into a scratch folder."""
    files = subprocess.run(["git", "-C", str(repo), "ls-tree", "-r", "--name-only", ref], capture_output=True, text=True, check=True)
    if not files.stdout.strip():
        return load_book(into)                  # an empty commit: a new repository has no IDs yet
    data = subprocess.run(["git", "-C", str(repo), "archive", "--format=tar", ref], capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(into, filter="data")
    return load_book(into)


def latest_sections_url(slug: str) -> str:
    origin = os.environ.get("RE_AI_ORIGIN", "https://rollingedition.ai")
    return f"{origin}/books/{slug}/latest/sections.json"


def load_previous_manifest(source: str | None) -> tuple[dict | None, str]:
    """The previous edition's sections.json, from a path or a URL. A missing one means no edition yet."""
    if not source or source == "none":
        return None, "no released edition yet"
    if source.startswith(("http://", "https://")):
        try:
            with urllib.request.urlopen(source, timeout=30) as resp:
                return json.load(resp), f"previous edition from {source}"
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None, "no released edition yet"
            raise
    p = Path(source)
    if not p.exists():
        return None, "no released edition yet"
    return json.loads(p.read_text(encoding="utf-8")), f"previous edition from {p.name}"


def scratch() -> tempfile.TemporaryDirectory:
    return tempfile.TemporaryDirectory(prefix="re-check-")
