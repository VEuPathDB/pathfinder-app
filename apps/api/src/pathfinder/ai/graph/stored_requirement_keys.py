from __future__ import annotations

from collections.abc import Mapping, Sequence

from pathfinder.ai.graph.turn_records import TurnMarkers
from pathfinder.domain.caveats import Gap
from pathfinder.domain.site_checks import SiteCheck, SiteCheckGap
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ReplacedLifecycle,
)
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.question_options import (
    Keep,
    OptionBinding,
    TypedOption,
    Withdraw,
)
from pathfinder.domain.strategy.questions import OpenQuestion
from pathfinder.domain.strategy.readings import ReadValues
from pathfinder.domain.strategy.requirement_lifecycle import RetiredRequirement

type Ids = Mapping[str, str]

_STORED_NAMES = {kind: kind.value for kind in ConstraintKind} | {
    ConstraintKind.UNTYPED: "other"
}
_STORED_KINDS = frozenset(_STORED_NAMES.values())


def _stored_key(c: Constraint) -> str:
    return f"{_STORED_NAMES[c.kind]}:{c.requested_value}"


def ids_by_stored_key(recorded: Sequence[Constraint]) -> dict[str, str]:
    return {_stored_key(c): c.id for c in recorded}


def _ids(references: Sequence[str], ids: Ids) -> list[str]:
    return [ids.get(reference, reference) for reference in references]


def _retired_by_id(retired: RetiredRequirement, ids: Ids) -> RetiredRequirement:
    match retired.lifecycle:
        case ReplacedLifecycle(by=by) if by in ids:
            return retired.model_copy(
                update={"lifecycle": ReplacedLifecycle(by=ids[by])}
            )
        case _:
            return retired


def retired_by_id(
    retired: Sequence[RetiredRequirement], ids: Ids
) -> list[RetiredRequirement]:
    return [_retired_by_id(r, ids) for r in retired]


def _binding_by_id(binding: OptionBinding, ids: Ids) -> OptionBinding:
    match binding:
        case Withdraw(constraint_id=key) | Keep(constraint_id=key) if key in ids:
            return binding.model_copy(update={"constraint_id": ids[key]})
        case ReadValues(replaces=replaces) if any(key in ids for key in replaces):
            return binding.model_copy(update={"replaces": _ids(replaces, ids)})
        case _:
            return binding


def _option_by_id(option: TypedOption, ids: Ids) -> TypedOption:
    binding = _binding_by_id(option.binding, ids)
    if binding is option.binding:
        return option
    return option.model_copy(update={"binding": binding})


def _question_by_id(question: OpenQuestion, ids: Ids) -> OpenQuestion:
    options = [_option_by_id(o, ids) for o in question.options]
    if options == question.options:
        return question
    return question.model_copy(update={"options": options})


def questions_by_id(questions: Sequence[OpenQuestion], ids: Ids) -> list[OpenQuestion]:
    return [_question_by_id(q, ids) for q in questions]


def _criterion_by_id(criterion: Criterion, ids: Ids) -> Criterion:
    reading = criterion.accepted_reading
    if reading is None or not any(
        key in ids for key in [*reading.replaces, reading.stand_in]
    ):
        return criterion
    held = reading.model_copy(
        update={
            "replaces": _ids(reading.replaces, ids),
            "stand_in": ids.get(reading.stand_in, reading.stand_in),
        }
    )
    return criterion.model_copy(update={"accepted_reading": held})


def spec_by_id(spec: OperationalSpec | None, ids: Ids) -> OperationalSpec | None:
    if spec is None:
        return None
    criteria = [_criterion_by_id(c, ids) for c in spec.criteria]
    if all(new is old for new, old in zip(criteria, spec.criteria, strict=True)):
        return spec
    return spec.model_copy(update={"criteria": criteria})


def check_by_id(check: SiteCheck, ids: Ids) -> SiteCheck:
    if check.requirement not in ids:
        return check
    return check.model_copy(update={"requirement": ids[check.requirement]})


def _gap_by_id(gap: Gap, ids: Ids) -> Gap:
    match gap:
        case SiteCheckGap(check=check) if check.requirement in ids:
            return SiteCheckGap(check=check_by_id(check, ids))
        case _:
            return gap


def _gap_check(gap: Gap) -> list[SiteCheck]:
    match gap:
        case SiteCheckGap(check=check):
            return [check]
        case _:
            return []


def _unrecorded_key(reference: str, ids: Ids) -> bool:
    kind, separator, _ = reference.partition(":")
    return bool(separator) and kind in _STORED_KINDS and reference not in ids


def names_an_unrecorded_key(
    checks: Sequence[SiteCheck], gaps: Sequence[Gap], ids: Ids
) -> bool:
    named = [*checks, *(c for gap in gaps for c in _gap_check(gap))]
    return any(_unrecorded_key(check.requirement, ids) for check in named)


def gaps_by_id(gaps: Sequence[Gap], ids: Ids) -> list[Gap]:
    return [_gap_by_id(gap, ids) for gap in gaps]


def markers_by_id(markers: TurnMarkers, ids: Ids) -> TurnMarkers:
    answered = markers.answered
    if answered is None:
        return markers
    asked = questions_by_id(answered.questions, ids)
    if asked == answered.questions:
        return markers
    return markers.model_copy(
        update={"answered": answered.model_copy(update={"questions": asked})}
    )
