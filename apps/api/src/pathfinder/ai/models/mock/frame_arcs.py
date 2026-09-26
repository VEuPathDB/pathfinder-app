"""The FRAME scripts of the arcs: a canned spec bound on the site's values, an
edit of the strategy the work order prints, or a pass that binds nothing and
says why."""

from __future__ import annotations

import re
from collections.abc import Callable

from assistant_core.models.scripted import (
    current_scope_id,
    scripted_call,
)
from pydantic import Field, TypeAdapter
from pydantic_ai.messages import ModelMessage, ToolCallPart

from pathfinder.ai.models.mock.arc import Script
from pathfinder.ai.models.mock.edit_frame import (
    EDIT_WORK_ORDER,
    WorkspaceCriterion,
    workspace_criteria,
)
from pathfinder.ai.models.mock.growths import portal_only_criterion
from pathfinder.ai.models.mock.history import acted_tool_names, head_work_order
from pathfinder.ai.models.mock.message_words import message
from pathfinder.ai.models.mock.reads import (
    ToolAnswer,
    instructions_of,
    last_answer,
    last_return,
    refusal_of,
)
from pathfinder.ai.models.mock.sheets import workspace_search
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import (
    CriterionSpec,
    SearchWhy,
    SpecPlan,
    criterion_call,
    criterion_replies,
    frame_call,
    leaf,
)
from pathfinder.ai.models.mock.strategy_specs import cross_organism_spec, single_spec

_LOOP_ARGS = {"record_type": "transcript"}


def _site() -> SiteValues:
    return SiteValues.for_site(current_scope_id.get())


def _unbound(summary: str) -> ToolCallPart:
    return scripted_call(
        "final_result",
        {"summary": summary, "disposition": "needs_research", "openQuestions": []},
    )


def spec_frame(spec: Callable[[SiteValues], SpecPlan]) -> Script:
    """Bind ``spec`` on the site's values."""

    def script(messages: list[ModelMessage]) -> ToolCallPart:
        return frame_call(
            spec(_site()),
            acted_tool_names(messages),
            criterion_replies(messages),
            instructions_of(messages),
        )

    return script


def on_edit_order(
    edit: Callable[[list[ModelMessage], str], ToolCallPart],
    fresh: Callable[[SiteValues], SpecPlan] = single_spec,
) -> Script:
    """Play ``edit`` on an EDIT work order, and bind ``fresh`` on any other."""
    framed = spec_frame(fresh)

    def script(messages: list[ModelMessage]) -> ToolCallPart:
        work_order = head_work_order(messages)
        if not work_order.startswith(EDIT_WORK_ORDER):
            return framed(messages)
        return edit(messages, work_order)

    return script


def loop_frame() -> ToolCallPart:
    """The same catalog listing over and over, which the repetition guard stops."""
    return scripted_call("list_searches", _LOOP_ARGS)


def no_search_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """Rank and list the searches, find none that states the request, and name
    what it asked for, binding nothing."""
    called = acted_tool_names(messages)
    if "search_for_searches" not in called:
        return scripted_call("search_for_searches", {"query": message()})
    if "list_searches" not in called:
        return scripted_call("list_searches", {"record_type": "transcript"})
    asked = message().rstrip(".")
    return _unbound(f"No search on {current_scope_id.get()} states: {asked}.")


class _Experiment(ToolAnswer):
    dataset_id: str


class _OtherSites(ToolAnswer):
    experiments: list[_Experiment] = Field(default_factory=list)


class _Ranked(ToolAnswer):
    note: str | None = None
    name: str | None = None
    display_name: str = ""
    semantic_similarity: float | None = None
    other_sites: _OtherSites | None = None


_RANKED = TypeAdapter(list[_Ranked])
_OWN = "own_experiment"
_HIGHER = re.compile(rf"{_OWN}: (?P<higher>.+?) scored higher than ")
# The words of the request a nearest choice is stated against.
_TERM_WORDS = 6


def _nearer(messages: list[ModelMessage]) -> str | None:
    """The hits the tool says scored higher than the own hit it refused, or None
    when the newest binding refusal is not that one."""
    refusal = refusal_of(messages, "set_criterion")
    found = None if refusal is None else _HIGHER.search(refusal)
    return None if found is None else found["higher"]


