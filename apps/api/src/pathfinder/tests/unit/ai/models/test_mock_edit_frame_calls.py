"""The mock's FRAME re-binds one criterion of an edit and declares the rest.

The edit work order prints the workspace and its shape, so the script reads the
criterion ids and the tree from it rather than from a canned spec.
"""

from __future__ import annotations

from pydantic_ai.messages import ToolCallPart
from veupathdb.domain.parameters import MultiPickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.edit_messages import edit_work_order
from pathfinder.ai.models.mock.edit_frame import (
    param_edit_call,
    workspace_criteria,
    workspace_shape,
)
from pathfinder.ai.models.mock.specs import CriterionReply
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_diff import SpecDiff

_PF = "Plasmodium falciparum 3D7"
_TM = "GenesByTransmembraneDomains"
_SHAPE = StructureNode(
    kind="combine",
    operator=CombineOp.MINUS,
    inputs=[
        StructureNode(kind="leaf", criterion_id="step_sp"),
        StructureNode(kind="leaf", criterion_id="step_tm"),
    ],
)


def _spec() -> OperationalSpec:
    organism = MultiPickValue(values=[_PF])
    return OperationalSpec(
        goal="secreted genes without membrane domains",
        criteria=[
            Criterion(
                id="step_sp",
                text="genes with a predicted signal peptide",
                search_name="GenesWithSignalPeptide",
                role="seed",
                resolved_params={"organism": organism},
            ),
            Criterion(
                id="step_tm",
                text="genes with 2 to 99 transmembrane domains",
                search_name=_TM,
                role="filter",
                resolved_params={
                    "organism": organism,
                    "min_tm": StringValue(value="2"),
                    "max_tm": StringValue(value="99"),
                },
            ),
        ],
        structure=SpecStructure(root=_SHAPE),
    )


def _order() -> str:
    spec = _spec()
    return edit_work_order(
        "change the domain range",
        "Change the transmembrane range to 1 to 99.",
        spec,
        pending=SpecDiff(),
        answered=spec,
        answer=None,
    )


def _call(
    already: frozenset[str] = frozenset(),
    replies: list[CriterionReply] | None = None,
) -> ToolCallPart:
    return param_edit_call(_order(), _TM, {"min_tm": "1"}, already, replies or [])


def _listed() -> frozenset[str]:
    return frozenset({"list_searches"})


def test_the_workspace_is_read_from_the_work_order() -> None:
    criteria = workspace_criteria(_order())

    assert [c.criterion_id for c in criteria] == ["step_sp", "step_tm"]
    assert criteria[1].search_name == _TM
    assert criteria[1].role == "filter"
    assert criteria[1].values == {
        "organism": f'["{_PF}"]',
        "min_tm": "2",
        "max_tm": "99",
    }


def test_the_shape_is_read_from_the_work_order() -> None:
    assert workspace_shape(_order()) == _SHAPE


def test_the_universe_is_opened_before_anything_is_bound() -> None:
    assert _call().tool_name == "list_searches"


def test_only_the_named_criterion_reads_its_sheet() -> None:
    call = _call(_listed())

    assert call.tool_name == "set_criterion"
    args = call.args_as_dict()
    assert args["criterion_id"] == "step_tm"
    assert "params" not in args


def test_the_proposal_moves_the_named_value_and_copies_the_rest() -> None:
    sheet = CriterionReply(
        criterion_id="step_tm",
        search_name=_TM,
        params_template={"organism": None, "min_tm": None, "max_tm": None},
    )

    call = _call(_listed(), [sheet])

    assert call.args_as_dict()["params"] == {
        "organism": f'["{_PF}"]',
        "min_tm": "1",
        "max_tm": "99",
    }


def test_the_result_declares_every_criterion_the_workspace_listed() -> None:
    bound = CriterionReply(
        criterion_id="step_tm", search_name=_TM, resolved_params={"min_tm": "1"}
    )

    call = _call(_listed(), [bound])

    assert call.tool_name == "final_result"
    assert call.args_as_dict()["changes"] == [
        {"criterionId": "step_sp", "disposition": "kept"},
        {
            "criterionId": "step_tm",
            "disposition": "changed",
            "changedParams": {"min_tm": "1"},
        },
    ]
