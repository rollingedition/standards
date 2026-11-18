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
    assert profile.rstrip().endswith("Written with AI. Verified by people.")         # the page ends with the disclosure


def test_contributions_come_in_under_cc_by_and_mit_with_the_dco():
    """What contributions come in under ([licences.contributions] in data/readme.toml): CC BY 4.0 for text and MIT for
    code, each commit signed off under the DCO, so they can be published with a book under its own licences, the text's
    with our added permission, and included when a book is licensed to others. The repository's README carries the
    trademark notice, as every generated README does."""
    out, _ = community.files()
    guide = out["CONTRIBUTING.md"]
    terms = guide.split("## Licences\n\n", 1)[1]
    assert terms.startswith("You keep the copyright in what you contribute. When you open a pull request, you license your "
                            "change under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) for text and "
                            "[MIT](https://opensource.org/license/mit) for code, and you sign off each commit (`git commit "
                            "-s`) to certify the [Developer Certificate of Origin](https://developercertificate.org/)")
    assert ("under the book's own licences, [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) for text, with "
            "[our added permission](https://rollingedition.com/reuse), and [MIT](https://opensource.org/license/mit) for "
            "code, and include it when we license a book to others.") in terms
    assert "{" not in terms
    assert "are trademarks of Distributed LLC" in out["README.md"] and "{" not in out["README.md"]
