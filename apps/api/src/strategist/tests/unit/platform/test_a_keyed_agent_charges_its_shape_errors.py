from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import AgentCapability
from pydantic_ai.toolsets import CombinedToolset, FunctionToolset

import strategist
from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.tools.toolsets._refusals import RefusalMemoryToolset
from strategist.platform.refusals import (
    ChargedArgumentRefusals,
    KeyedRefusalToolset,
    agent_capabilities,
)

_SOURCE = Path(strategist.__file__).parent


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _built_from(capabilities: ast.expr | None, toolsets: ast.expr) -> bool:
    match capabilities:
        case ast.Call(func=ast.Name(id="agent_capabilities")) as built:
            stated = _keyword(built, "toolsets")
            return stated is not None and ast.dump(stated) == ast.dump(toolsets)
        case _:
            return False


def unpaired_agents(source: str) -> list[int]:
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        match node:
            case ast.Call(func=ast.Name(id="Agent")):
                toolsets = _keyword(node, "toolsets")
                capabilities = _keyword(node, "capabilities")
                if toolsets is not None and not _built_from(capabilities, toolsets):
                    found.append(node.lineno)
            case _:
                pass
    return found


def test_every_production_agent_builds_its_capabilities_from_its_toolsets() -> None:
    production = [path for path in _SOURCE.rglob("*.py") if "tests" not in path.parts]

    unpaired = {
        str(path.relative_to(_SOURCE)): lines
        for path in production
        if (lines := unpaired_agents(path.read_text()))
    }

    assert len(production) > 100
    assert unpaired == {}


def test_a_new_keyed_agent_built_the_plain_way_is_found() -> None:
    plain = """
agent = Agent(
    model,
    toolsets=[KeyedRefusalToolset(wrapped=tools)],
    capabilities=[ToolResilience()],
)
other = Agent(
    model,
    toolsets=[KeyedRefusalToolset(wrapped=tools)],
    capabilities=agent_capabilities([ToolResilience()], toolsets=[]),
)
"""
    paired = """
toolsets = [KeyedRefusalToolset(wrapped=tools)]
agent = Agent(
    model,
    toolsets=toolsets,
    capabilities=agent_capabilities([ToolResilience()], toolsets=toolsets),
)
"""

    assert (unpaired_agents(plain), unpaired_agents(paired)) == ([2, 7], [])


def bind(ctx: RunContext[AgentDeps], criterion_id: str) -> str:
    del ctx
    return criterion_id


def _charges(capabilities: list[AgentCapability[Any]]) -> int:
    return len([c for c in capabilities if isinstance(c, ChargedArgumentRefusals)])


def test_the_capability_follows_from_a_keyed_toolset_at_any_depth() -> None:
    tools = FunctionToolset[AgentDeps]([bind])
    nested = RefusalMemoryToolset(wrapped=KeyedRefusalToolset(wrapped=tools))
    keyed = KeyedRefusalToolset(wrapped=RefusalMemoryToolset(wrapped=tools))

    filtered = KeyedRefusalToolset(wrapped=tools).filtered(lambda _c, _d: True)
    combined = CombinedToolset[AgentDeps]([tools, filtered])

    assert _charges(agent_capabilities([], toolsets=[keyed])) == 1
    assert _charges(agent_capabilities([], toolsets=[nested, keyed])) == 1
    assert _charges(agent_capabilities([], toolsets=[combined])) == 1
    assert _charges(agent_capabilities([], toolsets=[tools])) == 0
