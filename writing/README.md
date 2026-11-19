# Writing standards

How a Rolling Edition book is written. These rules apply to every book, whoever writes the text: our agents drafting a book, or a contributor fixing one paragraph. Critic agents check drafts against them, and anyone who reads a book can use them to correct it.

Draft. Rules may change before the first book is drafted with them.

**How to read a rule.** Each rule has an ID, the reason for it, and how it is checked:

- **lint:** an automatic check fails the pull request
- **critic:** a critic agent checks the draft and cites the rule's ID in the review packet
- **reviewer:** a judgement no automatic check can make: critic agents apply it, and any reader can correct a book that breaks it

Lint checks run with `re-check style --book PATH`. Those marked "when built" are planned, so a critic checks them until then. Limits and word lists are defaults, kept in `data/writing.toml`.

**Exemplars.** The sections in `exemplars/` show the rules applied, with notes. Drafting agents imitate them, and critics compare drafts against them. If an exemplar and a rule disagree, the rule wins; report the disagreement.

| Exemplar | What it shows |
| --- | --- |
| `explain-then-case.md` | The house pattern: explain, make it concrete, close with the working rule (W-8) |
| `chapter-opening.md` | A chapter's opening: the promise, the problem in the case, then the plan (W-2, W-64, W-65) |
| `results-paragraph.md` | Results that lead with the point, and a yes or no that's asserted (W-61) |
| `sourced-paragraph.md` | Sources cited in passing, as a textbook does (W-62) |
| `way-into-an-example.md` | Leading into an example and reading its output with the reader (W-63, W-67) |
| `commented-example.md` | An example that explains itself (W-68) |

The last five are passages from released books, before and after, so a writer sees what changes and why.

## 1. The reader and the promise

**W-1 Write for the book's level.** Every book is written at one of two levels, set by `level` in `book.toml`:

- **Foundations:** the reader is comfortable with Python and with handling data, and is new to the field. Define every term the field introduces, and build each idea up from scratch before using the library that does it (W-46).
- **In practice:** the reader already works in the field. Assume its core concepts and link to a Foundations book's sections for them. Spend the words on trade-offs, failure modes, measurement and operations (W-47).

Either way, don't explain what a DataFrame is in a book about search.
*Why:* one clear reader keeps the depth and the length consistent. *Check:* reviewer.

**W-2 State the promise.** A book's first page names its reader, its prerequisites and what the reader will be able to build. Each chapter opens with one or two sentences on what the reader can do by its end.
*Why:* readers, and agents choosing sections, decide in seconds whether this is the right text. *Check:* critic.

**W-3 One capability per chapter, one idea per section.** If a section heading needs "and", split the section.
*Why:* small units are easier to learn, review, cite and update. *Check:* critic.

**W-60 A summary in the catalog's shape.** The summary in `book.toml` is one sentence in three parts: what the book teaches, in the reader's words; after a colon, the main things it covers, in the book's order; and what it works on, its case, data or tools. Aim for about 40 words, as the other books' summaries run, so the catalog reads evenly; there's no fixed limit. Write "How search engines find and rank results, and how to measure whether a change helps: lexical, semantic and hybrid retrieval, reranking with learned models and LLMs, and judgments from people and LLMs, on a real product catalog." Not a tagline, such as "Forecasts you can trust", and not every chapter in turn.
*Why:* the catalog, the book's page, search results and the book's repository show it beside the other books'. *Check:* `re-check manifest` notes a summary far from the usual length (`[summary]` in `data/writing.toml`) and never fails for it; critic for the rest.

## 2. Structure

**W-4 The whole result first.** Chapter 1 builds a rough but working version of the book's end result, end to end. Each later chapter makes one part of it solid. Chapter 1's title names what the reader builds or the question it answers, in the book's own terms, as "Predicting the next word" does. Never call it "end to end": that describes every first chapter, so it says nothing about this one.
*Why:* a reader who has seen the whole knows why each part matters, and a title that could open any book doesn't tell them what this one builds. *Check:* reviewer; lint for the title while a book is drafted (`re-check style`; the phrases are in `data/writing.toml`).

**W-5 One running case.** Each book follows one plausible, generic case from start to finish, such as an online shop's orders, a support team's tickets or a recipe site's search. Use public or generated data. The introduction describes the case once and names it (W-49), and every chapter moves it forward.
*Why:* a single case gives every idea a concrete place to land, and lets examples build on each other. *Check:* critic.

**W-6 Chapter shape.** A chapter runs:

1. what you'll be able to do
2. the problem, as it shows up in the case
3. the sections
4. what goes wrong in production
5. the decisions the chapter made, in a short list

A chapter may skip a part. It never adds others: no history lessons, no "fun facts", no previews of later chapters beyond one sentence.
*Why:* a predictable shape lets readers skim and lets agents check completeness. *Check:* critic.

