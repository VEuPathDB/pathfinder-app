from dataclasses import dataclass

from veupathdb.domain.parameters import ParamValue
from veupathdb.errors import DataParsingError, ValidationError
from veupathdb.wdk import StrategyAPI, WDKStrategyDetails, get_strategy_api
from veupathdb_mcp.wdk import (
    GeneSetWdkContext,
    build_snapshot_from_wdk,
    canonicalize_synced_parameters,
)

from pathfinder.domain.gene_homes import holds_genes
from pathfinder.services.gene_sets.homes import StepGenes, read_genes_of, site_kind
from pathfinder.services.gene_sets.types import ResultNotGenes


class RecordsAreNotGenesError(ValidationError):
    def __init__(self, record_class: str) -> None:
        super().__init__(
            title="Not a gene result",
            detail=(
                f"The strategy returns {record_class or 'unnamed'} records, which "
                "are not genes, so no gene set takes them."
            ),
        )
        self.record_class = record_class

    def reason(self) -> ResultNotGenes:
        return ResultNotGenes(record_class=self.record_class)


@dataclass(frozen=True)
class StrategyGenes:
    genes: StepGenes
    context: GeneSetWdkContext
    step_count: int


async def read_strategy_genes(
    site_id: str, wdk_strategy_id: int, *, record_type: str | None
) -> StrategyGenes:
    api = get_strategy_api(site_id)
    strategy = await api.get_strategy(wdk_strategy_id)
    record_class = strategy.record_class_name or ""
    if not holds_genes(site_kind(site_id), record_class):
        raise RecordsAreNotGenesError(record_class)
    root = strategy.steps.get(str(strategy.root_step_id))
    if root is None:
        msg = f"Strategy {wdk_strategy_id} does not list its root step"
        raise DataParsingError(msg)
    genes = await read_genes_of(site_id, root)
    search_name, parameters = await _single_search(api, strategy)
    return StrategyGenes(
        genes=genes,
        context=GeneSetWdkContext(
            wdk_strategy_id=wdk_strategy_id,
            wdk_step_id=strategy.root_step_id,
            search_name=search_name,
            record_type=record_type or record_class,
            parameters=parameters,
        ),
        step_count=len(strategy.steps),
    )


async def _single_search(
    api: StrategyAPI, strategy: WDKStrategyDetails
) -> tuple[str | None, dict[str, ParamValue] | None]:
    if len(strategy.steps) != 1:
        return None, None
    ast, wire = build_snapshot_from_wdk(strategy)
    await canonicalize_synced_parameters(ast, api, wire)
    return ast.root.search_name, ast.root.parameters
