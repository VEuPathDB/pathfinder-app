"""The served research tools' answers, recorded as what this turn retrieved."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_ai import RunContext, ToolReturn
from pydantic_ai.toolsets import AbstractToolset, WrapperToolset
from pydantic_ai.toolsets.abstract import ToolsetTool
from pydantic_core import from_json

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, ToolCharge

# The served reads whose answers carry a reference the reply may cite.
RESEARCH_TOOLS: frozenset[str] = frozenset(
    {"research_web_search", "research_literature_search"},
)


class _RetrievedReference(BaseModel):
    """One result or source a research answer lists."""

    model_config = ConfigDict(extra="ignore")

    url: str | None = None
    doi: str | None = None
    pmid: str | None = None


def _answer_fields(value: object) -> object:
    """The object a served answer carries: a tool return, JSON text or a mapping."""
    match value:
        case ToolReturn(return_value=inner):
            return _answer_fields(inner)
        case str() as text:
            try:
                return _answer_fields(from_json(text))
            except ValueError:
                return {}
        case {**fields}:
            return fields
        case _:
            return {}


class ResearchAnswer(BaseModel):
    """The references one research tool's answer carries.

    A served tool answers JSON text, so the text is read before the fields
    are. A refusal or any other prose lists nothing.
    """

    model_config = ConfigDict(extra="ignore")

    results: list[_RetrievedReference] = Field(default_factory=list)
    sources: list[_RetrievedReference] = Field(default_factory=list)
    cost_usd: Decimal = Field(default=Decimal(0), validation_alias="costUsd")

    @model_validator(mode="before")
    @classmethod
    def _read_the_text_a_served_tool_answers(cls, value: object) -> object:
        return _answer_fields(value)

    def references(self) -> list[str]:
        """Every identifier this answer retrieved."""
        return [
            found
            for item in (*self.results, *self.sources)
            for found in (item.url, item.doi, item.pmid)
            if found
        ]


@dataclass
class RetrievalRecordingToolset(WrapperToolset[Any]):
    """Puts every reference a research tool answers with on the turn's markers,
    and what the answer cost on the turn's bill.

    The markers and the charge sink are the turn's, so the agent that reads
    through this toolset can be the Lead or one of its sub-agents.
    """

    markers: TurnMarkers
    charge: Callable[[ToolCharge], None]

    async def call_tool(
        self,
        name: str,
        tool_args: dict[str, Any],
        ctx: RunContext[Any],
        tool: ToolsetTool[Any],
    ) -> Any:
        result = await super().call_tool(name, tool_args, ctx, tool)
        if name in RESEARCH_TOOLS:
            answer = ResearchAnswer.model_validate(result)
            for reference in answer.references():
                self.markers.record_retrieved_source(reference)
            if answer.cost_usd:
                self.charge(ToolCharge(tool_name=name, cost_usd=answer.cost_usd))
        return result


def recording_retrievals(
    sources: AbstractToolset[Any] | None,
    deps: LeadDeps,
) -> AbstractToolset[Any] | None:
    """The turn's served sources, with their retrievals recorded on the turn."""
    if sources is None:
        return None
    return RetrievalRecordingToolset(
        sources,
        markers=deps.state.turn_markers,
        charge=deps.record_tool_charge,
    )
