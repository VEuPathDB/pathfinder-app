"""The tools the Lead carries itself: classification and clearing."""

from __future__ import annotations

from inspect import signature
from typing import Any

import pytest
from pydantic_ai import DeferredToolRequests, RunContext
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead import lead_tools
from pathfinder.ai.lead.intent import IntentClassification, UserIntent
from pathfinder.ai.lead.intent_gate import BUILDING_TOOLS, UNCLASSIFIED_TOOLS
from pathfinder.ai.lead.lead_agent import LeadResponse, build_lead_agent
from pathfinder.ai.lead.lead_tools import classify_user_intent, clear_strategy
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.models.mock import get_mock_model
from pathfinder.ai.tools.standalone import export, workbench
from pathfinder.ai.tools.standalone.conversation_models import ClearStrategyResult
from pathfinder.ai.tools.toolsets import execution
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.export.service import ExportResult
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.durable_dispatch import capture_durable_dispatch
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

    result = await clear_strategy(ctx, confirm=True)

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
        await clear_strategy(ctx, confirm=False)

    graph = ctx.deps.runtime.strategy_session.get_graph(None)
    assert graph is not None
    assert sorted(graph.steps) == ["step_a"]


_SAVE_REQUEST = "Save the 155 genes as a gene set called gametocyte candidates."


async def test_a_save_request_reaches_the_workbench_through_the_leads_toolset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scripted turn runs on the real Lead and its real registrations."""
    saved: list[GeneSet] = []
    monkeypatch.setattr(workbench, "save_gene_set", saved.append)
    deps = lead_deps(pipeline_state(user_prompt=_SAVE_REQUEST))

    result = await build_lead_agent().run(
        _SAVE_REQUEST,
        deps=deps,
        model=get_mock_model(),
    )

    assert isinstance(result.output, LeadResponse)
    assert [(gs.name, gs.gene_ids) for gs in saved] == [
        ("mock gene set", ["PF3D7_0709000", "PF3D7_1133400"]),
    ]
    assert saved[0].user_id == deps.runtime.user_id
    assert [gs.id for gs in deps.created_gene_sets] == [saved[0].id]


_CONTEXT_STATEMENT = "I'm investigating virulence factors in Leishmania major."


async def test_a_scripted_turn_classifies_the_message_once_and_replies() -> None:
    """The mock script classifies without a message text and answers once."""
    deps = lead_deps(pipeline_state(user_prompt=_CONTEXT_STATEMENT))

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


_ENRICHMENT_REQUEST = (
    "Run a GO enrichment on the gene set 'gametocyte secreted candidates' "
    "and summarize the top terms."
)


async def test_an_enrichment_request_parks_on_the_task_through_the_leads_toolset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scripted turn runs on the real Lead and its real registrations."""
    dispatch = capture_durable_dispatch(monkeypatch)
    deps = lead_deps(pipeline_state(user_prompt=_ENRICHMENT_REQUEST))

    result = await build_lead_agent().run(
        _ENRICHMENT_REQUEST,
        deps=deps,
        model=get_mock_model(),
    )

    assert isinstance(result.output, DeferredToolRequests)
    assert [entry["tool_name"] for entry in dispatch.created] == ["geneset_enrichment"]
    assert dispatch.created[0]["args"]["kwargs"]["gene_set_id"] == "gs_mock_enrichment"
    assert [d.tool_name for d in deps.durable_deferrals.values()] == [
        "geneset_enrichment"
    ]


def test_the_leads_enrichment_tool_is_registered_sequential() -> None:
    """One parked call is checkpointed per turn, so the batch cannot hold two."""
    tools = build_lead_agent()._function_toolset.tools

    assert tools["run_gene_set_enrichment"].sequential is True


def test_the_two_enrichment_registrations_take_the_same_arguments() -> None:
    """One declaration answers both, so the worker reads one set of kwargs.

    The annotation decides what is serialised into the job, so it is part of
    the argument and not of the context.
    """
    lead = signature(lead_tools.run_gene_set_enrichment).parameters
    verify = signature(workbench.run_gene_set_enrichment).parameters

    assert [str(p) for p in list(lead.values())[1:]] == [
        str(p) for p in list(verify.values())[1:]
    ]


def test_the_enrichment_tool_is_offered_before_the_turn_is_classified() -> None:
    """A request that names a saved set asks for no strategy."""
    assert "run_gene_set_enrichment" in UNCLASSIFIED_TOOLS
    assert "run_gene_set_enrichment" not in BUILDING_TOOLS


def test_the_enrichment_docstring_names_what_answers_the_call() -> None:
    """The completion call carries the terms, and the Lead reads them there."""
    doc = _flat(lead_tools.run_gene_set_enrichment.__doc__ or "")

    assert "get_enrichment_results" not in doc
    assert "enrichmentResults" in doc


_EXPORT_REQUEST = (
    "Export the gene set 'gametocyte secreted candidates' as CSV and tell me "
    "where to find the file."
)
_EXPORT_URL = "https://exports.test/gametocyte_secreted_candidates.csv"


class _ExportService:
    """The export service, without the database its files live in."""

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
        id="gs_mock_export",
        name="gametocyte secreted candidates",
        site_id="plasmodb",
        gene_ids=["PF3D7_0709000", "PF3D7_1133400"],
        source="paste",
    )

    async def _one(gene_set_id: str) -> GeneSet | None:
        return saved if gene_set_id == saved.id else None

    monkeypatch.setattr(export, "get_gene_set", _one)
    monkeypatch.setattr(export, "get_export_service", _ExportService)


@pytest.mark.usefixtures("_exportable_gene_set")
async def test_an_export_request_reaches_the_export_tool_and_answers_with_the_link() -> (
    None
):
    """A saved set is exported without a strategy, so the Lead exports it."""
    deps = lead_deps(pipeline_state(user_prompt=_EXPORT_REQUEST))

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
