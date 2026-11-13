"""One named disagreement between a case's expectation and its run."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict


class CaseDifference(CamelModel):
    """One named disagreement between the expectation and the run.

    ``read`` names the text a phrase check read; other checks read none.
    """

    model_config = ConfigDict(frozen=True)

    field: str
    expected: str
    actual: str
    read: str = ""


__all__ = ["CaseDifference"]
