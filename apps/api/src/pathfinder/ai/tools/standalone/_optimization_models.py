"""Optimization tool response models and helpers."""

from __future__ import annotations

from assistant_core.platform.logging import get_logger
from assistant_core.platform.types import JSONObject
from pydantic import BaseModel, ConfigDict, Field
from veupathdb.domain.parameters.values import ParamValue
from veupathdb.errors import VEuPathDBError

from pathfinder.platform.errors import AppError
from pathfinder.services.export import get_export_service
from pathfinder.services.parameter_optimization.config import ParameterSpec

logger = get_logger(__name__)


class OptimizationTarget(BaseModel):
    """Target search to optimize."""

    model_config = ConfigDict()

    site_id: str = ""
    record_type: str = "transcript"
    search_name: str
    fixed_parameters: dict[str, ParamValue] = Field(default_factory=dict)
    parameter_space: list[dict[str, object]] = Field(default_factory=list)


class OptimizationControls(BaseModel):
    """Control sets for scoring optimization trials."""

    model_config = ConfigDict()

    positive_controls: list[str] = Field(default_factory=list)
    negative_controls: list[str] = Field(default_factory=list)
    controls_search_name: str = "GeneByLocusTag"
    controls_param_name: str = "ds_gene_ids"
    controls_value_format: str = "newline"
    controls_extra_parameters: dict[str, ParamValue] = Field(default_factory=dict)
    id_field: str = "primary_key"


class OptimizationSettings(BaseModel):
    """Hyperparameters for optimization."""

    budget: int = 30
    objective: str = "f1"
    beta: float = 1.0
    method: str = "bayesian"
    estimated_size_penalty: float = 0.0
    max_parallel: int | None = None
    """Maximum number of variants to evaluate concurrently in the parallel
    sweep. ``None`` falls back to the impl default (5). Bounded so a large
    parameter grid does not stampede WDK."""
    criterion: str = ""
    """Free-text user goal from the launcher form (e.g. 'find params that
    give 50-200 results', 'maximize overlap with my known positives').
    The structured scorer (objective / beta / controls) is the source of
    truth for trial scoring; ``criterion`` is captured for audit, surfaced
    in progress messages, and reachable from the result for v2 when we
    add criterion-aware scoring."""
    model_id: str = ""
    """Resolved catalog model id from the launcher's model picker. Empty
    string means the impl uses its own default. Persisted on the result
    so the user can see which model produced a given sweep."""


def _parse_and_validate_inputs(
    target: OptimizationTarget,
    controls: OptimizationControls,
) -> tuple[list[ParameterSpec], dict[str, ParamValue], dict[str, ParamValue]]:
    """Parse and validate optimization inputs, returning specs and fixed params."""
    specs = [ParameterSpec.model_validate(raw) for raw in target.parameter_space]
    if not specs:
        msg = "parameter_space must contain at least one parameter specification."
        raise ValueError(msg)
    fixed_parameters = dict(target.fixed_parameters)
    controls_extra = dict(controls.controls_extra_parameters)
    return specs, fixed_parameters, controls_extra


async def _attach_export(result_json: JSONObject, search_name: str) -> None:
    """Attach export download links to an optimization result."""
    try:
        svc = get_export_service()
        export = await svc.export_json(result_json, f"{search_name}_optimization")
        result_json["downloads"] = {
            "jsonUrl": export.url,
            "expiresInSeconds": export.expires_in_seconds,
        }
    except (AppError, VEuPathDBError, OSError) as e:
        logger.warning("Optimization export failed", error=str(e))
