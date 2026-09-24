"""One scripted conversation through the whole EDA seam.

The real turn graph, the real EDA toolset, the real checkpointer and the real
event writer run over Postgres; only the model and the EDA wire are doubles.
Every assertion reads ``conversation_events`` or the persisted strategy, never
a tool's in-memory return.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from assistant_core.graph.single_agent import single_agent_graph
from assistant_core.graph.turn_state import TurnState
from assistant_core.models.scripted import (
    RoleMarkers,
    ScriptedModel,
    ScriptedPart,
    called_tool_parts,
    scripted_call,
    scripted_text,
    tool_return_parts,
)
from assistant_core.persistence.models import ConversationEvent
from assistant_core.platform.db import async_session_factory
from assistant_core.spec import AssistantSpec
from fastapi import FastAPI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from procrastinate.testing import InMemoryConnector
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage
from pydantic_ai.models.function import FunctionModel
from sqlalchemy import select
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import StrategyAst
from veupathdb.eda import EdaClient
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb.wdk import get_site
from veupathdb_mcp.embeddings import sync_study_index

from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone._eda_models import EdaSubsetPreviewResult
from pathfinder.ai.tools.standalone.eda_step import EdaStepCreated
from pathfinder.ai.tools.toolsets.eda import build_toolset
from pathfinder.assistants import registry
from pathfinder.assistants.pathfinder_spec import (
    _register_product_stream_parts,
    build_turn_context,
)
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.assistants.site_help.spec import (
    build_initial_state,
    charge_usage,
)
from pathfinder.persistence.models import User
from pathfinder.persistence.repositories.conversation import ConversationRepository
from pathfinder.platform.identity import SITE_HELP_ASSISTANT_ID
from pathfinder.services.eda import authoring, binding, catalog
from pathfinder.services.eda.binding import bound_conversation_analysis
from pathfinder.services.strategies import commit
from pathfinder.services.strategies.commit import _WDKCommitOutcome
from pathfinder.tests._support.eda_wire import recorded_distribution, wire_eda_client
from pathfinder.tests._support.step_params import string_param
from pathfinder.tests.integration.chat._helpers import (
    chat_post_body,
    chat_turn_jobs,
    run_deferred_chat_turns,
    wait_until_chat_turn_deferred,
)
from pathfinder.tests.integration.http.conftest import WDK_AUTH_HEADER, client_for

pytestmark = pytest.mark.asyncio

FIXTURES = FIXTURE_DIR

_PROMPT = "look at the rodent malaria phenotypes and keep the P. berghei rows"
_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_VARIABLE = "VAR_035294d0"
_ANALYSIS = "t4fszEJ"
_PURPOSE = "P. berghei rows"
_WDK_USER = "424242"
_SUBSET_SEARCH = "GenesByEdaSubset"
_FILTER = {
    "entityId": _ENTITY,
    "variableId": _VARIABLE,
    "type": "stringSet",
    "stringSet": ["P. berghei"],
}

# The live counts the bundle recorded for this subset.
_FILTERED = 4011
_UNFILTERED = 4279
_SPECIES = ["P. berghei", "P. falciparum", "P. yoelii"]
_SPECIES_COUNTS = [4011.0, 4130.0, 268.0]

_SEQUENCE: list[tuple[str, dict[str, Any]]] = [
    ("search_eda_studies", {"query": "rodent malaria phenotypes"}),
    ("describe_eda_study", {"dataset_id": _DATASET, "entity_id": _ENTITY}),
    ("open_eda_analysis", {"dataset_id": _DATASET, "purpose": _PURPOSE}),
    ("set_eda_filters", {"dataset_id": _DATASET, "filters": [_FILTER]}),
    (
        "preview_eda_subset",
        {"entity_id": _ENTITY, "distribution_variable_id": _VARIABLE},
    ),
    ("create_eda_step", {}),
]


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _script(messages: list[ModelMessage]) -> ScriptedPart:
    """Make the six calls in order, then quote what the last two returned."""
    called = {part.tool_name for part in called_tool_parts(messages)}
    for name, args in _SEQUENCE:
        if name not in called:
            return scripted_call(name, args)
    returns = {part.tool_name: part.content for part in tool_return_parts(messages)}
    preview = EdaSubsetPreviewResult.model_validate(
        returns["preview_eda_subset"], from_attributes=True
    )
    created = EdaStepCreated.model_validate(
        returns["create_eda_step"], from_attributes=True
    )
    return scripted_text(
        f"{preview.count} of {preview.unfiltered_count} gene phenotype rows are "
        f"P. berghei. The step {created.search_name} holds them."
    )


_MODEL = ScriptedModel(
    roles=(RoleMarkers(role="eda", markers=frozenset({"open_eda_analysis"})),),
    scripts={"eda": _script},
    unknown=_script,
)


def _build_mock() -> FunctionModel:
    return _MODEL.as_function_model()


def _build_agent() -> Agent[LeadDeps, str]:
    return Agent(
        _build_mock(),
        output_type=str,
        deps_type=LeadDeps,
        instructions="Explore the study the researcher names and export the subset.",
        toolsets=[build_toolset()],
        name="eda",
        defer_model_check=True,
    )


def _build_deps(state: TurnState, context: Context) -> LeadDeps:
    pipeline = PipelineState(
        conversation_id=state.conversation_id,
        user_id=state.user_id,
        site_id=state.site_id,
        mode=state.mode,
        user_prompt=state.user_prompt,
        domain=StrategyDomainState(),
    )
    return LeadDeps(state=pipeline, intent=None, runtime=context, retrieved_memories=[])


def _build_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph[TurnState, Context, TurnState, TurnState]:
    return single_agent_graph(
        checkpointer=checkpointer,
        state_type=TurnState,
        context_type=Context,
        build_agent=_build_agent,
        build_deps=_build_deps,
        charge_usage=charge_usage,
    )


def _build_spec() -> AssistantSpec:
    """Served under site help's id, so the turn needs no WDK identity gate."""
    return AssistantSpec(
        assistant_id=SITE_HELP_ASSISTANT_ID,
        build_graph=_build_graph,
        build_initial_state=build_initial_state,
        build_turn_context=build_turn_context,
        build_mock_model=_build_mock,
        register_stream_parts=_register_product_stream_parts,
    )


