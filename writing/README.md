# Writing standards

How a Rolling Edition book is written. These rules apply to every book, whoever writes the text: our agents drafting a book, or a contributor fixing one paragraph. Critic agents check drafts against them, and anyone who reads a book can use them to correct it.

Draft. Rules may change before the first book is drafted with them.

**How to read a rule.** Each rule has an ID, the reason for it, and how it is checked:

- **lint:** an automatic check fails the pull request
- **critic:** a critic agent checks the draft and cites the rule's ID in the review packet
- **reviewer:** a judgement no automatic check can make: critic agents apply it, and any reader can correct a book that breaks it

Lint checks run with `re-check style --book PATH`. Those marked "when built" are planned, so a critic checks them until then. Limits and word lists are defaults, kept in `data/writing.toml`.

**Exemplars.** The sections in `exemplars/` show the rules applied, with notes. Drafting agents imitate them, and critics compare drafts against them. If an exemplar and a rule disagree, the rule wins; report the disagreement.

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

## 2. Structure

**W-4 The whole result first.** Chapter 1 builds a rough but working version of the book's end result, end to end. Each later chapter makes one part of it solid.
*Why:* a reader who has seen the whole knows why each part matters. *Check:* reviewer.

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

**W-11 Predict, then run, at most once per chapter.** At a chapter's turning point, ask the reader to predict an output before the example that shows it. Foundations books do this in most chapters; In practice books rarely.
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

**W-17 Every example runs.** Examples use pinned versions, run offline and are deterministic, with fixed seeds. The output in the book is the output the example produced.
*Why:* this is the promise on every stamp. *Check:* lint (`re-check examples`).

**W-18 One idea per example.** Keep an example to about 30 lines. Longer setup moves into a shared module the reader can open.
*Why:* the reader should see the idea, not the scaffolding. *Check:* lint for length (`re-check style`); critic for the idea.

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

**W-26 Bind numbers from outputs.** When prose quotes a value an example printed, the example prints it on its own labelled line, such as `unreadable amounts: 1`. The prose then writes `{{out:fix-types:unreadable amounts}}`, and the build fills in the value from the recorded output.
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

**W-48 Record what can't run offline.** Code that calls a model or a remote service lives in `recordings/`. Each script pins its model version and prompt. Its outputs are saved under `examples/data/recorded/{name}/`, with a `manifest.json` naming the script, model, model version, prompt hash, date and output files. Examples then run offline on those outputs. Prefer open models anyone can run, and say so when a model is closed. A new model version is an update trigger, like a library release.
*Why:* examples must run offline and give the same output every time (W-17), and model calls do neither. *Check:* lint for complete manifests (`re-check style`); reviewer for the choice of model.

## 11. Reading flow

A reader follows a story more easily than a list of facts. These rules keep each sentence carrying the context it needs, so the text reads cleanly the first time.

**W-49 Introduce what the reader will keep meeting.** The first time the book, or a chapter, brings in something it will come back to, such as the running case, its data, a recording or a shared module, say what it is, what it does for the reader, and the short name the text uses from then on. Write "This book follows one case study throughout: an online furniture and home-goods store, which we call the store." Not "The case is an online furniture and home-goods store."
*Why:* a short name works only once the reader knows what it stands for and why it matters to them. *Check:* critic.

**W-50 Say which one, and what it's for.** When a sentence refers back to something the reader has met, such as the data, the judgments, a run or a result, make clear which one it means and the part it plays, unless the sentence before already does. Write "The store's data, which every example in this book uses, is real." Not "The store's data is real."
*Why:* across a book, one noun can mean several things: the catalog, the sample the book ships, the judgments. A reader who has to guess reads the sentence twice. *Check:* critic.

**W-51 Complete thoughts, not shorthand.** Write each sentence so it carries its own context. Don't make a bare label the subject ("The case is …"), stack nouns into compounds ("the train-pool LLM-grade agreement"), or drop the verb that says how two things relate. A sentence the reader has to reread needs more words, not fewer.
*Why:* compressed prose saves the writer words and costs the reader time. *Check:* critic.

**W-52 Connect each step to the last.** Open each section by saying, in one sentence, how it follows from what the reader has just seen, with a link when it points back (W-40). Within a paragraph, each sentence picks up something from the one before it.
*Why:* a section that starts from where the reader is lets them keep the thread, and the link keeps it usable alone. *Check:* critic.

**W-53 Tables fit a phone.** A table has at most 6 columns, short cells and a header row (W-39). For a wide comparison, put the things compared in the columns and the measures in the rows, or split it into two tables. Leave out what a sentence can say, such as whether two tests agree.
*Why:* a wide table scrolls sideways on a phone, and the reader loses which row they're on. *Check:* lint for the column count (`re-check style`); critic for the rest.
