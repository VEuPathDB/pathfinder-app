"""The bind schema of each FRAME step: the parameters and the display names the
open sheets hold, so the model reads them from the schema it fills and a
parameter term is one of them."""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.tools import ToolDefinition

from pathfinder.ai.graph.runtime import AgentDeps


def _object_branch(params: dict[str, Any]) -> dict[str, Any]:
    """The ``params`` schema that takes an object, not the null branch."""
    return next(b for b in params["anyOf"] if b.get("type") == "object")


def name_the_open_sheets(
    ctx: RunContext[AgentDeps], tool_def: ToolDefinition
) -> ToolDefinition:
    """``set_criterion`` with ``params`` keyed by the open sheets' parameters.

    The schema changes only when a sheet opens or closes, which is when the
    pinned sheets in the instructions change too.
    """
    sheets = {
        criterion_id: sheet
        for criterion_id, sheet in ctx.deps.agent_state.open_sheets.items()
        if sheet.opened and sheet.entries
    }
    if not sheets:
        return tool_def
    schema = copy.deepcopy(tool_def.parameters_json_schema)
    params = _object_branch(schema["properties"]["params"])
    value = params["additionalProperties"]
    names = sorted({e.name for sheet in sheets.values() for e in sheet.entries})
    params["properties"] = {name: copy.deepcopy(value) for name in names}
    params["additionalProperties"] = False
    shown = "; ".join(
        f"{criterion_id} ({sheet.search_name}): "
        f"{', '.join(e.display_name for e in sheet.entries)}"
        for criterion_id, sheet in sheets.items()
    )
    terms = sorted(
        {
            t
            for sheet in sheets.values()
            for e in sheet.entries
            for t in (e.name, e.display_name)
        }
    )
    schema["$defs"]["SearchChoice"] = _choice_by_basis(
        schema["$defs"]["SearchChoice"], terms, shown
    )
    return replace(tool_def, parameters_json_schema=schema)


def _choice_by_basis(
    choice: dict[str, Any], terms: list[str], shown: str
) -> dict[str, Any]:
    """``why`` as two branches: a parameter term is one name of an open sheet,
    and every other basis keeps a free term."""
    parameter = copy.deepcopy(choice)
    basis = parameter["properties"]["basis"]
    others = [b for b in basis.pop("enum") if b != "parameter"]
    basis["const"] = "parameter"
    term = parameter["properties"]["term"]
    term["enum"] = terms
    term["description"] += (
        f" With basis parameter, a display name of the open sheet: {shown}."
    )
    other = copy.deepcopy(choice)
    other["properties"]["basis"]["enum"] = others
    return {"anyOf": [parameter, other]}
