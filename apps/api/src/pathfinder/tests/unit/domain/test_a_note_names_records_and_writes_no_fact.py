from pathfinder.domain.reply_note import linked_records, note_facts, render_note
from pathfinder.domain.turn_facts import SourceFact, StepFact, TurnFacts

_URL = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1315100"
_READ = TurnFacts(
    steps=[StepFact(step_id="step_sp", display_name="Signal Peptide", count=479)],
    root_count=479,
    sources=[SourceFact(url=_URL, record_id="PF3D7_1315100", product="PK9")],
    request_messages=["Find the top 10 kinase genes in P. falciparum 3D7."],
)


def test_a_held_record_renders_as_its_link() -> None:
    note = "Start with [record:PF3D7_1315100], a well-studied kinase."

    assert render_note(note, _READ) == (
        f"Start with [PF3D7_1315100]({_URL}), a well-studied kinase."
    )


def test_a_record_the_turn_does_not_hold_is_dropped() -> None:
    note = "Compare it with [record:PF3D7_9999999]."

    assert render_note(note, _READ) == "Compare it with."


def test_the_rendered_note_names_the_records_it_links() -> None:
    rendered = render_note("[record:PF3D7_1315100] and [record:PF3D7_1315100].", _READ)

    assert linked_records(rendered) == ["PF3D7_1315100"]


def test_a_note_beside_the_facts_writes_no_number_of_its_own() -> None:
    note = (
        "The 479 genes carry a predicted signal peptide; about 12% are exported. "
        "SignalP-6.0 marks them in 3D7, and the top 10 by score are a place to start."
    )

    assert note_facts(note, _READ) == ["479", "12%"]


def test_a_name_with_digits_is_prose() -> None:
    note = "SignalP-6.0 reads PfEMP1 in 3D7, ME49 and NF54, and GO:0016301 names it."

    assert note_facts(note, _READ) == []


def test_a_record_reference_and_a_list_mark_are_no_number() -> None:
    note = "1. Read [record:PF3D7_1315100].\n2. Then decide."

    assert note_facts(note, _READ) == []


def test_a_link_beside_the_facts_is_written_by_the_facts() -> None:
    note = f"See {_URL} and doi:10.1000/invented.2026.99 for the exons."

    assert note_facts(note, _READ) == [_URL, "doi:10.1000/invented.2026.99"]


def test_a_turn_that_read_no_site_data_writes_freely() -> None:
    assert note_facts("A genome of 23 Mb holds 14 chromosomes.", TurnFacts()) == []
