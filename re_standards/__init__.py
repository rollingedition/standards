"""Rolling Edition standards: what every book must pass, in the open.

This package moves to the public `standards` repository. It holds the reference tape encoder
(title tape, edition code, history tape, cover SVG), the catalog validator, the book format
(chapters, sections and stable IDs), the examples runner and the checks that book repos call.
"""
from pathlib import Path
import os


def standards_root() -> Path:
    """The standards checkout: the folder holding data/, prompts/ and .github/workflows/."""
    env = os.environ.get("RE_STANDARDS_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def data_path(name: str) -> Path:
    return standards_root() / "data" / name
