from __future__ import annotations

from collections.abc import Container, Mapping
from dataclasses import dataclass, field
from typing import Literal

from veupathdb.model import CamelModel

NodeStatus = Literal["ok", "zero", "failed"]


def citable_count(
    step_id: str,
    *,
    counts: Mapping[str, int | None],
    refused: Container[str],
) -> int | None:
    """The count a step may be cited with, or nothing when there is none.

    A step whose last push did not reach VEuPathDB still runs the search it
    was created with, so the size measured on it answers a search the step no
    longer states.
    """
    if step_id in refused:
        return None
    return counts.get(step_id)


def node_status(*, count: int | None, failed: bool) -> NodeStatus:
    if failed:
        return "failed"
    if count == 0:
        return "zero"
    return "ok"


class NodeResult(CamelModel):
    """Per-node build result surfaced to the Ledger/UI (BUILD's count feedback)."""

    node_id: str
    search_name: str
    wdk_step_id: int | None = None
    count: int | None = None
    status: NodeStatus
    error: str | None = None


# A WDK answer at or above this status is the service failing, not a refusal.
_SERVER_ERROR = 500


@dataclass
class StepPushFailure:
    step_id: str
    search_name: str
    error: str
    wdk_status: int | None = None

    @property
    def wdk_refused_the_values(self) -> bool:
        """WDK read the request and refused it, so other values can pass."""
        return self.wdk_status is not None and self.wdk_status < _SERVER_ERROR


@dataclass
class BuildOutcome:
    """Structured result of a declarative strategy build."""

    pushed_step_ids: list[str] = field(default_factory=list)
    failed_steps: list[StepPushFailure] = field(default_factory=list)
    skipped_step_ids: list[str] = field(default_factory=list)
    wdk_strategy_id: int | None = None
    wdk_url: str | None = None
    counts: dict[str, int | None] = field(default_factory=dict)
    root_count: int | None = None
    zero_step_ids: list[str] = field(default_factory=list)
    node_results: list[NodeResult] = field(default_factory=list)

    @property
    def fully_succeeded(self) -> bool:
        return not self.failed_steps and not self.skipped_step_ids

    @property
    def recorded_step_ids(self) -> frozenset[str]:
        """Every step this build left the strategy holding, whatever minted it."""
        return frozenset(node.node_id for node in self.node_results)
