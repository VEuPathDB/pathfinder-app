"""The tools the Lead carries itself: classification and clearing."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from assistant_core.graph.stream_events import ToolSummaryPayload
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart, ToolReturn
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.lead import lead_tools
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS, UNCLASSIFIED_TOOLS
from pathfinder.ai.lead.lead_agent import build_lead_agent
from pathfinder.ai.lead.lead_tools import classify_user_intent, clear_strategy
from pathfinder.ai.lead.scripted_scope import bind_scripted_scope
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import LeadResponse
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.models.mock.kept_arcs import SAVED_GENE_SET_NAME
from pathfinder.ai.tools.standalone import export, gene_record, gene_sets
from pathfinder.ai.tools.standalone.conversation_models import ClearStrategyResult
from pathfinder.ai.tools.toolsets import execution
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.export.service import ExportResult
from pathfinder.services.gene_records import read
from pathfinder.services.gene_records.read import GeneRecordSummary
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests._support.sub_agents import toolset_tool_names
from pathfinder.tests._support.tool_returns import returned
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    session_with_one_step,
)

_REAL_MESSAGE = "Find the gametocyte proteases."


def _flat(text: str) -> str:
    return " ".join(text.split())


def _cleared_session() -> StrategySession:
    session = session_with_one_step()
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_a": 100},
        wdk_strategy_id=555,
    )
    return session


def _ctx() -> RunContext[LeadDeps]:
    state = pipeline_state(user_prompt="scrap this and start again")
    return run_context_for(
        lead_deps(state, strategy_session=_cleared_session()),
        tool_call_id="call_clear",
    )


@pytest.fixture
def _no_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "pathfinder.ai.tools.standalone.conversation."
        "persist_strategy_ast_to_conversation",
        _noop,
    )


def test_research_is_reachable_before_the_turn_is_classified() -> None:
    """The two served reads answer a question that has not been classified."""
    assert "research_web_search" in UNCLASSIFIED_TOOLS
    assert "research_literature_search" in UNCLASSIFIED_TOOLS
    assert not UNCLASSIFIED_TOOLS & BUILDING_TOOLS


def test_the_classifier_takes_no_message_text_from_the_model() -> None:
    """The classified message is the turn's own, so no text is passed in."""
    assert sorted(UserIntent.model_fields) == [
        "classification",
        "differential_sides",
        "explicit_constraints",
        "inferred_goal",
        "is_differential",
        "referenced_step_ids",
        "referenced_strategy_ids",
    ]


def test_the_classifier_records_the_message_the_turn_answers() -> None:
    """The recorded request is the state's prompt, whatever the model states."""
    state = pipeline_state(user_prompt=_REAL_MESSAGE)
    ctx = run_context_for(lead_deps(state), tool_call_id="call_classify")

    classify_user_intent(
        ctx,
        UserIntent(
            classification=IntentClassification.NEW_STRATEGY,
            inferred_goal="find the proteases",
        ),
    )

    assert state.domain.original_request == _REAL_MESSAGE


def test_the_classifier_reads_an_answer_as_a_clarification() -> None:
    """A message that answers an open question does not start the thread over."""
    guidance = _flat(classify_user_intent.__doc__ or "")

    assert (
        "A message that answers a question you asked is "
        "``clarification_response``, whatever else it carries"
    ) in guidance
    assert "``new_strategy`` is for a message that ABANDONS that request" in guidance


def test_the_classifier_calls_an_imperative_a_building_intent() -> None:
    guidance = _flat(classify_user_intent.__doc__ or "")

    assert "Any other imperative asks for a build" in guidance
    assert "rerun" in guidance
    assert "yes, do it" in guidance
    assert "None of them is a ``follow_up_question``" in guidance


def test_the_classifier_keeps_a_retry_on_the_request_s_own_intent() -> None:
    guidance = _flat(classify_user_intent.__doc__ or "")

    assert "A retry after a failed task is the same request again" in guidance


def test_the_classifier_guidance_is_ascii_only() -> None:
    assert (classify_user_intent.__doc__ or "").isascii()


def test_the_classifier_is_told_to_capture_a_stated_share() -> None:
    doc = classify_user_intent.__doc__ or ""
    assert "percentile" in doc
    assert "top 10%" in doc


def test_the_lead_registers_the_clear_tool_behind_an_approval() -> None:
    tools = build_lead_agent()._function_toolset.tools

    assert "clear_strategy" in tools
    assert tools["clear_strategy"].requires_approval is True


def test_the_recovery_sub_agent_cannot_clear_the_strategy() -> None:
    """One destructive door, and the Lead holds it."""
    assert "clear_strategy" not in toolset_tool_names(execution.build_toolset())


