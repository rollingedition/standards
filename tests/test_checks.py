import json
import subprocess

import pytest

from re_standards import bookfmt, checks, cli, examples, sections
from bookkit import CHAPTER, make_book


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                   check=True, capture_output=True)


# ---------------------------------------------------------------- section IDs

def test_renaming_a_heading_keeps_the_check_green(tmp_path):
    base = bookfmt.load_book(make_book(tmp_path / "base"))
    head = bookfmt.load_book(make_book(tmp_path / "head", chapter=CHAPTER.replace("Load the data {#", "Read the data {#")))
    assert checks.check_section_ids(head, base) == []


def test_changing_an_id_without_a_redirect_fails(tmp_path):
    base = bookfmt.load_book(make_book(tmp_path / "base"))
    head = bookfmt.load_book(make_book(tmp_path / "head", chapter=CHAPTER.replace("{#load-data}", "{#read-data}")))
    problems = checks.check_section_ids(head, base)
    assert len(problems) == 1 and "section ID 'load-data' was removed or changed" in problems[0]
    fixed = bookfmt.load_book(make_book(tmp_path / "fixed", chapter=CHAPTER.replace("{#load-data}", "{#read-data}"),
                                        redirects="load-data: read-data\n"))
    assert checks.check_section_ids(fixed, base) == []


def test_ids_from_the_previous_edition_need_redirects_too(tmp_path):
    prev = sections.build_manifest(bookfmt.load_book(make_book(tmp_path / "prev")), "2026.10.1", "main", None)
    head = bookfmt.load_book(make_book(tmp_path / "head", chapter=CHAPTER.replace("{#summarize}", "{#wrap-up}")))
    problems = checks.check_section_ids(head, None, prev)
    assert any("'summarize' from Edition 2026.10.1" in p for p in problems)


def test_removing_a_redirect_fails(tmp_path):
    base = bookfmt.load_book(make_book(tmp_path / "base", redirects="old-id: load-data\n"))
    head = bookfmt.load_book(make_book(tmp_path / "head", redirects="{}\n"))
    assert any("retired IDs stay retired" in p for p in checks.check_section_ids(head, base))


def test_section_ids_cli_compares_against_the_base_commit(tmp_path, capsys):
    repo = make_book(tmp_path / "repo")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    chapter = repo / "chapters" / "01-first-steps.md"
    chapter.write_text(CHAPTER.replace("{#a-detail}", "{#detail}"))
    assert cli.main(["section-ids", "--book", str(repo), "--base-ref", "HEAD"]) == 1
    assert "'a-detail' was removed or changed" in capsys.readouterr().err
    chapter.write_text(CHAPTER.replace("A detail {#", "One detail {#"))
    assert cli.main(["section-ids", "--book", str(repo), "--base-ref", "HEAD", "--previous", str(tmp_path / "none.json")]) == 0
    assert "none lost since the base branch" in capsys.readouterr().out


# ---------------------------------------------------------------- kind label

def test_kind_label():
    assert checks.check_kind_label(["kind:deps", "tier:quick"]) == []
    assert "needs at least one kind label" in checks.check_kind_label(["tier:quick", "breaking"])[0]
    assert any("unknown label 'kind:typo'" in p for p in checks.check_kind_label(["kind:typo", "kind:prose"]))


def test_kind_label_reads_the_github_event(tmp_path):
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"labels": [{"name": "kind:prose"}]}}))
    assert cli.main(["kind-label", "--event", str(event)]) == 0
    event.write_text(json.dumps({"pull_request": {"labels": []}}))
    assert cli.main(["kind-label", "--event", str(event)]) == 1


# ---------------------------------------------------------------- examples

def pinned(root, python="3.12.15", requirements=""):
    (root / "examples" / ".python-version").write_text(python + "\n")
    (root / "examples" / "requirements.txt").write_text(requirements)
    return root


def test_examples_pass_and_fail_on_output(tmp_path, capsys):
    root = pinned(make_book(tmp_path))
    assert cli.main(["examples", "--book", str(root), "--backend", "host"]) == 0
    assert "1 of 1 examples pass" in capsys.readouterr().out
    (root / "examples" / "hello.out").write_text("goodbye\n")
    assert cli.main(["examples", "--book", str(root), "--backend", "host"]) == 1
    err = capsys.readouterr().err
    assert "hello fails on Python" in err and "-goodbye" in err and "+hello" in err


def test_an_example_that_raises_fails_with_its_traceback(tmp_path, capsys):
    root = pinned(make_book(tmp_path, examples={"hello": ("raise ValueError('boom')\n", "\n")}))
    assert cli.main(["examples", "--book", str(root), "--backend", "host"]) == 1
    assert "ValueError: boom" in capsys.readouterr().err


