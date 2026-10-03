"""The caveat a value the request did not state makes: another reading of it
counts more genes, the count of that reading did not arrive, the pick
left options of its vocabulary untaken, or a picked label holds no word of the
looked-up concept."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field

from pathfinder.domain.strategy.measurement_clauses import shown_value
from pathfinder.domain.strategy.operational_spec import (
    CountedKind,
    Criterion,
    Measurement,
    OperationalSpec,
)

_READINGS: dict[CountedKind, str] = {
    "loosest_bound": "at {}",
    "wildcard_phrase": "for {}",
    "site_search_reach": "that the site search finds for {}",
    "any_strain": "with an ortholog in {}",
    "all_strains": "with an ortholog in {}",
    "site_default": "at the site's default, {}",
    "bound_count": "of the search at {}",
}
_SET_BY = {"default": "the site's default", "chosen": "chosen"}
AssumedSource = Literal["default", "chosen"]


class AssumedValueCaveat(CamelModel):
    """A value the request did not state, where another reading counts more genes."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["assumed_value"] = "assumed_value"
    criterion_id: str
    param_display_name: str
    value: str
    source: AssumedSource
    bound_count: int
    reading_kind: CountedKind
    reading: str
    reading_count: int

    @computed
    def sentence(self) -> str:
        """The value, who set it, and the count at it beside the other reading's."""
        return (
            f"{self.param_display_name} is {self.value}, {_SET_BY[self.source]}: "
            f"{self.bound_count:,} genes at that value, {self.reading_count:,} "
            f"{_READINGS[self.reading_kind].format(self.reading)}"
        )

    def texts(self) -> list[str]:
        return [self.value]

    def redacted(self, redact: Callable[[str], str]) -> AssumedValueCaveat:
        return self.model_copy(update={"value": redact(self.value)})


class UnmeasuredValueCaveat(CamelModel):
    """A value the request did not state, whose other reading did not arrive."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["unmeasured_value"] = "unmeasured_value"
    criterion_id: str
    param_display_name: str
    value: str
    source: AssumedSource
    reading_kind: CountedKind
    reading: str

    @computed
    def sentence(self) -> str:
        """The value, who set it, and the reading that was not counted."""
        return (
            f"{self.param_display_name} is {self.value}, {_SET_BY[self.source]}: "
            f"its effect was not measured, since the count "
            f"{_READINGS[self.reading_kind].format(self.reading)} did not arrive"
        )

    def texts(self) -> list[str]:
        return [self.value]

    def redacted(self, redact: Callable[[str], str]) -> UnmeasuredValueCaveat:
        return self.model_copy(update={"value": redact(self.value)})


class ChoiceCaveat(CamelModel):
    """A pick the request did not state, and the options of its vocabulary it
    did not take. ``unchosen`` is empty when the vocabulary is too large to list."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["chosen_among"] = "chosen_among"
    criterion_id: str
    param_display_name: str
    value: str
    source: AssumedSource
    unchosen: list[str] = Field(default_factory=list)
    unchosen_count: int

    @computed
    def sentence(self) -> str:
        """The value, who set it, and the options it did not take."""
        taken = f"{self.param_display_name} is {self.value}, {_SET_BY[self.source]}"
        if self.unchosen:
            return f"{taken}; the options not taken: {', '.join(self.unchosen)}"
        return f"{taken}; {self.unchosen_count:,} options not taken"

    def texts(self) -> list[str]:
        return [self.value]

    def redacted(self, redact: Callable[[str], str]) -> ChoiceCaveat:
        return self.model_copy(update={"value": redact(self.value)})


class LabelGapCaveat(CamelModel):
    """A picked entry the request did not state, whose label holds no word of
    the concept the lookup read."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["label_without_the_concept"] = "label_without_the_concept"
    criterion_id: str
    param_display_name: str
    value: str
    source: AssumedSource
    reading: str

    @computed
    def sentence(self) -> str:
        """The entry, who set it, and the terms its label holds no word of."""
        return (
            f"{self.param_display_name} took {self.value!r}, "
            f"{_SET_BY[self.source]}, whose label holds no word of {self.reading}"
        )

    def texts(self) -> list[str]:
        return [self.value]

    def redacted(self, redact: Callable[[str], str]) -> LabelGapCaveat:
        return self.model_copy(update={"value": redact(self.value)})


ValueCaveat = AssumedValueCaveat | UnmeasuredValueCaveat | ChoiceCaveat | LabelGapCaveat


def _value_caveat(
    criterion: Criterion, m: Measurement, source: AssumedSource
) -> ValueCaveat | None:
    """The caveat one measurement of a default or chosen value makes, if any."""
    name = criterion.display_name_of(m.param)
    value = shown_value(criterion.resolved_params[m.param].value)
    match m.kind, m.count, criterion.result_count:
        case (
            (
                "vocabulary_label"
                | "phrase_reading"
                | "not_measurable"
                | "picked_from_a_cut_list"
                | "picked_from_a_lookup"
            ),
            _,
            _,
        ):
            return None
        case "label_without_the_concept", _, _:
            return LabelGapCaveat(
                criterion_id=criterion.id,
                param_display_name=name,
                value=m.label,
                source=source,
                reading=m.reading,
            )
        case "options_not_taken", _, _:
            return ChoiceCaveat(
                criterion_id=criterion.id,
                param_display_name=name,
                value=value,
                source=source,
                unchosen=m.unchosen,
                unchosen_count=m.unchosen_count,
            )
        case kind, None, _:
            return UnmeasuredValueCaveat(
                criterion_id=criterion.id,
                param_display_name=name,
                value=value,
                source=source,
                reading_kind=kind,
                reading=m.reading,
            )
        case kind, int() as count, int() as bound if count > bound:
            return AssumedValueCaveat(
                criterion_id=criterion.id,
                param_display_name=name,
                value=value,
                source=source,
                bound_count=bound,
                reading_kind=kind,
                reading=m.reading,
                reading_count=count,
            )
        case _:
            return None


def _narrowing(criterion: Criterion) -> list[ValueCaveat]:
    """One caveat per default or chosen value a counted reading widens, or whose
    reading did not arrive."""
    found: list[ValueCaveat] = []
    for m in criterion.measurements:
        bound = criterion.resolved_params.get(m.param)
        if bound is None:
            continue
        match bound.source:
            case "default" | "chosen" as source:
                caveat = _value_caveat(criterion, m, source)
                if caveat is not None:
                    found.append(caveat)
            case _:
                pass
    return found


def assumed_value_caveats(spec: OperationalSpec | None) -> list[ValueCaveat]:
    """Every value of the spec the request did not state that narrows its step."""
    if spec is None:
        return []
    return [caveat for c in spec.criteria for caveat in _narrowing(c)]


__all__ = [
    "AssumedValueCaveat",
    "ChoiceCaveat",
    "LabelGapCaveat",
    "UnmeasuredValueCaveat",
    "ValueCaveat",
    "assumed_value_caveats",
]
