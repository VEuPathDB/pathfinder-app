"""The user-dataset arc: DESeq2 on the researcher's own counts upload, exported
at the cut the message states. The export runs the site's user-dataset search.

The study is the card the message names, the researcher's upload; the groups
are the sample variable with two values, and the caption names the kept group.
"""

from __future__ import annotations

from assistant_core.models.scripted import scripted_call
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import lead_final
from pathfinder.ai.models.mock.eda_arc import (
    applied_filter,
    comparison,
    group_variables,
)
from pathfinder.ai.models.mock.lead_flow import FACTS_BESIDE
from pathfinder.ai.models.mock.reads import text_return
from pathfinder.domain.eda_parts import (
    EdaComparison,
    EdaEffectDirection,
    EdaFilterSheetEntry,
)
from pathfinder.services.eda.direction import direction_sentence

# The cut the arc's message states: log2 fold change above 5, p below 1e-10, up only.
_DIRECTION: EdaEffectDirection = "upOnly"
STATED_CUT = {
    "effect_size_threshold": 5.0,
    "significance_threshold": 1e-10,
    "effect_direction": _DIRECTION,
}
_PAIR = 2
_EXPORTED_PROSE = (
    "I compared the two groups of your upload and added the genes past your cut "
    "as a step."
)


def _two_groups(
    messages: list[ModelMessage], samples: list[str]
) -> EdaFilterSheetEntry | None:
    """The sample variable with exactly two values, which names the two conditions."""
    return next(
        (e for e in group_variables(messages, samples) if len(e.vocabulary) == _PAIR),
        None,
    )


def _caption(messages: list[ModelMessage]) -> str:
    """The genes the stated direction keeps, named by the compared groups."""
    chosen = applied_filter(messages)
    labels = [] if chosen is None else chosen.string_set
    compared = EdaComparison(group_a=labels[:1], group_b=labels[1:2])
    return direction_sentence(compared, _DIRECTION)


def _exported_at_the_stated_cut(messages: list[ModelMessage]) -> ToolCallPart:
    if text_return(messages, "create_eda_step") is None:
        return scripted_call(
            "create_eda_step", {**STATED_CUT, "caption": _caption(messages)}
        )
    if text_return(messages, "verify_strategy") is None:
        return scripted_call("verify_strategy", {"reason": "check the exported step"})
    return lead_final(
        f"{_EXPORTED_PROSE}{FACTS_BESIDE}", "complete", strategy_changed=True
    )


user_dataset_deseq = comparison(_exported_at_the_stated_cut, choose=_two_groups)
