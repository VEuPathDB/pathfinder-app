"""A column of a step's search read over the whole step against the values its
criterion binds."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, JsonValue, model_validator
from pydantic_core import PydanticCustomError

from pathfinder.domain.clipped import number_at_least

type ColumnFitState = Literal["all", "some", "none", "not_shown"]
type CountedIn = Literal["genes", "transcripts"]


def _counted(surely: int, at_most: int) -> str:
    return str(surely) if surely == at_most else f"{surely} to {at_most}"


# The counts a column fit row opens with: "569 of 569 transcripts fit" or
# "300 of 569 transcripts hold". A row counts records in the column's own unit.
COLUMN_FIT_COUNTS = re.compile(
    r"\b\d[\d,]*(?: to \d[\d,]*)? of \d[\d,]* (?:genes|transcripts) (?:fit|hold)\b"
)


class ThresholdSides(CamelModel):
    """The records on each side of one threshold whose direction the site does
    not state, when the step does not hold every record on one side."""

    model_config = ConfigDict(frozen=True)

    value: str
    # The records at the threshold or above it; a bin across it raises the most.
    above: Annotated[int, number_at_least(0)]
    above_at_most: Annotated[int, number_at_least(0)]
    below: Annotated[int, number_at_least(0)]
    below_at_most: Annotated[int, number_at_least(0)]

    @property
    def nesting_problem(self) -> str:
        if self.above > self.above_at_most or self.below > self.below_at_most:
            return "each side of a threshold holds surely <= at_most"
        return ""

    def sentence(self, total: int, counted_in: CountedIn, display_name: str) -> str:
        return (
            f"{_counted(self.above, self.above_at_most)} of {total} {counted_in} "
            f"hold {display_name} {self.value} or more and "
            f"{_counted(self.below, self.below_at_most)} hold {self.value} or fewer"
        )


UNREADABLE_COLUMN_FIT = "unreadable_column_fit"


class _StoredShown(CamelModel):
    model_config = ConfigDict(extra="ignore", from_attributes=True)

    shown: bool = True
    refused_status: int | None = None


class ColumnFit(CamelModel):
    """One column of a step's search, read over the whole step against the
    values its criterion binds."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    criterion_text: str
    wdk_step_id: int
    column: str
    display_name: str
    # The bounds whose side is known, as one range; empty when none is.
    bound_value: str
    counted_in: CountedIn
    total: Annotated[int, number_at_least(0)]
    # The records inside ``bound_value``; a bin across a bound raises the most.
    fitting: Annotated[int, number_at_least(0)]
    fitting_at_most: Annotated[int, number_at_least(0)]
    no_value: Annotated[int, number_at_least(0)] = 0
    refused_status: int | None = None
    sides: list[ThresholdSides] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _a_stored_unshown_fit_names_its_refusal(cls, data: JsonValue) -> JsonValue:
        stored = _StoredShown.model_validate(data)
        if not stored.shown and stored.refused_status is None:
            raise PydanticCustomError(
                UNREADABLE_COLUMN_FIT,
                "a stored column fit the site did not show names no refusal "
                "status, so its verdict cannot be read",
            )
        return data

    @computed
    def shown(self) -> bool:
        return self.refused_status is None

    @property
    def nesting_problem(self) -> str:
        if not self.fitting <= self.fitting_at_most <= self.total:
            return "a column fit holds fitting <= fitting_at_most <= total"
        if self.fitting_at_most + self.no_value > self.total:
            return "a column fit holds fitting_at_most + no_value <= total"
        if any(
            max(side.above_at_most, side.below_at_most) > self.total
            for side in self.sides
        ):
            return "a side of a threshold holds at most the step's records"
        if not self.shown and (self.total or self.sides):
            return "a column the site refused carries no count"
        return next((p for side in self.sides if (p := side.nesting_problem)), "")

    @property
    def holds_no_value(self) -> bool:
        return self.total > 0 and self.no_value == self.total

    @computed
    def fits(self) -> ColumnFitState:
        """How many records of the step hold a value inside every bound."""
        if not self.shown:
            return "not_shown"
        if self.fitting_at_most == 0:
            return "none"
        return "all" if self.fitting == self.total and not self.sides else "some"

    @computed
    def sentence(self) -> str:
        """The records that fit out of the step, the records on each side of a
        threshold with no stated direction, or that the site refused the column."""
        if self.refused_status is not None:
            return (
                f"the site refused the {self.display_name} ({self.column}) column "
                f"(HTTP {self.refused_status}) for '{self.criterion_text}'"
            )
        inside = (
            [
                (
                    f"{_counted(self.fitting, self.fitting_at_most)} of {self.total} "
                    f"{self.counted_in} fit {self.display_name} ({self.bound_value})"
                )
            ]
            if self.bound_value
            else []
        )
        sides = [
            side.sentence(self.total, self.counted_in, self.display_name)
            for side in self.sides
        ]
        unvalued = [f"{self.no_value} hold no value"] if self.no_value else []
        return "; ".join([*inside, *sides, *unvalued])

    @property
    def column_key(self) -> tuple[int, str]:
        """The step and the column this fit reads."""
        return self.wdk_step_id, self.column

    def texts(self) -> list[str]:
        return [self.criterion_text, self.display_name, self.bound_value]


__all__ = [
    "COLUMN_FIT_COUNTS",
    "UNREADABLE_COLUMN_FIT",
    "ColumnFit",
    "ColumnFitState",
    "CountedIn",
    "ThresholdSides",
]
