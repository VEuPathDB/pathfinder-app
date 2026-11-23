"""An edit is measured against the spec the strategy realizes."""

from __future__ import annotations

import pytest
from veupathdb.domain.parameters import (
    HeldValue,
    MultiPickValue,
    NumberValue,
    ParamValue,
    StringValue,
)
from veupathdb.domain.strategy import CombineOp, StrategyStepNode

from strategist.ai.agents.execution import build_execution_agent
from strategist.ai.lead.lead_agent import build_lead_agent
from strategist.domain.refusal import Problems
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    PercentileValue,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
)
from strategist.domain.strategy.session import StrategyGraph
from strategist.domain.strategy.spec_edit_guard import (
    JoinContradiction,
    ValueContradiction,
    contradicted_joins,
    contradicted_values,
    new_join_contradictions,
    new_value_contradictions,
    spec_stated_values,
    stated_values,
)
from strategist.tests._support.bound_values import bound
from strategist.tests._support.tool_names import foreign_names

from ._builders import combine, graph_of, leaf, spec_joined, spec_leaf

_TM = "step_4f51bc4f"
_SIGNAL = "step_044e4c5c"
_PROFILE = "step_4951705a"
_MIC2 = "step_780fd940"
_RON2 = "step_fb1f017c"
_SIMILARITY_JOIN = "step_7eca55ff"
_TM_JOIN = "step_79b8b72b"
_PROFILE_JOIN = "step_811d87da"
_ROOT = "step_95c8dca2"
_EXPR = "step_expr"

# The wire value FRAME built for the phyletic profile. No part of it is words
# the user said.
_PROFILE_PATTERN = "%bbes:Y%bbig:Y%btau:N%chom:Y%hsap:N%tgme:Y%"

_DEFAULTED = [
    "ProfileDistanceMethod",
    "ProfileMinPoints",
    "ProfileMissingPtsPercent",
    "ProfileNumToReturn",
    "ProfileScaleFactor",
    "ProfileSearchGoal",
    "profile_time_shift",
]


def _similarity(criterion_id: str, gene_id: str, label: str) -> Criterion:
    params: dict[str, ParamValue] = {
        "ProfileGeneId": StringValue(value=gene_id),
        "ProfileNumToReturn": StringValue(value="50"),
    }
    return Criterion(
        id=criterion_id,
        text=f"Cell-cycle microarray expression profile similar to {label} ({gene_id})",
        search_name="GenesByToxoProfileSimilarity",
        resolved_params=bound(params, defaulted=list(_DEFAULTED)),
    )


def _spec() -> OperationalSpec:
    """The five-criterion spec, joined the way ``set_structure`` declared it."""
    return OperationalSpec(
        goal="apicomplexan-specific invasion-like genes",
        criteria=[
            Criterion(
                id=_TM,
                text="At least one predicted transmembrane domain",
                search_name="GenesByTransmembraneDomains",
            ),
            Criterion(
                id=_SIGNAL,
                text="Predicted signal peptide",
                search_name="GenesWithSignalPeptide",
            ),
            Criterion(
                id=_PROFILE,
                text="Ortholog present in Apicomplexa and absent from Mammalia",
                search_name="GenesByOrthologPattern",
                resolved_params=bound(
                    {
                        "profile_pattern": StringValue(value=_PROFILE_PATTERN),
                        "included_species": StringValue(value="APIC"),
                        "excluded_species": StringValue(value="MAMM"),
                    }
                ),
            ),
            _similarity(_MIC2, "TGME49_201780", "MIC2"),
            _similarity(_RON2, "TGME49_300100", "RON2"),
        ],
        structure=SpecStructure(
            root=spec_joined(
                CombineOp.INTERSECT,
                spec_joined(CombineOp.UNION, spec_leaf(_TM), spec_leaf(_SIGNAL)),
                spec_joined(
                    CombineOp.INTERSECT,
                    spec_leaf(_PROFILE),
                    spec_joined(CombineOp.UNION, spec_leaf(_MIC2), spec_leaf(_RON2)),
                ),
            ),
        ),
    )