def test_the_clear_docstring_does_not_claim_the_provenance_is_lost() -> None:
    """Clearing appends a revision, so a revert restores what it cleared."""
    doc = _flat(clear_strategy.__doc__ or "")

    assert "provenance" not in doc
    assert "destructive" in doc
    assert "revision" in doc


@pytest.mark.usefixtures("_no_persist")
async def test_clearing_empties_the_strategy_the_lead_can_see() -> None:
    ctx = _ctx()

    result = await clear_strategy(
        ctx,
        confirm=True,
        reply="I will make this change and report what it takes with it.",
    )

    session = ctx.deps.runtime.strategy_session
    graph = session.get_graph(None)
    assert graph is not None
    assert graph.steps == {}
    assert session.sync_state is not None
    assert session.sync_state.wdk_strategy_id is None
    assert returned(result, ClearStrategyResult).graph_id == "g1"


@pytest.mark.usefixtures("_no_persist")
async def test_clearing_without_confirmation_is_a_retry() -> None:
    ctx = _ctx()

    with pytest.raises(ModelRetry):
        await clear_strategy(
            ctx,
            confirm=False,
            reply="I will make this change and report what it takes with it.",
        )

    graph = ctx.deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    assert sorted(graph.steps) == ["step_a"]


_SAVE_REQUEST = "Save the genes of this strategy as a gene set. [[arc:save-gene-set]]"
_ROOT_GENES = ["PF3D7_0709000", "PF3D7_1133400"]


