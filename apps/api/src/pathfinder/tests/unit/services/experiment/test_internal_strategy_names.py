"""The names this application writes on the helper strategies WDK keeps."""

from __future__ import annotations

from uuid import uuid4

import pytest
from veupathdb.wdk.wdk_models import WDKStrategySummary
from veupathdb_mcp.controls.control_types import IntersectionConfig
from veupathdb_mcp.wdk.enrichment.types import EnrichmentResult

from pathfinder.platform.identity import (
    CONTROL_TEST_STRATEGY_NAME,
    ENRICHMENT_STRATEGY_NAME,
)
from pathfinder.services.experiment import sweep_service
from pathfinder.services.experiment.helpers import intersection_config_from_config
from pathfinder.services.experiment.types import ExperimentConfig
from pathfinder.services.gene_sets import enrichment
from pathfinder.services.gene_sets.types import GeneSet


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByText",
        parameters={},
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
        positive_controls=["PF3D7_0100100"],
        negative_controls=["PF3D7_0200200"],
    )


def test_a_control_run_names_the_strategy_it_writes() -> None:
    config = intersection_config_from_config(_config())
    assert config.internal_strategy_name == CONTROL_TEST_STRATEGY_NAME


async def test_the_pre_sweep_cleanup_matches_the_name_the_sweep_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One config, so a match can never drift from a write."""
    matched: list[str] = []
    listed = [
        WDKStrategySummary(
            strategyId=771,
            name=f"__pathfinder_internal__:{CONTROL_TEST_STRATEGY_NAME} 1",
            rootStepId=8801,
        )
    ]

    class _Api:
        async def list_strategies(self) -> list[WDKStrategySummary]:
            return listed

    async def _cleanup(
        api: object,
        wdk_items: list[WDKStrategySummary],
        config: IntersectionConfig,
    ) -> None:
        del api, wdk_items
        matched.append(config.internal_strategy_name)

    monkeypatch.setattr(sweep_service, "get_strategy_api", lambda _site: _Api())
    monkeypatch.setattr(
        sweep_service, "cleanup_internal_control_test_strategies", _cleanup
    )

    await sweep_service.cleanup_before_sweep(intersection_config_from_config(_config()))

    assert matched == [CONTROL_TEST_STRATEGY_NAME]


async def test_an_enrichment_run_names_the_strategy_it_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    class _Service:
        def __init__(self, *, strategy_name: str) -> None:
            seen.append(strategy_name)

        async def run_batch(
            self, **_kwargs: object
        ) -> tuple[list[EnrichmentResult], list[str]]:
            return [], []

    monkeypatch.setattr(enrichment, "EnrichmentService", _Service)

    gene_set = GeneSet(
        id="gs-1",
        user_id=uuid4(),
        name="Gametocyte markers",
        site_id="plasmodb",
        record_type="transcript",
        gene_ids=["PF3D7_0100100"],
        source="manual",
    )
    summary = await enrichment.run_enrichment_for_gene_set(gene_set, ["go_process"])

    assert seen == [ENRICHMENT_STRATEGY_NAME]
    assert summary["analysisTypesRun"] == []
