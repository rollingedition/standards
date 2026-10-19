"""The Rolling Edition logo: the wordmark is the mark, and an R on an amber tile is the icon.

The wordmark is "Rolling Edition" in Literata SemiBold with "Rolling" in italic. On the site it is live type; in a
file it is outlines. The icon is an upright Literata SemiBold R in ink on an amber tile: the favicon, app icons and
avatars, and the square beside the wordmark in a lockup. Both are drawn from Literata itself, in
data/mark-outlines.json, written by the platform's tools/mark_outlines.py, because a logo file can't load a web font.

    icon_svg(tile, letter)               the icon; radius=0 is full bleed, for the Apple touch icon and avatars
    icon_one_color_svg(ink)              the R cut out of a tile in one ink: embossing and single-ink print
    wordmark_svg(color)                  the wordmark, cropped to its ink
    lockup_svg(word, tile, letter)       the icon beside the wordmark
    lockup_one_color_svg(ink)            the same in one ink, the R cut out of the tile
    social_svg(ground, word, tile, letter)  a 1200 × 630 link preview: the lockup centred on a ground
    fragment(x, y, size, tile, letter)   the icon inside another SVG: cover footers

In a lockup the icon is 1.4 times the wordmark's font size, 0.4 times it from the wordmark, and centred on the
capitals.
"""
from __future__ import annotations

import json
from functools import cache

from . import data_path

GRID = 120
RADIUS = 26                         # the tile's corners on the 120 grid
ICON_RATIO, GAP_RATIO = 1.4, 0.4    # in a lockup: the icon's size and the gap, in units of the wordmark's font size
SOCIAL_W, SOCIAL_H, SOCIAL_LOCKUP = 1200, 630, 800   # the link preview, and the lockup's width on it


@cache
def outlines() -> dict:
    with open(data_path("mark-outlines.json"), encoding="utf-8") as f:
        data = json.load(f)
    if data["icon"]["grid"] != GRID:
        raise ValueError(f"mark-outlines.json draws the icon on a {data['icon']['grid']}-unit grid, not {GRID}")
    return data


def _n(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _open(view_box: str, label: str = "Rolling Edition") -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" role="img" aria-label="{label}">'


def _icon(tile: str, letter: str, radius: float = RADIUS) -> str:
    return f'<rect width="{GRID}" height="{GRID}" rx="{radius}" fill="{tile}"/><path d="{outlines()["icon"]["path"]}" fill="{letter}"/>'


def icon_svg(tile: str, letter: str, radius: float = RADIUS) -> str:
    return f'{_open(f"0 0 {GRID} {GRID}")}{_icon(tile, letter, radius)}</svg>\n'


def _icon_cut(ink: str, radius: float = RADIUS) -> str:
    """The R cut out of the tile, so whatever the tile is printed on shows through it."""
    return (f'<defs><mask id="r" maskUnits="userSpaceOnUse" x="0" y="0" width="{GRID}" height="{GRID}">'
            f'<rect width="{GRID}" height="{GRID}" rx="{radius}" fill="#fff"/><path d="{outlines()["icon"]["path"]}" fill="#000"/></mask></defs>'
            f'<rect width="{GRID}" height="{GRID}" fill="{ink}" mask="url(#r)"/>')


def icon_one_color_svg(ink: str, radius: float = RADIUS) -> str:
    return f'{_open(f"0 0 {GRID} {GRID}")}{_icon_cut(ink, radius)}</svg>\n'


def wordmark_svg(color: str) -> str:
    w = outlines()["wordmark"]
    x0, y0, x1, y1 = w["bounds"]
    return f'{_open(f"{_n(x0)} {_n(y0)} {_n(x1 - x0)} {_n(y1 - y0)}")}<path d="{w["path"]}" fill="{color}"/></svg>\n'


def _lockup(word: str, icon: str) -> tuple[tuple[float, float, float, float], str]:
    """The lockup's view box (x, y, width, height) and its contents, in the wordmark's units. `icon` is the icon's
    contents on its 120 grid."""
    w = outlines()["wordmark"]
    x0, y0, x1, y1 = w["bounds"]
    size, gap = ICON_RATIO * w["font_size"], GAP_RATIO * w["font_size"]
    top = -w["cap_height"] / 2 - size / 2                    # the icon is centred on the capitals
    dx = size + gap - x0                                     # the wordmark's ink starts one gap after the icon
    view = (0, min(top, y0), dx + x1, max(top + size, y1) - min(top, y0))
    body = (f'<svg x="0" y="{_n(top)}" width="{_n(size)}" height="{_n(size)}" viewBox="0 0 {GRID} {GRID}">{icon}</svg>'
            f'<path transform="translate({_n(dx)} 0)" d="{w["path"]}" fill="{word}"/>')
    return view, body


def lockup_svg(word: str, tile: str, letter: str) -> str:
    (x, y, width, height), body = _lockup(word, _icon(tile, letter))
    return f'{_open(f"{_n(x)} {_n(y)} {_n(width)} {_n(height)}")}{body}</svg>\n'


def lockup_one_color_svg(ink: str) -> str:
    (x, y, width, height), body = _lockup(ink, _icon_cut(ink))
    return f'{_open(f"{_n(x)} {_n(y)} {_n(width)} {_n(height)}")}{body}</svg>\n'


def social_svg(ground: str, word: str, tile: str, letter: str) -> str:
    (x, y, width, height), body = _lockup(word, _icon(tile, letter))
    h = SOCIAL_LOCKUP * height / width
    return (f'{_open(f"0 0 {SOCIAL_W} {SOCIAL_H}")}<rect width="{SOCIAL_W}" height="{SOCIAL_H}" fill="{ground}"/>'
            f'<svg x="{_n((SOCIAL_W - SOCIAL_LOCKUP) / 2)}" y="{_n((SOCIAL_H - h) / 2)}" width="{SOCIAL_LOCKUP}" height="{_n(h)}" '
            f'viewBox="{_n(x)} {_n(y)} {_n(width)} {_n(height)}">{body}</svg></svg>\n')


def fragment(x: float, y: float, size: float, tile: str, letter: str) -> str:
    return f'<svg x="{_n(x)}" y="{_n(y)}" width="{_n(size)}" height="{_n(size)}" viewBox="0 0 {GRID} {GRID}">{_icon(tile, letter)}</svg>'
