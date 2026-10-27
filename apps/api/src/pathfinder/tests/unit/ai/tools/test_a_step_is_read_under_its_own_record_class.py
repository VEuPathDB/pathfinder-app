from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict
from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain.parameters import MultiPickValue, ParamValue
from veupathdb.domain.strategy import CombineOp, StrategyStepNode, flatten_tree
from veupathdb.errors import ValidationError
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.ai.agents.state import AgentToolState
from pathfinder.ai.graph.runtime import Context
from pathfinder.ai.lead import pre_turn
from pathfinder.ai.tools.standalone import (
    _sample_page,
    optimization,
    step_ids,
)
from pathfinder.ai.tools.standalone._edit_refusal import refusal_context
from pathfinder.ai.tools.standalone._result_models import StepColumns
from pathfinder.ai.tools.standalone._step_read import read_as
from pathfinder.ai.tools.standalone.graph_helpers import build_step_response
from pathfinder.ai.tools.standalone.optimization import sweep_can_run
from pathfinder.ai.tools.standalone.results import read_step_columns
from pathfinder.ai.tools.standalone.step_ids import read_step_ids
from pathfinder.ai.tools.standalone.strategy import apply_operations
from pathfinder.ai.tools.standalone.strategy_edits import update_leaf_params
from pathfinder.ai.tools.standalone.stream_parts import strategy_meta_chunk
from pathfinder.domain.evidence import NamedControlSet
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.operations import UpdateStepParamsOp
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.strategy.session import StrategySession
from pathfinder.services.strategies import stated_sides
from pathfinder.tests._support.database import no_database
from pathfinder.tests._support.orthomcl_record_classes import (
    serve_orthomcl_record_classes,
)
from pathfinder.tests._support.orthomcl_step_columns import serve_step_columns
from pathfinder.tests._support.run_context import lead_run_context

from ._strategy_edit_stubs import ctx, install_stub_api, leaf, seed, session_with
from .conftest import agent_run_context

_PATTERN_STEP = 227284900
_PROTEIN_STEP = 227284890
_LOST_STEP = 227284870
_SAVED_SET_ID = "96eaafb0-659c-4041-8bf3-5c66e5a9f95c"


class _Refusal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    details: dict[str, str]


@pytest.fixture(autouse=True)
def _orthomcl(monkeypatch: pytest.MonkeyPatch) -> None:
    serve_orthomcl_record_classes(monkeypatch)
    serve_step_columns(monkeypatch, "group", _PATTERN_STEP, "GroupsByPhyleticPattern")


def _protein_and_groups() -> StrategySession:
    session = session_with(
        StrategyStepNode(
            id="step_root",
            search_name="__combine__",
            operator=CombineOp.INTERSECT,
            primary_input=StrategyStepNode(id="step_protein", search_name="ByIdList"),
            secondary_input=StrategyStepNode(
                id="step_groups", search_name="GroupsByPhyleticPattern"
            ),
        ),
        {
            "step_protein": _PROTEIN_STEP,
            "step_groups": _PATTERN_STEP,
            "step_lost": _LOST_STEP,
        },
    )
    graph = session.graph
    assert graph is not None
    graph.steps.update(
        flatten_tree(StrategyStepNode(id="step_lost", search_name="Unlisted"))
    )
    graph.record_type = "sequence"
    return session


async def test_a_group_step_under_a_protein_root_reads_as_groups() -> None:
    assert await read_as(_protein_and_groups(), _PATTERN_STEP) == (
        "group",
        "GroupsByPhyleticPattern",
    )


async def test_a_group_step_in_a_strategy_recorded_as_genes_reads_as_groups() -> None:
    session = _protein_and_groups()
    assert session.graph is not None
    session.graph.record_type = "transcript"

    assert await read_as(session, _PATTERN_STEP) == (
        "group",
        "GroupsByPhyleticPattern",
    )


@pytest.mark.parametrize(
    ("wdk_step_id", "refusal"),
    [
        (
            _LOST_STEP,
            (
                f"The site lists no record type for Unlisted, so step {_LOST_STEP} "
                f"cannot be read."
            ),
        ),
        (
            227284999,
            "Step 227284999 is not a step of this strategy, so it cannot be read.",
        ),
    ],
)
async def test_a_step_of_no_class_of_its_own_is_not_read_as_the_strategys(
    wdk_step_id: int, refusal: str
) -> None:
    session = _protein_and_groups()
    assert session.graph is not None
    session.graph.record_type = "transcript"

    with pytest.raises(ModelRetry) as refused:
        await read_as(session, wdk_step_id)

    assert str(refused.value) == refusal


async def test_the_columns_of_a_group_step_are_not_read_as_genes() -> None:
    session = _protein_and_groups()
    assert session.graph is not None
    session.graph.record_type = "transcript"
    state = AgentToolState()
    state.frame_set_criterion(
        Criterion(
            id="step_groups",
            text="groups with a mammal protein",
            search_name="GroupsByPhyleticPattern",
        )
    )

    result = await read_step_columns(
        agent_run_context(
            site_id="orthomcl", strategy_session=session, agent_state=state
        ).deps,
        _PATTERN_STEP,
    )

    assert result == StepColumns(
        wdk_step_id=_PATTERN_STEP,
        note=(
            f"Step {_PATTERN_STEP} is not a gene search step a criterion binds. "
            "Sample the root with get_sample_records for this criterion."
        ),
    )


