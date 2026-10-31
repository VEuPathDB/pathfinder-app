"""A reading of a free-text or range value that a question offers, and the
reading the researcher accepted for a criterion."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import ConfigDict, Field
from veupathdb.domain.parameters import ParamKind, ParamValue, from_wire
from veupathdb.model import CamelModel

from pathfinder.domain.clipped import text_clipped_to
from pathfinder.domain.strategy.words import words_of

_READING_LIMIT = 90
_LABEL_LIMIT = 120
_CAVEAT_LIMIT = 300
_READINGS_LIMIT = 3
READABLE_KINDS: frozenset[ParamKind] = frozenset(
    {"string", "number", "number-range", "date", "date-range", "timestamp"}
)


def why_no_readings(
    kind: ParamKind, *, listed: bool, pasted: bool, open_beside: str
) -> str:
    if kind not in READABLE_KINDS:
        return f"takes {kind}; only a free-text or range parameter takes readings"
    if listed or pasted:
        return "takes a value the researcher picks or pastes, which has no reading"
    if open_beside:
        return f"bind the rest of {open_beside} before its readings"
    return ""


class ReadingChooser(StrEnum):
    RESEARCHER_ON_A_CARD = "researcher_on_a_card"
    ASSISTANT = "assistant"


class Reading(CamelModel):
    model_config = ConfigDict(frozen=True)

    label: Annotated[str, Field(min_length=1), text_clipped_to(_READING_LIMIT)]
    value: str = Field(min_length=1)
    caveat: Annotated[str, text_clipped_to(_CAVEAT_LIMIT)] = ""


class ReadValues(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["read_values"] = "read_values"
    criterion_id: str
    params: dict[str, str] = Field(min_length=1)
    reading: str = Field(min_length=1, max_length=_LABEL_LIMIT)
    caveat: str = Field(default="", max_length=_CAVEAT_LIMIT)
    replaces: list[str] = Field(default_factory=list)
    names_no_requirement: bool = False

    def accepted(self, chosen_by: ReadingChooser) -> AcceptedReading:
        return AcceptedReading(
            reading=self.reading,
            chosen_by=chosen_by,
            caveat=self.caveat,
            params=self.params,
            replaces=self.replaces,
            names_no_requirement=self.names_no_requirement,
        )


class AcceptedReading(CamelModel):
    model_config = ConfigDict(frozen=True)

    reading: str = Field(min_length=1, max_length=_LABEL_LIMIT)
    caveat: str = Field(default="", max_length=_CAVEAT_LIMIT)
    params: dict[str, str] = Field(min_length=1)
    replaces: list[str] = Field(default_factory=list)
    names_no_requirement: bool = False
    stand_in: str = ""
    chosen_by: ReadingChooser = ReadingChooser.ASSISTANT

    def unbound(self, values: Mapping[str, ParamValue]) -> list[str]:
        return [
            name
            for name, wire in self.params.items()
            if name not in values or from_wire(values[name].type, wire) != values[name]
        ]

    def same_reading(self, other: AcceptedReading | None) -> bool:
        return (
            other is not None
            and other.reading == self.reading
            and other.params == self.params
        )


type _Keys = list[str] | str | None


def _listed(keys: _Keys) -> list[str]:
    match keys:
        case None:
            return []
        case str():
            return [keys]
        case list():
            return keys


class _KeyedReading(CamelModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)

    requirements: _Keys = None


class KeysOnTheReadings(CamelModel):
    model_config = ConfigDict(extra="allow", coerce_numbers_to_str=True)

    requirements: _Keys = None
    readings: list[_KeyedReading] = Field(min_length=1)

    def on_the_question(self) -> dict[str, object]:
        keys = [
            *_listed(self.requirements),
            *(k for r in self.readings for k in _listed(r.requirements)),
        ]
        return {
            **self.model_dump(by_alias=True),
            "requirements": list(dict.fromkeys(keys)),
        }


def reading_problems(
    readings: Sequence[Reading],
    *,
    options: Sequence[str],
    names_a_slot: bool,
) -> list[str]:
    if not readings:
        return []
    labels = {tuple(words_of(r.label)) or (r.label,) for r in readings}
    return [
        *(
            ["keep three readings at most, as a card offers no more"]
            if len(readings) > _READINGS_LIMIT
            else []
        ),
        *(
            ["drop its `options`, as a question offers readings or values, never both"]
            if options
            else []
        ),
        *(
            ["offer a second reading, as one reading is no choice"]
            if len(readings) == 1
            else []
        ),
        *(
            []
            if names_a_slot
            else ["name the `criterion_id` and `param_name` its readings set"]
        ),
        *(
            ["give each reading its own `value`, as two readings bind one value"]
            if len({r.value for r in readings}) != len(readings)
            else []
        ),
        *(
            ["give each reading its own `label`, as two readings share a label"]
            if len(labels) != len(readings)
            else []
        ),
    ]
