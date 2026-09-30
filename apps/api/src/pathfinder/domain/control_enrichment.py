"""The enrichment of positives among the controls a target returned."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict, Field


class ControlEnrichment(CamelModel):
    """The one-sided hypergeometric test of positives among the returned controls.

    The population is every control tested, the draws are the controls the
    target returned, and ``p_value`` is the chance of at least that many positives.
    """

    model_config = ConfigDict(frozen=True)

    population: int = Field(ge=1)
    positives: int = Field(ge=0)
    returned: int = Field(ge=0)
    positives_returned: int = Field(ge=0)
    p_value: float = Field(ge=0.0, le=1.0)


__all__ = ["ControlEnrichment"]