async def test_a_save_request_reaches_the_gene_set_store_through_the_leads_toolset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scripted turn runs on the real Lead and its real registrations."""
    saved: list[GeneSet] = []
    monkeypatch.setattr(gene_sets, "store_gene_set", saved.append)
    monkeypatch.setattr(gene_sets, "step_gene_ids", AsyncMock(return_value=_ROOT_GENES))
    monkeypatch.setattr(
        gene_sets, "visible_parameter_names", AsyncMock(return_value=set())
    )
    deps = lead_deps(
        pipeline_state(user_prompt=_SAVE_REQUEST), strategy_session=_cleared_session()
    )
    bind_scripted_scope("plasmodb", _SAVE_REQUEST)

    result = await build_lead_agent().run(
        _SAVE_REQUEST,
        deps=deps,
        model=get_mock_model(),
    )

    assert isinstance(result.output, LeadResponse)
    assert [(gs.name, gs.gene_ids, gs.wdk_step_id) for gs in saved] == [
        (SAVED_GENE_SET_NAME, _ROOT_GENES, 100),
    ]
    assert saved[0].user_id == deps.runtime.user_id
    assert [gs.id for gs in deps.created_gene_sets] == [saved[0].id]


_CONTEXT_STATEMENT = (
    "I'm investigating virulence factors in Leishmania major. [[arc:context]]"
)


async def test_a_scripted_turn_classifies_the_message_once_and_replies() -> None:
    """The mock script classifies without a message text and answers once."""
    deps = lead_deps(pipeline_state(user_prompt=_CONTEXT_STATEMENT))
    bind_scripted_scope("plasmodb", _CONTEXT_STATEMENT)

    result = await build_lead_agent().run(
        _CONTEXT_STATEMENT,
        deps=deps,
        model=get_mock_model(),
    )

    calls = [
        part.tool_name
        for message in result.all_messages()
        for part in message.parts
        if isinstance(part, ToolCallPart)
    ]
    assert calls.count("classify_user_intent") == 1
    assert isinstance(result.output, LeadResponse)
    assert deps.intent is not None
    assert deps.intent.classification is IntentClassification.CONTEXT_STATEMENT


_EXPORT_REQUEST = (
    "Export the gene set 'gametocyte secreted candidates' as a CSV. [[arc:export]]"
)
_EXPORT_URL = "https://pathfinder.example.org/api/v1/exports/e1"


class _ExportService:
    """Writes nothing, and answers with one link."""

    async def export_gene_set(
        self,
        gene_set: GeneSet,
        output_format: str,
    ) -> ExportResult:
        return ExportResult(
            export_id="e1",
            filename=f"{gene_set.name}.{output_format}",
            content_type="text/csv",
            url=_EXPORT_URL,
            size_bytes=64,
            expires_in_seconds=600,
        )


@pytest.fixture
def _exportable_gene_set(monkeypatch: pytest.MonkeyPatch) -> None:
    saved = GeneSet(
        id="gs_saved_export",
        name="gametocyte secreted candidates",
        site_id="plasmodb",
        gene_ids=["PF3D7_0709000", "PF3D7_1133400"],
        source="paste",
    )

    async def _one(gene_set_id: str) -> GeneSet | None:
        return saved if gene_set_id == saved.id else None

    monkeypatch.setattr(export, "get_gene_set", _one)
    monkeypatch.setattr(export, "get_export_service", _ExportService)
    monkeypatch.setattr(
        gene_sets, "list_stored_gene_sets", AsyncMock(return_value=[saved])
    )


@pytest.mark.usefixtures("_exportable_gene_set")
async def test_an_export_request_reaches_the_export_tool_and_answers_with_the_link() -> (
    None
):
    """A saved set is exported without a strategy, so the Lead exports it."""
    deps = lead_deps(pipeline_state(user_prompt=_EXPORT_REQUEST))
    bind_scripted_scope("plasmodb", _EXPORT_REQUEST)

    result = await build_lead_agent().run(
        _EXPORT_REQUEST,
        deps=deps,
        model=get_mock_model(),
    )

    assert isinstance(result.output, LeadResponse)
    assert result.output.prose == (
        f"The file is ready. Download it here: {_EXPORT_URL}"
    )


def test_the_export_tool_is_offered_before_the_turn_is_classified() -> None:
    """Exporting a saved set asks for no strategy, so it waits for no build."""
    assert "export_gene_set" in UNCLASSIFIED_TOOLS
    assert "export_gene_set" not in BUILDING_TOOLS


def test_the_lead_offers_no_download_it_has_no_id_for() -> None:
    """A WDK step id is not a name the Lead can read, so it takes none."""
    assert "get_download_url" not in UNCLASSIFIED_TOOLS
    assert "get_download_url" not in build_lead_agent()._function_toolset.tools


def _summary_lines(result: ToolReturn[Any]) -> list[str]:
    """The one-line summaries a tool return carries."""
    return [
        ToolSummaryPayload.model_validate(chunk.data).summary
        for chunk in result.metadata or []
        if isinstance(chunk, DataChunk) and chunk.type == "data-tool-summary"
    ]


_RECORD_LINE = (
    "TGME49_233460: SAG-related sequence SRS29B, 1 exon, chromosome VIII, 14 orthologs"
)

_TOXO_RECORD = GeneRecordSummary(
    site_id="toxodb",
    gene_id="TGME49_233460",
    record_url="https://toxodb.org/toxo/app/record/gene/TGME49_233460",
    organism="Toxoplasma gondii ME49",
    product="SAG-related sequence SRS29B",
    chromosome="VIII",
    exon_count=1,
    transcript_count=1,
    ortholog_count=14,
)


@pytest.fixture
def the_record(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """The record read the tool reaches, and what it was asked for."""
    asked: list[tuple[str, str]] = []

    async def _read(site_id: str, gene_id: str) -> GeneRecordSummary:
        asked.append((site_id, gene_id))
        return _TOXO_RECORD

    monkeypatch.setattr(read, "read_gene_record", _read)
    return asked


async def test_the_record_tool_answers_the_site_the_turn_runs_on(
    the_record: list[tuple[str, str]],
) -> None:
    ctx = run_context_for(
        lead_deps(
            pipeline_state(user_prompt="How many exons does TGME49_233460 have?")
        ),
        tool_call_id="call_record",
    )

    result = await gene_record.read_gene_record(ctx, "TGME49_233460")

    assert the_record == [("plasmodb", "TGME49_233460")]
    assert returned(result, GeneRecordSummary).product == "SAG-related sequence SRS29B"
    assert _summary_lines(result) == [_RECORD_LINE]


@pytest.mark.usefixtures("the_record")
async def test_a_record_read_is_a_source_the_turn_retrieved() -> None:
    ctx = run_context_for(
        lead_deps(pipeline_state(user_prompt="What is TGME49_233460?")),
        tool_call_id="call_record",
    )

    await gene_record.read_gene_record(ctx, "TGME49_233460")
    await gene_record.read_gene_record(ctx, "TGME49_233460")

    assert ctx.deps.state.turn_markers.retrieved_sources == [
        "https://toxodb.org/toxo/app/record/gene/TGME49_233460",
    ]


def test_the_record_read_is_offered_before_the_turn_is_classified() -> None:
    """A question about a gene needs no classification to be answered."""
    assert "read_gene_record" in UNCLASSIFIED_TOOLS
    assert "read_gene_record" not in BUILDING_TOOLS


def test_the_classifier_is_told_a_question_a_search_answers_is_a_build() -> None:
    doc = lead_tools.classify_user_intent.__doc__ or ""

    assert "A question whose answer is the size or the members of a gene search" in doc
    assert "``new_strategy``" in doc
    assert "follow_up_question" in doc
