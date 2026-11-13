"""`re-check`: the checks every book pull request runs.

Book repos call these through the reusable workflows in .github/workflows/. Each check prints one
"ok" line on success, or every problem it found and exits 1. A check that warns, as narration does, lists what it
found and exits 0, unless --strict.

A rule with a date (data/rules.toml) warns on a released book until its next content edition (rules.py): the manifest,
style, skill and addressed checks take `--base-ref`, the pull request's base, to tell whether the change makes that
edition. A released book's out-of-date workflows warn too, since only a maintainer-approved pull request changes them.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from . import addressed as addressed_check, affected, base_image, bookfmt, catalog, checks, community, data_path, examples, kit, readme, resolve, rules, skill, spoken, style
from . import models as model_files


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


def report_dated(name: str, problems: list[str], ok_line: str, root: Path, manifest: dict | None,
                 base_ref: str | None = None) -> int:
    """report(), with a dated rule that doesn't hold the book yet listed as a warning (rules.py) instead of failing."""
    failures, warnings = rules.split(problems, root, manifest, base_ref or None)
    rc = report(name, failures, ok_line)
    if warnings:
        report(f"{name}, rules this book takes with its next content edition", warnings, "", warn=True)
    return rc


def taxonomy_path(args) -> Path:
    return Path(args.taxonomy) if args.taxonomy else data_path("taxonomy.json")


def cmd_manifest(args) -> int:
    tax = catalog.load_taxonomy(taxonomy_path(args))
    manifest = Path(args.book) / "book.toml"
    notes: list[str] = []
    book: dict | None = None
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
            notes = summary_notes(book)
    rc = report_dated("Book manifest", problems,
                      f"book.toml validates against taxonomy v{tax['version']} ({len(tax['skills'])} skills)",
                      Path(args.book), book, args.base_ref)
    if not problems and manifest.exists() and notes:
        report("Book summary", notes, "", warn=True)       # guidance (W-60): it never fails a pull request
    return rc