**W-7 Length.** A chapter runs 3,000 to 6,000 words of prose, and a `##` section, with its subsections, 200 to 900. A book has 5 to 12 chapters.
*Why:* short enough to verify, long enough to teach. *Check:* lint (`re-check style`).

## 3. Explaining, then making it concrete

**W-8 Explain, then make it concrete.** This is the house pattern for every section:

1. **Explain** the idea in general terms, in a paragraph or two: what it is, and why it matters.
2. **Make it concrete** with the running case: what is at stake in the case, the example, its output, and what that output means for the case.
3. **Close with the working rule** (W-10).

*Why:* the explanation gives the reader something to hang the case on, and the case makes the idea stick. *Check:* critic.

**W-9 Show the failure.** When the obvious approach fails, run it and show the real failure before the fix: the error, the wrong number or the slow timing.
*Why:* a visible failure is what makes a fix worth reading, and readers will meet it in their own work. *Check:* critic.

**W-10 End with the working rule.** A section ends with its working rule: a paragraph that opens with **Working rule:** and then says, in full sentences, what to do, when, and when to do something else. A `###` subsection may close with a rule of its own. A section that ends in a list or a table, such as a chapter's summary, needs none.
*Why:* readers act on rules, and reviewers can check them. It's a working rule because it holds until your own measurements say otherwise. The sites show it as a quiet panel with the label on a line of its own, so a reader skimming a chapter can find it, and the rule's first word takes a capital. *Check:* lint for the label and its place (`re-check style`; the label is in `data/writing.toml`); critic for the rule itself.

**W-11 Predict, then run, at most once per chapter.** At a chapter's turning point, ask the reader to predict an output before the example that shows it, in words of the chapter's own (W-63). Foundations books do this in most chapters; In practice books rarely.
*Why:* predicting before seeing makes the key idea stick, but asked often it turns into a quiz. *Check:* critic.

**W-12 No characters.** The reader is "you", and the running case supplies the stakes. No named personas, dialogue or narrator.
*Why:* characters pad the text and age badly across editions. *Check:* critic.

**W-13 Take positions.** Recommend a default, state its trade-offs, and say when to choose differently. Use "we recommend" for judgement, and state what a library does as plain fact. Never list options without a recommendation.
*Why:* readers come for judgement they can trust, and a stated position can be reviewed. *Check:* reviewer.

**W-14 Math: words, formula, code.** Give the intuition in words, then the formula, then code that computes it on the case's data.
*Why:* each form checks the others, and the code proves the formula. *Check:* critic.

**W-15 Analogies sparingly.** Use one only where it shortens the explanation, and say where it breaks.
*Why:* an analogy that is pushed too far teaches the wrong model. *Check:* critic.

**W-16 Define terms at first use in each chapter.** After that, link to the definition.
*Why:* sections are read on their own (W-40). *Check:* critic.

## 4. Examples

