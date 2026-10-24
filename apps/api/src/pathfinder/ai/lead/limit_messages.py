from __future__ import annotations

from pathfinder.domain.column_reach import StepReach, TransformReach


def _reached(transform: TransformReach) -> str:
    columns = ", ".join(f"{c.name} ({c.display_name})" for c in transform.columns)
    return (
        f"{transform.search_name} ({transform.display_name}) reaches "
        f"{transform.record_type} records, which count by {columns}"
    )


def unfollowed_reach_message(reach: StepReach) -> str:
    reached = "; ".join(_reached(t) for t in reach.transforms if t.countable)
    return (
        f"step_columns found no countable column on step {reach.wdk_step_id} "
        f"({reach.record_type} records) for this count. {reached}. If one of "
        "these columns answers the question, add the transform with "
        "edit_strategy and count the new step with count_step_by_column, or "
        "offer the transform on a card. If none does, say in the reply which "
        "column the question needs and that none of these is it."
    )


def unmet_requirement_message(requirements: tuple[str, ...]) -> str:
    stated = ", ".join(f"'{text}'" for text in requirements)
    one = len(requirements) == 1
    it, stays = ("it", "stays") if one else ("them", "stay")
    return (
        f"The researcher stated {stated}, and the strategy does not answer {it}, "
        "so the turn is not complete. Set nextState to await_user and say in the "
        f"reply that {stated} {stays} unmet. When a search can state {it}, apply "
        f"{it} with edit_strategy first."
    )


__all__ = ["unfollowed_reach_message", "unmet_requirement_message"]
