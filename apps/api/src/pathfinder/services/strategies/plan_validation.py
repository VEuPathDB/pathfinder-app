"""Strategy plan validation helpers."""

from assistant_core.platform.types import JSONObject
from veupathdb.domain.strategy import StrategyAst
from veupathdb.errors import ValidationError

from pathfinder.domain.strategy.validate import validate_strategy


def validate_plan_or_raise(plan: JSONObject) -> StrategyAst:
    """Parse and validate a strategy plan, raising typed ValidationError."""
    try:
        payload = StrategyAst.model_validate(plan)
    except Exception as exc:
        raise ValidationError(
            title="Invalid plan",
            errors=[
                {"path": "", "message": str(exc), "code": "INVALID_STRATEGY"},
            ],
        ) from exc

    validation = validate_strategy(payload.root, payload.record_type)
    if not validation.valid:
        raise ValidationError(
            title="Invalid plan",
            errors=[
                {"path": err.path, "message": err.message, "code": err.code}
                for err in validation.errors
            ],
        )

    return payload
