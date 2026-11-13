"""The prefix this deployment tags helper strategies with, end to end."""

from __future__ import annotations

from veupathdb.wdk import (
    StrategyAPI,
    VEuPathDBClient,
    WDKStrategySummary,
    is_internal_wdk_strategy_name,
    tag_internal_wdk_strategy_name,
)
from veupathdb_mcp.controls import (
    IntersectionConfig,
    cleanup_internal_control_test_strategies,
    leftover_strategy_ids,
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


async def test_the_cleanup_deletes_a_stale_strategy_this_application_tagged() -> None:
    api = _RecordingStrategyAPI()
    tagged = tag_internal_wdk_strategy_name(f"{CONTROL_TEST_STRATEGY_NAME} 12345")
    items = [
        WDKStrategySummary(
            strategy_id=771,
            name=tagged,
            root_step_id=8801,
            created_time="2026-09-01T00:00:00",
        ),
        WDKStrategySummary(
            strategy_id=772,
            name="Kinases the researcher saved",
            root_step_id=8802,
            created_time="2026-09-01T00:00:00",
        ),
    ]

    await cleanup_internal_control_test_strategies(api, items, _config())

    assert api.deleted == [771]


def _summary(strategy_id: int, name: str) -> WDKStrategySummary:
    return WDKStrategySummary(
        strategy_id=strategy_id,
        name=name,
        root_step_id=strategy_id + 1,
        created_time="2026-09-01T00:00:00",
    )


def test_a_helper_names_no_product_beyond_its_prefix() -> None:
    assert tag_internal_wdk_strategy_name(CONTROL_TEST_STRATEGY_NAME) == (
        "__strategist_internal__:control test"
    )


def test_a_helper_left_under_an_earlier_name_is_still_a_leftover() -> None:
    items = [
        _summary(1, "__pathfinder_internal__:Pathfinder control test 12"),
        _summary(2, "__pathfinder_internal__:Strategist control test 34"),
        _summary(3, "__strategist_internal__:control test 56"),
        _summary(4, "__pathfinder_internal__:Pathfinder step counts"),
        _summary(5, "Pathfinder control test the researcher named"),
    ]

    assert leftover_strategy_ids(items, CONTROL_TEST_STRATEGY_NAME) == [1, 2, 3]
