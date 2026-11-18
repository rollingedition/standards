"""The local lab (labscripts.py): lab/start.sh, chapter.sh, check.sh and stop.sh, generated from the book, run end to end
on the sampler's plain shell steps with sh, as a reader runs them; and a k3s book's, which fetch every tool at its
pinned SHA-256 for the reader's platform and run k3s's image by digest. Each script run is bounded by a timeout."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from re_standards import bookfmt, cli, labscripts, stack
from test_stack import k3s_book, pinned

SAMPLER = Path(__file__).parent / "fixtures" / "terminal-sampler"
SECONDS = 60


def sampler(tmp_path: Path) -> Path:
    root = tmp_path / "sampler"
    shutil.copytree(SAMPLER, root)
    assert cli.main(["lab", "--book", str(root), "--write"]) == 0
    return root


def sh(root: Path, home: Path, *args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home), "RE_LAB_HOME": str(home / "lab")}
    script, *rest = args
    return subprocess.run(["sh", str(root / script), *rest], cwd=cwd or root, env=env, capture_output=True, text=True,
                          timeout=SECONDS)


def steps_in(work: Path, book: bookfmt.Book, *ids: str) -> None:
    """Run steps as a reader pastes them: each one's command, in the workspace, with bash."""
    for sid in ids:
        r = subprocess.run(["bash", "-c", book.steps[sid].command], cwd=work, capture_output=True, text=True,
                           timeout=SECONDS, stdin=subprocess.DEVNULL)
        assert r.returncode == book.steps[sid].directives.expect_exit, (sid, r.stdout, r.stderr)


def test_the_local_lab_runs_the_sampler_end_to_end(tmp_path, capsys):
    root = sampler(tmp_path)
    assert sorted(p.name for p in (root / "lab").iterdir()) == ["chapter.sh", "check.sh", "start.sh", "stop.sh"]
    assert all(os.access(p, os.X_OK) for p in (root / "lab").iterdir())
    home = tmp_path / "home"
    home.mkdir()
    lab, work = home / "lab", home / "lab" / "work"
    r = sh(root, home, "lab/start.sh")
    assert r.returncode == 0, r.stderr
    assert "Ready. The workspace is" in r.stdout and (work / "data" / "inventory.csv").exists()
    assert not list(work.glob("*.sh")) and not list(work.rglob("*.out"))      # the book's steps aren't the reader's
    assert (lab / "env.sh").read_text().endswith(f'cd "{work}"\n')

    r = sh(root, home, "lab/check.sh", "project-has-readme")
    assert r.returncode == 1 and "Not yet: project-has-readme. Run the step above: it writes project/README.md." in r.stdout
    book = bookfmt.load_book(root)
    steps_in(work, book, "make-project")
    r = sh(root, home, "lab/check.sh", "files-and-folders", cwd=work)      # from the workspace, where the reader is
    assert r.returncode == 0 and r.stdout == "Passed: project-has-readme\n", r.stdout + r.stderr

    r = sh(root, home, "lab/chapter.sh", "sort-and-filter")
    assert r.returncode == 0, r.stderr
    assert "make-project" in r.stdout and "copy-inventory" in r.stdout and "Chapter sort-and-filter starts here" in r.stdout
    assert (work / "project" / "inventory.csv").exists() and not (work / "project" / "low-stock.csv").exists()
    r = sh(root, home, "lab/check.sh", "low-stock-written")
    assert r.returncode == 1 and "Not yet" in r.stdout
    steps_in(work, book, "sort-low-first", "write-low-stock", "no-gadgets-low")
    assert sh(root, home, "lab/check.sh", "sort-and-filter").stdout == "Passed: low-stock-written\n"

    r = sh(root, home, "lab/chapter.sh", "files-and-folders")
    assert r.returncode == 0 and not (work / "project").exists()                     # a fresh start
    r = sh(root, home, "lab/stop.sh")
    assert r.returncode == 0 and "nothing to stop" in r.stdout and work.is_dir()

    r = sh(root, home, "lab/chapter.sh", "no-such-chapter")
    assert r.returncode == 1 and "There's no chapter no-such-chapter" in r.stderr
    r = sh(root, home, "lab/check.sh")
    assert r.returncode == 1 and "The checks: project-has-readme, low-stock-written" in r.stderr


