"""Pins that can't be installed together: the resolver reads them before the runtime is built, and the examples check
says so in plain words, as its own outcome, never as an example's failure.

The resolver is the real uv, reading a package index on disk made of metadata-only wheels (wheelkit.py), so nothing here
needs the network. The resolver messages in the second half are uv's own, for the five updates that couldn't install
alone in October 2026."""
import json
import subprocess

import pytest

from bookkit import make_book
from re_standards import cli, examples, resolve
from wheelkit import offline_env, wheel_index

PRESIDIO = {("presidio-anonymizer", "2.2.364"): ["cryptography<49.0.0,>=48.0.1"],
            ("cryptography", "48.0.0"): [], ("cryptography", "48.0.1"): [], ("cryptography", "50.0.0"): []}


def pinned(root, python="3.12.15", requirements="pandas==2.2.2\n"):
    (root / "examples" / ".python-version").write_text(python + "\n")
    (root / "examples" / "requirements.txt").write_text(requirements)
    return root


@pytest.fixture
def offline(tmp_path, monkeypatch):
    """uv reads only a folder of wheels, for every command in the test."""
    def use(packages):
        for key, value in offline_env(wheel_index(tmp_path / "index", packages), tmp_path / "uv-cache").items():
            monkeypatch.setenv(key, value)
    return use


def test_pins_that_install_together_resolve(offline):
    offline(PRESIDIO)
    found = resolve.check("3.12.15", "cryptography==48.0.1\npresidio-anonymizer==2.2.364\n", {})
    assert found.outcome == "ok" and found.pins == {"cryptography": "48.0.1", "presidio-anonymizer": "2.2.364"}
    assert found.tool.startswith("uv ")


def test_a_conflict_is_named_in_plain_words(offline):
    offline(PRESIDIO)
    text = "cryptography==50.0.0\npresidio-anonymizer==2.2.364\n"
    found = resolve.check("3.12.15", text, {"cryptography": "50.0.0", "presidio-anonymizer": "2.2.364"})
    assert found.outcome == "unsatisfiable" and "presidio-anonymizer" in found.message
    assert found.conflict == {"package": "presidio-anonymizer", "version": "2.2.364",
                              "requires": "cryptography>=48.0.1,<49.0.0", "pinned": "cryptography==50.0.0"}
    assert found.explanation == ("The pins can't be installed together: presidio-anonymizer 2.2.364 requires "
                                 "cryptography>=48.0.1,<49.0.0, and the pins say cryptography==50.0.0.")


def test_a_resolver_that_cant_reach_its_index_is_no_verdict(tmp_path, monkeypatch):
    """A network failure isn't the book's problem: the runtime is built as before and reports what goes wrong itself."""
    for key, value in {"UV_INDEX_URL": "http://127.0.0.1:9/simple", "UV_CACHE_DIR": str(tmp_path / "c"),
                       "UV_HTTP_RETRIES": "0", "UV_PYTHON_DOWNLOADS": "never"}.items():
        monkeypatch.setenv(key, value)
    found = resolve.check("3.12.15", "six==1.16.0\n", {"six": "1.16.0"})
    assert found.outcome == "unavailable" and "Failed to fetch" in found.message
    monkeypatch.setattr(resolve, "uv_command", lambda: None)
    assert resolve.check("3.12.15", "six==1.16.0\n", {}).outcome == "unavailable"


def test_the_check_reports_unsatisfiable_pins_as_their_own_outcome(tmp_path, offline, monkeypatch, capsys):
    offline(PRESIDIO)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    root = pinned(make_book(tmp_path / "book"), requirements="cryptography==50.0.0\npresidio-anonymizer==2.2.364\n")
    built = []
    monkeypatch.setattr(examples.VenvBackend, "prepare", lambda self, rt: built.append(rt))
    report = tmp_path / "report.json"
    assert cli.main(["examples", "--book", str(root), "--backend", "venv", "--report", str(report)]) == 1
    assert built == []                                              # no runtime was built, and no example ran
    data = json.loads(report.read_text())
    assert data["outcome"] == "unsatisfiable" and data["examples"] == [] and data["passing"] == 0 and data["total"] == 1
    assert data["resolver"]["conflict"]["package"] == "presidio-anonymizer" and data["resolver"]["tool"].startswith("uv ")
    assert data["resolver"]["explanation"].startswith("The pins can't be installed together: presidio-anonymizer 2.2.364")
    assert data["runtime"]["python"] == "3.12.15"
    out, err = capsys.readouterr()
    assert out.splitlines()[0] == ("::error title=The pins can't be installed together::The pins can't be installed together: "
                                   "presidio-anonymizer 2.2.364 requires cryptography>=48.0.1,<49.0.0, and the pins say "
                                   "cryptography==50.0.0.")
    assert "  - The pins can't be installed together: presidio-anonymizer 2.2.364" in err and "fails on" not in err
    assert "The resolver (uv " in err


