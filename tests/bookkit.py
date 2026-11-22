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


# ---------------------------------------------------------------- a book with figures (figures.py)

# A figure as matplotlib writes it, cut down: a DOCTYPE, metadata, the defaults every element takes, a clip path and a
# marker named by hashes, a tick label and two lines in the palette
SVG = '''<?xml version="1.0" encoding="utf-8" standalone="no"?>
<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN"
  "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">
<svg xmlns:xlink="http://www.w3.org/1999/xlink" width="460.8pt" height="187.2pt" viewBox="0 0 460.8 187.2" xmlns="http://www.w3.org/2000/svg" version="1.1">
 <metadata>
  <rdf:RDF xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:cc="http://creativecommons.org/ns#" xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
   <cc:Work>
    <dc:type rdf:resource="http://purl.org/dc/dcmitype/StillImage"/>
    <dc:format>image/svg+xml</dc:format>
   </cc:Work>
  </rdf:RDF>
 </metadata>
 <defs>
  <style type="text/css">*{stroke-linejoin: round; stroke-linecap: butt}</style>
 </defs>
 <g id="figure_1">
  <g id="axes_1">
   <path d="M 58.899401 153.198979
L 58.899401 3.00024
" clip-path="url(#p14e344082f)" style="fill: none; stroke: #e2d5b8; stroke-width: 0.6"/>
   <defs>
    <path id="m85059689ef" d="M 0 0 L 0 3.5" style="stroke: #61574a; stroke-width: 0.8"/>
   </defs>
   <use xlink:href="#m85059689ef" x="58.899401" y="153.198979" style="fill: #61574a; stroke: #61574a"/>
   <text style="font-size: 10px; font-family: 'IBM Plex Sans', 'DejaVu Sans', sans-serif; text-anchor: middle; fill: #61574a" x="58.899401" y="167.796635">0.20</text>
   <path d="M 40 100 L 400 20" clip-path="url(#p14e344082f)" style="fill: none; stroke: #9a4a06; stroke-width: 1.4"/>
  </g>
 </g>
 <defs>
  <clipPath id="p14e344082f">
   <rect x="39.904146" y="3.00024" width="417.895614" height="150.198739"/>
  </clipPath>
 </defs>
</svg>
'''

DRAWS = '''"""Draws one line, from the SVG beside it: a stand-in for matplotlib, which this Python hasn't got."""
from pathlib import Path

Path("figures").mkdir(exist_ok=True)
Path("figures/a-line.svg").write_text(Path("drawing.svg").read_text())
print("peak: 3")
print("figure: figures/a-line.svg")
'''
OUT = "peak: 3\nfigure: figures/a-line.svg\n"

FIGURE_CHAPTER = '''---
chapter_id: first-steps
---

# First steps

Opening text.

## Load the data {#load-data}

{{fig:a-line}} draws one line, which peaks at {{out:draws:peak}}.

![A line that rises to its peak, then falls back](../examples/figures/a-line.svg "One line, rising then falling")

[Example: draws](../examples/draws.py)

**Working rule:** Draw it.

## Summarize {#summarize}

Done, as {{fig:a-line}} shows.
'''

SECOND = '''---
chapter_id: second-steps
---

# Second steps

Opening text.

## Again {#again}

{{fig:a-line}} came first, and {{fig:b-curve}} comes next.

![A curve that falls all the way](../examples/figures/b-curve.svg "One curve, falling")

[Example: curves](../examples/curves.py)

**Working rule:** Draw it again.
'''


def make_figure_book(root, chapter=FIGURE_CHAPTER, svg=SVG, helper=True, second=False, **kw):
    make_book(root, chapter=chapter, examples={"draws": (DRAWS, OUT)}, **kw)
    (root / "examples" / ".python-version").write_text("3.12.15\n")      # the host backend runs this Python whatever it says
    (root / "examples" / "drawing.svg").write_text(svg)
    (root / "examples" / "figures").mkdir()
    (root / "examples" / "figures" / "a-line.svg").write_text(svg)
    if second:
        (root / "chapters" / "02-second-steps.md").write_text(SECOND)
        (root / "examples" / "curves.py").write_text("print('figure: figures/b-curve.svg')\n")
        (root / "examples" / "curves.out").write_text("figure: figures/b-curve.svg\n")
        (root / "examples" / "figures" / "b-curve.svg").write_text(svg)
    if helper:
        from re_standards import figures
        figures.write_helper(root)
    return root
