"""Builds small book checkouts for tests."""
from pathlib import Path

MANIFEST = '''slug = "tiny-book"
title = "Tiny Book"
summary = "A test book."
status = "live"
level = "foundations"
skills = ["data-pipelines"]
line = "main"
core_libraries = []
expert_reviewer = "demo-reviewer"
sponsor = ""
'''

# An authored book's [[authors]] and [authorship], added to MANIFEST: placeholder people and GitHub accounts. Jane Doe
# leads and owns the first chapter; kestrel, a pseudonym, shares the rest.
AUTHORS = '''
[[authors]]
name = "Jane Doe"
given = "Jane"
family = "Doe"
github = "jane-doe-example"
github_id = 1000001
role = "lead"
chapters = ["first-steps"]
interests = "Maintains a library this book teaches."

[[authors]]
name = "kestrel"
literal = "kestrel"
github = "kestrel-example"
github_id = 1000002

[authorship]
gate = "meaning"
state = "active"
'''

CHAPTER = '''---
chapter_id: first-steps
---

# First steps

Opening text.

## Load the data {#load-data}

Read the file.

[Example: hello](../examples/hello.py)

```markdown
## Not a heading {#nope}
```

### A detail {#a-detail}

More text.

## Summarize {#summarize}

Done.
'''


def make_book(root: Path, chapter: str = CHAPTER, examples: dict | None = None, redirects: str | None = None,
              manifest: str = MANIFEST) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "book.toml").write_text(manifest)
    (root / "chapters").mkdir(exist_ok=True)
    (root / "chapters" / "01-first-steps.md").write_text(chapter)
    ex = root / "examples"
    ex.mkdir(exist_ok=True)
    for name, (code, out) in (examples if examples is not None else {"hello": ('print("hello")\n', "hello\n")}).items():
        (ex / f"{name}.py").write_text(code)
        if out is not None:
            (ex / f"{name}.out").write_text(out)
    if redirects is not None:
        (root / "redirects.yml").write_text(redirects)
    return root
