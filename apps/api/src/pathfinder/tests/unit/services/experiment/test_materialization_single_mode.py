"""Single-mode materialization encodes typed parameter values for the wire.

``ExperimentConfig.parameters`` holds ``ParamValue``s and
``WDKSearchConfig.parameters`` holds strings, so the step this branch creates
goes through the same encoder the tree branch uses.
"""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.wdk import (
    NewStepSpec,
    WDKIdentifier,
    WDKStepTree,
)

from pathfinder.services.experiment import materialization
from pathfinder.services.experiment.materialization import (
    _persist_experiment_strategy,
)
from pathfinder.services.experiment.types.experiment import ExperimentConfig


def _su_parameters() -> dict[str, ParamValue]:
    """The Su-et-al step's typed values, as the variant tools build them."""
    return {
        "channel": SinglePickValue(value="Channel 1"),
        "any_or_all": SinglePickValue(value="all"),
        "profileset": MultiPickValue(values=["Su gametocyte"]),
        "min_max_avg_ref": SinglePickValue(value="avg"),
        "percentile_gte": StringValue(value="80"),
        "percentile_lte": StringValue(value="100"),
        "samples_ref": MultiPickValue(values=["stage V"]),
    }


class _RecordingAPI:
    """Records the step spec instead of reaching WDK."""

    def __init__(self) -> None:
        self.specs: list[NewStepSpec] = []

    async def create_step(
        self, spec: NewStepSpec, record_type: str, user_id: str | None = None
    ) -> WDKIdentifier:
        del record_type, user_id
        self.specs.append(spec)
        return WDKIdentifier(id=901)

    async def create_strategy(
        self,
        step_tree: WDKStepTree,
        name: str,
        description: str | None = None,
        *,
        is_public: bool = False,
        is_saved: bool = False,
        is_internal: bool = False,
    ) -> WDKIdentifier:
        del step_tree, name, description, is_public, is_saved, is_internal
        return WDKIdentifier(id=902)


def _config() -> ExperimentConfig:
    return ExperimentConfig(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByRNASeqSu",
        parameters=_su_parameters(),
        positive_controls=["PF3D7_1116700"],
        negative_controls=[],
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
        name="top 20%",
    )


class TestASingleModeStepCarriesEncodedValues:
    @pytest.mark.asyncio
    async def test_the_step_is_created_with_wire_strings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _RecordingAPI()
        monkeypatch.setattr(materialization, "get_strategy_api", lambda site_id: api)

        ids = await _persist_experiment_strategy(_config(), "exp_abc")

        assert ids == {"strategy_id": 902, "step_id": 901}
        [spec] = api.specs
        assert spec.search_config.parameters == {
            "channel": "Channel 1",
            "any_or_all": "all",
            "profileset": '["Su gametocyte"]',
            "min_max_avg_ref": "avg",
            "percentile_gte": "80",
            "percentile_lte": "100",
            "samples_ref": '["stage V"]',
        }

    @pytest.mark.asyncio
    async def test_every_value_reaches_the_wire_as_a_string(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        api = _RecordingAPI()
        monkeypatch.setattr(materialization, "get_strategy_api", lambda site_id: api)

        await _persist_experiment_strategy(_config(), "exp_abc")

        [spec] = api.specs
        assert all(
            isinstance(value, str) for value in spec.search_config.parameters.values()
        )
