"""concepts.toml (re_standards/concepts.py): the terms a book defines, each quoted from its own sentence, connected by a
fixed set of relation types (writing standards W-77 to W-80). The fixture tests/fixtures/concepts-sampler uses every
field and every relation type a book may use; tests/fixtures/concepts-organization.toml is an organization's file, in
its own namespace, with the two types reserved for it."""
import shutil
import tomllib
from pathlib import Path

import pytest
import yaml

from bookkit import make_book
from re_standards import bookfmt, checks, cli, concepts, data_path, rules, standards_root

FIXTURES = Path(__file__).parent / "fixtures"
SAMPLER = FIXTURES / "concepts-sampler"
ORGANIZATION = FIXTURES / "concepts-organization.toml"


def sampler(tmp_path, edit=None, chapter=None, toml=None) -> bookfmt.Book:
    """The fixture, copied: `edit` replaces text in its concepts.toml, (old, new) or a list of them; `chapter` in a
    chapter, (file, old, new) or a list of them; `toml` is a whole concepts.toml instead."""
    root = tmp_path / "sampler"
    shutil.copytree(SAMPLER, root)
    path = root / concepts.FILE
    if toml is not None:
        path.write_text(toml)
    for old, new in [edit] if edit and isinstance(edit[0], str) else edit or []:
        text = path.read_text()
        assert old in text, old
        path.write_text(text.replace(old, new, 1))
    for file, old, new in [chapter] if chapter and isinstance(chapter[0], str) else chapter or []:
        text = (root / "chapters" / file).read_text()
        assert old in text, old
        (root / "chapters" / file).write_text(text.replace(old, new, 1))
    return bookfmt.load_book(root)


# Chapter 1 without its opening's link to nDCG, or its mention of it: the use in its last section is then its first
QUIET = ("01-scoring-a-ranking.md", "[Chapter 2](#ndcg) builds nDCG on the same judgments.",
         "Chapter 2 builds on the same judgments.")
UNLINKED = [QUIET, ("01-scoring-a-ranking.md", "[nDCG](#ndcg) also weighs", "nDCG also weighs")]


def problems(book: bookfmt.Book) -> list[str]:
    found, notes = concepts.check(book)
    return found


def notes(book: bookfmt.Book) -> list[str]:
    return concepts.check(book)[1]


# ---------------------------------------------------------------- the fixture and the format


def test_the_fixture_passes_with_every_field_and_relation_type(tmp_path, capsys):
    book = bookfmt.load_book(SAMPLER)
    assert book.problems == [] and concepts.check(book) == ([], [])
    assert cli.main(["concepts", "--book", str(SAMPLER)]) == 0
    assert "ok  9 concept(s) in 2 context(s), each definition quoted from its section, with 18 relation(s)" in \
        capsys.readouterr().out
    raw = tomllib.loads((SAMPLER / concepts.FILE).read_text())
    fields = {key for c in raw["concepts"] for key in c}
    assert fields == concepts.CONCEPT_KEYS, concepts.CONCEPT_KEYS - fields
    org = concepts.load(ORGANIZATION)
    used = {r.type for c in book.concepts for r in c.relations} | {r.type for c in org for r in c.relations}
    assert used == set(concepts.relation_types())                        # every type, the reserved two in org's file


def test_a_book_without_concepts_passes_and_its_concepts_are_empty(tmp_path, capsys):
    book = bookfmt.load_book(make_book(tmp_path / "tiny"))
    assert not book.concepts.present and len(book.concepts) == 0 and list(book.concepts) == []
    assert concepts.check(book) == ([], [])
    assert cli.main(["concepts", "--book", str(book.root)]) == 0
    assert "no concepts.toml: the book indexes no concepts yet" in capsys.readouterr().out


def test_book_concepts_reads_the_file_beside_book_toml_and_load_reads_one_alone():
    book = bookfmt.load_book(SAMPLER)
    cs = book.concepts
    assert cs.present and cs.ours and cs.namespace == "rollingedition" and cs.context == "search-and-recommendation"
    ndcg = cs.get("search-and-recommendation", "ndcg")
    assert ndcg.aliases == ["nDCG", "nDCG@k"] and ndcg.applies_to == ["scikit-learn"] and ndcg.example == "ndcg-by-hand"
    assert concepts.Relation("implemented-by", "scikit-learn", ">=1.5") in ndcg.relations
    assert cs.get("graded-relevance", "gain").context == "graded-relevance"
    assert cs.contexts["graded-relevance"].broader == "search-evaluation"
    alone = concepts.load(SAMPLER / concepts.FILE)
    assert [c.key for c in alone] == [c.key for c in cs] and alone.problems == []
    assert not concepts.load(SAMPLER / "nothing.toml").present


def test_addresses_come_from_the_standards_data():
    cs = bookfmt.load_book(SAMPLER).concepts
    base = concepts.settings()["addresses"]["base"]
    assert base == "https://rollingedition.com/concepts"
    assert cs.address("search-and-recommendation", "ndcg") == f"{base}/search-and-recommendation/ndcg"
    assert cs.address("search-and-recommendation", "ndcg", "2026.11.8") == f"{base}/search-and-recommendation/ndcg@2026.11.8"
    assert cs.context_address("graded-relevance") == f"{base}/graded-relevance"


def test_every_relation_type_says_what_it_means_and_how_it_maps_onto_skos():
    types = concepts.relation_types()
    assert set(types) == {"broader", "narrower", "part-of", "measured-from", "computed-from", "prerequisite-of",
                          "contrasts-with", "implemented-by", "same-as", "close-to", "maps-to", "defined-by-organization"}
    for name, spec in types.items():
        assert spec["meaning"] and spec["property"] and spec["target"] in ("concept", "match", "package", "organization")
        assert spec["skos"] == "" or spec["skos"].startswith("skos:"), name
        if "inverse" in spec:
            assert types[spec["inverse"]]["inverse"] == name
    assert types["prerequisite-of"]["acyclic"] and types["same-as"]["skos"] == "skos:exactMatch"
    assert {n for n, s in types.items() if s.get("reserved") == "organization"} == {"maps-to", "defined-by-organization"}


