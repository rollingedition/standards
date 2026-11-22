"""Figures drawn by examples: the format's checks, the shared style every book's figures are drawn with, and the
SVG a figure is, checked, compared and made safe to show. data/figures.toml holds the settings.

**A figure is an example's output.** An example draws it from the book's own data with the shared style,
`examples/lib/figures.py`, and its `save(fig, NAME)` writes `examples/figures/NAME.svg` and prints the line that names
it, `figure: figures/NAME.svg`. The examples check compares the SVG it writes with the committed one, as it compares
printed output (examples.py), and `--record` writes it. A chapter embeds it with a paragraph that is only

    ![alt text that states its point](../examples/figures/NAME.svg "Its caption")

and its prose points to it with `{{fig:NAME}}`, which the build writes as "Figure 4.1" (bookfmt.Book.bind): no figure
number is typed. A figure's name is unique in its book.

**The shared style is generated** (`re-check figures --write`, helper): its settings, palette and fonts are
data/figures.toml's, and the check fails a book whose copy differs, as `re-check kit` does a kit file. Book examples run in the book's own
pinned runtime, where these standards aren't installed, so the style is a file in the book.

**The checks.** The format's (problems), which the section-ID check runs on every pull request: each figure's file is
there, within the size limit, drawn by an example the same chapter embeds, embedded once, and holding nothing active (no
script, event handler, foreignObject or reference outside itself); no chapter shows an image no example draws, and the
shared style is the generated one. The writing's (writing_problems, `re-check style`): alt text that states a point
(W-39), and a caption, a mention in the prose by its binding, no typed figure number, and only the palette's colours
(W-82).

**The SVG** (parse, active_problems, compare, clean): parsed with the standard library, which never fetches an external
entity; one that declares entities is refused. `compare` reads two SVGs as trees, IDs read in the order they appear, and lets each number in an
attribute differ by [compare] tolerance, since numpy's SIMD paths can round the last bit differently on Intel and AMD;
text, elements and attribute names must be the same. `clean` writes the SVG a surface shows: no metadata, no comment,
no DOCTYPE, its styles as presentation attributes (a page's Content-Security-Policy refuses style attributes), and,
inlined, its IDs prefixed so two figures on a page never share one, only the IDs it refers to kept, and each palette
colour classed for the page's stylesheet to draw in its theme.
"""
from __future__ import annotations

import html
import re
import tomllib
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree import ElementTree

from . import data_path

if TYPE_CHECKING:                       # bookfmt imports this module
    from .bookfmt import Book

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SRC = re.compile(r"^(?:\.\./)?examples/figures/([^/]+)\.svg$")
TYPED = re.compile(r"\b(?:Figure|Fig\.)\s+\d+(?:\.\d+)?\b")


@cache
def settings() -> dict:
    return tomllib.loads(data_path("figures.toml").read_text(encoding="utf-8"))


def folder() -> str:
    return settings()["format"]["folder"]


def anchor(name: str) -> str:
    """A figure's anchor in its chapter's page: a double hyphen after the word, which no book ID can have, so it never
    meets a chapter's, section's or example's."""
    return f"{settings()['format']['anchor']}{name}"


def from_anchor(value: str) -> str | None:
    prefix = settings()["format"]["anchor"]
    return value[len(prefix):] if value.startswith(prefix) and NAME.match(value[len(prefix):]) else None


def name_of(src: str) -> str | None:
    """The figure a chapter's image shows, by its address: `../examples/figures/NAME.svg`; None for any other image."""
    m = SRC.match(src or "")
    return m.group(1) if m and NAME.match(m.group(1)) else None


def label(number: str, word: str | None = None) -> str:
    """"Figure 4.1": the word, in the language a page is in (English unless given), and the number."""
    return f"{word or settings()['format']['label']} {number}"


def printed(expected: str | None) -> list[str]:
    """The figures an example's recorded output names, in order: each `figure: figures/NAME.svg` line save() prints."""
    key = settings()["format"]["printed"]
    out = []
    for line in (expected or "").splitlines():
        head, _, value = line.partition(":")
        m = re.fullmatch(r"\s*figures/([^/\s]+)\.svg\s*", value) if head.strip() == key else None
        if m:
            out.append(m.group(1))
    return out


