"""The parameter sheets FRAME holds open, pinned into its own instructions."""

from __future__ import annotations

import pytest
from assistant_core.conversation.history import elide_consumed
from pydantic_ai import ModelRetry
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    ToolReturnPart,
)
from veupathdb.domain.parameters import WDKVocabTerm
from veupathdb.wdk import WDKEnumParam, WDKParameter

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.agents.strategy_instructions import (
    PINNED_SHEETS_MAX_CHARS,
    pinned_frame_sheets,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec import (
    KINASE_PARAMS,
    bind,
    frame_ctx,
    genes_by_text,
    serve_definition,
    serve_search,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec_params import (
    aggregate,
    aggregation_under_samples,
)
from pathfinder.tests.unit.ai.tools.test_frame_spec_sheet import (
    serve_genes_by_text_definition,
    sheet_call,
)


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


def _rendered(state: AgentToolState) -> str:
    pinned = pinned_frame_sheets(frame_ctx(state))
    assert pinned is not None
    return pinned


class TestAnOpenSheetStaysReadable:
    """The sheet is copied from later, so it is pinned instead of returned."""

    @pytest.mark.asyncio
    async def test_the_first_sheet_survives_two_sheets_and_four_other_calls(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_genes_by_text_definition(monkeypatch)
        state = AgentToolState()

        first = await sheet_call(state, criterion_id="protease_text")
        await sheet_call(state, criterion_id="gametocyte")
        await sheet_call(state, criterion_id="orthologs")
        history = _pair("set_criterion", "c1", first.model_dump(by_alias=True))
        for index in range(4):
            history += _pair("get_search_overview", f"o{index}", "x" * 900)

        assert _returns(elide_consumed(history))["c1"] == first.model_dump(
            by_alias=True
        ), "the sheet-opening return is short enough to survive elision"
        pinned = _rendered(state)
        assert "protease_text" in pinned
        assert "Plasmodium falciparum 3D7" in pinned, "its vocabulary is still there"
        assert '"text_expression": null' in pinned, "and its template"

    @pytest.mark.asyncio
    async def test_the_return_names_the_pin_instead_of_carrying_the_sheet(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_genes_by_text_definition(monkeypatch)

        result = await sheet_call(AgentToolState())

        assert result.sheet_pinned is True
        assert list(result.params_template) == [
            "text_expression",
            "text_search_organism",
            "document_type",
            "text_fields",
        ]
        assert "vocabulary" not in result.model_dump_json()

    @pytest.mark.asyncio
    async def test_a_bound_criterion_leaves_the_pin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, genes_by_text)
        serve_genes_by_text_definition(monkeypatch)
        state = AgentToolState()

        await sheet_call(state)
        assert "text_search_organism" in _rendered(state)
        await bind(state, "GenesByText", dict(KINASE_PARAMS))

        assert state.open_sheets == {}
        assert pinned_frame_sheets(frame_ctx(state)) is None

    @pytest.mark.asyncio
    async def test_a_dropped_criterion_leaves_the_pin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_search(monkeypatch, genes_by_text)
        serve_genes_by_text_definition(monkeypatch)
        state = AgentToolState()

        await bind(state, "GenesByText", dict(KINASE_PARAMS))
        await sheet_call(state)
        state.frame_drop_criterion("c1", "the site has no such data")

        assert state.open_sheets == {}
        assert pinned_frame_sheets(frame_ctx(state)) is None

    def test_no_open_sheet_renders_nothing(self) -> None:
        state = AgentToolState()

        assert state.open_sheets == {}
        assert pinned_frame_sheets(frame_ctx(state)) is None


def _wide_search(*, params: int, value_width: int) -> list[WDKParameter]:
    """A search whose vocabularies are wide enough to be costly to pin."""
    return [
        WDKEnumParam(
            name=f"sample_{number}",
            display_name=f"Sample {number}",
            type="multi-pick-vocabulary",
            allow_empty_value=False,
            vocabulary=[
                WDKVocabTerm(
                    (
                        f"s{number}_{index:03d}_{'w' * value_width}",
                        f"Sample {index}",
                        None,
                    )
                )
                for index in range(200)
            ],
        )
        for number in range(params)
    ]


class TestThePinnedSheetsAreBounded:
    """Nothing shortens a pin, so the pins carry their own budget."""

    @pytest.mark.asyncio
    async def test_the_oldest_sheet_drops_to_its_names_over_the_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_definition(monkeypatch, _wide_search(params=4, value_width=60))
        state = AgentToolState()

        await sheet_call(state, criterion_id="first")
        await sheet_call(state, criterion_id="second")

        pinned = _rendered(state)
        assert len(pinned) < PINNED_SHEETS_MAX_CHARS
        first, second = pinned.split("### sheet for second")
        assert "s0_001" not in first, "the oldest sheet keeps its names only"
        assert "s0_001" in second, "the newest sheet keeps its vocabulary"

    @pytest.mark.asyncio
    async def test_a_cut_sheet_names_the_tool_that_still_reaches_its_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        serve_definition(monkeypatch, _wide_search(params=4, value_width=60))
        state = AgentToolState()

        await sheet_call(state, criterion_id="first")
        await sheet_call(state, criterion_id="second")

        first, _ = _rendered(state).split("### sheet for second")
        assert "get_parameter_options(search_name, parameter_id, query=...)" in first
        assert "re-open" not in first, "re-opening reproduces the same cut sheet"

    @pytest.mark.asyncio
    async def test_the_only_sheet_keeps_its_vocabulary_over_the_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A search this wide is the one the model can least afford to read a
        # parameter at a time, and nothing else holds its values.
        serve_definition(monkeypatch, _wide_search(params=4, value_width=200))
        state = AgentToolState()

        await sheet_call(state, criterion_id="only")

        pinned = _rendered(state)
        assert len(pinned) > PINNED_SHEETS_MAX_CHARS
        assert "s3_199" in pinned


class TestAFreshVocabularyIsNotASheet:
    """A dependent re-read names some parameters; a sheet names all of them."""

    @pytest.mark.asyncio
    async def test_a_criterion_that_opened_no_sheet_offers_no_template(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # This criterion bound params without a sheet, so what is pinned holds
        # one of its two parameters. A template built from it omits the other.
        serve_search(monkeypatch, aggregation_under_samples)
        state = AgentToolState()

        await aggregate(state, None)

        pinned = _rendered(state)
        assert "params_template" not in pinned
        assert "fresh vocabularies for c1" in pinned
        assert "minimum2" in pinned

    @pytest.mark.asyncio
    async def test_a_refused_re_call_leaves_no_decide_again_line(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The refusal names the values and the parameter was handed back once,
        # so the pin no longer asks for it.
        serve_search(monkeypatch, aggregation_under_samples)
        state = AgentToolState()

        await aggregate(state, None)
        with pytest.raises(ModelRetry):
            await aggregate(state, "median9")

        pinned = _rendered(state)
        assert "decide again" not in pinned
        assert "minimum2" in pinned, "the fresh vocabulary is still readable"
