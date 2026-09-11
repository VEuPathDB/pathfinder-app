"""Binding a criterion to a strategy the user saved."""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    CriterionRole,
    OpenSlot,
    SavedStrategyRef,
)
from pathfinder.services.strategies.insert_saved import clone_saved_strategy
from pathfinder.services.strategies.saved_library import (
    SavedStrategyListing,
    list_saved_strategies,
    match_saved_reference,
)

SAVED_STRATEGY_SLOT = "saved_strategy"


async def saved_strategy_listing(
    ctx: RunContext[AgentDeps],
) -> list[SavedStrategyListing]:
    """The saved strategies the caller owns on this site."""
    deps = ctx.deps
    if deps.user_id is None or deps.db_session_factory is None:
        msg = (
            "This thread has no signed-in user, so it cannot read the saved "
            "strategy library. Bind the criterion to a search instead."
        )
        raise ModelRetry(msg)
    return await list_saved_strategies(
        deps.db_session_factory, user_id=deps.user_id, site_id=deps.site_id
    )


async def bind_saved_criterion(
    ctx: RunContext[AgentDeps],
    *,
    criterion_id: str,
    text: str,
    role: CriterionRole,
    reference: str,
) -> SavedStrategyListing:
    """Record a criterion whose input is a saved strategy.

    An unresolved reference is recorded as an open slot before the retry, so a
    frame that never resolves it stays unbuildable instead of building the
    remaining criteria alone.
    """
    listing = await saved_strategy_listing(ctx)
    match = match_saved_reference(listing, reference)
    if match is None:
        ctx.deps.agent_state.frame_set_criterion(
            Criterion(
                id=criterion_id,
                text=text,
                role=role,
                open_params=[
                    OpenSlot(
                        criterion_id=criterion_id,
                        param_name=SAVED_STRATEGY_SLOT,
                        question=_which_one(listing),
                        options=[entry.name for entry in listing],
                    )
                ],
            )
        )
        raise ModelRetry(_unresolved_message(reference, listing))
    cloned = await clone_saved_strategy(ctx.deps.site_id, match.wdk_strategy_id)
    ctx.deps.agent_state.frame_set_criterion(
        Criterion(
            id=criterion_id,
            text=text,
            role=role,
            saved_strategy_ref=SavedStrategyRef(
                conversation_id=match.conversation_id,
                name=match.name,
                wdk_strategy_id=match.wdk_strategy_id,
                root_count=match.root_count,
                step_count=match.step_count,
                subtree=cloned.root,
            ),
        )
    )
    return match


def holds_open_saved_slot(criterion: Criterion) -> bool:
    """Whether the criterion still waits on the user to name a saved strategy."""
    return any(slot.param_name == SAVED_STRATEGY_SLOT for slot in criterion.open_params)


def _which_one(listing: list[SavedStrategyListing]) -> str:
    if not listing:
        return "You have no saved strategies on this site. Which one did you mean?"
    return f"Which saved strategy: {', '.join(entry.name for entry in listing)}?"


def _unresolved_message(reference: str, listing: list[SavedStrategyListing]) -> str:
    if not listing:
        return (
            f"{reference!r} does not name a saved strategy: you have no saved "
            f"strategies on this site. Ask the user which strategy to start "
            f"from, and do not build without it."
        )
    names = ", ".join(f"{entry.name!r}" for entry in listing)
    return (
        f"{reference!r} does not name one of your saved strategies. The saved "
        f"strategies on this site are: {names}. Call set_criterion again with "
        f"one of those names, or ask the user which one they mean. Do not drop "
        f"the criterion and do not build without it."
    )