def palette() -> dict[str, dict]:
    """The helper's colours, by their names in it (INK, MUTED, RULE, ACCENT): each a token and its light value."""
    return dict(settings()["palette"])


def palette_tokens() -> dict[str, str]:
    """Each palette colour, as an SVG writes it, to its design token: what a page draws it in, in either theme."""
    return {v["value"].lower(): v["token"] for v in palette().values()}


# ---------------------------------------------------------------- the shared style, generated

MARK = "Generated by `re-check figures`"          # in the helper's first lines

HELPER = '''"""How every figure in this book is drawn and saved. Generated by `re-check figures`: never edit it. The book's own
code goes beside it, in examples/lib/.

    from lib.figures import ACCENT, INK, new_figure, save

    fig, ax = new_figure()
    ax.plot(hours, load, color=ACCENT, label="each hour")
    save(fig, "lead-client-fortnight")

save() writes examples/figures/lead-client-fortnight.svg and prints the line that names it, which the example's recorded
output keeps. The examples check compares the SVG with the committed one, as it compares printed output.

The same data always gives the same SVG, on any machine and under any hash seed:
- matplotlib's SVG backend, with a fixed hash salt for the IDs inside the SVG and no date in its metadata;
- text kept as text (svg.fonttype "none"), so a page sets it in its own font and a screen reader can read it;
- the text laid out with the fonts matplotlib ships alone, never the machine's own, which differ from one to another.

The colours are the brand's: ACCENT for the series the prose points to, INK and MUTED beside it, RULE for the grid. A page
draws each in its design token, so the dark theme shows the figure in light ink. A third series is dashed, so no reader
needs colour alone to tell the series apart.
"""
import logging
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("svg")                       # no display: the SVG backend writes text, not pixels
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

{palette}
SERIES = ({series})
WIDTH, HEIGHT = {width}, {height}                # inches: the reading column's width
FIGURES = Path(__file__).resolve().parent.parent / "figures"

# Only the fonts matplotlib ships set the layout, never a machine's own, so every machine draws the same figure. The SVG
# still names the brand's font first, which a page that has it sets the text in.
_SHIPPED = os.path.realpath(matplotlib.get_data_path())
_manager = font_manager.fontManager
_manager.ttflist = [f for f in _manager.ttflist if os.path.realpath(f.fname).startswith(_SHIPPED)]
_manager.afmlist = [f for f in _manager.afmlist if os.path.realpath(f.fname).startswith(_SHIPPED)]
getattr(getattr(_manager, "_findfont_cached", None), "cache_clear", lambda: None)()
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)   # the brand's font is named, never installed

plt.rcParams.update({{
    "svg.hashsalt": "{salt}",           # fixed IDs inside the SVG, so a rerun gives the same bytes
    "svg.fonttype": "none",
    "font.family": "sans-serif",
    "font.sans-serif": {fonts},
    "font.size": {font_size},
    "text.color": INK, "axes.labelcolor": INK, "axes.titlecolor": MUTED,
    "axes.edgecolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": RULE, "grid.linewidth": {grid_width},
    "axes.prop_cycle": plt.cycler(color=SERIES, linestyle={styles}),
    "lines.linewidth": {line_width},
    "legend.frameon": False,
    "figure.facecolor": "none", "axes.facecolor": "none", "savefig.facecolor": "none", "savefig.edgecolor": "none",
}})


def new_figure(rows=1, height=HEIGHT, columns=1, sharex=True):
    """A figure the width of the reading column, with `rows` panels stacked (and `columns` side by side) sharing the
    time axis."""
    return plt.subplots(rows, columns, figsize=(WIDTH, height), sharex=sharex, layout="constrained")


def save(fig, name):
    """Write examples/figures/{{name}}.svg and print the line that names it."""
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name or ""):
        raise ValueError(f"{{name!r}}: a figure's name is lowercase words joined by hyphens")
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{{name}}.svg", format="svg", metadata={{"Date": None, "Creator": None}})
    plt.close(fig)
    print(f"{printed}: figures/{{name}}.svg")
'''


