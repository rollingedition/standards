"""`re-check`: the checks every book pull request runs.

Book repos call these through the reusable workflows in .github/workflows/. Each check prints one
"ok" line on success, or every problem it found and exits 1. A check that warns, as narration does, lists what it
found and exits 0, unless --strict.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from . import bookfmt, catalog, checks, community, data_path, examples, readme, resolve, spoken, style


def report(name: str, problems: list[str], ok_line: str, warn: bool = False) -> int:
    """Print what a check found. A check that warns (warn) lists its warnings and still passes."""
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if problems:
        what = "warning(s)" if warn else "problem(s)"
        print(f"{name}: {len(problems)} {what}", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        text = f"### {name}: {f'{len(problems)} {what}' if warn else 'failed'}\n\n" + "\n".join(f"- {p}" for p in problems) + "\n"
    else:
        print(f"ok  {ok_line}")
        text = f"### {name}: passed\n\n{ok_line}\n"
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text)
    return 1 if problems and not warn else 0


def taxonomy_path(args) -> Path:
    return Path(args.taxonomy) if args.taxonomy else data_path("taxonomy.json")


def cmd_manifest(args) -> int:
    tax = catalog.load_taxonomy(taxonomy_path(args))
    manifest = Path(args.book) / "book.toml"
    problems = catalog.validate_taxonomy(tax) + catalog.validate_anchors(tax)
    if not manifest.exists():
        problems.append("book.toml is missing at the root of the book")
    else:
        try:
            book = catalog.load_book(manifest)
        except Exception as e:   # a TOML syntax error is a check failure, not a crash
            problems.append(f"book.toml does not parse: {e}")
        else:
            problems += catalog.validate_book(book, tax)
    return report("Book manifest", problems,
                  f"book.toml validates against taxonomy v{tax['version']} ({len(tax['skills'])} skills)")


def cmd_wikidata(args) -> int:
    from . import wikidata
    path = taxonomy_path(args)
    problems = wikidata.resolve(path, write=args.write)
    return report("Wikidata anchors", problems, f"every Wikipedia title in {path.name} resolves to a Wikidata item")


def cmd_section_ids(args) -> int:
    head = bookfmt.load_book(Path(args.book))
    source = args.previous
    if source == "latest":   # the latest edition's machine copy, which CI can always reach
        source = checks.latest_sections_url(head.slug)
    previous, note = checks.load_previous_manifest(source)
    with checks.scratch() as tmp:
        base = checks.book_at_ref(Path(args.book), args.base_ref, Path(tmp)) if args.base_ref else None
        problems = checks.check_section_ids(head, base, previous)
    n = len(head.ids())
    against = ", ".join(x for x in ("the base branch" if base else "", f"Edition {previous['edition']}" if previous else "") if x)
    return report("Section IDs", problems, f"{n} IDs are valid and unique" + (f"; none lost since {against}" if against else f" ({note})"))


def cmd_kind_label(args) -> int:
    labels = checks.labels_from_event(Path(args.event)) if args.event else [x for x in (args.labels or "").split(",") if x]
    changed = checks.changed_from_event(Path(args.event), Path(args.book)) if args.event and args.book else None
    problems = checks.check_kind_label(labels, changed)
    kinds = [x for x in labels if x.startswith("kind:")]
    if not kinds and checks.narration_only(changed or []):
        ok = (f"only narration files changed ({', '.join(changed)}): no kind label needed, since the page doesn't "
              "change; the change rides with the book's next edition")
    else:
        ok = "kind labels: " + ", ".join(kinds)
    return report("Kind label", problems, ok)


def workflow_command(level: str, title: str, message: str) -> None:
    """An annotation on the check, in GitHub Actions' workflow-command syntax, when a workflow runner runs this (GitHub
    sets GITHUB_ACTIONS, and so does the platform's local runner). Elsewhere, nothing."""
    if "GITHUB_ACTIONS" not in os.environ:
        return
    data = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    prop = title.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C")
    print(f"::{level} title={prop}::{data}", flush=True)


