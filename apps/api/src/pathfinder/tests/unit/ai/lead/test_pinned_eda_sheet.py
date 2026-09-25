"""The EDA filter sheets the Lead holds open, pinned into its own instructions."""

from __future__ import annotations

import ast
from pathlib import Path
from types import ModuleType

import pytest
from assistant_core.conversation.history import elide_consumed
from pydantic_ai import RunContext
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from veupathdb.eda import EdaPermissionEntry, EdaStudyDetail

from pathfinder.ai.agents.pinned_sheets import PINNED_SHEETS_MAX_CHARS
from pathfinder.ai.graph import state
from pathfinder.ai.lead import lead_pins
from pathfinder.ai.lead.lead_pins import pinned_eda_sheet
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.ai.tools.standalone._eda_models import (
    EdaAnalysisOpened,
    EdaFiltersResult,
)
from pathfinder.domain.eda_parts import EdaAnalysisState, EdaFilterSheetEntry
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.services.eda import binding
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    RevisionCounter,
    permission_entry,
    phenotype_study,
    study_of,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
)
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

SHEET_VARIABLES = 13
SHEET_VALUES = 55
OTHER_DATASET = "DS_eeca6a5476"


@pytest.fixture
def lead_ctx() -> RunContext[LeadDeps]:
    return lead_run_context()


@pytest.fixture(autouse=True)
def revisions(monkeypatch: pytest.MonkeyPatch) -> RevisionCounter:
    counter = RevisionCounter()
    monkeypatch.setattr(binding, "bump_analysis_revision", counter.bump)
    return counter


async def _bound(_ctx: object) -> ConversationAnalysisView:
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=PHENOTYPE_DATASET,
        analysis_id=ANALYSIS_ID,
        revision=1,
    )


async def _applied(
    _site: str,
    *,
    conversation_id: object,
    analysis_id: str,
    dataset_id: str,
    filters: object,
) -> EdaAnalysisState:
    del conversation_id, analysis_id, filters
    return EdaAnalysisState(
        site_id="plasmodb",
        dataset_id=dataset_id,
        study_id=PHENOTYPE_STUDY,
        analysis_id=ANALYSIS_ID,
        revision=2,
        study_display_name="Rodent malaria phenotypes",
        display_name="berghei subset",
        num_filters=1,
        num_computations=0,
        filters=[],
        filter_summaries=["Species is one of P. berghei"],
        entity_counts=[],
        can_export_rows=False,
    )


