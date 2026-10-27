from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import TypeAdapter
from veupathdb.domain.parameters import ParamValue
from veupathdb.domain.strategy import StepKind, StrategyAst, StrategyStep, walk
from veupathdb.wdk import (
    StrategyAPI,
    WDKStepTree,
    WDKStrategyDetails,
)
from veupathdb_mcp.wdk import WireStep

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
from pathfinder.domain.strategy.build_outcome import BuildOutcome
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.tally_facts import TallyFact, TallyRowFact
from pathfinder.services.strategies import site_changes
from pathfinder.services.strategies.sync_state import WDKSyncState
from pathfinder.tests._support.bound_values import bound
from pathfinder.tests._support.orthomcl_record_classes import (
    recorded_orthomcl_record_types,
)
from pathfinder.tests.fixtures.builders import add_step_to_graph
from pathfinder.tests.unit.ai.lead._site_verdict import (
    UNANSWERED_DIGEST,
    VALID,
    serve_the_site,
    verify,
)
from pathfinder.tests.unit.ai.lead.conftest import (
    lead_deps,
    pipeline_state,
    requirement,
)

pytestmark = pytest.mark.usefixtures("collector")

_GROUPS, _PROTEINS = 227289040, 227289050
_STRATEGY = 214647810
_SINGLETONS = 523795
_ASKED = (
    "which organisms in OrthoMCL have the most singletons (orthogroups with just "
    "a single protein)"
)
_VALUE: TypeAdapter[ParamValue] = TypeAdapter(ParamValue)


def _range(low: float, high: float) -> ParamValue:
    return _VALUE.validate_python({"type": "number-range", "min": low, "max": high})


_SINGLETON_COUNTS = {
    "all_count": _range(1.0, 1.0),
    "core_count": _range(0.0, 100000.0),
    "peripheral_count": _range(0.0, 100000.0),
}
_SINGLETON_WIRE = {
    "all_count": '{"min": 1.0, "max": 1.0}',
    "core_count": '{"min": 0.0, "max": 100000.0}',
    "peripheral_count": '{"min": 0.0, "max": 100000.0}',
}
_RANKING = TallyFact(
    id="tally_a4cb04a0",
    title="Proteins by Taxon Code",
    record_noun="protein",
    total=_SINGLETONS,
    distinct=840,
    rows=[
        TallyRowFact(value="bpli", count=18260, label="Brachionus plicatilis"),
        TallyRowFact(value="osat", count=9365, label="Oryza sativa Japonica Group"),
        TallyRowFact(value="tvag", count=9301, label="Trichomonas vaginalis G3"),
    ],
    wdk_step_id=_PROTEINS,
)
_ONE_OR_TWO = '{"min": 1.0, "max": 2.0}'


def _site_step(
    wdk_step_id: int, search_name: str, record_class: str, wire: dict[str, str]
) -> dict[str, Any]:
    return {
        "id": wdk_step_id,
        "searchName": search_name,
        "searchConfig": {"parameters": wire},
        "recordClassName": record_class,
        "estimatedSize": _SINGLETONS,
        "validation": VALID,
    }


async def _ranges(
    payload: StrategyAst, api: StrategyAPI, wire: dict[str, WireStep]
) -> None:
    del api
    for node in walk(payload.root):
        if node.id in wire:
            node.parameters = {
                name: _VALUE.validate_python({"type": "number-range", **json.loads(v)})
                for name, v in wire[node.id].parameters.items()
            }


def _details(wire: dict[str, str] = _SINGLETON_WIRE) -> WDKStrategyDetails:
    return WDKStrategyDetails.model_validate(
        {
            "strategyId": _STRATEGY,
            "name": "Singletons",
            "rootStepId": _PROTEINS,
            "stepTree": {"stepId": _PROTEINS, "primaryInput": {"stepId": _GROUPS}},
            "steps": {
                str(_GROUPS): _site_step(
                    _GROUPS, "GroupsBySequenceCount", "group", wire
                ),
                str(_PROTEINS): _site_step(_PROTEINS, "FromGroups", "sequence", {}),
            },
        }
    )