def write_report(args, data: dict) -> None:
    if args.report:
        Path(args.report).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def runtime_or_none(book) -> dict:
    try:
        rt = examples.read_runtime(book.root)
    except examples.ExamplesError:
        return {}
    return {"python": rt.python, "key": rt.key, "requirements_sha256": hashlib.sha256(rt.requirements.encode()).hexdigest()}


def cmd_examples(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    backend = examples.backend_named(args.backend or os.environ.get("RE_EXAMPLES_BACKEND", "container"),
                                     block_network=os.environ.get("RE_EXAMPLES_NETWORK", "blocked") == "blocked")
    try:
        results, runtime = examples.run_examples(book, backend, timeout=args.timeout,
                                                 only=args.only.split(",") if args.only else None)
    except examples.UnsatisfiablePins as e:
        # Nothing was built and no example ran: a resolver's verdict, never an example's failure.
        found = e.resolution
        workflow_command("error", resolve.settings()["annotation"], found.explanation)
        write_report(args, {"outcome": "unsatisfiable", "resolver": found.as_json(), "runtime": runtime_or_none(book),
                            "passing": 0, "total": len(book.examples), "examples": []})
        detail = "\n".join("      " + line for line in found.message.splitlines())
        return report("Examples", [f"{found.explanation}\n    The resolver ({found.tool}) says:\n{detail}"], "")
    except examples.ExamplesError as e:
        write_report(args, {"outcome": "error", "error": str(e), "runtime": runtime_or_none(book),
                            "passing": 0, "total": len(book.examples), "examples": []})
        return report("Examples", [str(e)], "")
    problems = []
    for r in results:
        label = examples.describe_versions(r.versions, r.direct)
        if args.record and r.exit_code == 0:
            (book.root / "examples" / f"{r.example_id}.out").write_text(examples.normalize_output(r.stdout), encoding="utf-8")
            print(f"recorded  {r.example_id}  ({label})")
            continue
        print(f"{'pass' if r.passing else 'FAIL'}  {r.example_id}  ({label})  {r.seconds:.1f}s")
        if not r.passing:
            detail = r.diff or r.stderr_tail or f"exit code {r.exit_code}"
            problems.append(f"{r.example_id} fails on {label}:\n" + "\n".join("      " + x for x in detail.splitlines()))
    if not args.record:
        problems += book.output_problems
    outcome = "recorded" if args.record else ("passed" if not problems else "failed")
    write_report(args, examples.results_json(results, runtime, outcome))
    passing = sum(r.passing for r in results)
    where = f"Python {runtime['python']}, {runtime['backend']} runtime"
    return report("Examples", problems, f"{passing} of {len(results)} examples pass ({where})" if not args.record
                  else f"recorded the output of {len(results)} examples ({where})")


def cmd_style(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    problems = style.check_style(book, style.load_config(Path(args.config)) if args.config else None)
    words = sum(len(style.WORD.findall(t)) for c in book.chapters for _, t in style._prose_lines(c.body, c.body_offset))
    return report("Writing standards", problems,
                  f"{len(book.chapters)} chapter(s), {words:,} words of prose: the lint rules of the writing standards pass")


def cmd_narration(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    if args.chapter and args.chapter not in {c.chapter_id for c in book.chapters}:
        return report("Narration", [f"there's no chapter {args.chapter!r} in this book"], "")
    if args.script:
        lines = (spoken.chapter_script(book, args.chapter, edition=args.edition) if args.chapter
                 else spoken.book_script(book, edition=args.edition))
        print(spoken.format_script(lines), end="")
        return 0
    warnings = spoken.check_narration(book, chapter_id=args.chapter)
    chapters = f"chapter {args.chapter!r}" if args.chapter else f"{len(book.chapters)} chapter(s)"
    rc = report("Narration", warnings, f"{chapters}: every term has a reading, and every example, block and table a description",
                warn=True)
    return 1 if warnings and args.strict else rc


def cmd_readme(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    problems = readme.check(book, write=args.write)
    return report("Front page", problems, "README.md, CITATION.cff, LICENSE, LICENSE-CODE, renovate.json and the check workflows are "
                  + ("written" if args.write else "up to date"))


def cmd_licences(args) -> int:
    problems = readme.check_own_licences(write=args.write)
    return report("Licences", problems, "this repository's LICENSE and LICENSE-TEXT are " + ("written" if args.write else "up to date"))


def cmd_community(args) -> int:
    problems = community.write(Path(args.out))
    return report("Community files", problems, f"the organization's community files are written to {args.out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="re-check", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("manifest", help="validate book.toml against the taxonomy")
    s.add_argument("--book", default=".", help="the book repo checkout")
    s.add_argument("--taxonomy", help="taxonomy.json (default: this standards checkout)")
    s.set_defaults(fn=cmd_manifest)

    s = sub.add_parser("wikidata", help="check or fill Wikidata IDs from Wikipedia titles (needs the internet)")
    s.add_argument("--write", action="store_true", help="write the IDs into the taxonomy")
    s.add_argument("--taxonomy")
    s.set_defaults(fn=cmd_wikidata)

    s = sub.add_parser("section-ids", help="every chapter, section and example has a frozen ID; none disappears without a redirect")
    s.add_argument("--book", default=".")
    s.add_argument("--base-ref", help="the pull request's base commit, to compare IDs against")
    s.add_argument("--previous", help="the previous edition's sections.json: a path or URL")
    s.set_defaults(fn=cmd_section_ids)

    s = sub.add_parser("kind-label", help="the pull request has at least one kind: label, unless it changes only narration "
                                          "files")
    s.add_argument("--event", help="the GitHub event JSON (GITHUB_EVENT_PATH)")
    s.add_argument("--labels", help="comma-separated labels, instead of --event")
    s.add_argument("--book", help="the book's checkout, with the event's base and head commits: a pull request that "
                                  "changes only narration/ needs no kind label")
    s.set_defaults(fn=cmd_kind_label)

    s = sub.add_parser("examples", help="run every example in its pinned runtime and compare its output")
    s.add_argument("--book", default=".")
    s.add_argument("--backend", choices=["venv", "container", "host"], help="default: $RE_EXAMPLES_BACKEND, else container")
    s.add_argument("--record", action="store_true", help="write each passing run's output as the expected output")
    s.add_argument("--report", help="write the results as JSON")
    s.add_argument("--only", help="comma-separated example IDs")
    s.add_argument("--timeout", type=float, default=120)
    s.set_defaults(fn=cmd_examples)

    s = sub.add_parser("style", help="the lint rules of the writing standards: lengths, time words, typed versions, bindings, banned words")
    s.add_argument("--book", default=".")
    s.add_argument("--config", help="writing.toml (default: this standards checkout)")
    s.set_defaults(fn=cmd_style)

    s = sub.add_parser("narration", help="the spoken script: terms no rule reads, and examples, blocks and tables with no "
                       "description (warns; never fails, unless --strict)")
    s.add_argument("--book", default=".")
    s.add_argument("--chapter", help="one chapter's ID (default: every chapter)")
    s.add_argument("--script", action="store_true", help="print the spoken script instead: each line's number, kind and unit, then its words")
    s.add_argument("--edition", help="the edition code the whole book's credits read, with --script")
    s.add_argument("--strict", action="store_true", help="exit 1 when there are warnings")
    s.set_defaults(fn=cmd_narration)

    s = sub.add_parser("readme", help="the generated front page: README.md, CITATION.cff, LICENSE, LICENSE-CODE and renovate.json")
    s.add_argument("--book", default=".")
    s.add_argument("--write", action="store_true", help="regenerate the files instead of checking them")
    s.set_defaults(fn=cmd_readme)

    s = sub.add_parser("licences", help="this repository's own licences: LICENSE (MIT, the code) and LICENSE-TEXT (CC BY 4.0, writing/ and prompts/)")
    s.add_argument("--write", action="store_true", help="regenerate the files instead of checking them")
    s.set_defaults(fn=cmd_licences)

    s = sub.add_parser("community", help="write the organization's community files for its .github repository")
    s.add_argument("--out", required=True, help="a checkout of the organization's .github repository")
    s.set_defaults(fn=cmd_community)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
