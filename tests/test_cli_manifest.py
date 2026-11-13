from re_standards import cli


def write_book(d, **over):
    fields = {"slug": '"demo"', "title": '"Demo"', "status": '"live"', "level": '"foundations"', "skills": '["data-pipelines"]', "line": '"main"'}
    fields.update(over)
    (d / "book.toml").write_text("".join(f"{k} = {v}\n" for k, v in fields.items()))


def test_manifest_check_passes_and_fails(tmp_path, capsys):
    write_book(tmp_path)
    assert cli.main(["manifest", "--book", str(tmp_path)]) == 0
    assert "validates against taxonomy" in capsys.readouterr().out
    write_book(tmp_path, skills='["not-a-skill"]')
    assert cli.main(["manifest", "--book", str(tmp_path)]) == 1
    assert "unknown skill" in capsys.readouterr().err
    write_book(tmp_path, level='"beginner"')
    assert cli.main(["manifest", "--book", str(tmp_path)]) == 1
    assert "level must be one of foundations, in-practice" in capsys.readouterr().err


def test_manifest_check_reports_a_missing_or_broken_file(tmp_path, capsys, monkeypatch):
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert cli.main(["manifest", "--book", str(tmp_path)]) == 1
    (tmp_path / "book.toml").write_text("slug = \n")
    assert cli.main(["manifest", "--book", str(tmp_path)]) == 1
    assert "does not parse" in capsys.readouterr().err
    assert "Book manifest: failed" in summary.read_text()


def test_a_summary_far_from_the_catalog_s_length_gets_a_note_and_never_fails(tmp_path, capsys):
    """W-60: guidance, not a limit (the founder, Nov 11, 2026)."""
    write_book(tmp_path, summary='"Forecasts you can trust, from baselines and backtests to uncertainty you can act on."')
    assert cli.main(["manifest", "--book", str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert "validates against taxonomy" in out.out and "W-60: the summary has 14 words" in out.err
    words = " ".join(["word"] * 40)
    write_book(tmp_path, summary=f'"{words}"')
    assert cli.main(["manifest", "--book", str(tmp_path)]) == 0
    assert "W-60" not in capsys.readouterr().err
