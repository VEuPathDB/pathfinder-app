"""The comparison arc reads its group variable from the sheet the Lead pins."""

from __future__ import annotations

from pydantic_ai.messages import ModelMessage, ModelRequest, UserPromptPart

from strategist.ai.lead.lead_pins import pinned_eda_sheet
from strategist.ai.models.mock.eda_arc import group_variables
from strategist.domain.eda_parts import EdaFilterSheetEntry, OpenEdaSheet
from strategist.tests._support.run_context import lead_run_context

SAMPLE = "EUPATH_0000609"
STAGE = EdaFilterSheetEntry(
    entity_id=SAMPLE,
    variable_id="EUPATH_0000700",
    display_name="Life cycle stage",
    filter_type="stringSet",
    vocabulary=["Ring", "Trophozoite"],
)


def _pinned(description: str) -> list[ModelMessage]:
    ctx = lead_run_context()
    ctx.deps.state.domain.pin_eda_sheet(
        OpenEdaSheet(
            dataset_id="DS_compare",
            entries=[STAGE],
            study_description=description,
        )
    )
    return [
        ModelRequest(
            parts=[UserPromptPart(content="compare")],
            instructions=pinned_eda_sheet(ctx),
        )
    ]


def test_a_described_study_gives_its_group_variable() -> None:
    messages = _pinned("Illumina reads of 16h Ring and 16h Trophozoite.")

    assert group_variables(messages, [SAMPLE]) == [STAGE]


def test_an_undescribed_study_gives_its_group_variable() -> None:
    assert group_variables(_pinned(""), [SAMPLE]) == [STAGE]