def helper(cfg: dict | None = None) -> str:
    """The shared style's file, as every book gets it, from data/figures.toml."""
    s = cfg or settings()
    style, colours = s["style"], s["palette"]
    width = max(len(n) for n in colours)
    lines = "\n".join(f'{n} = "{c["value"]}"{" " * (width - len(n))}    # the {c["token"]} token' for n, c in colours.items())
    series = style["series"]
    return HELPER.format(palette=lines, series=", ".join(series) + ("," if len(series) == 1 else ""),
                         width=style["width_inches"], height=style["height_inches"], salt=style["hash_salt"],
                         fonts="[" + ", ".join(f'"{f}"' for f in style["fonts"]) + "]", font_size=style["font_size"],
                         grid_width=style["grid_width"], line_width=style["line_width"],
                         styles="[" + ", ".join('"--"' if i >= 2 else '"-"' for i in range(len(series))) + "]",
                         printed=s["format"]["printed"])


def helper_path(root: Path) -> Path:
    return Path(root) / settings()["format"]["helper"]


def has_figures(root: Path) -> bool:
    """Whether a book keeps any figure, or its chapters embed one: then it needs the shared style."""
    d = Path(root) / folder()
    return d.is_dir() and any(d.glob("*.svg"))


def helper_problems(root: Path, needed: bool | None = None) -> list[str]:
    """The shared style missing or changed, in a book that has figures (or `needed`)."""
    path = helper_path(root)
    rel = settings()["format"]["helper"]
    if needed is None:
        needed = has_figures(root) or path.is_file()
    if not needed:
        return []
    if not path.is_file():
        return [f"{rel} is missing: a book with figures draws them with the shared style; re-check figures --book . --write"]
    if path.read_text(encoding="utf-8") != helper():
        return [f"{rel} isn't the standards' shared style: it's generated, so the book's own code goes beside it; "
                "re-check figures --book . --write writes it again"]
    return []


def write_helper(root: Path) -> list[str]:
    """The shared style into the book; what was written."""
    path = helper_path(root)
    text = helper()
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return [settings()["format"]["helper"]]


# ---------------------------------------------------------------- the SVG

ELEMENTS = {"svg", "g", "defs", "path", "use", "clipPath", "rect", "circle", "ellipse", "line", "polyline", "polygon",
            "text", "tspan", "title", "desc", "linearGradient", "radialGradient", "stop", "pattern", "marker", "symbol",
            "mask"}
DROPPED = {"metadata"}                  # left out of what a surface shows; a <style> becomes attributes
# The CSS properties SVG has as presentation attributes: a style attribute's declarations become these
PRESENTATION = {"alignment-baseline", "baseline-shift", "clip-path", "clip-rule", "color", "display", "dominant-baseline",
                "fill", "fill-opacity", "fill-rule", "font-family", "font-size", "font-stretch", "font-style",
                "font-variant", "font-weight", "letter-spacing", "marker-end", "marker-mid", "marker-start", "mask",
                "opacity", "paint-order", "shape-rendering", "stop-color", "stop-opacity", "stroke", "stroke-dasharray",
                "stroke-dashoffset", "stroke-linecap", "stroke-linejoin", "stroke-miterlimit", "stroke-opacity",
                "stroke-width", "text-anchor", "text-decoration", "text-rendering", "visibility", "word-spacing",
                "writing-mode", "white-space"}
