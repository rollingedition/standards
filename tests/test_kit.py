"""The book kit (kit.py, `re-check kit`) and what `re-check style` holds a draft to with it."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from re_standards import bookfmt, cli, kit, style
from bookkit import make_book


def draft(root: Path, **kw) -> Path:
    make_book(root, **kw)
    (root / "book.toml").write_text((root / "book.toml").read_text().replace('status = "live"', 'status = "draft"'))
    return root


def kit_problems(root: Path) -> list[str]:
    return [p for p in style.check_style(bookfmt.load_book(root)) if "kit:" in p or "W-17" in p]


# ---------------------------------------------------------------- the files


def test_the_kit_is_generated_from_config(tmp_path):
    files = kit.files()
    assert set(files) == {".gitignore", "examples/lib/__init__.py", "recordings/recorded.py"}
    ignore = files[".gitignore"].splitlines()
    assert "__pycache__/" in ignore and "/scratch/" in ignore and ".venv/" in ignore
    lib = files["examples/lib/__init__.py"]
    assert "THREADS = 2" in lib and "SEED = 0" in lib and '"OMP_NUM_THREADS",' in lib and "import torch" not in lib
    assert kit.files({**kit.load_config(), "threads": 4, "seed": 7})["examples/lib/__init__.py"].count("THREADS = 4") == 1


def test_lib_fixes_threads_and_seeds_before_anything_else_loads(tmp_path):
    draft(tmp_path / "b")
    kit.write(tmp_path / "b")
    env = {k: v for k, v in os.environ.items() if not k.endswith("_THREADS") and k != "TOKENIZERS_PARALLELISM"}
    code = ("import lib, os, random\nprint(os.environ['OMP_NUM_THREADS'], os.environ['TOKENIZERS_PARALLELISM'], "
            "lib.THREADS, lib.SEED, random.random())")
    runs = [subprocess.run([sys.executable, "-c", code], cwd=tmp_path / "b" / "examples", env=env, capture_output=True,
                           text=True, check=True).stdout for _ in range(2)]
    assert runs[0] == runs[1] and runs[0].startswith("2 false 2 0 ")
    kept = subprocess.run([sys.executable, "-c", "import lib, os; print(os.environ['OMP_NUM_THREADS'])"],
                          cwd=tmp_path / "b" / "examples", env=dict(env, OMP_NUM_THREADS="1"), capture_output=True,
                          text=True, check=True).stdout
    assert kept == "1\n"                                     # a runner's own setting stays


def test_write_makes_the_kit_and_numbered_chapters_and_never_touches_one_that_exists(tmp_path):
    root = draft(tmp_path / "b")
    (root / ".gitignore").write_text("models/\n__pycache__/\n")
    written, problems = kit.write(root, ["first-steps", "a-catalog-you-can-test", "lineage"])
    assert problems == []
    assert written == [".gitignore", "examples/lib/__init__.py", "recordings/recorded.py",
                       "narration/first-steps.toml", "chapters/02-a-catalog-you-can-test.md",
                       "narration/a-catalog-you-can-test.toml", "chapters/03-lineage.md", "narration/lineage.toml"]
    ignore = (root / ".gitignore").read_text()
    assert ignore.startswith("models/\n__pycache__/\n") and ignore.count("__pycache__/") == 1 and "/scratch/" in ignore
    assert (root / "chapters" / "01-first-steps.md").read_text().startswith("---\nchapter_id: first-steps\n")  # kept
    assert (root / "chapters" / "02-a-catalog-you-can-test.md").read_text() == (
        "---\nchapter_id: a-catalog-you-can-test\n---\n\n# A catalog you can test\n")
    book = bookfmt.load_book(root)
    assert [c.chapter_id for c in book.chapters] == ["first-steps", "a-catalog-you-can-test", "lineage"] and not book.problems
    assert kit.check(root) == []
    again, _ = kit.write(root, ["first-steps", "a-catalog-you-can-test", "lineage"])
    assert again == []                                       # nothing to do twice
    lib = root / "examples" / "lib" / "__init__.py"
    lib.write_text(lib.read_text().replace("THREADS = 2", "THREADS = 8"))
    assert kit.check(root) == ["examples/lib/__init__.py isn't the kit's: it's generated, so the book's own code goes "
                               "beside it; re-check kit --book . --write writes it again"]
    assert kit.write(root)[0] == ["examples/lib/__init__.py"] and kit.check(root) == []
    lib.write_text("def load():\n    return 1\n")             # the book's own code, never overwritten
    message = ("examples/lib/__init__.py is the book's own, not the kit's: move its code into a module beside it, "
               "delete it, and run re-check kit --book . --write")
    assert kit.check(root) == [message] and kit.write(root) == ([], [message])
    assert lib.read_text() == "def load():\n    return 1\n"


def test_write_refuses_a_plan_that_disagrees_with_the_chapters_there(tmp_path):
    root = draft(tmp_path / "b")
    _, problems = kit.write(root, ["intro", "first-steps", "Bad ID"])
    assert "chapters/01-intro.md: another chapter is numbered 01: pass every chapter in the plan's order" in problems
    assert "chapters/01-first-steps.md holds chapter first-steps, which the plan puts 2: rename it to chapters/02-first-steps.md" in problems
    assert "--chapter 'Bad ID': a chapter ID is lowercase words joined by hyphens" in problems
    assert not (root / "chapters" / "01-intro.md").exists()


def test_re_check_kit_fails_a_draft_and_only_tells_a_released_book(tmp_path, capsys):
    root = draft(tmp_path / "b")
    assert cli.main(["kit", "--book", str(root)]) == 1
    assert ".gitignore is missing: re-check kit --book . --write" in capsys.readouterr().err
    assert cli.main(["kit", "--book", str(root), "--write", "--chapter", "first-steps"]) == 0
    assert "wrote  examples/lib/__init__.py" in capsys.readouterr().out
    assert cli.main(["kit", "--book", str(root)]) == 0
    live = make_book(tmp_path / "live")
    assert cli.main(["kit", "--book", str(live)]) == 0
    assert "warning(s)" in capsys.readouterr().err
    assert cli.main(["kit", "--book", str(root), "--chapter", "x"]) == 1


# ---------------------------------------------------------------- recordings: into scratch, then into the book


def recording(root: Path, body: str) -> subprocess.CompletedProcess:
    (root / "recordings" / "teacher.py").write_text(
        "from recorded import Recording\n\n"
        "with Recording('teacher-labels', model='an-org/a-model', model_version='abc123', prompt_sha256='f00d') as out:\n"
        + body)
    return subprocess.run([sys.executable, "recordings/teacher.py"], cwd=root, capture_output=True, text=True,
                          env=dict(os.environ, RE_SCRATCH=str(root.parent / "scratch")))


def test_a_recording_writes_into_scratch_and_reaches_the_book_only_when_it_finishes(tmp_path):
    root = draft(tmp_path / "b")
    kit.write(root)
    failed = recording(root, "    (out / 'labels.jsonl').write_text('{}')\n    raise SystemExit('stopped at row 168')\n")
    assert failed.returncode != 0
    assert not (root / "examples" / "data" / "recorded").exists()
    assert (tmp_path / "scratch" / "recordings" / "teacher-labels" / "labels.jsonl").exists()   # left to read
    done = recording(root, "    (out / 'labels.jsonl').write_text('{}')\n    (out / 'parts').mkdir()\n"
                           "    (out / 'parts' / 'a.txt').write_text('a')\n")
    assert done.returncode == 0, done.stderr
    folder = root / "examples" / "data" / "recorded" / "teacher-labels"
    manifest = json.loads((folder / "manifest.json").read_text())
    assert manifest["script"] == "recordings/teacher.py" and manifest["outputs"] == ["labels.jsonl", "parts/a.txt"]
    assert manifest["model"] == "an-org/a-model" and len(manifest["created"]) == 10
    assert style.check_recordings(root) == []
    assert sorted(p.name for p in folder.parent.iterdir()) == ["teacher-labels"]           # nothing half-made beside it
    again = recording(root, "    (out / 'labels.jsonl').write_text('{\"v\": 2}')\n")
    assert again.returncode == 0 and not (folder / "parts").exists()                        # replaced whole


def test_a_recording_that_writes_into_the_book_itself_is_a_kit_problem_on_a_draft(tmp_path):
    root = draft(tmp_path / "b")
    kit.write(root)
    (root / "recordings" / "old.py").write_text("from pathlib import Path\nOUT = Path('examples/data/recorded/x')\n")
    (root / "recordings" / "new.py").write_text("from recorded import Recording\nNAME = 'examples/data/recorded'\n")
    found = kit.recordings_problems(root)
    assert found == ["recordings/old.py:2: kit: a recording writes into scratch while it runs, and into "
                     "examples/data/recorded only when it finishes: use `with Recording(...) as out:` from "
                     "recordings/recorded.py"]


# ---------------------------------------------------------------- what re-check style holds a draft to


def test_a_draft_needs_numbered_chapter_files_and_its_gitignore(tmp_path):
    root = draft(tmp_path / "b")
    kit.write(root)
    (root / ".gitignore").write_text("models/\n")
    (root / "chapters" / "01-first-steps.md").rename(root / "chapters" / "first-steps.md")
    found = kit_problems(root)
    assert any(p.startswith("chapters/first-steps.md: kit: name chapter files chapters/NN-{chapter_id}.md") and
               p.endswith("so chapters/01-first-steps.md, or the number the plan gives it") for p in found)
    assert ".gitignore: kit: ignore __pycache__/ and scratch/, so bytecode and scratch files never reach the draft: " \
           "re-check kit --book . --write" in found
    (root / "chapters" / "first-steps.md").rename(root / "chapters" / "03-first-steps.md")      # a gap
    assert any("chapters/03-first-steps.md: kit:" in p for p in kit_problems(root))
    (root / "chapters" / "03-first-steps.md").rename(root / "chapters" / "01-first-steps.md")
    kit.write(root)
    assert kit_problems(root) == []


def test_a_draft_that_didnt_start_from_the_kit_keeps_its_rules_and_re_check_kit_says_what_it_lacks(tmp_path):
    """A member's own book is a draft with its own examples/lib and no kit: style holds it to what it was held to."""
    root = draft(tmp_path / "b", examples={"walk": ("import numpy\nimport os\nprint(os.listdir('.'))\n", None)})
    (root / "examples" / "lib").mkdir()
    (root / "examples" / "lib" / "__init__.py").write_text("SEED = 0\n")
    (root / "chapters" / "01-first-steps.md").rename(root / "chapters" / "first-steps.md")
    assert kit_problems(root) == [] and not kit.has_kit(root)
    assert ".gitignore is missing: re-check kit --book . --write" in kit.check(root)


