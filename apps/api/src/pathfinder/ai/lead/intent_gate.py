"""Which of the Lead's tools this turn's state allows it to reach.

Building is a response to a request, so a turn sees the tools that change a
strategy only after a classification of its own message that asks for one.
Each phase tool then carries a precondition the ledger, the live graph and
this turn's own record either meet or do not.
"""

from __future__ import annotations

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.graph.state import TurnMarkers
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.intent import BUILDING_INTENTS, IntentClassification
from pathfinder.ai.lead.ledger import InvestigationLedger
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
# itself, the two reads of what the thread holds, the two research reads, and
# both ways to keep something the user names. Every other tool waits for the
# classification.
UNCLASSIFIED_TOOLS: frozenset[str] = frozenset(
    {
        "classify_user_intent",
        "read_ledger_section",
        "get_live_strategy_state",
        "research_web_search",
        "research_literature_search",
        "remember",
        "create_workbench_gene_set",
        "list_workbench_gene_sets",
    }
)

# An edit and an extension of criteria that exist go through ``edit_strategy``.
_EDIT_INTENTS: frozenset[IntentClassification] = frozenset(
    {
        IntentClassification.EDIT_STRATEGY,
        IntentClassification.EXTEND_STRATEGY,
    }
)


def turn_is_classified(deps: LeadDeps) -> bool:
    """Whether this turn's own message carries a classification."""
    return deps.intent is not None and deps.state.turn_markers.intent_classified


def turn_builds(deps: LeadDeps) -> bool:
    """Whether the intent governing this turn asks for a build."""
    intent = deps.intent
    return (
        turn_is_classified(deps)
        and intent is not None
        and intent.classification in BUILDING_INTENTS
    )


def _step_count(deps: LeadDeps) -> int:
    graph = deps.runtime.strategy_session.get_graph(None)
    return 0 if graph is None else len(graph.steps)


def _frame_precondition_fails(
    deps: LeadDeps,
    ledger: InvestigationLedger,
    markers: TurnMarkers,
    steps: int,
) -> bool:
    if markers.framed:
        return True
    intent = deps.intent
    spec = ledger.frame.spec
    if (
        intent is not None
        and intent.classification in _EDIT_INTENTS
        and spec is not None
        and spec.criteria
        and steps
    ):
        return True
    return bool(ledger.build.zero_result_steps) and markers.built


def unmet_preconditions(deps: LeadDeps) -> frozenset[str]:
    """The tools whose precondition this turn does not meet."""
    markers = deps.state.turn_markers
    ledger = derive_ledger(deps.state, deps.intent)
    steps = _step_count(deps)
    unmet: set[str] = set()
    if _frame_precondition_fails(deps, ledger, markers, steps):
        unmet.add("frame_problem")
    if steps:
        unmet.add("build_strategy")
    if (ledger.build.outcome is None and not steps) or markers.verified:
        unmet.add("verify_strategy")
    if not markers.eda_previewed:
        unmet.add("create_eda_step")
    return frozenset(unmet)


def apply_tool_preconditions(
    ctx: RunContext[LeadDeps],
    tool_defs: list[ToolDefinition],
) -> list[ToolDefinition]:
    """Drop every tool this turn's state does not allow."""
    deps = ctx.deps
    if not turn_is_classified(deps):
        return [td for td in tool_defs if td.name in UNCLASSIFIED_TOOLS]
    if not turn_builds(deps):
        return [td for td in tool_defs if td.name not in BUILDING_TOOLS]
    unmet = unmet_preconditions(deps)
    return [td for td in tool_defs if td.name not in unmet]


__all__ = [
    "BUILDING_TOOLS",
    "UNCLASSIFIED_TOOLS",
    "apply_tool_preconditions",
    "turn_builds",
    "turn_is_classified",
    "unmet_preconditions",
]