def test_the_vocabulary_names_every_property_served_records_use_that_schema_org_and_skos_lack():
    data = concepts.settings()
    own = set(data["vocabulary"])
    assert own == {"formula", "appliesTo", "example", "firstEdition", "changedEdition"} and all(data["vocabulary"].values())
    properties = [spec["property"] for spec in data["relations"].values()]
    assert len(set(properties)) == len(properties) and not own & set(properties)      # one name, one meaning
    doc = concepts.served.__doc__
    assert all(f"the vocabulary's {name}" in doc for name in ("formula", "appliesTo", "example"))


def test_the_format_says_what_it_cant_read(tmp_path):
    found = problems(sampler(tmp_path, toml='''context = "search-and-recommendation"
colour = "blue"

[[concepts]]
id = "Not An ID"
term = "x"
definition = "x"
section = "dcg"

[[concepts]]
id = "no-term"
definition = "A gain is what a result's grade is worth to the score."
section = "dcg"
synonyms = ["y"]
wikidata = "2539"
'''))
    assert found == [
        "concepts.toml: unknown keys: colour; it holds context, [namespace], [[contexts]], [[concepts]] and [retired]",
        "concepts.toml:4: Not An ID: a concept's ID is lowercase words joined by hyphens, at most 64 characters",
        "concepts.toml:10: no-term: unknown keys: synonyms",
        "concepts.toml:10: no-term: needs term",
        "concepts.toml:10: no-term: wikidata is an item's ID, such as Q2539"]
    assert problems(sampler(tmp_path / "bad", toml="[[concepts]\n")) [0].startswith("concepts.toml does not parse:")


def test_a_concept_is_in_a_context_of_the_taxonomy_or_one_the_book_declares(tmp_path):
    found = problems(sampler(tmp_path, edit=[('id = "graded-relevance"\nbroader = "search-evaluation"',
                                              'id = "graded-relevance"\nbroader = "searching"'),
                                             ('context = "graded-relevance"', 'context = "gains"')]))
    assert "concepts.toml:7: the context graded-relevance is narrower than 'searching', which isn't a taxonomy area " \
           "or skill, or a context declared here" in found
    assert "concepts.toml:73: gain: 'gains' isn't a context: use a taxonomy area or skill, or declare a narrower one " \
           "under [[contexts]]" in found
    found = problems(sampler(tmp_path / "shadow", edit=('id = "graded-relevance"', 'id = "search-relevance"')))
    assert "concepts.toml:7: search-relevance is already one of the taxonomy's areas and skills: use it, don't declare " \
           "it" in found
    lost = sampler(tmp_path / "none", edit=('context = "search-and-recommendation"          #', '#'))
    assert "concepts.toml:14: relevance: name its context, or give the file one with context = \"…\" at its top" in \
        problems(lost)


def test_a_book_s_concepts_are_in_our_namespace(tmp_path):
    book = sampler(tmp_path, edit=('context = "search-and-recommendation"          #',
                                   '[namespace]\nid = "acme"\nbase = "https://concepts.example.com"\n\n#'))
    assert problems(book) == ["concepts.toml: a book's concepts are in our namespace; only an organization's file names "
                              "its own"]


# ---------------------------------------------------------------- W-77: quoted from the book's own sentence


def test_quotes_match_through_emphasis_links_line_breaks_and_bindings_as_written():
    source = ("A **relevance judgment**, written\n[judgment](#x), is a *person's* label &amp; more. It prints "
              "{{out:ex:count}} rows.\n\n```text\nnDCG@k  =  DCG@k / IDCG@k\n```\n")
    assert concepts.quoted_in("A relevance judgment, written judgment, is a person's label & more.", source)
    assert concepts.quoted_in("A **relevance judgment**, written [judgment](#x), is a *person's* label", source)
    assert concepts.quoted_in("It prints {{out:ex:count}} rows.", source)
    assert concepts.quoted_in("nDCG@k = DCG@k / IDCG@k", source)
    assert not concepts.quoted_in("It prints 12 rows.", source)                     # the value, not the binding
    assert not concepts.quoted_in("relevance judgment, written judgment, is a persons label", source)
    assert not concepts.quoted_in("elevance judgment", source)                       # from a word's edge to a word's edge
    assert not concepts.quoted_in("label & more. It prints", "label &amp; more.\n\nIt prints")   # never across blocks


def test_a_definition_or_formula_not_in_its_section_fails(tmp_path):
    book = sampler(tmp_path, edit=[("is the share of the top k results that are relevant.",
                                    "is the fraction of the top k results that are relevant."),
                                   ('formula = "nDCG@k = DCG@k / DCG@k of the ideal ranking"',
                                    'formula = "nDCG@k = DCG@k / IDCG@k"')])
    assert problems(book) == [
        "concepts.toml:36: precision-at-k: W-77: its definition isn't in #count-relevant-at-the-top's text, word for "
        "word: quote the book's own sentence, as the section writes it (emphasis, links and line breaks aside)",
        "concepts.toml:103: ndcg: W-77: its formula isn't in #ndcg's text, word for word: quote the book's own formula, "
        "as the section writes it (emphasis, links and line breaks aside)"]


def test_a_quote_of_the_text_as_read_says_to_quote_its_bindings_as_written(tmp_path):
    book = sampler(tmp_path, chapter=("02-graded-gains.md", "At scikit-learn {{version:scikit-learn}}, `ndcg_score` uses",
                                      "The ranking scores {{out:ndcg-by-hand:ndcg@3}}. At scikit-learn, `ndcg_score` uses"),
                   edit=('formula = "nDCG@k = DCG@k / DCG@k of the ideal ranking"', 'formula = "The ranking scores 0.860"'))
    assert problems(book) == [
        "concepts.toml:103: ndcg: W-77: its formula isn't in #ndcg's text, word for word: quote the book's own formula, "
        "as the section writes it (emphasis, links and line breaks aside); it quotes the text as read: quote its "
        "bindings as written, such as {{out:…}}"]


def test_a_quote_from_another_section_says_where_it_is(tmp_path):
    book = sampler(tmp_path, edit=('section = "judge-each-result"', 'section = "dcg"'))
    assert problems(book) == [
        "concepts.toml:25: relevance-judgment: W-77: its definition isn't in #dcg's text, word for word: quote the "
        "book's own sentence, as the section writes it (emphasis, links and line breaks aside); it's in "
        "#judge-each-result, so give that section"]


