"""Detect that a recorded build no longer describes the live strategy.

The Lead answers questions from the Ledger, whose counts come from the last
``BuildOutcome``. Edits made outside the conversation — the graph editor, the
WDK web UI — change the strategy without touching that outcome, so cached
counts silently become wrong. Comparing recorded counts against a live read
turns that silence into an explicit warning.
"""

from dataclasses import dataclass, field

from veupathdb.domain.strategy.build_outcome import BuildOutcome

__all__ = ["StaleBuild", "detect_build_staleness"]


@dataclass(frozen=True)
class StaleBuild:
    """What changed between the recorded build and the live strategy."""

    changed_nodes: list[tuple[str, int, int]] = field(default_factory=list)
    added_nodes: list[str] = field(default_factory=list)
    removed_nodes: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            (
                "STALE: the strategy was edited outside this conversation, so the "
                "build counts below are out of date. Call get_live_strategy_state "
                "before quoting any number to the user."
            ),
        ]
        lines.extend(
            f"  - {node_id}: recorded {recorded} -> now {live}"
            for node_id, recorded, live in self.changed_nodes
        )
        lines.extend(
            f"  - {node_id}: added since the build" for node_id in self.added_nodes
        )
        lines.extend(
            f"  - {node_id}: removed since the build" for node_id in self.removed_nodes
        )
        return "\n".join(lines)


def detect_build_staleness(
    outcome: BuildOutcome | None,
    live_counts: dict[str, int | None],
) -> StaleBuild | None:
    """Compare a recorded build against live per-node counts.

    ``None`` counts on either side mean "unknown", never "changed" — a WDK
    read that failed must not masquerade as a user edit. Returns ``None``
    when nothing observable diverged.
    """
    if outcome is None or not live_counts:
        return None

    recorded = {n.node_id: n.count for n in outcome.node_results}

    changed = [
        (node_id, count, live_counts[node_id])
        for node_id, count in recorded.items()
        if count is not None
        and node_id in live_counts
        and live_counts[node_id] is not None
        and live_counts[node_id] != count
    ]
    added = [node_id for node_id in live_counts if node_id not in recorded]
    removed = [node_id for node_id in recorded if node_id not in live_counts]

    if not changed and not added and not removed:
        return None
    return StaleBuild(
        changed_nodes=[(n, r, live) for n, r, live in changed if live is not None],
        added_nodes=added,
        removed_nodes=removed,
    )
