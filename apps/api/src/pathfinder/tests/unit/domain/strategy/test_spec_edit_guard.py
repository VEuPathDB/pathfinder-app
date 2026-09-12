"""An edit is measured against the spec the strategy realizes."""

from __future__ import annotations

from veupathdb.domain.parameters import NumberValue, ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
)
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.spec_edit_guard import (
    JoinContradiction,
    contradicted_joins,
    new_join_contradiction,
    stated_values,
    value_contradiction,
)

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
        resolved_params=params,
        defaulted_params=list(_DEFAULTED),
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
                resolved_params={
                    "profile_pattern": StringValue(value=_PROFILE_PATTERN),
                    "included_species": StringValue(value="APIC"),
                    "excluded_species": StringValue(value="MAMM"),
                },
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
    return new_join_contradiction(
        structure=spec.structure,
        graph=graph,
        criteria=[c.id for c in spec.criteria],
        before={},
    )


def test_a_combine_operator_the_spec_does_not_declare_is_refused() -> None:
    graph = _graph()
    graph.steps[_PROFILE_JOIN].operator = CombineOp.UNION

    refusal = _refusal_for(graph, _spec())

    assert refusal is not None
    assert "INTERSECT" in refusal
    assert "UNION" in refusal
    assert "set_structure" in refusal
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
        new_join_contradiction(
            structure=spec.structure,
            graph=graph,
            criteria=[c.id for c in spec.criteria],
            before=before,
        )
        is None
    )


def test_a_value_the_criterion_states_is_refused() -> None:
    refusal = value_contradiction(
        _spec(),
        step_id=_MIC2,
        parameters={"ProfileGeneId": StringValue(value="TGME49_300100")},
    )

    assert refusal is not None
    assert "ProfileGeneId" in refusal
    assert "TGME49_201780" in refusal
    assert "set_criterion" in refusal


def test_a_value_the_spec_left_to_the_search_default_is_applied() -> None:
    spec = _spec()
    criterion = next(c for c in spec.criteria if c.id == _MIC2)

    assert "ProfileNumToReturn" not in stated_values(spec, criterion)
    assert (
        value_contradiction(
            spec,
            step_id=_MIC2,
            parameters={"ProfileNumToReturn": StringValue(value="100")},
        )
        is None
    )


def test_a_value_frame_derived_is_applied() -> None:
    """The phyletic profile pattern is FRAME's own work, so recovery may fix it."""
    spec = _spec()
    criterion = next(c for c in spec.criteria if c.id == _PROFILE)

    assert sorted(stated_values(spec, criterion)) == []
    assert (
        value_contradiction(
            spec,
            step_id=_PROFILE,
            parameters={"profile_pattern": StringValue(value="%hsap:N%tgme:Y%")},
        )
        is None
    )


def test_a_value_a_stated_requirement_grounds_onto_is_refused() -> None:
    """The user asked for a share of a ranked population; the bound realizes it."""
    spec = _spec()
    spec.criteria.append(
        Criterion(
            id="step_expr",
            text="Expressed in the schizont stage",
            search_name="GenesByRNASeqEvidence",
            resolved_params={"min_expression_percentile": NumberValue(value=90)},
        ),
    )
    spec.constraints = [
        Constraint(
            kind=ConstraintKind.PERCENTILE,
            requested_value="top 10%",
            label="expression percentile",
            source=ConstraintSource.USER_EXPLICIT,
        ),
    ]
    criterion = spec.criteria[-1]

    assert stated_values(spec, criterion) == {"min_expression_percentile": "90"}
    refusal = value_contradiction(
        spec,
        step_id="step_expr",
        parameters={"min_expression_percentile": NumberValue(value=80)},
    )

    assert refusal is not None
    assert "min_expression_percentile" in refusal
    assert "'90'" in refusal


def test_a_stated_value_freezes_its_own_parameter_only() -> None:
    """Two parameters hold "90"; the requirement grounds onto one of them."""
    spec = _spec()
    spec.criteria.append(
        Criterion(
            id="step_expr",
            text="Expressed in the schizont stage",
            search_name="GenesByRNASeqEvidence",
            resolved_params={
                "min_expression_percentile": NumberValue(value=90),
                "min_percent_identity": NumberValue(value=90),
            },
        ),
    )
    spec.constraints = [
        Constraint(
            kind=ConstraintKind.PERCENTILE,
            requested_value="top 10%",
            label="expression percentile",
            source=ConstraintSource.USER_EXPLICIT,
        ),
    ]

    assert stated_values(spec, spec.criteria[-1]) == {"min_expression_percentile": "90"}
    assert (
        value_contradiction(
            spec,
            step_id="step_expr",
            parameters={"min_percent_identity": NumberValue(value=80)},
        )
        is None
    )


def test_a_value_the_spec_states_and_the_edit_repeats_is_applied() -> None:
    spec = _spec()
    criterion = next(c for c in spec.criteria if c.id == _MIC2)

    assert stated_values(spec, criterion)["ProfileGeneId"] == "TGME49_201780"
    assert (
        value_contradiction(
            spec,
            step_id=_MIC2,
            parameters={"ProfileGeneId": StringValue(value="TGME49_201780")},
        )
        is None
    )


def test_a_step_no_criterion_names_is_left_alone() -> None:
    spec = _spec()

    assert [c.id for c in spec.criteria] == [_TM, _SIGNAL, _PROFILE, _MIC2, _RON2]
    assert (
        value_contradiction(
            spec,
            step_id="step_elsewhere",
            parameters={"ProfileGeneId": StringValue(value="TGME49_300100")},
        )
        is None
    )