def summary_notes(book: dict) -> list[str]:
    """W-60: a summary far from the catalog's usual length, as a note. There's no fixed limit."""
    lo, hi = style.load_config().get("summary", {}).get("words", [0, 10 ** 6])
    n = len(str(book.get("summary") or "").split())
    if n and not lo <= n <= hi:
        return [f"W-60: the summary has {n} words; the catalog's run about {lo} to {hi}, in one sentence: what the book "
                "teaches, then after a colon what it covers, then what it works on"]
    return []


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
    if not kinds and checks.rides_along(changed or []):
        ok = (f"only {checks.riding_words(changed)} changed ({', '.join(changed)}): no kind label needed, "
              "since the page doesn't change; the change rides with the book's next edition")
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
    """The results as JSON, to --report, else to $RE_EXAMPLES_REPORT: how a caller that runs this check as it's given,
    such as the release service's gates, reads each example's time without changing the command."""
    path = args.report or os.environ.get("RE_EXAMPLES_REPORT")
    if path:
        Path(path).write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def seconds_from(path: str | None) -> dict[str, float]:
    """Each example's time in an earlier run, for --jobs to pack them by: a --report file or an edition's examples.json."""
    if not path:
        return {}
    try:
        return examples.recorded_seconds(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        why = e.strerror if isinstance(e, OSError) else str(e)
        raise examples.ExamplesError(f"--seconds: {path} isn't a report of an earlier run: {why}") from None


def runtime_or_none(book) -> dict:
    try:
        rt = examples.read_runtime(book.root)
    except examples.ExamplesError:
        return {}
    out = {"python": rt.python, "key": rt.key, "requirements_sha256": hashlib.sha256(rt.requirements.encode()).hexdigest()}
    if rt.models:
        out["models_sha256"] = model_files.digest(rt.model_list())
    return out


def cmd_examples(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    if (args.list or args.base_ref or args.recorded) and not args.affected:
        return report("Examples", ["--list, --base-ref and --recorded go with --affected"], "")
    try:
        seeds = examples.parse_seeds(args.seeds)
        backend = examples.backend_named(args.backend or os.environ.get("RE_EXAMPLES_BACKEND", "container"),
                                         block_network=os.environ.get("RE_EXAMPLES_NETWORK", "blocked") == "blocked",
                                         fresh=args.fresh)
    except (examples.ExamplesError, ValueError) as e:
        return report("Examples", [str(e)], "")
    try:
        return run_examples_check(args, book, backend, seeds)
    finally:
        backend.cleanup()                          # a fresh runtime's folder goes once its run is done


def run_examples_check(args, book: bookfmt.Book, backend: examples.Backend, seeds: list[int]) -> int:
    selection, chosen = None, {}
    try:
        only, prepared = args.only.split(",") if args.only else None, False
        if args.affected:
            selection, prepared = affected.choose(book, args.base_ref, backend, args.recorded, timeout=args.timeout)
            chosen = {"selection": selection.as_json()}
            print("\n".join(selection.lines()))
            only = None if selection.everything else selection.ids
        if args.list or only == []:
            results, runtime = [], (backend.describe(examples.read_runtime(book.root)) if only == [] else {})
        else:
            results, runtime = examples.run_examples(book, backend, timeout=args.timeout, only=only, prepared=prepared,
                                                     seeds=seeds, jobs=args.jobs, seconds=seconds_from(args.seconds))
    except examples.UnsatisfiablePins as e:
        # Nothing was built and no example ran: a resolver's verdict, never an example's failure.
        found = e.resolution
        workflow_command("error", resolve.settings()["annotation"], found.explanation)
        write_report(args, {"outcome": "unsatisfiable", "resolver": found.as_json(), "runtime": runtime_or_none(book),
                            "passing": 0, "total": len(book.examples), "examples": [], **chosen})
        detail = "\n".join("      " + line for line in found.message.splitlines())
        return report("Examples", [f"{found.explanation}\n    The resolver ({found.tool}) says:\n{detail}"], "")
    except examples.ExamplesError as e:
        write_report(args, {"outcome": "error", "error": str(e), "runtime": runtime_or_none(book),
                            "passing": 0, "total": len(book.examples), "examples": [], **chosen})
        return report("Examples", [str(e)], "")
    if args.list:
        return 0
    problems = []
    for r in results:
        label = examples.describe_versions(r.versions, r.direct)
        if args.record and r.exit_code == 0 and not r.seed_diff:
            (book.root / "examples" / f"{r.example_id}.out").write_text(examples.normalize_output(r.stdout), encoding="utf-8")
            print(f"recorded  {r.example_id}  ({label})")
            continue
        print(f"{'pass' if r.passing else 'FAIL'}  {r.example_id}  ({label})  {r.seconds:.1f}s")
        if not r.passing:
            detail = r.diff or (r.seed_diff if r.exit_code == 0 else "") or r.stderr_tail or f"exit code {r.exit_code}"
            problems.append(f"{r.example_id} fails on {label}:\n" + "\n".join("      " + x for x in detail.splitlines()))
    if not args.record:
        problems += book.output_problems
    outcome = "recorded" if args.record else ("passed" if not problems else "failed")
    write_report(args, examples.results_json(results, runtime, outcome) | chosen)
    passing = sum(r.passing for r in results)
    where = f"Python {runtime['python']}, {runtime['backend']} runtime" + \
        (f", hash seeds {', '.join(map(str, seeds))}" if len(seeds) > 1 else "") + \
        (", built fresh" if runtime.get("fresh") else "")
    if args.record:
        return report("Examples", problems, f"recorded the output of {len(results)} examples ({where})")
    if selection and not selection.everything:
        against = f"against {selection.base[:12]}"
        if not results:
            return report("Examples", problems, f"no example can be affected by this change, so none of "
                          f"{selection.total} ran ({against})")
        return report("Examples", problems, f"{passing} of {len(results)} affected examples pass; the other "
                      f"{selection.total - len(results)} can't be affected by this change ({against}; {where})")
    return report("Examples", problems, f"{passing} of {len(results)} examples pass ({where})")


def cmd_style(args) -> int:
    skip = {r.strip() for given in args.skip for r in given.split(",") if r.strip()}
    if bad := sorted(r for r in skip if not style.RULE_ID.match(r)):
        return report("Writing standards", [f"--skip takes rule IDs such as W-7, not {', '.join(map(repr, bad))}"], "")
    cfg, wrong = style.with_limits(style.load_config(Path(args.config) if args.config else None), args.limit)
    if wrong:
        return report("Writing standards", wrong, "")
    book = bookfmt.load_book(Path(args.book))
    problems = style.check_style(book, cfg, skip=skip)
    words = sum(len(style.WORD.findall(t)) for c in book.chapters for _, t in style._prose_lines(c.body, c.body_offset))
    skipped = f" (skipping {', '.join(sorted(skip))})" if skip else ""
    skipped += f" (with {', '.join(args.limit)})" if args.limit else ""
    return report_dated("Writing standards", problems,
                        f"{len(book.chapters)} chapter(s), {words:,} words of prose: the lint rules of the writing "
                        "standards pass" + skipped, book.root, book.manifest, args.base_ref)


def cmd_addressed(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    problems = addressed_check.check_addressed(book, addressed_check.load_config(Path(args.config)) if args.config else None)
    return report_dated("Text addressed to a model", problems,
                        f"no text addressed to a model in {len(book.chapters)} chapter(s)", book.root, book.manifest,
                        args.base_ref)


def cmd_skill(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    problems, notes = skill.check(book, style.load_config(Path(args.config)) if args.config else None)
    if not problems and notes:
        return report("Agent skill", notes, "", warn=True)
    found, _ = skill.read(book.root)
    n = sum(1 for line in found.body.split("\n") if line.startswith("## ")) if found else 0
    return report_dated("Agent skill", problems, f"skill.md: {n} procedure(s), each citing the sections it comes from",
                        book.root, book.manifest, args.base_ref)


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


def cmd_kit(args) -> int:
    """The book kit (kit.py): with --write, its files and, for each --chapter, a numbered stub and the chapter's own
    narration file; without, what the book lacks of it. A draft fails on what's missing; a released book is told."""
    root = Path(args.book)
    draft = kit.is_draft(root)
    if args.write:
        written, problems = kit.write(root, args.chapter)
        for rel in written:
            print(f"wrote  {rel}")
        return report("Book kit", problems, f"the kit is in place ({len(written)} file(s) written)")
    if args.chapter:
        return report("Book kit", ["--chapter goes with --write"], "")
    problems = kit.check(root)
    return report("Book kit", problems, "the kit's files are in place and unchanged", warn=not draft)


def cmd_readme(args) -> int:
    book = bookfmt.load_book(Path(args.book))
    problems, later = readme.held_for_maintainer(book, readme.check(book, write=args.write))
    rc = report("Front page", problems, "README.md, CITATION.cff, LICENSE, LICENSE-CODE, renovate.json and the check "
                "workflows are " + ("written" if args.write else "up to date") if not later else
                "README.md, CITATION.cff, LICENSE, LICENSE-CODE and renovate.json are up to date")
    if later:
        report("Front page, the book's workflows", later, "", warn=True)
    return rc


def cmd_models(args) -> int:
    root = Path(args.book)
    try:
        current = model_files.read(root)
        if args.pin:
            split = lambda v: [x.strip() for x in v.split(",") if x.strip()] if v else None
            new = model_files.pin(args.pin, revision=args.revision, files=split(args.files), include=split(args.include))
            current = model_files.upsert(current, new)
            text = model_files.to_toml(current)
            model_files.parse(text)                 # what it writes must read back, licence and size cap included
            (root / model_files.MODELS).write_text(text, encoding="utf-8")
            print(f"pinned {new.repo} at {new.revision[:12]} ({new.licence}): {len(new.files)} files, "
                  f"{sum(f.size for f in new.files) / 2**20:,.1f} MB")
    except model_files.ModelsError as e:
        return report("Models", [str(e)], "")
    if not current:
        return report("Models", [], f"no {model_files.MODELS}: the examples load no model")
    return report("Models", [], f"{len(current)} model(s), {model_files.total_bytes(current) / 2**20:,.1f} MB, each at a "
                  f"full commit with every file's SHA-256: {', '.join(m.repo for m in current)}")


def cmd_base_image(args) -> int:
    if args.python and not args.refresh:
        return report("Base image", ["--python goes with --refresh"], "")
    if args.refresh:
        try:
            new, changed = base_image.refresh(add=args.python)
        except (base_image.BaseImageError, OSError, ValueError, KeyError) as e:
            return report("Base image", [f"couldn't refresh: {e}"], "")
        text = base_image.to_toml(new, base_image.header(base_image.path().read_text(encoding="utf-8")))
        base_image.path().write_text(text, encoding="utf-8")
        print("\n".join(changed) or "nothing changed")
    data = base_image.load()
    pinned = [f"Python {v} on {p['debian']}" for v, p in sorted(data.get("python", {}).items())]
    return report("Base image", base_image.problems(data),
                  f"{len(pinned)} Python base image(s) pinned by digest ({', '.join(pinned)}), with "
                  f"{', '.join(data['packages'])} pinned on each")


def cmd_licences(args) -> int:
    problems = readme.check_own_licences(write=args.write)
    return report("Licences", problems, "this repository's LICENSE and LICENSE-TEXT are " + ("written" if args.write else "up to date"))


def cmd_community(args) -> int:
    problems = community.write(Path(args.out))
    return report("Community files", problems, f"the organization's community files are written to {args.out}")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="re-check", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)

    base_ref = ("the pull request's base commit: a rule with a date (data/rules.toml) holds a released book from the "
                "change that alters its text or examples, and warns before")
    s = sub.add_parser("manifest", help="validate book.toml against the taxonomy")
    s.add_argument("--book", default=".", help="the book repo checkout")
    s.add_argument("--taxonomy", help="taxonomy.json (default: this standards checkout)")
    s.add_argument("--base-ref", help=base_ref)
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
    s.add_argument("--report", help="write the results as JSON (default: $RE_EXAMPLES_REPORT, when it's set)")
    which = s.add_mutually_exclusive_group()
    which.add_argument("--only", help="comma-separated example IDs")
    which.add_argument("--affected", action="store_true",
                       help="run only the examples a change since --base-ref could affect, each with why, or every "
                            "example when that can't be told, saying why")
    s.add_argument("--base-ref", help="with --affected: the commit to compare with, such as a pull request's base")
    s.add_argument("--recorded", help="with --affected: the last run's record, whose loaded libraries add examples: a "
                                      "sections.json or a --report file, as a path or URL; `latest` for the latest "
                                      "edition's; `none` for no record (the default)")
    s.add_argument("--list", action="store_true", help="with --affected: print the selection and run nothing")
    s.add_argument("--timeout", type=float, default=120)
    s.add_argument("--jobs", type=int, default=1, help="run up to this many examples side by side, packed by --seconds; "
                                                         "one with no recorded time, or too slow to share the machine "
                                                         "within --timeout, runs alone (default 1: one at a time)")
    s.add_argument("--seconds", help="with --jobs: an earlier run's --report, or an edition's examples.json, for each "
                                     "example's time")
    s.add_argument("--seeds", help="comma-separated hash seeds, such as 0,1: each example runs under each, and fails "
                                   "when any output differs (default: [run] seed alone)")
    s.add_argument("--fresh", action="store_true", help="with the venv backend: build the runtime in a new folder, used "
                                                        "for this run alone, instead of the one kept")
    s.set_defaults(fn=cmd_examples)

    s = sub.add_parser("style", help="the lint rules of the writing standards: lengths, time words, typed versions, bindings, banned words")
    s.add_argument("--book", default=".")
    s.add_argument("--config", help="writing.toml (default: this standards checkout)")
    s.add_argument("--skip", action="append", default=[], metavar="RULE",
                   help="a rule this book doesn't keep, such as W-7: repeat it, or separate rules with commas")
    s.add_argument("--limit", action="append", default=[], metavar="NAME=LO,HI",
                   help="one of writing.toml's [length] limits as this book keeps it, such as chapter_words=1500,6000: "
                        "the rule's other limits stay; repeat it for more")
    s.add_argument("--base-ref", help=base_ref)
    s.set_defaults(fn=cmd_style)

    s = sub.add_parser("addressed", help="text written to an AI system: hidden characters, and phrases such as \"ignore previous "
                       "instructions\" in prose, comments, link titles and book.toml (code and inline code are exempt)")
    s.add_argument("--book", default=".")
    s.add_argument("--config", help="addressed.toml (default: this standards checkout)")
    s.add_argument("--base-ref", help=base_ref)
    s.set_defaults(fn=cmd_addressed)

    s = sub.add_parser("skill", help="skill.md, the procedures of the book's agent skill: each cites its sections, links "
                       "only to the book and the sources it cites, binds its versions, and fits the format")
    s.add_argument("--book", default=".")
    s.add_argument("--config", help="writing.toml (default: this standards checkout)")
    s.add_argument("--base-ref", help=base_ref)
    s.set_defaults(fn=cmd_skill)

    s = sub.add_parser("narration", help="the spoken script: terms no rule reads, and examples, blocks and tables with no "
                       "description (warns; never fails, unless --strict)")
    s.add_argument("--book", default=".")
    s.add_argument("--chapter", help="one chapter's ID (default: every chapter)")
    s.add_argument("--script", action="store_true", help="print the spoken script instead: each line's number, kind and unit, then its words")
    s.add_argument("--edition", help="the edition code the whole book's credits read, with --script")
    s.add_argument("--strict", action="store_true", help="exit 1 when there are warnings")
    s.set_defaults(fn=cmd_narration)

    s = sub.add_parser("kit", help="the book kit every draft starts with: .gitignore, examples/lib (threads and seeds), "
                       "recordings/recorded.py (record into scratch, then copy in); --write writes it, and --chapter ID, "
                       "repeated in the plan's order, numbered chapter stubs with their own narration files")
    s.add_argument("--book", default=".")
    s.add_argument("--write", action="store_true", help="write the kit's files; a generated one is written again, and "
                                                        "an existing chapter is never touched")
    s.add_argument("--chapter", action="append", default=[], metavar="ID",
                   help="with --write: a chapter's ID, in the plan's order, for chapters/NN-ID.md and narration/ID.toml")
    s.set_defaults(fn=cmd_kit)

    s = sub.add_parser("readme", help="the generated front page: README.md, CITATION.cff, LICENSE, LICENSE-CODE and renovate.json")
    s.add_argument("--book", default=".")
    s.add_argument("--write", action="store_true", help="regenerate the files instead of checking them")
    s.set_defaults(fn=cmd_readme)

    s = sub.add_parser("models", help="the open model files the examples load (examples/models.toml); --pin writes one "
                       "model's entry from Hugging Face (needs the internet)")
    s.add_argument("--book", default=".")
    s.add_argument("--pin", metavar="OWNER/NAME", help="pin this public model, or move it to --revision")
    s.add_argument("--revision", default="main", help="a branch, tag or commit; the entry records the full commit")
    s.add_argument("--files", help="comma-separated file names to pin, in place of the default patterns")
    s.add_argument("--include", help="comma-separated patterns for top-level files, in place of [models] default_files")
    s.set_defaults(fn=cmd_models)

    s = sub.add_parser("base-image", help="the runtime image's base, pinned by digest with its packages' versions "
                                          "(data/runtime-base.toml); --refresh rewrites it (needs the internet)")
    s.add_argument("--refresh", action="store_true", help="each Python's digest from Docker Hub and each package's "
                                                          "version from Debian, written back")
    s.add_argument("--python", action="append", metavar="VERSION",
                   help="with --refresh: add this Python, such as 3.13.17")
    s.set_defaults(fn=cmd_base_image)

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
