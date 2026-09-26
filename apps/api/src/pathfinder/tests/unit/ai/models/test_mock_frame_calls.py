"""The mock FRAME flow emits calls the real tools accept.

The mock drives the production ``set_criterion`` and ``set_structure``, so a
canned argument shape that has drifted from the tool signature fails only in an
e2e run, and reads there as a pipeline fault.
"""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolCallPart,
    ToolReturnPart,
)
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.ai.models.mock.specs import (
    CriterionReply,
    CriterionSpec,
    SpecPlan,
    criterion_replies,
    frame_call,
    proposal_args,
    set_structure_args,
    sheet_call_args,
)
from pathfinder.ai.models.mock.strategy_specs import (
    combined_spec,
    count_spec,
    go_spec,
    intersect_spec,
    minus_spec,
    single_spec,
    union_spec,
    zero_spec,
)
from pathfinder.ai.tools.standalone._frame_proposals import ParamProposals
from pathfinder.ai.tools.standalone._frame_rationale import SearchChoice
from pathfinder.ai.tools.standalone._frame_result import SetCriterionResult
from pathfinder.domain.strategy.operational_spec import StructureNode

_PF = "Plasmodium falciparum 3D7"
_PLASMO = SiteValues.for_site("plasmodb")
_SPECS = [
    build(_PLASMO)
    for build in (
        single_spec,
        go_spec,
        union_spec,
        intersect_spec,
        minus_spec,
        combined_spec,
        count_spec,
        zero_spec,
    )
]


def _reply(crit: CriterionSpec, names: list[str]) -> CriterionReply:
    return CriterionReply(
        criterion_id=crit.criterion_id,
        search_name=crit.search_name,
        params_template=dict.fromkeys(names),
    )


def _bound(crit: CriterionSpec) -> CriterionReply:
    return CriterionReply(
        criterion_id=crit.criterion_id,
        search_name=crit.search_name,
        resolved_params={"organism": "x"},
    )


_DISCOVERED = frozenset({"search_for_searches", "list_searches"})


def _called(*calls: ToolCallPart) -> frozenset[str]:
    """The calls made, the two catalog reads a frame opens with among them."""
    return frozenset(call.tool_name for call in calls) | _DISCOVERED


# ── Site awareness ──────────────────────────────────────────────────


def test_the_organism_reaches_every_criterion_of_the_spec() -> None:
    spec = combined_spec(SiteValues.for_site("toxodb"))
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
        args = proposal_args(criterion, sheet, "")

        assert set(args["params"]) == set(sheet)
        assert adapter.validate_python(args["params"])


def test_a_sheet_parameter_the_spec_does_not_value_is_proposed_as_null() -> None:
    criterion = union_spec(_PLASMO).criteria[1]

    params = proposal_args(criterion, dict.fromkeys(["min_tm", "unknown"]), "")[
        "params"
    ]

    assert params == {"min_tm": "2", "unknown": None}


def test_a_proposal_says_why_by_the_first_parameter_it_values() -> None:
    criterion = go_spec(_PLASMO).criteria[0]

    why = proposal_args(criterion, dict.fromkeys(["go_term", "go_typeahead"]), "")[
        "why"
    ]

    assert SearchChoice.model_validate(why) == SearchChoice(
        basis="parameter",
        term="go_typeahead",
        reason="sets go_typeahead to the value the request states",
    )


def test_a_proposal_that_values_nothing_gives_no_reason() -> None:
    criterion = go_spec(_PLASMO).criteria[0]

    assert "why" not in proposal_args(criterion, dict.fromkeys(["go_term"]), "")


