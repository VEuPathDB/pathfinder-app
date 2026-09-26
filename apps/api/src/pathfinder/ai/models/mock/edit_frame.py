"""The mock FRAME on an EDIT work order: it reads the criteria and the shape the
strategy holds, changes what the arc names, and states a disposition for the rest.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from assistant_core.models.scripted import scripted_call
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai.messages import ToolCallPart
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.growths import Growth
from pathfinder.ai.models.mock.specs import (
    CriterionReply,
    CriterionSpec,
    criterion_call,
    leaf,
)
from pathfinder.domain.strategy.operational_spec import StructureNode

EDIT_WORK_ORDER = "EDIT work order"


def _listing() -> ToolCallPart:
    return scripted_call("list_searches", {"record_type": "transcript"})


class WorkspaceCriterion(BaseModel):
    """One criterion an EDIT work order lists, with the values it holds."""

    model_config = ConfigDict(frozen=True)

    criterion_id: str
    text: str
    search_name: str
    role: str
    values: dict[str, str] = Field(default_factory=dict)


_HEADER = re.compile(
    r"^- \[(?P<cid>[^\]]+)\] (?P<text>.*) -> (?P<search>\S+) \((?P<role>\w+)\)$"
)
_VALUE = re.compile(r"^ {4}(?P<name>[^=]+)=(?P<value>.*)$")
_SHAPE_HEAD = "The shape the strategy has now:"
_SHAPE_LINE = re.compile(r"^(?P<pad> *)(?P<body>\S.*)$")
_NAMED = re.compile(r"^(?P<transform>TRANSFORM )?\[(?P<cid>[^\]]+)\]")


def workspace_criteria(work_order: str) -> list[WorkspaceCriterion]:
    """Read the criteria an EDIT work order prints, in order."""
    found: list[tuple[re.Match[str], dict[str, str]]] = []
    for line in work_order.splitlines():
        header = _HEADER.match(line)
        if header is not None:
            found.append((header, {}))
            continue
        value = _VALUE.match(line)
        if value is not None and found:
            found[-1][1][value.group("name")] = value.group("value")
    return [
        WorkspaceCriterion(
            criterion_id=header.group("cid"),
            text=header.group("text"),
            search_name=header.group("search"),
            role=header.group("role"),
            values=values,
        )
        for header, values in found
    ]


def _node(body: str, inputs: list[StructureNode]) -> StructureNode:
    named = _NAMED.match(body)
    if named is not None:
        kind = "transform" if named.group("transform") else "leaf"
        return StructureNode(kind=kind, criterion_id=named.group("cid"), inputs=inputs)
    if body == "COPY":
        return StructureNode(kind="copy", inputs=inputs)
    return StructureNode(kind="combine", operator=CombineOp(body), inputs=inputs)


def _build(rows: list[tuple[int, str]], at: int) -> tuple[StructureNode, int]:
    depth, body = rows[at]
    inputs: list[StructureNode] = []
    following = at + 1
    while following < len(rows) and rows[following][0] > depth:
        child, following = _build(rows, following)
        inputs.append(child)
    return _node(body, inputs), following


def workspace_shape(work_order: str) -> StructureNode | None:
    """The tree an EDIT work order prints under its shape heading."""
    lines = work_order.splitlines()
    if _SHAPE_HEAD not in lines:
        return None
    rows: list[tuple[int, str]] = []
    for line in lines[lines.index(_SHAPE_HEAD) + 1 :]:
        shaped = _SHAPE_LINE.match(line)
        if shaped is None:
            break
        rows.append((len(shaped.group("pad")), shaped.group("body")))
    return _build(rows, 0)[0] if rows else None


def _swap(node: StructureNode, old: str, new: StructureNode) -> StructureNode:
    if node.kind == "leaf" and node.criterion_id == old:
        return new
    return node.model_copy(update={"inputs": [_swap(c, old, new) for c in node.inputs]})


def _changes(
    criteria: list[WorkspaceCriterion],
    *,
    changed: Mapping[str, dict[str, str]] | None = None,
    dropped: str | None = None,
) -> list[dict[str, Any]]:
    moved = changed or {}
    out: list[dict[str, Any]] = []
    for crit in criteria:
        cid = crit.criterion_id
        if cid == dropped:
            out.append(
                {
                    "criterionId": cid,
                    "disposition": "dropped",
                    "reason": "the request removes it",
                }
            )
        elif cid in moved:
            out.append(
                {
                    "criterionId": cid,
                    "disposition": "changed",
                    "changedParams": moved[cid],
                }
            )
        else:
            out.append({"criterionId": cid, "disposition": "kept"})
    return out


def _final(summary: str, changes: list[dict[str, Any]]) -> ToolCallPart:
    return scripted_call(
        "final_result",
        {
            "summary": summary,
            "disposition": "spec_ready",
            "openQuestions": [],
            "changes": changes,
        },
    )


def _target(
    criteria: list[WorkspaceCriterion], search: str
) -> WorkspaceCriterion | None:
    return next((c for c in criteria if c.search_name == search), None)


def param_edit_call(
    work_order: str,
    search_name: str,
    change: dict[str, str],
    called: frozenset[str],
    replies: list[CriterionReply],
) -> ToolCallPart:
    """Move the named parameters of the criterion that runs ``search_name``,
    copying every other value the work order prints."""
    criteria = workspace_criteria(work_order)
    target = _target(criteria, search_name)
    if target is None:
        return _final("Nothing in the workspace runs that search.", _changes(criteria))
    if "list_searches" not in called:
        return _listing()
    if any(
        r.criterion_id == target.criterion_id and r.resolved_params for r in replies
    ):
        return _final(
            f"Moved {', '.join(change)} on {target.criterion_id}; the rest are unchanged.",
            _changes(criteria, changed={target.criterion_id: change}),
        )
    args: dict[str, Any] = {
        "criterion_id": target.criterion_id,
        "text": target.text,
        "search_name": target.search_name,
        "role": target.role,
    }
    sheets = {r.criterion_id: r.params_template for r in replies if r.params_template}
    sheet = sheets.get(target.criterion_id)
    if sheet is not None:
        held = {**target.values, **change}
        args["params"] = {name: held.get(name) for name in sheet}
    return scripted_call("set_criterion", args)


def _structure(root: StructureNode) -> ToolCallPart:
    return scripted_call(
        "set_structure", {"root": root.model_dump(mode="json", by_alias=True)}
    )


def grown_call(
    work_order: str,
    growth: Growth,
    called: frozenset[str],
    replies: list[CriterionReply],
    instructions: str,
) -> ToolCallPart:
    """Bind the growth's criteria and grow the tree the strategy holds with them."""
    criteria = workspace_criteria(work_order)
    shape = workspace_shape(work_order)
    if shape is None:
        return _final("The work order prints no shape to grow.", _changes(criteria))
    if "list_searches" not in called:
        return _listing()
    maps = next((c for c in growth.criteria if c.role == "transform"), None)
    if maps is not None and "search_for_searches" not in called:
        return scripted_call("search_for_searches", {"query": maps.text})
    for crit in growth.criteria:
        call = criterion_call(crit, replies, instructions)
        if call is not None:
            return call
    if "set_structure" not in called:
        return _structure(growth.grow(shape))
    return _final("Grew the strategy; the rest are unchanged.", _changes(criteria))