def test_the_section_exists_and_a_retired_one_names_its_successor(tmp_path):
    book = sampler(tmp_path, edit=('section = "ranking-metrics"', 'section = "metrics"'))
    assert problems(book) == ["concepts.toml:63: ranking-metric: W-77: there is no section #metrics in this book"]
    (book.root / "redirects.yml").write_text("metrics: ranking-metrics\n")
    assert problems(bookfmt.load_book(book.root)) == [
        "concepts.toml:63: ranking-metric: W-77: #metrics is retired; its successor is #ranking-metrics"]


def test_what_a_definition_applies_to_is_pinned(tmp_path):
    book = sampler(tmp_path, edit=('applies_to = ["scikit-learn"]', 'applies_to = ["scikit-learn", "bm25s"]'))
    assert problems(book) == ["concepts.toml:103: ndcg: W-77: applies_to names bm25s, which examples/requirements.txt "
                              "doesn't pin: the version a definition is true for comes from the book's pins"]


def test_an_example_is_one_the_book_has(tmp_path):
    book = sampler(tmp_path, edit=('example = "ndcg-by-hand"', 'example = "ndcg-twice"'))
    assert problems(book) == ["concepts.toml:103: ndcg: there is no example 'ndcg-twice' in this book"]


# ---------------------------------------------------------------- W-78: one concept, one definition


def test_a_concept_is_defined_once_and_its_names_are_unique_in_its_context(tmp_path):
    book = sampler(tmp_path, edit=[('id = "discount"', 'id = "dcg"'),
                                   ('aliases = ["recall@k"]', 'aliases = ["recall@k", "Precision@k"]'),
                                   ('aliases = ["nDCG", "nDCG@k"]', 'aliases = ["nDCG", "Normalized DCG"]')])
    found = problems(book)
    assert "concepts.toml:94: dcg: W-78: dcg is in search-and-recommendation twice (see line 83); a book defines a " \
           "concept once" in found
    assert "concepts.toml:51: recall-at-k: W-78: 'Precision@k' names both precision-at-k and recall-at-k in " \
           "search-and-recommendation: a term or alias names one concept in a context, and a second meaning goes in a " \
           "context of its own" in found
    assert "concepts.toml:103: ndcg: W-78: 'Normalized DCG' is listed twice for ndcg" in found


def test_two_concepts_never_quote_the_same_definition(tmp_path):
    book = sampler(tmp_path, edit=("Recall at k, recall@k, is the share of all relevant results that appear in the "
                                   "top k.", "Precision at k, written precision@k, is the share of the top k results "
                                   "that are relevant."))
    assert "concepts.toml:51: recall-at-k: W-78: recall-at-k quotes the same definition as precision-at-k: one " \
           "definition, one concept" in problems(book)


def test_one_id_in_two_contexts_is_two_concepts_and_a_bare_reference_to_it_must_say_which(tmp_path):
    toml = """context = "search-and-recommendation"

[[contexts]]
id = "graded-relevance"
broader = "search-evaluation"

[[contexts]]
id = "ranked-lists"
broader = "search-evaluation"

[[concepts]]
id = "gain"
term = "gain"
definition = "A gain is what a result's grade is worth to the score."
section = "dcg"

[[concepts]]
id = "gain"
term = "gain"
context = "graded-relevance"
definition = "A gain is what a result's grade is worth"
section = "dcg"

[concepts.relations]
close-to = ["gain"]

[[concepts]]
id = "discount"
term = "discount"
context = "ranked-lists"
definition = "The discount is the part of DCG that shrinks a gain lower down"
section = "dcg"

[concepts.relations]
contrasts-with = ["gain"]
"""
    assert problems(sampler(tmp_path, toml=toml)) == [         # no W-78: two contexts, two concepts
        "concepts.toml:17: gain: W-80: gain is close-to itself",   # a bare ID is its own context's first
        "concepts.toml:27: discount: W-80: contrasts-with gain: gain is in graded-relevance and search-and-recommendation: "
        "write context/gain"]
    fixed = toml.replace('close-to = ["gain"]', 'close-to = ["search-and-recommendation/gain"]').replace(
        'contrasts-with = ["gain"]', 'contrasts-with = ["graded-relevance/gain"]')
    assert problems(sampler(tmp_path / "fixed", toml=fixed)) == []


# ---------------------------------------------------------------- W-79: link a term used before its definition


def test_a_term_used_before_its_definition_with_no_link_is_listed_and_strict_fails(tmp_path, capsys):
    book = sampler(tmp_path, chapter=UNLINKED)
    assert problems(book) == []
    assert notes(book) == ['chapters/01-scoring-a-ranking.md:38: W-79: "nDCG" comes before its definition in #ndcg '
                           '(chapter 2): link this first use, as [nDCG](#ndcg)']
    assert cli.main(["concepts", "--book", str(book.root)]) == 0
    assert "Concepts, terms used before their definition: 1 warning(s)" in capsys.readouterr().err
    assert cli.main(["concepts", "--book", str(book.root), "--strict"]) == 1


def test_a_link_earlier_in_the_chapter_or_in_the_same_block_is_enough(tmp_path):
    earlier = sampler(tmp_path, chapter=("01-scoring-a-ranking.md", "[nDCG](#ndcg) also weighs", "nDCG also weighs"))
    assert notes(earlier) == []                         # the opening links it, then uses it, before the last section
    same = sampler(tmp_path / "same", chapter=[QUIET, ("01-scoring-a-ranking.md", "[nDCG](#ndcg) also weighs",
                                                       "nDCG, [defined later](#ndcg), also weighs")])
    assert notes(same) == []
    book = sampler(tmp_path / "sub", chapter=[("02-graded-gains.md", "## Normalize by the ideal ranking {#ndcg}",
                                               "## Normalize by the ideal ranking {#ndcg}\n\nWhy.\n\n"
                                               "### The ideal ranking {#ideal}"),
                                              ("01-scoring-a-ranking.md", "[nDCG](#ndcg) also weighs",
                                               "nDCG also weighs")],
                   edit=('section = "ndcg"', 'section = "ideal"'))
    assert notes(book) == []                            # linked to #ndcg, the ## section its ### #ideal is under


