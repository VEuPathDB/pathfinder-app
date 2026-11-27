from __future__ import annotations

from veupathdb.domain.parameters import StringValue
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk import WDKSearchResponse, phyletic_tree_of

from strategist.domain.strategy.phyletic_genomes import included_genomes


def test_the_included_codes_read_as_the_genomes_the_recorded_tree_names() -> None:
    recorded = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_ortholog_pattern").json_body()
    )
    tree = phyletic_tree_of(recorded.search_data.parameters or [])

    genomes = included_genomes(tree, {"included_species": StringValue(value="pviv")})

    assert genomes == ["Plasmodium vivax Sal-1"]