def test_a_released_book_is_never_held_to_the_kit(tmp_path):
    root = make_book(tmp_path / "live", examples={"walk": ("import os, time\nfor f in os.listdir('.'):\n    print(f, time.time())\n", None)})
    (root / "chapters" / "01-first-steps.md").rename(root / "chapters" / "first-steps.md")
    assert kit_problems(root) == []


LINT_HITS = {
    "timing": ("import lib\nimport time\nstart = time.perf_counter()\nprint('took', time.perf_counter() - start)\n",
               ["3: W-17: time.perf_counter reads the clock", "4: W-17: time.perf_counter reads the clock"]),
    "aliased": ("import lib\nfrom datetime import datetime as dt\nfrom time import monotonic\nprint(dt.now(), monotonic())\n",
                ["4: W-17: datetime.datetime.now reads", "4: W-17: time.monotonic reads"]),
    "memory": ("import lib\nimport tracemalloc\ntracemalloc.start()\n", ["3: W-17: tracemalloc.start reads"]),
    "listing": ("import lib\nimport os\nfor name in os.listdir('data'):\n    print(name)\n",
                ["3: W-17: os.listdir gives its results in whatever order"]),
    "globbed": ("import lib\nfrom pathlib import Path\nfiles = Path('data').glob('*.csv')\nprint(list(files))\n",
                ["3: W-17: .glob() gives its results"]),
    "a-set": ("import lib\nseen = {1, 2}\nseen.add(3)\nprint(seen)\nprint(', '.join({'a', 'b'}))\n",
              ["4: W-17: a set's order", "5: W-17: a set's order"]),
    "popped": ("import lib\nleft = set(range(3))\nprint(left.pop())\n", ["3: W-17: set.pop() takes"]),
    "workers": ("import lib\nfrom concurrent.futures import ThreadPoolExecutor, as_completed\n"
                "with ThreadPoolExecutor(2) as ex:\n    for f in as_completed([ex.submit(abs, -1)]):\n        print(f.result())\n",
                ["4: W-17: concurrent.futures.as_completed gives"]),
    "numpy-first": ("import numpy as np\nimport lib\nprint(np.arange(3).sum())\n",
                    ["1: W-17: import from lib first (`import lib`, or `from lib.x import y`), so threads and seeds are "
                     "fixed before numpy loads"]),
    "no-lib": ("from sklearn.linear_model import LinearRegression\nprint(LinearRegression())\n",
               ["1: W-17: import from lib first"]),
}

