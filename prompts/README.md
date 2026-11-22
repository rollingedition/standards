# Agent prompts

The prompts the Rolling Edition agents run with are published here, so anyone can read exactly what an agent was told. The agents load them at a tagged version of this repository.

| Prompt | Agent |
| --- | --- |
| `researcher.md` | Gathers and checks the sources for one chapter before it's drafted |
| `writer.md` | Drafts one chapter and its examples to the writing standards |
| `development-editor.md` | Edits the book's plan before any chapter, reads it again after chapter 1 and at the middle, and gives the whole book its final read; keeps the book's memo, `notes/editorial.md` |
| `technical-editor.md` | Checks one chapter's technical truth before its critic: every definition, every statement of how something works, every claim's support |
| `critic.md` | Reviews a chapter against the writing standards and prepares the review packet published with it; after a technical editor, writes the one edit letter the fixer works from |
| `proofreader.md` | Reads what readers see and hear, the spoken script with its bindings filled in, the figures and the tables, before the book's gates |

A brief gives each agent the writing standards cut for its task with `re-check rules`, not the whole of `writing/README.md`.

Triage is rule-based for now (`data/review-tiers.toml`). The update agent and freshness auditor prompts come with the update agents.
