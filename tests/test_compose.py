"""A compose stack (TL13): examples/compose.yaml's rules (every image by a digest the stack pins, nothing built, no
port beyond loopback, nothing privileged or on the host's network, no mount outside the book), the runner's compose
backend against a fake Docker, the local lab's scripts for a compose stack, and the OpenSearch sampler, the services
pilot. No Docker runs here."""
import shutil
import subprocess
from pathlib import Path

import pytest

from re_standards import bookfmt, commands, labscripts, stack

FIXTURES = Path(__file__).parent / "fixtures"
PILOT = FIXTURES / "opensearch-sampler"
DIGEST = "sha256:" + "0" * 64


def pilot_copy(tmp_path: Path) -> Path:
    root = tmp_path / "opensearch-sampler"
    shutil.copytree(PILOT, root)
    return root


def test_the_pilot_is_a_terminal_book_on_a_compose_stack_with_opensearch_pinned_and_allowed():
    book = bookfmt.load_book(PILOT)
    assert stack.lab(book.manifest) == {"kind": "terminal", "stack": "compose"}
    problems, pinned = stack.check(PILOT, book.manifest)
    assert problems == [], problems
    assert [i["ref"] for i in pinned.images] == ["opensearchproject/opensearch:2.19.1"]
    assert stack.compose_problems(PILOT, pinned) == []
    assert [c.chapter_id for c in book.chapters] == ["start-a-node", "index-and-search"]
    assert book.chapter("index-and-search").setup == ["cluster-health"]


def test_elasticsearch_would_be_refused_and_opensearch_named_instead():
    why = stack.licence_problem("Elastic-2.0", "image docker.elastic.co/elasticsearch/elasticsearch:8.17.0")
    assert why and "OpenSearch" in why


@pytest.mark.parametrize("change, said", [
    ("image: opensearchproject/opensearch:2.19.1", "named by its digest"),
    ("image: opensearchproject/opensearch:2.19.1@sha256:" + "1" * 64, "isn't one stack.toml pins"),
    ('ports:\n      - "9200:9200"', "beyond loopback"),
    ("privileged: true", "privileged"),
    ("network_mode: host", "privileged"),
    ("build: .", "builds an image"),
    ("volumes:\n      - /etc:/host-etc", "outside the book's examples folder"),
])
def test_compose_yaml_is_refused_where_it_would_run_what_isn_t_pinned_or_reach_past_loopback(tmp_path, change, said):
    root = pilot_copy(tmp_path)
    path = root / "examples" / "compose.yaml"
    text = path.read_text()
    if change.startswith("image:"):
        text = text.replace(f"image: opensearchproject/opensearch:2.19.1@{DIGEST}", change)
    elif change.startswith("ports:"):
        text = text.replace('ports:\n      - "127.0.0.1:9200:9200"', change)
    else:
        text = text.replace("    environment:", f"    {change}\n    environment:")
    path.write_text(text)
    problems = stack.compose_problems(root, stack.read_pinned(root))
    assert any(said in p for p in problems), problems


def test_a_compose_stack_without_its_file_says_so(tmp_path):
    root = pilot_copy(tmp_path)
    (root / "examples" / "compose.yaml").unlink()
    problems, _ = stack.check(root, bookfmt.load_book(root).manifest)
    assert any("compose.yaml" in p for p in problems)


class FakeDocker:
    def __init__(self, fail: str = ""):
        self.calls, self.fail = [], fail

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        rc = 1 if self.fail and self.fail in argv else 0
        return subprocess.CompletedProcess(argv, rc, "", "no such image" if rc else "")


def test_the_compose_backend_brings_a_chapter_s_services_up_from_its_workspace_and_takes_them_down(tmp_path):
    book = bookfmt.load_book(PILOT)
    docker = FakeDocker()
    backend = commands.ComposeBackend(run=docker)
    if shutil.which("docker") is None:                                       # here, with no Docker: said
        with pytest.raises(commands.CommandsError, match="Docker"):
            commands.backend_for(book)
    ws = backend.start(book, "start-a-node")
    up = docker.calls[0]
    assert up[:2] == ["docker", "compose"] and "up" in up and "--wait" in up and ["--pull", "never"] == \
        up[up.index("--pull"):up.index("--pull") + 2]
    assert up[up.index("--file") + 1] == str(ws.cwd / "compose.yaml") and (ws.cwd / "compose.yaml").is_file()
    assert not (ws.cwd / "cluster-health.sh").exists() and (ws.cwd / "data" / "products.ndjson").is_file()
    backend.stop(ws)
    assert "down" in docker.calls[-1] and "--volumes" in docker.calls[-1] and not ws.root.exists()
    with pytest.raises(commands.CommandsError, match="didn't come up"):
        commands.ComposeBackend(run=FakeDocker(fail="up")).start(book, "start-a-node")


def test_the_local_lab_runs_a_compose_stack_s_services_with_docker_compose():
    book = bookfmt.load_book(PILOT)
    scripts = labscripts.scripts(book)
    assert set(scripts) == {"lab/start.sh", "lab/chapter.sh", "lab/check.sh", "lab/stop.sh"}
    assert "docker compose" in scripts["lab/start.sh"] and "--wait" in scripts["lab/start.sh"]
    assert "down --volumes" in scripts["lab/stop.sh"]
    assert "start_services" in scripts["lab/chapter.sh"] and "step_cluster_health" in scripts["lab/chapter.sh"]
    for text in scripts.values():
        out = subprocess.run(["sh", "-n"], input=text, text=True, capture_output=True)
        assert out.returncode == 0, out.stderr