def test_what_isnt_a_use_code_headings_longer_names_and_the_defining_chapter_s_opening(tmp_path):
    chapter = "01-scoring-a-ranking.md"
    assert notes(sampler(tmp_path / "plain", chapter=UNLINKED))       # the use the variants below change
    for n, new in enumerate(["`nDCG` also weighs",                                      # inline code
                             "nDCG@10 also weighs",                                     # joined to more
                             "an ndcg also weighs",                                     # a capital inside: as written
                             "{{out:precision-and-recall:recall@3}} also weighs"]):     # a binding
        book = sampler(tmp_path / str(n), chapter=[QUIET, (chapter, "[nDCG](#ndcg) also weighs", new)])
        assert notes(book) == [], new
    heading = sampler(tmp_path / "heading", chapter=[QUIET, (chapter, "[nDCG](#ndcg) also weighs", "it also weighs"),
                                                     (chapter, "### Metrics that score", "### nDCG and metrics that score")])
    assert notes(heading) == []
    longer = sampler(tmp_path / "longer", chapter=(chapter, "the simplest;", "the simplest, and discounted cumulative "
                                                   "gain is another;"))
    assert [n.split(": ")[2] for n in notes(longer)] == ['"discounted cumulative gain" comes before its definition in '
                                                        '#dcg (chapter 2)']   # never "gain", inside dcg's longer name
    promise = sampler(tmp_path / "promise", chapter=("02-graded-gains.md", "compute DCG and nDCG by hand",
                                                     "compute DCG and nDCG and their discount by hand"))
    assert notes(promise) == []                                         # its own chapter's opening promises it


def test_a_term_s_first_letter_matches_in_either_case_unless_it_has_capitals_inside(tmp_path):
    chapter = "01-scoring-a-ranking.md"
    found = notes(sampler(tmp_path, chapter=(chapter, "the simplest;", "the simplest, as a Gain shows;")))
    assert found == ['chapters/01-scoring-a-ranking.md:38: W-79: "Gain" comes before its definition in #dcg (chapter '
                     '2): link this first use, as [Gain](#dcg)']
    assert notes(sampler(tmp_path / "caps", chapter=(chapter, "the simplest;", "the simplest, as DISCOUNTS show;"))) == []


# ---------------------------------------------------------------- W-80: relations from the fixed set


def test_a_relation_s_type_is_from_the_fixed_set_and_names_a_concept_that_exists(tmp_path):
    book = sampler(tmp_path, edit=[('measured-from = ["relevance-judgment"]\ncontrasts-with',
                                    'measured-from = ["relevance-judgments"]\nexplains = ["dcg"]\ncontrasts-with'),
                                   ('part-of = ["dcg"]', 'part-of = ["discount"]')])
    assert problems(book) == [
        "concepts.toml:36: precision-at-k: W-80: measured-from relevance-judgments: there's no concept "
        "relevance-judgments in this book",
        "concepts.toml:36: precision-at-k: W-80: 'explains' isn't a relation type; use one of broader, narrower, "
        "part-of, measured-from, computed-from, prerequisite-of, contrasts-with, implemented-by, same-as, close-to, "
        "maps-to, defined-by-organization",
        "concepts.toml:95: discount: W-80: discount is part-of itself"]   # a line down: "explains" is one more


def test_a_reference_to_another_context_is_well_formed_and_one_in_its_own_context_exists(tmp_path):
    book = sampler(tmp_path, edit=[('part-of = ["search-and-recommendation/dcg"]', 'part-of = ["graded-relevance/dcg"]'),
                                   ('close-to = ["https://rollingedition.com/concepts/machine-learning/label"]',
                                    'close-to = ["https://rollingedition.com/concepts/machine-learning/label@2026.11.1", '
                                    '"https://example.com/label", "kitchen/label"]')])
    assert problems(book) == [
        "concepts.toml:25: relevance-judgment: W-80: close-to "
        "https://rollingedition.com/concepts/machine-learning/label@2026.11.1: machine-learning/label@2026.11.1: point "
        "at a concept's address, never at one edition of it",
        "concepts.toml:25: relevance-judgment: W-80: close-to https://example.com/label: https://example.com/label isn't "
        "a concept's address: it starts https://rollingedition.com/concepts/",
        "concepts.toml:25: relevance-judgment: W-80: close-to kitchen/label: 'kitchen' isn't a context: a taxonomy area "
        "or skill, or one declared here",
        "concepts.toml:73: gain: W-80: part-of graded-relevance/dcg: there's no concept dcg in graded-relevance in this "
        "book"]


def test_same_as_and_close_to_point_at_another_context_or_wikidata(tmp_path):
    book = sampler(tmp_path, edit=('close-to = ["wikidata:Q25211005"]', 'close-to = ["ndcg", "wikidata:Q25211005"]'))
    assert problems(book) == [
        "concepts.toml:63: ranking-metric: W-80: close-to links to another context's concept, or to a Wikidata item "
        "(wikidata:Q…); in one context, two concepts that mean the same are one concept"]


def test_prerequisites_and_the_hierarchy_never_go_round_in_a_circle(tmp_path):
    book = sampler(tmp_path, edit=[('[concepts.relations]\ncomputed-from = ["dcg"]',
                                    '[concepts.relations]\ncomputed-from = ["dcg"]\nprerequisite-of = ["relevance"]'),
                                   ('narrower = ["ndcg"]', 'narrower = ["ndcg"]\nbroader = ["precision-at-k"]')])
    assert problems(book) == [                          # each circle once, from its least concept
        "concepts.toml:36: precision-at-k: W-80: broader goes round in a circle: precision-at-k → ranking-metric → "
        "precision-at-k (narrower counted the other way round)",
        "concepts.toml:104: ndcg: W-80: prerequisite-of goes round in a circle: ndcg → relevance → relevance-judgment → "
        "precision-at-k → ndcg"]


def test_a_version_range_goes_with_implemented_by_and_holds_the_pin(tmp_path):
    book = sampler(tmp_path, edit=[('versions = ">=1.5"', 'versions = ">=1.8"'),
                                   ('part-of = ["dcg"]', 'part-of = [{ to = "dcg", versions = ">=1" }]')])
    assert problems(book) == [
        "concepts.toml:94: discount: W-80: a version range goes with implemented-by, the package's; part-of dcg has one",
        "concepts.toml:103: ndcg: W-80: implemented-by scikit-learn >=1.8, and the book pins scikit-learn 1.7.2: say the "
        "range the relation holds within, or the definition the new version needs"]
    book = sampler(tmp_path / "range", edit=('versions = ">=1.5"', 'versions = "one point five"'))
    assert problems(book) == ["concepts.toml:103: ndcg: W-80: scikit-learn's versions 'one point five' isn't a version "
                              "range, such as \">=0.3,<0.4\""]


