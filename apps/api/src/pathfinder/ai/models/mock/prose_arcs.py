"""The Lead arcs that answer in prose: each classifies the turn and writes the
reply, dispatching no sub-agent."""

from __future__ import annotations

from assistant_core.models.scripted import last_user_text
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.calls import classify, lead_final
from pathfinder.ai.models.mock.directive import without_tokens

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
IMPACT_PROSE = (
    "Switching the combine to INTERSECT makes the **operator** **stricter**: "
    "the result **drops** to genes supported by *both* signals. That tightens "
    "specificity at the cost of recall, so expect a smaller candidate list."
)
CONTEXT_PROSE = (
    "Good area to be in. I have not built anything yet. Say the word and I "
    "will put a candidate strategy together for it."
)


def classified_prose(classification: str, prose: str) -> list[ToolCallPart]:
    return [classify(classification), lead_final(prose, "await_user")]


def off_topic() -> list[ToolCallPart]:
    return classified_prose("off_topic", OFF_TOPIC_PROSE)


def kinase_question() -> list[ToolCallPart]:
    return classified_prose("follow_up_question", KINASE_PROSE)


def impact() -> list[ToolCallPart]:
    return classified_prose("follow_up_question", IMPACT_PROSE)


def context() -> list[ToolCallPart]:
    return classified_prose("context_statement", CONTEXT_PROSE)


def echo(messages: list[ModelMessage]) -> list[ToolCallPart]:
    """A message that names no arc is answered with its own text."""
    return [
        lead_final(f"[mock] {without_tokens(last_user_text(messages))}", "await_user")
    ]
