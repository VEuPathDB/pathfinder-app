"""What every agent of this deployment does when one of its tools fails.

A refusal the model can correct answers the model; a defect ends the run.
"""

from __future__ import annotations

import importlib
import pkgutil
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.messages import (
    ModelMessage,
    ModelResponse,
    RetryPromptPart,
    ToolCallPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.toolsets.function import FunctionToolset

from pathfinder import ai, assistants
from pathfinder.ai.agents.frame import build_frame_agent
from pathfinder.ai.agents.tool_vocabulary import SEARCH_LOOKUP_TOOLS
from pathfinder.ai.agents.verification import build_verification_agent
from pathfinder.ai.capabilities.resilience import ToolResilience
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.platform.errors import NotFoundError
from pathfinder.platform.refusals import ServiceRefusalRetry
from pathfinder.tests._support.sub_agents import agent_tool_names
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_MISSING_GENE_SET = "d6edd975-f6d9-482e-bc50-3d666b55227f"
_FRAME_OUTPUT = {"summary": "framed nothing"}
_VERIFY_OUTPUT = {
    "digest": {
        "disposition": "awaiting_user",
        "prose": "nothing to report",
        "reason": "the tool refused",
        "success": False,
    },
}

# The agents the deployment is known to run. The walk below finds these and
# whatever else is declared, so a factory added later is held by the same rule.
NAMED_FACTORIES = frozenset(
    {
        "build_lead_agent",
        "build_frame_agent",
        "build_execution_agent",
        "build_verification_agent",
        "build_site_help_agent",
    },
)


def _declared_factories(module: object, name: str) -> bool:
    value = getattr(module, name)
    return (
        name.startswith("build_")
        and name.endswith("_agent")
        and callable(value)
        and getattr(value, "__module__", "") == getattr(module, "__name__", "")
    )


def agent_factories() -> dict[str, Callable[[], Agent[Any, Any]]]:
    """Every agent factory this application declares, by name."""
    found: dict[str, Callable[[], Agent[Any, Any]]] = {}
    for root in (ai, assistants):
        for info in pkgutil.walk_packages(root.__path__, prefix=f"{root.__name__}."):
            module = importlib.import_module(info.name)
            found.update(
                {
                    name: getattr(module, name)
                    for name in vars(module)
                    if _declared_factories(module, name)
                },
            )
    return found


def _agent_deps() -> AgentDeps:
    """Sub-agent deps that open no database: the run reads no scratchpad."""
    deps = agent_deps_for(lead_deps(pipeline_state(user_prompt="check the build")))
    deps.db_session_factory = None
    return deps


async def _defective(ctx: RunContext[AgentDeps]) -> str:
    del ctx
    msg = "unsupported operand"
    raise TypeError(msg)


async def _refusing(ctx: RunContext[AgentDeps], gene_set_id: str) -> str:
    del ctx
    raise NotFoundError(detail=f"Gene set not found: {gene_set_id}")


def _calls_then_answers(
    tool_name: str, args: dict[str, Any], output: dict[str, Any]
) -> FunctionModel:
    """A model that calls the registered tool, then answers with the output."""
    steps: list[int] = []

    def _respond(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        del messages, info
        steps.append(len(steps))
        if len(steps) == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name=tool_name, args=args, tool_call_id="tc_1")
                ]
            )
        return ModelResponse(
            parts=[
                ToolCallPart(
                    tool_name="final_result", args=output, tool_call_id="tc_final"
                )
            ]
        )

    return FunctionModel(_respond, model_name="scripted")


def _retry_messages(messages: list[ModelMessage]) -> list[str]:
    return [
        part.model_response()
        for message in messages
        for part in message.parts
        if isinstance(part, RetryPromptPart)
    ]


def _seams(agent: Agent[Any, Any]) -> int:
    """How many refusal seams the agent carries.

    ``_root_capability`` is the only route to the assembled list: the Agent
    publishes no accessor for it.
    """
    leaves: list[AbstractCapability[Any]] = []
    agent._root_capability.apply(leaves.append)
    return len([leaf for leaf in leaves if isinstance(leaf, ServiceRefusalRetry)])


def test_the_walk_finds_every_agent_the_deployment_is_known_to_run() -> None:
    """A walk that finds nothing would hold the rule below over nothing."""
    assert set(agent_factories()) >= NAMED_FACTORIES


def test_every_agent_that_carries_tools_carries_the_refusal_seam() -> None:
    """One rule over the deployment: a refusal answers the model, not the user."""
    built = {name: factory() for name, factory in agent_factories().items()}
    with_tools = {name: a for name, a in built.items() if agent_tool_names(a)}

    unseamed = sorted(name for name, a in with_tools.items() if _seams(a) != 1)

    assert unseamed == []
    assert set(with_tools) >= NAMED_FACTORIES


async def test_a_defect_in_a_frame_tool_ends_the_run() -> None:
    """A TypeError is no call the model can correct, so it reaches the alert."""
    agent = build_frame_agent()
    toolset = FunctionToolset[AgentDeps](tools=[_defective])
    model = _calls_then_answers("_defective", {}, _FRAME_OUTPUT)

    with agent.override(model=model, toolsets=[toolset]), pytest.raises(TypeError):
        await agent.run("frame it", deps=_agent_deps())


async def test_a_missing_id_in_a_verification_tool_names_the_listing_tool() -> None:
    """The refusal the model can correct comes back as a retry, not a directive."""
    agent = build_verification_agent()
    toolset = FunctionToolset[AgentDeps](tools=[_refusing])
    model = _calls_then_answers(
        "_refusing", {"gene_set_id": _MISSING_GENE_SET}, _VERIFY_OUTPUT
    )

    with agent.override(model=model, toolsets=[toolset]):
        result = await agent.run("verify it", deps=_agent_deps())

    retries = _retry_messages(result.all_messages())
    assert len(retries) == 1
    assert _MISSING_GENE_SET in retries[0]
    assert "list_workbench_gene_sets" in retries[0]


def _resilience_ctx() -> MagicMock:
    ctx: MagicMock = MagicMock()
    ctx.retries = {}
    return ctx


def _tool_def() -> ToolDefinition:
    return ToolDefinition(
        name="get_search_overview", description="test", parameters_json_schema={}
    )


async def _routed_by_resilience(error: Exception, args: dict[str, Any]) -> Any:
    return await ToolResilience(
        search_lookup_tools=SEARCH_LOOKUP_TOOLS
    ).on_tool_execute_error(
        _resilience_ctx(),
        call=ToolCallPart(
            tool_name="get_search_overview", args=args, tool_call_id="tc_1"
        ),
        tool_def=_tool_def(),
        args=args,
        error=error,
    )


async def test_a_defect_is_no_category_the_resilience_layer_answers() -> None:
    """An error of no known category ends the run instead of guiding the model."""
    error = KeyError("missing key")

    with pytest.raises(KeyError) as raised:
        await _routed_by_resilience(error, {})

    assert raised.value is error


async def test_an_application_refusal_is_left_to_the_refusal_seam() -> None:
    """One layer owns a refusal this application names, and it is not this one."""
    error = NotFoundError(detail=f"Gene set not found: {_MISSING_GENE_SET}")

    with pytest.raises(NotFoundError) as raised:
        await _routed_by_resilience(error, {"gene_set_id": _MISSING_GENE_SET})

    assert raised.value is error
