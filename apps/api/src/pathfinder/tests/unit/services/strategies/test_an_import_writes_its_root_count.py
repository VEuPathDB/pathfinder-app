"""An imported WDK strategy stores its root step's count beside its steps."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.services.strategies.wdk_sync import WdkChatSpec, import_write

_WDK_ID = 330679883


def _saved(counts: dict[str, int]) -> WdkChatSpec:
    root = StrategyStepNode(
        id="root",
        search_name="__combine__",
        primary_input=StrategyStepNode(id="sp", search_name="GenesWithSignalPeptide"),
        secondary_input=StrategyStepNode(
            id="tm", search_name="GenesByTransmembraneDomains"
        ),
        operator=CombineOp.INTERSECT,
    )
    ast = StrategyAst(record_type="transcript", root=root, step_counts=counts)
    return WdkChatSpec(
        wdk_id=_WDK_ID,
        name="UAT saved S7",
        strategy_ast=ast,
        record_type="transcript",
        is_saved=True,
        step_count=3,
    )


def test_the_write_carries_the_count_the_site_gave_the_root() -> None:
    write = import_write(_saved({"sp": 479, "tm": 840, "root": 116}), name="S7")

    assert (write.estimated_size, write.estimated_size_set, write.step_count) == (
        116,
        True,
        3,
    )


def test_a_root_the_site_did_not_count_clears_the_stored_count() -> None:
    write = import_write(_saved({"sp": 479, "tm": 840}), name="S7")

    assert (write.estimated_size, write.estimated_size_set) == (None, True)
