from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field
from veupathdb.domain.strategy import CombineOp
from veupathdb.model import CamelModel

OperatorRead = Literal["agrees", "disagrees", "unsure", "not_stated", "picked"]
OperatorSource = Literal["stated", "chosen", "card"]

_SOURCE: dict[OperatorRead, OperatorSource] = {
    "agrees": "stated",
    "picked": "card",
    "disagrees": "chosen",
    "unsure": "chosen",
    "not_stated": "chosen",
}


class OperatorReading(CamelModel):
    model_config = ConfigDict(frozen=True)

    criteria: list[str] = Field(min_length=2)
    built: CombineOp
    read: OperatorRead
    read_operator: CombineOp | None = None
    confidence: float = Field(default=0.0, ge=0, le=1)
    branches: list[list[str]] = Field(default_factory=list)

    @property
    def source(self) -> OperatorSource:
        return _SOURCE[self.read]

    def reads(self, criteria: frozenset[str], operator: CombineOp | None) -> bool:
        return frozenset(self.criteria) == criteria and self.built is operator


__all__ = ["OperatorRead", "OperatorReading", "OperatorSource"]
