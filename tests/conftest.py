import os
from pathlib import Path

import pytest


@pytest.fixture
def platform_var(monkeypatch):
    """Slow tests cache pinned runtimes under the platform's var/ (or $RE_VAR_DIR), never system-wide."""
    var = Path(os.environ.get("RE_VAR_DIR", Path(__file__).resolve().parents[2] / "var"))
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(var / "envs"))
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(var / "python"))
    monkeypatch.setenv("UV_CACHE_DIR", str(var / "cache" / "uv"))
    return var
