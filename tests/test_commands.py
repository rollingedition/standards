"""The PTY runner (commands.py) on plain shell steps: a login shell in a terminal, read through its OSC 133 markers;
waits, masks, tabs and checks; determinism between runs; recording; and `re-check commands`. Every test is bounded: each
step has its own small limit, and an alarm stops a test that would still hang."""
import os
import shutil
import signal
from pathlib import Path

import pytest

from re_standards import bookfmt, cli, commands, examples, steps

SAMPLER = Path(__file__).parent / "fixtures" / "terminal-sampler"
LIMIT_SECONDS = 90


@pytest.fixture(autouse=True)
def bounded():
    """No test here runs past LIMIT_SECONDS, whatever a shell does."""
    def stop(signum, frame):
        raise TimeoutError(f"a runner test ran past {LIMIT_SECONDS} s")
    previous = signal.signal(signal.SIGALRM, stop)
    signal.alarm(LIMIT_SECONDS)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


@pytest.fixture(autouse=True)
def network(monkeypatch):
    """Where the kernel won't block the network for a user, run with it open, as RE_COMMANDS_ALLOW_NETWORK=1 does."""
    if not examples.can_block_network():
        monkeypatch.setenv("RE_COMMANDS_ALLOW_NETWORK", "1")


def sampler(tmp_path: Path) -> Path:
    root = tmp_path / "sampler"
    shutil.copytree(SAMPLER, root)
    return root


CHAPTER = """---
chapter_id: one
---
# One

## Only {#only}

{links}
"""


def one_chapter(tmp_path: Path, files: dict[str, str], outs: dict[str, str] | None = None) -> bookfmt.Book:
    """A book of one chapter whose steps are `files`, by ID, each embedded in order; a check is labelled as one."""
    root = sampler(tmp_path)
    for p in (root / "chapters").glob("*.md"):
        p.unlink()
    for p in (root / "examples").glob("*.sh"):
        p.unlink()
    links = []
    for sid, text in files.items():
        (root / "examples" / f"{sid}.sh").write_text(text)
        label = "Check" if text.startswith("#| check") else "Step"
        links.append(f"[{label}: {sid}](../examples/{sid}.sh)")
    for sid, out in (outs or {}).items():
        (root / "examples" / f"{sid}.out").write_text(out)
    (root / "chapters" / "01-one.md").write_text(CHAPTER.replace("{links}", "\n\n".join(links)))
    book = bookfmt.load_book(root)
    assert book.problems == [], book.problems
    return book


def run(book: bookfmt.Book, **kw) -> commands.ChapterRun:
    return commands.run_chapter(book, book.chapters[0].chapter_id, commands.backend_for(book), **kw)


def verdicts(r: commands.ChapterRun) -> list[tuple[str, str]]:
    return [(x.step_id, x.verdict) for x in r.results if x.phase == "chapter"]


# ---------------------------------------------------------------- what a terminal shows


def test_screen_text_is_what_a_terminal_shows():
    raw = b"\x1b[1mbold\x1b[0m\r\n 50%\r100%\r\nab\bc\x1b]0;title\x07\r\nwide   \r\n\r\n"
    assert commands.screen_text(raw) == "bold\n100%\nac\nwide\n"


# ---------------------------------------------------------------- the sampler, end to end


