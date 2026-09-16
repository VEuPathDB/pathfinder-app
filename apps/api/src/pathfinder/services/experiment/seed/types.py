"""Seed definition models and the typed progress events ``run_seed`` yields."""

from typing import Literal

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field


class ControlSetDef(BaseModel):
    """A curated positive/negative gene-id pair shipped with a seed strategy."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    positive_ids: list[str]
    negative_ids: list[str]
    provenance_notes: str
    tags: list[str] = Field(default_factory=list)


class SeedDef(BaseModel):
    """One seed strategy and its control set, as stored in data/seeds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    site_id: str
    step_tree: JSONObject
    control_set: ControlSetDef
    record_type: str = "transcript"


# ---------------------------------------------------------------------------
# Progress events (SSE payloads)
# ---------------------------------------------------------------------------
#
# Each event has a ``type`` discriminator matching the SSE ``event:`` field.
# The transport layer derives the SSE event name from ``event.type`` and
# serializes the model body as the ``data:`` JSON payload.


class SeedProgress(CamelModel):
    """Periodic progress event. ``phase="starting"`` for the first frame
    (no per-item counters) and ``phase="running"`` for each item that
    begins processing."""

    type: Literal["seed_progress"] = "seed_progress"
    phase: Literal["starting", "running"]
    current: int | None = None
    total: int | None = None
    name: str | None = None
    message: str


class SeedStrategyComplete(CamelModel):
    """Emitted when a single seed strategy + control set finishes successfully."""

    type: Literal["seed_strategy_complete"] = "seed_strategy_complete"
    current: int
    total: int
    name: str
    wdk_strategy_id: int
    elapsed: float
    message: str


class SeedItemError(CamelModel):
    """Emitted when a single seed item fails. Other items continue."""

    type: Literal["seed_item_error"] = "seed_item_error"
    current: int
    total: int
    name: str
    error: str
    elapsed: float
    message: str


class SeedComplete(CamelModel):
    """Terminal event. Either the whole run finished, or a top-level
    failure occurred - in which case ``error`` is set and the counters
    reflect whatever was achieved before the failure."""

    type: Literal["seed_complete"] = "seed_complete"
    total: int = 0
    strategies_created: int = Field(default=0)
    control_sets_created: int = Field(default=0)
    failed: int = 0
    message: str
    error: str | None = None


SeedEvent = SeedProgress | SeedStrategyComplete | SeedItemError | SeedComplete
"""Discriminated union of all seed-stream event types."""
