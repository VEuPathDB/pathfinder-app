"""A scored comparison reports one line per failure and always answers
membership.

The user asks which variant recovers named genes. That question has an answer
even when scoring does not, so every variant carries the given ids it contains,
and a failure is one sentence rather than a validation dump.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError as PydanticValidationError
from veupathdb.wdk.wdk_models import (
    WDKAnswer,
    WDKAnswerMeta,
    WDKRecordInstance,
    WDKSearchConfig,
)

from pathfinder.services.experiment import scored_comparison
from pathfinder.services.experiment.metrics import (
    compute_confusion_matrix,
    compute_metrics,
)
from pathfinder.services.experiment.scored_comparison import run_scored_comparison
from pathfinder.services.experiment.types.experiment import (
    Experiment,
    ExperimentConfig,
)
from pathfinder.services.experiment.types.metrics import GeneInfo
from pathfinder.services.experiment.variant_comparison import VariantSpec

_POSITIVES = ["PF3D7_1116700", "PF3D7_0507500", "PF3D7_1245900"]


def _variants() -> list[VariantSpec]:
    return [
        VariantSpec(label="top 20%", search_name="SA", parameters={}),
        VariantSpec(label="top 5%", search_name="SB", parameters={}),
    ]


def _config(name: str) -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name=name,
        parameters={},
        positive_controls=_POSITIVES,
        negative_controls=[],
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
    )


def _completed(name: str, found: list[str]) -> Experiment:
    cm = compute_confusion_matrix(
        positive_hits=len(found),
        total_positives=len(_POSITIVES),
        negative_hits=0,
        total_negatives=0,
    )
    return Experiment(
        id=f"exp_{name}",
        config=_config(name),
        status="completed",
        metrics=compute_metrics(cm),
        truePositiveGenes=[GeneInfo(id=gene) for gene in found],
    )


def _wdk_validation_error() -> PydanticValidationError:
    """The failure the single-mode branch used to raise at persist time."""
    try:
        WDKSearchConfig.model_validate(
            {"parameters": {"channel": {"type": "single-pick-vocabulary"}}}
        )
    except PydanticValidationError as exc:
        return exc
    msg = "WDKSearchConfig accepted a typed value"
    raise AssertionError(msg)


def _answer(ids: list[str]) -> WDKAnswer:
    return WDKAnswer(
        meta=WDKAnswerMeta(totalCount=len(ids), displayTotalCount=len(ids)),
        records=[
            WDKRecordInstance(id=[{"name": "source_id", "value": gene}]) for gene in ids
        ],
    )


class TestAFailedVariantReportsOneLine:
    @pytest.mark.asyncio
    async def test_the_pydantic_dump_is_not_the_variants_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
            if config.search_name == "SB":
                raise _wdk_validation_error()
            return _completed("SA", _POSITIVES[:2])

        async def _search(site_id: str, spec: VariantSpec) -> WDKAnswer:
            del site_id, spec
            return _answer(_POSITIVES[:1])

        monkeypatch.setattr(scored_comparison, "run_experiment", _run)
        monkeypatch.setattr(scored_comparison, "run_variant_search", _search)

        result = await run_scored_comparison(
            "plasmodb",
            "u1",
            _variants(),
            positive_controls=_POSITIVES,
            negative_controls=[],
        )

        failed = next(v for v in result.variants if v.label == "top 5%")
        assert failed.error == "parameters.channel: Input should be a valid string"
        assert "pydantic.dev" not in failed.error
        assert "\n" not in failed.error

    @pytest.mark.asyncio
    async def test_the_failed_variant_still_answers_membership(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
            if config.search_name == "SB":
                raise _wdk_validation_error()
            return _completed("SA", _POSITIVES[:2])

        async def _search(site_id: str, spec: VariantSpec) -> WDKAnswer:
            del site_id, spec
            return _answer([_POSITIVES[0], "PF3D7_9999900"])

        monkeypatch.setattr(scored_comparison, "run_experiment", _run)
        monkeypatch.setattr(scored_comparison, "run_variant_search", _search)

        result = await run_scored_comparison(
            "plasmodb",
            "u1",
            _variants(),
            positive_controls=_POSITIVES,
            negative_controls=[],
        )

        by_label = {v.label: v for v in result.variants}
        assert by_label["top 5%"].control_hits == [_POSITIVES[0]]
        assert by_label["top 20%"].control_hits == _POSITIVES[:2]


class TestTheSummaryNamesTheFailure:
    @pytest.mark.asyncio
    async def test_a_variant_with_no_metrics_reports_its_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def _run(config: ExperimentConfig, **_kw: Any) -> Experiment:
            return Experiment(
                id="exp_err",
                config=_config(config.search_name),
                status="error",
                error="the site refused the step",
            )

        monkeypatch.setattr(scored_comparison, "run_experiment", _run)

        result = await run_scored_comparison(
            "plasmodb",
            "u1",
            _variants(),
            positive_controls=_POSITIVES,
            negative_controls=[],
        )

        assert result.winner_label is None
        assert [v.error for v in result.variants] == [
            "the site refused the step",
            "the site refused the step",
        ]
        assert [v.control_hits for v in result.variants] == [[], []]
