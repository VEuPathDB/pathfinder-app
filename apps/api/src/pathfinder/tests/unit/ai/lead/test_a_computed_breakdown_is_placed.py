"""A reply that places a computed comparison's group count places how those
groups divide: held by both sets, held by one set alone, the residual groups and
a species that leads a set."""

from __future__ import annotations

from veupathdb.domain.parameters import InputDatasetValue

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import Mismatch, reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.test_a_computed_comparison_reaches_the_facts import (
    _framed,
)

_STEP = "step_c276e1f0"
_DATASET = "202394260"
_OPEN, _CLOSE = chr(0x201C), chr(0x201D)
_RECORDED = (
    "The strategy is built and verified. It answers the request using the "
    f"reading {_OPEN}higher average gene copy number per genome{_CLOSE}: it "
    f"returns [count:{_STEP}] orthogroup records whose pooled per-genome average "
    "is higher in the left genus than in the right genus. It does not instead "
    "require that every left genome has more copies than every right genome, "
    "and it does not compare higher pooled total gene count. The result is a "
    "computed snapshot rather than a live recalculation. The strategy is "
    "available at [url]."
)
_BREAKDOWN = (
    "bothHeld",
    "leftOnly",
    "residualGroups",
    "left.leadingSpecies",
    "left.leadingSpeciesShare",
    "right.leadingSpecies",
    "right.leadingSpeciesShare",
)


async def _saved() -> tuple[LeadDeps, str]:
    deps, computed = await _framed()
    domain = deps.state.domain
    held = domain.computed_comparisons[computed.handle]
    domain.computed_comparisons[computed.handle] = held.model_copy(
        update={"dataset_id": _DATASET}
    )
    domain.operational_spec = OperationalSpec(
        criteria=[
            Criterion(
                id=_STEP,
                text="groups with more proteins per genome in the left set",
                search_name="GroupsByNameList",
                resolved_params={
                    "group_names": BoundValue(
                        value=InputDatasetValue(dataset_id=_DATASET), source="chosen"
                    )
                },
            )
        ]
    )
    return deps, computed.fact_id


def _breakdown(deps: LeadDeps, prose: str) -> list[Mismatch]:
    record = turn_record(run_context_for(deps))
    found = reconcile(reply(prose, changed=True), record)
    return [m for m in found if m.kind == "unplaced_breakdown"]


async def test_the_recorded_reply_is_refused_with_every_missing_path() -> None:
    deps, fact = await _saved()

    [refused] = _breakdown(deps, _RECORDED)

    missing = ", ".join(f"[stat:{fact}.{path}]" for path in _BREAKDOWN)
    assert refused.sentence.endswith(f"{missing}.")


async def test_a_reply_that_places_the_breakdown_stands() -> None:
    deps, fact = await _saved()
    placed = " ".join(f"[stat:{fact}.{path}]" for path in _BREAKDOWN)

    assert _breakdown(deps, f"{_RECORDED} {placed}") == []


async def test_the_groups_reference_of_the_fact_asks_the_same() -> None:
    deps, fact = await _saved()

    [refused] = _breakdown(deps, f"It holds [stat:{fact}.groups] groups.")

    missing = ", ".join(f"[stat:{fact}.{path}]" for path in _BREAKDOWN)
    assert refused.sentence.endswith(f"{missing}.")


async def test_a_reply_that_places_no_group_count_is_not_asked() -> None:
    deps, _ = await _saved()

    assert _breakdown(deps, "The strategy is available at [url].") == []
