"""This repository is public, so nothing in it cites Rolling Edition's private planning log: its decision and
question IDs, and its file names, mean nothing to a reader. Say the reason in plain words instead."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = re.compile(r"\b[DQ]-\d+\b|\bdecisions\.md\b|\bspecs/")
TEXT = {".py", ".md", ".toml", ".json", ".yml", ".yaml", ".txt", ".cff", ""}
SKIP = {".git", "__pycache__", ".venv", ".pytest_cache"}
FETCHED = {ROOT / "templates" / "licenses", ROOT / "templates" / "community" / "contributor-covenant-2.1.md"}


def ours(path: Path) -> bool:
    parts = path.relative_to(ROOT).parts
    return (path.is_file() and path.suffix in TEXT and not SKIP & set(parts) and not any(p.endswith(".egg-info") for p in parts)
            and not any(path == f or f in path.parents for f in FETCHED))


def test_nothing_cites_the_private_planning_log():
    hits = [f"{p.relative_to(ROOT)}:{n}: {m.group()}"
            for p in sorted(ROOT.rglob("*")) if ours(p)
            for n, line in enumerate(p.read_text(encoding="utf-8", errors="replace").splitlines(), 1)
            for m in PRIVATE.finditer(line)]
    assert not hits, "say it in plain words instead:\n" + "\n".join(hits)
