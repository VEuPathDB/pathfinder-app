from pathfinder.domain.read_facts import ReadFact, ReadRow, read_fact
from pathfinder.domain.reply_note import note_facts, render_note
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.domain.turn_facts import SourceFact, TurnFacts
from pathfinder.domain.written_links import written_links

_URL = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1315100"
_HELD = TurnFacts(sources=[SourceFact(url=_URL, record_id="PF3D7_1315100")])


def test_a_javascript_link_is_found_and_shown_as_its_words() -> None:
    note = "Open [the record](javascript:alert(1)) for the exons."

    assert (note_facts(note, TurnFacts()), render_note(note, TurnFacts())) == (
        ["javascript:alert(1)"],
        "Open the record for the exons.",
    )


def test_a_mailto_link_and_an_autolink_are_found_and_dropped() -> None:
    note = "Write to <mailto:curator@example.org> or mailto:curator@example.org now."

    assert (written_links(note), render_note(note, TurnFacts())) == (
        ["mailto:curator@example.org", "mailto:curator@example.org"],
        "Write to  or  now.",
    )


def test_an_entity_encoded_link_is_decoded_before_it_is_read() -> None:
    note = "See [it](&#104;ttps://evil.example/x) and h&#116;tps://evil.example/y."

    assert (written_links(note), render_note(note, TurnFacts())) == (
        ["https://evil.example/x", "https://evil.example/y"],
        "See it and .",
    )


def test_an_image_and_an_html_link_are_dropped() -> None:
    note = 'A ![chart](https://evil.example/c.png) and <a href="https://evil.example">x</a>.'

    assert render_note(note, TurnFacts()) == "A chart and x</a>."


def test_only_the_link_a_record_reference_renders_reaches_the_reader() -> None:
    note = f"Start with [record:PF3D7_1315100], not [this]({_URL}) or {_URL}."

    assert render_note(note, _HELD) == (
        f"Start with [PF3D7_1315100]({_URL}), not this or ."
    )


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


def test_a_fact_is_escaped_in_markdown() -> None:
    fact = ReadFact(
        title="Finding *1* [run]",
        rows=[ReadRow(label="cause <b>", value="kept `a` (b) !c")],
    )

    assert fact.markdown() == (
        "**Finding \\*1\\* \\[run\\]**\n- cause \\<b\\>: kept \\`a\\` \\(b\\) \\!c"
    )
