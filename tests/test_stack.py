"""Stack pins (stack.py): book.toml's [lab], stack.in.toml and the stack.toml generated from it, licences, version
bindings, and a book with no Python example needing no Python runtime. Pinning reads a fake internet."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from re_standards import bookfmt, cli, stack

SAMPLER = Path(__file__).parent / "fixtures" / "terminal-sampler"
H = {name: hashlib.sha256(name.encode()).hexdigest() for name in
     ("k3s", "airgap", "kubectl-linux-amd64", "kubectl-linux-arm64", "kubectl-darwin-arm64", "helm", "k3d-linux-amd64",
      "k3d-linux-arm64", "k3d-darwin-arm64", "chart")}
DIGEST = "sha256:" + "a" * 64
K3S_DIGEST = "sha256:" + "b" * 64

SOURCE = '''[tools]
k3s = "v1.31.4+k3s1"
kubectl = "v1.31.4"
k3d = "v5.7.5"

[charts.strimzi-kafka-operator]
repo = "https://strimzi.io/charts/"
version = "0.45.0"
licence = "Apache-2.0"

[images."quay.io/strimzi/kafka:0.45.0-kafka-3.9.0"]
licence = "Apache-2.0"
'''


def internet(url: str, headers: dict) -> tuple[bytes, dict]:
    """What the pinned tools' release pages, a chart repository and the registries answer."""
    k3s = "https://github.com/k3s-io/k3s/releases/download/v1.31.4%2Bk3s1/"
    k3d = "https://github.com/k3d-io/k3d/releases/download/v5.7.5/"
    files = {
        k3s + "sha256sum-amd64.txt": f"{H['k3s']}  k3s\n{H['airgap']}  k3s-airgap-images-amd64.tar.zst\n",
        k3d + "checksums.txt": "".join(f"{H['k3d-' + p]}  _dist/k3d-{p}\n" for p in ("linux-amd64", "linux-arm64", "darwin-arm64")),
        "https://strimzi.io/charts/index.yaml": "entries:\n  strimzi-kafka-operator:\n  - version: 0.45.0\n"
                                                 f"    digest: {H['chart']}\n    urls: [strimzi-kafka-operator-0.45.0.tgz]\n",
        "https://quay.io/v2/auth?service=quay.io&scope=repository:strimzi/kafka:pull": '{"token": "anonymous"}',
        "https://auth.docker.io/token?service=registry.docker.io&scope=repository:rancher/k3s:pull": '{"token": "anon"}',
    }
    for p in ("linux-amd64", "linux-arm64", "darwin-arm64"):
        os_, arch = p.split("-")
        files[f"https://dl.k8s.io/release/v1.31.4/bin/{os_}/{arch}/kubectl.sha256"] = H[f"kubectl-{p}"]
    if url == "https://quay.io/v2/strimzi/kafka/manifests/0.45.0-kafka-3.9.0":
        assert headers.get("Authorization") == "Bearer anonymous"
        return b"{}", {"docker-content-digest": DIGEST}
    if url == "https://registry-1.docker.io/v2/rancher/k3s/manifests/v1.31.4-k3s1":
        return b"{}", {"docker-content-digest": K3S_DIGEST}
    if url not in files:
        raise AssertionError(f"fetched {url}, which the pins don't need")
    return files[url].encode(), {}


def k3s_book(tmp_path: Path, source: str = SOURCE) -> Path:
    root = tmp_path / "book"
    shutil.copytree(SAMPLER, root)
    toml = (root / "book.toml").read_text().replace('stack = "none"', 'stack = "k3s"')
    (root / "book.toml").write_text(toml)
    (root / stack.STACK_IN).write_text(source)
    return root


def pinned(root: Path) -> stack.Pinned:
    text = stack.pin(root, bookfmt.load_book(root).manifest, fetch=internet)
    (root / stack.STACK).write_text(text)
    return stack.parse_pinned(text)


