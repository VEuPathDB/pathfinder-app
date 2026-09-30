"""The site's user-dataset searches on the registered account's own uploads.

The account holds `pathfinder-uat-genelist`, `pathfinder-uat-deseq` and
`pathfinder-uat-phenotype` on plasmodb and vectorbase (docs/knowledge/uat/
sites-and-accounts.md). The counts table holds 200 genes, 40 of them raised in
the treated samples and none lowered.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, Awaitable, Callable

import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaComparator,
    EdaComputation,
    EdaDifferentialExpressionConfig,
    EdaDifferentialExpressionDescriptor,
    EdaLabeledRange,
    EdaNewAnalysis,
    EdaNumberRangeFilter,
    EdaSubsetDescriptor,
    EdaVariableSpec,
    EdaVisualization,
    EdaVolcanoConfiguration,
    EdaVolcanoDescriptor,
)
from veupathdb.wdk import NewStepSpec, WDKSearchConfig, WDKStepTree, get_strategy_api
from veupathdb_mcp.catalog import COMPUTE_QUERY, SUBSET_QUERY

from pathfinder.services.eda.authoring import serialize_spec
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.compute import VolcanoThresholds
from pathfinder.services.eda.description import describe_study, permission_facts
from pathfinder.services.strategies.user_dataset_searches import (
    UserDatasetOffer,
    user_dataset_export_search,
    user_dataset_offers,
)

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITES = ["plasmodb", "vectorbase"]
_DEFAULT_CUT = VolcanoThresholds(effect_size_threshold=1.0, significance_threshold=0.05)
_STATED_CUT = VolcanoThresholds(
    effect_size_threshold=5.0, significance_threshold=1e-10, effect_direction="upOnly"
)
# Measured on build 71: 39 of the 40 raised genes pass 2-fold and p 0.05.
_AT_THE_DEFAULT_CUT = 39
_AT_THE_STATED_CUT = 16
_LOW_FITNESS = {"plasmodb": 32, "vectorbase": 35}

Count = Callable[[str, str, dict[str, str]], Awaitable[int]]


@pytest.fixture
async def count(require_wdk_creds: str) -> AsyncGenerator[Count]:
    """Count one step as the registered account, and delete what it made."""
    reset = veupathdb_auth_token_ctx.set(require_wdk_creds)
    made: list[tuple[str, int]] = []

    async def counted(site: str, search_name: str, parameters: dict[str, str]) -> int:
        api = get_strategy_api(site)
        step = await api.create_step(
            NewStepSpec(
                search_name=search_name,
                search_config=WDKSearchConfig(parameters=parameters),
            ),
            record_type="transcript",
        )
        strategy = await api.create_strategy(
            WDKStepTree(step_id=step.id),
            name="pathfinder-live-user-datasets",
            is_internal=True,
        )
        made.append((site, strategy.id))
        return await api.get_step_count(step.id)

    try:
        yield counted
    finally:
        for site, strategy_id in made:
            with contextlib.suppress(Exception):
                await get_strategy_api(site).delete_strategy(strategy_id)
        veupathdb_auth_token_ctx.reset(reset)


async def _offer(site: str, search_name: str, upload_name: str) -> UserDatasetOffer:
    offers = await user_dataset_offers(site, search_name)
    named = [o for o in offers if o.upload_name == upload_name]
    assert named, (
        f"The registered account holds no installed {upload_name!r} on {site}; "
        f"upload it as docs/knowledge/uat/sites-and-accounts.md says."
    )
    return named[0]


async def _comparison(site: str, dataset_id: str) -> EdaDifferentialExpressionConfig:
    """Treated against control on the upload's counts, as the notebook states it."""
    entry, study = await get_study_detail_for_dataset(site, dataset_id)
    facts = permission_facts(entry)
    counts = next(
        e
        for e in describe_study(facts, study, dataset_id=dataset_id).entities
        if e.has_gene_id
    )
    samples = str(counts.parent_entity_id)
    condition = next(
        v
        for v in describe_study(
            facts, study, dataset_id=dataset_id, entity_id=samples
        ).variables
        if v.display_name == "condition"
    )
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id=counts.entity_id, variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id=counts.entity_id, variable_id="SEQUENCE_READ_COUNT"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(
                entity_id=samples, variable_id=condition.variable_id
            ),
            group_a=[EdaLabeledRange(label="control")],
            group_b=[EdaLabeledRange(label="treated")],
        ),
    )


