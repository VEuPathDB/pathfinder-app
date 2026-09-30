"""The cut an export of the open analysis writes, on the scale its compute
names, and the step that cut plans."""

from __future__ import annotations

from typing import NamedTuple

from pydantic_ai.exceptions import ModelRetry
from veupathdb.eda import EdaAnalysisDetail

from pathfinder.ai.tools.standalone._eda_step_guard import volcano_thresholds
from pathfinder.domain.eda_parts import EdaEffectDirection
from pathfinder.domain.eda_thread import ConversationAnalysisView
from pathfinder.domain.log2_scale import in_the_sites_scale, on_scale, scale_of
from pathfinder.services.eda.compute import NoComputationError, VolcanoThresholds
from pathfinder.services.eda.export import read_the_export
from pathfinder.services.eda.gene_subset import (
    NoGeneSubsetError,
    refuse_a_subset_that_selects_no_genes,
)
from pathfinder.services.eda.steps import (
    EdaStepPlan,
    eda_step_node,
    on_the_user_dataset_search,
)


async def _planned_export(
    binding: ConversationAnalysisView,
    analysis: EdaAnalysisDetail,
    *,
    thresholds: VolcanoThresholds | None,
) -> EdaStepPlan:
    """The step the analysis exports, once it is known to hold genes, on the
    site's user-dataset search when the study is the researcher's upload."""
    try:
        if thresholds is None:
            await refuse_a_subset_that_selects_no_genes(
                binding.site_id, dataset_id=binding.dataset_id, analysis=analysis
            )
    except NoGeneSubsetError as exc:
        raise ModelRetry(exc.retry) from exc
    try:
        reading = await read_the_export(
            binding.site_id,
            dataset_id=binding.dataset_id,
            analysis=analysis,
            thresholds=thresholds,
        )
        plan = eda_step_node(
            analysis,
            dataset_id=binding.dataset_id,
            thresholds=thresholds,
            reading=reading,
        )
    except NoComputationError as exc:
        msg = (
            f"{exc} Call run_eda_compute to run the differential expression, "
            f"then export the genes that pass its thresholds."
        )
        raise ModelRetry(msg) from exc
    return await on_the_user_dataset_search(binding.site_id, plan)


class Rescaled(NamedTuple):
    """The cut a number written on the other scale stands for, and the sentence
    that says so."""

    cut: float
    sentence: str


def _on_the_computes_scale(
    label: str, threshold: float | None, said: list[str]
) -> Rescaled | None:
    """The cut a number the researcher wrote on the other scale stands for on
    the scale the compute names its effect size on, or None."""
    site = scale_of(label)
    stated = None if threshold is None else in_the_sites_scale(threshold, label, said)
    if stated is None or site is None:
        return None
    cut = on_scale(stated.number, stated.scale, site)
    return Rescaled(
        cut, f"{stated.words!r} is {cut:g} on the {label} scale, so the cut is {cut:g}."
    )


class VolcanoAsk(NamedTuple):
    """The cut one export call names."""

    effect_size: float | None
    significance: float | None
    direction: EdaEffectDirection | None


async def the_cut(
    binding: ConversationAnalysisView,
    analysis: EdaAnalysisDetail,
    ask: VolcanoAsk,
    said: list[str],
) -> tuple[VolcanoThresholds | None, EdaStepPlan, Rescaled | None]:
    """The cut the export writes, its plan, and the rescaling a number the
    researcher wrote on the other scale took."""
    thresholds = volcano_thresholds(analysis, *ask)
    plan = await _planned_export(binding, analysis, thresholds=thresholds)
    rescaled = _on_the_computes_scale(
        plan.binding.effect_size_label, ask.effect_size, said
    )
    if rescaled is None:
        return thresholds, plan, None
    thresholds = volcano_thresholds(
        analysis, rescaled.cut, ask.significance, ask.direction
    )
    plan = await _planned_export(binding, analysis, thresholds=thresholds)
    return thresholds, plan, rescaled


__all__ = ["Rescaled", "VolcanoAsk", "the_cut"]