def test_pinning_writes_every_file_by_sha256_and_every_image_by_digest(tmp_path):
    root = k3s_book(tmp_path)
    p = pinned(root)
    assert p.stack == "k3s"
    k3s = p.tools["k3s"]
    assert k3s["platforms"]["linux-amd64"] == {
        "url": "https://github.com/k3s-io/k3s/releases/download/v1.31.4%2Bk3s1/k3s", "sha256": H["k3s"]}
    assert k3s["airgap"]["sha256"] == H["airgap"] and k3s["image"] == {"ref": "docker.io/rancher/k3s:v1.31.4-k3s1",
                                                                        "digest": K3S_DIGEST}
    assert set(p.tools["kubectl"]["platforms"]) == {"linux-amd64", "linux-arm64", "darwin-arm64"}
    assert p.tools["k3d"]["platforms"]["darwin-arm64"]["sha256"] == H["k3d-darwin-arm64"]
    assert p.tools["k3d"]["licence"] == "MIT"
    assert p.charts == [{"name": "strimzi-kafka-operator", "repo": "https://strimzi.io/charts/", "version": "0.45.0",
                         "url": "https://strimzi.io/charts/strimzi-kafka-operator-0.45.0.tgz", "sha256": H["chart"],
                         "licence": "Apache-2.0"}]
    assert p.images == [{"ref": "quay.io/strimzi/kafka:0.45.0-kafka-3.9.0", "digest": DIGEST, "licence": "Apache-2.0"}]
    problems, _ = stack.check(root, bookfmt.load_book(root).manifest)
    assert problems == []
    assert stack.to_toml(stack.parse_pinned((root / stack.STACK).read_text())) == (root / stack.STACK).read_text()


def test_the_pins_bind_versions_and_a_python_book_binds_as_before(tmp_path):
    root = k3s_book(tmp_path)
    pinned(root)
    book = bookfmt.load_book(root)
    assert book.pins["k3s"] == "v1.31.4+k3s1" and book.pins["strimzi-kafka-operator"] == "0.45.0"
    assert book.bind("k3s {{version:k3s}} with kubectl {{version:kubectl}}") == "k3s v1.31.4+k3s1 with kubectl v1.31.4"
    assert "examples/stack.toml" in book.binding_value("version", "trino")[1]
    tiny = bookfmt.load_book(Path(__file__).parent / "fixtures" / "primer-chapter")
    assert tiny.binding_value("version", "trino")[1] == "{{version:trino}}: trino isn't pinned in examples/requirements.txt"


@pytest.mark.parametrize("edit, problem", [
    (lambda s: s.replace('k3d = "v5.7.5"\n', ""), "a k3s stack needs k3d"),
    (lambda s: s + '[images."docker.io/minio/minio:RELEASE.2025-01-01T00-00-00Z"]\nlicence = "AGPL-3.0-only"\n',
     "use SeaweedFS instead"),
    (lambda s: s.replace('licence = "Apache-2.0"\n\n[images', 'licence = "BUSL-1.1"\n\n[images'),
     "chart strimzi-kafka-operator 0.45.0: BUSL-1.1 isn't open source enough"),
    (lambda s: s + '[images."docker.io/library/postgres:17.2"]\nlicence = "LicenseRef-Custom"\n',
     "isn't on the allowed list"),
    (lambda s: s + '[images."docker.io/library/postgres:17.2"]\n', "give its licence"),
])
def test_what_a_stack_gets_wrong(tmp_path, edit, problem):
    root = k3s_book(tmp_path)
    pinned(root)
    (root / stack.STACK_IN).write_text(edit(SOURCE))
    with_pins = []
    try:
        pinned(root)
    except AssertionError:
        pass                                       # the fake internet has no such image: check the source alone
    except stack.StackError:
        pass
    else:
        with_pins = stack.check(root, bookfmt.load_book(root).manifest)[0]
    (root / stack.STACK).unlink()
    without = stack.check(root, bookfmt.load_book(root).manifest)[0]
    assert any(problem in p for p in with_pins + without), (with_pins, without)


