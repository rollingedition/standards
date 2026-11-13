"""A book repository's front page, generated: README.md, CITATION.cff, LICENSE, LICENSE-CODE and renovate.json, and
the two workflows that run the shared checks on every pull request.

Everything comes from the repository itself (book.toml, the chapters, the examples) and from
data/readme.toml, so nothing in these files is typed by hand. renovate.json is data/renovate.json, the same for
every book: among other things, it holds a new library release back until it is old enough. Facts that change with each edition
(its number, date, examples passing) stay on the site: the README shows them through the site's stamp
badge and latest cover, so it doesn't change at every release. `re-check readme` fails when a file is
out of date; `--write` regenerates them. `re-check licences` does the same for this repository's own licences.

A released book's workflows are the exception. A change under .github/ waits for a maintainer, and the agent that
regenerates a pull request's front page never writes them, so when their templates change, a released book takes the
new ones through one maintainer-approved pull request (`re retrofit workflows` opens one in every book). Until it
merges, `re-check readme` warns that they're out of date and doesn't fail, so none of the book's other pull requests
waits for it. A draft's are written at its launch, and fail the check when they're out of date.

The wording follows open verification: agents publish, anyone checks or corrects, and only serious
risks wait for a person. It never says that a person approved anything.
"""
from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path

import yaml

from . import data_path
from . import models as model_files
from .bookfmt import Book
from .catalog import LEVELS

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
PROMISE = re.compile(r"^by the end of this chapter,?\s+you\s+can\s+", re.IGNORECASE)


def load_config(path: Path | None = None) -> dict:
    with open(path or data_path("readme.toml"), "rb") as f:
        return tomllib.load(f)


def _url(cfg: dict, key: str, **values) -> str:
    return cfg["site"] + cfg["paths"][key].format(**values)


def repo_url(slug: str, cfg: dict) -> str:
    """The book's public repository on GitHub."""
    return f"{cfg['github']}/{cfg['repo'].format(book=slug)}"


def report_error_url(slug: str, cfg: dict) -> str:
    """The book repository's "Report an error" issue form, which asks for the section's ID."""
    return f"{repo_url(slug, cfg)}/issues/new?template=report-an-error.yml"


def first_sentence(chapter_body: str) -> str:
    """The chapter's first sentence, as written: by W-2, what the reader can do by its end ("By the end of this
    chapter you can …")."""
    paragraphs = [p.strip() for p in chapter_body.split("\n\n") if p.strip() and not p.lstrip().startswith("#")]
    if not paragraphs:
        return ""
    text = " ".join(paragraphs[0].split())
    match = re.search(r"(?<=[.!?])\s+(?=[A-Z])", text)
    return text[:match.start()] if match else text


def _first_sentence(chapter_body: str) -> str:
    """The first sentence after the chapter's title, for the contents table: what the reader can do by its end."""
    return PROMISE.sub("", first_sentence(chapter_body)).rstrip(".")


def reader(manifest: dict, cfg: dict) -> str:
    """Who the book is for: book.toml's `reader` sentence, or without one, its level's. The site's book page
    shows the same sentence."""
    return manifest.get("reader") or cfg["levels"].get(manifest.get("level", ""), "")


def reuse(cfg: dict, wording: str = "full") -> str:
    """How the book may be reused, in the short or the full wording every page of the site uses ([reuse])."""
    return cfg["reuse"][wording].format(copyright=cfg["code_copyright"])


def byline(manifest: dict, cfg: dict) -> str:
    """House books name the publisher; other books name their authors."""
    authors = manifest.get("authors") or []
    names = [a if isinstance(a, str) else a.get("name", "") for a in authors] or [cfg["publisher"]]
    joined = names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    return f"By {joined}, with AI"


