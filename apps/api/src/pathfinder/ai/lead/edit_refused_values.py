from __future__ import annotations

from collections.abc import Collection

import pydantic
from veupathdb.errors import ParamMessages, ValidationError

from pathfinder.ai.lead.edit_messages import wdk_refused_the_written_step_message
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.spec_diff import SpecDiff

_REFUSED_PARAMS = pydantic.TypeAdapter(list[ParamMessages])


def _params_wdk_named(exc: ValidationError) -> frozenset[str]:
    """The parameter names the refusal rows carry, empty when it carries none."""
    try:
        rows = _REFUSED_PARAMS.validate_python(exc.errors or [])
    except pydantic.ValidationError:
        return frozenset()
    return frozenset(row.param for row in rows)


def _steps_the_edit_writes(
    diff: SpecDiff, after: OperationalSpec, added: Collection[str]
) -> list[Criterion]:
    """The criteria whose values this edit sends to VEuPathDB.

    A criterion the edit builds a step for is written whatever the diff calls
    it, because the spec it is compared against already held it.
    """
    written = {
        change.criterion_id
        for change in diff.changes
        if change.disposition in {"added", "changed"}
    } | set(added)
    return [criterion for criterion in after.criteria if criterion.id in written]


def refused_values_message(
    exc: ValidationError,
    *,
    diff: SpecDiff,
    after: OperationalSpec,
    added: Collection[str],
) -> str:
    """The refusal for values VEuPathDB turned down while the edit was pushed.

    The refused step is the one this edit writes that states a parameter the
    answer names; every written step is named when the answer names none.
    """
    params = _params_wdk_named(exc)
    written = _steps_the_edit_writes(diff, after, added)
    named = [c for c in written if not params.isdisjoint(c.resolved_params)]
    return wdk_refused_the_written_step_message(
        exc.detail or str(exc),
        steps=[f"[{c.id}] {c.search_name}" for c in (named or written)],
        params=sorted(params),
    )
