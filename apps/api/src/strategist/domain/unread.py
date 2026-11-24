from __future__ import annotations

from pydantic import ConfigDict
from veupathdb.model import CamelModel


class Unread(CamelModel):
    model_config = ConfigDict(frozen=True)

    reason: str
