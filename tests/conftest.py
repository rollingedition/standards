import fcntl
import os
from pathlib import Path

import pytest


@pytest.fixture
def platform_var(monkeypatch):
    """Slow tests cache pinned runtimes under the platform's var/ (or $RE_VAR_DIR), never system-wide. pytest-xdist's
    workers share it, so a test holds its lock while it runs: two never build the same runtime at once, and the second
    finds it built."""
    var = Path(os.environ.get("RE_VAR_DIR", Path(__file__).resolve().parents[2] / "var"))
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(var / "envs"))
    monkeypatch.setenv("UV_PYTHON_INSTALL_DIR", str(var / "python"))
    monkeypatch.setenv("UV_CACHE_DIR", str(var / "cache" / "uv"))
    var.mkdir(parents=True, exist_ok=True)
    with open(var / "tests.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)              # released when the file closes, after the test
        yield var


@pytest.fixture(autouse=True)
def no_terminal_width(monkeypatch):
    """uv wraps its messages at $COLUMNS, and resolve.check passes it os.environ. pytest loads readline, which sets COLUMNS
    and LINES for the processes pytest starts: pytest-xdist's workers find them in os.environ, where a serial run never
    has them, so a worker's uv wrapped the resolver's sentences and the conflict in them wasn't read."""
    monkeypatch.delenv("COLUMNS", raising=False)
    monkeypatch.delenv("LINES", raising=False)


@pytest.fixture(autouse=True)
def no_step_summary(monkeypatch):
    """A check writes what it found to $GITHUB_STEP_SUMMARY, the page of the GitHub Actions run it's in. These tests run
    the checks on books made to fail them, so in CI their failures filled the run's own summary page, where they read as
    real ones (the founder saw them on Nov 5, 2026). A test that checks the summary sets its own file."""
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
