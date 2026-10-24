from __future__ import annotations

from pathfinder.domain.column_reach import StepReach, TransformReach


def _reached(transform: TransformReach) -> str:
    columns = ", ".join(f"{c.name} ({c.display_name})" for c in transform.columns)
    return (
        f"{transform.search_name} ({transform.display_name}) turns them into "
        f"{transform.record_type} records, which count by {columns}"
    )


def unfollowed_reach_message(reach: StepReach) -> str:
    reached = "; ".join(_reached(t) for t in reach.transforms if t.countable)
    return (
        f"step_columns found no countable column on step {reach.wdk_step_id} "
        f"({reach.record_type} records), and a transform reaches one: {reached}. "
        "Add the transform with edit_strategy and count the new step with "
        "count_step_by_column, or offer the transform on a card. The site does "
        "not lack this count."
    )


def unmet_requirement_message(requirements: tuple[str, ...]) -> str:
    stated = ", ".join(f"'{text}'" for text in requirements)
    it = "it" if len(requirements) == 1 else "them"
    return (
        f"The researcher stated {stated}, and nothing in the strategy answers "
        f"{it}, so the turn is not complete and the strategy does not answer the "
        f"request. Apply {it} with edit_strategy, or say in the reply that the "
        f"strategy leaves {it} unmet and set nextState to await_user."
    )


__all__ = ["unfollowed_reach_message", "unmet_requirement_message"]