def test_the_types_reserved_for_organizations_are_refused_in_a_book(tmp_path):
    book = sampler(tmp_path, edit=('part-of = ["dcg"]', 'part-of = ["dcg"]\nmaps-to = ["dcg"]'))
    assert problems(book) == ["concepts.toml:94: discount: W-80: maps-to is for an organization's own concepts, never a "
                              "book's"]


# ---------------------------------------------------------------- an organization's file


def test_an_organization_s_file_has_its_own_namespace_and_points_at_ours():
    cs = concepts.load(ORGANIZATION)
    assert cs.problems == [] and not cs.ours and cs.namespace == "example-org"
    assert cs.address("search-team", "search-quality") == "https://concepts.example.com/search-team/search-quality"
    assert concepts.context_problems(cs) == [] and concepts.relation_problems(cs, concepts.known_contexts(cs)) == []
    assert concepts.known_contexts(cs) == {"search-team"}                # never ours: its concepts live in its own
    target, _ = concepts.resolve(cs, "https://rollingedition.com/concepts/search-and-recommendation/ndcg", "search-team",
                                 concepts.known_contexts(cs))
    assert (target.namespace, target.context, target.id, target.local) == ("rollingedition", "search-and-recommendation",
                                                                           "ndcg", False)
    sources = {"metrics-handbook": "For dashboards, **Search quality** is nDCG at 10 over last month's judged queries.",
               "runbook": "An active index is one rebuilt in the last 24 hours."}
    assert concepts.quote_problems(cs, sources.get) == []               # its own documents stand in for a book's sections


def test_an_organization_s_namespace_names_its_own_base():
    cs = concepts.parse('[namespace]\nid = "acme"\n')
    assert cs.problems == ["concepts.toml: an organization's namespace names its own base, an https:// address under "
                           "which its concepts' addresses go"]
    assert concepts.parse('[namespace]\nid = "rollingedition"\nbase = "https://example.com"\n').problems == [
        "concepts.toml: our namespace's base is https://rollingedition.com/concepts"]


# ---------------------------------------------------------------- served


def test_served_gives_each_concept_its_addresses_versions_edition_and_provenance():
    book = bookfmt.load_book(SAMPLER)
    base = "https://rollingedition.com/concepts"
    records = concepts.served(book, "2026.11.8", changed={f"{base}/search-and-recommendation/ndcg":
                                                          {"first": "2026.10.1", "changed": "2026.11.3"}},
                              commit="a" * 40)
    by_id = {r["id"]: r for r in records}
    ndcg = by_id["ndcg"]
    assert ndcg["address"] == f"{base}/search-and-recommendation/ndcg"
    assert ndcg["edition_address"] == f"{base}/search-and-recommendation/ndcg@2026.11.8"
    assert ndcg["context_address"] == f"{base}/search-and-recommendation" and ndcg["namespace"] == "rollingedition"
    assert ndcg["applies_to"] == [{"package": "scikit-learn", "version": "1.7.2"}]
    assert (ndcg["edition"], ndcg["first_edition"], ndcg["changed_edition"]) == ("2026.11.8", "2026.10.1", "2026.11.3")
    assert ndcg["section"] == {"id": "ndcg", "chapter": "graded-gains", "title": "Normalize by the ideal ranking",
                               "link": None}
    assert ndcg["provenance"] == {"book": "concepts-sampler", "file": "concepts.toml", "section": "ndcg",
                                  "edition": "2026.11.8", "commit": "a" * 40, "checked_by": "re-check concepts",
                                  "checked_at": None}
    assert {"type": "implemented-by", "skos": None, "property": "implementedBy", "package": "scikit-learn",
            "versions": ">=1.5", "version": "1.7.2"} in ndcg["relations"]
    assert {"type": "computed-from", "skos": "skos:related", "property": "computedFrom",
            "target": f"{base}/search-and-recommendation/dcg"} in ndcg["relations"]
    judgment = by_id["relevance-judgment"]
    assert judgment["definition"] == "A relevance judgment is a person's label for one pair of a query and a result."
    assert judgment["first_edition"] == judgment["changed_edition"] == "2026.11.8"     # new in this edition
    assert by_id["relevance"]["wikidata"] == "https://www.wikidata.org/entity/Q1472529"
    assert {"type": "same-as", "skos": "skos:exactMatch", "property": "sameAs",
            "target": "https://www.wikidata.org/entity/Q1472529"} in by_id["relevance"]["relations"]
    assert by_id["gain"]["relations"][0]["target"] == f"{base}/search-and-recommendation/dcg"
    assert concepts.served(book, "2026.11.8", commit="a" * 40) == concepts.served(book, "2026.11.8", commit="a" * 40)


def test_served_binds_a_definition_and_a_terminal_book_s_versions_come_from_its_stack(tmp_path):
    root = tmp_path / "bound"
    shutil.copytree(SAMPLER, root)
    chapter = root / "chapters" / "02-graded-gains.md"
    chapter.write_text(chapter.read_text().replace("At scikit-learn {{version:scikit-learn}}, `ndcg_score` uses",
                                                   "**ndcg_score** scores at scikit-learn {{version:scikit-learn}} and uses"))
    (root / concepts.FILE).write_text((root / concepts.FILE).read_text() + '''
[[concepts]]
id = "ndcg-score"
term = "ndcg_score"
definition = "ndcg_score scores at scikit-learn {{version:scikit-learn}}"
section = "ndcg"
''')
    book = bookfmt.load_book(root)
    assert concepts.check(book) == ([], [])
    (record,) = [r for r in concepts.served(book, "2026.11.8") if r["id"] == "ndcg-score"]
    assert record["definition"] == "ndcg_score scores at scikit-learn 1.7.2"
    terminal = FIXTURES / "k3s-sampler"
    pins = bookfmt.load_book(terminal).pins
    tool = next(name for name in ("kubectl", "k3s") if name in pins)
    copy = tmp_path / "terminal"
    shutil.copytree(terminal, copy)
    first = bookfmt.load_book(copy).sections[0]
    words = concepts.squash(" ".join(b.text for b in concepts.blocks(first.source) if b.kind == "prose"))
    sentence = words.split(". ")[0]
    (copy / concepts.FILE).write_text(f'''context = "cloud-computing"

[[concepts]]
id = "first-idea"
term = "first idea"
definition = "{sentence}"
section = "{first.section_id}"
applies_to = ["{tool}"]
''')
    book = bookfmt.load_book(copy)
    assert concepts.check(book)[0] == []
    assert concepts.served(book, "2026.11.1")[0]["applies_to"] == [{"package": tool, "version": pins[tool]}]


