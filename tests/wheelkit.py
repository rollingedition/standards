"""A package index on disk, for tests: tiny wheels that hold only their metadata, which a resolver reads like PyPI's.

    index = wheel_index(tmp_path / "index", {("lib-a", "1.0"): ["lib-b<2"], ("lib-b", "1.0"): [], ("lib-b", "2.0"): []})
    env = offline_env(index)          # uv reads only that folder, through a uv.toml beside it
"""
import os
import re
import zipfile
from pathlib import Path


def dist_name(name: str) -> str:
    return re.sub(r"[-_.]+", "_", name).lower()


def stub_wheel(folder: Path, name: str, version: str, requires: list[str] | None = None,
               requires_python: str | None = None) -> Path:
    """A wheel with a dist-info and nothing to import: enough for a resolver, never meant to be installed."""
    folder.mkdir(parents=True, exist_ok=True)
    info = f"{dist_name(name)}-{version}.dist-info"
    metadata = [f"Metadata-Version: 2.1", f"Name: {name}", f"Version: {version}"]
    metadata += [f"Requires-Python: {requires_python}"] if requires_python else []
    metadata += [f"Requires-Dist: {r}" for r in requires or []]
    files = {f"{info}/METADATA": "\n".join(metadata) + "\n",
             f"{info}/WHEEL": "Wheel-Version: 1.0\nGenerator: wheelkit\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    files[f"{info}/RECORD"] = "".join(f"{path},,\n" for path in files) + f"{info}/RECORD,,\n"
    path = folder / f"{dist_name(name)}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as z:
        for arc, text in files.items():
            z.writestr(arc, text)
    return path


def wheel_index(folder: Path, packages: dict[tuple[str, str], list[str]]) -> Path:
    for (name, version), requires in packages.items():
        stub_wheel(folder, name, version, requires)
    return folder


def offline_env(index: Path, cache: Path | None = None) -> dict:
    """The environment for a uv that reads only `index`: `uv pip compile` takes no-index and find-links from a config
    file (UV_CONFIG_FILE), not from UV_NO_INDEX."""
    config = index.parent / f"{index.name}-uv.toml"
    config.write_text(f'[pip]\nno-index = true\nfind-links = ["{index.as_posix()}"]\n')
    env = dict(os.environ, UV_CONFIG_FILE=str(config), UV_PYTHON_DOWNLOADS="never")
    if cache is not None:
        env["UV_CACHE_DIR"] = str(cache)
    return env
