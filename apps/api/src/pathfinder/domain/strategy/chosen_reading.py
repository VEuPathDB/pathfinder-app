from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field


class ChosenReading(CamelModel):
    model_config = ConfigDict(frozen=True)

    chosen: str = Field(
        min_length=1,
        description="A short label of the reading you built, in the researcher's terms.",
    )
    alternatives: list[str] = Field(
        min_length=1,
        description="A short label of each other reading the request allows.",
    )

    def labels(self) -> list[str]:
        return [self.chosen, *self.alternatives]


__all__ = ["ChosenReading"]
