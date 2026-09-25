"""Seed definition models and the typed progress events ``run_seed`` yields."""

import datetime
import json
from collections import Counter
from typing import Literal, Self

from assistant_core.platform.pydantic_base import CamelModel
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field, model_validator
from veupathdb.domain.strategy import StrategyStepNode


def _coerce_param_value(value: object) -> object:
    """Convert a seed parameter from WDK wire format into a typed ParamValue.

    A value that is already typed passes through unchanged.
    """
    if isinstance(value, dict) or not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
    except ValueError, TypeError:
        return {"type": "string", "value": value}
    if isinstance(parsed, list):
        return {"type": "multi-pick-vocabulary", "values": [str(x) for x in parsed]}
    if isinstance(parsed, dict) and ("min" in parsed or "max" in parsed):
        bounds: dict[str, object] = {"type": "number-range"}
        if parsed.get("min") not in (None, ""):
            bounds["min"] = float(parsed["min"])
        if parsed.get("max") not in (None, ""):
            bounds["max"] = float(parsed["max"])
        return bounds
    return {"type": "string", "value": value}


def _coerce_step_tree_params(node: object) -> object:
    """Recursively coerce every step's ``parameters`` to typed ParamValues."""
    if not isinstance(node, dict):
        return node
    result: dict[str, object] = dict(node)
    params = result.get("parameters")
    if isinstance(params, dict):
        result["parameters"] = {k: _coerce_param_value(v) for k, v in params.items()}
    for child_key in ("primaryInput", "secondaryInput"):
        if result.get(child_key) is not None:
            result[child_key] = _coerce_step_tree_params(result[child_key])
    return result


def _repeated(ids: list[str]) -> list[str]:
    return sorted(gene_id for gene_id, times in Counter(ids).items() if times > 1)


class ControlSetDef(BaseModel):
    """A curated positive/negative gene-id pair shipped with a seed strategy.

    Each id is listed once, on one list.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    positive_ids: list[str]
    negative_ids: list[str]
    provenance_notes: str
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _each_id_is_listed_once(self) -> Self:
        repeated = _repeated(self.positive_ids + self.negative_ids)
        if repeated:
            msg = f"a control id is listed once, on one list: {repeated}"
            raise ValueError(msg)
        return self


class SeedMeasurement(BaseModel):
    """What the seed's own tree returned for its controls on one site build.

    A tree the site refused carries the refusal and no counts.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    site_build: str
    date: datetime.date
    positives_total: int
    negatives_total: int
    root_count: int | None = None
    positives_recovered: int | None = None
    negatives_admitted: int | None = None
    refusal: str | None = None

    @model_validator(mode="after")
    def _a_read_or_a_refusal(self) -> Self:
        counts = (self.root_count, self.positives_recovered, self.negatives_admitted)
        read = all(count is not None for count in counts)
        blank = all(count is None for count in counts)
        if not ((read and self.refusal is None) or (blank and self.refusal)):
            msg = "a measurement holds every count and no refusal, or a refusal alone"
            raise ValueError(msg)
        return self

    @property
    def recall(self) -> float | None:
        """The share of the positives the tree returned, or None when refused."""
        if self.positives_recovered is None:
            return None
        return self.positives_recovered / self.positives_total


class SeedDef(BaseModel):
    """One seed strategy and its control set, as stored in data/seeds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    description: str
    site_id: str
    step_tree: JSONObject
    control_set: ControlSetDef
    record_type: str = "transcript"
    measured: SeedMeasurement | None = None

    def step_node(self) -> StrategyStepNode:
        """The step tree with each parameter read from the wire form the file holds."""
        return StrategyStepNode.model_validate(_coerce_step_tree_params(self.step_tree))

    @model_validator(mode="after")
    def _the_measurement_counts_these_controls(self) -> Self:
        measured = self.measured
        if measured is None:
            return self
        totals = (
            len(self.control_set.positive_ids),
            len(self.control_set.negative_ids),
        )
        if (measured.positives_total, measured.negatives_total) != totals:
            msg = (
                f"the measurement counts {measured.positives_total} positives and "
                f"{measured.negatives_total} negatives; the controls hold {totals}"
            )
            raise ValueError(msg)
        return self


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