def test_outside_a_workflow_runner_there_is_no_annotation(tmp_path, offline, monkeypatch, capsys):
    offline(PRESIDIO)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    root = pinned(make_book(tmp_path / "book"), requirements="cryptography==50.0.0\npresidio-anonymizer==2.2.364\n")
    assert cli.main(["examples", "--book", str(root), "--backend", "venv"]) == 1
    assert "::error" not in capsys.readouterr().out


def test_the_report_says_passed_failed_or_error(tmp_path, monkeypatch):
    root = pinned(make_book(tmp_path / "book"))
    report = tmp_path / "report.json"
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--report", str(report)]) == 0
    assert json.loads(report.read_text())["outcome"] == "passed"
    (root / "examples" / "hello.out").write_text("goodbye\n")
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--report", str(report)]) == 1
    assert json.loads(report.read_text())["outcome"] == "failed"
    (root / "examples" / "requirements.txt").write_text("pandas>=2\n")
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--report", str(report)]) == 1
    data = json.loads(report.read_text())
    assert data["outcome"] == "error" and "not pinned" in data["error"]


def test_the_resolver_reads_only_pins_a_backend_is_about_to_install(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(resolve, "check", lambda *a, **k: calls.append(a) or resolve.Resolution("ok"))
    rt = examples.Runtime("3.12.15", "six==1.16.0\n")
    assert examples.check_pins(rt, examples.HostBackend()) is None              # installs nothing
    assert examples.check_pins(examples.Runtime("3.12.15", ""), examples.ContainerBackend()) is None   # no pins
    monkeypatch.setenv("RE_EXAMPLES_ENV_DIR", str(tmp_path / "envs"))
    venv = examples.VenvBackend()
    assert examples.check_pins(rt, venv).outcome == "ok" and len(calls) == 1
    venv.env_dir(rt).mkdir(parents=True)
    (venv.env_dir(rt) / ".ready").write_text("{}")                              # built before: its pins installed
    assert examples.check_pins(rt, venv) is None and len(calls) == 1
    assert examples.check_pins(rt, examples.ContainerBackend()).outcome == "ok" and len(calls) == 2


# ---------------------------------------------------------------- uv's messages, in plain words

DGAC = {"cryptography": "50.0.0", "presidio-anonymizer": "2.2.364", "presidio-analyzer": "2.2.364", "numpy": "2.5.4",
        "spacy": "3.8.16", "thinc": "9.1.1", "confection": "1.3.3"}
LMFGU_HTTPX2 = {"httpx2": "2.16.0", "httpcore2": "2.14.0"}
LMFGU_HTTPCORE2 = {"httpx2": "2.14.0", "httpcore2": "2.16.0"}
MESSAGES = [
    ("Because presidio-anonymizer==2.2.364 depends on cryptography>=48.0.1,<49.0.0 and you require cryptography==50.0.0, "
     "we can conclude that your requirements and presidio-anonymizer==2.2.364 are incompatible.\nAnd because you require "
     "presidio-anonymizer==2.2.364, we can conclude that your requirements are unsatisfiable.", DGAC,
     "presidio-anonymizer 2.2.364 requires cryptography>=48.0.1,<49.0.0, and the pins say cryptography==50.0.0."),
    ("Because presidio-analyzer==2.2.364 depends on numpy>=1.19.0,<2.5.0 and you require numpy==2.5.4, we can conclude "
     "that your requirements and presidio-analyzer==2.2.364 are incompatible.\nAnd because you require "
     "presidio-analyzer==2.2.364, we can conclude that your requirements are unsatisfiable.", DGAC,
     "presidio-analyzer 2.2.364 requires numpy>=1.19.0,<2.5.0, and the pins say numpy==2.5.4."),
    ("Because spacy==3.8.16 depends on thinc>=8.3.12,<8.4.0 and you require spacy==3.8.16, we can conclude that you "
     "require thinc>=8.3.12,<8.4.0.\nAnd because you require thinc==9.1.1, we can conclude that your requirements are "
     "unsatisfiable.", DGAC, "spacy 3.8.16 requires thinc>=8.3.12,<8.4.0, and the pins say thinc==9.1.1."),
    ("Because httpx2>=2.16.0 depends on httpcore2{sys_platform != 'emscripten'}==2.16.0 and you require httpcore2==2.14.0, "
     "we can conclude that your requirements and httpx2>=2.16.0 are incompatible.\nAnd because you require httpx2==2.16.0, "
     "we can conclude that your requirements are unsatisfiable.", LMFGU_HTTPX2,
     "httpx2 2.16.0 requires httpcore2==2.16.0, and the pins say httpcore2==2.14.0."),
    ("Because httpx2==2.14.0 depends on httpcore2{sys_platform != 'emscripten'}==2.14.0 and you require httpcore2==2.16.0, "
     "we can conclude that your requirements and httpx2==2.14.0 are incompatible.\nAnd because you require httpx2==2.14.0, "
     "we can conclude that your requirements are unsatisfiable.", LMFGU_HTTPCORE2,
     "httpx2 2.14.0 requires httpcore2==2.14.0, and the pins say httpcore2==2.16.0."),
    ("Because thinc>=9.1.1 depends on confection<1.0.0 and you require confection==1.3.3, we can conclude that your "
     "requirements and thinc>=9.1.1 are incompatible.", DGAC,
     "thinc 9.1.1 requires confection<1.0.0, and the pins say confection==1.3.3."),
    ("Because only presidio-analyzer<=2.2.365 is available and presidio-analyzer==2.2.364 depends on numpy>=1.19.0,<2.5.0, "
     "we can conclude that presidio-analyzer==2.2.364 depends on numpy>=1.19.0,<2.5.0.", DGAC,
     "presidio-analyzer 2.2.364 requires numpy>=1.19.0,<2.5.0, and the pins say numpy==2.5.4."),
]


@pytest.mark.parametrize("message,pins,sentence", MESSAGES)
def test_the_real_conflicts_read_as_sentences(message, pins, sentence):
    _, words = resolve.explain(message, pins, "3.12.15")
    assert words == "The pins can't be installed together: " + sentence


def test_a_python_too_old_is_said_as_such():
    message = ("Because the requested Python version (>=3.12.15) does not satisfy Python>=3.13 and numpy==3.0.0 depends "
               "on Python>=3.13, we can conclude that numpy==3.0.0 cannot be used.")
    assert resolve.explain(message, {"numpy": "3.0.0"}, "3.12.15")[1] == \
        "The pins can't be installed together: numpy 3.0.0 requires Python>=3.13, and the examples run on Python 3.12.15."


def test_other_answers_quote_the_resolver():
    assert resolve.explain("Because there is no version of numpy==9.9.9 and you require numpy==9.9.9, we can conclude "
                           "that your requirements are unsatisfiable.", {"numpy": "9.9.9"}, "3.12.15")[1] == \
        "The pins can't be installed: the package index has no release numpy 9.9.9."
    assert resolve.explain("Something new.", {}, "3.12.15")[1] == \
        "The pins can't be installed together. The resolver says: Something new."


def test_an_image_that_doesnt_build_says_what_pip_said(monkeypatch):
    stderr = ("#8 [3/4] RUN pip install --no-cache-dir -r /tmp/requirements.txt\n"
              "#8 1.204 ERROR: Cannot install cryptography==50.0.0 and presidio-anonymizer==2.2.364 because these package "
              "versions have conflicting dependencies.\n#8 1.205 \n#8 1.205 The conflict is caused by:\n"
              "ERROR: failed to solve: process \"/bin/sh -c pip install\" did not complete successfully: exit code: 1\n"
              "--------------------\nDockerfile:9\n--------------------\n")
    monkeypatch.setattr(examples.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 1, "", stderr))
    with pytest.raises(examples.ExamplesError) as e:
        examples.ContainerBackend(registry="").prepare(examples.Runtime("3.12.15", "cryptography==50.0.0\n"))
    assert str(e.value).startswith("could not build the example image: ERROR: Cannot install cryptography==50.0.0 and "
                                   "presidio-anonymizer==2.2.364")


def test_the_settings_name_the_runtimes_platform():
    cfg = resolve.settings()
    assert cfg["python_platform"].startswith("x86_64-manylinux_") and cfg["annotation"]