URL = re.compile(r"url\(\s*['\"]?([^'\")]*)['\"]?\s*\)")
NUMBER = re.compile(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?")
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
COLOUR_PROPS = ("fill", "stroke", "stop-color", "color")


class SvgError(ValueError):
    """An SVG that can't be read, or that holds what a figure never may."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _attr_name(key: str) -> str:
    if key.startswith(f"{{{XLINK_NS}}}"):
        return "xlink:" + key.split("}", 1)[1]
    if key.startswith(f"{{{XML_NS}}}"):
        return "xml:" + key.split("}", 1)[1]
    return key


def parse(text: str) -> ElementTree.Element:
    """The SVG as a tree. The standard library's parser never fetches anything; an SVG that declares entities, or isn't
    an <svg>, is refused."""
    if re.search(r"<!ENTITY", text, re.I) or re.search(r"<!DOCTYPE[^>]*\[", text, re.I):
        raise SvgError("it declares XML entities, which a figure never needs")
    try:
        root = ElementTree.fromstring(text.encode("utf-8"))
    except ElementTree.ParseError as e:
        raise SvgError(f"it isn't well-formed XML: {e}") from None
    if root.tag != f"{{{SVG_NS}}}svg":
        raise SvgError("it isn't an SVG: its root element isn't <svg> in the SVG namespace")
    return root


def styles(value: str) -> list[tuple[str, str]]:
    """A style attribute's (or a rule's) declarations, in order."""
    out = []
    for part in value.split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip():
                out.append((k.strip().lower(), v.strip()))
    return out


def _refs_ok(value: str) -> bool:
    """Every url() and address in a value is a reference inside the SVG itself (#id)."""
    return all(u.strip().startswith("#") for u in URL.findall(value))


def active_problems(text: str) -> list[str]:
    """What in an SVG could run or reach outside itself: a script, an event handler, a foreignObject, an element a
    figure never needs, a link, style or image from elsewhere, or an entity. Empty for a safe one."""
    try:
        root = parse(text)
    except SvgError as e:
        return [str(e)]
    problems: set[str] = set()
    if re.search(r"<\?xml-stylesheet", text, re.I):
        problems.add("it links a stylesheet (<?xml-stylesheet?>)")
    metadata = {d for m in root.iter(f"{{{SVG_NS}}}metadata") for d in m.iter()}
    for el in root.iter():
        if not isinstance(el.tag, str) or el in metadata:
            continue
        tag = _local(el.tag)
        if not el.tag.startswith(f"{{{SVG_NS}}}"):
            problems.add(f"it holds a <{tag}> element from another namespace")
            continue
        if tag == "style":
            if _style_rule(el.text or "") is None:
                problems.add("its <style> holds more than the defaults every element takes")
            continue
        if tag not in ELEMENTS:
            problems.add(f"it holds a <{tag}> element, which a figure never needs" +
                         (": draw it with paths, as pcolormesh does, not as an embedded image" if tag == "image" else ""))
        for key, value in el.attrib.items():
            name = _attr_name(key).lower()
            low = value.lower()
            if name.startswith("on"):
                problems.add(f"<{tag}> has an event handler ({name})")
            elif name in ("href", "xlink:href") and not value.strip().startswith("#"):
                problems.add(f"<{tag}> refers to {value[:60]!r}, outside the figure")
            elif "javascript:" in low or "data:" in low:
                problems.add(f"<{tag}> has {name}={value[:60]!r}")
            elif not _refs_ok(value):
                problems.add(f"<{tag}> refers to {', '.join(URL.findall(value))[:60]!r}, outside the figure")
            elif name == "style" and re.search(r"@import|expression\(|behavior\s*:", value, re.I):
                problems.add(f"<{tag}> has a style that loads or runs something")
    return sorted(problems)


def _style_rule(css: str) -> list[tuple[str, str]] | None:
    """A <style> that only sets defaults every element takes, as matplotlib's `*{stroke-linejoin: round; …}`: its
    declarations, which become the root's inherited attributes. None for anything else."""
    m = re.fullmatch(r"\s*\*\s*\{([^{}]*)\}\s*", css or "")
    if not m:
        return None
    found = styles(m.group(1))
    return found if all(k in PRESENTATION and "url(" not in v.lower() for k, v in found) else None


# ---------------------------------------------------------------- comparing two SVGs


def _ids(root: ElementTree.Element) -> dict[str, str]:
    """Each ID in the order it appears, as id1, id2, …: matplotlib names a clip path or a marker by a hash of its
    coordinates, which a last-bit difference changes."""
    out: dict[str, str] = {}
    for el in root.iter():
        value = el.attrib.get("id")
        if value is not None and value not in out:
            out[value] = f"id{len(out) + 1}"
    return out


def _canonical_refs(value: str, ids: dict[str, str]) -> str:
    value = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{ids.get(m.group(1), m.group(1))})", value)
    return re.sub(r"^#(\S+)$", lambda m: f"#{ids.get(m.group(1), m.group(1))}", value)


