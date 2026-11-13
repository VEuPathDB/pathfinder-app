import pytest

from strategist.domain.reply_links import reference_urls, reply_links
from strategist.domain.turn_facts import SourceFact, TurnFacts

_RECORD = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1315100"
_PAPER = "https://journals.plos.org/plospathogens/article?id=10.1371/journal.ppat.1"


@pytest.mark.parametrize(
    ("reference", "urls"),
    [
        (_PAPER, [_PAPER]),
        ("10.1371/journal.ppat.1", ["https://doi.org/10.1371/journal.ppat.1"]),
        ("doi:10.1371/journal.ppat.1", ["https://doi.org/10.1371/journal.ppat.1"]),
        (
            "https://dx.doi.org/10.1371/journal.ppat.1",
            [
                "https://dx.doi.org/10.1371/journal.ppat.1",
                "https://doi.org/10.1371/journal.ppat.1",
            ],
        ),
        ("38500000", ["https://pubmed.ncbi.nlm.nih.gov/38500000/"]),
        ("PMID:38500000", ["https://pubmed.ncbi.nlm.nih.gov/38500000/"]),
        ("javascript:alert(1)", []),
        ("mailto:curator@example.org", []),
        ("www.example.org", []),
    ],
)
def test_a_reference_links_by_its_web_forms(reference: str, urls: list[str]) -> None:
    assert reference_urls(reference) == urls


def test_a_reply_links_the_records_it_can_cite_and_the_sources_read() -> None:
    facts = TurnFacts(sources=[SourceFact(url=_RECORD, record_id="PF3D7_1315100")])

    links = reply_links(facts, ["38500000", _PAPER, "38500000"])

    assert links.links == [
        _RECORD,
        "https://pubmed.ncbi.nlm.nih.gov/38500000/",
        _PAPER,
    ]


def test_a_reply_with_nothing_read_links_nothing() -> None:
    assert reply_links(TurnFacts(), []).links == []
