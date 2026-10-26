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
| `re_standards/bookfmt.py`, `sections.py` | The book format: chapters, sections, examples and their frozen IDs, and `sections.json`, with two hashes for each chapter opening and section: `sha256`, of its source, and `rendered_sha256`, of its text as read, with every binding filled in from that edition's recorded outputs and pins. A section changed when its text as read did, so a library update that moves a number an example prints changes it |
| `re_standards/examples.py`, `harness.py`, `runtime/Dockerfile` | Runs every example in its pinned runtime and compares its output |
| `re_standards/resolve.py`, `data/examples.toml` | Before the runtime is built, reads the pins with a resolver (uv, pinned with this package) for that runtime's Python and platform. Pins that can't be installed together fail the examples check in plain words, naming the conflict, as their own outcome, `unsatisfiable`: in the `--report` JSON, with the resolver's message, and as an annotation on the check run. No example runs then, so it's never mistaken for an example's failure |
| `writing/` | The writing standards every book follows: rules with IDs, reasons and checks, and annotated exemplars |
| `data/writing.toml` | Limits and word lists for `re-check style`, the lint half of the writing standards |
| `data/drafting.toml` | The model bar: the models books may be drafted with. Open models are for recorded outputs only (W-48) |
| `prompts/` | The agents' prompts, published so anyone can read what an agent was told |

Run the checks on a book checkout with `re-check`:

```sh
pip install -e .                       # from this folder
re-check examples --book path/to/book  # every example, in its pinned runtime (--backend venv locally); --report FILE writes
                                       # the outcome (passed, failed, unsatisfiable or error) and each example's result
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