def readme(book: Book, cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    m, slug = book.manifest, book.slug
    repo = repo_url(slug, cfg)
    level = LEVELS.get(m.get("level", ""), "")
    who = reader(m, cfg)
    first_example = next((e.example_id for c in book.chapters for e in c.embeds), None)
    python = (book.root / "examples" / ".python-version")
    pins = book.root / "examples" / "requirements.txt"
    # PyTorch's CPU index beside PyPI: uv takes each package from the first index that has it unless told otherwise
    indexed = pins.exists() and any(line.strip().startswith("--extra-index-url") for line in pins.read_text().splitlines())
    data_cards = sorted(p.relative_to(book.root).as_posix() for p in (book.root / "examples" / "data").glob("*/README.md"))
    recorded = (book.root / "examples" / "data" / "recorded").is_dir()
    preview = m.get("status") == "draft"          # a draft: private, unpublished, with no cover, edition or pages yet
    home = _url(cfg, "book", book=slug)

    rows = []
    for c in book.chapters:
        number = int(re.match(r"\d+", Path(c.file).name).group(0)) if re.match(r"\d+", Path(c.file).name) else ""
        promise = book.bind(_first_sentence(c.body))
        title = (f"[{c.title}]({c.file})" if preview else
                 f"[{c.title}]({_url(cfg, 'chapter', book=slug, chapter_id=c.chapter_id)}) · [source]({c.file})")
        rows.append(f"| {number} | {title} | {promise} | {len(c.embeds)} |")

    checks = f"[![Checks]({repo}/actions/workflows/checks.yml/badge.svg)]({repo}/actions/workflows/checks.yml)"
    if preview:
        # A draft carries no images: its repository is private, its checks run only on pull requests, so the badge
        # has nothing to show, and the site that serves the mark isn't live yet.
        head = [f"{byline(m, cfg)} · **{level}**", "", m.get("summary", ""), "",
                f"**{cfg['draft_banner']}.** Its first edition is published once agents have reviewed every chapter and "
                f"every example passes. [How we make books]({_url(cfg, 'editorial')})", ""]
    else:
        head = [f"{byline(m, cfg)} · **{level}** · [Read it free online]({home})", "",
                f"[![The latest edition's stamp]({_url(cfg, 'stamp', book=slug)})]({home}) {checks}", "",
                m.get("summary", ""), "",
                f"**{cfg['disclosure']}** [How we make books]({_url(cfg, 'editorial')}) · [Check a copy]({_url(cfg, 'check')})", ""]
    out = ["<!-- Generated by re-check readme from book.toml, the chapters and the examples. Don't edit by hand. -->", ""]
    if not preview:
        out += [f'<p align="center"><a href="{home}"><img src="{_url(cfg, "cover", book=slug)}" width="220" '
                f'alt="Cover of {m["title"]}: its title punched in tape"></a></p>', ""]
    out += [
        f"# {m['title']}",
        "",
        *head,
        "## Who it's for",
        "",
        who,
        "",
        "## Contents",
        "",
        "| | Chapter | By the end, you can | Examples |",
        "| --- | --- | --- | --- |",
        *rows,
        "",
        "## Run the examples",
        "",
        "Every example runs offline, in a pinned environment, and its output must match the book's. With "
        "[uv](https://docs.astral.sh/uv/):",
        "",
        "```sh",
        f"uv venv --python {python.read_text().strip() if python.exists() else '3'}",
        "uv pip install -r examples/requirements.txt" + (" --index-strategy unsafe-best-match" if indexed else ""),
        f"cd examples && ../.venv/bin/python {first_example}.py" if first_example else "cd examples",
        "```",
        "",
    ]
    pinned = model_files.read(book.root) if (book.root / model_files.MODELS).exists() else []
    if pinned:
        size = model_files.total_bytes(pinned) / 2**20
        names = ", ".join(f"[{m.repo}](https://huggingface.co/{m.repo}/tree/{m.revision})" for m in pinned)
        which = "an open model, pinned" if len(pinned) == 1 else f"{len(pinned)} open models, each pinned"
        out += [f"The examples load {which} to an exact commit with every file's SHA-256 in `examples/models.toml`: "
                f"{names}. The first run "
                f"downloads {'it' if len(pinned) == 1 else 'them'} from Hugging Face (about {size:,.0f} MB); after that, "
                "the examples run offline.", ""]
    if recorded:
        # The same words for every book: what a book records differs (embeddings, an LLM's judgments, a model it
        # trains itself), so naming examples here would be untrue of some book. A book that also runs open models
        # live says "hosted": its examples do load a model.
        never = "never call a hosted model" if pinned else "never call a model"
        out += ["Model outputs are recorded once in `examples/data/recorded/`, each folder with a `manifest.json` that names "
                f"the model, its exact version and the script that recorded it, so the examples {never}. "
                "`recordings/` holds the scripts that record them again.", ""]
    if data_cards:
        out += ["Where the data comes from, and its licence: " + ", ".join(f"[`{p}`]({p})" for p in data_cards) + ".", ""]
    out += [
        "## How this book stays current",
        "",
        "When a library this book uses releases a new version, the examples that use it run again in the new version, "
        "and every example runs again each week. Agents draft "
        "any fix and check every change, and a change merges once its checks pass; one with a serious risk, such as a "
        "security or copyright problem, waits for a Rolling Edition maintainer. Anyone can check the book or correct it "
        "with a pull request. Each new edition is stamped with its date, its examples passing and what changed."
        + ("" if preview else f" [See what changed in each edition]({_url(cfg, 'changes', book=slug)})."),
        "",
        "## Contribute",
        "",
        f"- **Found an error?** [Report it]({report_error_url(slug, cfg)}) with the section's ID: the last part of the "
        f"link beside each heading on {cfg['site'].split('//')[1]}.",
        f"- **Fix it** with a pull request. Checks run every example and the [writing standards]({cfg['links']['writing_standards']}) "
        "automatically, and it merges once they pass.",
        f"- **Read [how to contribute]({cfg['links']['contributing']})** and the [code of conduct]({cfg['links']['conduct']}).",
        "",
        "Everyone whose change ships is credited by name or pseudonym in that edition.",
        "",
        "## Cite this book",
        "",
        ("Until its first edition, cite the book as a whole: GitHub's \"Cite this repository\" button, from "
         "`CITATION.cff`, does that. Once the book has an edition, every page gets a Cite button for that edition and section.")
        if preview else
        "Cite the edition you read: every page of the book has a Cite button with APA, Chicago, MLA and BibTeX for that "
        "edition and section. GitHub's \"Cite this repository\" button, from `CITATION.cff`, cites the book as a whole.",
        "",
        "## Licence",
        "",
        "Text: [CC BY 4.0](LICENSE). Code examples: [MIT](LICENSE-CODE)." + (" Data: see each data folder's README." if data_cards else ""),
        "",
        f"{reuse(cfg)} We'd be glad of a link back for the code, too.",
        "",
        "---",
        "",
        ("" if preview else f'<a href="{cfg["site"]}"><img src="{cfg["site"]}{cfg["paths"]["icon"]}" width="28" alt=""></a> ')
        + f"{cfg['about']} [{cfg['site'].split('//')[1]}]({cfg['site']})",
        "",
    ]
    return "\n".join(out)


def citation(book: Book, cfg: dict | None = None) -> str:
    """CITATION.cff for the book as a whole, without an edition: the site cites the edition you read."""
    cfg = cfg or load_config()
    m, slug = book.manifest, book.slug
    authors = [{"name": a if isinstance(a, str) else a.get("name", "")} for a in (m.get("authors") or [])] or [{"name": cfg["publisher"]}]
    url = _url(cfg, "book", book=slug)
    doc = {
        "cff-version": "1.2.0",
        "message": "To cite the edition you read, use the Cite button on any page of the book. To cite the book as a whole, use this.",
        "title": m["title"],
        "authors": authors,
        "abstract": m.get("summary", ""),
        "url": url,
        "repository-code": repo_url(slug, cfg),
        "license": ["CC-BY-4.0", "MIT"],
        "preferred-citation": {"type": "book", "title": m["title"], "authors": authors, "publisher": {"name": cfg["publisher"]},
                               "url": url, "notes": cfg["disclosure"]},
    }
    class Plain(yaml.SafeDumper):
        def ignore_aliases(self, data):   # write repeated values out in full, not as YAML anchors
            return True
    return ("# Generated by re-check readme from book.toml. Don't edit by hand.\n"
            + yaml.dump(doc, Dumper=Plain, sort_keys=False, allow_unicode=True, width=1000))


def renovate() -> str:
    """Every book's renovate.json: how Renovate proposes library releases, and how long it waits first."""
    text = data_path("renovate.json").read_text(encoding="utf-8")
    json.loads(text)                                  # fail here, not in Renovate, if the shared config is broken
    return text


def renovate_config() -> dict:
    return json.loads(renovate())


def licence_code(cfg: dict | None = None) -> str:
    cfg = cfg or load_config()
    return (TEMPLATES / "licenses" / "MIT.txt").read_text(encoding="utf-8").replace("Copyright (c) <year> <copyright holders>",
                                                                                  cfg["code_copyright"])


def weekly_cron(slug: str, cfg: dict | None = None) -> str:
    """When a book's weekly run of every example starts: [workflows] weekly_cron, its minute, hour and day of the week
    drawn from a hash of the book's slug, so the books' runs don't all start at once. The minute stays clear of the
    hour's first minutes ([workflows] weekly_minutes), when GitHub's scheduled runs are busiest. Never typed: the same
    slug always gives the same time."""
    cfg = cfg or load_config()
    w = cfg["workflows"]
    first, last = w["weekly_minutes"]
    n = int.from_bytes(hashlib.sha256(slug.encode()).digest()[:8], "big")
    minute = first + n % (last - first + 1)
    n //= last - first + 1
    hour, weekday = n % 24, (n // 24) % 7
    return w["weekly_cron"].format(minute=minute, hour=hour, weekday=weekday)


def workflows(cfg: dict | None = None, slug: str = "") -> dict[str, str]:
    """Every book's .github/workflows: checks.yml runs the standards repository's book checks on each pull request, the
    examples its change could affect, and every example once a week, at a time drawn from the book's slug
    (weekly_cron); labels.yml reruns the kind-label check when labels change. Without them a pull request gets no
    checks, so it can never be approved."""
    cfg = cfg or load_config()
    org = cfg["github"].rstrip("/").rsplit("/", 1)[-1]
    fill = {"{org}": org, "{weekly_cron}": weekly_cron(slug, cfg)}
    out = {}
    for path in sorted((TEMPLATES / "book" / "workflows").glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        for key, value in fill.items():
            text = text.replace(key, value)
        out[f".github/workflows/{path.name}"] = text
    return out


MAINTAINED = ".github/"            # generated files that change on a released book only with a maintainer's approval
FRONT_PAGE = ("README.md", "CITATION.cff", "LICENSE", "LICENSE-CODE", "renovate.json")


def generated_names() -> set[str]:
    """The paths `files` writes in every book: the front page, the licences, renovate.json and the workflows."""
    return set(FRONT_PAGE) | {f"{MAINTAINED}workflows/{p.name}" for p in (TEMPLATES / "book" / "workflows").glob("*.yml")}


def files(book: Book, cfg: dict | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    return {"README.md": readme(book, cfg), "CITATION.cff": citation(book, cfg),
            "LICENSE": (TEMPLATES / "licenses" / "CC-BY-4.0.txt").read_text(encoding="utf-8"), "LICENSE-CODE": licence_code(cfg),
            "renovate.json": renovate(), **workflows(cfg, book.slug)}


def own_licences(cfg: dict | None = None) -> dict[str, str]:
    """This repository's licences: MIT for its code, CC BY 4.0 for the writing standards and the prompts."""
    return {"LICENSE": licence_code(cfg), "LICENSE-TEXT": (TEMPLATES / "licenses" / "CC-BY-4.0.txt").read_text(encoding="utf-8")}


def sync(root: Path, texts: dict[str, str], command: str, write: bool = False) -> list[str]:
    """Problems with generated files under root, or none after writing them."""
    problems = []
    for name, text in texts.items():
        path = root / name
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        else:
            problems.append(f"{name} is {'missing' if current is None else 'out of date'}; run {command} --write")
    return problems


def check(book: Book, write: bool = False, cfg: dict | None = None) -> list[str]:
    """Problems with the generated files, or none after writing them."""
    return sync(book.root, files(book, cfg), "re-check readme", write)


def released(book: Book) -> bool:
    return book.manifest.get("status", "draft") != "draft"


def held_for_maintainer(book: Book, problems: list[str]) -> tuple[list[str], list[str]]:
    """(problems, warnings): on a released book, an out-of-date or missing workflow is a warning, since only a
    maintainer-approved pull request changes it there; on a draft, everything is a problem."""
    if not released(book):
        return problems, []
    later = [p for p in problems if p.startswith(MAINTAINED)]
    return ([p for p in problems if p not in later],
            [p.replace("; run re-check readme --write", "; a maintainer-approved pull request brings it up to date "
                       "(re-check readme --write writes it)") for p in later])


def check_own_licences(write: bool = False, cfg: dict | None = None) -> list[str]:
    return sync(TEMPLATES.parent, own_licences(cfg), "re-check licences", write)
