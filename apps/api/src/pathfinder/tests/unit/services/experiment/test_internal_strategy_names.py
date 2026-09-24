"""The names this application writes on the helper strategies WDK keeps."""

from __future__ import annotations

from pathfinder.platform.identity import CONTROL_TEST_STRATEGY_NAME
from pathfinder.services.experiment.helpers import intersection_config_from_config
from pathfinder.services.experiment.types import ExperimentConfig


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
