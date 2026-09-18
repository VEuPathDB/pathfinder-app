"""Which WDK question a step names, and the one name no step may push."""

from __future__ import annotations

from veupathdb.domain.strategy import (
    COMBINE_SEARCH_NAME,
    StepKind,
    StrategyStep,
    wdk_search_name,
)
from veupathdb.errors import ValidationError

_SET_OPERATION_PREFIX = "boolean_question_"


def is_a_set_operation(search_name: str) -> bool:
    """Reports whether WDK lists this name as a record class boolean question."""
    return search_name.startswith(_SET_OPERATION_PREFIX)


def states_a_question(search_name: str) -> bool:
    """Reports whether this name is a question a caller states parameters for.

    The AST sentinel and a record class boolean question both stand for a set
    operation, which WDK builds from an operator and two inputs.
    """
    return (
        bool(search_name)
        and search_name != COMBINE_SEARCH_NAME
        and not is_a_set_operation(search_name)
    )


def names_a_wdk_question(step: StrategyStep) -> bool:
    """Reports whether this step pushes a question of its own, with parameters.

    Kind decides first. A combine that WDK named keeps that name, and the name
    carries none of the parameters a search takes.
    """
    if step.kind is StepKind.COMBINE:
        return False
    return states_a_question(wdk_search_name(step))


def refuse_a_set_operation(step_id: str, search_name: str) -> None:
    """Refuse a WDK write whose search name is a record class boolean question.

    WDK builds that step from an operator and two inputs, so a step reaching a
    search write under the name has lost its combine kind or an input slot.
    """
    if not is_a_set_operation(search_name):
        return
    raise ValidationError(
        title="set operation pushed as a search",
        detail=(
            f"step {step_id} names {search_name}. WDK builds that step from an "
            f"operator and two inputs, so it is not a search and states none "
            f"of the parameters a search takes."
        ),
    )
