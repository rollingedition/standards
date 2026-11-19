"""voice.toml (re_standards.voice): an authored book's voice, its overrides only of the rules the writing standards mark
adjustable and within their bounds, and `re-check style` and `re-check manifest` reading it."""
import tomllib

import pytest

from re_standards import checks, cli, style, voice

CFG = style.load_config()


def test_the_standards_say_what_s_adjustable_and_what_s_fixed():
    adj = CFG["adjustable"]
    assert set(adj["length"]) <= set(CFG["length"]) and set(adj["narrative"]) <= set(CFG["narrative"])
    for key, (lo, hi) in {**adj["length"], **adj["narrative"]}.items():
        current = {**CFG["length"], **CFG["narrative"]}[key]
        inside = current if isinstance(current, list) else [current, current]
        assert lo <= inside[0] <= inside[1] <= hi, key                      # the standards' own limit is inside its bounds
    assert adj["person"]["allowed"][0] == "we"
    for rule in ("W-17", "W-25", "W-28", "W-29", "W-39"):                # examples, versions, claims, citations, access
        assert rule in adj["fixed"]


def test_a_new_draft_s_voice_is_valid_and_changes_nothing():
    data = tomllib.loads('[profile]\nsummary = ""\nperson = "we"\ntraits = []\nsamples = []\n\n[glossary]\n\n'
                         '[avoid]\nwords = []\nphrases = []\n\n[overrides]\n')
    assert voice.problems(data, CFG) == [] and voice.apply(CFG, data) == CFG


def test_overrides_go_only_as_far_as_the_bounds_and_never_to_a_fixed_rule():
    good = {"profile": {"person": "I", "traits": ["dry humour"]}, "overrides": {"chapter_words": [2000, 8000], "example_lines": 50,
                                                                                "paragraph_bindings": 6},
            "avoid": {"words": ["utterly"], "phrases": ["at the end of the day"]}, "glossary": {"contract": "a pinned schema"}}
    assert voice.problems(good, CFG) == []
    applied = voice.apply(CFG, good)
    assert applied["length"]["chapter_words"] == [2000, 8000] and applied["length"]["example_lines"] == 50
    assert applied["length"]["section_words"] == CFG["length"]["section_words"]
    assert applied["narrative"]["paragraph_bindings"] == 6
    assert applied["words"]["banned"][-2:] == ["utterly", "at the end of the day"] and CFG["words"]["banned"][-1] != "utterly"
    for over, said in (({"chapter_words": [100, 8000]}, "within"), ({"chapter_words": [8000, 2000]}, "within"),
                       ({"example_lines": 500}, "from"), ({"examples_run": False}, "Examples that run"),
                       ({"time": []}, "isn't a limit"), ({"chapter_words": 3000}, "range")):
        found = voice.problems({"overrides": over}, CFG)
        assert found and said in found[0], (over, found)
        assert voice.apply(CFG, {"overrides": over}) == CFG                   # a voice with problems changes nothing


def test_its_shapes_are_checked():
    for data, said in (({"style": {}}, "isn't one of"), ({"profile": {"person": "they"}}, "person is one of"),
                       ({"profile": {"traits": ["x"] * 9}}, "at most 8"), ({"profile": {"samples": ["../secret"]}}, "plan/samples/"),
                       ({"profile": {"tone": "x"}}, "isn't one of"), ({"avoid": {"words": [""]}}, "at most 100"),
                       ({"glossary": {"x": 1}}, "glossary"), ({"profile": {"sentence_words": 99}}, "sentence_words")):
        assert any(said in p for p in voice.problems(data, CFG)), (data, voice.problems(data, CFG))


def test_profile_toml_replaces_the_profile_and_keeps_the_rest():
    before = ('# my voice\n[profile]\nsummary = "old"\nperson = "we"\n\n[glossary]\ncontract = "a pinned schema"\n\n'
              '[overrides]\nchapter_words = [2000, 8000]\n')
    after = voice.profile_toml({"summary": 'Dry, "exact".\n[x]', "person": "I", "traits": ["short sentences"],
                                "samples": ["plan/samples/post.md"], "sentence_words": 14}, before)
    data = tomllib.loads(after)
    assert data["profile"] == {"summary": 'Dry, "exact".\n[x]', "person": "I", "traits": ["short sentences"],
                               "samples": ["plan/samples/post.md"], "sentence_words": 14}
    assert data["glossary"] == {"contract": "a pinned schema"} and data["overrides"] == {"chapter_words": [2000, 8000]}
    assert after.startswith("# my voice\n") and voice.problems(data, CFG) == []
    assert tomllib.loads(voice.profile_toml({"summary": "s"}, ""))["profile"]["summary"] == "s"


def test_a_voice_only_change_rides_along_with_no_kind_label():
    assert checks.rides_along(["voice.toml"]) and checks.rides_along(["voice.toml", "narration/lexicon.toml"])
    assert checks.check_kind_label([], ["voice.toml"]) == []
    assert "the author's voice" in checks.riding_words(["voice.toml"])


def test_re_check_style_keeps_the_book_to_its_voice_and_manifest_checks_it(tmp_path, capsys):
    from bookkit import make_book
    root = tmp_path / "book"
    make_book(root, examples={})
    (root / "voice.toml").write_text('[overrides]\nchapter_words = [1, 9000]\n')
    assert cli.main(["manifest", "--book", str(root)]) == 1
    said = capsys.readouterr()
    assert "chapter_words is a range [low, high] within" in said.out + said.err
    (root / "voice.toml").write_text('[overrides]\nchapter_words = [1500, 9000]\nsection_words = [150, 1500]\n'
                                     '[avoid]\nwords = ["file"]\n')
    assert cli.main(["manifest", "--book", str(root)]) == 0
    capsys.readouterr()
    cli.main(["style", "--book", str(root)])
    said = capsys.readouterr()
    assert "W-35" in said.out + said.err and '"file"' in said.out + said.err      # the book's own word to avoid
    assert "1500" in said.out + said.err                                          # its chapter length, not the standards'
    (root / "voice.toml").unlink()
    cli.main(["style", "--book", str(root)])
    said = capsys.readouterr()
    assert '"file"' not in said.out + said.err
