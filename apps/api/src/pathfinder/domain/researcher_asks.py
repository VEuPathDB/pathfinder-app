from __future__ import annotations

from pydantic import ConfigDict
from veupathdb.model import CamelModel


class ResearcherAsk(CamelModel):
    model_config = ConfigDict(frozen=True)

    message: str
    text: str


__all__ = ["ResearcherAsk"]
