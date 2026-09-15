"""The count a subset export clears before it becomes a strategy step."""

from __future__ import annotations

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import find_gene_entity
from veupathdb.eda import EdaAnalysisDetail

from pathfinder.services.eda.authoring import verified_count
from pathfinder.services.eda.catalog import get_study_detail_for_dataset


async def refuse_an_empty_gene_subset(
    site_id: str,
    *,
    dataset_id: str,
    analysis: EdaAnalysisDetail,
) -> None:
    """A subset that selects no genes is not exported, and the refusal says why.

    A study with no gene entity is left to the export, which names that problem.
    """
    _entry, study = await get_study_detail_for_dataset(site_id, dataset_id)
    gene = find_gene_entity(study, subject="strategy step")
    if gene.entity_id is None:
        return
    counted = await verified_count(
        site_id,
        dataset_id=dataset_id,
        entity_id=gene.entity_id,
        filters=analysis.descriptor.subset.descriptor,
    )
    if counted.count:
        return
    msg = (
        f"The subset selects 0 of {counted.unfiltered_count:,} genes, so there is "
        "no step to export; nothing was written. A filter on a sample-level "
        "entity selects samples, not genes. For 'up in A versus B' run "
        "run_eda_compute and export the genes that pass its thresholds; to "
        "subset genes directly, filter a variable that lives on the gene entity."
    )
    raise ModelRetry(msg)
