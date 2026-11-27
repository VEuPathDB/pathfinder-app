from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionResponse,
    use_decisions_transport,
)

from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.frame_requirements import questions_for_the_card
from strategist.ai.lead.operator_reader import read_the_operators
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from strategist.platform.config import get_settings
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_CASE = Path(__file__).parents[4] / "evals/corpus/uat-dry-c-plasmodb.json"
_TURNS: list[str] = json.loads(_CASE.read_text())["turns"][:6]
_FIXTURE = Path(__file__).parents[3] / "fixtures/decisions/operator_reading.json"
_RECORDED: dict[str, Any] = json.loads(_FIXTURE.read_text())


@pytest.fixture(autouse=True)
def _a_deployment_that_asks_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "strategist_chat_provider", "default")


def _stated(rid: str, kind: ConstraintKind, value: str, quote: str) -> Constraint:
    return Constraint(
        id=rid,
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
        quote=quote,
    )


_REQUIREMENTS = [
    _stated(
        "f93ed1f082f2",
        ConstraintKind.ORGANISM,
        "Plasmodium falciparum 3D7",
        "Plasmodium falciparum 3D7",
    ),
    _stated(
        "c873c10a23f9",
        ConstraintKind.PROPERTY,
        "predicted signal peptide",
        "a predicted signal peptide",
    ),
    _stated(
        "845d6b3e2fc9",
        ConstraintKind.COUNT,
        "at least one transmembrane domain",
        "at least one transmembrane domain",
    ),
    _stated(
        "4019f79c2e84",
        ConstraintKind.PERCENTILE,
        "top 5 percent of the expression ranking",
        "top 5 percent",
    ),
    _stated(
        "d3ac9dc82b1c",
        ConstraintKind.PROPERTY,
        "expressed in Plasmodium falciparum 3D7 blood stage",
        "3D7 blood-stage expression",
    ),
]


def _criterion(cid: str, *linked: str) -> Criterion:
    return Criterion(
        id=cid,
        text=cid,
        search_name="GenesByText",
        record_class="transcript",
        answers=[RequirementLink(requirement=rid) for rid in linked],
    )


def _leaf(cid: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=cid)


_UNION_OVER_THE_SURFACE_FEATURES = OperationalSpec(
    criteria=[
        _criterion("c_signal_peptide", "f93ed1f082f2", "c873c10a23f9"),
        _criterion("c_transmembrane", "f93ed1f082f2", "845d6b3e2fc9"),
        _criterion("c_sporozoite_expression", "4019f79c2e84", "d3ac9dc82b1c"),
    ],
    structure=SpecStructure(
        root=StructureNode(
            kind="combine",
            operator=CombineOp.UNION,
            inputs=[
                StructureNode(
                    kind="combine",
                    operator=CombineOp.INTERSECT,
                    inputs=[_leaf("c_signal_peptide"), _leaf("c_transmembrane")],
                ),
                _leaf("c_sporozoite_expression"),
            ],
        )
    ),
)


class _ByMessages:
    """The newest message alone reads the root as a union at the given
    confidence and states nothing of the inner combine; the whole thread reads
    each as the intersect the recorded turn held."""

    def __init__(self, newest: float) -> None:
        self.newest = newest

    async def __call__(self, request: DecisionRequest) -> DecisionResponse | None:
        newest_alone = _TURNS[0] not in request.input
        root = "3D7 blood-stage expression" in request.input
        choice, confidence = ("intersect", 0.57)
        if newest_alone:
            choice, confidence = ("union", self.newest) if root else ("not_stated", 0.9)
        response: dict[str, Any] = json.loads(json.dumps(_RECORDED["response"]))
        response["answers"][0].update({"choice": choice, "confidence": confidence})
        return DecisionResponse.model_validate(response)


async def _read_with(newest_confidence: float) -> tuple[str, int, bool]:
    domain = StrategyDomainState(
        requirements=_REQUIREMENTS,
        operational_spec=_UNION_OVER_THE_SURFACE_FEATURES,
        original_request=_TURNS[0],
        request_messages=_TURNS[1:5],
    )
    deps = lead_deps(pipeline_state(user_prompt=_TURNS[5], domain=domain))
    use_decisions_transport(_ByMessages(newest_confidence))

    read = await read_the_operators(_UNION_OVER_THE_SURFACE_FEATURES, deps)
    deps.state.domain.operational_spec = read
    root = next(r for r in read.operator_reads if r.built is CombineOp.UNION)
    return (
        root.read,
        len(questions_for_the_card(deps, FrameResult(), [])),
        (read.ready_to_build),
    )


async def test_a_confident_flip_the_message_states_is_not_asked_back() -> None:
    assert await _read_with(0.82) == ("agrees", 0, True)


async def test_a_newest_reading_below_the_floor_asks_the_card() -> None:
    assert await _read_with(0.45) == ("disagrees", 1, False)