def _study_overview() -> dict[str, Any]:
    """The catalog row for the phenotype study, from its permission entry.

    The recorded ``/studies`` slice stops before this study, and the permission
    entry carries every field the overview needs.
    """
    entry = _fixture("permissions.json")["perDataset"][_DATASET]
    return {
        "id": _STUDY,
        "datasetId": _DATASET,
        "sha1hash": entry["sha1Hash"],
        "sourceType": "curated",
        "displayName": entry["displayName"],
        "shortDisplayName": entry["shortDisplayName"],
        "description": entry["description"],
        "lastModified": "2026-05-27T20:00:00-04:00",
    }


class _AnalysesStore:
    """The upstream analysis store, kept in memory for one conversation."""

    def __init__(self) -> None:
        self.documents: dict[str, dict[str, Any]] = {}
        self.root = f"/eda/users/{_WDK_USER}/analyses/{get_site('plasmodb').project_id}"

    def create(self, body: dict[str, Any]) -> dict[str, Any]:
        self.documents[_ANALYSIS] = {
            "analysisId": _ANALYSIS,
            "displayName": body["displayName"],
            "description": body.get("description", ""),
            "studyId": body["studyId"],
            "isPublic": False,
            "creationTime": "2026-08-28T00:00:00",
            "modificationTime": "2026-08-28T00:00:00",
            "descriptor": body["descriptor"],
        }
        return {"analysisId": _ANALYSIS}

    def get(self, analysis_id: str) -> dict[str, Any]:
        document = dict(self.documents[analysis_id])
        descriptor = document["descriptor"]
        document["numFilters"] = len(descriptor["subset"]["descriptor"])
        document["numComputations"] = len(descriptor.get("computations", []))
        return document

    def patch(self, analysis_id: str, body: dict[str, Any]) -> None:
        self.documents[analysis_id].update(body)

    def route(self, request: httpx.Request, body: Any) -> httpx.Response | None:
        """The analysis routes, or None when the path is not one of them."""
        path = request.url.path
        if path == self.root and request.method == "POST":
            return httpx.Response(200, json=self.create(body))
        if not path.startswith(f"{self.root}/"):
            return None
        analysis_id = path.removeprefix(f"{self.root}/")
        if request.method == "GET":
            return httpx.Response(200, json=self.get(analysis_id))
        self.patch(analysis_id, body)
        return httpx.Response(204)