def _split_numbers(value: str) -> tuple[str, list[float]]:
    """A value with each number taken out, and the numbers: a colour stays as it is written."""
    words, numbers = [], []
    pos = 0
    for m in re.finditer(f"{HEX.pattern}|{NUMBER.pattern}", value):
        words.append(value[pos:m.start()])
        if m.group(0).startswith("#"):
            words.append(m.group(0))
        else:
            words.append("\0")
            numbers.append(float(m.group(0)))
        pos = m.end()
    words.append(value[pos:])
    return "".join(words), numbers


def compare(expected: str, actual: str, tolerance: float | None = None, limit: int = 5) -> list[str]:
    """How `actual` differs from `expected`, read as SVG trees: each element, attribute name and text the same, IDs read
    in the order they appear, and each number in an attribute within `tolerance` ([compare] tolerance). Empty when they
    match. A number in text, such as a tick label, must be the same."""
    if expected == actual:
        return []
    tol = float(settings()["compare"]["tolerance"] if tolerance is None else tolerance)
    try:
        a, b = parse(expected), parse(actual)
    except SvgError as e:
        return [f"it can't be compared: {e}"]
    ids_a, ids_b = _ids(a), _ids(b)
    found: list[str] = []

    def walk(x: ElementTree.Element, y: ElementTree.Element, where: str) -> None:
        if len(found) >= limit:
            return
        if x.tag != y.tag:
            found.append(f"{where}: <{_local(y.tag)}> where the committed figure has <{_local(x.tag)}>")
            return
        if set(x.attrib) != set(y.attrib):
            gone, new = sorted(set(x.attrib) - set(y.attrib)), sorted(set(y.attrib) - set(x.attrib))
            found.append(f"{where}: attributes differ" + (f"; without {', '.join(map(_attr_name, gone))}" if gone else "")
                         + (f"; with {', '.join(map(_attr_name, new))}" if new else ""))
            return
        for key in x.attrib:
            va, vb = x.attrib[key], y.attrib[key]
            if key == "id":
                va, vb = ids_a.get(va, va), ids_b.get(vb, vb)
            else:
                va, vb = _canonical_refs(va, ids_a), _canonical_refs(vb, ids_b)
            if va == vb:
                continue
            (wa, na), (wb, nb) = _split_numbers(va), _split_numbers(vb)
            if wa != wb or len(na) != len(nb):
                found.append(f"{where}: {_attr_name(key)} is {_short(vb)} where the committed figure has {_short(va)}")
                return
            gap = max((abs(p - q) for p, q in zip(na, nb)), default=0.0)
            if gap > tol:
                found.append(f"{where}: {_attr_name(key)} moved by {gap:g}, more than the tolerance of {tol:g}")
                return
        if (x.text or "").strip() != (y.text or "").strip():
            found.append(f"{where}: the text is {(y.text or '').strip()!r} where the committed figure has "
                         f"{(x.text or '').strip()!r}")
            return
        kids_a, kids_b = list(x), list(y)
        if len(kids_a) != len(kids_b):
            found.append(f"{where}: {len(kids_b)} elements inside where the committed figure has {len(kids_a)}")
            return
        seen: dict[str, int] = {}
        for ca, cb in zip(kids_a, kids_b):
            tag = _local(ca.tag)
            seen[tag] = seen.get(tag, 0) + 1
            walk(ca, cb, f"{where}/{tag}[{seen[tag]}]")
    walk(a, b, "/svg")
    return found


def _short(value: str, n: int = 60) -> str:
    return repr(value if len(value) <= n else value[:n] + "…")


# ---------------------------------------------------------------- what a surface shows


