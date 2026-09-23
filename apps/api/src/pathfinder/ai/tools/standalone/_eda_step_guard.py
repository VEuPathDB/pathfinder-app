"""The checks an export clears before it becomes a strategy step."""

from __future__ import annotations

from pydantic_ai.exceptions import ModelRetry
from veupathdb.domain import find_gene_entity
from veupathdb.eda import EdaAnalysisDetail

from pathfinder.domain.eda_parts import EdaComparison
from pathfinder.services.eda.authoring import verified_count
from pathfinder.services.eda.catalog import get_study_detail_for_dataset
from pathfinder.services.eda.compute import VolcanoThresholds, analysis_comparison
from pathfinder.services.eda.direction import (
    caption_verdict,
    direction_sentence,
    sign_sentence,
)


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


def _groups(comparison: EdaComparison) -> str:
    return (
        f"group A ({', '.join(comparison.group_a)}) and group B "
        f"({', '.join(comparison.group_b)})"
    )


def compared_groups(
    analysis: EdaAnalysisDetail,
    thresholds: VolcanoThresholds | None,
    caption: str,
) -> EdaComparison | None:
    """The groups a compute export compares, once its caption agrees with them.

    A one-sided export needs a caption whose first group label is a label of
    the kept group. The subset export compares no groups.
    """
    if thresholds is None:
        return None
    comparison = analysis_comparison(analysis)
    direction = thresholds.effect_direction
    kept = direction_sentence(comparison, direction)
    if direction != "upAndDown" and not caption:
        msg = (
            f'effect_direction="{direction}" needs a caption that names the kept '
            f"group's label first. The compute compares {_groups(comparison)}. "
            f"{sign_sentence(comparison)} This call keeps: {kept}. Nothing was "
            f"written."
        )
        raise ModelRetry(msg)
    verdict = caption_verdict(caption, comparison, direction)
    if verdict == "agrees":
        return comparison
    if verdict == "names_no_group":
        msg = (
            f'The caption "{caption}" names no label of either group: '
            f"{_groups(comparison)}. Write a caption that names the kept "
            f"group's label first. This call keeps: {kept}. Nothing was written."
        )
        raise ModelRetry(msg)
    other = "downOnly" if direction == "upOnly" else "upOnly"
    msg = (
        f'The caption "{caption}" does not agree with '
        f'effect_direction="{direction}", which keeps: {kept}. '
        f"{sign_sentence(comparison)} Nothing was written. Name the kept "
        f"group's label first in the caption, or send "
        f'effect_direction="{other}" to keep the other side.'
    )
    raise ModelRetry(msg)
