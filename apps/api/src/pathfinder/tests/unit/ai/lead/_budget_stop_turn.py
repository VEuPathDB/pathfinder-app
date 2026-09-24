"""A turn that built one step and saw verification object, as a budget stop reads it."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyStepNode, flatten_tree

from pathfinder.ai.graph.state import PhaseDisposition, VerificationDigest
from pathfinder.ai.lead.ledger_sections import BuildSection
from pathfinder.domain.strategy.build_outcome import BuildOutcome, NodeResult
from pathfinder.domain.strategy.session import StrategyGraph, StrategySession
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.services.strategies.sync_state import WDKSyncState

SITE_ID = "vectorbase"
STEP = "step_83639bb9"
TITLE = "Up at 24 h against 18 h and 36 h"
SEARCH = "GenesByEdaSubset"
_WDK_STEP = 440_545_693
_WDK_STRATEGY = 330_683_723
URL = (
    "https://vectorbase.org/vectorbase/app/workspace/strategies/"
    f"{_WDK_STRATEGY}/{_WDK_STEP}"
)
OBJECTION = "The step keeps genes higher at 24 h than at 36 h, not at 18 h."
QUESTION = "Should the comparison use 18 h alone as the reference?"
BUDGET = (
    "I stopped this turn at its budget of 80 model calls and 600000 tokens. "
    "Narrow the request and send it again, and I will start a fresh turn on it."
)
WORDS = "genes higher at 24 h than at 18 h and 36 h"
ADDED = AddedSearch(step_id=STEP, search_display_name=TITLE, criterion_text=WORDS)
ADDED_LINE = f'This turn added 1 step: "{TITLE}" ({WORDS}).'
NOT_VERIFIED = "The strategy was not verified this turn."
CHANGED_NOTHING = "This turn changed nothing."
STRATEGY_LINE = (
    f'The strategy holds 1 step; the final step "{TITLE}" returns 70 genes. '
    f"It is on VEuPathDB at {URL}."
)


def hold_the_built_step(session: StrategySession, step: str = STEP) -> None:
    """Put one gene step that reached the site with 70 genes into the session."""
    graph = StrategyGraph(graph_id="g1", name="Aedes 72 h", site_id=SITE_ID)
    graph.record_type = "transcript"
    graph.steps = flatten_tree(
        StrategyStepNode(id=step, search_name=SEARCH, display_name=TITLE)
    )
    graph.recompute_roots()
    session.graph = graph
    session.sync_state = WDKSyncState(
        wdk_step_ids={step: _WDK_STEP},
        step_counts={step: 70},
        wdk_strategy_id=_WDK_STRATEGY,
    )


def built_session() -> StrategySession:
    """A strategy of one gene step that reached the site with 70 genes."""
    session = StrategySession(site_id=SITE_ID)
    hold_the_built_step(session)
    return session


def built_outcome(step: str = STEP) -> BuildOutcome:
    return BuildOutcome(
        pushed_step_ids=[step],
        wdk_strategy_id=_WDK_STRATEGY,
        wdk_url=URL,
        counts={step: 70},
        root_count=70,
        node_results=[
            NodeResult(
                node_id=step,
                search_name=SEARCH,
                wdk_step_id=_WDK_STEP,
                count=70,
                status="ok",
            )
        ],
    )


def built() -> BuildSection:
    return BuildSection(outcome=built_outcome(), pushed_count=1)


def objection() -> VerificationDigest:
    return VerificationDigest(
        disposition=PhaseDisposition.DONE,
        prose=f"{OBJECTION} The export read the wrong reference group.",
        reason="reference group differs from the request",
        success=False,
    )
