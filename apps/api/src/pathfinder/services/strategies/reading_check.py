"""The site's check of a value a reading offers: the validation and the
expression check a bound value passes, under the budget a count read has."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from veupathdb import get_logger
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import to_wire
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb_mcp.catalog import make_validation_callbacks, validate_parameters

from pathfinder.domain.strategy.card_answers import option_value
from pathfinder.domain.strategy.expression_handles import resolved_params, site_values
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.services.strategies.measurements import MEASUREMENT_BUDGET_SECONDS

logger = get_logger(__name__)

CHECK_BUDGET_SECONDS = MEASUREMENT_BUDGET_SECONDS


async def site_spelling(
    site_id: str,
    record_type: str,
    criterion: Criterion,
    param: str,
    wire: str,
    expressions: Mapping[str, str],
) -> str | None:
    sent = resolved_params({param: wire}, expressions)[param]
    parameters = site_values(
        {**criterion.param_values, param: option_value(criterion, param, sent)}
    )
    try:
        async with asyncio.timeout(CHECK_BUDGET_SECONDS):
            validated = await validate_parameters(
                SearchContext(site_id, record_type, criterion.search_name),
                parameters=parameters,
                callbacks=make_validation_callbacks(site_id),
            )
    except ValidationError:
        raise
    except (VEuPathDBError, TimeoutError) as unanswered:
        logger.warning("Reading check did not answer", error=str(unanswered))
        return None
    spelled = to_wire(validated.params[param])
    return wire if spelled == sent else spelled
