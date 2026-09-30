"""create_eda_step binds a fold the researcher wrote at its log2 when the
compute names its effect size on the log2 scale, so loosening a 2-fold cut to
1.5-fold keeps more genes and never fewer."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb.eda import EdaVolcanoConfiguration, VolcanoStatsResponse

from pathfinder.ai.tools.standalone import eda_step
from pathfinder.domain.strategy.analysis_binding import AnalysisKind
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.services.eda.compute import retained_summary
from pathfinder.services.eda.export import exported_analysis
from pathfinder.tests._support.eda_step_doubles import (
    DE_GENES,
    de_analysis,
    de_study,
    gene_filter,
    pushing_commit,
    sample_filter,
    wire_analysis,
    wire_gene_count,
)
from pathfinder.tests._support.eda_wire import fixture
from pathfinder.tests._support.run_context import lead_run_context
from pathfinder.tests._support.tool_returns import returned

_LOG2 = "log2(Fold Change)"
_CAPTION = "Genes higher in normal than in febrile"


def _analysis(label: str) -> Any:
    return de_analysis(
        filters=[sample_filter(), gene_filter()],
        with_computation=True,
        volcano=EdaVolcanoConfiguration(
            effect_size_threshold=1.0,
            significance_threshold=0.05,
            effect_direction="upOnly",
            effect_size_label=label,
        ),
    )


async def _exported_cut(
    monkeypatch: pytest.MonkeyPatch, said: str, threshold: float, label: str = _LOG2
) -> tuple[float | None, float | None, str]:
    session = StrategySession(site_id="plasmodb")
    session.add_graph(StrategyGraph("g1", "Test", "plasmodb"))
    applied: list[Any] = []
    wire_analysis(monkeypatch, eda_step, _analysis(label))
    wire_gene_count(monkeypatch, study=de_study, genes=DE_GENES)
    monkeypatch.setattr(
        eda_step,
        "apply_operations_and_commit",
        pushing_commit(applied, session=session, count=50),
    )
    ctx = lead_run_context(user_prompt=said, strategy_session=session)

    answer = await eda_step.create_eda_step(
        ctx,
        effect_size_threshold=threshold,
        significance_threshold=0.05,
        effect_direction="upOnly",
        caption=_CAPTION,
    )

    created = returned(answer, eda_step.EdaStepCreated)
    written = exported_analysis(AnalysisKind.COMPUTE, applied[0][0].step.parameters)
    assert written is not None
    return (
        written.effect_size_threshold,
        created.effect_size_threshold,
        created.guidance,
    )


async def test_a_fold_the_researcher_wrote_is_written_at_its_log2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written, reported, guidance = await _exported_cut(
        monkeypatch, "loosen the fold change to 1.5-fold", 1.5
    )

    assert (written, reported) == (0.585, 0.585)
    assert "'1.5-fold' is 0.585 on the log2(Fold Change) scale" in guidance


async def test_a_loosen_in_other_words_is_written_at_its_log2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written, _, _ = await _exported_cut(
        monkeypatch, "please loosen it to 1.5-fold", 1.5
    )

    assert written == 0.585


async def test_a_log2_number_the_researcher_wrote_is_written_as_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written, _, guidance = await _exported_cut(
        monkeypatch, "use a log2 fold change of 1.5", 1.5
    )

    assert (written, "log2(Fold Change) scale" in guidance) == (1.5, False)


async def test_a_compute_that_names_no_scale_takes_the_number_as_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written, _, _ = await _exported_cut(
        monkeypatch, "loosen the fold change to 1.5-fold", 1.5, label=""
    )

    assert written == 1.5


def test_the_loosened_cut_keeps_more_of_the_recorded_volcano() -> None:
    """On the recorded volcano the up side keeps 33 genes at log2 1, 50 at the
    1.5-fold cut (log2 0.585), and 23 at log2 1.5."""
    statistics = VolcanoStatsResponse.model_validate(fixture("volcano_statistics"))

    kept = [
        retained_summary(
            statistics, effect_size_threshold=cut, significance_threshold=0.05
        ).retained_up
        for cut in (1.0, 0.585, 1.5)
    ]

    assert (statistics.effect_size_label, kept) == (_LOG2, [33, 50, 23])