def _graph() -> StrategyGraph:
    """The strategy the spec built, one combine step per structure node."""
    return graph_of(
        combine(
            _ROOT,
            combine(_TM_JOIN, leaf(_TM), leaf(_SIGNAL), CombineOp.UNION),
            combine(
                _PROFILE_JOIN,
                leaf(_PROFILE),
                combine(_SIMILARITY_JOIN, leaf(_MIC2), leaf(_RON2), CombineOp.UNION),
            ),
        ),
    )


def _refusal_for(graph: StrategyGraph, spec: OperationalSpec) -> str | None:
    found = new_join_contradictions(
        structure=spec.structure,
        graph=graph,
        criteria=[c.id for c in spec.criteria],
        before={},
    )
    return found.text() or None


def test_a_combine_operator_the_spec_does_not_declare_is_refused() -> None:
    graph = _graph()
    graph.steps[_PROFILE_JOIN].operator = CombineOp.UNION

    refusal = _refusal_for(graph, _spec())

    assert refusal is not None
    assert "INTERSECT" in refusal
    assert "UNION" in refusal
    assert "framing pass" in refusal


def test_a_join_the_spec_does_not_reach_is_left_alone() -> None:
    """The tree the spec declares, a spec with no structure, and a spec whose
    criteria meet at no combine of it: none of the three is refused."""
    unstructured = _spec()
    unstructured.structure = None
    one_criterion = _spec()
    one_criterion.criteria = [c for c in one_criterion.criteria if c.id == _TM]
    flipped = _graph()
    flipped.steps[_TM_JOIN].operator = CombineOp.INTERSECT

    refusals = [
        _refusal_for(_graph(), _spec()),
        _refusal_for(_graph(), unstructured),
        _refusal_for(flipped, one_criterion),
    ]

    assert refusals == [None, None, None]


def test_a_join_that_already_contradicted_the_spec_is_not_refused_again() -> None:
    """The write answers for what it changes, not for what it found."""
    graph = _graph()
    graph.steps[_PROFILE_JOIN].operator = CombineOp.UNION
    spec = _spec()
    before = contradicted_joins(spec.structure, graph, [c.id for c in spec.criteria])

    assert list(before.values()) == [
        JoinContradiction(declared=CombineOp.INTERSECT, written=CombineOp.UNION)
    ]
    assert (
        new_join_contradictions(
            structure=spec.structure,
            graph=graph,
            criteria=[c.id for c in spec.criteria],
            before=before,
        )
        == Problems()
    )


def _with_value(
    graph: StrategyGraph, step_id: str, name: str, value: ParamValue
) -> StrategyGraph:
    graph.steps[step_id].parameters = {name: value}
    return graph


def _values_refusal(graph: StrategyGraph, spec: OperationalSpec) -> str | None:
    found = new_value_contradictions(
        stated=spec_stated_values(spec), graph=graph, before={}, after={}
    )
    return found.text() or None


def _with_percentile_criterion(spec: OperationalSpec, **params: ParamValue) -> None:
    """The user asked for a share of a ranked population; the bound realizes it."""
    top_10 = Constraint(
        kind=ConstraintKind.PERCENTILE,
        requested_value="top 10%",
        label="expression percentile",
        source=ConstraintSource.USER_EXPLICIT,
        value=PercentileValue(end="top", share=10),
    )
    spec.criteria.append(
        Criterion(
            id=_EXPR,
            text="Expressed in the schizont stage",
            search_name="GenesByRNASeqEvidence",
            resolved_params=bound(dict(params)),
            answers=[
                RequirementLink(
                    requirement=top_10.id, param="min_expression_percentile"
                )
            ],
        ),
    )
    spec.constraints = [top_10]


def _graph_with_expr() -> StrategyGraph:
    return graph_of(combine("step_expr_join", leaf(_EXPR), leaf(_TM)))


def test_a_value_the_spec_left_to_the_search_default_is_applied() -> None:
    spec = _spec()
    criterion = next(c for c in spec.criteria if c.id == _MIC2)
    graph = _with_value(_graph(), _MIC2, "ProfileNumToReturn", StringValue(value="100"))

    assert "ProfileNumToReturn" not in stated_values(spec, criterion)
    assert _values_refusal(graph, spec) is None