def serve_phenotype_study(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", phenotype_study)
    monkeypatch.setattr(eda_analysis, "bound_analysis", _bound)


def _pair(tool: str, call_id: str, content: object) -> list[ModelMessage]:
    """One tool call and the return it got."""
    return [
        ModelResponse(
            parts=[ToolCallPart(tool_name=tool, args={}, tool_call_id=call_id)]
        ),
        ModelRequest(
            parts=[
                ToolReturnPart(tool_name=tool, content=content, tool_call_id=call_id)
            ]
        ),
    ]


def _returns(messages: list[ModelMessage]) -> dict[str, object]:
    return {
        part.tool_call_id: part.content
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    }


async def _open_the_sheet(
    ctx: RunContext[LeadDeps], dataset_id: str = PHENOTYPE_DATASET
) -> EdaFiltersResult:
    return returned(
        await eda_analysis.set_eda_filters(ctx, dataset_id=dataset_id),
        EdaFiltersResult,
    )


def _rendered(ctx: RunContext[LeadDeps]) -> str:
    pinned = pinned_eda_sheet(ctx)
    assert pinned is not None
    return pinned


def _sheeted_studies(ctx: RunContext[LeadDeps]) -> list[str]:
    """The study the thread holds a sheet for, as none or one dataset id."""
    sheet = ctx.deps.state.domain.open_eda_sheet
    return [] if sheet is None else [sheet.dataset_id]


def _pinned_values(ctx: RunContext[LeadDeps], dataset_id: str) -> list[str]:
    sheet = ctx.deps.state.domain.open_eda_sheet
    assert sheet is not None
    assert sheet.dataset_id == dataset_id
    return [value for entry in sheet.entries for value in entry.vocabulary]


class TestAnOpenFilterSheetStaysReadable:
    """The sheet is copied from later, so it is pinned instead of returned."""

    async def test_the_sheet_survives_four_other_calls(
        self, monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        serve_phenotype_study(monkeypatch)

        opened = await _open_the_sheet(lead_ctx)
        history = _pair("set_eda_filters", "c1", opened.model_dump(by_alias=True))
        for index in range(4):
            history += _pair("describe_eda_study", f"o{index}", "x" * 900)

        assert _returns(elide_consumed(history))["c1"] == opened.model_dump(
            by_alias=True
        ), "the sheet-opening return is short enough to survive elision"
        pinned = _rendered(lead_ctx)
        values = _pinned_values(lead_ctx, PHENOTYPE_DATASET)
        assert len(values) == SHEET_VALUES
        assert [value for value in values if value not in pinned] == []

    async def test_the_return_names_the_pin_instead_of_carrying_the_sheet(
        self, monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        serve_phenotype_study(monkeypatch)

        opened = await _open_the_sheet(lead_ctx)

        assert opened.sheet_pinned is True
        assert "vocabulary" not in opened.model_dump_json()
        sheet = lead_ctx.deps.state.domain.open_eda_sheet
        assert sheet is not None
        assert len(sheet.entries) == SHEET_VARIABLES

    async def test_a_second_sheet_for_the_same_study_keeps_every_value(
        self, monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        """The elision took the first return, so the second may not strip it."""
        serve_phenotype_study(monkeypatch)

        await _open_the_sheet(lead_ctx)
        await _open_the_sheet(lead_ctx)

        pinned = _rendered(lead_ctx)
        values = _pinned_values(lead_ctx, PHENOTYPE_DATASET)
        assert len(values) == SHEET_VALUES
        assert [value for value in values if value not in pinned] == []

    async def test_an_applied_subset_leaves_the_pin(
        self, monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        serve_phenotype_study(monkeypatch)
        monkeypatch.setattr(eda_analysis, "apply_filters", _applied)

        await _open_the_sheet(lead_ctx)
        assert pinned_eda_sheet(lead_ctx) is not None
        await eda_analysis.set_eda_filters(
            lead_ctx, dataset_id=PHENOTYPE_DATASET, filters=[]
        )

        assert _sheeted_studies(lead_ctx) == []
        assert pinned_eda_sheet(lead_ctx) is None

    async def test_opening_another_study_leaves_the_pin(
        self, monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        """A closed study's sheet describes nothing the conversation can filter."""
        serve_phenotype_study(monkeypatch)

        async def _other_study(
            _site: str, _dataset_id: str
        ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
            return permission_entry(), study_of(
                [
                    {
                        "id": "VAR_gene",
                        "type": "string",
                        "displayName": "Gene ID",
                        "dataShape": "categorical",
                        "vocabulary": ["PF3D7_0709000"],
                    }
                ],
                entity_id=PHENOTYPE_ENTITY,
            )

        async def _bind(
            _site: str, *, dataset_id: str, conversation_id: object, display_name: str
        ) -> EdaAnalysisState:
            del conversation_id, display_name
            return await _applied(
                "plasmodb",
                conversation_id=None,
                analysis_id=ANALYSIS_ID,
                dataset_id=dataset_id,
                filters=[],
            )

        await _open_the_sheet(lead_ctx)
        monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", _other_study)
        monkeypatch.setattr(eda_analysis, "bind_analysis", _bind)
        opened = await eda_analysis.open_eda_analysis(
            lead_ctx, dataset_id=OTHER_DATASET, purpose="the other study"
        )

        assert returned(opened, EdaAnalysisOpened).dataset_id == OTHER_DATASET
        assert _sheeted_studies(lead_ctx) == []
        assert pinned_eda_sheet(lead_ctx) is None

    def test_no_open_sheet_renders_nothing(
        self, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        assert _sheeted_studies(lead_ctx) == []
        assert pinned_eda_sheet(lead_ctx) is None


def _wide_sheet(*, variables: int, value_width: int) -> list[EdaFilterSheetEntry]:
    """A study whose vocabularies are wide enough to be costly to pin."""
    return [
        EdaFilterSheetEntry(
            entity_id=PHENOTYPE_ENTITY,
            variable_id=f"VAR_{number}",
            display_name=f"Variable {number}",
            filter_type="stringSet",
            vocabulary=[
                f"v{number}_{index:03d}_{'w' * value_width}" for index in range(200)
            ],
            vocabulary_total=200,
            example={
                "entityId": PHENOTYPE_ENTITY,
                "variableId": f"VAR_{number}",
                "type": "stringSet",
                "stringSet": [f"v{number}_000_{'w' * value_width}"],
            },
        )
        for number in range(variables)
    ]


class TestThePinnedSheetIsBounded:
    """Nothing shortens a pin, so the pin carries its own budget."""

    def test_a_sheet_over_the_budget_drops_its_values(
        self, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        lead_ctx.deps.state.domain.pin_eda_sheet(
            PHENOTYPE_DATASET, _wide_sheet(variables=4, value_width=200)
        )

        pinned = _rendered(lead_ctx)
        assert len(pinned) < PINNED_SHEETS_MAX_CHARS
        assert "v3_199" not in pinned, "the values it cannot afford are gone"
        assert "preview_eda_subset" in pinned, "and the tool that reaches them is named"

    def test_a_cut_sheet_keeps_the_names_types_and_examples(
        self, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        """What is left is everything a filter needs but the value itself."""
        lead_ctx.deps.state.domain.pin_eda_sheet(
            PHENOTYPE_DATASET, _wide_sheet(variables=4, value_width=200)
        )

        pinned = _rendered(lead_ctx)
        assert "VAR_3" in pinned
        assert "stringSet" in pinned
        assert PHENOTYPE_ENTITY in pinned
        assert "v3_000" in pinned, "the example still carries one real value"

    def test_a_sheet_within_the_budget_keeps_every_value(
        self, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        lead_ctx.deps.state.domain.pin_eda_sheet(
            PHENOTYPE_DATASET, _wide_sheet(variables=1, value_width=20)
        )

        pinned = _rendered(lead_ctx)
        assert len(pinned) < PINNED_SHEETS_MAX_CHARS
        assert "v0_199" in pinned

    def test_the_guidance_is_written_once_above_the_block(
        self, lead_ctx: RunContext[LeadDeps]
    ) -> None:
        lead_ctx.deps.state.domain.pin_eda_sheet(
            PHENOTYPE_DATASET, _wide_sheet(variables=2, value_width=20)
        )

        pinned = _rendered(lead_ctx)
        assert pinned.count("Copy entityId, variableId and filterType") == 1


def _tool_imports(module: ModuleType) -> list[str]:
    source = Path(str(module.__file__)).read_text()
    return [
        node.module
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith("pathfinder.ai.tools")
    ]


def test_the_sheet_the_checkpoint_and_the_pin_share_is_a_domain_shape() -> None:
    """A shape two packages hold is the domain's, not a tool return's."""
    assert EdaFilterSheetEntry.__module__ == "pathfinder.domain.eda_parts"
    assert _tool_imports(state) == []
    assert _tool_imports(lead_pins) == []