def test_record_writes_expected_output_and_reports(tmp_path):
    root = pinned(make_book(tmp_path, examples={"hello": ('print("hi")   \nprint()\n', None)}))
    assert cli.main(["examples", "--book", str(root), "--backend", "host"]) == 1   # no expected output yet
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--record"]) == 0
    assert (root / "examples" / "hello.out").read_text() == "hi\n"
    report = tmp_path / "report.json"
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--report", str(report)]) == 0
    data = json.loads(report.read_text())
    assert data["passing"] == data["total"] == 1 and data["examples"][0]["versions"]["python"]


def test_examples_run_in_a_scratch_copy_with_a_clean_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_TOKEN", "do-not-leak")
    code = "import os\nprint(os.getcwd() != os.environ['HOME'] or 'home is the scratch dir')\nprint('SECRET_TOKEN' in os.environ)\nopen('scribble.txt', 'w').write('x')\n"
    root = pinned(make_book(tmp_path, examples={"hello": (code, "home is the scratch dir\nFalse\n")}))
    book = bookfmt.load_book(root)
    results, runtime = examples.run_examples(book, examples.HostBackend())
    assert results[0].passing, results[0].diff or results[0].stderr_tail
    assert not (root / "examples" / "scribble.txt").exists()


def test_unpinned_runtimes_are_rejected(tmp_path):
    root = make_book(tmp_path)
    with pytest.raises(examples.ExamplesError, match=".python-version is missing"):
        examples.read_runtime(root)
    pinned(root, python="3.12")
    with pytest.raises(examples.ExamplesError, match="exact version"):
        examples.read_runtime(root)
    pinned(root, requirements="pandas>=2\n")
    with pytest.raises(examples.ExamplesError, match="not pinned"):
        examples.read_runtime(root)
    pinned(root, requirements="# libraries\npandas==2.2.2  # the one we teach\nnumpy==1.26.4\n")
    assert examples.read_runtime(root).pins() == {"pandas": "2.2.2", "numpy": "1.26.4"}


def test_container_backend_builds_from_the_same_pins_and_runs_offline(tmp_path):
    rt = examples.Runtime("3.12.15", "pandas==2.2.2\n")
    backend = examples.ContainerBackend()
    build = backend.build_command(rt, tmp_path)
    assert "PYTHON_VERSION=3.12.15" in build and build[-1] == str(tmp_path)
    run, _ = backend.command(rt, tmp_path, "load-orders.py")
    assert run[:5] == ["docker", "run", "--rm", "--network", "none"] and backend.image(rt) in run
    assert examples.DOCKERFILE.exists()


def test_describe_versions():
    assert examples.describe_versions({"python": "3.12.15", "pandas": "2.2.2", "numpy": "1.26.4"}, ["pandas"]) == \
        "Python 3.12.15 · pandas 2.2.2"


@pytest.mark.slow
def test_venv_backend_builds_the_pinned_runtime_and_blocks_the_network(tmp_path, monkeypatch, platform_var):
    code = ("import socket, six, sys\nprint(six.__version__, sys.version.split()[0])\n"
            "try:\n    socket.create_connection(('1.1.1.1', 53), timeout=3)\n    print('online')\n"
            "except OSError:\n    print('offline')\n")
    root = pinned(make_book(tmp_path, examples={"hello": (code, "1.16.0 3.12.15\noffline\n")}), requirements="six==1.16.0\n")
    results, runtime = examples.run_examples(bookfmt.load_book(root), examples.VenvBackend(block_network=True))
    r = results[0]
    assert r.passing, r.diff or r.stderr_tail
    assert r.versions == {"python": "3.12.15", "six": "1.16.0"} and r.direct == ["six"]
    assert runtime["network"] == "blocked" and runtime["backend"] == "venv"


def test_the_venv_backend_refuses_to_run_online_when_it_cant_block_the_network(tmp_path, monkeypatch):
    monkeypatch.setattr(examples, "can_block_network", lambda: False)
    monkeypatch.delenv("RE_EXAMPLES_ALLOW_NETWORK", raising=False)
    backend = examples.VenvBackend(block_network=True)
    with pytest.raises(examples.ExamplesError, match="can't be blocked"):
        backend.command(examples.Runtime("3.12.15", ""), tmp_path, "hello")
    monkeypatch.setenv("RE_EXAMPLES_ALLOW_NETWORK", "1")                  # said out loud, and recorded as open
    allowed = examples.VenvBackend(block_network=True)
    assert "unshare" not in allowed.command(examples.Runtime("3.12.15", ""), tmp_path, "hello")[0]
    assert allowed.describe(examples.Runtime("3.12.15", ""))["network"] == "open"


def test_an_empty_base_commit_has_no_ids(tmp_path):
    repo = make_book(tmp_path / "repo")
    git(repo, "init", "-q", "-b", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "Create repository")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "First edition")
    assert cli.main(["section-ids", "--book", str(repo), "--base-ref", "HEAD~1", "--previous", "none"]) == 0
