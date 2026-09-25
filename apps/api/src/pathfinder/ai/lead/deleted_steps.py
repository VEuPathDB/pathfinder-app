"""The step a delete removes, as its approval card asks and its reply names it."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from os.path import commonprefix
from typing import Any

from assistant_core.graph.emit import emit_chunk
from assistant_core.graph.tool_summary import count_noun, summary_chunks
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import ConfigDict
from pydantic_ai.tools import DeferredToolRequests
from veupathdb.domain.strategy import CombineOp, StepKind, StrategyStep

from pathfinder.ai.graph.turn_records import NamedStep
from pathfinder.ai.lead.live_state import LiveStrategyState, read_live_state
from pathfinder.ai.lead.sub_agent_tools import LeadDeps

DELETE_TOOL = "delete_step"
REPLACE_TOOL = "replace_subtree"

_OPERATOR_WORDS: Mapping[CombineOp, tuple[str, ...]] = {
    CombineOp.INTERSECT: ("intersection",),
    CombineOp.UNION: ("union",),
    CombineOp.MINUS: ("minus", "subtraction"),
    CombineOp.RMINUS: ("minus", "subtraction"),
    CombineOp.LONLY: ("minus", "subtraction"),
    CombineOp.RONLY: ("minus", "subtraction"),
    CombineOp.COLOCATE: ("colocation",),
}
# A claim of a removal: "removed the intersection step", "deleted the orthology
# transform step".
_REMOVED = re.compile(
    r"\b(?:removed|deleted|dropped)\s+(?:the\s+)?((?:[\w'-]+\s+){1,4}?)steps?\b",
    re.IGNORECASE,
)
_SHORTEST_STEM = 5
_SHARED_STEM = 7
# Words every step name can carry, which name no one step.
_COMMON_WORDS = frozenset({"genes", "steps", "search", "searches"})


class _DeleteArgs(CamelModel):
    model_config = ConfigDict(extra="ignore")

    step_id: str


def named_step(step: StrategyStep) -> NamedStep:
    """The step as a reply can name it."""
    kind_words: tuple[str, ...] = (
        ("transform",) if step.kind is StepKind.TRANSFORM else ()
    )
    if step.operator is not None:
        kind_words = _OPERATOR_WORDS[step.operator]
    return NamedStep(
        title=step.display_label,
        search_name=step.search_name,
        kind_words=kind_words,
    )


def _named(live: LiveStrategyState, step_id: str) -> str | None:
    """The step by its title, search and count, as a card names it."""
    step = next((s for s in live.steps if s.step_id == step_id), None)
    if step is None:
        return None
    count = (
        "count not available"
        if step.estimated_size is None
        else count_noun(step.estimated_size, "gene")
    )
    facts = [fact for fact in (step.search_name, count) if fact]
    return f"'{step.display_name}' ({', '.join(facts)})"


def delete_question(live: LiveStrategyState, step_id: str) -> str | None:
    """The delete card's question: the step by its title, search and count."""
    named = _named(live, step_id)
    return None if named is None else f"Delete step {named}?"


def _removal_question(
    live: LiveStrategyState, tool_name: str, step_id: str
) -> str | None:
    if tool_name == DELETE_TOOL:
        return delete_question(live, step_id)
    named = _named(live, step_id)
    return None if named is None else f"Replace step {named} and the steps under it?"


async def ask_about_the_removals(
    deps: LeadDeps, requests: DeferredToolRequests, writer: Any
) -> None:
    """Write each parked removal's question as the first line of its call.

    The Lead's own deletes are asked, and so are the removals a pass it
    dispatched stopped at.
    """
    parked = [
        (call.tool_call_id, call.tool_name, call.args_as_dict())
        for call in requests.approvals
    ] + [
        (call.tool_call_id, call.tool_name, call.args)
        for pending in deps.pending_sub_agent_approvals.values()
        for call in pending.approvals
    ]
    removals = [p for p in parked if p[1] in (DELETE_TOOL, REPLACE_TOOL)]
    if not removals:
        return
    runtime = deps.runtime
    live = await read_live_state(runtime.strategy_session, runtime.site_id)
    for tool_call_id, tool_name, args in removals:
        step_id = _DeleteArgs.model_validate(args).step_id
        question = _removal_question(live, tool_name, step_id)
        if question is None:
            continue
        for chunk in summary_chunks(tool_call_id, question):
            emit_chunk(writer, chunk)


def _stems_meet(said: str, held: str) -> bool:
    """Whether two words are one word: one a prefix of the other, or a long stem."""
    if min(len(said), len(held)) < _SHORTEST_STEM:
        return False
    shared = len(commonprefix([said, held]))
    return shared == min(len(said), len(held)) or shared >= _SHARED_STEM


def _names_a_step(phrase: str, steps: Iterable[NamedStep]) -> bool:
    """Whether a word of the phrase is a word of one of the steps."""
    said = [
        word
        for word in (found.casefold() for found in re.findall(r"[A-Za-z]+", phrase))
        if word not in _COMMON_WORDS
    ]
    return any(
        _stems_meet(word, held)
        for step in steps
        for held in step.words()
        for word in said
    )


def _removed_phrases(prose: str) -> list[str]:
    """What the reply says it removed, each as the words before "step"."""
    return [match.group(1).strip() for match in _REMOVED.finditer(prose)]


def misnamed_removal(
    prose: str, deleted: Sequence[NamedStep], standing: Sequence[NamedStep]
) -> str | None:
    """The removal the reply claims that names a standing step and no deleted one."""
    return next(
        (
            phrase
            for phrase in _removed_phrases(prose)
            if not _names_a_step(phrase, deleted) and _names_a_step(phrase, standing)
        ),
        None,
    )


__all__ = [
    "DELETE_TOOL",
    "ask_about_the_removals",
    "delete_question",
    "misnamed_removal",
    "named_step",
]
