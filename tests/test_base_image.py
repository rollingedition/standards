"""The runtime image's base, pinned by digest with its Debian packages' versions (base_image.py), the image's tag that
carries it, and the venv backend's fresh runtimes."""
import hashlib
import json
import lzma
import subprocess
from pathlib import Path

import pytest

from re_standards import base_image, cli, examples

INDEX = json.dumps({"manifests": [{"digest": "sha256:" + "a" * 64, "platform": {"os": "linux", "architecture": "amd64"}},
                                  {"digest": "sha256:" + "b" * 64, "platform": {"os": "linux", "architecture": "arm64"}}]})
PACKAGES = "Package: libgomp1\nVersion: 14.2.0-19\n\nPackage: libatomic1\nVersion: 14.2.0-19\n\nPackage: other\nVersion: 1\n"
UPDATES = "Package: libgomp1\nVersion: 14.2.0-19+deb13u1\n"


def fake_get(digests: dict, packages: dict):
    """Docker Hub's token, index, manifest and config, and Debian's package indexes, from what the test gives."""
    def get(url, headers=None):
        if url.startswith("https://auth.docker.io/"):
            return json.dumps({"token": "t"}).encode(), {}
        if "/manifests/sha256:" in url:
            return json.dumps({"config": {"digest": "sha256:" + "c" * 64}}).encode(), {}
        if "/manifests/" in url:
            tag = url.rsplit("/", 1)[1]
            return INDEX.encode(), {"docker-content-digest": digests[tag]}
        if "/blobs/" in url:
            return json.dumps({"history": [{"created_by": "# debian.sh --arch 'amd64' out/ 'trixie' '@1792531975'"}]}).encode(), {}
        for suite, text in packages.items():
            if f"/{suite}/main/" in url:
                return lzma.compress(text.encode()), {}
        raise OSError(f"404 {url}")
    return get


def test_every_pinned_python_has_a_digest_and_every_package_a_version():
    data = base_image.load()
    assert base_image.problems(data) == []
    assert {"3.12.15", "3.13.16"} <= set(data["python"])                  # every live book's Python
    for python in data["python"]:
        e = base_image.entry(python, data)
        assert e["image"] == f"python:{python}-slim@{data['python'][python]['digest']}"
        assert [p.split("=")[0] for p in e["packages"]] == data["packages"]
    with pytest.raises(base_image.BaseImageError, match="--python 3.11.2"):
        base_image.entry("3.11.2", data)
    text = base_image.path().read_text(encoding="utf-8")
    assert base_image.to_toml(data, base_image.header(text)) == text       # the refresh writes it back as it is


def test_a_new_base_changes_the_image_tag(monkeypatch):
    rt = examples.Runtime("3.12.15", "six==1.16.0\n")
    backend = examples.ContainerBackend(registry="")
    before = backend.tag(rt)
    data = base_image.load()
    data["python"]["3.12.15"]["digest"] = "sha256:" + "d" * 64
    monkeypatch.setattr(base_image, "load", lambda source=None: data)
    assert backend.tag(rt) != before and backend.tag(rt).rsplit("-", 1)[0] == before.rsplit("-", 1)[0]
    assert backend.describe(rt)["base"] == "python:3.12.15-slim@sha256:" + "d" * 64