def test_a_canned_value_for_a_parameter_the_site_omits_is_never_sent() -> None:
    # GenesByGoTerm publishes different visible params per site; only the ones
    # the sheet lists may be proposed, or the tool refuses the whole call.
    criterion = go_spec(_PLASMO).criteria[0]

    params = proposal_args(criterion, dict.fromkeys(["organism", "go_typeahead"]), "")[
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
    """A ranked read opens the pass, and the listing puts every name in the
    enum-guarded universe before anything is bound."""
    first = frame_call(spec, frozenset(), [], "")
    second = frame_call(spec, frozenset({first.tool_name}), [], "")

    assert (first.tool_name, first.args_as_dict()) == (
        "search_for_searches",
        {"query": spec.title},
    )
    assert (second.tool_name, second.args_as_dict()) == (
        "list_searches",
        {"record_type": "transcript"},
    )


def test_discovery_is_not_repeated_once_called() -> None:
    spec = union_spec(_PLASMO)

    nxt = frame_call(spec, _called(), [], "")

    assert nxt.tool_name == "set_criterion"


def test_frame_reads_the_sheet_then_proposes_then_moves_on() -> None:
    spec = union_spec(_PLASMO)
    first, second = spec.criteria
    discovery = frame_call(spec, frozenset(), [], "")

    sheet_call = frame_call(spec, _called(discovery), [], "")
    assert sheet_call.args_as_dict()["criterion_id"] == first.criterion_id
    assert "params" not in sheet_call.args_as_dict()

    replies = [_reply(first, ["signalp_version"])]
    proposal = frame_call(spec, _called(discovery, sheet_call), replies, "")
    assert proposal.args_as_dict()["params"] == {"signalp_version": "SignalP-6.0"}

    replies = [_bound(first)]
    nxt = frame_call(spec, _called(discovery, sheet_call, proposal), replies, "")
    assert nxt.args_as_dict()["criterion_id"] == second.criterion_id


def test_a_refused_proposal_is_retried_not_skipped() -> None:
    # The tool raises ModelRetry for a value it cannot match, so no reply
    # carries resolved params. Marching on would build an empty strategy.
    spec = single_spec(_PLASMO)
    crit = spec.criteria[0]
    discovery = frame_call(spec, frozenset(), [], "")
    sheet_call = frame_call(spec, _called(discovery), [], "")
    replies = [_reply(crit, ["organism"])]
    proposal = frame_call(spec, _called(discovery, sheet_call), replies, "")

    again = frame_call(spec, _called(discovery, sheet_call, proposal), replies, "")

    assert again.tool_name == "set_criterion"
    assert again.args_as_dict()["criterion_id"] == crit.criterion_id
    assert again.args_as_dict()["params"] == {"organism": [_PF]}


def test_structure_follows_once_every_criterion_is_bound() -> None:
    spec = union_spec(_PLASMO)
    discovery = frame_call(spec, frozenset(), [], "")
    replies = [_bound(c) for c in spec.criteria]

    assert (
        frame_call(spec, _called(discovery), replies, "").tool_name == "set_structure"
    )


def test_the_frame_result_follows_the_structure() -> None:
    spec = union_spec(_PLASMO)
    discovery = frame_call(spec, frozenset(), [], "")
    replies = [_bound(c) for c in spec.criteria]
    structure = frame_call(spec, _called(discovery), replies, "")

    assert (
        frame_call(spec, _called(discovery, structure), replies, "").tool_name
        == "final_result"
    )


def test_the_go_criterion_carries_the_vocabulary_half_only() -> None:
    # go_term and go_typeahead are ORed halves of one criterion; a proposal
    # that fills both is refused by set_criterion.
    for spec in (go_spec(_PLASMO), combined_spec(_PLASMO)):
        go = next(c for c in spec.criteria if c.search_name == "GenesByGoTerm")

        assert go.values["go_typeahead"] == ["GO:0004672"]
        assert go.values["go_term"] is None


# ── Reading the tool's reply back ───────────────────────────────────


def _run(part: ToolReturnPart) -> list[ModelMessage]:
    return [ModelRequest(parts=[part])]


def test_a_real_set_criterion_result_parses_into_a_reply() -> None:
    result = SetCriterionResult(
        criterion_id="c1",
        search_name="GenesByTaxon",
        params_template={"organism": None},
    )
    part = ToolReturnPart(
        tool_name="set_criterion", content=result, tool_call_id="call-1"
    )

    (reply,) = criterion_replies(_run(part))

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

    (reply,) = criterion_replies(_run(part))

    assert reply.resolved_params == {"organism": '["x"]'}


def test_a_compacted_reply_yields_no_reply() -> None:
    part = ToolReturnPart(
        tool_name="set_criterion", content="no entry matching", tool_call_id="call-1"
    )

    assert criterion_replies(_run(part)) == []


def test_a_reply_of_another_shape_fails() -> None:
    part = ToolReturnPart(
        tool_name="set_criterion",
        content={"criterionId": "c1", "paramsTemplate": 5},
        tool_call_id="call-1",
    )

    with pytest.raises(ValidationError, match="paramsTemplate"):
        criterion_replies(_run(part))


def test_another_tool_s_return_is_ignored() -> None:
    part = ToolReturnPart(
        tool_name="set_structure", content={"criteriaCombined": 2}, tool_call_id="s-1"
    )

    assert criterion_replies(_run(part)) == []


# ── The structure call ──────────────────────────────────────────────


@pytest.mark.parametrize("spec", _SPECS)
def test_the_structure_call_is_a_tree_over_the_specs_criteria(spec: SpecPlan) -> None:
    root = StructureNode.model_validate(set_structure_args(spec)["root"])

    assert sorted(_criterion_ids(root)) == sorted(c.criterion_id for c in spec.criteria)


def test_the_two_leaf_spec_unions_its_leaves() -> None:
    root = StructureNode.model_validate(set_structure_args(union_spec(_PLASMO))["root"])

    assert root.kind == "combine"
    assert root.operator == CombineOp.UNION
    assert [n.kind for n in root.inputs] == ["leaf", "leaf"]


def test_the_all_param_spec_nests_a_union_inside_an_intersect() -> None:
    root = StructureNode.model_validate(
        set_structure_args(combined_spec(_PLASMO))["root"]
    )

    assert root.operator == CombineOp.INTERSECT
    assert root.inputs[0].operator == CombineOp.UNION
    assert root.inputs[1].kind == "leaf"


@pytest.mark.parametrize("spec", _SPECS)
def test_every_spec_names_a_search_for_every_criterion(spec: SpecPlan) -> None:
    assert all(c.search_name for c in spec.criteria)


def _criterion_ids(node: StructureNode) -> list[str]:
    own = [node.criterion_id] if node.criterion_id else []
    return own + [cid for child in node.inputs for cid in _criterion_ids(child)]
