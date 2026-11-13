# Exemplar: sources cited in passing

A paragraph from a released book, before and after it was rewritten to W-62, with notes. It's from "Finding personal data", chapter 3 of *Data governance as code*, which runs Presidio, an open-source library for finding personal data, with no network access. `{{version:…}}` is a version binding (W-25).

Every claim keeps its source (W-28). What changes is how the source appears: the claim is said in the book's own words, and the source is named in the sentence and linked, as a textbook cites. A quotation is kept only where its wording is the point.

---

## Before

`lib.pii.detector` configures the engine explicitly instead, with `NoOpNlpEngine`, which "loads no external model" ([source](https://github.com/data-privacy-stack/presidio/blob/2.2.364/presidio-analyzer/presidio_analyzer/nlp_engine/no_op_nlp_engine.py)). The cost is context words. Presidio raises a pattern's score when a word such as "phone" appears near the match, by comparing "each recognizer's context terms with the lemma of each token in the sentence" ([Presidio docs](https://github.com/data-privacy-stack/presidio/blob/2.2.364/docs/tutorial/06_context.md)), and with no model there are no lemmas, so the engine "cannot use context words from the analyzed text". One more call reaches the network: the email recognizer checks domains with tldextract ([source](https://github.com/data-privacy-stack/presidio/blob/2.2.364/presidio-analyzer/presidio_analyzer/predefined_recognizers/generic/email_recognizer.py)), which "fetches the latest Public Suffix List on first use" ([tldextract {{version:tldextract}} README](https://github.com/john-kurkowski/tldextract/blob/5.4.0/README.md)). An empty `TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS` turns that off if it's set "before importing `tldextract`", as the README says, and importing Presidio imports tldextract. So `lib/__init__.py`, which Python runs before any module of the book's `lib`, sets it. When an example imported Presidio first, the same file replaces tldextract's shared extractor ([source](https://github.com/john-kurkowski/tldextract/blob/5.4.0/tldextract/tldextract.py)) with one that has no URLs. `lib.pii` refuses to load if any remain, and tldextract uses the copy it ships with, so the same text gives the same answer on every machine.

## After

`lib.pii.detector` configures the engine itself, with `NoOpNlpEngine`, which loads no language model at all ([Presidio's `NoOpNlpEngine`](https://github.com/data-privacy-stack/presidio/blob/2.2.364/presidio-analyzer/presidio_analyzer/nlp_engine/no_op_nlp_engine.py)). What that costs is context. With a model, Presidio raises a pattern's score when a word such as "phone" appears near the match, by comparing the words around it with each recognizer's context terms; without one, it has no words to compare ([Presidio's tutorial on context](https://github.com/data-privacy-stack/presidio/blob/2.2.364/docs/tutorial/06_context.md)). The engine has one more way onto the network. Its [email recognizer](https://github.com/data-privacy-stack/presidio/blob/2.2.364/presidio-analyzer/presidio_analyzer/predefined_recognizers/generic/email_recognizer.py) checks domains with tldextract, which fetches the Public Suffix List the first time it's used, unless `TLDEXTRACT_PUBLIC_SUFFIX_LIST_URLS` is empty before tldextract is imported ([tldextract {{version:tldextract}}'s README](https://github.com/john-kurkowski/tldextract/blob/5.4.0/README.md)). Importing Presidio imports tldextract, so `lib/__init__.py`, which runs before any of the book's modules, empties the variable, and in case an example imported Presidio first, it replaces tldextract's shared extractor with one that has no URLs. `lib.pii` refuses to load if a URL remains. tldextract then reads the copy of the list it ships with, and the same text gives the same answer on every machine.

---

## Notes

| Rule | What changed, and why |
| --- | --- |
| W-62 Cite the way a textbook does | Five quotations became none. Each said something the book can say in its own words, and the reader loses nothing: the link is on the claim. Each source is named in the sentence ("Presidio's tutorial on context", "tldextract's README") instead of hiding behind "source". |
| W-62, links | Six links became four, one on each claim. The link on tldextract's source code went: the book's own `lib/__init__.py` is what replaces the extractor, and the reader can open it. |
| W-28 Every claim shown or sourced | Unchanged. Each claim about Presidio or tldextract still has its source at the pinned version. |
| W-67 Write as the author | "What that costs is context." and "The engine has one more way onto the network." are short sentences that tell the reader where the paragraph turns. The long sentence about the environment variable now runs in the order things happen: Presidio imports tldextract, so the variable has to be set first. |

When to keep a quotation: when the wording itself is what the reader needs, such as a definition the chapter relies on, or a specification's MUST or SHOULD. Then quote it once, name its source in the sentence, and say in your own words what it means for the case.
