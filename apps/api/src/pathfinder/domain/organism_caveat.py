from __future__ import annotations

from collections.abc import Callable
from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict


class RecordsOrganismCaveat(CamelModel):
    model_config = ConfigDict(frozen=True)

    kind: Literal["records_organism"] = "records_organism"
    records: list[str]
    seed: list[str]

    @computed
    def sentence(self) -> str:
        return (
            f"The strategy's records are genes of {', '.join(self.records)}; "
            f"the seed searched {', '.join(self.seed)}"
        )

    def texts(self) -> list[str]:
        return [*self.records, *self.seed]

    def redacted(self, redact: Callable[[str], str]) -> RecordsOrganismCaveat:
        return self


__all__ = ["RecordsOrganismCaveat"]
