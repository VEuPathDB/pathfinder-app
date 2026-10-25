from __future__ import annotations

from collections.abc import Mapping, Sequence

from assistant_core.graph.tool_summary import count_noun

from pathfinder.domain.strategy.computed_groups import HeldComparison
from pathfinder.domain.strategy.question_options import (
    SaveComputedGroups,
    TypedOption,
)
from pathfinder.domain.strategy.questions import OpenQuestion


def save_question(held: HeldComparison) -> OpenQuestion:
    return OpenQuestion(
        question=f"Save these {count_noun(held.answer.groups, 'group')} as a step?",
        options=[
            TypedOption(
                id="save-as-a-step",
                label="Save them as a step",
                binding=SaveComputedGroups(handle=held.handle, save=True),
            ),
            TypedOption(
                id="keep-the-counts-only",
                label="Keep the counts only",
                binding=SaveComputedGroups(handle=held.handle, save=False),
            ),
        ],
    )


def with_save_offers(
    questions: Sequence[OpenQuestion], held: Mapping[str, HeldComparison]
) -> list[OpenQuestion]:
    offered = [save_question(one) for one in held.values() if one.dataset_id is None]
    return [*questions, *(q for q in offered if q not in questions)]


__all__ = ["save_question", "with_save_offers"]
