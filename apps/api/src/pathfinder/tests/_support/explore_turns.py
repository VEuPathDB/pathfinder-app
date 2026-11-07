from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from assistant_core.graph.turn_state import DurableCall, PendingDurableCall
from langgraph.runtime import Runtime
from langgraph.types import Command
from pydantic_ai.messages import (
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    ToolCallPart,
    UserPromptPart,
)
from veupathdb.wdk import WDKAnswer, WDKSearchConfig
from veupathdb_mcp.catalog import ParameterInfo, format_param_info_typed

from pathfinder.ai.capabilities.metering import ModelSpend
from pathfinder.ai.conversation._turn_helpers import _extract_chunk
from pathfinder.ai.graph import explore_node
from pathfinder.ai.graph.explore_node import make_explore_node
from pathfinder.ai.graph.state import PipelineState, StrategyDomainState
from pathfinder.ai.models.mock.strategy_specs import GENE_TYPE, SIGNAL_PEPTIDE
from pathfinder.domain.modes import EXPLORE_PHASE
from pathfinder.services.experiment import variant_comparison
from pathfinder.tests._support.record_classes import recorded_searches
from pathfinder.tests._support.recorded_columns import recorded_body
from pathfinder.tests._support.run_context import turn_runtime

SITE = "plasmodb"
GENE_TYPE_REPORT = "report_gene_type_protein_coding"
SIGNAL_PEPTIDE_REPORT = "report_signal_peptide_signalp6"
EXPLORE_PROMPT = "Which genes carry a signal peptide? [[arc:explore]]"
PREFERENCE_PROMPT = (
    "I prefer SignalP 6.0. Which genes carry a signal peptide? [[arc:explore]]"
)
NO_READING_PROMPT = "What is known about this family? [[arc:explore-no-reading]]"
ONE_READING_PROMPT = "Which genes carry a signal peptide? [[arc:explore-one-reading]]"


@dataclass
class RecordedReports:
    answers: dict[str, WDKAnswer]
    ran: list[tuple[str, dict[str, str]]] = field(default_factory=list)

    async def run_search_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        *,
        report_config: object,
        view_filters: object,
    ) -> WDKAnswer:
        del record_type, report_config, view_filters
        self.ran.append((search_name, dict(search_config.parameters)))
        return self.answers[search_name]


async def _recorded_parameters(
    site_id: str, record_type: str, search_name: str, context: dict[str, str]
) -> list[ParameterInfo]:
    del site_id, record_type, context
    return format_param_info_typed(recorded_searches()[search_name].parameters or [])


def chunks_of(payloads: Sequence[object]) -> list[dict[str, Any]]:
    return [c for p in payloads if (c := _extract_chunk(p)) is not None]


@dataclass
class ExploreDoubles:
    payloads: list[object] = field(default_factory=list)
    charges: list[tuple[UUID, int]] = field(default_factory=list)

    def chunks(self) -> list[dict[str, Any]]:
        return chunks_of(self.payloads)

    def of_type(self, kind: str) -> list[dict[str, Any]]:
        return [chunk for chunk in self.chunks() if chunk["type"] == kind]

    def replies(self) -> list[str]:
        return [str(chunk["delta"]) for chunk in self.of_type("text-delta")]

    def types(self) -> list[str]:
        return [str(chunk["type"]) for chunk in self.chunks()]


def serve_recorded_readings(monkeypatch: pytest.MonkeyPatch) -> RecordedReports:
    served = RecordedReports(
        answers={
            SIGNAL_PEPTIDE: WDKAnswer.model_validate(
                recorded_body(SIGNAL_PEPTIDE_REPORT)
            ),
            GENE_TYPE: WDKAnswer.model_validate(recorded_body(GENE_TYPE_REPORT)),
        }
    )
    monkeypatch.setattr(variant_comparison, "get_wdk_client", lambda _site: served)
    monkeypatch.setattr(variant_comparison, "search_parameters", _recorded_parameters)
    return served


def install_explore_doubles(monkeypatch: pytest.MonkeyPatch) -> ExploreDoubles:
    doubles = ExploreDoubles()
    serve_recorded_readings(monkeypatch)

    async def _charge(
        session_factory: object, *, user_id: UUID, spent: Sequence[ModelSpend]
    ) -> None:
        del session_factory
        doubles.charges.append((user_id, sum(spend.tokens for spend in spent)))

    monkeypatch.setattr(explore_node, "charge_spend", _charge)
    monkeypatch.setattr(
        explore_node, "get_stream_writer", lambda: doubles.payloads.append
    )
    return doubles


def explore_state(prompt: str, **fields: Any) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id=SITE,
        mode="explore",
        user_prompt=prompt,
        user_message_id=uuid4(),
        **fields,
    )


async def run_explore(state: PipelineState) -> Command[Any]:
    runtime = Runtime(context=turn_runtime(site_id=SITE, user_id=state.user_id))
    return await make_explore_node()(state, runtime=runtime)


def update_of(command: Command[Any]) -> dict[str, Any]:
    match command.update:
        case dict() as update:
            return update
        case other:
            pytest.fail(f"the node handed back no update: {other!r}")


def domain_of(command: Command[Any]) -> StrategyDomainState:
    match update_of(command):
        case {"domain": StrategyDomainState() as domain}:
            return domain
        case other:
            pytest.fail(f"the node handed back no domain: {other!r}")


def parked_durable(
    prompt: str, *, tool_name: str, task: UUID, args: dict[str, Any]
) -> PendingDurableCall:
    call_id = f"call-{tool_name}"
    asked = ModelRequest(parts=[UserPromptPart(content=prompt)])
    called = ModelResponse(parts=[ToolCallPart(tool_name, args, tool_call_id=call_id)])
    return PendingDurableCall(
        phase=EXPLORE_PHASE,
        tool_call_id=call_id,
        tool_name=tool_name,
        tool_args=args,
        prior_messages_json=ModelMessagesTypeAdapter.dump_json(
            [asked, called]
        ).decode(),
        durable_calls=[
            DurableCall(
                tool_call_id=call_id,
                tool_name=tool_name,
                args=args,
                task_id=task,
                durable_tool_name=tool_name,
            )
        ],
    )
