"""How the mock's FRAME binds a canned spec, and the result it answers with.

Each criterion reads its parameter sheet (``set_criterion`` with no
``params``), then proposes one value per sheet parameter, then ``set_structure``
assembles the tree and ``final_result`` answers. A proposal names only the
parameters the sheet listed, so a name a site does not publish is never sent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from assistant_core.models.scripted import scripted_call
from pydantic import Field
from pydantic_ai.messages import ModelMessage, ToolCallPart
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.message_words import message
from pathfinder.ai.models.mock.reads import ToolAnswer, returns_of
from pathfinder.ai.models.mock.sheets import (
    alt_organism,
    contrast_values,
    outside_value,
    richest_value,
    sheet_entries,
    workspace_criteria,
)
from pathfinder.ai.models.mock.site_values import ParamValues
from pathfinder.domain.strategy.operational_spec import StructureNode


@dataclass(frozen=True)
class SearchWhy:
    """Why a criterion runs its search, when no parameter it sets decides."""

    basis: str
    term: str
    reason: str


@dataclass(frozen=True)
class CriterionSpec:
    criterion_id: str
    text: str
    search_name: str
    role: str = "filter"
    # Only the names the sheet lists are proposed; a sheet name absent here is
    # proposed as null, so the search default applies.
    values: ParamValues = field(default_factory=dict)
    # A parameter valued with another organism than ``site_organism``, read
    # from this criterion's own sheet when it is proposed.
    alt_param: str | None = None
    site_organism: str = ""
    # Whether that other organism shares the genus of ``site_organism``.
    alt_same_genus: bool = True
    # A parameter valued with the sheet entry that counts the most records, for
    # a value no seed of the site carries.
    sheet_first: str | None = None
    # A parameter valued with the first of ``outside_choices`` its sheet does
    # not list, so the value is one the site does not reach.
    outside_param: str | None = None
    outside_choices: tuple[str, ...] = ()
    why: SearchWhy | None = None


@dataclass(frozen=True)
class SpecPlan:
    title: str
    criteria: tuple[CriterionSpec, ...]
    structure: StructureNode


class OpenSlotReply(ToolAnswer):
    """A parameter a binding left open, and the values the tool offers for it."""

    param_name: str
    options: list[str] = Field(default_factory=list)


class CriterionReply(ToolAnswer):
    """The part of a ``set_criterion`` reply the mock reads back.

    The sheet reply carries ``params_template``; the binding reply carries
    ``resolved_params``. Each names the search it answers. A refusal is no
    reply, so the mock re-issues the call instead of marching on unbound.
    """

    criterion_id: str = ""
    search_name: str
    params_template: dict[str, str | None] = Field(default_factory=dict)
    resolved_params: dict[str, Any] = Field(default_factory=dict)
    open_slots: list[OpenSlotReply] = Field(default_factory=list)


def leaf(crit: CriterionSpec) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=crit.criterion_id)


def combine(
    operator: CombineOp, left: StructureNode, right: StructureNode
) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=[left, right])


def transform(crit: CriterionSpec, source: StructureNode) -> StructureNode:
    return StructureNode(
        kind="transform", criterion_id=crit.criterion_id, inputs=[source]
    )


def sheet_call_args(crit: CriterionSpec) -> dict[str, Any]:
    """The sheet-reading call. It carries no ``params``, so nothing is bound."""
    return {
        "criterion_id": crit.criterion_id,
        "text": crit.text,
        "search_name": crit.search_name,
        "role": crit.role,
    }


def proposal_args(
    crit: CriterionSpec, sheet: dict[str, str | None], instructions: str
) -> dict[str, Any]:
    """The binding call: one entry per sheet parameter, valued or null, and why
    the search runs it: the first parameter it values, in sheet order. Each
    side of a contrast takes a group of its own."""
    values = {**contrast_values(instructions, crit.criterion_id), **crit.values}
    if crit.alt_param is not None:
        values[crit.alt_param] = [
            alt_organism(
                instructions,
                crit.criterion_id,
                crit.site_organism,
                same_genus=crit.alt_same_genus,
            )
        ]
    if crit.sheet_first is not None:
        values[crit.sheet_first] = [
            richest_value(instructions, crit.criterion_id, crit.sheet_first)
        ]
    if crit.outside_param is not None:
        values[crit.outside_param] = [
            outside_value(
                instructions,
                crit.criterion_id,
                crit.outside_param,
                crit.outside_choices,
            )
        ]
    return _binding_args(crit, {name: values.get(name) for name in sheet})


def _binding_args(crit: CriterionSpec, params: dict[str, Any]) -> dict[str, Any]:
    """A binding call with ``params``, and why: the criterion's own reason, else
    the first parameter it values."""
    args = sheet_call_args(crit)
    args["params"] = params
    stated = next((name for name, value in params.items() if value is not None), None)
    if crit.why is not None:
        args["why"] = asdict(crit.why)
    elif stated is not None:
        args["why"] = {
            "basis": "parameter",
            "term": stated,
            "reason": f"sets {stated} to the value the request states",
        }
    return args


def _sheet_is_readable(crit: CriterionSpec, instructions: str) -> bool:
    """Whether the pinned sheet lists the vocabulary the proposal copies from."""
    needed = {
        name
        for name in (crit.alt_param, crit.sheet_first, crit.outside_param)
        if name is not None
    }
    listed = {
        entry.name
        for entry in sheet_entries(instructions, crit.criterion_id)
        if entry.vocabulary
    }
    return needed <= listed


def _slots_answered(
    crit: CriterionSpec, bound: CriterionReply, sheet: list[str]
) -> ToolCallPart | None:
    """The binding again on the ``sheet`` names only, each open slot set to its
    first offered value and every other name to the value the tool resolved.
    It passes no why, so the reason the binding recorded is kept."""
    answered = {
        slot.param_name: [slot.options[0]] for slot in bound.open_slots if slot.options
    }
    if not answered:
        return None
    resolved = {n: v for n, v in bound.resolved_params.items() if n in sheet}
    params = {**dict.fromkeys(sheet), **resolved, **answered}
    return scripted_call("set_criterion", {**sheet_call_args(crit), "params": params})


def set_structure_args(spec: SpecPlan) -> dict[str, Any]:
    return {"root": spec.structure.model_dump(mode="json", by_alias=True)}


def criterion_replies(messages: list[ModelMessage]) -> list[CriterionReply]:
    """The ``set_criterion`` replies of the run, in order. A reply of another
    shape fails."""
    return returns_of(messages, "set_criterion", CriterionReply)


def criterion_call(
    crit: CriterionSpec, replies: list[CriterionReply], instructions: str
) -> ToolCallPart | None:
    """The next call that binds ``crit``, or None once a reply or the pinned
    workspace holds it bound. A proposal whose sheet is no longer pinned reads
    the sheet again first."""
    own = [
        r
        for r in replies
        if (r.criterion_id, r.search_name) == (crit.criterion_id, crit.search_name)
    ]
    bound = [r for r in own if r.resolved_params]
    sheets = [r.params_template for r in own if r.params_template]
    if bound:
        sheet = list(sheets[-1] if sheets else bound[-1].resolved_params)
        return _slots_answered(crit, bound[-1], sheet)
    if crit.criterion_id in workspace_criteria(instructions):
        return None
    if not sheets or not _sheet_is_readable(crit, instructions):
        return scripted_call("set_criterion", sheet_call_args(crit))
    return scripted_call("set_criterion", proposal_args(crit, sheets[-1], instructions))


def frame_call(
    spec: SpecPlan,
    already_called: frozenset[str],
    replies: list[CriterionReply],
    instructions: str,
) -> ToolCallPart:
    """The next FRAME tool call.

    A ranked read of the request runs first, or of the transform's words when
    the spec has one, since the listing leaves transforms out. ``list_searches``
    follows so every canned search name enters the enum-guarded universe.
    Progress follows the replies, not the calls, so a refused proposal is
    retried rather than skipped.
    """
    maps = next((crit for crit in spec.criteria if crit.role == "transform"), None)
    query = maps.text if maps is not None else message() or spec.title
    if "search_for_searches" not in already_called:
        return scripted_call("search_for_searches", {"query": query})
    if "list_searches" not in already_called:
        return scripted_call("list_searches", {"record_type": "transcript"})
    for crit in spec.criteria:
        call = criterion_call(crit, replies, instructions)
        if call is not None:
            return call
    if "set_structure" not in already_called:
        return scripted_call("set_structure", set_structure_args(spec))
    return scripted_call("final_result", frame_result(spec))


def frame_result(spec: SpecPlan) -> dict[str, Any]:
    return {
        "summary": f"Framed {len(spec.criteria)} criterion(s) for {spec.title}.",
        "disposition": "spec_ready",
        "openQuestions": [],
    }