def _own_hit(ranked: list[_Ranked], nearer: str | None) -> _Ranked | None:
    """The site's own search the ranking scored nearest, else its first own
    search, or None when it ranked none. Among hits the ranking rounds to one
    score, the one a refusal names as higher wins."""
    own = [r for r in ranked if r.name is not None]
    scored = [(s, r) for r in own if (s := r.semantic_similarity) is not None]
    higher = [p for p in scored if nearer is not None and p[1].display_name in nearer]
    if higher or scored:
        return max(higher or scored, key=lambda pair: pair[0])[1]
    return own[0] if own else None


def _other_dataset(ranked: list[_Ranked]) -> str | None:
    found = [
        e.dataset_id for r in ranked if r.other_sites for e in r.other_sites.experiments
    ]
    return found[0] if found else None


class _Read(ToolAnswer):
    name: str
    site: str
    where_they_run: str = ""


def _why(hit: _Ranked, name: str) -> SearchWhy:
    """Nearest to the request when the ranking scored the hit, else the only
    search that names itself."""
    if hit.semantic_similarity is None:
        term = hit.display_name or name
        return SearchWhy("only_match", term, f"{term} is the search the ranking named.")
    term = " ".join(message().split()[:_TERM_WORDS])
    return SearchWhy(
        "nearest", term, f"Of the searches ranked for {term}, this one scored nearest."
    )


def _own_spec(search_name: str, why: SearchWhy | None) -> SpecPlan:
    crit = CriterionSpec(
        criterion_id=_OWN,
        text=message(),
        search_name=search_name,
        role="seed",
        values={"organism": [_site().organism]},
        why=why,
    )
    return SpecPlan(title=message(), criteria=(crit,), structure=leaf(crit))


def other_site_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """List, then rank the searches, so the ranked read is the one that answers
    the binding, and bind the site's nearest own hit; rank again when the read
    is cut before the hit is bound. With no own hit at all, read the first
    experiment another site holds and bind nothing."""
    called = acted_tool_names(messages)
    if "list_searches" not in called:
        return scripted_call("list_searches", {"record_type": "transcript"})
    instructions = instructions_of(messages)
    replies = criterion_replies(messages)
    held = workspace_search(instructions, _OWN)
    if held is not None:
        return frame_call(_own_spec(held, None), called, replies, instructions)
    answer = last_answer(messages, "search_for_searches")
    if answer is None:
        return scripted_call("search_for_searches", {"query": message()})
    ranked = _RANKED.validate_python(answer)
    hit = _own_hit(ranked, _nearer(messages))
    if hit is not None and hit.name is not None:
        own = _own_spec(hit.name, _why(hit, hit.name))
        return frame_call(own, called, replies, instructions)
    return _elsewhere(messages, ranked, called)


def _elsewhere(
    messages: list[ModelMessage], ranked: list[_Ranked], called: frozenset[str]
) -> ToolCallPart:
    """Read the first experiment another site holds, then bind nothing."""
    dataset = _other_dataset(ranked)
    if dataset is not None and "read_experiment" not in called:
        return scripted_call("read_experiment", {"dataset_id": dataset})
    read = last_return(messages, "read_experiment", _Read)
    if read is None:
        return _unbound("No experiment of another site matches the request.")
    return _unbound(f"{read.name} runs on {read.site}. {read.where_they_run}")


def _kept(criteria: list[WorkspaceCriterion]) -> list[dict[str, str]]:
    return [{"criterionId": c.criterion_id, "disposition": "kept"} for c in criteria]


def portal_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """Propose orthologs in an organism another site holds; the refusal ends it,
    and an edit keeps every criterion it found."""
    called = acted_tool_names(messages)
    crit = portal_only_criterion(_site())
    if "list_searches" not in called:
        return scripted_call("list_searches", {"record_type": "transcript"})
    if "search_for_searches" not in called:
        return scripted_call("search_for_searches", {"query": crit.text})
    refused = refusal_of(messages, "set_criterion")
    call = criterion_call(crit, criterion_replies(messages), instructions_of(messages))
    if refused is None and call is not None:
        return call
    work_order = head_work_order(messages)
    held = (
        workspace_criteria(work_order) if work_order.startswith(EDIT_WORK_ORDER) else []
    )
    return scripted_call(
        "final_result",
        {
            "summary": "Nothing was bound.",
            "disposition": "spec_ready",
            "openQuestions": [],
            "changes": _kept(held),
        },
    )


def cross_organism_frame(messages: list[ModelMessage]) -> ToolCallPart:
    """Bind one search on two organisms under an INTERSECT, which is refused."""
    refused = refusal_of(messages, "set_structure")
    if refused is not None:
        return _unbound(refused)
    return spec_frame(cross_organism_spec)(messages)
