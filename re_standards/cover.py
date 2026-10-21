"""Cover SVG: the title, its punched tape, the edition fingerprint, the edition line and the footer.

The executable form of the cover-generation spec. Layout is in 300 x 480 cover units; the 1600 x 2560
master is the same layout scaled by 16/3. Standard library only, plus optional fontTools for real
font metrics when RE_TITLE_FONT points at Literata SemiBold.

On the site's pages the cover's text is live type, in the site's web fonts. A cover file is shown as an image
everywhere else (a book's README, a download), and an image can't load a web font, so `outlined=True` draws the
same text, in the same places, as outlines: the title's and the code's from data/cover-glyphs.json, generated from
the fonts with their kerning and ligatures, and the wordmark's from data/mark-outlines.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from xml.sax.saxutils import escape

from . import data_path, mark
from .tape import fingerprint_columns, parse_code, title_strips, bits5

# Cover tokens: the same values in both themes, because a cover is an image and never flips.
COVER_GROUND = "#1f3d3b"     # deep teal
COVER_PAPER = "#fbf5e6"      # buff, the colour of paper tape
COVER_TAIL = "#e58f2a"       # amber: the fingerprint and the icon's tile
INK = "#1b1712"              # the icon's R, as on every icon
COVER_MUTED = "#a8c4c0"

# Page geometry, in cover units.
COVER_W, COVER_H = 300, 480
MASTER_W = 1600
MARGIN_X, MARGIN_TOP, MARGIN_BOTTOM = 28, 28, 24
TITLE_ZONE_H = 88
TITLE_SIZE, TITLE_MIN_SIZE, TITLE_LEADING, TITLE_MAX_LINES = 25.0, 20.0, 1.14, 3
FIELD_GAP = 20                        # title zone to tape field
FIELD_W, FIELD_H = 244, 230
CODE_SIZE, CODE_OFFSET, CODE_LINE = 11, 6, 14
LINE_SIZE, LINE_RISE = 11, 16          # the edition line: the edition number's size, its baseline above the footer
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
FOOT_H, FOOT_GAP, MARK_SIZE = 22, 14, 22
WORDMARK_SIZE, WORDMARK_GAP, CAP = 16, 6, 0.705   # the footer's wordmark: the icon is 1.4 times it

# Tape geometry at scale k = 1. Every value scales with k when a long title needs three strips.
P, HOLE, FEED, PAD, LEAD, GAP, CUT, TAIL_GAP = 8, 6, 3, 5, 2, 10, 8, 8
MAX_STRIPS = 3
MIN_K = 5 / 8                         # the pitch never drops below 5 units

FONT_PATH_ENV = "RE_TITLE_FONT"
_font_cache: dict[str, tuple] = {}


# ---------------------------------------------------------------- title


def measure_text(text: str, size: float) -> float:
    """Advance width in cover units: Literata SemiBold metrics when RE_TITLE_FONT is set,
    otherwise a conservative per-character estimate."""
    path = os.environ.get(FONT_PATH_ENV)
    if path:
        try:
            from fontTools.ttLib import TTFont  # type: ignore
            if path not in _font_cache:
                font = TTFont(path)
                _font_cache[path] = (font.getBestCmap(), font["hmtx"].metrics, font["head"].unitsPerEm)
            cmap, hmtx, upm = _font_cache[path]
            total = sum(hmtx[cmap.get(ord(ch)) or cmap.get(ord("n"))][0] for ch in text)
            return total * size / upm
        except Exception:
            pass
    narrow, wide = set("fijlrt.,:;'!|- "), set("mwMW")
    em = 0.0
    for ch in text:
        if ch in narrow:
            em += 0.34
        elif ch in wide:
            em += 0.86
        elif ch.isupper():
            em += 0.70
        else:
            em += 0.57
    return em * size


def wrap_title(title: str, size: float, width: float = FIELD_W) -> list[str]:
    """Greedy wrap at spaces only, so a hyphenated word never breaks after its hyphen."""
    lines: list[str] = []
    current = ""
    for word in title.split():
        trial = f"{current} {word}" if current else word
        if current and measure_text(trial, size) > width:
            lines.append(current)
            current = word
        else:
            current = trial
    if current:
        lines.append(current)
    return lines


def fit_title(title: str) -> tuple[float, list[str]]:
    """The largest size from 25 down to 20, in steps of 1, at which the title fits 3 lines."""
    size = TITLE_SIZE
    while size >= TITLE_MIN_SIZE:
        lines = wrap_title(title, size)
        if len(lines) <= TITLE_MAX_LINES and all(measure_text(line, size) <= FIELD_W for line in lines):
            return size, lines
        size -= 1
    raise ValueError(f"title does not fit three lines at {TITLE_MIN_SIZE} units: {title!r}; set a shorter cover title")


def title_problem(title: str) -> str | None:
    """Why no cover can be drawn for this title, or None: it fits three lines, its tape fits the field, and the cover
    file has an outline for every character."""
    try:
        fit_title(title)
        tape_scale(len(title_strips(title)))
    except ValueError as e:
        return str(e)
    if missing := sorted({ch for ch in title if ch not in glyphs()["title"]["glyphs"]}):
        return f"the cover has no outline for {', '.join(map(repr, missing))}; use another character, or add it to the cover's characters"
    return None


# ---------------------------------------------------------------- tape layout


def tape_field_height(n_strips: int, k: float) -> float:
    band = (2 * PAD + 6 * P) * k
    return n_strips * (band + GAP * k) + TAIL_GAP * k + band + CODE_OFFSET + CODE_LINE


def tape_scale(n_strips: int) -> float:
    """1 when the tape fits the field at full size, otherwise the largest k >= MIN_K that fits,
    rounded down to 4 decimals so the tape never overflows."""
    if n_strips > MAX_STRIPS:
        raise ValueError(f"title tape needs {n_strips} strips; the limit is {MAX_STRIPS}")
    band = 2 * PAD + 6 * P
    k = min(1.0, (FIELD_H - CODE_OFFSET - CODE_LINE) / (n_strips * (band + GAP) + TAIL_GAP + band))
    if k < MIN_K:
        raise ValueError("title tape does not fit the field at the minimum pitch")
    return int(k * 10000) / 10000


@dataclass
class TapeLayout:
    k: float
    strips: list[list[int]]
    tail: list[int]

    @property
    def band(self) -> float:
        return (2 * PAD + 6 * P) * self.k

    def height(self) -> float:
        return tape_field_height(len(self.strips), self.k)


def layout_tape(title: str, code: str) -> TapeLayout:
    strips = title_strips(title)
    return TapeLayout(k=tape_scale(len(strips)), strips=strips, tail=fingerprint_columns(code))


# ---------------------------------------------------------------- outlines


@cache
def glyphs() -> dict:
    with open(data_path("cover-glyphs.json"), encoding="utf-8") as f:
        return json.load(f)


def glyph_run(text: str, face: str) -> tuple[list[tuple[float, int, str]], float]:
    """Each glyph's x in font units, the index of its first character and its outline, and the run's advance: the
    face's ligatures and pair kerning, as a browser sets the same text live. `face` is "title" or "mono"."""
    table = glyphs()[face]
    ligatures, kerning = table.get("ligatures", {}), table.get("kerning", {})
    longest = max(map(len, ligatures), default=1)
    run, x, i, prev = [], 0.0, 0, ""
    while i < len(text):
        for n in range(min(longest, len(text) - i), 0, -1):
            piece = text[i:i + n]
            entry = ligatures.get(piece) if n > 1 else table["glyphs"].get(piece)
            if entry:
                break
        else:
            raise ValueError(f"the cover has no outline for {text[i]!r}; add it to the cover's characters and regenerate "
                             "data/cover-glyphs.json")
        x += kerning.get(prev + piece[0], 0) if prev else 0
        advance, outline = entry
        if outline:
            run.append((x, i, outline))
        x += advance
        prev, i = piece[-1], i + n
    return run, x


