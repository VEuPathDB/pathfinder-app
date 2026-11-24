"""Every tool that names a step of the strategy refuses an id the strategy does
not hold with the one sentence, written in one place."""

from __future__ import annotations

from collections.abc import Awaitable
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter
from pydantic_ai import Tool
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.strategy import CombineOp

from strategist.ai.lead.lead_agent import build_lead_toolset, build_sweep_toolset
from strategist.ai.tools.standalone._eda_step_arguments import IntoSlot
from strategist.ai.tools.standalone._eda_step_write import export_write
from strategist.ai.tools.standalone._validation_helpers import OperationPayload
from strategist.ai.tools.standalone.optimization import sweep_can_run
from strategist.ai.tools.standalone.strategy import apply_operations
from strategist.ai.tools.toolsets import eda, execution, verification
from strategist.domain.evidence import NamedControlSet
from strategist.domain.strategy.revision import strategy_revision
from strategist.domain.strategy.session import StrategySession, not_a_step
from strategist.tests._support.run_context import lead_run_context
from strategist.tests.unit.ai.tools._strategy_edit_stubs import (
    combine,
    ctx,
    leaf,
    seed,
    session_with,
    stated_leaf,
)
from strategist.tests.unit.ai.tools.conftest import unwrap_function_toolset

_SOURCE = Path(__file__).resolve().parents[4]
_STEP_ARGUMENTS = frozenset({"step_id", "target_step_id", "wdk_step_id"})
_SET_ID = "96eaafb0-659c-4041-8bf3-5c66e5a9f95c"
_GRAPH_SENTENCE = not_a_step("ghost", ["step_a", "step_b", "step_c"])
_WDK_SENTENCE = not_a_step(99, [11, 12, 13])

_EXEMPT = {
    "get_estimated_size": "it counts a step of an imported strategy by its own id",
    "run_control_tests_on_step": "its worker reads the step from the account",
}

_GRAPH_ID_ARGUMENTS: dict[str, dict[str, Any]] = {
    "update_leaf_params": {"step_id": "ghost", "parameters": {}},
    "update_combine_operator": {"step_id": "ghost", "operator": CombineOp.UNION},
    "update_step_metadata": {"step_id": "ghost", "display_name": "x"},
    "delete_step": {"step_id": "ghost"},
    "replace_subtree": {"step_id": "ghost", "new_subtree": stated_leaf("n")},
    "insert_saved_strategy": {"target_step_id": "ghost", "saved_wdk_strategy_id": 7},
    "add_step_filter": {"step_id": "ghost", "filter_name": "f", "value": "v"},
    "save_gene_set": {"step_id": "ghost", "name": "kinases"},
}

_WDK_ID_ARGUMENTS: dict[str, dict[str, Any]] = {
    "read_step_ids": {"wdk_step_id": 99},
    "step_columns": {"wdk_step_id": 99},
    "count_step_by_column": {"wdk_step_id": 99, "column": "organism"},
    "get_sample_records": {"wdk_step_id": 99},
    "get_download_url": {"wdk_step_id": 99},
}

_LEAD_DELETE = {"delete_step": {"step_id": "ghost", "reply": "It goes."}}


def _session() -> StrategySession:
    root = combine("step_c", leaf("step_a"), leaf("step_b"), CombineOp.INTERSECT)
    return session_with(root, {"step_a": 11, "step_b": 12, "step_c": 13})


def _tools(toolset: Any) -> dict[str, Tool[Any]]:
    return unwrap_function_toolset(toolset).tools


_AGENT_TOOLS = {
    **_tools(execution.build_toolset()),
    **_tools(verification.build_toolset()),
    **_tools(eda.build_toolset()),
}
_LEAD_TOOLS = _tools(build_lead_toolset())


def _naming_a_step(tools: dict[str, Tool[Any]]) -> set[str]:
    return {
        name
        for name, tool in tools.items()
        if _STEP_ARGUMENTS & set(tool.tool_def.parameters_json_schema["properties"])
    }


def test_every_tool_that_names_a_step_is_checked() -> None:
    checked = {*_GRAPH_ID_ARGUMENTS, *_WDK_ID_ARGUMENTS, *_EXEMPT}

    assert (
        sorted(_naming_a_step(_AGENT_TOOLS) - checked),
        sorted(_naming_a_step(_LEAD_TOOLS) - checked),
        sorted(_naming_a_step(_tools(build_sweep_toolset()))),
    ) == ([], [], ["optimize_search_parameters"])


