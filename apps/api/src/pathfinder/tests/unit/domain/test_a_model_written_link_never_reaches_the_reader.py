import re

import pytest

from pathfinder.domain.read_facts import ReadFact, ReadRow, read_fact
from pathfinder.domain.reply_note import linked_records, note_facts, render_note
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.turn_facts import SourceFact, TurnFacts
from pathfinder.domain.written_links import written_links

_URL = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1315100"
_RECORD_LINK = f"[PF3D7_1315100]({_URL})"
_HELD = TurnFacts(sources=[SourceFact(url=_URL, record_id="PF3D7_1315100")])
_UNESCAPED = re.compile(r"(?<!\\)(?:\\\\)*[!-/:-@\[-`{-~]")


def _unescaped_marks(rendered: str) -> list[str]:
    plain = rendered.replace(_RECORD_LINK, "")
    marks = (m.group()[-1] for m in _UNESCAPED.finditer(plain))
    return [mark for mark in marks if mark != "\\"]


@pytest.mark.parametrize(
    "note",
    [
        "[x][r]\n\n[r]: http://evil.example",
        "Go to https:\\\\evil.com now.",
        "Run javascript:alert(1) now.",
        "&#91;x&#93;(http://evil.example)",
        "A nested [[x](a)](b) link.",
        'A ![chart](https://evil.example/c.png) and <a href="https://evil.example">x</a>.',
        "Write to <mailto:curator@example.org> or www.evil.example.",
        "*bold* `code` _under_ # head | pipe & amp",
    ],
)
def test_the_rendered_note_holds_no_link_but_the_record_links(note: str) -> None:
    rendered = render_note(f"Start with [record:PF3D7_1315100]. {note}", _HELD)

    assert (linked_records(rendered), _unescaped_marks(rendered)) == (
        ["PF3D7_1315100"],
        [],
    )


def test_a_record_the_turn_does_not_hold_renders_no_link() -> None:
    rendered = render_note("Compare it with [record:PF3D7_9999999].", _HELD)

    assert (linked_records(rendered), rendered) == ([], "Compare it with\\.")


def test_the_links_a_note_writes_are_found_for_its_correction() -> None:
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


def test_a_note_with_no_site_data_still_writes_no_link() -> None:
    assert note_facts("See www.example.org and 14 chromosomes.", TurnFacts()) == [
        "www.example.org"
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
