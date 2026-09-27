"""Strategy plan validation helpers."""

from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import StrategyAst
from veupathdb.errors import ValidationError

from pathfinder.domain.strategy.validate import validate_strategy
from pathfinder.services.strategies.organism_params import tree_organism_parameters


async def validate_plan_or_raise(plan: JSONObject, *, site_id: str) -> StrategyAst:
    """Parse and validate a strategy plan, raising typed ValidationError."""
    try:
        payload = StrategyAst.model_validate(plan)
    except Exception as exc:
        raise ValidationError(
            title="Invalid strategy",
            errors=[
                {"path": "", "message": str(exc), "code": "INVALID_STRATEGY"},
            ],
        ) from exc

    marks = await tree_organism_parameters(site_id, payload.record_type, payload.root)
    validation = validate_strategy(payload.root, payload.record_type, marks)
    if not validation.valid:
        raise ValidationError(
            title="Invalid strategy",
            errors=[
                {"path": err.path, "message": err.message, "code": err.code}
                for err in validation.errors
            ],
        )

    return payload
