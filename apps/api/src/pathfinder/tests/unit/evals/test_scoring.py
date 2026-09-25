"""Structural signatures and the named differences a failing case reports."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome
from pathfinder.evals.distance import tree_from_ast, tree_from_signature
from pathfinder.evals.scoring import ObservedOutcome, score_case, structure_signature


def _leaf(search_name: str) -> StrategyStepNode:
    return StrategyStepNode(search_name=search_name)


def _combine(
    left: StrategyStepNode,
    op: CombineOp,
    right: StrategyStepNode,
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="__combine__",
        primary_input=left,
        secondary_input=right,
        operator=op,
    )


def _ast(root: StrategyStepNode) -> StrategyAst:
    return StrategyAst(record_type="transcript", root=root)


def test_a_single_search_signs_as_its_search_name() -> None:
    assert structure_signature(_ast(_leaf("GenesByText"))) == "GenesByText"


def test_a_combine_signs_as_an_operator_between_its_inputs() -> None:
    tree = _combine(_leaf("GenesByText"), CombineOp.INTERSECT, _leaf("GenesByGoTerm"))

    assert structure_signature(_ast(tree)) == "(GenesByText INTERSECT GenesByGoTerm)"


def test_a_transform_signs_as_a_call_on_its_input() -> None:
    tree = StrategyStepNode(search_name="GenesByOrthologs", primary_input=_leaf("A"))

    assert structure_signature(_ast(tree)) == "GenesByOrthologs(A)"


def test_step_ids_do_not_reach_the_signature() -> None:
    """Two builds of the same shape sign the same, so ids cannot fail a case."""
    one = _ast(_combine(_leaf("A"), CombineOp.UNION, _leaf("B")))
    other = _ast(_combine(_leaf("A"), CombineOp.UNION, _leaf("B")))

    assert one.root.id != other.root.id
    assert structure_signature(one) == structure_signature(other)


def _case(expected: ExpectedOutcome) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["build something"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins a thing",
        expected=expected,
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-08-23",
        ),
    )


def test_a_case_that_forbids_a_build_passes_when_none_happened() -> None:
    case = _case(ExpectedOutcome(builds_strategy=False))
    observed = ObservedOutcome(built_strategy=False, reply_text="stored it")

    score = score_case(case, observed)

    assert score.passed
    assert score.differences == []


def test_a_case_that_forbids_a_build_names_the_structure_it_got() -> None:
    case = _case(ExpectedOutcome(builds_strategy=False))
    observed = ObservedOutcome(
        built_strategy=True,
        structure="(A INTERSECT B)",
        reply_text="built it",
    )

    score = score_case(case, observed)

    assert not score.passed
    assert [(d.field, d.actual) for d in score.differences] == [
        ("builtStrategy", "(A INTERSECT B)"),
    ]


def test_a_structure_mismatch_reports_both_sides() -> None:
    case = _case(
        ExpectedOutcome(builds_strategy=True, structure="(A INTERSECT B)"),
    )
    observed = ObservedOutcome(
        built_strategy=True,
        structure="(A UNION B)",
        reply_text="",
    )

    score = score_case(case, observed)

    assert not score.passed
    difference = score.differences[0]
    assert difference.field == "structure"
    assert difference.expected == "(A INTERSECT B)"
    assert difference.actual == "(A UNION B)"


def test_an_unstated_expectation_is_not_compared() -> None:
    case = _case(ExpectedOutcome(builds_strategy=True, structure="(A INTERSECT B)"))
    observed = ObservedOutcome(
        built_strategy=True,
        structure="(A INTERSECT B)",
        record_type="transcript",
        step_count=3,
        verified=True,
        reply_text="",
    )

    assert score_case(case, observed).passed


def test_a_required_phrase_missing_from_the_reply_fails_the_case() -> None:
    case = _case(
        ExpectedOutcome(builds_strategy=False, reply_mentions=["remember"]),
    )
    observed = ObservedOutcome(built_strategy=False, reply_text="Done.")

    score = score_case(case, observed)

    assert not score.passed
    assert score.differences[0].field == "replyMentions"


def test_a_forbidden_phrase_present_in_the_reply_fails_the_case() -> None:
    case = _case(
        ExpectedOutcome(builds_strategy=False, reply_omits=["Verified end-to-end"]),
    )
    observed = ObservedOutcome(
        built_strategy=False,
        reply_text="**Verified end-to-end.** all good",
    )

    score = score_case(case, observed)

    assert not score.passed
    assert score.differences[0].field == "replyOmits"


def test_phrase_checks_ignore_case() -> None:
    case = _case(ExpectedOutcome(builds_strategy=False, reply_mentions=["CLARIFY"]))
    observed = ObservedOutcome(built_strategy=False, reply_text="let me clarify")

    assert score_case(case, observed).passed


def test_every_difference_is_reported_not_only_the_first() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            structure="(A INTERSECT B)",
            step_count=3,
            verified=True,
        ),
    )
    observed = ObservedOutcome(
        built_strategy=True,
        structure="(A UNION B)",
        step_count=5,
        verified=False,
        reply_text="",
    )

    fields = [d.field for d in score_case(case, observed).differences]

    assert fields == ["structure", "stepCount", "verified"]


def test_a_case_that_wants_the_step_ids_kept_fails_when_they_moved() -> None:
    case = _case(ExpectedOutcome(builds_strategy=True, step_ids_unchanged=True))
    observed = ObservedOutcome(
        built_strategy=True,
        step_ids_unchanged=False,
        reply_text="rebuilt it",
    )

    score = score_case(case, observed)

    assert not score.passed
    difference = score.differences[0]
    assert difference.field == "stepIdsUnchanged"
    assert (difference.expected, difference.actual) == ("True", "False")


def test_a_case_that_wants_the_step_ids_kept_passes_when_they_held() -> None:
    case = _case(ExpectedOutcome(builds_strategy=True, step_ids_unchanged=True))
    observed = ObservedOutcome(
        built_strategy=True,
        step_ids_unchanged=True,
        reply_text="patched one step",
    )

    assert score_case(case, observed).passed


def test_an_unobserved_step_id_answer_fails_a_case_that_asked_for_one() -> None:
    """Nothing was built before the last turn, so the case cannot be satisfied."""
    case = _case(ExpectedOutcome(builds_strategy=True, step_ids_unchanged=True))
    observed = ObservedOutcome(built_strategy=True, reply_text="")

    score = score_case(case, observed)

    assert not score.passed
    assert score.differences[0].actual == "None"


def test_a_named_parameter_the_run_changed_is_reported() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            structure="GenesByTaxon",
            parameters={"GenesByTaxon": {"organism": "Plasmodium vivax P01"}},
        ),
    )
    observed = ObservedOutcome(
        built_strategy=True,
        structure="GenesByTaxon",
        tree=tree_from_ast(
            _ast(
                StrategyStepNode(
                    search_name="GenesByTaxon",
                    parameters={
                        "organism": MultiPickValue(values=["Plasmodium falciparum 3D7"])
                    },
                )
            )
        ),
        reply_text="",
    )

    score = score_case(case, observed)

    assert not score.passed
    difference = score.differences[0]
    assert difference.field == "parameters.GenesByTaxon.organism"
    assert difference.expected == "Plasmodium vivax P01"
    assert difference.actual == "Plasmodium falciparum 3D7"


def test_a_named_parameter_the_run_kept_passes() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            structure="GenesByTaxon",
            parameters={"GenesByTaxon": {"organism": "Plasmodium vivax P01"}},
        ),
    )
    observed = ObservedOutcome(
        built_strategy=True,
        structure="GenesByTaxon",
        tree=tree_from_ast(
            _ast(
                StrategyStepNode(
                    search_name="GenesByTaxon",
                    parameters={
                        "organism": MultiPickValue(values=["Plasmodium vivax P01"])
                    },
                )
            )
        ),
        reply_text="",
    )

    assert score_case(case, observed).passed


def _transform(syntenic: str, over: StrategyStepNode) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="GenesByOrthologs",
        parameters={"isSyntenic": MultiPickValue(values=[syntenic])},
        primary_input=over,
    )


def test_every_step_of_a_named_search_is_held_to_the_value() -> None:
    """A round trip runs the transform twice; each leg carries the parameter."""
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            parameters={"GenesByOrthologs": {"isSyntenic": "yes"}},
        ),
    )
    observed = ObservedOutcome(
        built_strategy=True,
        tree=tree_from_ast(
            _ast(_transform("no", _transform("yes", _leaf("GenesByTaxon"))))
        ),
        reply_text="",
    )

    score = score_case(case, observed)

    assert [(d.field, d.expected, d.actual) for d in score.differences] == [
        ("parameters.GenesByOrthologs.isSyntenic", "yes", "no")
    ]


def test_the_score_carries_the_distance_when_both_shapes_are_known() -> None:
    case = _case(
        ExpectedOutcome(
            builds_strategy=True,
            structure="(A UNION B)",
        ),
    )
    observed = ObservedOutcome(
        built_strategy=True,
        structure="(A INTERSECT B)",
        tree=tree_from_signature("(A INTERSECT B)"),
        reply_text="",
    )

    score = score_case(case, observed)

    assert score.distance is not None
    assert score.distance.topology == 0.0
    assert score.distance.labelled == 0.1


def test_a_run_that_built_nothing_carries_no_distance() -> None:
    case = _case(ExpectedOutcome(builds_strategy=False))
    observed = ObservedOutcome(built_strategy=False, reply_text="stored it")

    assert score_case(case, observed).distance is None