def _without(node: StructureNode, removed: str) -> StructureNode:
    """The tree with one leaf gone: a combine over it keeps its other input."""
    kept = [
        _without(child, removed)
        for child in node.inputs
        if not (child.kind == "leaf" and child.criterion_id == removed)
    ]
    if node.kind == "combine" and len(kept) == 1:
        return kept[0]
    return node.model_copy(update={"inputs": kept})


def removed_step_call(
    work_order: str, search_name: str, called: frozenset[str]
) -> ToolCallPart:
    """Drop the criterion that runs ``search_name`` and close the tree over it."""
    criteria = workspace_criteria(work_order)
    target = _target(criteria, search_name)
    shape = workspace_shape(work_order)
    if target is None or shape is None:
        return _final("Nothing in the workspace runs that search.", _changes(criteria))
    if "drop_criterion" not in called:
        return scripted_call(
            "drop_criterion",
            {"criterion_id": target.criterion_id, "reason": "the request removes it"},
        )
    if "set_structure" not in called:
        return _structure(_without(shape, target.criterion_id))
    return _final(
        f"Dropped {target.criterion_id}.",
        _changes(criteria, dropped=target.criterion_id),
    )


def replaced_step_call(
    work_order: str,
    search_name: str,
    added: CriterionSpec,
    called: frozenset[str],
    replies: list[CriterionReply],
    instructions: str,
) -> ToolCallPart:
    """Put ``added`` in the place of the criterion that runs ``search_name``."""
    criteria = workspace_criteria(work_order)
    target = _target(criteria, search_name)
    shape = workspace_shape(work_order)
    if target is None or shape is None:
        return _final("Nothing in the workspace runs that search.", _changes(criteria))
    if "list_searches" not in called:
        return _listing()
    call = criterion_call(added, replies, instructions)
    if call is not None:
        return call
    if "drop_criterion" not in called:
        return scripted_call(
            "drop_criterion",
            {
                "criterion_id": target.criterion_id,
                "reason": f"replaced by {added.search_name}",
            },
        )
    if "set_structure" not in called:
        return _structure(_swap(shape, target.criterion_id, leaf(added)))
    return _final(
        f"Replaced {target.criterion_id} with {added.criterion_id}.",
        _changes(criteria, dropped=target.criterion_id),
    )