def test_served_gives_each_section_its_permanent_link_and_the_check_its_time():
    book = bookfmt.load_book(SAMPLER)
    records = concepts.served(book, "2026.11.8", commit="b" * 40, link=lambda unit: f"https://example.com/s/{unit}",
                              checked_at="2026-11-19T08:00:00Z")
    ndcg = next(r for r in records if r["id"] == "ndcg")
    assert ndcg["section"]["link"] == "https://example.com/s/ndcg"
    assert ndcg["provenance"]["checked_at"] == "2026-11-19T08:00:00Z"
    opening = next(r for r in records if r["id"] == "relevance")          # defined in a chapter's opening
    assert opening["section"] == {"id": "scoring-a-ranking", "chapter": "scoring-a-ranking", "title": "Scoring a ranking",
                                  "link": "https://example.com/s/scoring-a-ranking"}


# ---------------------------------------------------------------- an edition's records, and the next one's


def edition(book, name, previous=None):
    return concepts.edition_record(book, name, concepts.carry(concepts.served(book, name), previous))


def test_carry_keeps_a_concept_s_first_edition_and_moves_its_changed_edition_only_when_its_meaning_changes(tmp_path):
    first = edition(bookfmt.load_book(SAMPLER), "2026.11.1")
    assert {(r["first_edition"], r["changed_edition"]) for r in first["concepts"]} == {("2026.11.1", "2026.11.1")}
    same = edition(bookfmt.load_book(SAMPLER), "2026.11.2", first["concepts"])
    assert {(r["first_edition"], r["changed_edition"]) for r in same["concepts"]} == {("2026.11.1", "2026.11.1")}
    # nDCG's alias and the discount's relation change; the gain's section moves without its words, which is no change
    book = sampler(tmp_path, edit=[('aliases = ["nDCG", "nDCG@k"]', 'aliases = ["nDCG", "nDCG@k", "NDCG"]'),
                                   ('part-of = ["dcg"]', 'part-of = ["dcg"]\nprerequisite-of = ["ndcg"]')])
    third = edition(book, "2026.11.3", same["concepts"])
    changed = {r["id"]: (r["first_edition"], r["changed_edition"]) for r in third["concepts"]}
    assert changed["ndcg"] == changed["discount"] == ("2026.11.1", "2026.11.3")
    assert changed["dcg"] == ("2026.11.1", "2026.11.1")
    fourth = edition(book, "2026.11.4", third["concepts"])
    assert {r["id"]: r["changed_edition"] for r in fourth["concepts"]}["ndcg"] == "2026.11.3"   # kept, once changed
    ndcg = next(r for r in third["concepts"] if r["id"] == "ndcg")
    moved = dict(ndcg, section={"id": "elsewhere"}, edition="2027.1.1", example=None,
                 applies_to=[{"package": "scikit-learn", "version": "9.9"}])
    assert concepts.meaning(moved) == concepts.meaning(ndcg)            # where and at which version: not its meaning
    assert concepts.meaning(dict(ndcg, applies_to=[])) != concepts.meaning(ndcg)


def test_an_edition_stores_its_records_and_retired_addresses_and_only_the_addresses_are_public():
    book = bookfmt.load_book(SAMPLER)
    record = edition(book, "2026.11.8")
    base = "https://rollingedition.com/concepts/search-and-recommendation"
    assert record["book"] == "concepts-sampler" and record["edition"] == "2026.11.8" and len(record["concepts"]) == 9
    assert record["retired"] == {f"{base}/normalized-gain": f"{base}/ndcg"}
    public = concepts.addresses(record)
    assert public == {"schema": 1, "book": "concepts-sampler", "edition": "2026.11.8",
                      "addresses": sorted(r["address"] for r in record["concepts"]), "retired": record["retired"]}
    assert "definition" not in str(public)
    for shape in (record, public):
        got = concepts.released(shape)
        assert got.edition == "2026.11.8" and got.retired == record["retired"]
        assert got.addresses == {r["address"] for r in record["concepts"]}
    assert concepts.released({"nothing": 1}) is None and concepts.released(None) is None


# ---------------------------------------------------------------- frozen addresses


def released_with(*extra: str, retired: dict | None = None, edition_name: str = "2026.11.8"):
    record = edition(bookfmt.load_book(SAMPLER), edition_name)
    public = concepts.addresses(record)
    public["addresses"] += [f"https://rollingedition.com/concepts/{a}" for a in extra]
    public["retired"].update(retired or {})
    return concepts.released(public)


def test_a_released_concept_s_address_never_goes_and_a_retired_one_stays_retired(tmp_path):
    book = bookfmt.load_book(SAMPLER)
    assert concepts.check(book, previous=released_with()) == ([], [])
    gone = sampler(tmp_path / "gone", edit=('id = "discount"', 'id = "the-discount"'))
    found = problems_with(gone, released_with())
    assert found == ["concepts.toml: W-78: search-and-recommendation/discount was released in Edition 2026.11.8, and a "
                     "concept's address is permanent (https://rollingedition.com/concepts/search-and-recommendation/"
                     "discount): keep its context and ID, or retire it to the concept that replaces it, as "
                     "\"search-and-recommendation/discount\" = \"…\" under [retired]"]
    retired = sampler(tmp_path / "retired", edit=[('id = "discount"', 'id = "the-discount"'),
                                                 ('"normalized-gain" = "ndcg"',
                                                  '"normalized-gain" = "ndcg"\n"discount" = "the-discount"')])
    assert problems_with(retired, released_with()) == []
    # the edition before had retired an address this one drops from [retired]
    unretired = sampler(tmp_path / "unretired", edit=('"normalized-gain" = "ndcg"', ''))
    assert [p.split(" was released")[0] for p in problems_with(unretired, released_with())] == [
        "concepts.toml: W-78: search-and-recommendation/normalized-gain"]
    # one the edition before had retired may come back as a concept
    back = sampler(tmp_path / "back", edit=('"normalized-gain" = "ndcg"', ''))
    assert problems_with(back, released_with(retired={
        "https://rollingedition.com/concepts/search-and-recommendation/ranking-metric":
        "https://rollingedition.com/concepts/search-and-recommendation/ndcg"})) == \
        [p for p in problems_with(back, released_with()) if "normalized-gain" in p]
    # a book that loses its concepts.toml after releasing them keeps the addresses too
    lost = sampler(tmp_path / "lost")
    (lost.root / concepts.FILE).unlink()
    lost = bookfmt.load_book(lost.root)
    found, _ = concepts.check(lost, previous=released_with())
    assert len(found) == 10 and all("a concept's address is permanent" in p for p in found)


