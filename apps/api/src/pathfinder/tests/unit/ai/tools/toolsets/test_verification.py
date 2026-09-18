"""The verification toolset's registration contract for its durable tools.

A durable tool parks one checkpointed call per turn, so it must be registered
``sequential=True``.
"""

from __future__ import annotations

from typing import Any

from pathfinder.ai.tools.toolsets.verification import build_toolset
from pathfinder.tests.unit.ai.tools.conftest import unwrap_function_toolset

_DURABLE_TOOLS = frozenset(
    {
        "run_control_tests_on_step",
        "run_gene_set_enrichment",
    }
)


def _tools_by_name() -> dict[str, Any]:
    toolset = unwrap_function_toolset(build_toolset())
    return {tool.name: tool for tool in toolset.tools.values()}


def test_every_durable_tool_is_registered_and_sequential() -> None:
    by_name = _tools_by_name()

    assert sorted(_DURABLE_TOOLS - by_name.keys()) == []
    assert (
        sorted(name for name in _DURABLE_TOOLS if not by_name[name].tool_def.sequential)
        == []
    )
