from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict
from veupathdb.domain.strategy.graph_model import StrategyStep


class UnrevisableSubsetCaveat(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["unrevisable_subset"] = "unrevisable_subset"
    step: str

    @computed
    def sentence(self) -> str:
        return (
            f"The site's Revise form cannot edit the dataset filter of "
            f"'{self.step}'; ask Strategist to change it."
        )

    def texts(self) -> list[str]:
        return [self.step]

    def redacted(self, redact: Callable[[str], str]) -> UnrevisableSubsetCaveat:
        return self.model_copy(update={"step": redact(self.step)})


def unrevisable_subset_caveats(
    steps: Mapping[str, StrategyStep], generic_search: str
) -> list[UnrevisableSubsetCaveat]:
    return [
        UnrevisableSubsetCaveat(step=step.display_label)
        for step in steps.values()
        if step.search_name == generic_search
    ]
