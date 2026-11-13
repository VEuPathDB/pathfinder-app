"""The name Strategist gives a step: what runs, and the labels of the values it binds."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ConfigDict, Field
from veupathdb.domain.parameters import ParamValue
from veupathdb.model import CamelModel
from veupathdb_mcp.catalog import RADIO_OFF

from strategist.domain.strategy.operational_spec import BoundValue, Criterion

__all__ = ["StepTitle", "TitleLabel", "criterion_title", "cut_on_a_word"]

LABELS_LENGTH = 60


def cut_on_a_word(shown: str) -> str:
    if len(shown) <= LABELS_LENGTH:
        return shown
    cut = shown[: LABELS_LENGTH + 1]
    boundary = cut.rfind(" ")
    return f"{cut[:boundary] if boundary > 0 else cut[:LABELS_LENGTH]}..."


class TitleLabel(CamelModel):
    model_config = ConfigDict(frozen=True)

    param: str
    wire: str
    label: str


class StepTitle(CamelModel):
    model_config = ConfigDict(frozen=True, extra="ignore")

    head: str
    labels: list[TitleLabel] = Field(default_factory=list)

    @property
    def name(self) -> str:
        shown = ", ".join(label.label for label in self.labels)
        if not shown:
            return self.head
        return f"{self.head}: {cut_on_a_word(shown)}"

    def kept(self, parameters: Mapping[str, ParamValue]) -> StepTitle:
        return self.model_copy(
            update={
                "labels": [
                    label
                    for label in self.labels
                    if (value := parameters.get(label.param)) is not None
                    and value.to_wire() == label.wire
                ]
            }
        )


def criterion_title(criterion: Criterion) -> StepTitle:
    """What runs, else the researcher's words, with the labels of the values the
    criterion binds."""
    return StepTitle(
        head=criterion.search_display_name or criterion.text[:60],
        labels=[
            TitleLabel(param=name, wire=bound.value.to_wire(), label=label)
            for name, bound in criterion.resolved_params.items()
            if (label := _label(criterion.radio_pairs, name, bound))
            and bound.visible
            and not bound.unset
            and name != criterion.organism_param
        ],
    )


def _label(pairs: Mapping[str, str], name: str, bound: BoundValue) -> str:
    off = bound.value.to_decoded() in (RADIO_OFF, [RADIO_OFF])
    if name in pairs.values():
        return "" if off else bound.value.to_wire()
    return "" if name in pairs and off else bound.label