def test_the_sampler_records_then_passes_and_a_change_fails_it(tmp_path, capsys):
    root = sampler(tmp_path)
    assert cli.main(["commands", "--book", str(root)]) == 0                   # as committed, recorded
    capsys.readouterr()
    for out in (root / "examples").glob("*.out"):
        out.unlink()
    assert cli.main(["commands", "--book", str(root)]) == 1                   # nothing recorded yet
    assert "no recorded output; record it with re-check commands --record" in capsys.readouterr().err
    assert cli.main(["commands", "--book", str(root), "--record"]) == 0
    out = capsys.readouterr().out
    assert "recorded the output of 7 steps and 0 checks" in out and "2 runs of each chapter" in out
    assert (root / "examples" / "make-project.out").read_text() == "README.md\n"
    assert (root / "examples" / "sort-low-first.out").read_text() == \
        "widget-mini,2\nsprocket,4\nflange,7\nwidget,12\ngadget,30\n"
    assert (root / "examples" / "stamp-the-check.out").read_text().startswith("checked at 20")
    assert (root / "examples" / "no-gadgets-low.out").read_text() == ""
    assert not (root / "examples" / "follow-log.out").exists()                # a background step is never compared
    report = tmp_path / "report.json"
    assert cli.main(["commands", "--book", str(root), "--report", str(report)]) == 0
    assert "10 of 10 steps and checks pass" in capsys.readouterr().out
    import json
    data = json.loads(report.read_text())
    assert data["outcome"] == "passed" and [c["chapter"] for c in data["chapters"]] == ["files-and-folders",
                                                                                        "sort-and-filter"]
    (root / "examples" / "data" / "inventory.csv").write_text("item,quantity\nwidget,1\n")
    assert cli.main(["commands", "--book", str(root), "--chapter", "sort-and-filter"]) == 1
    err = capsys.readouterr().err
    assert "step sort-low-first prints something other than its recorded output" in err
    assert "-widget-mini,2" in err and "+widget,1" in err


def test_a_chapter_starts_fresh_from_its_setup(tmp_path):
    book = bookfmt.load_book(SAMPLER)
    r = commands.run_chapter(book, "sort-and-filter", commands.backend_for(book))
    assert [(x.step_id, x.phase, x.verdict) for x in r.results[:2]] == [
        ("make-project", "setup", "ran"), ("copy-inventory", "setup", "ran")]
    assert ("low-stock-written", "passed") in verdicts(r)
    before = [x for x in r.results if x.phase == "before"]
    assert [(x.step_id, x.verdict) for x in before] == [("low-stock-written", "not-yet")]


# ---------------------------------------------------------------- one step at a time


def test_a_paste_runs_whole_and_reports_each_commands_exit_code(tmp_path):
    book = one_chapter(tmp_path, {
        "several": "mkdir -p deep/er\ncd deep/er\ncat <<EOF\nhere doc\nEOF\npwd | sed 's#.*/work#WORK#'\n",
        "folder-check": "#| check\ntest \"$(basename \"$PWD\")\" = er\n",
        "fails-midway": "false\necho still here\n",
    }, {"several": "here doc\nWORK/deep/er\n"})
    r = run(book, check_before=False)
    assert verdicts(r) == [("several", "same"), ("folder-check", "passed"), ("fails-midway", "error")]
    several = r.results[0]
    assert several.exit_codes == [0, 0, 0, 0]
    midway = r.results[2]
    assert midway.exit_codes == [1, 0] and midway.output == "still here\n" and "exit codes 1, 0" in midway.why


def test_a_step_past_its_limit_is_interrupted_and_stops_the_chapter(tmp_path):
    book = one_chapter(tmp_path, {"waits-for-input": "#| timeout: 1\nread answer\n", "after": "echo after\n"})
    r = run(book)
    assert verdicts(r) == [("waits-for-input", "timeout"), ("after", "not-run")]
    assert r.results[0].seconds < 5 and "ran past 1 s" in r.results[0].why


def test_a_wait_polls_until_it_passes_or_the_limit(tmp_path):
    book = one_chapter(tmp_path, {
        "start-later": "#| wait: test -f ready\n#| compare: none\n( for i in 1 2 3 4 5 6 7 8; do :; done; touch ready ) &\n",
        "never-ready": "#| timeout: 2\n#| wait: test -f never\ntrue\n",
    })
    r = run(book)
    assert verdicts(r) == [("start-later", "ran"), ("never-ready", "timeout")]
    assert "waited for `test -f never` past 2 s" in r.results[1].why


def test_expected_exit_codes_and_compare_modes(tmp_path):
    book = one_chapter(tmp_path, {
        "missing": "#| expect-exit: 2\nls no-such-file\n",
        "some-lines": "#| compare: lines\nprintf 'a\\nnoise\\nb\\n'\n",
        "masked": "#| mask: uid\necho \"id $(cat /proc/sys/kernel/random/uuid)\"\n",
    }, {"missing": "ls: cannot access 'no-such-file': No such file or directory\n", "some-lines": "a\nb\n",
        "masked": "id 00000000-0000-0000-0000-000000000000\n"})
    assert verdicts(run(book)) == [("missing", "same"), ("some-lines", "same"), ("masked", "same")]