def problems_with(book, previous):
    return concepts.check(book, previous=previous)[0]


def test_retired_names_a_successor_the_book_defines_and_never_a_concept_it_still_has(tmp_path):
    book = sampler(tmp_path, edit=('"normalized-gain" = "ndcg"',
                                   '"normalized-gain" = "nothing-here"\n"dcg" = "ndcg"\n"elsewhere/x" = "ndcg"\n'
                                   '"Bad ID" = "ndcg"'))
    assert problems(book) == [
        "concepts.toml: [retired] 'Bad ID': a retired concept and its successor are each an ID in the file's context, "
        "or context/ID",
        "concepts.toml: [retired] search-and-recommendation/normalized-gain: W-78: its successor "
        "search-and-recommendation/nothing-here isn't a concept here: a retired concept's address goes to one this book "
        "defines",
        "concepts.toml: [retired] search-and-recommendation/dcg: W-78: it's retired and defined here too: take it out of "
        "[retired], since its address is a concept again",
        "concepts.toml: [retired] elsewhere/x: W-78: 'elsewhere' isn't a context: a taxonomy area or skill, or one declared here"]
    assert problems(sampler(tmp_path / "table", edit=[('[retired]\n"normalized-gain" = "ndcg"', ''),
                                                      ('context = "search-and-recommendation"',
                                                       'retired = "ndcg"\ncontext = "search-and-recommendation"')])) == [
        "concepts.toml: [retired] maps each retired concept to its successor, such as \"recall\" = \"recall-at-k\""]


def test_no_context_may_take_the_vocabulary_s_address(tmp_path):
    assert concepts.vocabulary_segment() == "vocabulary"
    found = problems(sampler(tmp_path, edit=('id = "graded-relevance"\nbroader', 'id = "vocabulary"\nbroader')))
    assert ("concepts.toml:7: vocabulary is the address of our vocabulary, "
            "https://rollingedition.com/concepts/vocabulary#, so no context may take it") in found


def test_the_command_line_reads_the_edition_before_from_its_addresses_its_record_or_beside_its_sections(tmp_path, capsys):
    record = edition(bookfmt.load_book(SAMPLER), "2026.11.8")
    record["concepts"].append(dict(record["concepts"][0], address="https://rollingedition.com/concepts/"
                                                                  "search-and-recommendation/gone"))
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "sections.json").write_text("{}")
    (bundle / "concepts.json").write_text(__import__("json").dumps(record))
    public = tmp_path / "concept-addresses.json"
    public.write_text(__import__("json").dumps(concepts.addresses(record)))
    for source in (str(bundle / "sections.json"), str(bundle / "concepts.json"), str(public)):
        assert cli.main(["concepts", "--book", str(SAMPLER), "--previous", source]) == 1
        assert "search-and-recommendation/gone was released in Edition 2026.11.8" in capsys.readouterr().err
    ok = tmp_path / "ok.json"
    ok.write_text(__import__("json").dumps(concepts.addresses(edition(bookfmt.load_book(SAMPLER), "2026.11.8"))))
    assert cli.main(["concepts", "--book", str(SAMPLER), "--previous", str(ok)]) == 0
    assert "every address Edition 2026.11.8 released still answers" in capsys.readouterr().out
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "sections.json").write_text("{}")                   # an edition before concepts: nothing beside it
    for source in (str(empty / "sections.json"), "none"):
        assert cli.main(["concepts", "--book", str(SAMPLER), "--previous", source]) == 0
        assert "no released edition with concepts yet" in capsys.readouterr().out or source == "none"
    assert checks.latest_concepts_url("concepts-sampler") == \
        "https://rollingedition.ai/books/concepts-sampler/latest/concept-addresses.json"


def test_a_book_without_concepts_fetches_nothing_for_latest(tmp_path, monkeypatch, capsys):
    book = bookfmt.load_book(make_book(tmp_path / "tiny"))
    monkeypatch.setattr(checks, "load_previous_manifest", lambda source: pytest.fail(f"fetched {source}"))
    assert cli.main(["concepts", "--book", str(book.root), "--previous", "latest"]) == 0
    assert "no concepts.toml" in capsys.readouterr().out


# ---------------------------------------------------------------- the checks' place


def test_the_book_checks_workflow_runs_it_and_a_change_to_concepts_alone_rides_along():
    flow = yaml.safe_load((standards_root() / ".github" / "workflows" / "book-checks.yml").read_text())
    runs = [s.get("run", "") for s in flow["jobs"]["manifest"]["steps"]]
    assert 're-check concepts --book . --previous "${RE_PREVIOUS_SECTIONS:-latest}" --library latest' in runs
    with open(data_path("review-tiers.toml"), "rb") as f:
        assert tomllib.load(f)["files"]["concepts"] == [concepts.FILE]
    assert checks.rides_along([concepts.FILE]) and checks.check_kind_label([], [concepts.FILE]) == []
    assert checks.riding_words([concepts.FILE, "skill.md"]) == "the agent skill's procedures and the book's concepts"
    assert not checks.rides_along([concepts.FILE, "chapters/01-scoring-a-ranking.md"])


def test_the_rules_are_dated_and_their_problems_name_them():
    days = rules.dated()
    assert all(f"W-{n}" in days for n in range(77, 81))
    text = (standards_root() / "writing" / "README.md").read_text()
    assert all(f"**W-{n} " in text for n in range(77, 81)) and "## 16. Concepts" in text


@pytest.mark.parametrize("rule", ["W-77", "W-78", "W-79", "W-80"])
def test_each_rule_s_problems_lead_with_its_id(rule, tmp_path):
    edits = {"W-77": ('section = "ranking-metrics"', 'section = "metrics"'),
             "W-78": ('aliases = ["recall@k"]', 'aliases = ["recall@k", "precision@k"]'),
             "W-80": ('part-of = ["dcg"]', 'part-of = ["discount"]')}
    if rule == "W-79":
        found = notes(sampler(tmp_path, chapter=UNLINKED))
    else:
        found = problems(sampler(tmp_path, edit=edits[rule]))
    assert found and all(rules.rule_of(p) == rule for p in found)


