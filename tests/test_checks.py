import json
import subprocess
from pathlib import Path

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


def test_a_change_to_narration_alone_needs_no_kind_label():
    narration = ["narration/lexicon.toml", "narration/what-relevance-means.toml"]
    assert checks.narration_only(narration) and not checks.narration_only([]) and not checks.narration_only(
        narration + ["chapters/01-a.md"]) and not checks.narration_only(["chapters/narration/x.toml"])
    assert checks.check_kind_label([], narration) == []
    assert checks.check_kind_label(["tier:expert"], narration) == []
    assert "needs at least one kind label" in checks.check_kind_label([], narration + ["chapters/01-a.md"])[0]
    assert "needs at least one kind label" in checks.check_kind_label([], [])[0]       # nothing known: as before
    assert any("unknown label 'kind:audio'" in p for p in checks.check_kind_label(["kind:audio"], narration))


def test_the_kind_label_check_reads_what_the_pull_request_changes_from_the_book(tmp_path, capsys):
    import subprocess
    book = tmp_path / "book"
    git = lambda *a: subprocess.run(["git", "-C", str(book), "-c", "user.name=T", "-c", "user.email=t@example.invalid",  # noqa: E731
                                     *a], check=True, capture_output=True, text=True).stdout.strip()
    (book / "chapters").mkdir(parents=True)
    (book / "chapters" / "01-a.md").write_text("# A\n")
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-qm", "base")
    base = git("rev-parse", "HEAD")
    git("checkout", "-qb", "describe")
    (book / "narration").mkdir()
    (book / "narration" / "a.toml").write_text('[examples.x]\nsay = "It prints one."\n')
    git("add", "-A")
    git("commit", "-qm", "describe")
    head = git("rev-parse", "HEAD")
    event = tmp_path / "event.json"
    event.write_text(json.dumps({"pull_request": {"labels": [], "base": {"sha": base}, "head": {"sha": head}}}))
    assert checks.changed_from_event(event, book) == ["narration/a.toml"]
    assert cli.main(["kind-label", "--event", str(event), "--book", str(book)]) == 0
    assert "only narration changed (narration/a.toml): no kind label needed" in capsys.readouterr().out
    assert cli.main(["kind-label", "--event", str(event)]) == 1                 # without the book, a label is needed
    (book / "chapters" / "01-a.md").write_text("# A, again\n")
    git("commit", "-qam", "and the page")
    event.write_text(json.dumps({"pull_request": {"labels": [], "base": {"sha": base}, "head": {"sha": git("rev-parse", "HEAD")}}}))
    assert cli.main(["kind-label", "--event", str(event), "--book", str(book)]) == 1
    event.write_text(json.dumps({"pull_request": {"labels": [], "base": {"sha": "0" * 40}, "head": {"sha": head}}}))
    assert checks.changed_from_event(event, book) is None                       # an unknown commit: no verdict


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


def test_every_run_sets_the_same_threads_whatever_the_machine_has(monkeypatch):
    """A sum split across another number of threads rounds differently, so the count is [run]'s on every machine,
    pinned to a few CPUs or not; the BLAS kernels join it only when [run] pins them."""
    threads = str(examples.run_settings()["threads"])
    for cpus in (2, 4, 32):
        monkeypatch.setattr(examples.os, "cpu_count", lambda: cpus)
        monkeypatch.setattr(examples.os, "sched_getaffinity", lambda pid: set(range(cpus)), raising=False)
        env = examples._clean_env({})
        assert [env[v] for v in examples.THREAD_VARS] == [threads] * len(examples.THREAD_VARS)
    assert {"OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"} <= set(examples.THREAD_VARS)
    pinned = examples.thread_env({"threads": 2, "openblas_coretype": "Haswell", "mkl_cbwr": ""})
    assert pinned["OPENBLAS_CORETYPE"] == "Haswell" and "MKL_CBWR" not in pinned and pinned["OMP_NUM_THREADS"] == "2"
    with pytest.raises(examples.ExamplesError, match="1 or more"):
        examples.thread_env({"threads": 0})


def test_the_seed_and_the_threads_take_effect_in_a_run(tmp_path):
    """The flags honour the clean environment, as -I didn't: the hash printed twice is the same, under each seed its
    own; no bytecode is written; and the example's folder is on the path, the user's site isn't."""
    code = ("import os, sys\nprint(hash('abc'))\nprint(os.environ['PYTHONHASHSEED'], os.environ['OMP_NUM_THREADS'])\n"
            "f = sys.flags\nprint(f.dont_write_bytecode, f.no_user_site, f.safe_path, f.ignore_environment)\n"
            "import lib\nprint(lib.VALUE)\n")
    root = pinned(make_book(tmp_path, examples={"seeded": (code, "")}))
    (root / "examples" / "lib.py").write_text("VALUE = 'local module'\n")
    book = bookfmt.load_book(root)
    rt = examples.read_runtime(root)
    runs = [examples.run_one(book, "seeded", rt, examples.HostBackend(), 60, seed) for seed in (0, 0, 1)]
    assert all(r.exit_code == 0 for r in runs), runs[0].stderr_tail
    first, again, other = (r.stdout.splitlines() for r in runs)
    assert first == again                                                  # the same hash on every run
    assert first[0] != other[0] and other[1].startswith("1 ")              # and another under another seed
    assert first[1] == f"0 {examples.run_settings()['threads']}" and first[2] == "1 1 True 0"
    assert first[3] == "local module"
    assert not list((root / "examples").rglob("__pycache__"))


