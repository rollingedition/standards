"""Fetch a book's pinned model files into a Hugging Face cache, checking each file's SHA-256 (models.py).

Standard library only, and no imports from this package: the runtime's image runs it on the book's own Python before
anything else is installed, as

    python fetch_models.py MODELS_JSON CACHE_DIR BASE_URL

and models.py imports it for the venv backend. The files land where the Hugging Face libraries look for a pinned
commit, `{cache}/hub/models--{owner}--{name}/snapshots/{revision}/{file}`, so an example's ordinary
`from_pretrained(repo, revision=...)` finds them with HF_HUB_OFFLINE=1. No credentials are sent: the models are public.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CHUNK = 1 << 20
AGENT = "rolling-edition-runtime"


class HashMismatch(ValueError):
    """A file's bytes aren't the ones models.toml pins: never retried, and never kept."""


def snapshot(cache: Path | str, repo: str, revision: str) -> Path:
    return Path(cache) / "hub" / ("models--" + repo.replace("/", "--")) / "snapshots" / revision


def file_url(base: str, repo: str, revision: str, name: str) -> str:
    return f"{base.rstrip('/')}/{repo}/resolve/{revision}/{urllib.parse.quote(name)}"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def fetch_file(src: str, dest: Path, sha256: str, attempts: int = 3) -> int:
    """`src` into `dest`, unless `dest` already holds the pinned bytes. Returns the bytes downloaded."""
    if dest.exists() and sha256_of(dest) == sha256:
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            h, n = hashlib.sha256(), 0
            with urllib.request.urlopen(urllib.request.Request(src, headers={"User-Agent": AGENT}), timeout=60) as r, \
                    open(part, "wb") as out:
                for block in iter(lambda: r.read(CHUNK), b""):
                    h.update(block)
                    out.write(block)
                    n += len(block)
            if h.hexdigest() != sha256:
                part.unlink(missing_ok=True)
                raise HashMismatch(f"{src}: its SHA-256 is {h.hexdigest()}, but examples/models.toml pins {sha256}")
            os.replace(part, dest)
            return n
        except OSError as e:                    # network errors, HTTP errors and timeouts are retried
            last = e
            part.unlink(missing_ok=True)
            time.sleep(2 ** attempt)
    raise OSError(f"could not fetch {src} after {attempts} tries: {last}")


def fetch_all(models: list[dict], cache: Path | str, base: str) -> int:
    """Every file of every model, as models.Model.as_json gives them. Returns the bytes downloaded."""
    total = 0
    for m in models:
        snap = snapshot(cache, m["repo"], m["revision"])
        for name, f in sorted(m["files"].items()):
            total += fetch_file(file_url(base, m["repo"], m["revision"], name), snap / name, f["sha256"])
    return total


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("usage: fetch_models.py MODELS_JSON CACHE_DIR BASE_URL")
    got = fetch_all(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")), sys.argv[2], sys.argv[3])
    print(f"fetched {got:,} bytes of pinned model files")