def test_the_refresh_reads_docker_hub_and_debian_and_says_what_changed(tmp_path):
    source = tmp_path / "runtime-base.toml"
    source.write_text(base_image.path().read_text(encoding="utf-8"))
    digests = {"3.12.15-slim": "sha256:" + "1" * 64, "3.13.16-slim": base_image.load()["python"]["3.13.16"]["digest"],
               "3.13.17-slim": "sha256:" + "2" * 64}
    get = fake_get(digests, {"debian/dists/trixie": PACKAGES, "debian/dists/trixie-updates": UPDATES})
    new, changed = base_image.refresh(add=["3.13.17"], source=source, get=get)
    assert new["python"]["3.12.15"] == {"digest": "sha256:" + "1" * 64, "debian": "trixie"}
    assert new["python"]["3.13.17"]["debian"] == "trixie"
    assert new["debian"]["trixie"] == {"libgomp1": "14.2.0-19+deb13u1", "libatomic1": "14.2.0-19"}   # the newest
    assert any(c.startswith("Python 3.12.15:") for c in changed) and any(c.startswith("Python 3.13.17:") for c in changed)
    assert not any(c.startswith("Python 3.13.16") for c in changed)
    assert any(c.startswith("libgomp1 on Debian trixie") for c in changed)
    with pytest.raises(base_image.BaseImageError, match="no libatomic1"):
        base_image.refresh(source=source, get=fake_get(digests, {"debian/dists/trixie": "Package: libgomp1\nVersion: 1\n"}))


def test_debian_versions_compare_as_dpkg_compares_them():
    order = ["1.0~rc1", "1.0", "1.0-1", "1.0-1+deb13u1", "1.0a", "1.2.9", "1.2.10", "1:0.1"]
    for a, b in zip(order, order[1:]):
        assert base_image.compare_versions(a, b) == -1 and base_image.compare_versions(b, a) == 1, (a, b)
    assert base_image.compare_versions("14.2.0-19", "14.2.0-19") == 0


def test_the_command_reports_the_pins(capsys):
    assert cli.main(["base-image"]) == 0
    assert "pinned by digest" in capsys.readouterr().out
    assert cli.main(["base-image", "--python", "3.13.17"]) == 1                  # --python goes with --refresh


def fake_uv(cmd, **kwargs):
    if "venv" in cmd:
        Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
        (Path(cmd[-1]) / "bin").mkdir(exist_ok=True)
    return subprocess.CompletedProcess(cmd, 0, "", "")


def test_a_fresh_runtime_is_built_in_a_new_folder_and_removed_after(tmp_path, monkeypatch):
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(tmp_path / "envs"))
    monkeypatch.setattr(examples.subprocess, "run", fake_uv)
    rt = examples.Runtime("3.12.15", "six==1.16.0\n")
    kept = examples.VenvBackend(block_network=False)
    kept.prepare(rt)
    assert kept.ready(rt) and kept.env_dir(rt).parent == tmp_path / "envs"
    fresh = examples.backend_named("venv", block_network=False, fresh=True)
    assert not fresh.ready(rt) and fresh.env_dir(rt) != kept.env_dir(rt)
    fresh.prepare(rt)
    assert fresh.ready(rt) and fresh.describe(rt)["fresh"] is True and "fresh" not in kept.describe(rt)
    folder = fresh.fresh
    fresh.cleanup()
    assert not folder.exists() and kept.ready(rt)
    with pytest.raises(ValueError, match="only the venv backend"):
        examples.backend_named("container", fresh=True)


def test_a_fresh_runtime_with_models_copies_the_kept_ones_files_and_checks_them(tmp_path, monkeypatch):
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(tmp_path / "envs"))
    monkeypatch.setattr(examples.subprocess, "run", fake_uv)
    rt = examples.Runtime("3.12.15", "six==1.16.0\n", models="x")
    monkeypatch.setattr(examples.Runtime, "model_list", lambda self: [])
    fetched = []
    monkeypatch.setattr(examples.model_files, "fetch", lambda models, cache: fetched.append(Path(cache)) or 0)
    monkeypatch.setattr(examples.model_files, "digest", lambda models: hashlib.sha256(b"").hexdigest())
    kept = examples.VenvBackend(block_network=False)
    (kept.models_dir(rt) / "hub").mkdir(parents=True)
    (kept.models_dir(rt) / "hub" / "weights").write_text("w")
    fresh = examples.VenvBackend(block_network=False, fresh=True)
    fresh.prepare(rt)
    assert (fresh.models_dir(rt) / "hub" / "weights").read_text() == "w" and fetched == [fresh.models_dir(rt)]
    fresh.cleanup()