def _singleton_session() -> StrategySession:
    session = StrategySession(site_id="orthomcl")
    graph = StrategyGraph("graph-1", "Singletons", "orthomcl")
    graph.record_type = "sequence"
    add_step_to_graph(
        graph,
        StrategyStep(
            id="step_be4749c9",
            kind=StepKind.SEARCH,
            search_name="GroupsBySequenceCount",
            parameters=dict(_SINGLETON_COUNTS),
            record_class="group",
            display_name="Number of Sequences",
        ),
    )
    add_step_to_graph(
        graph,
        StrategyStep(
            id="c_singleton_proteins",
            kind=StepKind.TRANSFORM,
            search_name="FromGroups",
            primary_input_id="step_be4749c9",
            record_class="sequence",
            display_name="Transform Groups to Proteins",
        ),
    )
    session.add_graph(graph)
    session.sync_state = WDKSyncState(
        wdk_step_ids={"step_be4749c9": _GROUPS, "c_singleton_proteins": _PROTEINS},
        step_counts={"step_be4749c9": _SINGLETONS, "c_singleton_proteins": _SINGLETONS},
        wdk_strategy_id=_STRATEGY,
        wdk_step_tree=WDKStepTree(
            step_id=_PROTEINS, primary_input=WDKStepTree(step_id=_GROUPS)
        ),
    )
    return session


def _singleton_spec() -> OperationalSpec:
    return OperationalSpec(
        goal=_ASKED,
        criteria=[
            Criterion(
                id="step_be4749c9",
                text="orthogroups with exactly one protein in total",
                search_name="GroupsBySequenceCount",
                record_class="group",
                role="seed",
                resolved_params=bound(_SINGLETON_COUNTS),
            ),
            Criterion(
                id="c_singleton_proteins",
                text="proteins in the singleton orthogroups",
                search_name="FromGroups",
                record_class="sequence",
                role="transform",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="c_singleton_proteins",
                inputs=[StructureNode(kind="leaf", criterion_id="step_be4749c9")],
            )
        ),
    )


def _singleton_deps() -> LeadDeps:
    state = pipeline_state("orthomcl", user_prompt=_ASKED)
    state.domain.operational_spec = _singleton_spec()
    state.domain.requirements = [
        requirement(ConstraintKind.OTHER, "orthology dataset/search", "OrthoMCL"),
        requirement(
            ConstraintKind.OTHER,
            "singleton definition",
            "orthogroups with just a single protein",
        ),
    ]
    state.domain.last_build_outcome = BuildOutcome(
        pushed_step_ids=["step_be4749c9", "c_singleton_proteins"],
        wdk_strategy_id=_STRATEGY,
    )
    state.turn_markers.record_tally(_RANKING)
    return lead_deps(state, strategy_session=_singleton_session())


async def test_the_recorded_singleton_ranking_passes_over_an_objecting_checker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_the_site(monkeypatch, _details(), recorded_orthomcl_record_types())
    deps = _singleton_deps()

    delta = await verify(monkeypatch, deps, UNANSWERED_DIGEST)

    digest = delta.digest
    assert (digest.success, digest.gaps, digest.handoff_to) == (True, [], None)
    assert [(c.kind, c.status) for c in digest.review.checks] == [
        ("step_valid", "pass"),
        ("bound_values", "pass"),
        ("result_count", "pass"),
        (ConstraintKind.OTHER, "unchecked"),
        (ConstraintKind.OTHER, "unchecked"),
        (ConstraintKind.ORGANISM, "unchecked"),
        ("tally", "pass"),
    ]
    assert digest.review.checks[-1].evidence == (
        "the site counted 523,795 proteins of step 227289050 over 840 values"
    )
    assert deps.state.turn_markers.verified is True


async def test_a_bound_value_the_site_holds_otherwise_fails_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    widened = {**_SINGLETON_WIRE, "all_count": _ONE_OR_TWO}
    serve_the_site(monkeypatch, _details(widened), recorded_orthomcl_record_types())
    monkeypatch.setattr(site_changes, "canonicalize_synced_parameters", _ranges)
    monkeypatch.setattr(site_changes, "get_strategy_api", lambda _site: None)

    delta = await verify(monkeypatch, _singleton_deps(), UNANSWERED_DIGEST)

    moved = SiteCheck(
        kind="bound_values",
        subject="the strategy on the site",
        status="fail",
        evidence=(
            f"step {_GROUPS} ('Number of Sequences') holds {_ONE_OR_TWO!r} for "
            f"all_count, the spec binds {_SINGLETON_WIRE['all_count']!r}"
        ),
    )
    assert (delta.digest.success, delta.digest.gaps) == (
        False,
        [SiteCheckGap(check=moved)],
    )