@dataclass
class Clean:
    svg: str                            # the SVG to show
    width: str = ""                     # the drawing's size, as the SVG gave it (in points, from matplotlib)
    height: str = ""
    view_box: str = ""
    texts: list[str] = field(default_factory=list)   # the words inside it, for the files' font subsets


def clean(text: str, prefix: str | None = None, inline: bool = False, classes: dict[str, str] | None = None,
          root_attrs: dict[str, str] | None = None) -> Clean:
    """The SVG a surface shows (module docstring). `inline`, for a page: IDs prefixed with `prefix`, only those it
    refers to kept, its width and height left to the page, and each colour in `classes` (a colour as the SVG writes it
    to a class's stem) classed `{stem}-fill` or `{stem}-stroke`. `root_attrs` go on the <svg>, such as its role and
    label. Refuses one with anything active (active_problems)."""
    problems = active_problems(text)
    if problems:
        raise SvgError("; ".join(problems))
    root = parse(text)
    used: set[str] = set()
    for el in root.iter():
        for key, value in el.attrib.items():
            used.update(re.findall(r"url\(#([^)]+)\)", value))
            if _attr_name(key) in ("href", "xlink:href") and value.startswith("#"):
                used.add(value[1:])
    inherited: list[tuple[str, str]] = []
    out = Clean("", root.attrib.get("width", ""), root.attrib.get("height", ""), root.attrib.get("viewBox", ""))
    renamed = inline and bool(prefix)

    def ref(name: str, value: str) -> str:
        """A reference to an ID inside the SVG, renamed with the prefix: url(#id) in any value, #id in an address."""
        if not renamed:
            return value
        value = re.sub(r"url\(#([^)]+)\)", lambda m: f"url(#{prefix}{m.group(1)})", value)
        return f"#{prefix}{value[1:]}" if name in ("href", "xlink:href") and value.startswith("#") else value

    def attributes(el: ElementTree.Element) -> dict[str, str]:
        attrs: dict[str, str] = {}
        for key, value in el.attrib.items():
            name = _attr_name(key)
            if name == "style":
                continue
            if name == "id":
                if not inline or value in used:
                    attrs["id"] = f"{prefix}{value}" if renamed else value
                continue
            attrs[name] = ref(name, value)
        for prop, value in styles(el.attrib.get("style", "")):
            if prop not in PRESENTATION:
                raise SvgError(f"<{_local(el.tag)}> has the style {prop}, which SVG has no attribute for")
            attrs[prop] = ref(prop, value)
        if inline and "d" in attrs:
            attrs["d"] = re.sub(r"\s+", " ", attrs["d"]).strip()
        if inline and classes:
            found = [f"{classes[attrs[p].lower()]}-{p}" for p in ("fill", "stroke")
                     if p in attrs and attrs[p].lower() in classes]
            if found:
                attrs["class"] = " ".join(filter(None, [attrs.get("class", ""), *found]))
        return attrs

    def tag_open(tag: str, attrs: dict[str, str]) -> str:
        return f"<{tag}" + "".join(f' {k}="{_attr(v)}"' for k, v in attrs.items())

    def words(value: str | None) -> str:
        if value and value.strip():
            out.texts.append(value.strip())
            return html.escape(value, quote=False)
        return ""

    def write(el: ElementTree.Element) -> str:
        tag = _local(el.tag)
        tail = words(el.tail) if tag == "tspan" else ""
        if tag in DROPPED:
            return ""
        if tag == "style":
            inherited.extend(_style_rule(el.text or "") or [])
            return ""
        attrs = attributes(el)
        body = (words(el.text) if tag in ("text", "tspan", "title", "desc") else "") + "".join(write(c) for c in el)
        if tag == "defs" and not body:
            return tail
        if not body and tag not in ("text", "tspan"):
            return tag_open(tag, attrs) + "/>" + tail
        return f"{tag_open(tag, attrs)}>{body}</{tag}>" + tail

    inner = "".join(write(child) for child in root)
    attrs = {"xmlns": SVG_NS, **({"xmlns:xlink": XLINK_NS} if _uses_xlink(root) else {})}
    for key, value in attributes(root).items():
        if key == "version" or (inline and key in ("width", "height")):
            continue
        attrs[key] = value
    for key, value in inherited:                 # the defaults every element took: inherited from the root
        attrs.setdefault(key, value)
    attrs.update(root_attrs or {})
    out.svg = f"{tag_open('svg', attrs)}>{inner}</svg>"
    return out


