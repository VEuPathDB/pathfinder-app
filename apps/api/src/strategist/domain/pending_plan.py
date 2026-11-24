from __future__ import annotations

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel, computed
from pydantic import ConfigDict, Field, model_validator

_WAITS_ON = {
    "answer": "Not applied, waiting on your answer: ",
    "build": "Not applied until the strategy is built: ",
}


class PendingPlan(CamelModel):
    model_config = ConfigDict(frozen=True)

    text: str = Field(exclude=True)
    waits_on: Literal["answer", "build"] = Field(default="answer", exclude=True)

    @model_validator(mode="before")
    @classmethod
    def _read_back(cls, data: object) -> object:
        match data:
            case {"rendered": str() as rendered, **rest} if "text" not in rest:
                for waits_on, prefix in _WAITS_ON.items():
                    if rendered.startswith(prefix):
                        return {"text": rendered[len(prefix) :], "waits_on": waits_on}
        return data

    @computed
    def rendered(self) -> str:
        return _WAITS_ON[self.waits_on] + self.text
