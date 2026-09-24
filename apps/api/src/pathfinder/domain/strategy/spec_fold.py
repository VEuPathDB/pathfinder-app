"""The fold: a criterion the structure leaves out states its values on the
criterion that runs the same search."""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pydantic import ConfigDict
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.model import CamelModel

from pathfinder.domain.strategy.operational_spec import (
    AssumedValue,
    Criterion,
    OperationalSpec,
    structure_criteria,
)


class FoldedSpec(CamelModel):
    """The spec the fold produced, and the options it could not place."""

    model_config = ConfigDict(frozen=True)

    spec: OperationalSpec
    unplaced: tuple[str, ...] = ()


def stated_wire_values(spec: OperationalSpec | None) -> dict[str, dict[str, str]]:
    """The wire values each criterion of a spec states, by criterion id."""
    if spec is None:
        return {}
    return {
        criterion.id: {
            name: to_wire(value) for name, value in criterion.resolved_params.items()
        }
        for criterion in spec.criteria
    }


def fold_option_criteria(
    spec: OperationalSpec,
    *,
    live_step_ids: Collection[str] = (),
    answered_values: Mapping[str, Mapping[str, str]] | None = None,
) -> FoldedSpec:
    """Move an option onto the step that runs its search.

    A criterion the structure leaves out states its values on the criterion that
    names the same search; one no single criterion carries is reported unplaced.
    A criterion the strategy holds a step for runs that step, so it is never an
    option however the structure reads. ``answered_values`` are the values the
    strategy already answers to, which is how a value the carrier only
    inherited is told from one this pass stated for it.
    """
    answered = answered_values or {}
    named = structure_criteria(spec.structure)
    answers_to_a_step = named | frozenset(live_step_ids)
    if all(c.id in answers_to_a_step for c in spec.criteria):
        return FoldedSpec(spec=spec)
    folded = spec.model_copy(deep=True)
    # An analysis states its own document, so it carries no option and is none.
    carriers = [c for c in folded.criteria if c.id in named and c.analysis is None]
    absorbed: set[str] = set()
    unplaced: list[str] = []
    for option in folded.criteria:
        if (
            option.id in answers_to_a_step
            or not option.search_name
            or option.open_params
            or option.analysis is not None
        ):
            continue
        runs_it = [c for c in carriers if c.search_name == option.search_name]
        if len(runs_it) != 1 or not _carry_the_option(
            runs_it[0], option, answered.get(runs_it[0].id, {})
        ):
            unplaced.append(option.id)
            continue
        absorbed.add(option.id)
    if not absorbed:
        return FoldedSpec(spec=spec, unplaced=tuple(unplaced))
    folded.criteria = [c for c in folded.criteria if c.id not in absorbed]
    return FoldedSpec(spec=folded, unplaced=tuple(unplaced))


def carried_values(carrier: Criterion) -> dict[str, str]:
    """The wire values a fold has already carried onto this criterion."""
    return {a.param_name: a.value for a in carrier.assumptions if a.carried_from}


def _carry_the_option(
    carrier: Criterion, option: Criterion, answered: Mapping[str, str]
) -> bool:
    """Give the carrier the values the option states, and report that it can.

    A value the option defaulted or the carrier's own text states does not
    move, and a value contradicting one the fold carried moves nothing at all.
    A value the carrier only holds because the strategy answers to it is the
    strategy's, and the option is what the request says about it.
    """
    carried = carried_values(carrier)
    assumed = {a.param_name for a in carrier.assumptions if not a.carried_from}
    defaulted = set(option.defaulted_params)
    stated: dict[str, ParamValue] = {}
    for name, value in option.resolved_params.items():
        if name in defaulted:
            continue
        if name in carried:
            if carried[name] != to_wire(value):
                return False
            continue
        held = name in carrier.resolved_params and name not in carrier.defaulted_params
        if held and name not in assumed:
            current = to_wire(carrier.resolved_params[name])
            if current == to_wire(value) or answered.get(name) != current:
                continue
        stated[name] = value
    carrier.resolved_params.update(stated)
    carrier.defaulted_params = sorted(set(carrier.defaulted_params) - set(stated))
    # The option replaces the assumption it overrides, so one value has one
    # reason on the ledger.
    carrier.assumptions = [
        *(a for a in carrier.assumptions if a.param_name not in stated),
        *(
            AssumedValue(
                param_name=name,
                value=to_wire(value),
                reason=option.text,
                carried_from=option.id,
            )
            for name, value in stated.items()
        ),
    ]
    return True
