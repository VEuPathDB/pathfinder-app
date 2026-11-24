from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict

_WAITS_ON = {
    "answer": "Not applied, waiting on your answer: ",
    "build": "Not applied until the strategy is built: ",
}


class PendingPlan(CamelModel):
    model_config = ConfigDict(frozen=True)

    text: str
    waits_on: Literal["answer", "build"] = "answer"

    @computed
    def rendered(self) -> str:
        return _WAITS_ON[self.waits_on] + self.text
