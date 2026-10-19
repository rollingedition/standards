"""The organization's community files, generated for its public .github repository.

GitHub applies them to every repository in the organization that has none of its own: the contributing
guide, the code of conduct (the Contributor Covenant 2.1, fetched verbatim), the security policy, issue
forms and the pull request template. The repository's own README says what's in it, and profile/README.md
is the organization's page on GitHub. Conduct and security reports go to the addresses in data/community.toml.
"""
from __future__ import annotations

import tomllib
from pathlib import Path

from . import data_path
from .readme import TEMPLATES
from .tape import KIND_LABELS

COMMUNITY = TEMPLATES / "community"


def load_config(path: Path | None = None) -> dict:
    with open(path or data_path("community.toml"), "rb") as f:
        return tomllib.load(f)


def files(cfg: dict | None = None) -> tuple[dict[str, str], list[str]]:
    """({path in the .github repository: text}, problems)."""
    cfg = cfg or load_config()
    kinds = ", ".join(f"`{k}`" for k in KIND_LABELS)

    def fill(name: str) -> str:
        return ((COMMUNITY / name).read_text(encoding="utf-8").replace("{kinds}", kinds).replace("{standards}", cfg["standards"])
                .replace("{site}", cfg["site"]).replace("{security_contact}", cfg.get("security_contact", ""))
                .replace("{contributing}", cfg.get("contributing", "")))
    out = {
        "README.md": fill("README.md"),
        "profile/README.md": fill("profile-README.md"),
        "CONTRIBUTING.md": fill("CONTRIBUTING.md"),
        ".github/PULL_REQUEST_TEMPLATE.md": fill("PULL_REQUEST_TEMPLATE.md"),
        ".github/ISSUE_TEMPLATE/report-an-error.yml": fill("report-an-error.yml"),
        ".github/ISSUE_TEMPLATE/ask-a-question.yml": fill("ask-a-question.yml"),
        ".github/ISSUE_TEMPLATE/config.yml": fill("issue-config.yml"),
    }
    problems = []
    if cfg.get("security_contact"):
        out["SECURITY.md"] = fill("SECURITY.md")
    else:
        problems.append("SECURITY.md: set security_contact in data/community.toml, where security reports go when a "
                        "repository's Security tab doesn't offer private reporting")
    covenant = (COMMUNITY / "contributor-covenant-2.1.md").read_text(encoding="utf-8")
    body = covenant.split("+++", 2)[2].lstrip() if covenant.startswith("+++") else covenant
    if cfg.get("conduct_contact"):
        out["CODE_OF_CONDUCT.md"] = body.replace("[INSERT CONTACT METHOD]", cfg["conduct_contact"])
    else:
        problems.append("CODE_OF_CONDUCT.md: set conduct_contact in data/community.toml, where conduct reports go")
    return out, problems


def write(folder: Path, cfg: dict | None = None) -> list[str]:
    out, problems = files(cfg)
    for name, text in out.items():
        path = folder / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return problems