def _catalog_route(path: str, body: Any) -> httpx.Response | None:
    """The recorded study reads, or None when the path is not one of them."""
    if path.endswith("/permissions"):
        return httpx.Response(200, json=_fixture("permissions.json"))
    if path == "/eda/studies":
        listed = _fixture("studies_list.json")
        listed["studies"].append(_study_overview())
        return httpx.Response(200, json=listed)
    if path == f"/eda/studies/{_STUDY}":
        return httpx.Response(200, json=_fixture("study_detail_phenotype.json"))
    if path == f"/eda/studies/{_STUDY}/entities/{_ENTITY}/count":
        name = "count_filtered.json" if body["filters"] else "count_unfiltered.json"
        return httpx.Response(200, json=_fixture(name))
    return recorded_distribution(path, body, "study_detail_phenotype")


def _wire(store: _AnalysesStore) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        served = _catalog_route(request.url.path, body) or store.route(request, body)
        if served is not None:
            return served
        return httpx.Response(
            404, json={"status": "not-found", "path": request.url.path}
        )

    return httpx.MockTransport(handle)


@dataclass(frozen=True)
class _Seam:
    """The app, its job queue and the EDA double, for one conversation."""

    app: FastAPI
    jobs: InMemoryConnector
    store: _AnalysesStore


