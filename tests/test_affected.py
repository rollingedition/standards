"""`re-check examples --affected`: only the examples a change could affect run, each with why, and every example runs,
saying why, whenever that can't be told."""
import importlib.machinery
import json
import subprocess
import sys
from pathlib import Path

import pytest

from re_standards import affected, bookfmt, cli, examples
from bookkit import make_book

LIB = {
    "__init__.py": "",
    "frames.py": "try:\n    import pandas as pd\nexcept ImportError:      # not on the host backend\n    pd = None\n\n"
                 "from .shapes import square\n\ndef table(n):\n    return [square(n)]\n",
    "shapes.py": "def square(n):\n    return n * n\n",
    "words.py": "try:\n    import six\nexcept ImportError:      # not on the host backend\n    six = None\n\nWORD = 'word'\n",
}
EXAMPLES = {
    "uses-frames": ("from lib.frames import table\nprint(table(3))\n", "[9]\n"),
    "uses-shapes": ("from lib import shapes\nprint(shapes.square(2))\n", "4\n"),
    "uses-words": ("import lib.words\nprint(lib.words.WORD)\n", "word\n"),
    "uses-numpy": ("try:\n    import numpy\nexcept ImportError:\n    numpy = None\nprint('numpy')\n", "numpy\n"),
    "plain": ("import os\nprint('plain')\n", "plain\n"),
}
PINS = "# pins\nnumpy==2.0.0\npandas==3.0.0\nsix==1.16.0\n"
ENVIRONMENT = affected.Environment({
    "numpy": {"version": "2.0.0", "imports": ["numpy"], "requires": []},
    "pandas": {"version": "3.0.0", "imports": ["pandas"], "requires": ["numpy", "python-dateutil"]},
    "python-dateutil": {"version": "2.9.0", "imports": ["dateutil"], "requires": ["six"]},
    "six": {"version": "1.16.0", "imports": ["six"], "requires": []},
}, stdlib={"os", "sys", "importlib", "subprocess", "json"})


