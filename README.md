# Rolling Edition standards

How a Rolling Edition book gets verified, in the open. This is the public, read-only `standards` repository: every book's checks, the writing standards and the reference encoder, published from Rolling Edition's platform. To suggest a change, open an issue.

| Path | What |
| --- | --- |
| `.github/workflows/book-checks.yml` | The reusable workflow every book pull request runs: examples, book manifest, section IDs |
| `.github/workflows/kind-label.yml` | The kind-label check, rerun whenever labels change. A pull request that changes only the book's narration files (`narration/`) passes without a kind label: the page doesn't change, so it has no kind of change and rides with the next edition |
| `data/taxonomy.json` | Areas and skills, the catalog's source of truth, anchored to Wikipedia and Wikidata |
| `data/review-tiers.toml` | The three review tiers, the file classes triage reads, and the rules that flag a serious risk |
| `re_standards/tape.py`, `cover.py` | The reference encoder: title tape, edition code, fingerprint, history tape and cover SVG. Anyone can decode a tape or recompute a code with it |
| `data/cover-glyphs.json` | The letter outlines a cover file draws its text with, since an image can't load a web font. Generated from the fonts the site uses |
| `re_standards/catalog.py` | Validates the taxonomy and `book.toml`, and builds the catalog |
| `re_standards/bookfmt.py`, `sections.py` | The book format: chapters, sections, examples and their frozen IDs, and `sections.json`, with three hashes for each chapter opening and section: `sha256`, of its source; `rendered_sha256`, of its text as read, with every binding filled in from that edition's recorded outputs and pins; and `content_sha256`, the same with each version binding left as written. A section changed when its text as read did, so a library update that moves a number an example prints changes it; when only a version number moved, its content didn't, and the change is a quiet one |
| `re_standards/examples.py`, `harness.py`, `runtime/Dockerfile` | Runs every example in its pinned runtime and compares its output |
| `re_standards/resolve.py`, `data/examples.toml` | Before the runtime is built, reads the pins with a resolver (uv, pinned with this package) for that runtime's Python and platform. Pins that can't be installed together fail the examples check in plain words, naming the conflict, as their own outcome, `unsatisfiable`: in the `--report` JSON, with the resolver's message, and as an annotation on the check run. No example runs then, so it's never mistaken for an example's failure |
| `writing/` | The writing standards every book follows: rules with IDs, reasons and checks, and annotated exemplars |
| `data/writing.toml` | Limits and word lists for `re-check style`, the lint half of the writing standards |
| `re_standards/spoken.py`, `data/narration.toml` | The spoken script narration reads, built by code from each chapter, and the shared rules it reads with: templates, common terms, symbols and numbers as words (see Narration) |
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
re-check kind-label --event "$GITHUB_EVENT_PATH" --book .   # a pull request's labels, and the files it changes
re-check style --book path/to/book    # the lint rules of the writing standards
re-check narration --book path/to/book # terms no rule reads, and examples, blocks and tables with no description (warns)
re-check wikidata                      # needs the internet; --write fills Wikidata IDs
python -m re_standards.tape code SLUG EDITION COMMIT_SHA
```

## Narration

Narration reads a book's text word for word, and never its code, output or tables. `re_standards/spoken.py` builds each chapter's spoken script by code, never by a model, from the parsed chapter with every binding filled in: one line per recorded paragraph, list item, heading or element, each with its kind and the section it belongs to.
- Headings, prose, quotes, list items and working rules are read as written, links by their text.
- Inline code is read through the lexicon, or by its parts: `lib.store.product_text` is "lib dot store dot product text".
- Numbers, years, decimals, signs, symbols and edition codes are read as words: 0.615 is "zero point six one five", (Chen et al., 2022) is "twenty twenty-two", 2026.10.6 is "twenty twenty-six point ten point six". A number a binding fills in is a count, never a year.
- Each example, fenced block and table is read as the description the book writes for it, or announced where it has none ("Example: inverted index by hand. Its code and output are on the page.").
- A chapter opens with its number and title, the book's title, the edition and the disclosure, and ends with its number. The whole-book file opens and closes with credits.

Every word is the edition's text or a template in `data/narration.toml`, whose `rules_version` a recorded paragraph's key includes, so a change to how the rules read means recording again.

A book's narration lives in `narration/`, beside its chapters, so adding or editing a description never changes a section's hash:

| File | What |
| --- | --- |
| `narration/lexicon.toml` | The book's own readings: `[terms]`, exact and case-sensitive, such as `"nDCG@10" = "N D C G at ten"`; `[words]`, whole words in any case, such as the words of an example's ID. They add to the shared terms, and win where both have one |
| `narration/{chapter_id}.toml` | The chapter's descriptions: `[examples.{example_id}]`, and `[[blocks]]` and `[[tables]]`, each with `section`, the section's ID, or the chapter's for its opening text, and `starts`, the start of its first line as written. `blocks` covers every fenced block that isn't an example, formulas included. Each has `say`, which may use `{{out:…}}` and `{{version:…}}` |

```toml
[examples.ndcg-for-one-query]
say = "The code takes BM25's top ten for clear shower curtain, adds up each grade divided by a log discount, does the same for the best possible top ten, and prints their ratio: {{out:ndcg-for-one-query:ndcg@10}}."

[[blocks]]
section = "score-one-ranking"
starts = "DCG@10  = sum over positions"
say = "D C G at ten is the sum, over positions one to ten, of each grade divided by log base two of the position plus one."

[[tables]]
section = "check-stemming-on-test"
starts = "| Measure |"
say = "A table of the mean difference, interval and p-value of each change this chapter tested."
```

`re-check narration` lists, per chapter, every term no rule reads (a word that still holds a digit or a character such as `_`, `/` or `<`, or is written in capitals or camelCase, and inline code named whole), every example, block and table with no description, every description whose example, section or first line no longer matches, and bindings that don't resolve. It warns, and exits 0 unless `--strict`. `--script` prints the spoken script instead, for a chapter with `--chapter` or the whole book, with `--edition` for the opening.

## Licence

Code: [MIT](LICENSE). The writing standards in `writing/` and the agents' prompts in `prompts/`: [CC BY 4.0](LICENSE-TEXT). `re-check licences` writes both files.

`data/mark-outlines.json` and `data/cover-glyphs.json` hold letter outlines from two typefaces, each under the SIL Open Font License 1.1: Literata ([licence](templates/licenses/OFL-Literata.txt)), and IBM Plex Mono ([licence](templates/licenses/OFL-IBM-Plex-Mono.txt)), whose reserved name the outlines don't take. The other texts in `templates/licenses/`, and the Contributor Covenant in `templates/community/`, belong to their publishers: `templates/fetch.py` copies them verbatim.
