"""`re-check rules`: the writing standards cut for one task (P-7), from the README itself, never typed."""
import re

from re_standards import cli, digest

README = digest.readme_path().read_text(encoding="utf-8")


def test_every_rule_in_the_standards_is_cut_once_in_its_own_section():
    sections = digest.parse(README)
    ids = [r.id for s in sections for r in s.rules]
    assert ids and len(ids) == len(set(ids))
    assert sorted(ids) == sorted(re.findall(r"^\*\*(W-\d+) ", README, re.M))
    w28 = next(r for s in sections for r in s.rules if r.id == "W-28")
    assert w28.section == 6 and w28.title.startswith("Every claim about a tool")
    assert w28.text.startswith("**W-28") and "*Check:*" in w28.text and "**W-29" not in w28.text


def test_a_task_gets_every_rule_as_a_line_and_only_what_it_applies_in_full(capsys):
    assert cli.main(["rules", "--section", "6", "--rule", "w-26"]) == 0
    out = capsys.readouterr().out
    assert "- W-24 No time words. (lint, critic)" in out                     # a line: ID, title, how it's checked
    assert "**W-26 Bind numbers from outputs.**" in out                      # asked for by ID, in full
    assert "**W-29 Citations must resolve.**" in out                         # its section, in full
    assert "**W-63" not in out and "- W-63 " in out
    assert len(out) < len(README) / 3


def test_a_section_or_rule_the_standards_dont_have_fails_rather_than_cutting_silently(capsys):
    assert cli.main(["rules", "--section", "99", "--rule", "W-999"]) == 1
    seen = capsys.readouterr()
    out = seen.out + seen.err
    assert "no section 99" in out and "no rule W-999" in out
