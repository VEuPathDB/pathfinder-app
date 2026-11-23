from __future__ import annotations

import inspect
import json
from collections.abc import Callable, Iterator, Mapping
from typing import Any, NamedTuple

from pydantic import BaseModel
from pydantic_ai import Agent, NativeOutput, Tool
from pydantic_ai.capabilities.abstract import AbstractCapability
from pydantic_ai.toolsets import AbstractToolset, FunctionToolset, WrapperToolset

from strategist.ai.agents.compactor import _COMPACTOR_INSTRUCTIONS
from strategist.ai.agents.execution import build_execution_agent
from strategist.ai.agents.frame import build_frame_agent
from strategist.ai.agents.verification import build_verification_agent
from strategist.ai.audit.auditor import build_auditor_agent
from strategist.ai.audit.review import build_reviewer_agent
from strategist.ai.audit.synthesis import build_synthesis_agent
from strategist.ai.conversation.title_generator import _TITLE_INSTRUCTIONS
from strategist.ai.explore.explore_agent import build_explore_agent
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.ai.prompts.loader import (
    load_reading_guide,
    load_request_guide,
    load_system_prompt,
)
from strategist.tests._support.literal_reach import Literal, literals_reached, reach
from strategist.tests._support.sub_agents import agent_tool_names


class AgentSite(NamedTuple):
    qualname: str
    build: Callable[[], Agent[Any, Any]] | None
    texts: Callable[[], list[str]]


_SUB_AGENTS = frozenset({"frame", "execution", "verification"})
BUILT: Mapping[str, Callable[[], Agent[Any, Any]]] = {
    "lead": build_lead_agent,
    "explore": build_explore_agent,
    "frame": build_frame_agent,
    "execution": build_execution_agent,
    "verification": build_verification_agent,
    "auditor": build_auditor_agent,
    "reviewer": build_reviewer_agent,
    "synthesis": build_synthesis_agent,
}

DISPATCH_TEXTS: Mapping[str, tuple[str, ...]] = {
    "strategist.ai.lead.edit_messages.edit_work_order": ("frame",),
    "strategist.ai.lead.frame_dispatch.frame_work_order": ("frame",),
    "strategist.ai.lead.frame_dispatch._continuation_work_order": ("frame",),
    "strategist.ai.lead.verify_dispatch.work_order": ("verification",),
    "strategist.ai.lead.verify_dispatch.root_sample": ("verification",),
    "strategist.ai.lead.verify_dispatch._live_fits": ("verification",),
    "strategist.ai.lead.sample_by_steps.steps_decide": ("verification",),
    "strategist.ai.lead.dispatch_context.edit_message": ("frame",),
    "strategist.ai.lead.sub_agent_dispatch.run_recovery": ("execution",),
    "strategist.ai.lead.derive.derive_ledger": tuple(sorted(_SUB_AGENTS)),
}


def _outputs(output_type: object) -> Iterator[type[BaseModel]]:
    match output_type:
        case list() | tuple():
            for each in output_type:
                yield from _outputs(each)
        case NativeOutput(outputs=outputs):
            yield from _outputs(outputs)
        case type() if issubclass(output_type, BaseModel):
            yield output_type
        case _:
            return


def _function_tools(toolset: AbstractToolset[Any]) -> dict[str, Tool[Any]]:
    while isinstance(toolset, WrapperToolset):
        toolset = toolset.wrapped
    return dict(toolset.tools) if isinstance(toolset, FunctionToolset) else {}


def held_tools(agent: Agent[Any, Any]) -> dict[str, Tool[Any]]:
    held = agent_tool_names(agent)
    return {
        name: tool
        for toolset in agent.toolsets
        for name, tool in _function_tools(toolset).items()
        if name in held
    }


def static_texts(role: str, agent: Agent[Any, Any]) -> list[str]:
    texts = [
        sourced.instruction
        for sourced in agent._instructions
        if isinstance(sourced.instruction, str)
    ]
    for tool in held_tools(agent).values():
        texts.append(tool.description or "")
        texts.append(json.dumps(tool.tool_def.parameters_json_schema))
    texts.extend(
        json.dumps(model.model_json_schema()) for model in _outputs(agent.output_type)
    )
    if role in _SUB_AGENTS:
        texts.append(load_system_prompt(include_site_hints=True))
    return texts


def _built_site(role: str, qualname: str) -> AgentSite:
    build = BUILT[role]
    return AgentSite(qualname, build, lambda: static_texts(role, build()))


AGENT_SITES: tuple[AgentSite, ...] = (
    _built_site("lead", "strategist.ai.lead.lead_agent.build_lead_agent"),
    _built_site("explore", "strategist.ai.explore.explore_agent.build_explore_agent"),
    _built_site("frame", "strategist.ai.agents.frame.build_frame_agent"),
    _built_site("execution", "strategist.ai.agents.execution.build_execution_agent"),
    _built_site(
        "verification", "strategist.ai.agents.verification.build_verification_agent"
    ),
    _built_site("auditor", "strategist.ai.audit.auditor.build_auditor_agent"),
    _built_site("reviewer", "strategist.ai.audit.review._reviewer_agent"),
    _built_site("synthesis", "strategist.ai.audit.synthesis.build_synthesis_agent"),
    AgentSite(
        "strategist.ai.agents.compactor.build_compactor_agent",
        None,
        lambda: [_COMPACTOR_INSTRUCTIONS],
    ),
    AgentSite(
        "strategist.ai.lead.message_reader._model_reading",
        None,
        lambda: [load_reading_guide()],
    ),
    AgentSite(
        "strategist.ai.lead.message_reader._stated_request",
        None,
        lambda: [load_request_guide()],
    ),
    AgentSite(
        "strategist.ai.conversation.title_generator.generate_conversation_title",
        None,
        lambda: [_TITLE_INSTRUCTIONS],
    ),
)


def _qualname(obj: object) -> str | None:
    target = inspect.unwrap(obj) if callable(obj) else obj
    module = inspect.getmodule(target)
    name = getattr(target, "__qualname__", None)
    if module is None or name is None:
        return None
    return f"{module.__name__}.{name.split('.')[0]}"


def _capabilities(agent: Agent[Any, Any]) -> list[AbstractCapability[Any]]:
    leaves: list[AbstractCapability[Any]] = []
    agent.root_capability.apply(leaves.append)
    return leaves


def _wrappers(toolset: AbstractToolset[Any]) -> Iterator[object]:
    yield type(toolset)
    while isinstance(toolset, WrapperToolset):
        toolset = toolset.wrapped
        yield type(toolset)


def roots(role: str) -> set[str]:
    agent = BUILT[role]()
    objects: list[object] = []
    for tool in held_tools(agent).values():
        objects.extend([tool.function, tool.prepare, tool.args_validator])
    objects.extend(
        sourced.instruction
        for sourced in agent._instructions
        if not isinstance(sourced.instruction, str)
    )
    objects.extend(validator.function for validator in agent._output_validators)
    objects.extend(type(capability) for capability in _capabilities(agent))
    for toolset in agent.toolsets:
        objects.extend(_wrappers(toolset))
    found = {name for name in map(_qualname, objects) if name is not None}
    received = {text for text, roles in DISPATCH_TEXTS.items() if role in roles}
    return found | received


def _fences(own: set[str]) -> set[str]:
    return ({site.qualname for site in AGENT_SITES} | set(DISPATCH_TEXTS)) - own


def reached_units(role: str) -> set[str]:
    own = roots(role)
    return reach(own, _fences(own))


def reached_by(role: str) -> list[Literal]:
    own = roots(role)
    return literals_reached(own, _fences(own))
