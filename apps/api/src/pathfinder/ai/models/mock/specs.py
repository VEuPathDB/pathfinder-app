"""Canned FRAME specs for the deterministic test mock.

The mock's FRAME sub-agent drives ``set_criterion`` twice per criterion (once
with no ``params`` to read the parameter sheet, once to propose them) then
``set_structure`` to assemble an ``OperationalSpec``, then returns a
``FrameResult``. A proposal names only the parameters the sheet just listed, so
a canned name that a site does not publish is never sent. Organisms are chosen
per site, because a value outside the site's vocabulary binds nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from assistant_core.models.scripted import scripted_call
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from pydantic_ai.messages import ToolCallPart, ToolReturnPart

from pathfinder.domain.strategy.operational_spec import StructureNode
from pathfinder.domain.strategy.ops import CombineOp

# One organism per site, each an entry of that site's GenesByTaxon vocabulary.
# The portal and any unlisted site take the plasmo organism.
_DEFAULT_ORGANISM = "Plasmodium falciparum 3D7"
_SITE_ORGANISMS = {
    "plasmodb": _DEFAULT_ORGANISM,
    "toxodb": "Toxoplasma gondii ME49",
    "tritrypdb": "Leishmania major strain Friedlin",
    "cryptodb": "Cryptosporidium parvum Iowa II",
    "fungidb": "Aspergillus fumigatus Af293",
}

_KINASE_GO_TERM = "GO:0004672"

# The organism an edit turn substitutes in, one per site and never the site's
# own default, so the swap moves a value.
_DEFAULT_ALT_ORGANISM = "Plasmodium vivax P01"
_SITE_ALT_ORGANISMS = {
    "plasmodb": _DEFAULT_ALT_ORGANISM,
    "toxodb": "Toxoplasma gondii GT1",
    "tritrypdb": "Leishmania donovani BPK282A1",
    "cryptodb": "Cryptosporidium hominis TU502",
    "fungidb": "Aspergillus nidulans FGSC A4",
}


def alt_organism_for(site_id: str) -> str:
    """The organism an edit substitutes in on a site."""
    return _SITE_ALT_ORGANISMS.get(site_id, _DEFAULT_ALT_ORGANISM)


def organism_for(site_id: str) -> str:
    """The canned organism for a site. Unlisted sites take the plasmo organism."""
    return _SITE_ORGANISMS.get(site_id, _DEFAULT_ORGANISM)


ParamValues = dict[str, str | list[str] | None]


@dataclass(frozen=True)
class CriterionSpec:
    criterion_id: str
    text: str
    search_name: str
    role: str = "filter"
    # Values by parameter name. Only the names the sheet lists are proposed; a
    # sheet name absent here is proposed as null, so the search default applies.
    values: ParamValues = field(default_factory=dict)


@dataclass(frozen=True)
class SpecPlan:
    title: str
    criteria: tuple[CriterionSpec, ...]
    structure: StructureNode


class CriterionReply(BaseModel):
    """The part of a ``set_criterion`` reply the mock reads back.

    The sheet reply carries ``params_template``; the binding reply carries
    ``resolved_params``. A retry carries neither, so the mock re-issues the call
    instead of marching on with an unbound criterion.
    """

    model_config = ConfigDict(
        extra="ignore", populate_by_name=True, from_attributes=True
    )

    criterion_id: str = Field(default="", alias="criterionId")
    params_template: dict[str, str | None] = Field(
        default_factory=dict, alias="paramsTemplate"
    )
    resolved_params: dict[str, Any] = Field(
        default_factory=dict, alias="resolvedParams"
    )


def _leaf(crit: CriterionSpec) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=crit.criterion_id)


def _combine(
    operator: CombineOp, left: StructureNode, right: StructureNode
) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=[left, right])


def _taxon(organism: str, criterion_id: str = "taxon_genes") -> CriterionSpec:
    return CriterionSpec(
        criterion_id=criterion_id,
        text=f"{organism} genes",
        search_name="GenesByTaxon",
        role="seed",
        values={"organism": [organism]},
    )


def _text_kinases(organism: str) -> CriterionSpec:
    return CriterionSpec(
        criterion_id="text_kinases",
        text=f"{organism} genes whose product mentions kinase",
        search_name="GenesByText",
        role="filter",
        values={
            "text_search_organism": [organism],
            "text_expression": "kinase",
            "text_fields": ["product"],
        },
    )


def _go_kinases(organism: str) -> CriterionSpec:
    # go_term stays unset: it is the free-text half of the criterion, and
    # set_criterion refuses a proposal that fills both ORed halves.
    return CriterionSpec(
        criterion_id="go_kinase_genes",
        text=f"{organism} genes annotated with protein kinase activity",
        search_name="GenesByGoTerm",
        role="filter",
        values={
            "organism": [organism],
            "go_typeahead": [_KINASE_GO_TERM],
            "go_term_evidence": ["Curated", "Computed"],
            "go_term_slim": "No",
        },
    )


def single_spec(organism: str) -> SpecPlan:
    """One GenesByTaxon leaf. The smallest spec that still builds a strategy."""
    taxon = _taxon(organism)
    return SpecPlan(
        title=f"{organism} genes (mock)",
        criteria=(taxon,),
        structure=_leaf(taxon),
    )


def go_spec(organism: str) -> SpecPlan:
    """One GenesByGoTerm leaf, whose vocabulary depends on the organism."""
    go = _go_kinases(organism)
    return SpecPlan(
        title=f"{organism} kinases by GO term (mock)",
        criteria=(go,),
        structure=_leaf(go),
    )


def interpro_spec(organism: str) -> SpecPlan:
    """Two leaves under a UNION: a text search and a taxon search."""
    text = _text_kinases(organism)
    taxon = _taxon(organism)
    return SpecPlan(
        title=f"{organism} kinase candidates (mock)",
        criteria=(text, taxon),
        structure=_combine(CombineOp.UNION, _leaf(text), _leaf(taxon)),
    )


def combined_spec(organism: str) -> SpecPlan:
    """Five nodes over three search types: (text UNION go) INTERSECT taxon."""
    text = _text_kinases(organism)
    go = _go_kinases(organism)
    taxon = _taxon(organism)
    return SpecPlan(
        title=f"{organism} comprehensive kinases (mock)",
        criteria=(text, go, taxon),
        structure=_combine(
            CombineOp.INTERSECT,
            _combine(CombineOp.UNION, _leaf(text), _leaf(go)),
            _leaf(taxon),
        ),
    )


def sheet_call_args(crit: CriterionSpec) -> dict[str, Any]:
    """The sheet-reading call. It carries no ``params``, so nothing is bound."""
    return {
        "criterion_id": crit.criterion_id,
        "text": crit.text,
        "search_name": crit.search_name,
        "role": crit.role,
    }


def proposal_args(crit: CriterionSpec, sheet: dict[str, str | None]) -> dict[str, Any]:
    """The binding call: one entry per sheet parameter, valued or null."""
    args = sheet_call_args(crit)
    args["params"] = {name: crit.values.get(name) for name in sheet}
    return args


def set_structure_args(spec: SpecPlan) -> dict[str, Any]:
    return {"root": spec.structure.model_dump(mode="json", by_alias=True)}


def criterion_replies(parts: list[ToolReturnPart]) -> list[CriterionReply]:
    """The ``set_criterion`` replies, in order. A retry reply parses to nothing."""
    replies: list[CriterionReply] = []
    for part in parts:
        if part.tool_name != "set_criterion":
            continue
        try:
            replies.append(CriterionReply.model_validate(part.content))
        except ValidationError:
            continue
    return replies


def frame_call(
    spec: SpecPlan,
    already_called: list[ToolCallPart] | None = None,
    replies: list[CriterionReply] | None = None,
) -> ToolCallPart:
    """The next FRAME tool call.

    ``list_searches`` runs first so every canned search name enters the
    enum-guarded universe. Each criterion then reads its sheet and proposes
    the sheet's parameters, then ``set_structure``, then the ``FrameResult``.
    Progress follows the replies, not the calls, so a refused proposal is
    retried rather than skipped.
    """
    if not any(c.tool_name == "list_searches" for c in already_called or []):
        return scripted_call("list_searches", {"record_type": "transcript"})
    sheets = {
        r.criterion_id: r.params_template for r in replies or [] if r.params_template
    }
    bound = {r.criterion_id for r in replies or [] if r.resolved_params}
    for crit in spec.criteria:
        if crit.criterion_id in bound:
            continue
        sheet = sheets.get(crit.criterion_id)
        if sheet is None:
            return scripted_call("set_criterion", sheet_call_args(crit))
        return scripted_call("set_criterion", proposal_args(crit, sheet))
    if not any(c.tool_name == "set_structure" for c in already_called or []):
        return scripted_call("set_structure", set_structure_args(spec))
    return scripted_call("final_result", frame_result(spec))


def frame_result(spec: SpecPlan) -> dict[str, Any]:
    return {
        "summary": f"Framed {len(spec.criteria)} criterion(s) for {spec.title}.",
        "disposition": "spec_ready",
        "openQuestions": [],
    }


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


def edit_frame_call(
    work_order: str,
    organism: str,
    already_called: list[ToolCallPart] | None = None,
    replies: list[CriterionReply] | None = None,
) -> ToolCallPart:
    """Re-bind only the seed criterion under a new organism.

    Every other criterion the workspace lists is left alone, which is what the
    edit gate checks the result against.
    """
    criteria = workspace_criteria(work_order)
    target = next((c for c in criteria if c.search_name == "GenesByTaxon"), None)
    if target is None:
        return scripted_call(
            "final_result", edit_frame_result(criteria, None, organism)
        )
    if not any(c.tool_name == "list_searches" for c in already_called or []):
        return scripted_call("list_searches", {"record_type": "transcript"})
    bound = {r.criterion_id for r in replies or [] if r.resolved_params}
    if target.criterion_id in bound:
        return scripted_call(
            "final_result", edit_frame_result(criteria, target, organism)
        )
    args: dict[str, Any] = {
        "criterion_id": target.criterion_id,
        "text": target.text,
        "search_name": target.search_name,
        "role": target.role,
    }
    sheets = {
        r.criterion_id: r.params_template for r in replies or [] if r.params_template
    }
    sheet = sheets.get(target.criterion_id)
    if sheet is None:
        return scripted_call("set_criterion", args)
    args["params"] = {
        name: ([organism] if name == "organism" else None) for name in sheet
    }
    return scripted_call("set_criterion", args)


def edit_frame_result(
    criteria: list[WorkspaceCriterion],
    target: WorkspaceCriterion | None,
    organism: str,
) -> dict[str, Any]:
    """One disposition per criterion the workspace listed."""
    return {
        "summary": (
            f"Moved {target.criterion_id} to {organism}; the rest are unchanged."
            if target is not None
            else "Nothing in the workspace matches the request."
        ),
        "disposition": "spec_ready",
        "openQuestions": [],
        "changes": [
            {
                "criterionId": crit.criterion_id,
                "disposition": "changed" if crit is target else "kept",
                "changedParams": ({"organism": organism} if crit is target else {}),
            }
            for crit in criteria
        ],
    }


def verification_delta(*, success: bool, prose: str) -> dict[str, Any]:
    return {
        "digest": {
            "disposition": "done" if success else "awaiting_user",
            "prose": prose,
            "reason": "mock verification",
            "success": success,
        },
    }
