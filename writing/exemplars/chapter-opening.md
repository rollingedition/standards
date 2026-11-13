# Exemplar: a chapter's opening

The opening of a released chapter, before and after it was rewritten to the narrative rules, with notes. It's the opening of "Finding personal data", chapter 3 of *Data governance as code*, whose running case is an online learning platform, called the platform. The chapter has no bindings in its opening, so none appear here.

A chapter's opening has three jobs, in order: the promise (W-2), the problem as the case shows it (W-65), and what the chapter builds to answer it. The case itself gets a clause, in this chapter's terms (W-64).

---

## Before

By the end of this chapter you can find personal data on a data platform automatically. You'll propose a classification for every column from its name, its type and a reproducible sample of its values, find personal data inside free text span by span, and measure each detector against labelled data, so you know what it misses before anyone relies on it. You'll run Presidio's pattern recognizers offline with thresholds chosen by measurement, compare them with the recorded detections of a model trained to find personal data, and classify again only the columns a schema change adds.

The platform, the online learning platform this book follows, sells professional courses to adult learners, and keeps its warehouse in an Iceberg catalog of eight source tables, each under the namespace of the team that runs it. [Chapter 2](#a-catalog-you-can-test) gave every column a classification in `governance/metadata.toml`, a file people review. A reviewed file records what its reviewers believe a column holds, and on the platform three beliefs need checking. `billing.payments.card_number` is a legacy column whose description says it holds full card numbers, and nobody has checked. `crm.learners.notes` is free text that support agents type, so its name says nothing about what's in it. And learners write whatever they like in support tickets and course reviews, so a classification of the whole column can't protect that text: the platform has to find each name, email and phone number inside it before the text can be masked span by span, which [chapter 9](#replace-personal-data) does to reviews before the platform's course assistant learns from them.

This chapter builds the book's shared module for this, `lib.pii`: rules on column names, seeded samples of a column's values, a Presidio detector configured to run offline, and code that scores any detector against labelled data. Every detector in this chapter is measured against one file, which we call the truth: `data/platform/pii_spans.parquet`. The script that generated the platform's data writes it beside the tickets and reviews: every piece of personal data it placed in their text, with its exact start and end. Invoice numbers, order numbers and the date a problem happened stay unlabelled, because the platform doesn't treat them as personal data.

## After

By the end of this chapter you can find personal data on a data platform automatically, and say how much of it you miss. You'll propose a classification for every column from its name, its type and a reproducible sample of its values; find personal data inside free text, span by span; and measure each detector against labelled data before anyone relies on it. Along the way you'll run Presidio's pattern recognizers offline, with thresholds chosen by measurement, compare them with the recorded detections of a model trained for the job, and classify again only the columns a schema change adds.

Every column on the platform already has a classification. [Chapter 2](#a-catalog-you-can-test) put one in `governance/metadata.toml`, and people reviewed it. But a reviewed file records what its reviewers believe a column holds, and on the platform, the online learning platform whose warehouse this book governs, three of those beliefs have never been checked. `billing.payments.card_number` is a legacy column whose description says it holds full card numbers; nobody has looked. `crm.learners.notes` is free text that support agents type, so its name says nothing about its contents. And support tickets and course reviews hold whatever learners choose to write. No classification of a whole column can protect that text. Before it can be masked, the platform has to find each name, email and phone number inside it, span by span, as [chapter 9](#replace-personal-data) does to reviews before the course assistant learns from them.

So this chapter builds the book's shared module for finding personal data, `lib.pii`: rules on column names, seeded samples of a column's values, a Presidio detector that runs offline, and code that scores any detector against labelled data. Every detector is scored against one file, which we call the truth, `data/platform/pii_spans.parquet`. The script that generated the platform's data wrote it down as it went: every piece of personal data it placed in the tickets and reviews, with its exact start and end. Invoice numbers, order numbers and the dates of problems aren't in it, because the platform doesn't treat them as personal data.

---

## Notes

| Rule | What changed, and why |
| --- | --- |
| W-64 The case once, in this chapter's terms | Before, the second paragraph opened with the sentence that opened chapters 2 to 10 word for word: "The platform, the online learning platform this book follows, sells professional courses …". After, the case is a clause, and the clause says what this chapter needs from it: a warehouse that someone governs. The Iceberg catalog's eight tables don't matter here, so they go. |
| W-65 The problem before the protocol | The paragraph now opens on the problem: a classification exists, and nobody has checked it. Before, the problem arrived in the third sentence, after the case and the catalog. |
| W-67 Write as the author | "No classification of a whole column can protect that text." is its own short sentence, because it's the turn the paragraph rests on. "So this chapter builds …" ties the plan to the problem it answers. "And say how much of it you miss" puts the chapter's real promise in its first sentence. |
| W-2 State the promise | Kept, and tightened: one list in semicolons instead of three clauses joined by commas. |
| W-49, W-50 Introduce what the reader keeps meeting | `lib.pii` and the truth are introduced once, by what they are and what they're for, as before. |

What the opening leaves out: the catalog's layout, every detector's name, and any preview of the chapter's results.