def test_two_seeds_fail_an_example_whose_output_depends_on_the_seed(tmp_path):
    ordered = "print(sorted({'pear', 'apple', 'fig', 'kiwi', 'plum'}))\n"
    unordered = "print(list({'pear', 'apple', 'fig', 'kiwi', 'plum', 'lime', 'date', 'yuzu'}))\n"
    root = pinned(make_book(tmp_path, examples={"ordered": (ordered, "['apple', 'fig', 'kiwi', 'pear', 'plum']\n"),
                                               "unordered": (unordered, None)}))
    book = bookfmt.load_book(root)
    one, _ = examples.run_examples(book, examples.HostBackend(), only=["unordered"])
    (root / "examples" / "unordered.out").write_text(one[0].stdout)          # recorded under seed 0
    book = bookfmt.load_book(root)
    results, runtime = examples.run_examples(book, examples.HostBackend(), seeds=[0, 1])
    by = {r.example_id: r for r in results}
    assert by["ordered"].passing and by["ordered"].seeds == [0, 1] and not by["ordered"].seed_diff
    assert not by["unordered"].passing and by["unordered"].diff == ""     # seed 0 still matches the book
    assert "PYTHONHASHSEED=1" in by["unordered"].seed_diff and runtime["seeds"] == [0, 1]
    assert examples.parse_seeds("0,1") == [0, 1] and examples.parse_seeds(None) == [examples.run_settings()["seed"]]
    for bad in ("0,0", "a", "-1", ","):
        with pytest.raises(examples.ExamplesError, match="--seeds"):
            examples.parse_seeds(bad)


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
    base = examples.base_for("3.12.15")
    assert f"BASE={base['image']}" in build and build[-1] == str(tmp_path)
    assert base["image"].startswith("python:3.12.15-slim@sha256:") and f"PACKAGES={' '.join(base['packages'])}" in build
    assert all("=" in p for p in base["packages"])                         # each Debian package at its version
    run, _ = backend.command(rt, tmp_path, "load-orders.py")
    assert run[:5] == ["docker", "run", "--rm", "--network", "none"] and backend.image(rt) in run
    assert run[run.index(backend.image(rt)) + 1:] == ["python", "-B", "-P", "-s", ".re_harness.py", "load-orders.py"]
    with pytest.raises(examples.ExamplesError, match="no pinned base image"):
        backend.tag(examples.Runtime("3.12.4", "pandas==2.2.2\n"))
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


def test_a_runtime_is_built_without_the_callers_credentials(tmp_path, monkeypatch):
    """The venv backend's build steps and the resolver install from the package index, where a package with no wheel
    runs its own build code: they get the caller's environment without a key, a token or a password in it."""
    caller = {"PATH": "/usr/bin", "HOME": "/home/someone", "UV_CACHE_DIR": "/cache/uv", "XDG_CACHE_HOME": "/cache",
              "ANTHROPIC_API_KEY": "sk-ant-placeholder", "ANTHROPIC_BASE_URL": "http://127.0.0.1:8099",
              "GITHUB_TOKEN": "placeholder", "RE_GCP_ACCESS_TOKEN": "placeholder", "MY_SERVICE_PASSWORD": "placeholder",
              "AWS_SECRET_ACCESS_KEY": "placeholder", "SSH_AUTH_SOCK": "/tmp/agent", "CLAUDE_CODE_OAUTH_TOKEN": "x",
              "UV_INDEX_URL": "https://user:pw@index.example.com/simple", "PIP_INDEX_URL": "https://pypi.org/simple",
              "PWD": "/work", "KEYBOARD_LAYOUT": "us"}
    env = examples.credential_free_env(caller)
    assert env == {"PATH": "/usr/bin", "HOME": "/home/someone", "UV_CACHE_DIR": "/cache/uv", "XDG_CACHE_HOME": "/cache",
                   "PIP_INDEX_URL": "https://pypi.org/simple", "PWD": "/work", "KEYBOARD_LAYOUT": "us"}
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-placeholder")
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(tmp_path / "envs"))
    seen = []

    def fake_run(cmd, **kw):
        seen.append(kw.get("env"))
        if "venv" in cmd:
            Path(cmd[-1]).mkdir(parents=True)                      # uv venv makes the runtime's folder
        return subprocess.CompletedProcess(cmd, 0, "", "")
    monkeypatch.setattr(examples.subprocess, "run", fake_run)
    examples.VenvBackend(block_network=False).prepare(examples.Runtime("3.12.15", "six==1.16.0\n"))
    assert len(seen) == 3 and all(e is not None and "ANTHROPIC_API_KEY" not in e for e in seen)   # venv, install, stdlib
    got = []
    monkeypatch.setattr(examples.resolve, "check", lambda *a, **k: got.append(k.get("env")) or examples.resolve.Resolution("ok"))
    examples.check_pins(examples.Runtime("3.12.16", "six==1.16.0\n"), examples.VenvBackend(block_network=False))
    assert got and "ANTHROPIC_API_KEY" not in got[0]
