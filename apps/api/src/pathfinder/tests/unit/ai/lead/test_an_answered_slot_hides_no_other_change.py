"""An answered open slot on a kept criterion excuses that answer and nothing else."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, ParamValue

from pathfinder.ai.lead.dispatch_messages import undeclared_spec_changes
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
)
from pathfinder.domain.strategy.spec_diff import CriterionChange, diff_specs

_ID = "c_mass_spec"
_OPEN = "min_peptide_count"
_KEPT = [CriterionChange(criterion_id=_ID, disposition="kept")]


def _spec(
    *, search_name: str, resolved: dict[str, ParamValue], open_names: list[str]
) -> OperationalSpec:
    return OperationalSpec(
        goal="candidate antigens",
        criteria=[
            Criterion(
                id=_ID,
                text="detected by mass spectrometry",
                search_name=search_name,
                resolved_params=resolved,
                open_params=[
                    OpenSlot(criterion_id=_ID, param_name=name) for name in open_names
                ],
            )
        ],
    )


def _baseline() -> OperationalSpec:
    return _spec(
        search_name="GenesByMassSpec",
        resolved={"min_sequence_count": NumberValue(value=1)},
        open_names=[_OPEN],
    )


def test_an_answer_and_a_moved_value_name_only_the_moved_value() -> None:
    before = _baseline()
    after = _spec(
        search_name="GenesByMassSpec",
        resolved={
            "min_sequence_count": NumberValue(value=5),
            _OPEN: NumberValue(value=2),
        },
        open_names=[],
    )

    problem = undeclared_spec_changes(diff_specs(before, after), _KEPT, before)

    assert "min_sequence_count=5" in problem
    assert _OPEN not in problem


def test_an_answer_does_not_excuse_a_changed_search() -> None:
    before = _baseline()
    after = _spec(
        search_name="GenesByProteomicsEvidence",
        resolved={
            "min_sequence_count": NumberValue(value=1),
            _OPEN: NumberValue(value=2),
        },
        open_names=[],
    )

    problem = undeclared_spec_changes(diff_specs(before, after), _KEPT, before)

    assert [name for name in (_ID,) if name in problem] == [_ID]


def test_an_answer_does_not_excuse_a_removed_value() -> None:
    before = _baseline()
    after = _spec(
        search_name="GenesByMassSpec",
        resolved={_OPEN: NumberValue(value=2)},
        open_names=[],
    )

    problem = undeclared_spec_changes(diff_specs(before, after), _KEPT, before)

    assert [name for name in (_ID,) if name in problem] == [_ID]
