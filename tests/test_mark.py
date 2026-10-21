import re

from re_standards import cover, mark

INK, AMBER = "#1b1712", "#e58f2a"


def test_the_icon_is_literata_s_r_on_an_amber_tile():
    o = mark.outlines()
    assert o["icon"]["axes"] == {"wght": 600, "opsz": 72} and o["wordmark"]["axes"]["wght"] == 600
    svg = mark.icon_svg(AMBER, INK)
    assert f'<rect width="120" height="120" rx="26" fill="{AMBER}"/><path d="{o["icon"]["path"]}" fill="{INK}"/>' in svg
    assert "<text" not in svg and 'rx="0"' in mark.icon_svg(AMBER, INK, radius=0)    # outlines: a favicon loads no font
    assert 'mask="url(#r)"' in mark.icon_one_color_svg(INK)                            # one ink: the R is cut out


def test_the_wordmark_is_cropped_to_its_ink_and_the_lockup_keeps_its_proportions():
    w = mark.outlines()["wordmark"]
    x0, y0, x1, y1 = w["bounds"]
    assert f'viewBox="{x0:g} {y0:g} {round(x1 - x0, 2):g} {round(y1 - y0, 2):g}"' in mark.wordmark_svg(INK)
    lockup = mark.lockup_svg(INK, AMBER, INK)
    size = float(re.search(r'<svg x="0" y="[-\d.]+" width="([\d.]+)"', lockup).group(1))
    assert size == mark.ICON_RATIO * w["font_size"]                                     # 1.4 times the font size
    assert f'translate({mark._n(size + mark.GAP_RATIO * w["font_size"] - x0)} 0)' in lockup   # then a gap of 0.4
    assert 'viewBox="0 0 1200 630"' in mark.social_svg("#fbf5e6", INK, AMBER, INK)


def test_a_cover_footer_shows_the_icon_and_the_wordmark():
    svg = cover.render_cover("A Tiny Book", "2026.10.1", "7K3M-Q9TD", 1, "2026-10-19T12:00:00Z")
    assert mark.outlines()["icon"]["path"] in svg
    assert '<tspan font-style="italic">Rolling</tspan> Edition</text>' in svg and "IBM Plex Sans" not in svg.split("Rolling</tspan>")[0][-300:]
