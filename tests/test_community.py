from re_standards import community


def test_community_files_are_generated_and_the_conduct_contact_is_required(tmp_path):
    cfg = community.load_config()
    problems = community.write(tmp_path, {**cfg, "conduct_contact": ""})
    assert problems == ["CODE_OF_CONDUCT.md: set conduct_contact in data/community.toml, where conduct reports go"]
    assert not (tmp_path / "CODE_OF_CONDUCT.md").exists()
    assert "`kind:prose`" in (tmp_path / ".github" / "PULL_REQUEST_TEMPLATE.md").read_text()
    assert "{standards}" not in (tmp_path / "CONTRIBUTING.md").read_text()
    assert community.write(tmp_path, {**cfg, "conduct_contact": "conduct@example.org"}) == []
    conduct = (tmp_path / "CODE_OF_CONDUCT.md").read_text()
    assert conduct.startswith("# Contributor Covenant Code of Conduct") and "conduct@example.org" in conduct
    assert "[INSERT CONTACT METHOD]" not in conduct


def test_every_file_is_generated_with_the_contact_address(tmp_path):
    """One address for conduct and security reports (Proposed); SECURITY.md falls back to it when a repository's
    Security tab doesn't offer private reporting."""
    cfg = community.load_config()
    assert cfg["conduct_contact"] and cfg["security_contact"] == cfg["conduct_contact"]
    assert community.write(tmp_path) == []
    assert cfg["conduct_contact"] in (tmp_path / "CODE_OF_CONDUCT.md").read_text()
    security = (tmp_path / "SECURITY.md").read_text()
    assert f"If the tab doesn't offer it, email {cfg['security_contact']}." in security and "{security_contact}" not in security
    problems = community.write(tmp_path / "none", {**cfg, "security_contact": ""})
    assert problems and "security_contact" in problems[0] and not (tmp_path / "none" / "SECURITY.md").exists()
    form = (tmp_path / ".github" / "ISSUE_TEMPLATE" / "report-an-error.yml").read_text()
    assert "The ID is the last part of the link beside each heading, such as rank-with-bm25." in form


def test_the_contributing_guide_describes_open_verification():
    """Open verification: agents publish, anyone checks or corrects, and only serious risks go to a person. The guide never says a
    person approves a change, and credits contributors by name or pseudonym, with no reviewer credit."""
    files, _ = community.files()
    guide = files["CONTRIBUTING.md"]
    assert "Agents publish every book, anyone can check it or correct it, and only serious risks go to a person." in guide
    assert "It merges once its checks pass,** whatever kind of change it is" in guide
    assert "A flagged change waits for a Rolling Edition maintainer instead." in guide
    assert "https://github.com/rollingedition/standards/blob/main/data/review-tiers.toml" in guide   # the published rules
    assert "credited by name, or by the pseudonym you choose" in guide
    for gone in ("community reviewers", "Reviewers are credited", "once approved", "its reviewers", "a maintainer invites"):
        assert gone not in guide, gone


def test_the_repository_and_the_organization_get_a_readme(tmp_path):
    out, problems = community.files()
    assert out["README.md"].startswith("# Rolling Edition's community files") and "[CONTRIBUTING.md](CONTRIBUTING.md)" in out["README.md"]
    profile = out["profile/README.md"]
    assert profile.startswith("# Rolling Edition") and "(https://rollingedition.com)" in profile
    assert "(https://github.com/rollingedition/.github/blob/main/CONTRIBUTING.md)" in profile and "{" not in profile + out["README.md"]
    assert "Written with AI. Verified by people." in profile