def git(repo, *args) -> str:
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A small book with a lib/ package, committed: the base every test changes."""
    root = make_book(tmp_path / "book", examples=EXAMPLES)
    (root / "examples" / ".python-version").write_text("3.12.15\n")
    (root / "examples" / "requirements.txt").write_text(PINS)
    (root / "examples" / "lib").mkdir()
    for name, text in LIB.items():
        (root / "examples" / "lib" / name).write_text(text)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    return root


def chosen(root, environment=ENVIRONMENT, recorded=None, base="HEAD"):
    change, why = affected.change_from_git(root, base)
    return affected.select(bookfmt.load_book(root), change, environment, recorded, why_unknown=why)


def edit(root, rel, text):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# ---------------------------------------------------------------- the rules


def test_nothing_in_the_examples_changed_so_none_runs(repo):
    edit(repo, "chapters/01-first-steps.md", (repo / "chapters" / "01-first-steps.md").read_text() + "\nMore prose.\n")
    edit(repo, "narration/lexicon.toml", "[terms]\n")
    sel = chosen(repo)
    assert sel.examples == {} and sel.everything == [] and sel.total == 5
    assert sel.lines()[0].startswith("No example can be affected by this change")


def test_an_examples_own_code_or_recorded_output(repo):
    edit(repo, "examples/plain.py", "import os\nprint('plain, again')\n")
    assert chosen(repo).examples == {"plain": ["its code changed"]}
    git(repo, "checkout", "--", ".")
    edit(repo, "examples/uses-numpy.out", "numpy, recorded again\n")
    assert chosen(repo).examples == {"uses-numpy": ["its recorded output changed"]}


def test_a_new_example_runs_even_before_it_is_committed(repo):
    edit(repo, "examples/brand-new.py", "print('new')\n")
    edit(repo, "examples/brand-new.out", "new\n")
    assert chosen(repo).examples == {"brand-new": ["its recorded output changed", "its code changed"]}


def test_a_local_module_reruns_every_example_that_imports_it_directly_or_not(repo):
    edit(repo, "examples/lib/shapes.py", "def square(n):\n    return n ** 2\n")
    sel = chosen(repo)
    assert sel.ids == ["uses-frames", "uses-shapes"]                  # uses-frames reaches it through lib/frames.py
    assert sel.examples["uses-frames"] == ["it imports lib/shapes.py, which changed, through lib/frames.py"]
    assert sel.examples["uses-shapes"] == ["it imports lib/shapes.py, which changed"]
    git(repo, "checkout", "--", ".")
    edit(repo, "examples/lib/words.py", LIB["words.py"].replace("'word'", "'words'"))
    assert chosen(repo).ids == ["uses-words"]


def test_a_package_init_reaches_every_example_that_imports_from_the_package(repo):
    edit(repo, "examples/lib/__init__.py", "\"\"\"Shared code.\"\"\"\n")
    assert chosen(repo).ids == ["uses-frames", "uses-shapes", "uses-words"]


def test_a_removed_module_still_reaches_what_imported_it(repo):
    (repo / "examples" / "lib" / "words.py").unlink()
    assert chosen(repo).ids == ["uses-words"]


def test_a_data_change_runs_every_example_since_what_each_reads_isnt_recorded(repo):
    edit(repo, "examples/data/orders/orders.csv", "id\n1\n")
    sel = chosen(repo)
    assert sel.ids == sorted(EXAMPLES) and len(sel.everything) == 1
    assert sel.everything[0] == ("examples/data/orders/orders.csv changed under examples/data/, and what each example "
                                 "reads isn't recorded")


@pytest.mark.parametrize("path", ["examples/pipelines/orders.sql", "examples/lib/stopwords.txt", "examples/requirements.in"])
def test_any_other_file_beside_the_examples_runs_them_all(repo, path):
    edit(repo, path, "something\n")
    sel = chosen(repo)
    assert sel.ids == sorted(EXAMPLES)
    assert sel.everything == [f"{path} changed: a file beside the examples, which any of them may read"]


def test_a_new_python_runs_them_all_and_a_reformatted_one_runs_none(repo):
    edit(repo, "examples/.python-version", "3.12.15  \n")
    assert chosen(repo).examples == {}
    edit(repo, "examples/.python-version", "3.13.9\n")
    sel = chosen(repo)
    assert sel.ids == sorted(EXAMPLES)
    assert sel.everything == ["examples/.python-version changed from 3.12.15 to 3.13.9: every example runs on the new Python"]


def test_a_moved_pin_reruns_what_imports_it_or_depends_on_it(repo):
    edit(repo, "examples/requirements.txt", PINS.replace("numpy==2.0.0", "numpy==2.1.0"))
    sel = chosen(repo)
    assert sel.ids == ["uses-frames", "uses-numpy"]
    assert sel.examples["uses-numpy"] == ["numpy 2.0.0 to 2.1.0: it imports numpy"]
    assert sel.examples["uses-frames"] == ["numpy 2.0.0 to 2.1.0: it imports pandas, which depends on numpy"]
    edit(repo, "examples/requirements.txt", PINS.replace("six==1.16.0", "six==1.17.0"))
    sel = chosen(repo)                       # through lib, and through pandas, which requires dateutil, which requires six
    assert sel.ids == ["uses-frames", "uses-words"]
    assert sel.examples["uses-words"] == ["six 1.16.0 to 1.17.0: it imports six, through lib/words.py"]
    assert sel.examples["uses-frames"] == ["six 1.16.0 to 1.17.0: it imports pandas, which depends on six"]
    assert sel.reached == {"six": ["uses-frames", "uses-words"]}           # what each moved pin reached, for the record
    assert sel.as_json()["reached"] == {"six": ["uses-frames", "uses-words"]}


def test_a_comment_in_the_pins_changes_nothing(repo):
    edit(repo, "examples/requirements.txt", PINS + "# a note\n")
    assert chosen(repo).examples == {}


@pytest.mark.parametrize("pins,words", [
    (PINS + "scipy==1.18.1\n", "scipy newly pinned"),
    (PINS.replace("six==1.16.0\n", ""), "six unpinned"),
])
def test_an_added_or_removed_pin_runs_them_all(repo, pins, words):
    edit(repo, "examples/requirements.txt", pins)
    sel = chosen(repo)
    assert sel.ids == sorted(EXAMPLES)
    assert sel.everything == [f"{words}: what's installed changed, and a library can import another only once it's there"]


def test_without_the_runtimes_metadata_a_moved_pin_runs_them_all(repo):
    edit(repo, "examples/requirements.txt", PINS.replace("six==1.16.0", "six==1.17.0"))
    sel = affected.select(bookfmt.load_book(repo), affected.change_from_git(repo, "HEAD")[0], None,
                          environment_problem="the runtime didn't answer")
    assert sel.ids == sorted(EXAMPLES)
    assert sel.everything == ["the runtime's installed packages couldn't be read: the runtime didn't answer, so what "
                              "imports six isn't known"]


def test_an_unknown_mapping_runs_them_all(repo):
    edit(repo, "examples/requirements.txt", PINS.replace("six==1.16.0", "six==1.17.0"))
    gone = affected.Environment({k: v for k, v in ENVIRONMENT.distributions.items() if k != "six"}, ENVIRONMENT.stdlib)
    assert chosen(repo, gone).everything == ["six isn't installed in the runtime, so what imports it isn't known"]
    nameless = affected.Environment(dict(ENVIRONMENT.distributions, six={"version": "1.16.0", "imports": None,
                                                                          "requires": []}), ENVIRONMENT.stdlib)
    assert chosen(repo, nameless).everything == ["six 1.16.0 to 1.17.0: six has no metadata naming what it can be "
                                                 "imported as"]
    dependent = dict(ENVIRONMENT.distributions)
    dependent["python-dateutil"] = dict(dependent["python-dateutil"], imports=None, pth=True)
    assert chosen(repo, affected.Environment(dependent, ENVIRONMENT.stdlib)).everything == [
        "six 1.16.0 to 1.17.0: python-dateutil, which depends on it, installs a .pth file, which runs at every start of "
        "Python and can change what any import finds"]


def test_an_example_whose_imports_cant_all_be_read_runs_on_every_pin_or_module_change(repo):
    edit(repo, "examples/plain.py", "import importlib\nname = 'json'\nimportlib.import_module(name)\nprint('plain')\n")
    git(repo, "commit", "-qam", "dynamic")
    edit(repo, "examples/requirements.txt", PINS.replace("six==1.16.0", "six==1.17.0"))
    assert chosen(repo).examples["plain"] == ["six 1.16.0 to 1.17.0: its imports can't all be read: import_module with a "
                                              "computed name in plain.py"]
    git(repo, "checkout", "--", ".")
    edit(repo, "examples/lib/shapes.py", "def square(n):\n    return n ** 2\n")
    assert chosen(repo).examples["plain"] == ["a local module changed, and its imports can't all be read: import_module "
                                              "with a computed name in plain.py"]


@pytest.mark.parametrize("code,why", [
    ("import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'print(1)'])\n",
     "plain.py imports subprocess, so it can start another program"),
    ("import os\nos.system('true')\n", "os.system in plain.py starts another program"),
    ("code = open('x').read()\nexec(code)\n", "exec of a computed string in plain.py"),
    ("import runpy\nrunpy.run_path('other.py')\n", "run_path in plain.py"),
])
def test_another_program_or_computed_code_counts_as_unknown_imports(tmp_path, code, why):
    root = make_book(tmp_path / "b", examples={"plain": (code, "\n")})
    assert why in affected.imports_of(root / "examples", "plain.py").unknown


def test_written_out_dynamic_imports_and_exec_are_read(tmp_path):
    root = make_book(tmp_path / "b", examples={"plain": (
        "import importlib\nimportlib.import_module('numpy')\n__import__('six')\nexec('import pandas')\n"
        "model = object()\n", "\n")})
    imp = affected.imports_of(root / "examples", "plain.py")
    assert imp.unknown == [] and {"numpy", "six", "pandas", "importlib"} <= set(imp.names)


def test_an_import_no_installed_package_names_runs_on_every_pin_change(repo):
    edit(repo, "examples/plain.py", "import mystery\nprint('plain')\n")
    git(repo, "commit", "-qam", "mystery")
    edit(repo, "examples/requirements.txt", PINS.replace("six==1.16.0", "six==1.17.0"))
    assert chosen(repo).examples["plain"] == ["six 1.16.0 to 1.17.0: it imports mystery, which no installed package's "
                                              "metadata names"]


def test_the_last_runs_record_adds_what_an_example_loaded(repo):
    """A library that imports another only when it's installed: the harness saw it loaded, the imports don't say."""
    edit(repo, "examples/requirements.txt", PINS.replace("six==1.16.0", "six==1.17.0"))
    record = {"examples": [{"example_id": "uses-numpy", "versions": {"python": "3.12.15", "numpy": "2.0.0", "six": "1.16.0"}},
                           {"example_id": "plain", "versions": {"python": "3.12.15"}}]}
    sel = chosen(repo, recorded=record)
    assert sel.examples["uses-numpy"] == ["six 1.16.0 to 1.17.0: it loaded six when it last ran"]
    assert "plain" not in sel.examples                                  # the record only ever adds


def test_without_the_base_commit_every_example_runs(repo):
    sel = chosen(repo, base="0" * 40)
    assert sel.ids == sorted(EXAMPLES) and "isn't in this checkout" in sel.everything[0]
    sel = chosen(repo, base="")
    assert sel.everything == ["no base commit was given to compare with"]


def test_a_changed_runtime_outside_the_book_runs_them_all():
    before = {"backend": "container", "python": "3.12.15", "network": "none", "image": "re-examples:py3.12.15-abc-1111",
              "runner": "r1"}
    assert affected.runtime_changes(before, dict(before)) == []
    assert affected.runtime_changes(before, dict(before, image="re-examples:py3.12.15-def-1111")) == []   # new pins only
    assert affected.runtime_changes(before, dict(before, image="re-examples:py3.12.15-abc-2222")) == [
        "the runtime image's definition changed"]
    assert affected.runtime_changes(before, dict(before, backend="venv", runner="r2")) == [
        "the runtime's backend changed from container to venv", "the code that runs the examples changed"]
    assert affected.runtime_changes({k: v for k, v in before.items() if k != "runner"}, before) == [
        "the last run doesn't record which version of the code that runs the examples it used"]
    assert affected.runtime_changes(None, before) == []
    assert len(affected.runner_key()) == 16


# ---------------------------------------------------------------- the runtime's metadata, read in the runtime


def fake_dist(site: Path, name: str, version: str, files: list[str], requires: list[str] = (), top_level: str | None = None):
    info = site / f"{name.replace('-', '_')}-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
                                   + "".join(f"Requires-Dist: {r}\n" for r in requires))
    (info / "RECORD").write_text("".join(f"{f},,\n" for f in files + [f"{info.name}/METADATA", f"{info.name}/RECORD"]))
    for f in files:                             # Python leaves out a RECORD entry whose file is missing
        (site / f).parent.mkdir(parents=True, exist_ok=True)
        (site / f).write_text("")
    if top_level is not None:
        (info / "top_level.txt").write_text(top_level)


def test_the_harness_reads_import_names_and_requirements_from_metadata(tmp_path):
    site = tmp_path / "site"
    so = "_alpha_speedups" + importlib.machinery.EXTENSION_SUFFIXES[0]       # as this Python names an extension module
    fake_dist(site, "alpha-lib", "1.0", ["alpha/__init__.py", "alpha/core.py", so], ["beta>=2", 'gamma; extra == "fast"', 'delta; python_version < "3.9"'])
    fake_dist(site, "beta", "2.0", ["beta.py"], top_level="beta\nbeta_compat\n")
    fake_dist(site, "editable-thing", "0.1", ["__editable__.editable_thing-0.1.pth"])
    fake_dist(site, "no-record", "1.0", [])
    (site / "no_record-1.0.dist-info" / "RECORD").unlink()
    harness = tmp_path / ".re_harness.py"
    harness.write_text(examples.HARNESS.read_text())
    report = tmp_path / "report.json"
    code = (f"import sys; sys.path.insert(0, {str(site)!r}); sys.argv = ['h', '--metadata']; "
            f"import runpy; runpy.run_path({str(harness)!r}, run_name='__main__')")
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, env={"RE_EXAMPLE_REPORT": str(report)})
    assert r.returncode == 0, r.stderr
    found = json.loads(report.read_text())
    dists = found["distributions"]
    assert dists["alpha-lib"] == {"version": "1.0", "imports": ["_alpha_speedups", "alpha"],
                                  "requires": ["beta", "delta", "gamma"], "pth": False}       # extras and markers count
    assert dists["beta"]["imports"] == ["beta", "beta_compat"]                                # top_level.txt and RECORD
    assert dists["editable-thing"]["imports"] is None and dists["editable-thing"]["pth"] is True
    assert dists["no-record"]["imports"] is None
    assert "os" in found["stdlib"] and found["python"] == ".".join(map(str, sys.version_info[:3]))


def test_installed_reads_the_metadata_inside_the_runtime(tmp_path):
    found = examples.installed(examples.Runtime("3.12.15", ""), examples.HostBackend())
    assert found["distributions"]["packaging"]["imports"] == ["packaging"]
    assert "json" in found["stdlib"]
    env = affected.Environment.from_report(found)
    assert "packaging" in env.providers()["packaging"]


# ---------------------------------------------------------------- the command


def test_the_command_runs_only_the_affected_examples_and_says_why(repo, tmp_path, capsys):
    edit(repo, "examples/lib/shapes.py", "def square(n):\n    return n * n  # the same\n")
    report = tmp_path / "report.json"
    assert cli.main(["examples", "--book", str(repo), "--backend", "host", "--affected", "--base-ref", "HEAD",
                     "--report", str(report)]) == 0
    out = capsys.readouterr().out
    assert "Examples this change could affect, against" in out and "2 of 5 run" in out
    assert "run   uses-frames: it imports lib/shapes.py, which changed, through lib/frames.py" in out
    assert "3 more: nothing this change touches reaches them" in out
    assert "2 of 2 affected examples pass; the other 3 can't be affected by this change" in out
    data = json.loads(report.read_text())
    assert data["outcome"] == "passed" and data["total"] == 2
    assert [e["example_id"] for e in data["examples"]] == ["uses-frames", "uses-shapes"]
    assert data["selection"]["all"] is False and sorted(data["selection"]["run"]) == ["uses-frames", "uses-shapes"]


def test_the_command_runs_none_when_nothing_reaches_an_example(repo, capsys):
    edit(repo, "README.md", "A new front page.\n")
    assert cli.main(["examples", "--book", str(repo), "--backend", "host", "--affected", "--base-ref", "HEAD"]) == 0
    assert "no example can be affected by this change, so none of 5 ran" in capsys.readouterr().out


def test_the_command_reads_the_runtime_only_when_a_pin_moved(repo, monkeypatch, capsys):
    calls = []

    def installed(runtime, backend, timeout=120):
        calls.append(runtime.pins())
        return {"python": "3.12.15", "stdlib": sorted(ENVIRONMENT.stdlib), "distributions": ENVIRONMENT.distributions}
    monkeypatch.setattr(examples, "installed", installed)
    edit(repo, "examples/plain.py", "import os\nprint('plain')  # unchanged output\n")
    assert cli.main(["examples", "--book", str(repo), "--backend", "host", "--affected", "--base-ref", "HEAD", "--list"]) == 0
    assert calls == [] and "run   plain: its code changed" in capsys.readouterr().out
    edit(repo, "examples/requirements.txt", PINS.replace("numpy==2.0.0", "numpy==2.1.0"))
    assert cli.main(["examples", "--book", str(repo), "--backend", "host", "--affected", "--base-ref", "HEAD", "--list"]) == 0
    out = capsys.readouterr().out
    assert calls == [{"numpy": "2.1.0", "pandas": "3.0.0", "six": "1.16.0"}]
    assert "run   uses-numpy: numpy 2.0.0 to 2.1.0: it imports numpy" in out and "3 of 5 run" in out
    assert "pass" not in out                                                     # --list runs nothing


def test_every_example_runs_and_the_command_says_why(repo, capsys):
    edit(repo, "examples/data/orders.csv", "id\n")
    assert cli.main(["examples", "--book", str(repo), "--backend", "host", "--affected", "--base-ref", "HEAD"]) == 0
    out = capsys.readouterr().out
    assert "Every example runs (5), against" in out and "what each example reads isn't recorded" in out
    assert "5 of 5 examples pass" in out


def test_the_affected_options_go_together(repo, capsys):
    assert cli.main(["examples", "--book", str(repo), "--backend", "host", "--base-ref", "HEAD"]) == 1
    assert "go with --affected" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["examples", "--book", str(repo), "--affected", "--only", "plain"])


def test_a_record_that_cant_be_read_leaves_the_imports_to_decide(repo):
    record, note = affected.load_recorded("http://127.0.0.1:9/sections.json", "tiny-book")
    assert record is None and "the imports alone decide" in note
    assert affected.load_recorded("none", "tiny-book") == (None, "")
    path = repo.parent / "sections.json"
    path.write_text(json.dumps({"examples": [{"example_id": "plain", "versions": {"python": "3.12.15", "Six": "1"}}]}))
    record, _ = affected.load_recorded(str(path), "tiny-book")
    assert affected.recorded_loaded(record) == {"plain": {"six"}}
