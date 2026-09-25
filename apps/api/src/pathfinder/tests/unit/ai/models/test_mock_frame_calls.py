"""The mock FRAME flow emits calls the real tools accept.

The mock drives the production ``set_criterion`` and ``set_structure``, so a
canned argument shape that has drifted from the tool signature fails only in an
e2e run, and reads there as a pipeline fault.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic_ai.messages import ToolCallPart, ToolReturnPart
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.specs import (
    CriterionReply,
    SpecPlan,
    combined_spec,
    criterion_replies,
    frame_call,
    go_spec,
    interpro_spec,
    organism_for,
    proposal_args,
    set_structure_args,
    sheet_call_args,
    single_spec,
)
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.domain.strategy.operational_spec import StructureNode

_PF = "Plasmodium falciparum 3D7"
_SPECS = [single_spec(_PF), go_spec(_PF), interpro_spec(_PF), combined_spec(_PF)]


def _reply(criterion_id: str, names: list[str]) -> CriterionReply:
    return CriterionReply(
        criterion_id=criterion_id, params_template=dict.fromkeys(names)
    )


def _bound(criterion_id: str) -> CriterionReply:
    return CriterionReply(criterion_id=criterion_id, resolved_params={"organism": "x"})


def _called(*calls: ToolCallPart) -> frozenset[str]:
    return frozenset(call.tool_name for call in calls)


# ── Site awareness ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("site_id", "organism"),
    [
        ("plasmodb", _PF),
        ("cryptodb", "Cryptosporidium parvum Iowa II"),
        ("fungidb", "Aspergillus fumigatus Af293"),
        ("tritrypdb", "Leishmania major strain Friedlin"),
        ("toxodb", "Toxoplasma gondii ME49"),
    ],
)
def test_each_site_gets_an_organism_of_its_own(site_id: str, organism: str) -> None:
    assert organism_for(site_id) == organism


def test_an_unlisted_site_falls_back_to_the_plasmo_organism() -> None:
    assert organism_for("veupathdb") == _PF


def test_the_organism_reaches_every_criterion_of_the_spec() -> None:
    spec = combined_spec("Toxoplasma gondii ME49")
    organisms = [
        value
        for crit in spec.criteria
        for name, value in crit.values.items()
        if name in {"organism", "text_search_organism"}
    ]

    assert organisms == [["Toxoplasma gondii ME49"]] * 3


# ── Proposals follow the sheet ──────────────────────────────────────


@pytest.mark.parametrize("spec", _SPECS)
def test_a_proposal_names_exactly_the_sheet_parameters(spec: SpecPlan) -> None:
    adapter: TypeAdapter[ParamProposals] = TypeAdapter(ParamProposals)

    for criterion in spec.criteria:
        sheet = dict.fromkeys(["organism", "some_other_param"])
        args = proposal_args(criterion, sheet)

        assert set(args["params"]) == set(sheet)
        assert adapter.validate_python(args["params"])


def test_a_sheet_parameter_the_spec_does_not_value_is_proposed_as_null() -> None:
    criterion = interpro_spec(_PF).criteria[0]

    params = proposal_args(criterion, dict.fromkeys(["text_expression", "unknown"]))[
        "params"
    ]

    assert params == {"text_expression": "kinase", "unknown": None}


def test_a_proposal_says_why_by_the_first_parameter_it_values() -> None:
    criterion = go_spec(_PF).criteria[0]

    why = proposal_args(criterion, dict.fromkeys(["go_term", "go_typeahead"]))["why"]

    assert SearchChoice.model_validate(why) == SearchChoice(
        basis="parameter",
        term="go_typeahead",
        reason="sets go_typeahead to the value the request states",
    )


def test_a_proposal_that_values_nothing_gives_no_reason() -> None:
    criterion = go_spec(_PF).criteria[0]

    assert "why" not in proposal_args(criterion, dict.fromkeys(["go_term"]))


def test_a_canned_value_for_a_parameter_the_site_omits_is_never_sent() -> None:
    # GenesByGoTerm publishes different visible params per site; only the ones
    # the sheet lists may be proposed, or the tool refuses the whole call.
    criterion = go_spec(_PF).criteria[0]

    params = proposal_args(criterion, dict.fromkeys(["organism", "go_typeahead"]))[
        "params"
    ]

    assert params == {"organism": [_PF], "go_typeahead": ["GO:0004672"]}


@pytest.mark.parametrize("spec", _SPECS)
def test_the_sheet_is_read_before_the_params_are_proposed(spec: SpecPlan) -> None:
    for criterion in spec.criteria:
        assert "params" not in sheet_call_args(criterion)


# ── Progress follows the replies, not the calls ─────────────────────


@pytest.mark.parametrize("spec", _SPECS)
def test_discovery_precedes_every_criterion(spec: SpecPlan) -> None:
    # set_criterion's search_name is enum-guarded to discovered names, so a
    # frame that binds before listing the catalog is refused on its second
    # search. The first call must put the whole catalog in the universe.
    first = frame_call(spec, frozenset(), [])

    assert first.tool_name == "list_searches"
    assert first.args_as_dict() == {"record_type": "transcript"}


def test_discovery_is_not_repeated_once_called() -> None:
    spec = interpro_spec(_PF)
    discovery = frame_call(spec, frozenset(), [])

    nxt = frame_call(spec, _called(discovery), [])

    assert nxt.tool_name == "set_criterion"


def test_frame_reads_the_sheet_then_proposes_then_moves_on() -> None:
    spec = interpro_spec(_PF)
    first, second = spec.criteria
    discovery = frame_call(spec, frozenset(), [])

    sheet_call = frame_call(spec, _called(discovery), [])
    assert sheet_call.args_as_dict()["criterion_id"] == first.criterion_id
    assert "params" not in sheet_call.args_as_dict()

    replies = [_reply(first.criterion_id, ["text_expression"])]
    proposal = frame_call(spec, _called(discovery, sheet_call), replies)
    assert proposal.args_as_dict()["params"] == {"text_expression": "kinase"}

    replies = [_bound(first.criterion_id)]
    nxt = frame_call(spec, _called(discovery, sheet_call, proposal), replies)
    assert nxt.args_as_dict()["criterion_id"] == second.criterion_id


def test_a_refused_proposal_is_retried_not_skipped() -> None:
    # The tool raises ModelRetry for a value it cannot match, so no reply
    # carries resolved params. Marching on would build an empty strategy.
    spec = single_spec(_PF)
    crit = spec.criteria[0]
    discovery = frame_call(spec, frozenset(), [])
    sheet_call = frame_call(spec, _called(discovery), [])
    replies = [_reply(crit.criterion_id, ["organism"])]
    proposal = frame_call(spec, _called(discovery, sheet_call), replies)

    again = frame_call(spec, _called(discovery, sheet_call, proposal), replies)

    assert again.tool_name == "set_criterion"
    assert again.args_as_dict()["criterion_id"] == crit.criterion_id
    assert again.args_as_dict()["params"] == {"organism": [_PF]}


def test_structure_follows_once_every_criterion_is_bound() -> None:
    spec = interpro_spec(_PF)
    discovery = frame_call(spec, frozenset(), [])
    replies = [_bound(c.criterion_id) for c in spec.criteria]

    assert frame_call(spec, _called(discovery), replies).tool_name == "set_structure"


def test_the_frame_result_follows_the_structure() -> None:
    spec = interpro_spec(_PF)
    discovery = frame_call(spec, frozenset(), [])
    replies = [_bound(c.criterion_id) for c in spec.criteria]
    structure = frame_call(spec, _called(discovery), replies)

    assert (
        frame_call(spec, _called(discovery, structure), replies).tool_name
        == "final_result"
    )


def test_the_go_criterion_carries_the_vocabulary_half_only() -> None:
    # go_term and go_typeahead are ORed halves of one criterion; a proposal
    # that fills both is refused by set_criterion.
    for spec in (go_spec(_PF), combined_spec(_PF)):
        go = next(c for c in spec.criteria if c.search_name == "GenesByGoTerm")

        assert go.values["go_typeahead"] == ["GO:0004672"]
        assert "go_term" not in go.values


# ── Reading the tool's reply back ───────────────────────────────────


def test_a_real_set_criterion_result_parses_into_a_reply() -> None:
    result = SetCriterionResult(
        criterion_id="c1",
        search_name="GenesByTaxon",
        params_template={"organism": None},
    )
    part = ToolReturnPart(
        tool_name="set_criterion", content=result, tool_call_id="call-1"
    )

    (reply,) = criterion_replies([part])

    assert reply.criterion_id == "c1"
    assert list(reply.params_template) == ["organism"]


def test_a_serialized_reply_parses_the_same_way() -> None:
    part = ToolReturnPart(
        tool_name="set_criterion",
        content={
            "criterionId": "c1",
            "searchName": "GenesByTaxon",
            "resolvedParams": {"organism": '["x"]'},
        },
        tool_call_id="call-1",
    )

    (reply,) = criterion_replies([part])

    assert reply.resolved_params == {"organism": '["x"]'}


def test_a_retry_message_yields_no_reply() -> None:
    part = ToolReturnPart(
        tool_name="set_criterion", content="no entry matching", tool_call_id="call-1"
    )

    assert criterion_replies([part]) == []


def test_another_tool_s_return_is_ignored() -> None:
    part = ToolReturnPart(
        tool_name="set_structure", content={"criteriaCombined": 2}, tool_call_id="s-1"
    )

    assert criterion_replies([part]) == []


# ── The structure call ──────────────────────────────────────────────


@pytest.mark.parametrize("spec", _SPECS)
def test_the_structure_call_is_a_tree_over_the_specs_criteria(spec: SpecPlan) -> None:
    root = StructureNode.model_validate(set_structure_args(spec)["root"])

    assert sorted(_criterion_ids(root)) == sorted(c.criterion_id for c in spec.criteria)


def test_the_two_leaf_spec_unions_its_leaves() -> None:
    root = StructureNode.model_validate(set_structure_args(interpro_spec(_PF))["root"])

    assert root.kind == "combine"
    assert root.operator == CombineOp.UNION
    assert [n.kind for n in root.inputs] == ["leaf", "leaf"]


def test_the_all_param_spec_nests_a_union_inside_an_intersect() -> None:
    root = StructureNode.model_validate(set_structure_args(combined_spec(_PF))["root"])

    assert root.operator == CombineOp.INTERSECT
    assert root.inputs[0].operator == CombineOp.UNION
    assert root.inputs[1].kind == "leaf"


@pytest.mark.parametrize("spec", _SPECS)
def test_every_spec_names_a_search_for_every_criterion(spec: SpecPlan) -> None:
    assert all(c.search_name for c in spec.criteria)


def _criterion_ids(node: StructureNode) -> list[str]:
    own = [node.criterion_id] if node.criterion_id else []
    return own + [cid for child in node.inputs for cid in _criterion_ids(child)]
