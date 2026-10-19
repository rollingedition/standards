# Agent prompts

The prompts the Rolling Edition agents run with are published here, so anyone can read exactly what an agent was told. The agents load them at a tagged version of this repository.

| Prompt | Agent |
| --- | --- |
| `researcher.md` | Gathers and checks the sources for one chapter before it's drafted |
| `writer.md` | Drafts one chapter and its examples to the writing standards |
| `critic.md` | Reviews a chapter against the writing standards and prepares the review packet published with it |

Triage is rule-based for now (`data/review-tiers.toml`). The update agent and freshness auditor prompts come with the update agents.
