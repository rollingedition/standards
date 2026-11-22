"""`re-check rules`: the writing standards cut to what one task needs.

A subagent that opens writing/README.md whole carries about 12,000 tokens it mostly doesn't apply, on every turn of its
task; in the security book that, with the exemplars, put nearly every task over its budget (P-7). This prints every
rule as one line, its ID, title and how it's checked, and in full only the sections or rules a task applies. A brief
gives its subagent this output, so the subagent never opens the README.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import standards_root

SECTION = re.compile(r"^## (\d+)\. (.+?)\s*$")
RULE = re.compile(r"^\*\*(W-\d+) (.+?)\*\*")
CHECKS = ("lint", "critic", "reviewer")


@dataclass
class Rule:
    id: str
    title: str
    section: int
    text: str

    @property
    def checks(self) -> list[str]:
        """How it's checked, from its *Check:* line, in the README's words."""
        line = next((l for l in self.text.splitlines() if "*Check:*" in l), "")
        said = line.split("*Check:*", 1)[1].lower() if line else ""
        return [c for c in CHECKS if c in said]

    def line(self) -> str:
        checks = f" ({', '.join(self.checks)})" if self.checks else ""
        return f"- {self.id} {self.title.rstrip('.')}.{checks}"


@dataclass
class Section:
    number: int
    title: str
    rules: list[Rule]


def readme_path() -> Path:
    return standards_root() / "writing" / "README.md"


def parse(text: str) -> list[Section]:
    """The README's numbered sections and the rules in each, every rule's text up to the next rule or heading."""
    sections: list[Section] = []
    rule: Rule | None = None
    body: list[str] = []

    def close():
        nonlocal rule, body
        if rule:
            rule.text = "\n".join(body).strip()
            sections[-1].rules.append(rule)
        rule, body = None, []

    for line in text.splitlines():
        if line.startswith("## "):
            close()
            m = SECTION.match(line)
            if m:
                sections.append(Section(int(m.group(1)), m.group(2), []))
            continue
        m = RULE.match(line)
        if m and sections:
            close()
            rule = Rule(m.group(1), m.group(2), sections[-1].number, "")
        if rule:
            body.append(line)
    close()
    return sections


def cut(sections: list[Section], full_sections: set[int], full_rules: set[str]) -> str:
    """Every rule as a line; in full, the rules of `full_sections` and each rule in `full_rules`."""
    out = ["Writing standards, cut for one task: every rule as a line, and in full only what this task applies. "
           "The rule's text in writing/README.md wins; it's the same text, cut here."]
    for s in sections:
        out.append(f"\n## {s.number}. {s.title}")
        for r in s.rules:
            out.append("\n" + r.text if s.number in full_sections or r.id in full_rules else r.line())
    return "\n".join(out).rstrip() + "\n"


def unknown(sections: list[Section], full_sections: set[int], full_rules: set[str]) -> list[str]:
    numbers = {s.number for s in sections}
    ids = {r.id for s in sections for r in s.rules}
    return ([f"no section {n} in writing/README.md" for n in sorted(full_sections - numbers)]
            + [f"no rule {i} in writing/README.md" for i in sorted(full_rules - ids)])
