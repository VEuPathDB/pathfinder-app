"""The separation card, and the build a yes runs from the offer it names.

The offer is the measured spec, so a yes builds it with no model in between. A
no never reaches this tool: the turn ends without the Lead.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.graph.turn_records import CreatedControlSet
from pathfinder.ai.lead.card_reply import CardReply
from pathfinder.ai.lead.deltas import ExecuteDelta
from pathfinder.ai.lead.lead_tools import clear_the_strategy
from pathfinder.ai.lead.sub_agent_dispatch import build_the_minted, minted_spec
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.domain.separation import AttachedControls, SeparationOffer
from pathfinder.services.evidence.control_sets import (
    create_control_set,
    new_control_set,
)


def unknown_offer_message(task_id: str, offers: Mapping[str, SeparationOffer]) -> str:
    """Why an adoption names no offer, with the offers the thread holds."""
    held = ", ".join(sorted(offers)) or "none"
    return (
        f"No separation run of this conversation has task id {task_id!r}. The runs "
        f"that offered a strategy: {held}. Call adopt_separating_strategy with "
        f"the task id of the report you are offering."
    )


async def _attach_the_controls(
    deps: LeadDeps, offer: SeparationOffer
) -> AttachedControls:
    """Save the offer's controls as a set, and name them for VERIFY."""
    runtime = deps.runtime
    positives = sorted([*offer.positive.returned, *offer.positive.not_returned])
    negatives = sorted([*offer.negative.returned, *offer.negative.not_returned])
    async with runtime.db_session_factory() as session:
        created = await create_control_set(
            session,
            new_control_set(
                name=(
                    f"Separation controls: {len(positives)} positive, "
                    f"{len(negatives)} negative"
                ),
                site_id=runtime.site_id,
                record_type=offer.spec.record_type,
                positive_ids=positives,
                negative_ids=negatives,
                source="separation",
            ),
            user_id=runtime.user_id,
        )
        await session.commit()
    deps.state.turn_markers.record_control_set(
        CreatedControlSet(id=created.id, name=created.name),
    )
    return AttachedControls(
        task_id=offer.task_id,
        control_set_id=created.id,
        positives=positives,
        negatives=negatives,
    )


async def adopt_separating_strategy(
    ctx: RunContext[LeadDeps], task_id: str, *, reply: CardReply
) -> ExecuteDelta:
    """Offer the strategy a separation run found, as a card the researcher answers.

    Call it when a ``separate_controls`` result carries an ``offer``, with
    that report's task id and your reply, which reports the result from its
    counts and streams above the card: the card's question and every number
    on it are read from the run, never from you. A yes builds the measured strategy,
    replacing any strategy the conversation holds with a revision a revert undoes,
    saves the controls as a control set, and returns the ``ExecuteDelta``:
    report it as after any build, then call ``verify_strategy``, which tests
    the strategy with exactly those controls. A no ends the turn with your
    text as it stands.
    """
    del reply
    deps = ctx.deps
    offer = deps.state.domain.separation_offers.get(task_id)
    if offer is None:
        raise ModelRetry(
            unknown_offer_message(task_id, deps.state.domain.separation_offers)
        )
    # The checks run before the clear, so a refused offer leaves the strategy.
    minted = minted_spec(offer.spec)
    deps.state.turn_markers.accepted_proposal = True
    deps.state.domain.declined_proposal = None
    if deps.step_count:
        await clear_the_strategy(ctx)
    deps.state.domain.operational_spec = offer.spec
    delta = await build_the_minted(deps, minted)
    deps.state.domain.attached_controls = await _attach_the_controls(deps, offer)
    return delta


__all__ = ["adopt_separating_strategy", "unknown_offer_message"]
