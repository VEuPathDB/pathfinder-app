from __future__ import annotations

from typing import Any

import pytest
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb.wdk import WDKRecordType

from pathfinder.ai.lead import sub_agent_tools
from pathfinder.ai.lead.deltas import VerificationDelta
from pathfinder.ai.lead.dispatch_context import agent_deps_for
from pathfinder.ai.lead.sub_agent_tools import LeadDeps, apply_agent_state
from pathfinder.ai.lead.verify_dispatch import run_verification
from pathfinder.ai.tools.toolsets import verification
from pathfinder.domain.caveats import RequirementGap
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.strategies import record_classes
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)
from pathfinder.tests._support.sub_agents import pinned_sub_agent
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead.conftest import (
    final_result_model,
    lead_deps,
    pipeline_state,
    requirement,
)

pytestmark = pytest.mark.usefixtures("collector")

_MOST_PLASMODIUM = (
    "Which ortholog groups are found in at least 90% of the Plasmodium genomes "
    "and in no Toxoplasma gondii genome?"
)
_PATTERN = "GroupsByPhyleticPattern"


def _record_type_requirement(value: str, label: str) -> Constraint:
    return requirement(ConstraintKind.RECORD_TYPE, label, value)


def _session() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("graph-1", "Plasmodium groups", "orthomcl")
    graph.record_type = "group"
    add_step_to_graph(
        graph,
        StrategyStep(id="step_b08116fe", kind=StepKind.SEARCH, search_name=_PATTERN),
    )
    graph.steps["step_b08116fe"].record_class = "group"
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_b08116fe": 227284530},
        step_counts={"step_b08116fe": 1088},
        wdk_strategy_id=214645250,
    )
    return session


def _framed_deps(stated: Constraint) -> LeadDeps:
    state = pipeline_state("orthomcl", user_prompt=_MOST_PLASMODIUM)
    state.domain.requirements = [stated]
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["step_b08116fe"], wdk_strategy_id=214645250
    )
    deps = lead_deps(state, strategy_session=_session())
    framing = agent_deps_for(deps, call_id="call_test")
    framing.agent_state.frame_set_criterion(
        Criterion(
            id="step_b08116fe",
            text="ortholog groups",
            search_name=_PATTERN,
            record_class="group",
        )
    )
    framing.agent_state.frame_set_structure(
        SpecStructure(root=StructureNode(kind="leaf", criterion_id="step_b08116fe"))
    )
    apply_agent_state(deps, framing)
    return deps


def _checked(text: str) -> dict[str, Any]:
    return {
        "digest": {
            "disposition": "done",
            "success": True,
            "prose": "The strategy returns **1,088** ortholog groups.",
            "reason": "The built step binds the requested phyletic expression.",
            "review": {
                "requirements": [
                    {
                        "text": text,
                        "turn": 1,
                        "answeredBy": ["step_b08116fe"],
                        "how": "search",
                        "status": "met",
                        "note": (
                            "The built search uses record type `group` for "
                            "ortholog groups."
                        ),
                    }
                ]
            },
        }
    }


async def _verify(
    monkeypatch: pytest.MonkeyPatch, deps: LeadDeps, text: str
) -> VerificationDelta:
    async def _record_types(_site_id: str) -> list[WDKRecordType]:
        return recorded_orthomcl_record_types()

    monkeypatch.setattr(record_classes, "get_raw_record_types", _record_types)
    monkeypatch.setattr(
        sub_agent_tools, "get_mock_model", lambda: final_result_model(_checked(text))
    )
    with pinned_sub_agent(
        monkeypatch,
        "verification",
        toolsets=[verification.build_toolset()],
        instructions="Return the digest the script names.",
    ):
        result = await run_verification(
            deps=deps, parent_tool_call_id="lead_call_verify", reason="check it"
        )
    assert isinstance(result, VerificationDelta)
    return result


async def test_a_framed_group_strategy_verifies_with_no_record_type_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _framed_deps(_record_type_requirement("ortholog groups", "ortholog groups"))

    delta = await _verify(monkeypatch, deps, "ortholog groups")

    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert spec.record_type == "group"
    row = delta.digest.review.requirements[0]
    assert (row.text, row.status, row.note) == (
        "ortholog groups",
        "met",
        "the strategy returns groups",
    )
    assert (delta.digest.success, delta.digest.gaps) == (True, [])


async def test_a_request_for_proteins_on_a_group_strategy_keeps_its_gap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deps = _framed_deps(_record_type_requirement("proteins", "proteins"))
    deps.state.domain.request_messages = ["Which proteins are in these groups?"]

    delta = await _verify(monkeypatch, deps, "proteins")

    row = delta.digest.review.requirements[0]
    assert (row.text, row.status, row.note) == (
        "proteins",
        "unmet",
        "the strategy returns groups",
    )
    assert delta.digest.success is False
    assert delta.digest.gaps == [RequirementGap(text="proteins", status="unmet")]
