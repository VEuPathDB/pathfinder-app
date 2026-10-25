"""The steps between the result and a tallied step that is not the result."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import ConfigDict
from veupathdb.domain.strategy import StepKind, StrategyStep
from veupathdb.model import CamelModel

from pathfinder.domain.column_reach import StepReach, TransformReach


class StepAbove(CamelModel):
    model_config = ConfigDict(frozen=True)

    wdk_step_id: int
    display_name: str
    transforms_only: bool


class TallyPath(CamelModel):
    model_config = ConfigDict(frozen=True)

    tallied_step_id: int
    record_type: str
    above: list[StepAbove]

    @property
    def removable(self) -> bool:
        return bool(self.above) and all(s.transforms_only for s in self.above)

    def names(self) -> str:
        return ", ".join(f'"{s.display_name}"' for s in self.above)

    def leads_back(self, reach: StepReach, transform: TransformReach) -> bool:
        return (
            self.removable
            and self.above[0].wdk_step_id == reach.wdk_step_id
            and transform.record_type == self.record_type
        )


def _record_type(steps: Mapping[str, StrategyStep], step_id: str) -> str:
    step = steps[step_id]
    if step.kind is StepKind.COMBINE and step.primary_input_id is not None:
        return _record_type(steps, step.primary_input_id)
    return step.record_class or ""


def _path(
    steps: Mapping[str, StrategyStep], step_id: str, target: str
) -> list[str] | None:
    if step_id == target:
        return []
    for input_id in steps[step_id].input_ids():
        below = _path(steps, input_id, target)
        if below is not None:
            return [step_id, *below]
    return None


def tally_paths(
    steps: Mapping[str, StrategyStep],
    wdk_ids: Mapping[str, int],
    root_id: str,
    tallied: Sequence[int],
) -> list[TallyPath]:
    by_wdk = {wdk: sid for sid, wdk in wdk_ids.items() if sid in steps}
    paths: list[TallyPath] = []
    for wdk_step_id in dict.fromkeys(tallied):
        target = by_wdk.get(wdk_step_id)
        found = None if target is None else _path(steps, root_id, target)
        if target is None or not found:
            continue
        paths.append(
            TallyPath(
                tallied_step_id=wdk_step_id,
                record_type=_record_type(steps, target),
                above=[
                    StepAbove(
                        wdk_step_id=wdk_ids[sid],
                        display_name=steps[sid].display_label,
                        transforms_only=steps[sid].kind is StepKind.TRANSFORM,
                    )
                    for sid in found
                    if sid in wdk_ids
                ],
            )
        )
    return paths


__all__ = ["StepAbove", "TallyPath", "tally_paths"]
