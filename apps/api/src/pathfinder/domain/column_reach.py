from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict

type ColumnReach = Literal["step", "transform", "none"]


class ReachedColumn(CamelModel):
    model_config = ConfigDict(frozen=True)

    name: str
    display_name: str


class TransformReach(CamelModel):
    model_config = ConfigDict(frozen=True)

    search_name: str
    display_name: str
    record_type: str
    countable: int
    columns: list[ReachedColumn]


class StepReach(CamelModel):
    model_config = ConfigDict(frozen=True)

    wdk_step_id: int
    record_type: str
    transforms: list[TransformReach]
    tallies_before: int = 0

    @property
    def reach(self) -> ColumnReach:
        if any(t.countable for t in self.transforms):
            return "transform"
        return "none"

    def unfollowed(self, tallies: int) -> bool:
        return self.reach == "transform" and tallies == self.tallies_before


__all__ = ["ColumnReach", "ReachedColumn", "StepReach", "TransformReach"]
