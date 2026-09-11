"""The prefix this deployment tags helper strategies with, end to end."""

from __future__ import annotations

from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.strategy_api import (
    StrategyAPI,
    is_internal_wdk_strategy_name,
    tag_internal_wdk_strategy_name,
)
from veupathdb.wdk.wdk_models import WDKStrategySummary
from veupathdb_mcp.controls import (
    IntersectionConfig,
    cleanup_internal_control_test_strategies,
)

from pathfinder.platform.identity import (
    CONTROL_TEST_STRATEGY_NAME,
    INTERNAL_STRATEGY_NAME_PREFIX,
)


class _RecordingStrategyAPI(StrategyAPI):
    """A strategy API that records the strategies it was asked to delete."""

    def __init__(self) -> None:
        super().__init__(VEuPathDBClient("https://plasmodb.example.org/plasmo"))
        self.deleted: list[int] = []

    async def delete_strategy(
        self, strategy_id: int, user_id: str | None = None
    ) -> None:
        del user_id
        self.deleted.append(strategy_id)


def _config() -> IntersectionConfig:
    return IntersectionConfig(
        site_id="plasmodb",
        record_type="transcript",
        target_search_name="GenesByText",
        target_parameters={},
        controls_search_name="GeneByLocusTag",
        controls_param_name="ds_gene_ids",
        internal_strategy_name=CONTROL_TEST_STRATEGY_NAME,
    )


def test_a_helper_strategy_this_application_writes_carries_its_own_prefix() -> None:
    tagged = tag_internal_wdk_strategy_name(CONTROL_TEST_STRATEGY_NAME)
    assert tagged == f"{INTERNAL_STRATEGY_NAME_PREFIX}{CONTROL_TEST_STRATEGY_NAME}"
    assert is_internal_wdk_strategy_name(tagged)


async def test_the_cleanup_deletes_the_strategy_this_application_tagged() -> None:
    api = _RecordingStrategyAPI()
    tagged = tag_internal_wdk_strategy_name(f"{CONTROL_TEST_STRATEGY_NAME} 12345")
    items = [
        WDKStrategySummary(strategy_id=771, name=tagged, root_step_id=8801),
        WDKStrategySummary(
            strategy_id=772,
            name="Kinases the researcher saved",
            root_step_id=8802,
        ),
    ]

    await cleanup_internal_control_test_strategies(api, items, _config())

    assert api.deleted == [771]
