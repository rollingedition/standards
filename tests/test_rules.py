"""Rules with dates (rules.py): a new rule warns on a released book until its next content edition, and holds a draft
from the start; and a released book's out-of-date workflows warn, since only a maintainer-approved pull request changes
them."""
import datetime as dt
import os
import re
import subprocess

import pytest

from re_standards import bookfmt, checks, cli, data_path, readme, rules, standards_root
from bookkit import CHAPTER, MANIFEST, make_book

BANNED = CHAPTER.replace("Read the file.", "Simply read the file.")        # W-35: a banned word
DATED = {"undated_through": "W-60", "content": ["prose", "code"],
         "rules": {"W-35": {"since": "2026-11-20", "what": "banned words"}}}


def git(root, *args, when="2026-11-01T12:00:00+00:00"):
    env = dict(os.environ, GIT_AUTHOR_DATE=when, GIT_COMMITTER_DATE=when, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@x",
               GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@x")
    return subprocess.run(["git", "-C", str(root), *args], env=env, capture_output=True, text=True, check=True).stdout.strip()


def released_repo(tmp_path, chapter=BANNED, manifest=MANIFEST):
    """A released book with two commits: the first edition (the root commit), then a content change on Nov 5."""
    root = make_book(tmp_path / "book", chapter=chapter.replace("More text.", "Text."), manifest=manifest)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Edition 2026.11.1", when="2026-11-01T12:00:00+00:00")
    (root / "chapters" / "01-first-steps.md").write_text(chapter)
    git(root, "commit", "-qam", "A content change", when="2026-11-05T12:00:00+00:00")
    return root


@pytest.fixture
def dated(monkeypatch):
    monkeypatch.setattr(rules, "load", lambda path=None: DATED)


def test_a_dated_rule_warns_on_a_released_book_whose_text_predates_it(tmp_path, dated):
    root = released_repo(tmp_path)
    book = bookfmt.load_book(root)
    where = rules.standing(root, book.manifest)
    assert where.released and not where.content_change and where.content_on == dt.date(2026, 11, 5)
    failures, warnings = rules.split(["chapters/01-first-steps.md:10: W-35: \"simply\" is a banned word",
                                      "W-7: a book has 5 to 12 chapters; this one has 1"], root, book.manifest)
    assert failures == ["W-7: a book has 5 to 12 chapters; this one has 1"]       # not dated: it holds every book
    assert warnings == ["chapters/01-first-steps.md:10: W-35: \"simply\" is a banned word (a rule since Nov 20, 2026, "
                        "and its text and examples last changed on Nov 5, 2026: it holds this book from its next content "
                        "edition)"]


def test_a_dated_rule_holds_a_draft_from_the_start(tmp_path, dated):
    root = released_repo(tmp_path, manifest=MANIFEST.replace('status = "live"', 'status = "draft"'))
    book = bookfmt.load_book(root)
    assert not rules.standing(root, book.manifest).released
    problem = "chapters/01-first-steps.md:10: W-35: \"simply\" is a banned word"
    assert rules.split([problem], root, book.manifest) == ([problem], [])
    assert rules.split([problem], tmp_path, None) == ([problem], [])           # no book.toml: a draft


def test_a_change_to_the_text_or_examples_makes_the_next_content_edition_and_keeps_the_rule(tmp_path, dated):
    root = released_repo(tmp_path)
    book = bookfmt.load_book(root)
    problem = "chapters/01-first-steps.md:10: W-35: \"simply\" is a banned word"
    (root / "examples" / "hello.py").write_text('print("hello")  # a change to an example\n')
    assert rules.standing(root, book.manifest).content_change
    assert rules.split([problem], root, book.manifest) == ([problem], [])
    git(root, "checkout", "-q", "--", "examples/hello.py")
    (root / "examples" / "requirements.txt").write_text("pandas==3.0.0\n")      # pins alone aren't a content change
    (root / "narration").mkdir()
    (root / "narration" / "first-steps.toml").write_text("")                    # nor narration
    assert rules.split([problem], root, book.manifest)[0] == []


def test_against_a_base_only_the_pull_requests_own_changes_count(tmp_path, dated):
    root = released_repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-qb", "renovate/pandas")
    (root / "examples" / "requirements.txt").write_text("pandas==3.0.0\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "Update pandas", when="2026-11-25T12:00:00+00:00")
    book = bookfmt.load_book(root)
    problem = "chapters/01-first-steps.md:10: W-35: \"simply\" is a banned word"
    where = rules.standing(root, book.manifest, base)
    assert not where.content_change and where.content_on == dt.date(2026, 11, 5)  # read on the base, not the branch
    assert rules.split([problem], root, book.manifest, base)[0] == []
    git(root, "checkout", "-q", "main")
    git(root, "checkout", "-qb", "agent/fix")
    (root / "chapters" / "01-first-steps.md").write_text(BANNED.replace("Done.", "Done, again."))
    git(root, "commit", "-qam", "A fix", when="2026-11-25T12:00:00+00:00")
    assert rules.split([problem], root, book.manifest, base) == ([problem], [])
    assert rules.split([problem], root, book.manifest, "0" * 40)[0] == []       # a base git doesn't have: no change known


def test_once_the_text_changed_after_the_rule_every_pull_request_keeps_it(tmp_path, dated):
    root = released_repo(tmp_path)
    (root / "chapters" / "01-first-steps.md").write_text(BANNED + "\nMore.\n")
    git(root, "commit", "-qam", "Edition after the rule", when="2026-11-21T09:00:00+00:00")
    book = bookfmt.load_book(root)
    assert rules.standing(root, book.manifest).content_on == dt.date(2026, 11, 21)
    problem = "W-35: \"simply\" is a banned word"
    assert rules.split([problem], root, book.manifest) == ([problem], [])


def test_the_first_commit_alone_says_nothing_so_a_copy_from_a_tarball_isnt_read_as_changed_today(tmp_path, dated):
    root = make_book(tmp_path / "copy", chapter=BANNED)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base 1234", when="2026-11-30T12:00:00+00:00")
    book = bookfmt.load_book(root)
    where = rules.standing(root, book.manifest)
    assert where.content_on is None and rules.split(["W-35: x"], root, book.manifest)[1][0].endswith(
        "its history doesn't say when its text last changed: it holds this book from its next content edition)")
    plain = make_book(tmp_path / "plain", chapter=BANNED)                        # not a git checkout at all
    failures, warnings = rules.split(["W-35: x"], plain, bookfmt.load_book(plain).manifest)
    assert failures == [] and "git can't say what this change touches" in warnings[-1]


def test_re_check_style_lists_a_dated_rule_as_a_warning_on_a_released_book(tmp_path, dated, capsys):
    root = released_repo(tmp_path)
    assert cli.main(["style", "--book", str(root), "--skip", "W-7,W-10"]) == 0
    err = capsys.readouterr().err
    assert "Writing standards, rules this book takes with its next content edition: 1 warning(s)" in err
    assert "W-35: \"simply\" is a banned word (a rule since Nov 20, 2026" in err
    (root / "chapters" / "01-first-steps.md").write_text(BANNED + "\nAn edit.\n")
    assert cli.main(["style", "--book", str(root), "--skip", "W-7,W-10"]) == 1    # this change makes the next edition


def test_the_rules_data_dates_every_rule_after_the_undated_ones():
    """A writing rule added after rules had dates is listed with the day it took effect, so it can't stop a released
    book's pull requests the day it arrives."""
    cfg = rules.load()
    days = rules.dated(cfg)
    assert set(cfg["content"]) <= {"prose", "code", "deps", "narration", "skill", "meta"}
    last = int(cfg["undated_through"].split("-")[1])
    written = {int(n) for n in re.findall(r"^\*\*W-(\d+)\b", (standards_root() / "writing" / "README.md").read_text(), re.M)}
    assert max(written) >= last
    missing = sorted(f"W-{n}" for n in written if n > last and f"W-{n}" not in days)
    assert not missing, f"date these rules in data/rules.toml: {missing}"
    for rid, entry in (cfg.get("rules") or {}).items():
        assert rules.RULE.fullmatch(rid) and entry.get("what") and dt.date.fromisoformat(str(entry["since"]))
    assert data_path("rules.toml").is_file()


def test_a_released_books_out_of_date_workflows_warn_and_a_drafts_fail(tmp_path, capsys):
    root = make_book(tmp_path / "live")
    book = bookfmt.load_book(root)
    readme.check(book, write=True)
    (root / ".github" / "workflows" / "checks.yml").write_text("# an older template\n")
    assert cli.main(["readme", "--book", str(root)]) == 0
    out = capsys.readouterr()
    assert "Front page, the book's workflows: 1 warning(s)" in out.err
    assert ".github/workflows/checks.yml is out of date; a maintainer-approved pull request brings it up to date" in out.err
    assert "README.md, CITATION.cff, LICENSE, LICENSE-CODE and renovate.json are up to date" in out.out
    (root / "README.md").write_text("by hand\n")                               # the front page itself still fails
    assert cli.main(["readme", "--book", str(root)]) == 1
    draft = make_book(tmp_path / "draft", manifest=MANIFEST.replace('status = "live"', 'status = "draft"'))
    readme.check(bookfmt.load_book(draft), write=True)
    (draft / ".github" / "workflows" / "checks.yml").write_text("# an older template\n")
    assert cli.main(["readme", "--book", str(draft)]) == 1


def test_a_change_to_generated_files_alone_rides_with_the_next_edition(tmp_path):
    book = bookfmt.load_book(make_book(tmp_path))
    assert set(readme.files(book)) == readme.generated_names()
    assert checks.generated_only(["README.md", ".github/workflows/checks.yml"])
    assert checks.rides_along([".github/workflows/checks.yml", "renovate.json", "narration/x.toml"])
    assert not checks.rides_along([".github/workflows/other.yml"]) and not checks.rides_along(["README.md", "book.toml"])
    assert checks.check_kind_label([], [".github/workflows/checks.yml", ".github/workflows/labels.yml"]) == []
    assert checks.riding_words(["README.md", "skill.md"]) == "the agent skill's procedures and the generated front page and workflows"