def test_a_value_frame_derived_is_applied() -> None:
    """The phyletic profile pattern is FRAME's own work, so recovery may fix it."""
    spec = _spec()
    criterion = next(c for c in spec.criteria if c.id == _PROFILE)
    graph = _with_value(
        _graph(), _PROFILE, "profile_pattern", StringValue(value="%hsap:N%tgme:Y%")
    )

    assert sorted(stated_values(spec, criterion)) == []
    assert _values_refusal(graph, spec) is None


def test_a_value_a_stated_requirement_grounds_onto_is_refused() -> None:
    spec = _spec()
    _with_percentile_criterion(spec, min_expression_percentile=NumberValue(value=90))
    graph = _with_value(
        _graph_with_expr(), _EXPR, "min_expression_percentile", NumberValue(value=80)
    )

    assert stated_values(spec, spec.criteria[-1]) == {"min_expression_percentile": "90"}
    refusal = _values_refusal(graph, spec)

    assert refusal is not None
    assert "min_expression_percentile" in refusal
    assert "'90'" in refusal


def test_a_stated_value_freezes_its_own_parameter_only() -> None:
    """Two parameters hold "90"; the requirement grounds onto one of them."""
    spec = _spec()
    _with_percentile_criterion(
        spec,
        min_expression_percentile=NumberValue(value=90),
        min_percent_identity=NumberValue(value=90),
    )
    graph = _with_value(
        _graph_with_expr(), _EXPR, "min_percent_identity", NumberValue(value=80)
    )

    assert stated_values(spec, spec.criteria[-1]) == {"min_expression_percentile": "90"}
    assert _values_refusal(graph, spec) is None


def test_a_step_no_criterion_names_is_left_alone() -> None:
    spec = _spec()
    graph = _with_value(
        _graph(), _TM, "ProfileGeneId", StringValue(value="TGME49_300100")
    )

    assert stated_values(spec, spec.criteria[0]) == {}
    assert _values_refusal(graph, spec) is None


def test_a_value_the_criterion_text_carries_is_not_stated() -> None:
    spec = _spec()
    criterion = next(c for c in spec.criteria if c.id == _MIC2)
    graph = _with_value(
        _graph(), _MIC2, "ProfileGeneId", StringValue(value="TGME49_300100")
    )

    assert stated_values(spec, criterion) == {}
    assert _values_refusal(graph, spec) is None


def test_a_value_that_already_departed_is_not_refused_again() -> None:
    """The write answers for what it changes, not for what it found."""
    spec = _spec()
    _with_percentile_criterion(spec, min_expression_percentile=NumberValue(value=90))
    graph = _with_value(
        _graph_with_expr(), _EXPR, "min_expression_percentile", NumberValue(value=80)
    )
    before = contradicted_values(spec_stated_values(spec), graph, {})

    assert [found.parameter for found in before.values()] == [
        "min_expression_percentile"
    ]
    assert (
        new_value_contradictions(
            stated=spec_stated_values(spec), graph=graph, before=before, after={}
        )
        == Problems()
    )


def test_a_value_the_spec_states_and_the_edit_repeats_is_applied() -> None:
    spec = _spec()
    _with_percentile_criterion(spec, min_expression_percentile=NumberValue(value=90))
    graph = _with_value(
        _graph_with_expr(), _EXPR, "min_expression_percentile", NumberValue(value=90)
    )

    assert (stated_values(spec, spec.criteria[-1]), _values_refusal(graph, spec)) == (
        {"min_expression_percentile": "90"},
        None,
    )


def _departure(stated: ParamValue, written: ParamValue) -> ValueContradiction:
    return ValueContradiction(
        criterion_text="expressed in trophozoites",
        parameter="p",
        stated=stated,
        written=written,
    )


@pytest.mark.parametrize(
    ("stated", "before", "after"),
    [
        (NumberValue(value=90), HeldValue(wire="80.0"), NumberValue(value=80)),
        (
            MultiPickValue(values=["a"]),
            MultiPickValue(values=["b", "c"]),
            MultiPickValue(values=["c", "b"]),
        ),
    ],
    ids=["number-spelling", "pick-order"],
)
def test_a_departure_held_in_another_writing_is_the_same_departure(
    stated: ParamValue, before: ParamValue, after: ParamValue
) -> None:
    assert _departure(stated, after).repeats(_departure(stated, before))


