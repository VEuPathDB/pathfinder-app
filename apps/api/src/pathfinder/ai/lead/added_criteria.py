from __future__ import annotations

from pathfinder.ai.lead.dispatch_context import refuse_and_keep_what_it_bound
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.strategy.constraints import Constraint, message_states
from pathfinder.domain.strategy.listed_transforms import listed_transform_ids
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.services.strategies.record_classes import site_transforms


def _names_the_requirement(text: str, requirement: Constraint) -> bool:
    """Whether the words carry each other: one requirement, in either phrasing."""
    value = requirement.requested_value
    return message_states(text, value) or message_states(value, text)


def _unstated(
    deps: LeadDeps, found: OperationalSpec, draft: OperationalSpec
) -> list[Criterion]:
    intent = deps.intent
    if intent is None:
        return []
    message = deps.state.user_prompt
    rest = message.casefold()
    for ask in intent.researcher_asks(message):
        rest = rest.replace(ask.text.casefold(), " ")
    held = {c.id for c in found.criteria}
    return [
        criterion
        for criterion in draft.criteria
        if criterion.id not in held
        and not message_states(rest, criterion.text)
        and not any(
            _names_the_requirement(criterion.text, c)
            for c in intent.explicit_constraints
        )
    ]


async def refuse_an_added_criterion_the_message_does_not_state(
    deps: LeadDeps, found: OperationalSpec | None, draft: OperationalSpec
) -> None:
    """Refuse an edit pass that adds a criterion no requirement of the message
    states and the site lists as no transform of the input it maps. An edit
    changes what the message asks for, and a question is answered without a step."""
    if deps.intent is None or found is None or deps.step_count == 0:
        return
    unstated = _unstated(deps, found, draft)
    if not unstated:
        return
    listed = (
        listed_transform_ids(draft, await site_transforms(deps.site_id))
        if deps.intent.asks_a_change
        else frozenset[str]()
    )
    for criterion in unstated:
        if criterion.id in listed:
            continue
        refuse_and_keep_what_it_bound(
            deps,
            f"The pass adds '{criterion.id}' ('{criterion.text}'), which no "
            "requirement of the message states; a question is answered with "
            "compare_search_variants, not with a step. Drop it, or name the "
            "requirement the message states for it.",
            refused={criterion.id},
        )


__all__ = ["refuse_an_added_criterion_the_message_does_not_state"]
