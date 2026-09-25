"""The Lead arcs of the deterministic test model that answer in prose.

They classify the turn and write the reply, dispatching no sub-agent. The two
call builders every arc shares live here as well, so the arcs in ``arcs`` and
the arcs here build the same calls.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from assistant_core.models.scripted import has_any, scripted_call, terminal_call
from pydantic_ai.messages import ToolCallPart

LeadTurnState = Literal["await_user", "complete"]

CLASSIFY = "classify_user_intent"

# Two sentences, no code, under the cap the off-topic validator holds.
OFF_TOPIC_PROSE = (
    "PathFinder builds and checks search strategies on the VEuPathDB "
    "sites, and runs EDA and exports on what they return. "
    "Ask me one of those and I will take it from there."
)
KINASE_PROSE = (
    "A kinase transfers a phosphate group onto a substrate. The genes here "
    "that carry protein kinase activity are the ones the GO criterion "
    "selected."
)
_CLARIFY_PROSE = (
    "Before I build this, let me **clarify** a few things so the strategy "
    "matches what you mean:\n\n"
    "- **Which** evidence defines 'expressed' - a mass-spec stage or a "
    "microarray percentile?\n"
    "- **How strict** on 'doesn't vary much' - what dN/dS cutoff?\n"
    "- What counts as 'no human equivalent' - which phylogenetic profile "
    "pattern?\n\n"
    "Answer those and I'll frame the strategy."
)
_IMPACT_PROSE = (
    "Switching the combine to INTERSECT makes the **operator** **stricter**: "
    "the result **drops** to genes supported by *both* signals. That tightens "
    "specificity at the cost of recall, so expect a smaller candidate list."
)
_CONTEXT_PROSE = (
    "Good area to be in. I have not built anything yet. Say the word and I "
    "will put a candidate strategy together for it."
)

# A request PathFinder does no part of: it names no gene, organism or dataset.
_OFF_TOPIC_MARKERS = ("write me a python script", "reverses a linked list")
# A biology question about the genes on the thread. It is in scope.
_KINASE_MARKERS = ("which of these genes are kinases",)
_IMPACT_MARKERS = ("switching the interpro", "switch the interpro", "interpro/go")
CLARIFY_MARKERS = ("human equivalent", "vary much")
_CONTEXT_MARKERS = ("i'm investigating", "i am investigating")


def lead_final(
    prose: str,
    next_state: LeadTurnState,
    *,
    strategy_changed: bool = False,
    sources: Sequence[Mapping[str, str]] = (),
) -> ToolCallPart:
    """The Lead's final answer, as the turn contract reads it: what the arc
    wrote and the references it cites."""
    return terminal_call(
        {
            "prose": prose,
            "nextState": next_state,
            "strategyChanged": strategy_changed,
            "sources": [dict(source) for source in sources],
        },
    )


def classify(classification: str) -> ToolCallPart:
    return scripted_call(
        CLASSIFY,
        {
            "intent": {
                "classification": classification,
                "inferredGoal": f"[mock] {classification}",
            },
        },
    )


def _classified_prose(classification: str, prose: str) -> list[ToolCallPart]:
    return [classify(classification), lead_final(prose, "await_user")]


def prose_only_sequence(lowered: str) -> list[ToolCallPart] | None:
    """The arcs that answer in prose and dispatch no sub-agent."""
    if has_any(lowered, _OFF_TOPIC_MARKERS):
        return _classified_prose("off_topic", OFF_TOPIC_PROSE)
    if has_any(lowered, _KINASE_MARKERS):
        return _classified_prose("follow_up_question", KINASE_PROSE)
    if has_any(lowered, _IMPACT_MARKERS):
        return [lead_final(_IMPACT_PROSE, "await_user")]
    if has_any(lowered, CLARIFY_MARKERS):
        return [lead_final(_CLARIFY_PROSE, "await_user")]
    if has_any(lowered, _CONTEXT_MARKERS):
        return _classified_prose("context_statement", _CONTEXT_PROSE)
    return None


__all__ = [
    "CLARIFY_MARKERS",
    "CLASSIFY",
    "KINASE_PROSE",
    "OFF_TOPIC_PROSE",
    "LeadTurnState",
    "classify",
    "lead_final",
    "prose_only_sequence",
]
