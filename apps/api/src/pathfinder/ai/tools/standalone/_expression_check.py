from __future__ import annotations

from veupathdb.domain.parameters import PHYLETIC_EXPRESSION_PARAM, PhyleticExpression
from veupathdb.errors import ValidationError
from veupathdb.wdk import get_strategy_api
from veupathdb_mcp.catalog import ortho_taxonomy
from veupathdb_mcp.wdk import GROUP_GENOME_TABLE, group_genome_counts

from pathfinder.domain.expression_fit import (
    SAMPLED_GROUP_LIMIT,
    ExpressionFit,
    expression_fit,
)
from pathfinder.domain.strategy.operational_spec import Criterion


async def read_expression_fit(
    site_id: str, wdk_step_id: int, criterion: Criterion
) -> ExpressionFit | None:
    bound = criterion.param_values.get(PHYLETIC_EXPRESSION_PARAM)
    if bound is None:
        return None
    try:
        expression = PhyleticExpression.parse(bound.to_wire())
    except ValidationError:
        return None
    tree = await ortho_taxonomy(site_id)
    if tree is None or any(unit.repeated(tree) for unit in expression.units()):
        return None
    answer = await get_strategy_api(site_id).get_step_records(
        wdk_step_id,
        tables=[GROUP_GENOME_TABLE],
        pagination={"offset": 0, "numRecords": SAMPLED_GROUP_LIMIT},
    )
    groups = {g.group: g.proteins for g in group_genome_counts(answer.records)}
    return expression_fit(wdk_step_id, expression, groups, tree)


__all__ = ["read_expression_fit"]