# ---------------------------------------------------------------- check 4, across books

BASE = "https://rollingedition.com/concepts/"
LABEL = ("ml-book", "machine-learning/label", "label", "A label is the answer a model learns to give.")   # the sampler links it


def lib(*concepts_, retired=None) -> concepts.Library:
    """A library of other books' concepts, (book, context/id, term, definition), with the one the sampler links to."""
    books: dict = {}
    for book, ref, term, definition in (LABEL, *concepts_):
        books.setdefault(book, {"edition": "2026.11.1", "retired": {}, "concepts": []})["concepts"].append(
            {"address": BASE + ref, "term": term, "aliases": [], "definition": definition, "first_edition": "2026.11.1"})
    for book, old, new in retired or []:
        books.setdefault(book, {"edition": "2026.11.1", "retired": {}, "concepts": []})["retired"][BASE + old] = BASE + new
    return concepts.library({"schema": concepts.LIBRARY_SCHEMA, "books": books})


def across(book, library, released=None, fails=True, monkeypatch=None):
    if monkeypatch:
        monkeypatch.setitem(concepts.settings(), "library", {"fails": fails})
    return concepts.library_problems(book.concepts, book.slug, library, concepts.known_contexts(book.concepts), released)


def line_of(book, cid) -> int:
    return next(c.line for c in book.concepts if c.id == cid)


NDCG = ("another-search-book", "search-and-recommendation/ndcg", "nDCG", "nDCG divides DCG by the DCG of the ideal ranking.")
DCG = ("third-book", "search-and-recommendation/dcg", "DCG", "DCG adds up discounted gains.")


def test_a_new_concept_at_another_book_s_address_records_its_agreement_or_fails(tmp_path, monkeypatch):
    book = bookfmt.load_book(SAMPLER)
    found, notes = across(book, lib(NDCG, DCG), monkeypatch=monkeypatch)
    assert found == [f"concepts.toml:{line_of(book, 'dcg')}: dcg: check 4: search-and-recommendation/dcg is third-book's "
                     "too: \"DCG adds up discounted gains.\". If yours means the same, keep the address and record it, "
                     "agrees = [{ book = \"third-book\", definition = \"its sentence\" }]; if not, give yours an ID or a "
                     "context of its own"]
    assert not [n for n in notes if ": ndcg: check 4: " in n]                 # ndcg's agreement holds
    # released already, at this book's edition before: only listed, so another book's later choice never stops it
    released = concepts.Released("2026.11.1", {BASE + "search-and-recommendation/dcg"}, {})
    found, notes = across(book, lib(NDCG, DCG), released, monkeypatch=monkeypatch)
    assert found == [] and any("dcg is third-book's too" in n and "retire this address to it" in n for n in notes)


def test_an_agreement_whose_sentence_changed_or_whose_book_left_is_listed_not_failed(tmp_path, monkeypatch):
    book = bookfmt.load_book(SAMPLER)
    found, notes = across(book, lib(NDCG[:3] + ("nDCG is DCG over the ideal DCG.",)), monkeypatch=monkeypatch)
    assert found == [] and any("has changed its sentence for search-and-recommendation/ndcg" in n for n in notes)
    found, notes = across(book, lib(), monkeypatch=monkeypatch)
    assert found == [] and any("agrees names another-search-book, which doesn't define" in n for n in notes)


def test_a_link_to_another_context_names_a_released_concept_or_its_successor(tmp_path, monkeypatch):
    book = sampler(tmp_path, edit=('close-to = ["https://rollingedition.com/concepts/machine-learning/label"]',
                                   'close-to = ["https://rollingedition.com/concepts/machine-learning/old-label", '
                                   '"https://rollingedition.com/concepts/machine-learning/nowhere"]'))
    found, _ = across(book, lib(retired=[("ml-book", "machine-learning/old-label", "machine-learning/label")]),
                      monkeypatch=monkeypatch)
    assert sorted(p.split("check 4: ")[1] for p in found) == [
        "close-to machine-learning/nowhere: no released book defines it",
        "close-to machine-learning/old-label: ml-book retired it; its successor is machine-learning/label"]


def test_the_same_term_in_another_book_and_context_is_a_note_until_linked(tmp_path, monkeypatch):
    book = bookfmt.load_book(SAMPLER)
    found, notes = across(book, lib(("ml-book", "machine-learning/precision-at-k", "precision@k",
                                     "Precision at k is the share of the top k that is relevant.")), monkeypatch=monkeypatch)
    assert found == [] and any("ml-book also defines 'precision@k', as machine-learning/precision-at-k" in n for n in notes)
    assert not any("'label'" in n for n in notes)                       # linked already, with close-to


def test_until_every_book_records_its_agreements_check_4_lists_and_passes(tmp_path, monkeypatch, capsys):
    assert concepts.settings()["library"]["fails"] is False          # the founder's hard check comes after the pass
    book = bookfmt.load_book(SAMPLER)
    found, notes = across(book, lib(DCG), fails=False, monkeypatch=monkeypatch)
    assert found == [] and any("dcg is third-book's too" in n for n in notes)
    records = {}
    for b, ref, term, definition in (LABEL, NDCG, DCG):
        records.setdefault(b, {"edition": "2026.11.1", "concepts": []})["concepts"].append(
            {"address": BASE + ref, "term": term, "aliases": [], "definition": definition, "first_edition": "2026.11.1"})
    path = tmp_path / "library.json"
    path.write_text(__import__("json").dumps(concepts.library_record(records)))
    monkeypatch.setitem(concepts.settings(), "library", {"fails": True})
    assert cli.main(["concepts", "--book", str(SAMPLER), "--library", str(path)]) == 1
    assert "dcg is third-book's too" in capsys.readouterr().err
    monkeypatch.setitem(concepts.settings(), "library", {"fails": False})
    assert cli.main(["concepts", "--book", str(SAMPLER), "--library", str(path)]) == 0
    out = capsys.readouterr()
    assert "checked against 3 released book(s)" in out.out and "Concepts across books (check 4)" in out.err + out.out


def test_a_library_that_can_t_be_read_skips_check_4_and_says_so(tmp_path, capsys):
    assert cli.main(["concepts", "--book", str(SAMPLER), "--library", str(tmp_path / "missing.json")]) == 0
    assert "no library yet" in capsys.readouterr().out
