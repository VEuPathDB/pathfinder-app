"""The caveat of a reading the researcher accepted: what it leaves out of their
words."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict

from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.domain.strategy.readings import AcceptedReading

_REPLACES_NONE = (
    "The question named no stated requirement, so the pick replaces none and each "
    "requirement it approximates is still judged on its own words."
)


class ReadingCaveat(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["reading"] = "reading"
    criterion_id: str
    reading: str
    caveat: str
    names_no_requirement: bool = False

    @computed
    def sentence(self) -> str:
        said = f"Read as '{self.reading}'"
        return " ".join(
            [
                f"{said}: {self.caveat}" if self.caveat else f"{said}.",
                *([_REPLACES_NONE] if self.names_no_requirement else []),
            ]
        )

    def texts(self) -> list[str]:
        return [self.reading, self.caveat]

    def redacted(self, redact: Callable[[str], str]) -> ReadingCaveat:
        return self.model_copy(
            update={"reading": redact(self.reading), "caveat": redact(self.caveat)}
        )


def reading_caveats(spec: OperationalSpec | None) -> list[ReadingCaveat]:
    if spec is None:
        return []
    return [
        ReadingCaveat(
            criterion_id=c.id,
            reading=held.reading,
            caveat=held.caveat,
            names_no_requirement=held.names_no_requirement,
        )
        for c in spec.criteria
        if (held := c.held_reading) is not None
        and (held.caveat or held.names_no_requirement)
    ]


def reading_line(criterion: Criterion, held: AcceptedReading) -> str:
    values = ", ".join(
        f"{criterion.display_name_of(name)} = {value}"
        for name, value in held.params.items()
    )
    line = f"'{held.reading}', stated by {values}"
    noted = f"{line}; its caveat: {held.caveat}" if held.caveat else line
    return f"{noted}. {_REPLACES_NONE}" if held.names_no_requirement else noted
