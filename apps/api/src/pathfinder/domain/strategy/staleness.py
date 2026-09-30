"""Detect that the counts a thread holds no longer describe the live strategy:
the counts the session's sync state holds, compared with the site's own."""

from dataclasses import dataclass, field

from pathfinder.domain.strategy.build_outcome import BuildOutcome, BuiltCounts

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
                "counts this conversation holds are out of date. Call "
                "get_live_strategy_state "
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
    held: BuiltCounts,
    live_counts: dict[str, int | None],
) -> StaleBuild | None:
    """What differs between the counts the thread holds for its build and the
    site's, or None. A count unknown on either side is no change."""
    if outcome is None or not live_counts:
        return None

    recorded = dict(held.by_step)

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