def test_a_string_parameter_holds_two_spellings_of_a_number_apart() -> None:
    stated = StringValue(value="x")

    assert not _departure(stated, StringValue(value="80")).repeats(
        _departure(stated, StringValue(value="80.0"))
    )


def test_a_contradicting_write_names_the_framing_pass() -> None:
    joined = _graph()
    joined.steps[_PROFILE_JOIN].operator = CombineOp.UNION
    spec = _spec()
    _with_percentile_criterion(spec, min_expression_percentile=NumberValue(value=90))
    valued = _with_value(
        _graph_with_expr(), _EXPR, "min_expression_percentile", NumberValue(value=80)
    )
    refusals = [_refusal_for(joined, _spec()), _values_refusal(valued, spec)]

    for refusal in refusals:
        assert refusal is not None
        assert "framing pass" in refusal
        assert foreign_names(refusal, build_lead_agent()) == []
        assert foreign_names(refusal, build_execution_agent()) == []


def test_a_mirrored_join_with_its_sides_swapped_states_the_spec() -> None:
    graph = graph_of(combine("step_root", leaf("c_k"), leaf("c_e"), CombineOp.RMINUS))
    structure = SpecStructure(
        root=spec_joined(CombineOp.MINUS, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {}


def test_a_mirrored_join_on_the_same_sides_departs_from_the_spec() -> None:
    graph = graph_of(combine("step_root", leaf("c_e"), leaf("c_k"), CombineOp.RMINUS))
    structure = SpecStructure(
        root=spec_joined(CombineOp.MINUS, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {
        frozenset({"c_e", "c_k"}): JoinContradiction(
            declared=CombineOp.MINUS, written=CombineOp.RMINUS
        )
    }


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
def test_a_one_sided_join_over_swapped_sides_departs_from_the_spec(
    operator: CombineOp,
) -> None:
    graph = graph_of(combine("step_root", leaf("c_k"), leaf("c_e"), operator))
    structure = SpecStructure(
        root=spec_joined(operator, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {
        frozenset({"c_e", "c_k"}): JoinContradiction(
            declared=operator, written=operator
        )
    }


def test_a_symmetric_join_over_swapped_sides_states_the_spec() -> None:
    graph = graph_of(
        combine("step_root", leaf("c_k"), leaf("c_e"), CombineOp.INTERSECT)
    )
    structure = SpecStructure(
        root=spec_joined(CombineOp.INTERSECT, spec_leaf("c_e"), spec_leaf("c_k"))
    )

    assert contradicted_joins(structure, graph, ["c_e", "c_k"]) == {}


def _folded(operator: CombineOp, ids: list[str]) -> StrategyStepNode:
    tree = leaf(ids[0])
    for index, criterion_id in enumerate(ids[1:]):
        tree = combine(f"step_join_{index}", tree, leaf(criterion_id), operator)
    return tree


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
@pytest.mark.parametrize("count", [2, 3, 4])
def test_a_one_sided_join_over_many_inputs_folded_left_states_the_spec(
    operator: CombineOp, count: int
) -> None:
    ids = [f"c_{index}" for index in range(count)]
    structure = SpecStructure(root=spec_joined(operator, *(spec_leaf(i) for i in ids)))

    assert contradicted_joins(structure, graph_of(_folded(operator, ids)), ids) == {}


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
def test_a_one_sided_join_over_many_inputs_reversed_departs_from_the_spec(
    operator: CombineOp,
) -> None:
    ids = ["c_0", "c_1", "c_2"]
    reversed_tree = combine(
        "step_root",
        leaf("c_2"),
        combine("step_inner", leaf("c_0"), leaf("c_1"), operator),
        operator,
    )
    structure = SpecStructure(root=spec_joined(operator, *(spec_leaf(i) for i in ids)))

    assert contradicted_joins(structure, graph_of(reversed_tree), ids) == {
        frozenset(ids): JoinContradiction(declared=operator, written=operator)
    }
