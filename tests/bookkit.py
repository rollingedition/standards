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
