"""A link to a strategy opens the result list of its root step on its own site."""

from veupathdb.wdk import WDKStepTree

from pathfinder.services.strategies.result_list import (
    live_result_list_url,
    result_list_url,
)
from pathfinder.services.strategies.sync_state import WDKSyncState


def test_a_gene_strategy_opens_the_result_table_of_its_root() -> None:
    assert result_list_url("plasmodb", 214647970, 227289210) == (
        "https://qa.plasmodb.org/plasmo.qa/app/workspace/strategies/"
        "214647970/227289210/summary:_default"
    )


def test_an_orthomcl_strategy_opens_on_orthomcl() -> None:
    assert result_list_url("orthomcl", 1188, 227284080) == (
        "https://qa.orthomcl.org/orthomcl.qa/app/workspace/strategies/"
        "1188/227284080/summary:_default"
    )


def test_a_portal_strategy_opens_on_the_portal() -> None:
    assert result_list_url("veupathdb", 330871000, 441174000) == (
        "https://qa.veupathdb.org/veupathdb.qa/app/workspace/strategies/"
        "330871000/441174000/summary:_default"
    )


def test_a_strategy_with_no_known_root_opens_its_page() -> None:
    assert result_list_url("toxodb", 330528343, None) == (
        "https://qa.toxodb.org/toxo.qa/app/workspace/strategies/330528343"
    )


def test_the_live_link_names_the_root_the_strategy_holds() -> None:
    sync = WDKSyncState(
        wdk_strategy_id=214647970, wdk_step_tree=WDKStepTree(step_id=227289210)
    )

    assert live_result_list_url("plasmodb", sync) == result_list_url(
        "plasmodb", 214647970, 227289210
    )


def test_no_link_before_the_strategy_is_on_the_site() -> None:
    assert (
        live_result_list_url("plasmodb", None),
        live_result_list_url("plasmodb", WDKSyncState()),
    ) == (None, None)
