# Rolling Edition standards

How a Rolling Edition book gets verified, in the open. This is the public, read-only `standards` repository: every book's checks, the writing standards and the reference encoder, published from Rolling Edition's platform. To suggest a change, open an issue.

| Path | What |
| --- | --- |
| `.github/workflows/book-checks.yml` | The reusable workflow every book pull request runs: examples, book manifest, section IDs |
| `.github/workflows/kind-label.yml` | The kind-label check, rerun whenever labels change |
| `data/taxonomy.json` | Areas and skills, the catalog's source of truth, anchored to Wikipedia and Wikidata |
| `data/review-tiers.toml` | The three review tiers, the file classes triage reads, and the rules that flag a serious risk |
| `re_standards/tape.py`, `cover.py` | The reference encoder: title tape, edition code, fingerprint, history tape and cover SVG. Anyone can decode a tape or recompute a code with it |
| `data/cover-glyphs.json` | The letter outlines a cover file draws its text with, since an image can't load a web font. Generated from the fonts the site uses |
| `re_standards/catalog.py` | Validates the taxonomy and `book.toml`, and builds the catalog |
| `re_standards/bookfmt.py`, `sections.py` | The book format: chapters, sections, examples and their frozen IDs, and `sections.json` |
| `re_standards/examples.py`, `harness.py`, `runtime/Dockerfile` | Runs every example in its pinned runtime and compares its output |
| `writing/` | The writing standards every book follows: rules with IDs, reasons and checks, and annotated exemplars |
| `data/writing.toml` | Limits and word lists for `re-check style`, the lint half of the writing standards |
| `data/drafting.toml` | The model bar: the models books may be drafted with. Open models are for recorded outputs only (W-48) |
| `prompts/` | The agents' prompts, published so anyone can read what an agent was told |

Run the checks on a book checkout with `re-check`:

```sh
pip install -e .                       # from this folder
re-check examples --book path/to/book  # every example, in its pinned runtime (--backend venv locally)
re-check manifest --book path/to/book
re-check section-ids --book path/to/book --base-ref <base commit> --previous latest
re-check kind-label --labels kind:deps
re-check style --book path/to/book    # the lint rules of the writing standards
re-check wikidata                      # needs the internet; --write fills Wikidata IDs
python -m re_standards.tape code SLUG EDITION COMMIT_SHA
```

## Licence

Code: [MIT](LICENSE). The writing standards in `writing/` and the agents' prompts in `prompts/`: [CC BY 4.0](LICENSE-TEXT). `re-check licences` writes both files.

`data/mark-outlines.json` and `data/cover-glyphs.json` hold letter outlines from two typefaces, each under the SIL Open Font License 1.1: Literata ([licence](templates/licenses/OFL-Literata.txt)), and IBM Plex Mono ([licence](templates/licenses/OFL-IBM-Plex-Mono.txt)), whose reserved name the outlines don't take. The other texts in `templates/licenses/`, and the Contributor Covenant in `templates/community/`, belong to their publishers: `templates/fetch.py` copies them verbatim.
