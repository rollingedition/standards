"""Examples side by side (`re-check examples --jobs`): packed by each one's time in the last run, the slow ones and the
ones with no time alone, and the same results in the same order as one at a time."""
import json
import threading
import time

import pytest

from re_standards import bookfmt, cli, examples
from bookkit import CHAPTER, make_book


def tiny_book(root, n: int = 4):
    """A book of `n` examples, each linked from its own paragraph, each printing its name."""
    links = "\n\n".join(f"[Example: ex{i}](../examples/ex{i}.py)" for i in range(n))
    chapter = CHAPTER.replace("[Example: hello](../examples/hello.py)", links)
    found = make_book(root, chapter=chapter, examples={f"ex{i}": (f'print("ex{i}")\n', f"ex{i}\n") for i in range(n)})
    (found / "examples" / ".python-version").write_text("3.12.15\n")
    (found / "examples" / "requirements.txt").write_text("")
    return found


def test_the_plan_shares_what_fits_within_the_limit_longest_first_and_leaves_the_rest_alone():
    seconds = {"a": 2.0, "b": 25.0, "c": 31.0, "d": 0.4, "e": 0.0}
    shared, alone = examples.plan_side_by_side(["a", "b", "c", "d", "e", "new"], seconds, 2, 120)
    # beside one other an example may take twice its time: 30 s at most keeps that within half the 120 s limit
    assert shared == ["b", "a", "d", "e"]
    assert alone == ["c", "new"]                                  # too slow to share, and never timed
    shared, alone = examples.plan_side_by_side(["a", "b", "c", "d"], seconds, 4, 120)
    assert shared == ["a", "d"] and alone == ["b", "c"]           # four at once: 15 s at most
    assert examples.plan_side_by_side(["a"], {"a": True}, 2, 120) == ([], ["a"])   # not a time


def test_one_job_runs_every_example_in_turn_as_before():
    order = []
    out = examples.side_by_side(["a", "b", "c"], lambda eid: order.append(eid) or eid.upper(), 1, {"a": 1, "b": 1, "c": 1}, 120)
    assert out == ["A", "B", "C"] and order == ["a", "b", "c"]


def test_side_by_side_runs_up_to_jobs_at_once_the_slow_ones_alone_and_answers_in_order():
    lock, running, seen = threading.Lock(), set(), {}

    def run(eid):
        with lock:
            running.add(eid)
            seen[eid] = set(running)
        time.sleep(0.05)
        with lock:
            running.discard(eid)
        return eid

    ids = ["a", "b", "c", "d", "slow", "new"]
    seconds = {"a": 1, "b": 1, "c": 1, "d": 1, "slow": 100}
    assert examples.side_by_side(ids, run, 3, seconds, 120) == ids
    assert max(len(s) for s in seen.values()) == 3                     # three at once, never more
    assert seen["slow"] == {"slow"} and seen["new"] == {"new"}         # each alone


def test_a_book_s_examples_give_the_same_results_side_by_side(tmp_path):
    root = tiny_book(tmp_path / "book")
    book = bookfmt.load_book(root)
    one, runtime = examples.run_examples(book, examples.HostBackend())
    seconds = examples.recorded_seconds(examples.results_json(one, runtime))
    assert set(seconds) == set(book.examples)
    two, _ = examples.run_examples(book, examples.HostBackend(), jobs=3, seconds=seconds)
    assert [r.example_id for r in two] == [r.example_id for r in one] == sorted(book.examples)
    assert [(r.passing, r.stdout) for r in two] == [(r.passing, r.stdout) for r in one] and all(r.passing for r in two)
    only, _ = examples.run_examples(book, examples.HostBackend(), only=["ex2", "ex0"], jobs=2, seconds=seconds)
    assert [r.example_id for r in only] == ["ex0", "ex2"]


def test_recorded_seconds_come_from_a_report_or_an_edition_s_examples_json():
    report = {"examples": [{"example_id": "a", "seconds": 1.5}, {"example_id": "b", "seconds": 0},
                           {"example_id": "c", "carried": {"edition": "2026.11.1"}, "seconds": 3},
                           {"example_id": "d"}, {"seconds": 2}, "nope", {"example_id": "e", "seconds": "2"},
                           {"example_id": "f", "seconds": True}]}
    assert examples.recorded_seconds(report) == {"a": 1.5, "c": 3.0}
    assert examples.recorded_seconds(None) == {} == examples.recorded_seconds({"examples": None})


def test_the_cli_runs_side_by_side_from_an_earlier_report(tmp_path, capsys):
    root = tiny_book(tmp_path / "book")
    first, second = tmp_path / "first.json", tmp_path / "second.json"
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--report", str(first)]) == 0
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--jobs", "4", "--seconds", str(first),
                     "--report", str(second)]) == 0
    a, b = json.loads(first.read_text()), json.loads(second.read_text())
    assert [(e["example_id"], e["stdout"], e["passing"]) for e in a["examples"]] == \
        [(e["example_id"], e["stdout"], e["passing"]) for e in b["examples"]]
    capsys.readouterr()
    assert cli.main(["examples", "--book", str(root), "--backend", "host", "--jobs", "2", "--seconds",
                     str(tmp_path / "missing.json")]) == 1
    assert "isn't a report of an earlier run: No such file or directory" in capsys.readouterr().err


@pytest.mark.parametrize("jobs", [0, -1])
def test_no_jobs_is_one_job(tmp_path, jobs):
    root = tiny_book(tmp_path / "book", 2)
    results, _ = examples.run_examples(bookfmt.load_book(root), examples.HostBackend(), jobs=jobs, seconds={"ex0": 1, "ex1": 1})
    assert [r.passing for r in results] == [True, True]
