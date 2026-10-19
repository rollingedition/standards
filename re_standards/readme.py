"""A book repository's front page, generated: README.md, CITATION.cff, LICENSE, LICENSE-CODE and renovate.json.

Everything comes from the repository itself (book.toml, the chapters, the examples) and from
data/readme.toml, so nothing in these files is typed by hand. renovate.json is data/renovate.json, the same for
every book: among other things, it holds a new library release back until it is old enough. Facts that change with each edition
(its number, date, examples passing) stay on the site: the README shows them through the site's stamp
badge and latest cover, so it doesn't change at every release. `re-check readme` fails when a file is
out of date; `--write` regenerates them. `re-check licences` does the same for this repository's own licences.

The wording follows open verification: agents publish, anyone checks or corrects, and only serious
risks wait for a person. It never says that a person approved anything.
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import yaml

from . import data_path
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


def _first_sentence(chapter_body: str) -> str:
    """The first sentence after the chapter's title: by W-2, what the reader can do by its end."""
    paragraphs = [p.strip() for p in chapter_body.split("\n\n") if p.strip() and not p.lstrip().startswith("#")]
    if not paragraphs:
        return ""
    text = " ".join(paragraphs[0].split())
    match = re.search(r"(?<=[.!?])\s+(?=[A-Z])", text)
    sentence = text[:match.start()] if match else text
    return PROMISE.sub("", sentence).rstrip(".")


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
        "uv pip install -r examples/requirements.txt",
        f"cd examples && ../.venv/bin/python {first_example}.py" if first_example else "cd examples",
        "```",
        "",
    ]
    if recorded:
        out += ["Model outputs, such as embeddings and LLM judgments, are recorded once in `examples/data/recorded/`, each "
                "with a `manifest.json` naming the exact model and prompts, so the examples never call a model. "
                "`recordings/` holds the scripts that record them again.", ""]
    if data_cards:
        out += ["Where the data comes from, and its licence: " + ", ".join(f"[`{p}`]({p})" for p in data_cards) + ".", ""]
    out += [
        "## How this book stays current",
        "",
        "When a library this book uses releases a new version, every example runs again in the new version. Agents draft "
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


def files(book: Book, cfg: dict | None = None) -> dict[str, str]:
    cfg = cfg or load_config()
    return {"README.md": readme(book, cfg), "CITATION.cff": citation(book, cfg),
            "LICENSE": (TEMPLATES / "licenses" / "CC-BY-4.0.txt").read_text(encoding="utf-8"), "LICENSE-CODE": licence_code(cfg),
            "renovate.json": renovate()}


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
            path.write_text(text, encoding="utf-8")
        else:
            problems.append(f"{name} is {'missing' if current is None else 'out of date'}; run {command} --write")
    return problems


def check(book: Book, write: bool = False, cfg: dict | None = None) -> list[str]:
    """Problems with the generated files, or none after writing them."""
    return sync(book.root, files(book, cfg), "re-check readme", write)


def check_own_licences(write: bool = False, cfg: dict | None = None) -> list[str]:
    return sync(TEMPLATES.parent, own_licences(cfg), "re-check licences", write)