**W-17 Every example runs.** Examples use pinned versions, run offline and are deterministic, with fixed seeds. Their output doesn't depend on Python's hash seed: sort a set, or anything built from one, before printing it. The output in the book is the output the example produced.
*Why:* this is the promise on every stamp, and a reader's Python picks a new hash seed for every run. *Check:* lint (`re-check examples`; a draft's under two hash seeds, `--seeds 0,1`); while a book that started from the kit is drafted, `re-check style` also refuses examples that read the clock or the memory in use, print an unordered result (a set, a directory listing, workers' results as they finish) without sorting it, or import a numerical library before `lib`, which fixes threads and seeds first.

**W-18 One idea per example.** Keep an example to about 30 lines. Longer setup moves into a shared module the reader can open. Its docstring and comment lines don't count (W-68).
*Why:* the reader should see the idea, not the scaffolding. *Check:* lint for length, comments aside (`re-check style`); critic for the idea.

**W-19 Examples build on each other.** Use the same data and the same names from chapter to chapter, through the running case.
*Why:* readers carry their understanding forward instead of re-reading setup. *Check:* critic.

**W-20 Realistic data, small sizes.** Data looks like the real thing, with messy values, realistic column names and skew, and is small enough to run in seconds. Use public or generated data only, and state its source and licence.
*Why:* toy data hides the problems the book exists to solve. Large data slows every check. *Check:* reviewer.

**W-21 Print what the prose discusses.** An example's output shows the values the text talks about, and little else.
*Why:* readers compare output to text. Noise hides the point. *Check:* critic.

**W-22 Current idioms.** Write code the library's documentation recommends at the pinned version. Deprecated APIs aren't allowed: warnings fail the run.
*Why:* readers copy examples into their own work. *Check:* lint (when built: warnings as errors); critic.

**W-23 Names are words.** Variables, columns and functions use real words, and the prose uses the same names.
*Why:* the text and the code should read as one. *Check:* critic.

## 5. Time, versions and numbers

A rolling book is read as current in every edition. These rules keep its text true when the libraries it teaches change.

**W-24 No time words.** Never write "recently", "currently", "as of this writing", "the latest", "modern", "nowadays", "state of the art" or "soon". Use "now" and "new" only for steps in a procedure ("the column is now numeric"), never for the state of a library or the field. Describe what the library does at the pinned version.
*Why:* time words go stale without anyone noticing. *Check:* lint for the listed words (`re-check style`); critic for "now" and "new".

**W-25 Never type a version.** Write `{{version:pandas}}` for a pinned package and `{{version:python}}` for the pinned Python. The build fills them in from `examples/requirements.txt` and `examples/.python-version`, so an update changes every mention at once.
*Why:* generate, never type. *Check:* lint (`re-check style`).

**W-26 Bind numbers from outputs.** When prose quotes a value an example printed, the example prints it on its own labelled line, such as `unreadable amounts: 1`. The prose then writes `{{out:fix-types:unreadable amounts}}`, and the build fills in the value from the recorded output. A yes or no is asserted, not bound (W-61).
*Why:* a library update can change an output, and a typed number would then contradict the example beside it. *Check:* lint (`re-check style` fails any binding that doesn't resolve to exactly one line).

**W-27 Name deprecations.** When the pinned version warns that a behaviour will change, say so in one sentence and show the replacement.
*Why:* the next edition will need it, and readers on newer versions need it now. *Check:* critic.

## 6. Claims and sources

**W-28 Every claim about a tool is shown or sourced.** A claim about how a library or tool behaves is either shown by an example in the book, or backed by a primary source for the pinned version: its documentation, changelog, specification or source code.
*Why:* this is the difference between a verified book and a plausible one. *Check:* critic, which extracts claims and resolves sources for the review packet.

**W-29 Citations must resolve.** Every link and reference must open and support the claim it is attached to. Never cite from memory.
*Why:* invented references are the best-known failure of AI-drafted books. *Check:* lint (when built) that the source resolves; critic that it supports the claim.

**W-30 Secondary sources never stand alone.** Blogs, answers and tutorials may add context, but never carry a claim by themselves.
*Why:* they go stale and repeat each other's errors. *Check:* critic.

**W-31 Separate measurement from judgement.** A benchmark states its setup and runs as an example. A rule of thumb is labelled as one.
*Why:* readers should know which numbers they can reproduce. *Check:* critic.

**W-32 Original text.** No passage may closely follow a published source. When wording matters, quote briefly and attribute it.
*Why:* copyright, and trust. *Check:* lint (when built: similarity check before every stamp).

**W-69 Research changes a book only as far as its evidence goes.** A paper is a hypothesis until the book can show it. What a result may change depends on how settled it is:
- A single preprint without code changes nothing.
- A single paper with code may be mentioned in passing, as recent and preliminary ("a 2026 preprint reports…"), or added as a caution. It changes no recommendation.
- A result the book reproduces on its own case, with an example, may become a measured claim. The number is the book's own; the paper is cited as where the idea came from.
- A recommendation (W-13) changes only when a result has been reproduced by others, or peer-reviewed and supported by maintained libraries, and the book reproduces it on its own case. Reversing a recommendation needs more evidence than adding a caution.

When studies disagree, give both with their setups, and make the recommendation depend on what separates them, measured on the book's case where possible (W-31).

Weigh a study by its evidence, not its authors:
- whether others have reproduced it;
- whether its code and data are open;
- online experiments over offline metrics;
- a scale and setting close to the reader's;
- any stake the authors have in the result.

Label a preprint as one, and say when a study's authors make the product it measures. Never copy a number from a paper into the book's results: results are the book's own runs.
*Why:* readers trust a book to say what's established. A single preprint can be wrong, and results often don't carry over between scales and settings. *Check:* critic, and the researcher's labels for how settled each source is.

## 7. Style

**W-33 Voice.** Precise, generous and plain, like a senior engineer explaining something to a capable colleague. Use short sentences, exact numbers and no hype.
*Why:* readers trust exact claims, not enthusiasm. *Check:* reviewer.

**W-34 Use "we" for Rolling Edition and "you" for the reader.** *Check:* critic.

**W-35 Banned words.** Never write "simply", "just", "easy" or "easily", "obviously", "clearly", "of course", "powerful", "seamless", "cutting-edge", "revolutionary", "leverage" (as a verb), "utilize", "dive into" or "delve". Never use exclamation marks, emoji, or superlatives as praise, such as "the best", "ultimate" or "world-class". A superlative that reports a measurement, such as "the best-scoring model", is fine.
*Why:* minimizers make readers who struggle feel slow, and hype erodes trust. *Check:* lint for the listed words, exclamation marks and emoji (`re-check style`); critic for superlatives.

**W-36 Sentence case for headings.** Use title case only for book titles. Names keep their capitals; the linter's list of them is in `data/writing.toml`. *Check:* lint (`re-check style`).

**W-37 Active voice, present tense.** *Check:* critic.

**W-38 Code font for code.** Functions, columns, arguments and values go in code font. Library names stay in plain text: pandas, scikit-learn. *Check:* critic.

**W-39 Accessible by default.** Every figure has alt text that states its point. Never use colour alone to carry meaning. Every table has a header row.
*Why:* every reader, and every agent, should get the same content. *Check:* lint for alt text (`re-check style`); critic for the rest.

## 8. Written for agents too

Agents read sections, not books, so every section must work when it is read alone.

**W-40 Sections stand alone.** A reader or an agent landing on any section can follow it. Restate the case's context in a sentence where needed. Never write "as we saw above" or "below" without a link.
*Why:* most of a book's reads will be single sections, fetched by search or by an agent. *Check:* critic.

**W-41 Headings say what the section does.** Write "Coerce bad values, then count them", not "A tricky column".
*Why:* headings are what readers and agents navigate by. *Check:* critic.

**W-42 Keep IDs.** Every chapter has a `chapter_id`, and every `##` and `###` heading has an explicit `{#section-id}`. IDs never change once created.
*Why:* citations, links and the history tape depend on them. *Check:* lint (`re-check section-ids`).

## 9. What a book never contains

**W-43 Nothing generated by hand.** Never write an edition stamp, edition code, "verified" claim, reviewer name or version history by hand. The release pipeline generates them.
*Check:* lint (when built).

**W-44 The AI is named once, in the disclosure.** The text doesn't mention how it was drafted. "Written with AI. Verified by people." is generated beside the stamp.
*Check:* critic.

**W-45 No private material.** No personal details, no material from anyone's employer, and no data without a stated public source or generator.
*Check:* lint (forbidden-terms scan); reviewer.

## 10. Levels and recorded outputs

**W-46 Foundations builds before it borrows.** In a Foundations book, implement each core idea from scratch, small and readable, before using the library that does it properly. Then show that the library gives the same result.
*Why:* readers who have built an idea once can reason about the library's version of it. *Check:* critic.

**W-47 In practice starts from production.** In an In practice book, use production tools and idioms from the first example. Every chapter covers what goes wrong in production and how you'd notice.
*Why:* its readers already know the idea; they need to run it. *Check:* critic.

**W-48 Record what can't run offline.** Code that calls a model or a remote service lives in `recordings/`. Each script pins its model version and prompt. Its outputs are saved under `examples/data/recorded/{name}/`, with a `manifest.json` naming the script, model, model version, prompt hash, date and output files. Examples then run offline on those outputs. Prefer open models anyone can run, and say so when a model is closed. A new model version is an update trigger, like a library release. An open model small enough for a CPU can run live instead: pin it in `examples/models.toml` with `re-check models --pin`, and load it with its pinned revision, as `from_pretrained(repo, revision=REVISION)`. That's how the runtime finds it offline, and how a reader gets the same files.
*Why:* examples must run offline and give the same output every time (W-17), and model calls do neither. *Check:* lint for complete manifests (`re-check style`); reviewer for the choice of model.

## 11. Reading flow

A reader follows a story more easily than a list of facts. These rules keep each sentence carrying the context it needs, so the text reads cleanly the first time.

**W-49 Introduce what the reader will keep meeting.** The first time the book, or a chapter, brings in something it will come back to, such as the running case, its data, a recording or a shared module, say what it is, what it does for the reader, and the short name the text uses from then on. Write "This book follows one case study throughout: an online furniture and home-goods store, which we call the store." Not "The case is an online furniture and home-goods store." Introduce the case once per chapter, in that chapter's words, never in a sentence copied from another chapter (W-64).
*Why:* a short name works only once the reader knows what it stands for and why it matters to them. *Check:* critic.

**W-50 Say which one, and what it's for.** When a sentence refers back to something the reader has met, such as the data, the judgments, a run or a result, make clear which one it means and the part it plays, unless the sentence before already does. Write "The store's data, which every example in this book uses, is real." Not "The store's data is real."
*Why:* across a book, one noun can mean several things: the catalog, the sample the book ships, the judgments. A reader who has to guess reads the sentence twice. *Check:* critic.

**W-51 Complete thoughts, not shorthand.** Write each sentence so it carries its own context. Don't make a bare label the subject ("The case is …"), stack nouns into compounds ("the train-pool LLM-grade agreement"), or drop the verb that says how two things relate. A sentence the reader has to reread needs more words, not fewer.
*Why:* compressed prose saves the writer words and costs the reader time. *Check:* critic.

**W-52 Connect each step to the last.** Open each section by saying, in one sentence, how it follows from what the reader has just seen, with a link when it points back (W-40). Within a paragraph, each sentence picks up something from the one before it.
*Why:* a section that starts from where the reader is lets them keep the thread, and the link keeps it usable alone. *Check:* critic.

**W-53 Tables fit a phone.** A table has at most 6 columns, short cells and a header row (W-39). For a wide comparison, put the things compared in the columns and the measures in the rows, or split it into two tables. Leave out what a sentence can say, such as whether two tests agree.
*Why:* a wide table scrolls sideways on a phone, and the reader loses which row they're on. *Check:* lint for the column count (`re-check style`); critic for the rest.

## 12. Spoken descriptions

Narration reads a chapter word for word, but never its code, output or tables. Each example, fenced block and table is read as a description written for it in the book's `narration/{chapter_id}.toml`, beside the chapter, so a listener keeps what a reader sees.

**W-54 Describe every example, block and table.** In a sentence or two, say what the code does and what its output shows, what a formula says, or what a table compares. Write for a listener who can't see the page: name what goes in and what comes out, never the syntax. Narration reads an example's name first ("Example: N D C G for one query."), so don't repeat it. Write "The code takes BM25's top ten for clear shower curtain, adds up each grade divided by a log discount, does the same for the best possible top ten, and prints their ratio: {{out:ndcg-for-one-query:ndcg@10}}." Not "It calls `ndcg_at_k` on the ranking and prints the result." Never write "as you can see", "below" or "on the page".
*Why:* code read aloud is noise, and an example announced by name alone tells a listener nothing about what it found. *Check:* `re-check narration` lists a missing description, and one whose example, section or first line no longer matches; it warns, and never fails a pull request. Critic for the rest.

**W-55 Bind the numbers a description quotes.** Quote an output's values with `{{out:…}}` and versions with `{{version:…}}`, as the prose does (W-25, W-26). Claim nothing the output doesn't show.
*Why:* a description stays current from one edition to the next only through its bindings, and a listener can't check a claim against the page. *Check:* `re-check narration` lists bindings that don't resolve; critic for claims.

**W-56 Say hard terms through the lexicon, never by changing the text.** When a voice can't read a term, such as BM25, nDCG@10 or a model's name, add its reading to the book's `narration/lexicon.toml`: under `[terms]` for text as written, or `[words]` for a whole word in any case, such as a word of an example's ID. Never rewrite the chapter for the voice.
*Why:* the page and the narration say the same words, and the text is written for readers. *Check:* `re-check narration` lists every term no rule reads; critic for readings that say a term wrongly.

## 13. Agent skills

Every edition of a book also ships as an agent skill: the book in the open Agent Skills format, which coding agents load and follow. The release builds most of it from the edition: the stamp, the pins, the chapters as references and the examples as scripts. The book's own `skill.md`, beside `book.toml`, holds the two parts written by hand: a `description` in its front matter, and the procedures in its body. An agent does what this file says, so it says only what the book teaches.

**W-57 Procedures from the book, step by step.** Give each method the book teaches a procedure under a `## ` heading: when to use it, its steps in order, how to check the result, and the pitfalls the book warns about. Every step comes from a section, linked by its ID, as `[BM25 from scratch](#bm25-from-scratch)`, and a script is linked as its example, `[the example](examples/bm25-from-scratch.py)`. Teach nothing the book doesn't.
*Why:* a reader's agent then does what the reader learned, and the reader can check each step against the section it came from. *Check:* `re-check skill` fails a procedure that cites no section, a section or example that doesn't exist, and a book in draft without `skill.md`; critic for steps the cited sections don't support.

**W-58 Written for an agent at work.** The description says what the book teaches and when to use it, in the words a reader would use for the task, as "Use when evaluating or improving search ranking: BM25, nDCG, hybrid retrieval, reranking". Write each step as an instruction an agent can carry out on someone else's project: what to look at, what to do, what to compare. Keep it short: the format loads the whole file, so the procedures stay within the limits in `data/writing.toml`. Bind versions and printed values, as the prose does (W-25, W-26).
*Why:* an agent decides from the description alone whether to load the skill, and then reads all of it. *Check:* `re-check skill` for the description's length, the limits, typed versions and bindings; critic for the rest.

**W-59 Nothing that acts beyond the procedures.** Link only to the book's sections and examples, to rollingedition.com and rollingedition.ai, and to sources the chapters themselves cite. Never tell an agent to fetch or run anything from elsewhere, to read credentials, to change its own settings or permissions, or to do anything but the task it was given. A change to `skill.md` from anyone but the book's agents waits for a maintainer.
*Why:* someone else's agent follows this text with their files and their tools, so it carries the same trust as code they run. *Check:* `re-check skill` for links; `re-check addressed` reads `skill.md` as it reads a chapter; a contributor's change to it is flagged for a maintainer.

## 14. Narrative

A book should read the way a good textbook does: an author who knows where the chapter is going, says what matters, and uses each number to make a point. The rules above make a chapter true; these make it read naturally. They come from a review of the released books (Nov 13, 2026), which found that the rules above, each followed to the letter, could produce prose no author would write: a sentence built to hold a bound value, a paragraph that reads out every number an example printed, documentation quoted clause by clause, the same opener before every example. Nothing here relaxes a rule above: every number stays bound and every claim sourced. The exemplars show each rule applied to a passage from a released book.

**W-61 Lead with the point, then the number.** A paragraph that reports results opens with the sentence the reader should keep, then the one to three numbers that show it. The rest of what the example measured stays in its output, beside the prose, or goes in a table (W-53). Write each sentence around a bound number so it stays true if the number changes (W-26). A yes or no the prose relies on is an `assert` in the example, so a change fails its run, and the prose states it as a fact; one the prose must quote is printed as a word the sentence can use, such as `same notes as the first: yes`, never as `True` or `False`. Write "Product text writes the size apart, as `7 qt` in 8 products, and the tokenizer drops the `7`". Not "The number of products whose text says `7 qt` is 8".
*Why:* a reader keeps one sentence, not a ledger, and a sentence shaped to hold a value reads like a form. *Check:* lint fails a binding whose value is `True` or `False`, and warns at more than 4 bound numbers in a paragraph (`[narrative]` in `data/writing.toml`); critic for the point.

**W-62 Cite the way a textbook does.** Every claim keeps its source (W-28), cited in passing: the claim in the book's own words, and the author's name or the document's title in the sentence, linked. Quote only when the wording is itself the point, such as a definition or a specification's MUST, and then at most once in a paragraph. Put one link on a claim, not one on every clause. Name a source in full the first time in a section, and by a short name after.
*Why:* a page of spliced quotations reads as a brief; the reader came for the author's account of the source, and can open it. *Check:* lint warns at more than one quotation of 4 words or more in a paragraph, and at more than 2 links in a sentence; critic for the rest.

**W-63 Vary the way in.** Introduce each example with what the reader will see and why it's worth running, in words that differ from the last. Name the case where the sentence needs it, never as a prefix that marks the step: not "For the store, …", "The example …" or "Asked whether …". Ask the chapter's prediction (W-11) in words of its own. A working rule names its example only when the rule is the example, as "print the weight matrix, as this example does"; never "as here". A sentence says its thing once in a book.
*Why:* after the third repeat a reader hears the template and stops reading the sentence. *Check:* lint fails a chapter that uses a stock opener or phrase more than twice, and a sentence of 12 words or more that appears twice in the book; critic for variety.

**W-64 Introduce the case once per chapter, in that chapter's terms.** A chapter's opening says what the case is in one sentence written for this chapter's problem, as a clause where a clause will do. After that, the short name alone. A module, file or data set the book has introduced is linked, not defined again. W-49 and W-50 ask that a reference be clear, not that it be restated.
*Why:* the same appositive at the top of every chapter tells the reader a machine wrote it, and buries the chapter's problem under the book's. *Check:* lint fails a sentence whose first 10 words open sentences in 3 chapters or more; critic for the rest.

**W-65 The problem before the protocol.** After the promise (W-2), a chapter's first paragraphs show the problem as it appears in the case. A protocol, a list of planned comparisons, a glossary, a standard's definitions or a model's configuration comes after the problem, or in the section that needs it. In a section, the intuition comes first and in the reader's words, as a paragraph, not a clause, before the formula or the definition (W-14).
*Why:* a reader who doesn't yet have the problem can't hold the method. *Check:* critic.

**W-66 Say a caveat once.** A caveat that holds for a whole chapter, such as what counts as evidence, which questions are legal ones or what is our judgement, is said once, where it first matters, and linked after.
*Why:* a disclaimer at every result reads as anxiety, and hides the result. *Check:* critic, which quotes the repeats.

**W-67 Write as the author.** Guide the reader in the book's voice (W-34): "notice that", "the point is", "the line to remember is", "we now turn to". Use short sentences, as W-33 asks, but not only short ones: let a sentence's length follow its thought, and join clauses with "because", "so" and "which", or with a second sentence, rather than every time with a colon. Don't open consecutive paragraphs, sections or production bullets with the same words. After a run of results, say in one sentence what they add up to. End a chapter's list of decisions with what was learned, in sentences a reader carries away, not with the numbers again.
*Why:* this is what natural means on the page: an author who knows what matters and says so. *Check:* critic.

**W-68 Every example explains itself.** An example opens with a docstring of one or two sentences: what it shows, and which printed line the prose's point rests on. A comment, in the prose's own words (W-23), sits on every line that a reader copying the file would otherwise have to open `lib` or the chapter to understand: an index or slice with an offset, a condition that encodes a fact about the data, a keyword that hides the chapter's idea in a shared module, a seed, a tie-break, a threshold, a `None` that means "all", a library call whose return surprises. A comment never restates a print's label or the prose's conclusion, and never says what the code plainly does, such as "load the data". The docstring and comment lines don't count toward W-18's limit.
*Why:* readers copy examples into their own work, and the reason for a line is the first thing they lose. *Check:* lint fails an example without a docstring, and warns at an index with a literal offset and no comment on or above its line (`re-check style`); critic for the rest.

## 15. Command chapters

A terminal book's chapters are worked in a shell, step by step, beside a live cluster or a plain shell (the standards' README, Terminal books). Its steps are checked as its examples are: every release runs them again, so they keep these rules, and the checks below hold most of them.

**W-70 Every step prints the same on every run.** A step's recorded output is what a reader sees, so nothing in it may change from one run to the next unless a mask names it. Name a resource, never let a command generate its name; sort a listing whose order varies; read the time only where `#| mask: time` covers it. Mask what Kubernetes generates and no one chooses: a pod's suffix, an age, an address, a UID, a resource version and a background job's process ID (`#| mask: pod-suffix, age`). Where the order of a few lines varies, compare with `#| compare: lines`. Write "`kubectl -n shop get pods -l app=web`" with `#| mask: pod-suffix, age`. Not "`kubectl get pods -A`", whose system pods and their order change with every release of the stack.
*Why:* a step whose output changes on its own fails the next release, and a reader can't tell their mistake from the book's noise. *Check:* `re-check commands --record` runs each chapter twice, each on a fresh cluster, and records nothing until every step printed the same after its masks; `re-check commands` refuses a step that uses `$RANDOM`, `uuidgen` or `/dev/urandom`, runs `date` without `#| mask: time`, or starts a job with `&` in its tab without `#| mask: job`.

**W-71 Wait for what a step needs, never sleep.** A step that starts something a later step needs waits until it's true: `#| wait:` polls a command until it exits 0, within the step's limit. Wait on the state itself, such as a deployment's available replicas or a port that answers, never on time passing. Write `#| wait: test "$(kubectl -n shop get deployment web -o jsonpath='{.status.availableReplicas}')" = 3`. Not `sleep 30`.
*Why:* a fixed pause is too short on a slow machine and wasted on a fast one, and a reader's laptop is both. *Check:* `re-check commands` refuses a step or a wait that sleeps.

**W-72 Every chapter starts from a fresh cluster and its setup.** A chapter never relies on what an earlier chapter left behind. The earlier steps it builds on are named in its front matter's `setup`, which brings a fresh cluster to the chapter's start, and nothing else is assumed: no file the reader made, no resource from another chapter that `setup` doesn't make. A step in the background, such as a port-forward, is never part of a chapter's setup: the chapter starts it again where it needs it.
*Why:* readers start anywhere, the Lab gives each chapter a fresh cluster, and every chapter is checked alone, in parallel. *Check:* `re-check commands` runs each chapter on a cluster of its own, from the stack's clean snapshot, then its setup; `re-check section-ids` refuses a setup that names a later chapter's step or a background one.

**W-73 Every check fails before its section and passes after.** A check proves the reader did what its section asks: it fails on the cluster as the section finds it, and passes once the section's steps have run. Check the state the section creates, such as three available replicas, never something that was true already, and give the check a hint that says what to try. A check that passes either way checks nothing.
*Why:* "Check my work" is only worth pressing if it can say Not yet. *Check:* `re-check commands` runs each check before its section's steps and fails one that passes then, then runs it after them and fails one that doesn't pass.

**W-74 Nothing in the cluster reaches the network.** Every tool, chart and image a chapter uses is pinned in `examples/stack.toml`, and the cluster runs only those. A step never fetches anything from beyond the machine and the cluster: no `helm repo add`, no `kubectl apply -f https://…`, no `curl` to a public address, no `git clone`, no `pip install`. Manifests name each image by the tag the stack pins, never `latest` and never with `imagePullPolicy: Always`. Data a chapter needs ships in `examples/`.
*Why:* a reader's Lab has no way out to the internet, every release must run the same bytes, and a download can change or vanish between editions. *Check:* `re-check commands` refuses a step that names an address outside the machine and the cluster, or a command that downloads; `re-check stack` refuses a manifest that names an image the stack doesn't pin, by digest or as `latest`, or that always pulls; on k3s every run has no registry to pull from and a fence that lets the steps and the pods reach only the cluster.

**W-75 Run only what readers may run as a service.** Everything a Lab runs reaches readers' sessions, so it must be open source, and Apache-2.0 is preferred. The stack never pins software under the AGPL, the SSPL, the Elastic License, the Business Source License, the Redis Source Available License, Commons Clause or the Confluent Community License: use SeaweedFS for MinIO, OpenSearch for Elasticsearch, Valkey for Redis, Apache Kafka for Redpanda, OpenTofu for Terraform and OpenBao for Vault. Give each tool, chart and image its licence in `stack.in.toml`, as its project publishes it.
*Why:* those licences restrict offering the software as a service, which is what a Lab is, or aren't open source at all. *Check:* `re-check stack` refuses a refused licence, names what to use instead, and refuses one on neither list until it's read and added.

**W-76 Steps run in any bash.** A reader on a Mac runs the book's local lab with the bash it ships, version 3.2, so steps keep to what it has: no associative arrays (`declare -A`), `mapfile` or `readarray`, case changes in an expansion (`${name,,}`), `&>>` or `|&`, `coproc`, `wait -n`, namerefs, `globstar`, or zero-padded or stepped ranges (`{01..10}`).
*Why:* a step that runs in the Lab but fails on a reader's own machine breaks the free way to work the book. *Check:* `re-check commands` refuses what bash 3.2 can't run; the local lab runs the steps with a newer bash when one is on the PATH.

## 16. Concepts

A book's concepts are the terms it defines, indexed in `concepts.toml` beside `book.toml`: each one's term and aliases, the sentence that defines it and the section that sentence is in, its context, an example that shows it, the packages its meaning depends on, and how it relates to the book's other concepts. Readers' assistants, the book's glossary, its translations and its agent skill read them, so a term means the same wherever a learner meets it, and each edition says which version of a package a definition is true for. The definition is always the book's own sentence, quoted, never a second copy that can drift. A book without `concepts.toml` has nothing to check. The format, the contexts and the relation types are in the standards' README (Concepts) and `data/concepts.toml`.

**W-77 Define a term in the book's own sentence, and quote it exactly.** A concept's `definition` is a sentence of its section, or a clause of one, word for word, and its `formula`, if it has one, is the formula as the section writes it. Emphasis, links and line breaks don't matter; words, numbers and punctuation do, and a binding is quoted as written. Where the meaning depends on a package or tool, name it in `applies_to`, so every edition says the version it's true for. Write `definition = "Recall at k, recall@k, is the share of all relevant products that appear in the top k."` for the section that says so. Not a paraphrase, a dictionary's wording or a summary of the section.
*Why:* a definition copied out of the text drifts from it at the first edit, and an assistant that quotes the copy then contradicts the book. *Check:* `re-check concepts` fails a definition or formula that isn't in its section's text, a section that doesn't exist, and an `applies_to` the book doesn't pin; critic for a quote that doesn't say what the term means.

**W-78 One concept, one definition, in one context.** A book defines each concept once. Put it in the broadest context where the term means one thing: the book's area, or one of its skills, from the taxonomy. Where two meanings meet, as embedding does in search and in language models, each meaning is a concept of its own in a context of its own; declare a narrower context under `[[contexts]]` only when no area or skill fits. A concept's ID, its term and each of its aliases name one concept in its context. List as aliases the forms a reader searches for, such as `recall@k` for Recall at k. Once a concept is released, its context and ID are its permanent address: never change them.
*Why:* an assistant asked what a term means needs one answer for each meaning, and has to say which it gave; a link to a concept must still work after the book changes. *Check:* `re-check concepts` fails a concept defined twice, an ID, term or alias that names two concepts in a context, an unknown context, and two concepts that quote the same definition; critic for the context chosen.

**W-79 Link a term used before its definition.** A chapter that uses a concept's term or an alias before the section that defines it links its first such use to that section, as `[recall at k](#count-relevant-in-top-k)`. A chapter's opening may name a term its own sections define, and after the definition no link is needed.
*Why:* a reader who meets a term before it's explained needs to know where it is, and readers start anywhere. *Check:* `re-check concepts` lists each chapter whose first such use comes before its link, matching whole words: a term with a capital after its first letter, such as BM25, only as written, and any other with its first letter in either case. A term that's also an everyday word, such as gain, can match its everyday uses, so the list doesn't fail the check; `--strict` fails it, and a critic reads it.

**W-80 Relations from the fixed set.** Connect a concept to others only with the relation types in `data/concepts.toml`: broader and narrower, part-of, measured-from and computed-from, prerequisite-of, contrasts-with, implemented-by a package or tool, and same-as or close-to another context's concept or a Wikidata item. Each names a concept this book defines, or another context's concept by its address, and states only what the book itself says. Prerequisite-of, the hierarchy and part-of never go round in a circle. A version range belongs to implemented-by, as `{ to = "bm25s", versions = ">=0.3" }`, and the book's pin must be within it.
*Why:* a graph with invented or vague links can't answer what comes before a concept, and a learning path built on a circle never starts. *Check:* `re-check concepts` fails an unknown type, a relation to a concept that doesn't exist, one reserved for an organization's own concepts, a circle and a pin outside a version range; critic for whether each relation is true.