async def _refusal(call: Awaitable[Any]) -> str:
    with pytest.raises(ModelRetry) as refused:
        await call
    return str(refused.value)


def _cases(
    tools: dict[str, Tool[Any]], arguments: dict[str, dict[str, Any]], sentence: str
) -> list[Any]:
    return [
        pytest.param(tools[name], args, sentence, id=name)
        for name, args in arguments.items()
        if name in tools
    ]


@pytest.mark.parametrize(
    ("tool", "args", "sentence"),
    [
        *_cases(_AGENT_TOOLS, _GRAPH_ID_ARGUMENTS, _GRAPH_SENTENCE),
        *_cases(_AGENT_TOOLS, _WDK_ID_ARGUMENTS, _WDK_SENTENCE),
    ],
)
async def test_a_building_tool_refuses_a_step_the_strategy_does_not_hold(
    tool: Tool[Any], args: dict[str, Any], sentence: str
) -> None:
    deps = seed(leaf("unused"), {})
    deps.strategy_session = _session()

    assert await _refusal(tool.function(ctx(deps), **args)) == sentence


@pytest.mark.parametrize(
    ("tool", "args", "sentence"),
    [
        *_cases(_LEAD_TOOLS, {**_GRAPH_ID_ARGUMENTS, **_LEAD_DELETE}, _GRAPH_SENTENCE),
        *_cases(_LEAD_TOOLS, _WDK_ID_ARGUMENTS, _WDK_SENTENCE),
    ],
)
async def test_a_lead_tool_refuses_a_step_the_strategy_does_not_hold(
    tool: Tool[Any], args: dict[str, Any], sentence: str
) -> None:
    run = lead_run_context(strategy_session=_session(), tool_call_id="call_ghost")

    assert await _refusal(tool.function(run, **args)) == sentence


async def test_a_sweep_refuses_a_step_the_strategy_does_not_hold() -> None:
    run = lead_run_context(strategy_session=_session())
    run.deps.state.domain.attach_control_set(
        NamedControlSet(id=_SET_ID, name="Signal peptide controls")
    )

    refusal = await _refusal(
        sweep_can_run(run, reply="", wdk_step_id=99, control_set_id=_SET_ID)
    )

    assert refusal == f"{_WDK_SENTENCE} Nothing was started and no card was shown."


async def test_a_batch_on_a_step_the_strategy_does_not_hold_names_what_it_holds() -> (
    None
):
    deps = seed(leaf("unused"), {})
    deps.strategy_session = _session()
    graph = deps.strategy_session.graph
    assert graph is not None

    refusal = await _refusal(
        apply_operations(
            ctx(deps),
            base_revision=strategy_revision(graph.to_strategy_ast()),
            operations=[
                TypeAdapter(OperationPayload).validate_python(
                    {"kind": "updateStepMeta", "stepId": "ghost", "displayName": "x"}
                )
            ],
        )
    )

    assert refusal.split('"')[1] == _GRAPH_SENTENCE


def test_an_export_into_a_slot_of_no_held_step_is_refused() -> None:
    run = lead_run_context(strategy_session=_session())
    graph = run.deps.runtime.strategy_session.graph
    assert graph is not None

    with pytest.raises(ModelRetry) as refused:
        export_write(
            run,
            graph,
            leaf("step_export"),
            placement=IntoSlot(
                kind="into_slot", attach_to_step_id="ghost", slot="secondary"
            ),
            join=None,
        )

    assert str(refused.value) == _GRAPH_SENTENCE


def test_the_sentence_lists_what_the_strategy_holds() -> None:
    assert (not_a_step("x", ["a", "b"]), not_a_step("x", [])) == (
        "Step x is not a step of this strategy. It holds a, b.",
        "Step x is not a step of this strategy. It holds no step yet.",
    )


def test_the_sentence_is_written_once() -> None:
    writers = sorted(
        str(path.relative_to(_SOURCE))
        for path in _SOURCE.rglob("*.py")
        if "tests" not in path.relative_to(_SOURCE).parts
        and "is not a step of this strategy" in path.read_text()
    )

    assert writers == ["domain/strategy/session.py"]
