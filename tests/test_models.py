"""Pinned model files (models.py, fetch_models.py) and how the runtimes carry them (examples.py). A local HTTP server
stands in for Hugging Face, and a stand-in for subprocess.run records the container engine's commands."""
import hashlib
import json
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from re_standards import cli, examples, models

COMMIT = "12fd25f77366fa6b3b4b768ec3050bf629380bac"
REPO = "owner/tiny-model"
WEIGHTS = b"weights" * 1000
CONFIG = b'{"layers": 2}'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def entry(files=None, licence="apache-2.0", revision=COMMIT, repo=REPO) -> str:
    files = files or {"config.json": CONFIG, "model.safetensors": WEIGHTS}
    lines = [f'"{n}" = {{ sha256 = "{sha(d)}", size = {len(d)} }}' for n, d in files.items()]
    return f'[[model]]\nrepo = "{repo}"\nrevision = "{revision}"\nlicence = "{licence}"\n\n[model.files]\n' + "\n".join(lines) + "\n"


@pytest.fixture
def hub(tmp_path):
    """A stand-in for Hugging Face: files at /{repo}/resolve/{commit}/{name}, and the model's API record."""
    root = tmp_path / "hub"
    folder = root / REPO / "resolve" / COMMIT
    folder.mkdir(parents=True)
    (folder / "config.json").write_bytes(CONFIG)
    (folder / "model.safetensors").write_bytes(WEIGHTS)
    (folder / "trainer_state.json").write_bytes(b"{}")
    info = {"sha": COMMIT, "cardData": {"license": "apache-2.0"},
            "siblings": [{"rfilename": "config.json"}, {"rfilename": "trainer_state.json"}, {"rfilename": "onnx/model.onnx"},
                         {"rfilename": "model.safetensors", "lfs": {"sha256": sha(WEIGHTS), "size": len(WEIGHTS)}}]}
    api = root / "api" / "models" / REPO / "revision"
    api.mkdir(parents=True)
    (api / "main").write_text(json.dumps(info))           # the query string (?blobs=true) is ignored by the server

    class Quiet(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", root
    server.shutdown()


def test_a_pinned_model_parses_and_its_digest_ignores_comments_and_layout():
    (m,) = models.parse(entry())
    assert (m.repo, m.revision, m.licence) == (REPO, COMMIT, "apache-2.0")
    assert [f.name for f in m.files] == ["config.json", "model.safetensors"]
    assert models.total_bytes([m]) == len(CONFIG) + len(WEIGHTS)
    assert models.digest(models.parse("# a comment\n" + entry())) == models.digest([m])
    assert models.parse(models.to_toml([m])) == [m]                        # what it writes reads back


@pytest.mark.parametrize("text, says", [
    (entry(revision="main"), "full 40-character commit"),
    (entry(licence="llama3.2"), "licence 'llama3.2' isn't one a book can ship"),
    (entry(licence="cc-by-nc-4.0"), "isn't one a book can ship"),
    (entry() + entry(), "listed twice"),
    (entry(files={"../escape": CONFIG}), "isn't a file name"),
    (entry(repo="no-owner"), "owner/name"),
    ("[model]\nrepo = 1\n", "each model is a [[model]] table"),
    ("[other]\n", "only [[model]] tables"),
    ("", "lists no model"),
    (entry().replace(", size = 13 }", " }"), "exactly sha256 and size"),
])
def test_anything_unpinned_or_unshippable_is_refused(text, says):
    with pytest.raises(models.ModelsError, match=None) as e:
        models.parse(text)
    assert says in str(e.value)


def test_the_size_cap_is_checked_from_the_pinned_sizes():
    cfg = dict(models.settings(), max_total_mb=0)
    with pytest.raises(models.ModelsError, match="over the 0 MB"):
        models.parse(entry(), cfg)


def test_files_are_fetched_into_the_pinned_commit_once_and_a_wrong_hash_is_never_kept(hub, tmp_path):
    base, root = hub
    cache = tmp_path / "cache"
    pinned = models.parse(entry())
    assert models.fetch(pinned, cache, base) == len(CONFIG) + len(WEIGHTS)
    snap = cache / "hub" / "models--owner--tiny-model" / "snapshots" / COMMIT
    assert (snap / "model.safetensors").read_bytes() == WEIGHTS and not list(snap.glob("*.part"))
    assert models.fetch(pinned, cache, base) == 0                          # already there: nothing downloaded
    (root / REPO / "resolve" / COMMIT / "config.json").write_bytes(b"tampered")
    (snap / "config.json").unlink()
    with pytest.raises(ValueError, match="examples/models.toml pins"):
        models.fetch(pinned, cache, base)
    assert not (snap / "config.json").exists() and not list(snap.glob("*.part"))
    assert models.env(cache) == {"HF_HOME": str(cache), "HF_HUB_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1"}


def test_pinning_resolves_the_commit_licence_and_hashes_and_skips_what_no_model_loads(hub):
    base, _ = hub
    m = models.pin(REPO, base=base)
    assert m.revision == COMMIT and m.licence == "apache-2.0"
    assert {f.name: f.sha256 for f in m.files} == {"config.json": sha(CONFIG), "model.safetensors": sha(WEIGHTS)}
    assert [f.name for f in models.pin(REPO, base=base, files=["config.json"]).files] == ["config.json"]
    with pytest.raises(models.ModelsError, match="has no missing.bin"):
        models.pin(REPO, base=base, files=["missing.bin"])


def test_a_licence_outside_the_list_stops_the_pin(hub):
    base, root = hub
    api = root / "api" / "models" / REPO / "revision" / "main"
    info = json.loads(api.read_text())
    info["cardData"] = {"license": "other"}
    api.write_text(json.dumps(info))
    with pytest.raises(models.ModelsError, match="licence is other, which a book can't ship"):
        models.pin(REPO, base=base)


def test_the_command_writes_the_entry_and_reports_the_models(hub, tmp_path, capsys, monkeypatch):
    base, _ = hub
    monkeypatch.setattr(models, "settings", lambda: dict(tomllib_settings(), base_url=base))
    (tmp_path / "examples").mkdir()
    assert cli.main(["models", "--book", str(tmp_path)]) == 0
    assert "the examples load no model" in capsys.readouterr().out
    assert cli.main(["models", "--book", str(tmp_path), "--pin", REPO]) == 0
    text = (tmp_path / "examples" / "models.toml").read_text()
    assert text.startswith(models.HEADER) and COMMIT in text and "trainer_state" not in text
    assert "1 model(s)" in capsys.readouterr().out


def tomllib_settings():
    import tomllib
    from re_standards import data_path
    return tomllib.loads(data_path("examples.toml").read_text())["models"]


# ---------------------------------------------------------------- the runtimes


def fake_uv(cmd, **kwargs):
    """Answers every build step, and makes the venv's folder as `uv venv` would."""
    if "venv" in cmd:
        Path(cmd[-1]).mkdir(parents=True, exist_ok=True)
    return subprocess.CompletedProcess(cmd, 0, "", "")


def book_root(tmp_path, models_text=None, requirements="transformers==5.22.2\n"):
    ex = tmp_path / "examples"
    ex.mkdir(parents=True, exist_ok=True)
    (ex / ".python-version").write_text("3.12.15\n")
    (ex / "requirements.txt").write_text(requirements)
    if models_text is not None:
        (ex / "models.toml").write_text(models_text)
    return tmp_path


def test_a_runtime_without_models_keeps_its_key_and_image_and_one_with_models_gets_its_own(tmp_path):
    plain = examples.read_runtime(book_root(tmp_path / "a"))
    assert plain.key == hashlib.sha256(b"3.12.15\ntransformers==5.22.2\n").hexdigest()[:16]
    assert "models_sha256" not in examples.HostBackend().describe(plain)
    with_models = examples.read_runtime(book_root(tmp_path / "b", entry()))
    assert with_models.key != plain.key and with_models.model_list()[0].repo == REPO
    assert examples.HostBackend().describe(with_models)["models_sha256"] == models.digest(with_models.model_list())
    backend = examples.ContainerBackend(registry="")
    assert backend.tag(plain).endswith(f"-{plain.key}-{examples.dockerfile_key()}")
    assert backend.tag(with_models).endswith(f"-{with_models.key}-{examples.models_dockerfile_key()}")
    with pytest.raises(examples.ExamplesError, match="full 40-character commit"):
        examples.read_runtime(book_root(tmp_path / "c", entry(revision="main")))


def test_only_a_listed_index_may_join_pypi_and_uv_then_reads_every_index(tmp_path, monkeypatch):
    ok = "--extra-index-url https://download.pytorch.org/whl/cpu\ntorch==2.14.1+cpu\n"
    rt = examples.read_runtime(book_root(tmp_path / "a", requirements=ok))
    assert rt.indexes() == ["https://download.pytorch.org/whl/cpu"] and rt.pins() == {"torch": "2.14.1+cpu"}
    with pytest.raises(examples.ExamplesError, match="isn't an index a book may use"):
        examples.read_runtime(book_root(tmp_path / "b", requirements="--extra-index-url https://example.invalid/simple\nx==1\n"))
    calls = []
    monkeypatch.setattr(examples.subprocess, "run", lambda cmd, **k: calls.append(cmd) or fake_uv(cmd))
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(tmp_path / "envs"))
    examples.VenvBackend(block_network=False).prepare(rt)
    assert calls[-1][-2:] == examples.BEST_MATCH