def test_a_setup_step_that_fails_stops_the_chapter(tmp_path):
    root = sampler(tmp_path)
    (root / "examples" / "copy-inventory.sh").write_text("cp data/missing.csv project/\n")
    assert cli.main(["lab", "--book", str(root), "--write"]) == 0
    home = tmp_path / "home"
    home.mkdir()
    assert sh(root, home, "lab/start.sh").returncode == 0
    r = sh(root, home, "lab/chapter.sh", "sort-and-filter")
    assert r.returncode == 1 and "Step copy-inventory ended with exit code 1, not 0." in r.stderr


def test_the_scripts_are_generated_never_typed(tmp_path, capsys):
    root = sampler(tmp_path)
    assert cli.main(["lab", "--book", str(root)]) == 0
    assert "lab/start.sh, chapter.sh, check.sh and stop.sh are up to date" in capsys.readouterr().out
    text = (root / "chapters" / "02-sort-and-filter.md").read_text()
    (root / "chapters" / "02-sort-and-filter.md").write_text(text.replace("setup: [make-project, copy-inventory]",
                                                                          "setup: [make-project]"))
    assert cli.main(["lab", "--book", str(root)]) == 1
    assert "lab/chapter.sh is out of date: run re-check lab --write" in capsys.readouterr().err
    python_book = Path(__file__).parent / "fixtures" / "primer-chapter"
    assert cli.main(["lab", "--book", str(python_book)]) == 0
    assert "not a terminal book" in capsys.readouterr().out


def test_a_k3s_books_scripts_pin_every_tool_for_the_readers_platform(tmp_path):
    root = k3s_book(tmp_path)
    p = pinned(root)
    book = bookfmt.load_book(root)
    found = labscripts.scripts(book)
    start, chapter = found["lab/start.sh"], found["lab/chapter.sh"]
    for platform in ("linux-amd64", "linux-arm64", "darwin-arm64"):
        entry = p.tools["k3d"]["platforms"][platform]
        assert f"k3d-{platform}) echo {entry['url']} {entry['sha256']} ;;" in start
        assert f"kubectl-{platform})" in start
    image = p.tools["k3s"]["image"]
    assert f"--image {image['ref']}@{image['digest']}" in chapter and "fetch_tool k3d" in start
    assert "--disable=traefik@server:0" in start and 'cluster delete "$cluster"' in found["lab/stop.sh"]
    for rel, text in found.items():
        path = tmp_path / rel.replace("/", "-")
        path.write_text(text)
        assert subprocess.run(["sh", "-n", str(path)], capture_output=True, timeout=SECONDS).returncode == 0, rel
    (root / stack.STACK).unlink()
    with pytest.raises(labscripts.LabError):
        labscripts.scripts(bookfmt.load_book(root))


def test_every_script_is_posix_sh(tmp_path):
    root = sampler(tmp_path)
    for path in sorted((root / "lab").iterdir()):
        for shell in ("sh", "dash", "bash"):
            if shutil.which(shell):
                r = subprocess.run([shell, "-n", str(path)], capture_output=True, text=True, timeout=SECONDS)
                assert r.returncode == 0, (shell, path.name, r.stderr)
        assert path.read_text().startswith("#!/bin/sh\n# Generated by `re-check lab --write`")


def test_a_terminal_books_front_page_says_how_to_work_through_it_locally():
    from re_standards import readme
    text = readme.readme(bookfmt.load_book(SAMPLER))
    assert "## Work through it on your own machine" in text and "## Run the examples" not in text
    assert "lab/chapter.sh files-and-folders" in text and "uv venv" not in text
    python = readme.readme(bookfmt.load_book(Path(__file__).parent / "fixtures" / "primer-chapter"))
    assert "## Run the examples" in python and "lab/start.sh" not in python


def test_setup_never_names_a_background_step(tmp_path):
    root = tmp_path / "book"
    shutil.copytree(SAMPLER, root)
    path = root / "chapters" / "02-sort-and-filter.md"
    text = path.read_text().replace("setup: [make-project, copy-inventory]", "setup: [make-project, copy-inventory, follow-log]")
    # follow-log moves to the first chapter, so the second can name it
    text = text.replace("[Step: follow-log](../examples/follow-log.sh)\n\n", "")
    path.write_text(text)
    first = root / "chapters" / "01-files-and-folders.md"
    first.write_text(first.read_text() + "\n[Step: follow-log](../examples/follow-log.sh)\n")
    assert any("which runs in the background" in p for p in bookfmt.load_book(root).problems)