LINT_CLEAN = """import lib
import os
import time
from pathlib import Path
import numpy as np

names = sorted(os.listdir("data"))
count = len(set(names))
files = Path("data").glob("*.csv")
for f in sorted(files):
    print(f.name)
print(sorted(p.name for p in Path("data").iterdir()))
print("a" in set(names), sorted(set(names) - {"b"}), max({1, 2}))
labels = {n: 1 for n in set(names)}
print(sorted({x for x in set(names)}))
time.sleep(0)
"""


@pytest.mark.parametrize("name", sorted(LINT_HITS))
def test_the_examples_lint_finds_timings_unordered_results_and_imports_before_lib(tmp_path, name):
    code, wanted = LINT_HITS[name]
    root = draft(tmp_path / "b", examples={name: (code, None)})
    found = kit.lint_examples(root)
    for w in wanted:
        assert any(p.startswith(f"examples/{name}.py:{w}") for p in found), (w, found)
    assert len(found) == len(wanted), found


def test_the_examples_lint_leaves_sorted_counted_and_tested_results_alone(tmp_path):
    root = draft(tmp_path / "b", examples={"clean": (LINT_CLEAN, None)})
    (root / "examples" / "lib").mkdir()
    (root / "examples" / "lib" / "store.py").write_text("import numpy\nfrom pathlib import Path\n\ndef files(d):\n"
                                                        "    return sorted(Path(d).rglob('*.parquet'))\n")
    (root / "examples" / "data").mkdir()
    (root / "examples" / "data" / "make.py").write_text("import time\nprint(time.time())\n")   # data isn't linted
    assert kit.lint_examples(root) == []


def test_the_lint_reaches_shared_modules_and_reports_through_style_on_a_draft(tmp_path):
    root = draft(tmp_path / "b")
    kit.write(root)
    (root / "examples" / "lib" / "timer.py").write_text("import time\n\ndef now():\n    return time.time()\n")
    found = kit_problems(root)
    assert [p for p in found if "W-17" in p] == [
        "examples/lib/timer.py:4: W-17: time.time reads the clock or the memory in use, so what an example prints with "
        "it changes from run to run and under load: print only what the inputs decide, and leave speed to the prose or "
        "a recording"]
    assert style.check_style(bookfmt.load_book(root), skip={"W-17"}) == [
        p for p in style.check_style(bookfmt.load_book(root)) if "W-17" not in p]
