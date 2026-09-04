"""The mock's FRAME re-binds one criterion of an edit and declares the rest.

The edit work order prints the workspace, so the script reads the criterion ids
from it rather than from a canned spec whose ids the build already replaced.
"""

from __future__ import annotations

from typing import Any

from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.lead.edit_messages import edit_work_order
from pathfinder.ai.models.mock.specs import (
    CriterionReply,
    edit_frame_call,
    workspace_criteria,
)
from pathfinder.domain.parameters.values import MultiPickValue, SinglePickValue
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.ops import CombineOp

_PV = "Plasmodium vivax P01"


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="kinase candidates",
        criteria=[
            Criterion(
                id="step_text",
                text="genes whose product mentions kinase",
                search_name="GenesByText",
                role="filter",
                resolved_params={
                    "text_expression": SinglePickValue(value="kinase"),
                    "text_search_organism": MultiPickValue(
                        values=["Plasmodium falciparum 3D7"]
                    ),
                },
            ),
            Criterion(
                id="step_taxon",
                text="Plasmodium falciparum 3D7 genes",
                search_name="GenesByTaxon",
                role="seed",
                resolved_params={
                    "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])
                },
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.UNION,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="step_text"),
                    StructureNode(kind="leaf", criterion_id="step_taxon"),
                ],
            )
        ),
    )


def _order() -> str:
    return edit_work_order("swap the organism", "keep the rest", _spec())


def _call(
    already: list[ToolCallPart] | None = None,
    replies: list[CriterionReply] | None = None,
) -> ToolCallPart:
    return edit_frame_call(_order(), _PV, already, replies)


def _listed() -> list[ToolCallPart]:
    return [ToolCallPart(tool_name="list_searches", args={}, tool_call_id="c0")]


def test_the_workspace_is_read_from_the_work_order() -> None:
    criteria = workspace_criteria(_order())

    assert [c.criterion_id for c in criteria] == ["step_text", "step_taxon"]
    assert criteria[1].search_name == "GenesByTaxon"
    assert criteria[1].role == "seed"
    assert criteria[1].values["organism"] == '["Plasmodium falciparum 3D7"]'


def test_the_universe_is_opened_before_anything_is_bound() -> None:
    assert _call().tool_name == "list_searches"


def test_only_the_seed_criterion_reads_its_sheet() -> None:
    call = _call(_listed())

    assert call.tool_name == "set_criterion"
    args: dict[str, Any] = dict(call.args or {})
    assert args["criterion_id"] == "step_taxon"
    assert "params" not in args


def test_the_proposal_moves_only_the_organism() -> None:
    sheet = CriterionReply(
        criterion_id="step_taxon", params_template={"organism": None}
    )

    call = _call(_listed(), [sheet])

    args: dict[str, Any] = dict(call.args or {})
    assert args["params"] == {"organism": [_PV]}
    assert args["role"] == "seed"


def test_the_result_declares_every_criterion_the_workspace_listed() -> None:
    bound = CriterionReply(criterion_id="step_taxon", resolved_params={"organism": _PV})

    call = _call(_listed(), [bound])

    assert call.tool_name == "final_result"
    args: dict[str, Any] = dict(call.args or {})
    assert [(c["criterionId"], c["disposition"]) for c in args["changes"]] == [
        ("step_text", "kept"),
        ("step_taxon", "changed"),
    ]
