from strategist.domain.reply_note import linked_records, render_note
from strategist.domain.turn_facts import SourceFact, StepFact, TurnFacts

_URL = "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_1315100"
_READ = TurnFacts(
    steps=[StepFact(step_id="step_sp", display_name="Signal Peptide", count=479)],
    root_count=479,
    sources=[SourceFact(url=_URL, record_id="PF3D7_1315100", product="PK9")],
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


def test_the_note_keeps_the_markdown_the_model_wrote() -> None:
    note = (
        "## Reading\n\n- **SignalP 6.0** finds [record:PF3D7_1315100]\n- `code` stays"
    )

    assert render_note(note, _READ) == (
        f"## Reading\n\n- **SignalP 6.0** finds [PF3D7_1315100]({_URL})\n- `code` stays"
    )