@pytest.fixture
async def seam(
    app: FastAPI,
    patch_app_db_engine: None,
    db_cleaner: None,
    in_memory_jobs: InMemoryConnector,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[_Seam]:
    """The EDA assistant under site help's id, over the recorded EDA wire."""
    del patch_app_db_engine, db_cleaner
    store = _AnalysesStore()
    client = EdaClient(base_url="https://plasmodb.org/eda", transport=_wire(store))
    wire_eda_client(monkeypatch, client)
    monkeypatch.setattr(registry, "build_site_help_spec", _build_spec)
    get_assistant_registry.cache_clear()
    # The api syncs the study index at warm-up; the turn only searches it.
    token = veupathdb_auth_token_ctx.set("t")
    await sync_study_index(await catalog.list_studies("plasmodb"))
    veupathdb_auth_token_ctx.reset(token)
    yield _Seam(app=app, jobs=in_memory_jobs, store=store)
    get_assistant_registry.cache_clear()


async def _fixed_wdk_user(site_id: str) -> str:
    del site_id
    return _WDK_USER


@pytest.fixture
def analyses_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """The analysis store is a double, so its user key is fixed."""
    monkeypatch.setattr(authoring, "resolve_eda_user_id", _fixed_wdk_user)
    monkeypatch.setattr(binding, "resolve_eda_user_id", _fixed_wdk_user)


@pytest.fixture
def hermetic_wdk(monkeypatch: pytest.MonkeyPatch, analyses_user: None) -> list[Any]:
    """WDK is not reached: the step push is recorded instead of sent."""
    del analyses_user
    pushed: list[Any] = []

    async def no_push(**kwargs: Any) -> _WDKCommitOutcome:
        pushed.append(kwargs["new_ast"])
        return _WDKCommitOutcome(succeeded_step_ids=[], failures=[], sync_result=None)

    monkeypatch.setattr(commit, "_commit_to_wdk", no_push)
    return pushed


async def _make_user() -> UUID:
    user_id = uuid4()
    async with async_session_factory() as session:
        session.add(User(id=user_id))
        await session.commit()
    return user_id


async def _turn(seam: _Seam, *, wdk_token: str) -> UUID:
    """Drive one turn. The persisted rows, not the streamed body, are the proof."""
    user_id = await _make_user()
    conversation_id = uuid4()
    body = chat_post_body(conversation_id, _PROMPT)
    body["assistantId"] = SITE_HELP_ASSISTANT_ID
    queued = len(chat_turn_jobs(seam.jobs))
    async with client_for(seam.app, user_id) as client:
        client.headers[WDK_AUTH_HEADER] = wdk_token
        post = asyncio.create_task(
            client.post("/api/v1/chat", json=body, timeout=120.0),
        )
        await asyncio.wait_for(
            wait_until_chat_turn_deferred(seam.jobs, queued), timeout=20.0
        )
        await run_deferred_chat_turns()
        response = await asyncio.wait_for(post, timeout=120.0)
    assert response.status_code == 200, response.text
    return conversation_id


async def _rows(conversation_id: UUID) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        found = await session.scalars(
            select(ConversationEvent)
            .where(ConversationEvent.conversation_id == conversation_id)
            .order_by(ConversationEvent.id),
        )
        return [dict(row.chunk) for row in found]


def _of_type(rows: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["type"] == kind]


def _tool_output(rows: list[dict[str, Any]], tool_name: str) -> Any:
    """The persisted output of one tool call, matched through its call id."""
    call_id = next(
        row["toolCallId"]
        for row in _of_type(rows, "tool-input-available")
        if row["toolName"] == tool_name
    )
    return next(
        row["output"]
        for row in _of_type(rows, "tool-output-available")
        if row["toolCallId"] == call_id
    )


async def _persisted_strategy(conversation_id: UUID) -> StrategyAst:
    async with async_session_factory() as session:
        view = await ConversationRepository(session).get_strategy(conversation_id)
    assert view.strategy_ast is not None
    return StrategyAst.model_validate(view.strategy_ast)


def _assert_catalog_reads(rows: list[dict[str, Any]]) -> None:
    """Steps 1 and 2: the card came back, and the species variable with it.

    A tool's return is persisted as the model reads it: field names, not aliases.
    """
    cards = _tool_output(rows, "search_eda_studies")["studies"]
    card = next(card for card in cards if card["dataset_id"] == _DATASET)
    assert card["study_id"] == _STUDY
    assert card["can_subset"] is True
    assert card["can_export_rows"] is True
    described = _tool_output(rows, "describe_eda_study")
    species = next(v for v in described["variables"] if v["variable_id"] == _VARIABLE)
    assert species["filter_type"] == "stringSet"
    assert species["vocabulary"] == _SPECIES
    assert species["is_multi_valued"] is True


def _assert_analysis_states(rows: list[dict[str, Any]]) -> None:
    """Steps 3 and 4: opening then filtering announced revisions 1 and 2."""
    states = _of_type(rows, "data-eda.analysis-state")
    assert [state["data"]["revision"] for state in states] == [1, 2]
    assert [state["data"]["numFilters"] for state in states] == [0, 1]
    for state in states:
        assert state["data"]["analysisId"] == _ANALYSIS
        assert state["data"]["datasetId"] == _DATASET
        assert state["data"]["studyId"] == _STUDY
        assert state["data"]["displayName"] == _PURPOSE
        assert state["data"]["canExportRows"] is True
    assert states[1]["data"]["filters"] == [_FILTER]
    assert states[1]["data"]["filterSummaries"] == ["Species is one of P. berghei"]


def _assert_preview(rows: list[dict[str, Any]]) -> None:
    """Step 5: the preview carries the recorded counts."""
    previews = _of_type(rows, "data-eda.subset-preview")
    assert len(previews) == 1
    preview = previews[0]["data"]
    assert preview["analysisId"] == _ANALYSIS
    assert preview["entityCounts"] == [
        {
            "entityId": _ENTITY,
            "entityDisplayName": "Gene Phenotype Data",
            "count": _FILTERED,
            "unfilteredCount": _UNFILTERED,
        }
    ]
    assert preview["distribution"]["labels"] == _SPECIES
    assert preview["distribution"]["values"] == _SPECIES_COUNTS
    assert preview["distribution"]["subsetSize"] == _UNFILTERED
    assert preview["distribution"]["isMultiValued"] is True


def _summary_for(rows: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    """The one line the named tool wrote about its own call, as persisted."""
    call_id = next(
        row["toolCallId"]
        for row in _of_type(rows, "tool-input-available")
        if row["toolName"] == tool_name
    )
    found: list[dict[str, Any]] = [
        row["data"]
        for row in _of_type(rows, "data-tool-summary")
        if row["data"]["toolCallId"] == call_id
    ]
    assert len(found) == 1, f"{tool_name} wrote {len(found)} summaries"
    return found[0]


def _assert_tool_summaries(rows: list[dict[str, Any]]) -> None:
    """Every call on the turn says what it did, in the reader's numbers."""
    for tool_name, _args in _SEQUENCE:
        _summary_for(rows, tool_name)
    studies = _summary_for(rows, "search_eda_studies")
    cards = _tool_output(rows, "search_eda_studies")["studies"]
    permitted = set(_fixture("permissions.json")["perDataset"])
    listed = [*_fixture("studies_list.json")["studies"], _study_overview()]
    catalog = sum(1 for study in listed if study["datasetId"] in permitted)
    assert studies["summary"] == (
        f"{len(cards)} closest of {catalog} studies on this site "
        f"(best match {max(card['relevance'] for card in cards):.2f})"
    )
    assert studies["status"] == "ok"
    preview = _summary_for(rows, "preview_eda_subset")
    assert preview["summary"] == (
        f"{_FILTERED:,} of {_UNFILTERED:,} Gene Phenotype Data"
    )
    assert preview["status"] == "ok"


def _assert_step_snapshot(rows: list[dict[str, Any]]) -> None:
    """Step 6: one snapshot, after the two states and the preview."""
    types = [row["type"] for row in rows]
    snapshots = _of_type(rows, "data-graph-snapshot")
    assert len(snapshots) == 1
    assert [n["searchName"] for n in snapshots[0]["data"]["nodes"]] == [_SUBSET_SEARCH]
    order = [
        types.index("data-eda.analysis-state"),
        len(types) - 1 - types[::-1].index("data-eda.analysis-state"),
        types.index("data-eda.subset-preview"),
        types.index("data-graph-snapshot"),
    ]
    assert order == sorted(order)


def _assert_step_persisted(strategy: StrategyAst) -> None:
    root = strategy.root
    assert root.search_name == _SUBSET_SEARCH
    assert root.display_name == _PURPOSE
    assert string_param(root, "eda_dataset_id") == _DATASET
    spec = json.loads(string_param(root, "eda_analysis_spec"))
    assert spec["studyId"] == _DATASET
    assert spec["displayName"] == _PURPOSE
    assert spec["descriptor"]["subset"]["descriptor"] == [_FILTER]


async def test_the_conversation_persists_every_eda_chunk_in_order(
    seam: _Seam,
    hermetic_wdk: list[Any],
) -> None:
    conversation_id = await _turn(seam, wdk_token="t")

    rows = await _rows(conversation_id)
    types = [row["type"] for row in rows]
    assert "error" not in types
    assert "tool-output-error" not in types
    assert types[-2:] == ["finish", "done"]

    _assert_catalog_reads(rows)
    _assert_analysis_states(rows)
    bound = await bound_conversation_analysis(conversation_id=conversation_id)
    assert bound is not None
    assert bound.dataset_id == _DATASET
    assert bound.analysis_id == _ANALYSIS
    assert bound.revision == 2
    subset = seam.store.documents[_ANALYSIS]["descriptor"]["subset"]["descriptor"]
    assert subset == [_FILTER]
    _assert_preview(rows)
    _assert_tool_summaries(rows)
    _assert_step_snapshot(rows)
    _assert_step_persisted(await _persisted_strategy(conversation_id))
    assert len(hermetic_wdk) == 1

    # The model read the numbers it was given.
    prose = "".join(row["delta"] for row in _of_type(rows, "text-delta"))
    assert f"{_FILTERED} of {_UNFILTERED} gene phenotype rows" in prose
    assert _SUBSET_SEARCH in prose


async def test_the_step_lands_on_live_wdk(
    seam: _Seam,
    analyses_user: None,
    require_wdk_creds: str,
) -> None:
    """The same conversation, with the step pushed to the live site."""
    del analyses_user
    conversation_id = await _turn(seam, wdk_token=require_wdk_creds)

    rows = await _rows(conversation_id)
    assert "error" not in [row["type"] for row in rows]
    created = _tool_output(rows, "create_eda_step")
    assert created["search_name"] == _SUBSET_SEARCH
    assert created["wdk_strategy_id"] is not None
    strategy = await _persisted_strategy(conversation_id)
    _assert_step_persisted(strategy)
    assert strategy.wdk_step_ids is not None
    assert strategy.root.id in strategy.wdk_step_ids
    assert strategy.step_counts is not None
    assert strategy.step_counts[strategy.root.id] > 0
    snapshot = _of_type(rows, "data-graph-snapshot")[-1]["data"]
    assert snapshot["nodes"][0]["searchName"] == _SUBSET_SEARCH
    assert snapshot["geneCount"] == strategy.step_counts[strategy.root.id]
