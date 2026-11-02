from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field

from pathfinder.domain.caveats import EditDirection

type Effect = Literal["none", "new", "add", "change", "remove", "undo"]
type Want = Literal[
    "nothing",
    "status",
    "show_records",
    "show_again",
    "explain",
    "recommend",
    "compare",
    "count_by_value",
    "look_up",
    "analysis",
    "save_export",
    "help",
]
type RequirementKind = Literal[
    "organism",
    "record_type",
    "data_type",
    "percentile",
    "fold_change",
    "significance",
    "count",
    "ortholog",
    "text",
    "property",
    "untyped",
]
type ReadBy = Literal["decisions", "model", "script"]


class MessageReading(CamelModel):
    model_config = ConfigDict(frozen=True)

    effect: Effect
    wants: Want
    answers_open: bool = False
    disputes_result: bool = False
    audit: bool = False
    remember: bool = False
    context_only: bool = False
    off_topic: bool = False
    edit_direction: EditDirection = "other"
    read_by: ReadBy
    effect_confidence: float = Field(default=1.0, ge=0, le=1)
    wants_confidence: float = Field(default=1.0, ge=0, le=1)


class StatedRequirement(CamelModel):
    model_config = ConfigDict(frozen=True)

    quote: str = Field(min_length=1)
    kind: RequirementKind
    value: str = Field(min_length=1)
    hard: bool = True


class StatedWithdrawal(CamelModel):
    model_config = ConfigDict(frozen=True)

    quote: str = Field(min_length=1)
    kind: RequirementKind
    value: str = Field(min_length=1)


class StatedRequest(CamelModel):
    model_config = ConfigDict(frozen=True)

    goal: str = Field(default="", max_length=500)
    requirements: list[StatedRequirement] = Field(default_factory=list)
    withdrawn: list[StatedWithdrawal] = Field(default_factory=list)
    asks: list[str] = Field(default_factory=list)
    differential_sides: list[str] = Field(default_factory=list, max_length=2)
    referenced_step_ids: list[str] = Field(default_factory=list)
    named_gene_ids: list[str] = Field(default_factory=list)
    positive_control_ids: list[str] = Field(default_factory=list)
    negative_control_ids: list[str] = Field(default_factory=list)

    def quotes_outside(self, said: str) -> list[str]:
        quoted = [r.quote for r in self.requirements] + [
            w.quote for w in self.withdrawn
        ]
        return [q for q in quoted if q not in said]

    def within(self, said: str) -> StatedRequest:
        return self.model_copy(
            update={
                "requirements": [r for r in self.requirements if r.quote in said],
                "withdrawn": [w for w in self.withdrawn if w.quote in said],
            }
        )


__all__ = [
    "Effect",
    "MessageReading",
    "ReadBy",
    "RequirementKind",
    "StatedRequest",
    "StatedRequirement",
    "StatedWithdrawal",
    "Want",
]
