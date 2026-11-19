"""The pull request's `commands` job: book-commands.yml, the reusable workflow a terminal book's checks.yml calls, and the
template's block that only a terminal book's checks.yml carries. Every other book's workflows are exactly as before."""
import re
from pathlib import Path

import yaml

from re_standards import bookfmt, readme

FIXTURES = Path(__file__).parent / "fixtures"
REUSABLE = readme.TEMPLATES.parent / ".github" / "workflows" / "book-commands.yml"
TEMPLATE = readme.TEMPLATES / "book" / "workflows" / "checks.yml"
TERMINAL = {"slug": "a-book", "lab": {"kind": "terminal", "stack": "k3s"}}


def test_a_python_books_workflows_are_the_template_without_its_terminal_block():
    """Byte for byte what the template made before it had the block: the block's lines, markers included, are gone."""
    before = TEMPLATE.read_text()
    while "  # {terminal}\n" in before:                   # each block, its markers included
        begin = before.index("  # {terminal}\n")
        end = before.index("  # {/terminal}\n") + len("  # {/terminal}\n")
        before = before[:begin] + before[end:]
    cfg = readme.load_config()
    want = before.replace("{org}", "rollingedition").replace("{weekly_cron}", readme.weekly_cron("a-book", cfg))
    for manifest in (None, {"slug": "a-book"}, {"slug": "a-book", "lab": {"kind": "notebook"}}):
        got = readme.workflows(cfg, "a-book", manifest)
        assert got[".github/workflows/checks.yml"] == want
        assert all("{terminal}" not in t and "book-commands" not in t for t in got.values())
    assert readme.workflows(cfg, "a-book") == readme.workflows(cfg, "a-book", {"slug": "a-book"})


def test_a_terminal_books_checks_also_run_its_commands():
    cfg = readme.load_config()
    text = readme.workflows(cfg, "a-book", TERMINAL)[".github/workflows/checks.yml"]
    assert "{terminal}" not in text and "{/terminal}" not in text
    jobs = yaml.safe_load(text)["jobs"]
    assert jobs["checks"]["uses"] == "rollingedition/standards/.github/workflows/book-checks.yml@v1"
    assert jobs["commands"] == {"uses": "rollingedition/standards/.github/workflows/book-commands.yml@v1",
                                "with": {"scope": "${{ github.event_name == 'pull_request' && 'affected' || 'all' }}",
                                         "record": "${{ github.event_name == 'workflow_dispatch' && inputs.record == true }}"}}
    # by hand, a terminal book's outputs can be recorded on GitHub's runner, twice from a fresh start, as an artifact
    dispatch = yaml.safe_load(text)[True]["workflow_dispatch"]
    assert dispatch["inputs"]["record"] == {"description": dispatch["inputs"]["record"]["description"], "type": "boolean",
                                            "default": False}
    book = bookfmt.load_book(FIXTURES / "k3s-sampler")
    assert readme.files(book)[".github/workflows/checks.yml"] == readme.workflows(cfg, book.slug, book.manifest)[
        ".github/workflows/checks.yml"] and "book-commands.yml" in readme.files(book)[".github/workflows/checks.yml"]


def test_the_commands_job_runs_on_githubs_runner_with_no_secrets_and_only_with_steps():
    text = REUSABLE.read_text()
    wf = yaml.safe_load(text)
    assert wf["permissions"] == {"contents": "read"}
    assert set(wf[True]["workflow_call"]["inputs"]) == {"standards-ref", "scope", "record"}
    (job,) = wf["jobs"].values()
    assert job["name"] == "commands" and job["runs-on"] == "ubuntu-24.04"
    for absent in ("secrets.", "id-token", "google-github-actions", "RE_TARGET", "docker login", "${{ secrets"):
        assert absent not in text, absent
    steps = job["steps"]
    guarded = [s for s in steps[1:] if "hashFiles('examples/*.sh')" in str(s.get("if", ""))]
    assert len(guarded) == len(steps) - 1                     # everything after the checkout looks for steps first
    runs = "\n".join(s.get("run", "") for s in steps)
    for command in ("re-check stack --book .", "re-check lab --book .", "re-check stack --book . --digest",
                    "re-check stack --book . --images", 're-check commands --book . --affected --base-ref "$BASE_SHA"',
                    "re-check commands --book . --record"):
        assert command in runs, command
    (cache,) = [s for s in steps if str(s.get("uses", "")).startswith("actions/cache@")]
    assert cache["with"] == {"path": "~/.cache/re-stack", "key": "re-stack-${{ steps.stack.outputs.digest }}"}
    assert re.search(r"key: re-stack-\$\{\{ steps\.stack\.outputs\.digest \}\}", text)
