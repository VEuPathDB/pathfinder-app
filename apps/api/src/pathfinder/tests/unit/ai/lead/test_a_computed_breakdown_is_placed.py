from __future__ import annotations

import pytest
from veupathdb.domain.parameters import InputDatasetValue

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from pathfinder.tests._support.computed_comparison import framed_comparison
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply

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
_ROWS = (
    "bothHeld",
    "leftOnly",
    "residualGroups",
    "right.leadingSpecies",
    "right.leadingSpeciesShare",
)
_SHARES = (
    "bothHeldShare",
    "leftOnlyShare",
    "residualGroupsShare",
    "right.leadingSpecies",
    "right.leadingSpeciesGenomes",
)


async def _saved() -> tuple[LeadDeps, str]:
    deps, computed = await framed_comparison()
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


def _asked(deps: LeadDeps, prose: str) -> list[str]:
    record = turn_record(run_context_for(deps))
    found = reconcile(reply(prose, changed=True), record)
    return [m.sentence for m in found if m.kind == "unplaced_breakdown"]


def _placed(fact: str, kind: str, rows: tuple[str, ...]) -> str:
    return " ".join(f"[{kind}:{fact}.{row}]" for row in rows)


def _refusal(fact: str) -> str:
    items = "; ".join(
        (
            f"[stat:{fact}.bothHeld] or [stat:{fact}.bothHeldShare]",
            f"[stat:{fact}.leftOnly] or [stat:{fact}.leftOnlyShare]",
            f"[stat:{fact}.residualGroups] or [stat:{fact}.residualGroupsShare]",
            f"[stat:{fact}.right.leadingSpecies]",
            (
                f"[stat:{fact}.right.leadingSpeciesShare] or "
                f"[stat:{fact}.right.leadingSpeciesGenomes]"
            ),
        )
    )
    return (
        "The reply places the group count of a computed comparison and not how "
        "those groups divide. A group that one set alone holds is absent from the "
        "other set, not larger in it, and the residual groups and a species that "
        "leads a set change what the count means. Place one reference of each item "
        f"with the words that say what it counts: {items}."
    )


async def test_the_recorded_reply_is_refused_with_every_missing_item() -> None:
    deps, fact = await _saved()

    assert _asked(deps, _RECORDED) == [_refusal(fact)]


@pytest.mark.parametrize(
    ("kind", "rows"),
    [("stat", _ROWS), ("cite", _ROWS), ("stat", _SHARES), ("cite", _SHARES)],
)
async def test_a_reply_that_places_each_item_stands(
    kind: str, rows: tuple[str, ...]
) -> None:
    deps, fact = await _saved()

    assert _asked(deps, f"{_RECORDED} {_placed(fact, kind, rows)}") == []


async def test_genomes_of_the_set_place_the_leading_share() -> None:
    deps, fact = await _saved()
    split = _placed(fact, "stat", _ROWS[:4])
    of_the_set = (
        f"[stat:{fact}.right.leadingSpeciesGenomes] of [stat:{fact}.right.genomes]"
    )

    assert _asked(deps, f"{_RECORDED} {split} {of_the_set}") == []


@pytest.mark.parametrize("kind", ["stat", "cite"])
async def test_the_groups_row_of_the_fact_places_the_count(kind: str) -> None:
    deps, fact = await _saved()
    prose = f"It holds [{kind}:{fact}.groups] groups."

    assert _asked(deps, prose) == [_refusal(fact)]


async def test_a_reply_that_places_no_group_count_is_not_asked() -> None:
    deps, _ = await _saved()

    assert _asked(deps, "The strategy is available at [url].") == []