def _num(v: float, places: int = 2) -> str:
    return f"{v:.{places}f}".rstrip("0").rstrip(".")


def outlined_text(text: str, face: str, size: float, x: float, y: float, fill: str, letter_spacing: float = 0.0,
                  anchor: str = "start") -> str:
    """The text as one outline per glyph, its baseline at y, from x (or ending at x)."""
    run, advance = glyph_run(text, face)
    scale = size / glyphs()[face]["units_per_em"]
    if anchor == "end":
        x -= advance * scale + letter_spacing * len(text)
    paths = "".join(f'<path transform="matrix({_num(scale, 5)} 0 0 {_num(scale, 5)} {_num(x + gx * scale + letter_spacing * ci)} '
                    f'{_num(y)})" d="{outline}"/>' for gx, ci, outline in run)
    return f'<g fill="{fill}">{paths}</g>'


def outlined_wordmark(x: float, y: float, size: float, fill: str) -> str:
    w = mark.outlines()["wordmark"]
    scale = size / w["font_size"]
    return f'<path transform="matrix({_num(scale, 5)} 0 0 {_num(scale, 5)} {_num(x)} {_num(y)})" d="{w["path"]}" fill="{fill}"/>'


# ---------------------------------------------------------------- SVG


def strip_svg(cols: list[int], x0: float, y0: float, k: float, fill: str) -> list[str]:
    """One strip: the light tape with its angled cut, feed holes on every column, data holes punched through."""
    p, pad, cut = P * k, PAD * k, CUT * k
    columns: list[int | None] = [None] * LEAD + list(cols)
    w = 2 * pad + len(columns) * p
    h = (2 * PAD + 6 * P) * k
    out = [f'<polygon points="{x0 + cut:.2f},{y0:.2f} {x0 + w:.2f},{y0:.2f} {x0 + w:.2f},{y0 + h:.2f} {x0:.2f},{y0 + h:.2f}" fill="{fill}"/>']
    for ci, value in enumerate(columns):
        cx = x0 + pad + ci * p + p / 2
        out.append(f'<circle cx="{cx:.2f}" cy="{y0 + pad + 3 * p + p / 2:.2f}" r="{FEED * k / 2:.2f}" fill="{COVER_GROUND}"/>')
        if not value:
            continue
        for bit_index, bit in enumerate(bits5(value)):
            if bit:
                row = bit_index if bit_index < 3 else bit_index + 1   # row 3 is the feed row
                out.append(f'<circle cx="{cx:.2f}" cy="{y0 + pad + row * p + p / 2:.2f}" r="{HOLE * k / 2:.2f}" fill="{COVER_GROUND}"/>')
    return out


