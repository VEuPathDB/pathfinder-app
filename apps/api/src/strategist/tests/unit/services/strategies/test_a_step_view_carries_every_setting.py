from __future__ import annotations

from veupathdb.domain.strategy import (
    StepAnalysis,
    StepSettings,
    StrategyAst,
    flatten_tree,
    settings_of,
)

from strategist.ai.lead.live_state import read_live_state
from strategist.ai.tools.standalone.graph_helpers import build_graph_snapshot
from strategist.domain.strategy.expression_handles import stated_values
from strategist.domain.strategy.session import StrategySession
from strategist.domain.strategy.step_words import StepWords
from strategist.persistence.models import PersistedStrategyGraph
from strategist.services.conversations.responses import derive_steps_from_strategy_ast
from strategist.services.strategies.schemas import StepResponse, step_response
from strategist.services.strategies.session_factory import build_strategy_session
from strategist.tests.unit.services.strategies.test_one_commit_path_writes_a_strategy import (
    node_of,
    plan_root,
)

_WDK_IDS = {
    "step_a": 501,
    "step_b": 502,
    "step_c": 503,
    "step_d": 504,
    "step_union": 505,
    "step_coloc": 506,
    "step_root": 507,
}


def _stored() -> StrategyAst:
    root = plan_root()
    node_of(root, "step_b").analyses = [
        StepAnalysis(analysis_type="go-enrichment", parameters={"goSubset": "No"})
    ]
    return StrategyAst(
        record_type="transcript",
        root=root,
        name="Kinases near membrane genes",
        wdk_step_ids=_WDK_IDS,
        step_counts={"step_a": 120, "step_root": 8},
    )


def _session() -> StrategySession:
    return build_strategy_session(
        site_id="plasmodb",
        strategy_graph=PersistedStrategyGraph(
            id="thread-1", name="Kinases near membrane genes", strategy_ast=_stored()
        ),
    )


_SETTINGS = set(StepSettings.model_fields)


def test_a_weighted_filtered_leaf_shows_its_weight_and_filter() -> None:
    steps = flatten_tree(plan_root())

    shown = step_response(
        steps["step_a"],
        steps=steps,
        record_type="transcript",
        words=StepWords(),
        sync=None,
    ).model_dump(by_alias=True, mode="json")

    assert (shown["wdkWeight"], shown["filters"]) == (
        10,
        [
            {
                "name": "matched_transcript_filter_array",
                "value": {"values": ["N"]},
                "disabled": False,
            }
        ],
    )


def test_the_chat_snapshot_and_the_rest_load_show_one_step_view() -> None:
    session = _session()
    assert session.graph is not None

    chat = {
        step["id"]: StepResponse.model_validate(step)
        for step in build_graph_snapshot(session, session.graph).steps
    }
    rest = {step.id: step for step in derive_steps_from_strategy_ast(_stored())}

    assert chat == rest
    assert (rest["step_root"].expanded_strategy_id, rest["step_a"].record_type) == (
        9001,
        "transcript",
    )


async def test_the_live_read_lists_every_setting_of_every_step() -> None:
    session = _session()
    graph = session.graph
    assert graph is not None

    live = await read_live_state(session, "plasmodb")

    assert {step.id: step.model_dump(include=_SETTINGS) for step in live.steps} == {
        step_id: {
            **settings_of(step).model_dump(),
            "parameters": stated_values(step.parameters),
        }
        for step_id, step in graph.steps.items()
    }
    assert live.root_step_id == "step_root"