def test_a_check_that_passes_before_its_section_checks_nothing(tmp_path):
    book = one_chapter(tmp_path, {"noop": "true\n", "always": "#| check\ntrue\n"})
    r = run(book)
    assert any("check always passes before its section's steps run" in p for p in r.problems)


def test_a_check_that_doesnt_pass_says_its_hint(tmp_path):
    book = one_chapter(tmp_path, {"noop": "#| compare: none\ntrue\n", "file-exists": "#| check\n#| hint: Write it first.\ntest -f x\n"})
    r = run(book)
    assert verdicts(r) == [("noop", "ran"), ("file-exists", "not-yet")]
    assert r.results[-1].why == "Write it first."
    assert any("check file-exists doesn't pass after its section's steps" in p for p in r.problems)


def test_the_network_is_blocked_for_every_step(tmp_path):
    if not examples.can_block_network():
        pytest.skip("this kernel doesn't let a user block the network")
    book = one_chapter(tmp_path, {"interfaces": "awk 'NR > 2 { print $1 }' /proc/net/dev\n"}, {"interfaces": "lo:\n"})
    assert verdicts(run(book)) == [("interfaces", "same")]


def test_a_step_sees_only_the_runners_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("RE_SECRET_TOKEN", "do-not-leak")
    book = one_chapter(tmp_path, {"env": "env | grep -c -e TOKEN -e do-not-leak || true\n"
                                         "echo \"$TZ $LANG $NO_COLOR $COLUMNS $LINES\"\n"},
                       {"env": "0\nUTC C.UTF-8 1 120 40\n"})
    r = run(book)
    assert verdicts(r) == [("env", "same")], r.results[0]


# ---------------------------------------------------------------- determinism and recording


def test_recording_refuses_what_prints_differently_from_run_to_run(tmp_path, capsys):
    book = one_chapter(tmp_path, {"random": "cat /proc/sys/kernel/random/uuid\n"})
    assert cli.main(["commands", "--book", str(book.root), "--record"]) == 1
    assert "step random prints differently from run to run" in capsys.readouterr().err
    assert not (book.root / "examples" / "random.out").exists()


def test_a_book_with_a_stack_needs_its_backend(tmp_path, capsys):
    root = sampler(tmp_path)
    (root / "book.toml").write_text((root / "book.toml").read_text().replace('stack = "none"', 'stack = "k3s"'))
    assert cli.main(["commands", "--book", str(root)]) == 1
    assert "need k3s pinned in examples/stack.toml" in capsys.readouterr().err
    with pytest.raises(commands.CommandsError):
        commands.backend_for(bookfmt.load_book(root))


def test_a_book_with_no_steps_has_nothing_to_run(capsys):
    assert cli.main(["commands", "--book", str(Path(__file__).parent / "fixtures" / "primer-chapter")]) == 0
    assert "no steps or checks" in capsys.readouterr().out


def test_no_shell_is_left_running(monkeypatch):
    """Every process a chapter's tabs started is gone once it ends, a background `tail -f` included."""
    sessions = []
    start = commands.Tab.__init__

    def recorded(self, *args, **kw):
        start(self, *args, **kw)
        sessions.append(self.proc.pid)
    monkeypatch.setattr(commands.Tab, "__init__", recorded)
    book = bookfmt.load_book(SAMPLER)
    commands.run_chapter(book, "sort-and-filter", commands.backend_for(book))
    assert len(sessions) == 2                                   # the main tab and the log's
    left = []
    for entry in Path("/proc").iterdir():
        if entry.name.isdigit():
            try:
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            except OSError:
                continue
            if int(fields[3]) in sessions and fields[0] != "Z":
                left.append(entry.name)
    assert left == []


def test_a_flood_of_output_is_cut_short(tmp_path, monkeypatch):
    monkeypatch.setitem(commands.settings(), "output_max_bytes", 20000)
    book = one_chapter(tmp_path, {"flood": "#| timeout: 30\n#| compare: none\nyes | head -c 400000\n"})
    r = run(book)
    assert verdicts(r) == [("flood", "error")] and "its output passed 20,000 bytes" in r.results[0].why
    assert r.results[0].seconds < 10
