import pytest

from strategist.domain.read_facts import ReadFact, ReadRow, read_fact
from strategist.domain.reply_note import linked_records, render_note
from strategist.domain.statistic_facts import StatisticFact, StatisticRowFact
from strategist.domain.turn_facts import SourceFact, TurnFacts
from strategist.domain.written_links import written_links

_URL = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1315100"
_RECORD_LINK = f"[PF3D7_1315100]({_URL})"
_HELD = TurnFacts(sources=[SourceFact(url=_URL, record_id="PF3D7_1315100")])


@pytest.mark.parametrize(
    "note",
    [
        "[x][r]\n\n[r]: http://evil.example",
        "Run javascript:alert(1) now.",
        'A ![chart](https://evil.example/c.png) and <a href="https://evil.example">x</a>.',
        "Write to <mailto:curator@example.org> or www.evil.example.",
    ],
)
def test_the_note_writes_no_link_of_its_own_beside_the_record_links(
    note: str,
) -> None:
    rendered = render_note(f"Start with [record:PF3D7_1315100]. {note}", _HELD)

    assert (linked_records(rendered), rendered) == (
        ["PF3D7_1315100"],
        f"Start with {_RECORD_LINK}. {note}",
    )


def test_a_record_the_turn_does_not_hold_renders_no_link() -> None:
    rendered = render_note("Compare it with [record:PF3D7_9999999].", _HELD)

    assert (linked_records(rendered), rendered) == ([], "Compare it with.")


def test_every_link_shape_a_text_writes_is_found() -> None:
    note = (
        "See [it](&#104;ttps://evil.example/x), https:\\\\evil.com, "
        "javascript:alert(1) and <mailto:a@example.org>."
    )

    assert written_links(note) == [
        "https://evil.example/x",
        "mailto:a@example.org",
        "https:\\\\evil.com",
        "javascript:alert(1)",
    ]


def test_a_fact_row_that_holds_a_link_is_not_shown() -> None:
    fact = StatisticFact(
        id="stat_1",
        kind="gene_check",
        title="A check",
        rows=[
            StatisticRowFact(name="cause", value="[x](http://evil.example)"),
            StatisticRowFact(name="genome", value="Examplea alpha A"),
        ],
    )

    assert read_fact(fact).rows == [ReadRow(label="genome", value="Examplea alpha A")]


def test_a_fact_is_plain_text_in_markdown() -> None:
    fact = ReadFact(
        title="Finding *1* [run]", rows=[ReadRow(label="cause", value="(b)")]
    )

    assert fact.markdown() == "**Finding \\*1\\* \\[run\\]**\n- cause: \\(b\\)"