def test_stack_toml_out_of_step_with_its_source_or_edited_by_hand(tmp_path):
    root = k3s_book(tmp_path)
    pinned(root)
    (root / stack.STACK_IN).write_text(SOURCE.replace("v1.31.4\"", "v1.31.5\"", 1))
    problems, _ = stack.check(root, bookfmt.load_book(root).manifest)
    assert any("out of date with examples/stack.in.toml" in p for p in problems)
    (root / stack.STACK_IN).write_text(SOURCE)
    text = (root / stack.STACK).read_text().replace(f'digest = "{DIGEST}"', 'digest = ""')
    (root / stack.STACK).write_text(text)
    problems, _ = stack.check(root, bookfmt.load_book(root).manifest)
    assert any("isn't pinned by digest" in p for p in problems)


def test_licence_expressions():
    assert stack.licence_problem("Apache-2.0", "x") is None
    assert stack.licence_problem("Apache-2.0 AND MIT", "x") is None
    assert stack.licence_problem("SSPL-1.0 OR Apache-2.0", "x") is None          # an OR needs one allowed
    assert "isn't open source enough" in stack.licence_problem("Apache-2.0 AND Elastic-2.0", "elasticsearch")
    assert "use OpenSearch instead" in stack.licence_problem("Elastic-2.0", "image elasticsearch:8")
    assert "use Valkey instead" in stack.licence_problem("RSALv2", "image redis:8.0")
    assert "isn't open source enough" in stack.licence_problem("LicenseRef-Confluent-Community-1.0", "schema-registry")
    assert "isn't open source enough" in stack.licence_problem("Apache-2.0 WITH Commons-Clause", "x")


@pytest.mark.parametrize("lab, problem", [
    ({"kind": "shell"}, "[lab] kind is one of notebook, terminal"),
    ({"kind": "terminal", "stack": "kind"}, "[lab] stack is one of k3s, compose, none"),
    ({"kind": "terminal", "size": "big"}, "[lab] takes kind and stack, not size"),
])
def test_book_toml_lab(lab, problem):
    assert any(problem in p for p in stack.manifest_problems({"slug": "b", "lab": lab}))
    assert stack.manifest_problems({"slug": "b"}) == []
    assert stack.lab({}) == {"kind": "notebook", "stack": "none"}


def test_re_check_stack_and_manifest(tmp_path, capsys, monkeypatch):
    assert cli.main(["stack", "--book", str(SAMPLER)]) == 0
    assert "no stack to pin" in capsys.readouterr().out
    root = k3s_book(tmp_path)
    assert cli.main(["stack", "--book", str(root)]) == 1
    assert "examples/stack.toml is missing" in capsys.readouterr().err
    monkeypatch.setattr(stack, "http_fetch", internet)
    assert cli.main(["stack", "--book", str(root), "--pin"]) == 0
    out = capsys.readouterr().out
    assert "pinned 3 tools, 1 chart and 1 image" in out and (root / stack.STACK).exists()
    (root / "book.toml").write_text((root / "book.toml").read_text().replace('stack = "k3s"', 'stack = "swarm"'))
    assert cli.main(["manifest", "--book", str(root)]) == 1
    assert "[lab] stack is one of" in capsys.readouterr().err


def test_pin_refuses_to_write_a_licence_the_lab_cant_ship(tmp_path, capsys, monkeypatch):
    root = k3s_book(tmp_path, SOURCE.replace('licence = "Apache-2.0"\n\n[images', 'licence = "SSPL-1.0"\n\n[images'))
    monkeypatch.setattr(stack, "http_fetch", internet)
    assert cli.main(["stack", "--book", str(root), "--pin"]) == 1
    assert not (root / stack.STACK).exists()
    assert "SSPL-1.0 isn't open source enough" in capsys.readouterr().err


def test_a_book_with_no_python_example_needs_no_python_runtime(tmp_path, capsys):
    report = tmp_path / "report.json"
    assert cli.main(["examples", "--book", str(SAMPLER), "--backend", "host", "--report", str(report)]) == 0
    assert "no Python examples, so no Python runtime to build" in capsys.readouterr().out
    data = json.loads(report.read_text())
    assert (data["outcome"], data["passing"], data["total"], data["examples"]) == ("passed", 0, 0, [])