def _attr(value: str) -> str:
    """An attribute's value, quoted for "…": its &, <, > and " escaped, its ' as it is (a font's name keeps its quotes)."""
    return html.escape(value, quote=False).replace('"', "&quot;")


def _uses_xlink(root: ElementTree.Element) -> bool:
    return any(k.startswith(f"{{{XLINK_NS}}}") for el in root.iter() for k in el.attrib)


def colours(text: str) -> set[str]:
    """Every colour an SVG draws with, as it writes them (lowercase), its metadata aside."""
    try:
        root = parse(text)
    except SvgError:
        return set()
    found: set[str] = set()
    for el in root.iter():
        values = [(p, v) for p, v in styles(el.attrib.get("style", ""))] + \
            [(k, v) for k, v in el.attrib.items() if k in COLOUR_PROPS]
        for prop, value in values:
            if prop in COLOUR_PROPS and value.strip().lower() not in ("none", "currentcolor", "inherit", "transparent") \
                    and not value.strip().startswith("url("):
                found.add(value.strip().lower())
    return found


# ---------------------------------------------------------------- the book's checks


def drawn_by(book: "Book") -> dict[str, list[str]]:
    """Each figure an example's recorded output names, to the examples that name it."""
    out: dict[str, list[str]] = {}
    for eid in sorted(book.examples):
        for name in printed(book.examples[eid].expected):
            out.setdefault(name, []).append(eid)
    return out


def problems(book: "Book") -> list[str]:
    """The format's problems (module docstring): what the section-ID check fails."""
    s = settings()
    found: list[str] = []
    rel_folder = s["format"]["folder"]
    by = drawn_by(book)
    seen: dict[str, str] = {}
    for c in book.chapters:
        for f in c.figures:
            where = f"{c.file}:{f.start + c.body_offset + 1}"
            if f.name is None:
                found.append(f"{where}: an image no example draws ({f.src}): a figure is an example's output, "
                             f"embedded as ![its point](../{rel_folder}/NAME.svg \"Its caption\")")
                continue
            if f.name in seen:
                found.append(f"{where}: figure {f.name!r} is embedded more than once (first in {seen[f.name]}); a "
                             "figure's name is unique in its book")
                continue
            seen[f.name] = c.file
            for part, text in (("alt text", f.alt), ("caption", f.caption)):
                if "{{fig:" in text.replace(" ", ""):
                    found.append(f"{where}: the {part} of figure {f.name!r} points to a figure; say it in the prose")
            path = book.root / rel_folder / f"{f.name}.svg"
            if not path.is_file():
                found.append(f"{where}: embeds {rel_folder}/{f.name}.svg, which doesn't exist; record it with "
                             "re-check examples --record")
                continue
            here = [e for e in by.get(f.name, []) if book.examples[e].chapter_id == c.chapter_id]
            if not here:
                elsewhere = by.get(f.name, [])
                found.append(f"{where}: figure {f.name!r} isn't drawn by an example this chapter embeds" +
                             (f" ({', '.join(elsewhere)} draws it, in another chapter)" if elsewhere else
                              f": its example saves it with save(fig, \"{f.name}\"), and its recorded output names it"))
            found += [f"{rel_folder}/{f.name}.svg: {p}" for p in svg_problems(path)]
        found += [f"{c.file}:{line + c.body_offset + 1}: an image no example draws ({src}): a figure is an example's "
                  "output, in a paragraph of its own" for line, src in c.images]
    folder_path = book.root / rel_folder
    for path in sorted(folder_path.glob("*")) if folder_path.is_dir() else []:
        if path.suffix != ".svg" or not NAME.match(path.stem):
            found.append(f"{rel_folder}/{path.name}: {rel_folder}/ holds only figures, each NAME.svg, its name lowercase "
                         "words joined by hyphens")
        elif path.stem not in seen:
            found.append(f"{rel_folder}/{path.name}: not embedded in any chapter")
    for name, eids in sorted(by.items()):
        if not (folder_path / f"{name}.svg").is_file() and name not in seen:
            found.append(f"examples/{eids[0]}.out names figures/{name}.svg, which isn't in {rel_folder}/: record it with "
                         "re-check examples --record")
    found += helper_problems(book.root, needed=bool(seen) or has_figures(book.root))
    return found


