"""Which of the Lead's tools this turn's state allows it to reach.

Building is a response to a request, so a turn sees the tools that change a
strategy only after a classification of its own message that asks for one.
Each phase tool then carries a precondition the ledger, the live graph and
this turn's own record either meet or do not.
"""

from __future__ import annotations

from collections.abc import Collection

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import BUILDING_INTENTS, IntentClassification
from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.ai.lead.sub_agent_tools import LeadDeps

# The tools that write: they frame, materialize, patch or check a strategy, or
# they edit the EDA analysis a step is exported from.
BUILDING_TOOLS: frozenset[str] = frozenset(
    {
        "frame_problem",
        "build_strategy",
        "edit_strategy",
        "recover_failed_steps",
        "verify_strategy",
        "open_eda_analysis",
        "set_eda_filters",
        "run_eda_compute",
        "create_eda_step",
    }
)

# What a turn reaches before it says what the message asks: the classification
# itself, the two reads of what the thread holds, the gene record read, the two
# research reads, both ways to keep something the user names, the export of a
# gene set the user already saved, and the proposal card,
# which a typed yes accepts before any classification. Every other tool waits
# for the classification.
UNCLASSIFIED_TOOLS: frozenset[str] = frozenset(
    {
        "classify_user_intent",
        PROPOSAL_TOOL,
        "read_ledger_section",
        "get_live_strategy_state",
        "read_gene_record",
        "research_web_search",
        "research_literature_search",
        "remember",
        "save_gene_set",
        "list_gene_sets",
        "export_gene_set",
    }
)

# What a turn outside PathFinder's scope reaches. The answer is a redirect the
# instructions state, so the turn writes it and calls nothing.
OFF_TOPIC_TOOLS: frozenset[str] = frozenset()


def turn_is_classified(deps: LeadDeps) -> bool:
    """Whether this turn's own message carries a classification."""
    return deps.intent is not None and deps.state.turn_markers.intent_classified


def turn_is_off_topic(deps: LeadDeps) -> bool:
    """Whether this turn's own message asks for something PathFinder is not."""
    intent = deps.intent
    return (
        turn_is_classified(deps)
        and intent is not None
        and intent.classification is IntentClassification.OFF_TOPIC
    )


def turn_builds(deps: LeadDeps) -> bool:
    """Whether the intent governing this turn asks for a build.

    A researcher who accepts a proposal asks for the work the card names.
    """
    intent = deps.intent
    return (
        turn_is_classified(deps)
        and intent is not None
        and (
            intent.classification in BUILDING_INTENTS
            or deps.state.turn_markers.accepted_proposal
        )
    )


def verification_pending(deps: LeadDeps) -> bool:
    """Whether this turn's answer was refused before a check passed.

    A dispatch that reported failure is a check the build did not pass, so the
    turn keeps the one way out until a verification succeeds.
    """
    markers = deps.state.turn_markers
    return markers.contract_refused and markers.built and not markers.verified


def _subset_was_previewed(deps: LeadDeps) -> bool:
    """Whether the thread's open analysis has had its subset counted."""
    analysis = deps.state.domain.open_eda_analysis
    return analysis is not None and analysis.subset_previewed


def unmet_preconditions(deps: LeadDeps) -> frozenset[str]:
    """The tools whose precondition this turn does not meet.

    A turn whose answer was refused for want of a check reaches the check and
    no other tool that writes, so the refusal has one way out.
    """
    markers = deps.state.turn_markers
    ledger = derive_ledger(deps.state, deps.intent)
    steps = deps.step_count
    unmet: set[str] = set()
    # A strategy that holds a step is changed by an edit, never framed again.
    if markers.framed or steps:
        unmet.add("frame_problem")
    if steps:
        unmet.add("build_strategy")
    if not ledger.build.needs_recovery:
        unmet.add("recover_failed_steps")
    if not steps or markers.verified:
        unmet.add("verify_strategy")
    if not _subset_was_previewed(deps):
        unmet.add("create_eda_step")
    if verification_pending(deps):
        unmet |= BUILDING_TOOLS - {"verify_strategy"}
    return frozenset(unmet)


def tools_the_turn_offers(deps: LeadDeps, names: Collection[str]) -> frozenset[str]:
    """Which of ``names`` this turn's state lets the Lead reach."""
    if not turn_is_classified(deps):
        return frozenset(name for name in names if name in UNCLASSIFIED_TOOLS)
    if turn_is_off_topic(deps):
        return frozenset(name for name in names if name in OFF_TOPIC_TOOLS)
    if not turn_builds(deps):
        return frozenset(name for name in names if name not in BUILDING_TOOLS)
    unmet = unmet_preconditions(deps)
    return frozenset(name for name in names if name not in unmet)


def apply_tool_preconditions(
    ctx: RunContext[LeadDeps],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    """Drop every tool this turn's state does not allow."""
    offered = tools_the_turn_offers(ctx.deps, [td.name for td in tool_defs])
    return [td for td in tool_defs if td.name in offered]


__all__ = [
    "BUILDING_TOOLS",
    "OFF_TOPIC_TOOLS",
    "UNCLASSIFIED_TOOLS",
    "apply_tool_preconditions",
    "tools_the_turn_offers",
    "turn_builds",
    "turn_is_classified",
    "turn_is_off_topic",
    "unmet_preconditions",
    "verification_pending",
]