def test_the_venv_fetches_the_models_beside_itself_and_its_examples_read_them_offline(tmp_path, monkeypatch):
    rt = examples.read_runtime(book_root(tmp_path, entry()))
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(tmp_path / "envs"))
    monkeypatch.setattr(examples.subprocess, "run", fake_uv)
    fetched = []
    monkeypatch.setattr(examples.model_files, "fetch", lambda ms, cache: fetched.append((ms, cache)) or 0)
    backend = examples.VenvBackend(block_network=False)
    backend.prepare(rt)
    assert fetched == [(rt.model_list(), backend.env_dir(rt) / "hf")] and backend.ready(rt)
    _, env = backend.command(rt, tmp_path, "load.py")
    assert env["HF_HOME"] == str(backend.env_dir(rt) / "hf") and env["HF_HUB_OFFLINE"] == "1"
    _, plain_env = backend.command(examples.Runtime("3.12.15", ""), tmp_path, "load.py")
    assert "HF_HOME" not in plain_env


def test_the_container_puts_the_models_in_a_layer_on_the_pins_image(tmp_path, monkeypatch):
    rt = examples.read_runtime(book_root(tmp_path, entry()))
    calls, contexts = [], []

    def run(cmd, **k):
        calls.append(cmd)
        if cmd[1] == "build" and "models.Dockerfile" in " ".join(cmd):
            contexts.append(sorted(p.name for p in Path(cmd[-1]).iterdir()))
            assert json.loads((Path(cmd[-1]) / "models.json").read_text())[0]["revision"] == COMMIT
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(examples.subprocess, "run", run)
    backend = examples.ContainerBackend(registry="")
    backend.prepare(rt)
    base, layer = calls
    assert base[base.index("-t") + 1] == backend.base_image(rt)
    assert layer[layer.index("-t") + 1] == backend.image(rt) and f"BASE={backend.base_image(rt)}" in layer
    assert contexts == [["fetch_models.py", "models.json"]]
    cmd, _ = backend.command(rt, tmp_path, "load.py")
    assert "HF_HUB_OFFLINE=1" in cmd and f"HF_HOME={models.settings()['image_cache']}" in cmd


def test_the_readme_names_the_models_and_how_to_install_beside_pytorchs_index(tmp_path):
    from bookkit import make_book
    from re_standards import bookfmt, readme
    root = make_book(tmp_path / "book")
    (root / "examples" / ".python-version").write_text("3.12.15\n")
    (root / "examples" / "requirements.txt").write_text("--extra-index-url https://download.pytorch.org/whl/cpu\ntorch==2.14.1+cpu\n")
    (root / "examples" / "models.toml").write_text(entry())
    text = readme.readme(bookfmt.load_book(root))
    assert "uv pip install -r examples/requirements.txt --index-strategy unsafe-best-match" in text
    assert f"The examples load an open model, pinned to an exact commit" in text and f"/{REPO}/tree/{COMMIT})" in text
    (root / "examples" / "models.toml").unlink()
    (root / "examples" / "requirements.txt").write_text("pandas==2.2.2\n")
    plain = readme.readme(bookfmt.load_book(root))
    assert "open model" not in plain and "index-strategy" not in plain