async def test_the_ids_of_a_group_step_are_sampled_as_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[str] = []

    async def _sample(*_args: Any, record_type: str, **_kwargs: Any) -> Any:
        asked.append(record_type)
        return _sample_page.SampledRecords(
            _sample_page.StepSample(step_id=_PATTERN_STEP, total_count=0), []
        )

    monkeypatch.setattr(step_ids, "sample_page", _sample)

    await read_step_ids(
        lead_run_context(strategy_session=_protein_and_groups()),
        wdk_step_id=_PATTERN_STEP,
        limit=5,
    )

    assert asked == ["group"]


async def test_a_sweep_reads_the_parameters_of_a_group_search_as_groups(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asked: list[tuple[str, str]] = []

    async def _tunable(_site_id: str, record_class: str, search_name: str) -> list[str]:
        asked.append((record_class, search_name))
        return ["phyletic_expression"]

    monkeypatch.setattr(optimization, "tunable_parameters_of_search", _tunable)
    run = lead_run_context(strategy_session=_protein_and_groups())
    run.deps.state.domain.attach_control_set(
        NamedControlSet(id=_SAVED_SET_ID, name="Mammal group controls")
    )

    await sweep_can_run(
        run,
        reply="I will sweep the phyletic expression against your controls.",
        wdk_step_id=_PATTERN_STEP,
        control_set_id=_SAVED_SET_ID,
        parameters=["phyletic_expression"],
    )

    assert asked == [("group", "GroupsByPhyleticPattern")]


def test_a_strategy_of_no_known_class_names_none() -> None:
    session = _protein_and_groups()
    graph = session.graph
    assert graph is not None
    graph.record_type = None

    chunk = strategy_meta_chunk(session, graph)

    assert chunk.data == {
        "strategyId": "g1",
        "name": "Test",
        "isSaved": False,
        "estimatedSize": None,
        "recordClassName": None,
    }


async def _turns_the_value_down(*_args: Any, **_kwargs: Any) -> ValidatedParams:
    raise ValidationError(title="Invalid parameter value", detail="no such organism")


async def test_a_refused_value_names_the_steps_class_not_the_strategys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_stub_api(monkeypatch)
    monkeypatch.setattr(stated_sides, "validate_parameters", _turns_the_value_down)
    deps = seed(
        leaf("a", params={"organism": MultiPickValue(values=["Pf3D7"])}),
        wdk_step_ids={"a": 100},
    )
    graph = deps.strategy_session.graph
    assert graph is not None
    graph.record_type = "group"
    edit: dict[str, ParamValue] = {
        "organism": MultiPickValue(values=["Plasmodium nowhere"])
    }

    with pytest.raises(ModelRetry) as batch:
        await apply_operations(
            ctx(deps),
            strategy_revision(graph.to_strategy_ast()),
            [UpdateStepParamsOp(step_id="a", parameters=edit)],
        )
    with pytest.raises(ModelRetry) as single:
        await update_leaf_params(ctx(deps), "a", edit)

    assert [
        _Refusal.model_validate_json(str(raised.value)).details
        for raised in (batch, single)
    ] == [
        {
            "detail": "no such organism",
            "recordType": "transcript",
            "searchName": "GenesByTaxon",
        }
    ] * 2


async def test_a_refused_edit_of_a_group_step_names_the_group_class() -> None:
    session = _protein_and_groups()
    deps = seed(StrategyStepNode(id="unused", search_name="GenesByTaxon"), {})
    deps.strategy_session = session

    contexts = [
        await refusal_context(
            deps, UpdateStepParamsOp(step_id="step_groups", parameters={})
        ),
        await refusal_context(
            deps, UpdateStepParamsOp(step_id="step_lost", parameters={})
        ),
    ]

    assert contexts == [
        {"recordType": "group", "searchName": "GroupsByPhyleticPattern"},
        {"recordType": None, "searchName": "Unlisted"},
    ]


def test_a_step_response_carries_the_steps_class_not_the_strategys() -> None:
    session = _protein_and_groups()
    graph = session.graph
    assert graph is not None
    graph.record_type = "transcript"
    graph.steps["step_groups"].record_class = "group"

    responses = [
        build_step_response(graph, graph.steps[step_id]).record_type
        for step_id in ("step_groups", "step_protein", "step_root")
    ]

    assert responses == ["group", None, "group"]


async def test_a_turn_classes_every_step_of_its_strategy_on_arrival() -> None:
    session = _protein_and_groups()
    graph = session.graph
    assert graph is not None

    await pre_turn._class_every_step(
        Context(
            site_id="orthomcl",
            user_id=uuid4(),
            strategy_session=session,
            db_session_factory=no_database,
            cancel_event=asyncio.Event(),
        )
    )

    assert {sid: step.record_class for sid, step in graph.steps.items()} == {
        "step_root": None,
        "step_protein": "sequence",
        "step_groups": "group",
        "step_lost": None,
    }
