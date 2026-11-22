"""The site's check of a value a reading offers: the validation and the
expression check a bound value passes, under the budget a count read has."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping

from veupathdb import get_logger
from veupathdb.domain import SearchContext
from veupathdb.domain.parameters import HeldValue, to_wire
from veupathdb.errors import ValidationError, VEuPathDBError
from veupathdb_mcp.catalog import make_validation_callbacks, validate_parameters

from strategist.domain.strategy.card_answers import option_value
from strategist.domain.strategy.expression_handles import resolved_params, site_values
from strategist.domain.strategy.operational_spec import Criterion
from strategist.services.strategies.measurements import MEASUREMENT_BUDGET_SECONDS

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
    held = site_values(criterion.param_values)
    stated = {param: option_value(criterion, param, sent)}
    try:
        async with asyncio.timeout(CHECK_BUDGET_SECONDS):
            validated = await validate_parameters(
                SearchContext(site_id, record_type, criterion.search_name),
                stated=stated,
                context=held,
                callbacks=make_validation_callbacks(site_id),
                about=None,
            )
    except ValidationError:
        raise
    except (VEuPathDBError, TimeoutError) as unanswered:
        logger.warning("Reading check did not answer", error=str(unanswered))
        return None
    read = validated.params[param]
    return wire if read == HeldValue(wire=sent) else to_wire(read)