def svg_problems(path: Path) -> list[str]:
    s = settings()
    size = path.stat().st_size
    if size > int(s["format"]["max_bytes"]):
        return [f"{size:,} bytes, more than the {int(s['format']['max_bytes']):,} a figure may be: draw fewer points, or "
                "less of the data"]
    text = path.read_text(encoding="utf-8", errors="replace")
    return active_problems(text)


def writing_problems(book: "Book") -> list[str]:
    """The writing's problems: W-39 for alt text, W-82 for the rest (module docstring)."""
    s = settings()["check"]
    found: list[str] = []
    allowed = set(palette_tokens())
    referenced = {m.group(2).strip() for c in book.chapters for m in _bindings(c.body) if m.group(1) == "fig"}
    for c in book.chapters:
        for f in c.figures:
            if f.name is None:
                continue
            where = f"{c.file}:{f.start + c.body_offset + 1}"
            alt = f.alt.strip()
            words = re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", alt)
            if not alt:
                found.append(f"{where}: W-39: figure {f.name!r} needs alt text that states its point")
            elif len(words) < int(s["alt_min_words"]) or alt.lower().replace(" ", "-") in (f.name, f"{f.name}.svg") \
                    or re.search(r"\.(svg|png)\b", alt, re.I) or TYPED.match(alt):
                found.append(f"{where}: W-39: the alt text of figure {f.name!r} names it rather than stating its "
                             f"point ({alt!r}); say what a reader sees in it, in a sentence")
            caption = f.caption.strip()
            if not caption:
                found.append(f"{where}: W-82: figure {f.name!r} needs a caption, the title after its address: "
                             f"![its point](../examples/figures/{f.name}.svg \"What it draws\")")
            elif len(caption.split()) > int(s["caption_max_words"]):
                found.append(f"{where}: W-82: the caption of figure {f.name!r} has {len(caption.split())} words; name "
                             f"what it draws in at most {s['caption_max_words']}, and say what to see in the prose")
            if f.name not in referenced:
                found.append(f"{where}: W-82: the prose never points to figure {f.name!r}; say what to see in it, with "
                             f"{{{{fig:{f.name}}}}} for its number")
            path = book.root / folder() / f"{f.name}.svg"
            if path.is_file():
                odd = sorted(colours(path.read_text(encoding="utf-8", errors="replace")) - allowed)
                if odd:
                    found.append(f"{folder()}/{f.name}.svg: W-82: draws in {', '.join(odd)}, which the shared style's "
                                 "palette doesn't have, so the dark theme can't show it; use ACCENT, INK, MUTED or RULE")
    for c in book.chapters:
        for n, line in _prose(c):
            for m in TYPED.finditer(line):
                found.append(f"{c.file}:{n}: W-82: a typed figure number ({m.group(0)!r}); write {{{{fig:NAME}}}}, which "
                             "the build numbers")
    for eid, ex in book.examples.items():
        if (book.root / folder()).is_dir() and printed(ex.expected):
            for m in TYPED.finditer(ex.code):
                found.append(f"{ex.file}: W-82: a typed figure number ({m.group(0)!r}) in the example; its docstring "
                             "says what it draws, and the chapter numbers it")
                break
    return found


def _bindings(text: str):
    from .bookfmt import BINDING
    return BINDING.finditer(text)


def _prose(chapter) -> list[tuple[int, str]]:
    from .style import _prose_lines
    return [(n, t) for n, t in _prose_lines(chapter.body, chapter.body_offset)
            if not t.lstrip().startswith("![")]
