from __future__ import annotations

from collections.abc import Collection
from typing import Annotated, Literal

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Discriminator, Field

from pathfinder.domain.caveats import EditDirection
from pathfinder.domain.log2_scale import Scale
from pathfinder.domain.strategy.constraints import (
    Bound,
    DataKind,
    DataTypeValue,
    FoldChangeValue,
    FoldDirection,
    OrganismValue,
    PercentileEnd,
    PercentileValue,
    RecordRole,
    RecordTypeValue,
    RequirementValue,
    Share,
    SignificanceValue,
    Statistic,
    UntypedValue,
)

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


class _Stated(CamelModel):
    model_config = ConfigDict(frozen=True)

    quote: str = Field(min_length=1)
    value: str = Field(min_length=1)
    hard: bool = True
    beside: str = ""

    def on_the_site(self, listed: Collection[str]) -> _Stated:
        del listed
        return self


class StatedPercentile(_Stated):
    kind: Literal["percentile"]
    end: PercentileEnd
    share: Share

    def typed(self) -> RequirementValue:
        return PercentileValue(end=self.end, share=self.share)


class StatedFoldChange(_Stated):
    kind: Literal["fold_change"]
    cut: float | None = None
    scale: Scale = "fold"
    direction: FoldDirection = "either"

    def typed(self) -> RequirementValue:
        return FoldChangeValue(cut=self.cut, scale=self.scale, direction=self.direction)


class StatedSignificance(_Stated):
    kind: Literal["significance"]
    statistic: Statistic = "unspecified"
    at_most: Bound

    def typed(self) -> RequirementValue:
        return SignificanceValue(statistic=self.statistic, at_most=self.at_most)


class StatedDataType(_Stated):
    kind: Literal["data_type"]
    data: DataKind

    def typed(self) -> RequirementValue:
        return DataTypeValue(data=self.data)


class StatedRecordType(_Stated):
    kind: Literal["record_type"]
    record_class: str = Field(min_length=1)
    role: RecordRole = "answer"

    def typed(self) -> RequirementValue:
        return RecordTypeValue(record_class=self.record_class, role=self.role)

    def on_the_site(self, listed: Collection[str]) -> _Stated:
        if self.record_class in listed:
            return self
        return StatedUntyped(
            kind="untyped",
            quote=self.quote,
            value=self.value,
            hard=self.hard,
            beside=self.beside,
        )


class StatedOrganism(_Stated):
    kind: Literal["organism"]
    organism: str = Field(min_length=1)

    def typed(self) -> RequirementValue:
        return OrganismValue(organism=self.organism)


class StatedUntyped(_Stated):
    kind: Literal["untyped"]

    def typed(self) -> RequirementValue:
        return UntypedValue(text=self.value)


class StatedOther(_Stated):
    kind: Literal["count", "ortholog", "text", "property"]

    def typed(self) -> RequirementValue | None:
        return None


StatedRequirement = Annotated[
    StatedPercentile
    | StatedFoldChange
    | StatedSignificance
    | StatedDataType
    | StatedRecordType
    | StatedOrganism
    | StatedUntyped
    | StatedOther,
    Discriminator("kind"),
]


class StatedWithdrawal(CamelModel):
    model_config = ConfigDict(frozen=True)

    quote: str = Field(min_length=1)
    requirement: str = ""


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

    def within(
        self, said: str, held: Collection[str], record_classes: Collection[str]
    ) -> StatedRequest:
        return self.model_copy(
            update={
                "requirements": [
                    r.on_the_site(record_classes)
                    for r in self.requirements
                    if r.quote in said
                ],
                "withdrawn": [
                    w
                    for w in self.withdrawn
                    if w.quote in said and w.requirement in held
                ],
            }
        )


__all__ = [
    "Effect",
    "MessageReading",
    "ReadBy",
    "RequirementKind",
    "StatedDataType",
    "StatedFoldChange",
    "StatedOrganism",
    "StatedOther",
    "StatedPercentile",
    "StatedRecordType",
    "StatedRequest",
    "StatedRequirement",
    "StatedSignificance",
    "StatedUntyped",
    "StatedWithdrawal",
    "Want",
]