def _volcano_parameters(
    dataset_id: str, config: EdaDifferentialExpressionConfig, cut: VolcanoThresholds
) -> dict[str, str]:
    """The comparison with one volcano at this cut, as the notebook stores it."""
    volcano = EdaVisualization(
        visualization_id="pathfinder-uat-volcano",
        descriptor=EdaVolcanoDescriptor(
            configuration=EdaVolcanoConfiguration.model_validate(
                {**cut.model_dump(), "effect_size_label": "log2(Fold Change)"}
            )
        ),
    )
    computation = EdaComputation(
        computation_id="pathfinder-uat",
        descriptor=EdaDifferentialExpressionDescriptor(configuration=config),
        visualizations=[volcano],
    )
    analysis = EdaNewAnalysis(
        study_id=dataset_id,
        display_name="pathfinder-uat",
        descriptor=EdaAnalysisDescriptor(computations=[computation]),
    )
    return {"eda_dataset_id": dataset_id, "eda_analysis_spec": serialize_spec(analysis)}


@pytest.mark.parametrize("site", _SITES)
async def test_the_gene_list_search_counts_the_twenty_uploaded_genes(
    site: str, count: Count
) -> None:
    offer = await _offer(site, "GenesByUserDatasetGeneList", "pathfinder-uat-genelist")

    counted = await count(site, offer.search_name, {offer.parameter: offer.value})

    assert counted == 20


@pytest.mark.parametrize("site", _SITES)
async def test_the_deseq_search_counts_fewer_genes_at_the_stated_cut(
    site: str, count: Count
) -> None:
    offer = await _offer(site, "GenesByDESeqUserDataset", "pathfinder-uat-deseq")
    config = await _comparison(site, offer.value)

    at_default = await count(
        site, offer.search_name, _volcano_parameters(offer.value, config, _DEFAULT_CUT)
    )
    at_stated = await count(
        site, offer.search_name, _volcano_parameters(offer.value, config, _STATED_CUT)
    )

    assert (at_default, at_stated) == (_AT_THE_DEFAULT_CUT, _AT_THE_STATED_CUT)


@pytest.mark.parametrize("site", _SITES)
async def test_the_generic_export_counts_the_genes_the_deseq_search_counts(
    site: str, count: Count
) -> None:
    """A zero from the export beside a count from the search is a site fault."""
    offer = await _offer(site, "GenesByDESeqUserDataset", "pathfinder-uat-deseq")
    config = await _comparison(site, offer.value)
    parameters = _volcano_parameters(offer.value, config, _DEFAULT_CUT)

    exported = await count(site, COMPUTE_QUERY, parameters)
    searched = await count(site, offer.search_name, parameters)

    assert (exported, searched) == (_AT_THE_DEFAULT_CUT, _AT_THE_DEFAULT_CUT)
    assert (
        await user_dataset_export_search(site, offer.value, reads_a_volcano=True)
        == offer.search_name
    )


@pytest.mark.parametrize("site", _SITES)
async def test_the_phenotype_search_counts_the_genes_of_the_subset(
    site: str, count: Count
) -> None:
    offer = await _offer(
        site, "GenesByPhenotypeUserDataset", "pathfinder-uat-phenotype"
    )
    entry, study = await get_study_detail_for_dataset(site, offer.value)
    phenotype = describe_study(permission_facts(entry), study, dataset_id=offer.value)
    entity = phenotype.entities[0].entity_id
    score = next(
        v
        for v in describe_study(
            permission_facts(entry), study, dataset_id=offer.value, entity_id=entity
        ).variables
        if v.display_name == "fitness_score"
    )
    analysis = EdaNewAnalysis(
        study_id=offer.value,
        display_name="pathfinder-uat",
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(
                descriptor=[
                    EdaNumberRangeFilter(
                        entity_id=entity,
                        variable_id=score.variable_id,
                        min=-10.0,
                        max=-2.0,
                    )
                ]
            )
        ),
    )
    parameters = {
        "eda_dataset_id": offer.value,
        "eda_analysis_spec": serialize_spec(analysis),
    }

    searched = await count(site, offer.search_name, parameters)
    exported = await count(site, SUBSET_QUERY, parameters)

    assert (searched, exported) == (_LOW_FITNESS[site], _LOW_FITNESS[site])
    assert (
        await user_dataset_export_search(site, offer.value, reads_a_volcano=False)
        == offer.search_name
    )
