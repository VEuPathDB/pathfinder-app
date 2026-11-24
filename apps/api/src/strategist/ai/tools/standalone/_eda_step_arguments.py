"""The place and the volcano cut an export call names, as its argument types."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.strategy import CombineOp

from strategist.domain.eda_parts import EdaEffectDirection


class _Argument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class WaitingCriterion(_Argument):
    kind: Literal["criterion"]
    criterion_id: str = Field(
        description="A criterion the pinned route names as waiting for this analysis."
    )


class IntoSlot(_Argument):
    kind: Literal["into_slot"]
    attach_to_step_id: str = Field(description="The combine step to wire this into.")
    slot: Literal["primary", "secondary"] = Field(
        description="Which input of that combine to fill. It must be empty."
    )


class InPlaceOf(_Argument):
    kind: Literal["replace"]
    replace_step_id: str = Field(description="The step this export takes the place of.")


class BesideRoot(_Argument):
    kind: Literal["beside_root"]
    operator: CombineOp = Field(
        description="The operator of the new combine over the old root and the export."
    )


ExportPlacement = Annotated[
    WaitingCriterion | IntoSlot | InPlaceOf | BesideRoot, Field(discriminator="kind")
]


class VolcanoCut(_Argument):
    effect_size_threshold: float = Field(
        description="Minimum absolute effect size to keep."
    )
    significance_threshold: float = Field(description="Maximum p-value to keep.")
    effect_direction: EdaEffectDirection | None = Field(
        default=None,
        description="upOnly keeps group B's side, downOnly group A's.",
    )


def replaced_step(placement: ExportPlacement | None) -> str | None:
    match placement:
        case InPlaceOf(replace_step_id=step_id):
            return step_id
        case _:
            return None


__all__ = [
    "BesideRoot",
    "ExportPlacement",
    "InPlaceOf",
    "IntoSlot",
    "VolcanoCut",
    "WaitingCriterion",
    "replaced_step",
]