def edition_line(editions: int, first_released: str) -> str:
    """The line above the footer, read at a glance: how many editions the book has had and since when, as "3 editions
    since Oct 2026", or "First edition, Oct 2026". `first_released` is the first edition's release time, ISO 8601."""
    first = datetime.fromisoformat(first_released.replace("Z", "+00:00"))
    since = f"{MONTHS[first.month - 1]} {first.year}"
    return f"First edition, {since}" if editions == 1 else f"{editions} editions since {since}"


def cover_alt(title: str, edition: str, code: str) -> str:
    return f"Cover of {title}, edition {edition}, code {parse_code(code)}"


def render_cover(title: str, edition: str, code: str, editions: int, first_released: str, width: int = MASTER_W,
                 outlined: bool = False) -> str:
    """The SVG for one cover. `editions` counts released editions, including this one, and `first_released` is when
    the first came out, for the edition line. `outlined` draws its text as outlines, for a cover file."""
    if editions < 1:
        raise ValueError("a cover needs at least one edition")
    size, lines = fit_title(title)
    tape = layout_tape(title, code)
    height = round(width * COVER_H / COVER_W)
    alt = escape(cover_alt(title, edition, code))
    o: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {COVER_W} {COVER_H}" role="img" aria-label="{alt}">',
        f"<title>{alt}</title>",
        f'<rect width="{COVER_W}" height="{COVER_H}" rx="4" fill="{COVER_GROUND}"/>',
    ]
    # title
    lh = size * TITLE_LEADING
    first_baseline = MARGIN_TOP + (lh - size) / 2 + size * 0.86
    if outlined:
        o += [outlined_text(line, "title", size, MARGIN_X, round(first_baseline + i * lh, 2), COVER_PAPER) for i, line in enumerate(lines)]
    else:
        o.append(f'<g font-family="Literata, Georgia, serif" font-weight="600" font-size="{size:g}" fill="{COVER_PAPER}">')
        for i, line in enumerate(lines):
            o.append(f'<text x="{MARGIN_X}" y="{first_baseline + i * lh:.2f}">{escape(line)}</text>')
        o.append("</g>")
    # tape field: title strips, then the fingerprint and its code
    fx, y = MARGIN_X, MARGIN_TOP + TITLE_ZONE_H + FIELD_GAP
    for strip in tape.strips:
        o += strip_svg(strip, fx, y, tape.k, COVER_PAPER)
        y += tape.band + GAP * tape.k
    y += TAIL_GAP * tape.k
    o += strip_svg(tape.tail, fx, y, tape.k, COVER_TAIL)
    code_x = fx + (PAD + LEAD * P) * tape.k
    code_y = y + tape.band + CODE_OFFSET + CODE_SIZE * 0.82
    if outlined:
        o.append(outlined_text(parse_code(code), "mono", CODE_SIZE, round(code_x, 2), round(code_y, 2), COVER_TAIL,
                               letter_spacing=round(0.08 * CODE_SIZE, 2)))
    else:
        o.append(
            f'<text x="{code_x:.2f}" y="{code_y:.2f}" font-family="\'IBM Plex Mono\', ui-monospace, monospace" '
            f'font-weight="500" font-size="{CODE_SIZE}" letter-spacing="{0.08 * CODE_SIZE:.2f}" fill="{COVER_TAIL}">{parse_code(code)}</text>'
        )
    # footer: the edition line, then the icon, the wordmark and the edition number
    foot_top = COVER_H - MARGIN_BOTTOM - FOOT_H
    line, line_y = edition_line(editions, first_released), foot_top - LINE_RISE
    if outlined:
        o.append(outlined_text(line, "mono", LINE_SIZE, MARGIN_X, line_y, COVER_MUTED))
    else:
        o.append(
            f'<text x="{MARGIN_X}" y="{line_y}" font-family="\'IBM Plex Mono\', ui-monospace, monospace" '
            f'font-weight="500" font-size="{LINE_SIZE}" fill="{COVER_MUTED}">{escape(line)}</text>'
        )
    o.append(mark.fragment(MARGIN_X, foot_top, MARK_SIZE, COVER_TAIL, INK))
    mid = foot_top + FOOT_H / 2
    word_x, word_y = MARGIN_X + MARK_SIZE + WORDMARK_GAP, mid + WORDMARK_SIZE * CAP / 2   # its capitals centred on the icon
    if outlined:
        o.append(outlined_wordmark(word_x, round(word_y, 2), WORDMARK_SIZE, COVER_PAPER))
        o.append(outlined_text(edition, "mono", 11, COVER_W - MARGIN_X, round(mid + 3.9, 2), COVER_MUTED, anchor="end"))
    else:
        o.append(
            f'<text x="{word_x}" y="{word_y:.2f}" font-family="Literata, Georgia, serif" '
            f'font-weight="600" font-size="{WORDMARK_SIZE}" fill="{COVER_PAPER}"><tspan font-style="italic">Rolling</tspan> Edition</text>'
        )
        o.append(
            f'<text x="{COVER_W - MARGIN_X}" y="{mid + 3.9:.2f}" text-anchor="end" font-family="\'IBM Plex Mono\', ui-monospace, monospace" '
            f'font-weight="500" font-size="11" fill="{COVER_MUTED}">{escape(edition)}</text>'
        )
    o.append("</svg>")
    return "\n".join(o) + "\n"
