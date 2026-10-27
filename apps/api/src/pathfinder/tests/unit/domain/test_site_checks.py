from __future__ import annotations

import pytest
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.validation import StepValidation

from pathfinder.domain.requirement_checks import grounded_check
from pathfinder.domain.site_checks import (
    CountedOrganisms,
    HeldValue,
    JoinedCounts,
    OrganismCount,
    SiteCheck,
    SiteCheckGap,
    SiteStep,
    UnreadOrganisms,
    bound_values_check,
    combine_counts_check,
    failed,
    organism_check,
    result_count_check,
    tally_checks,
    unanswered_checks,
    unanswered_columns,
    validity_check,
)
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    GroundedConstraint,
)
from pathfinder.domain.strategy.organism_phrases import names_the_organism
from pathfinder.domain.tally_facts import TallyFact
from pathfinder.tests._support.qa_recording import client_recording
from pathfinder.tests._support.recorded_counts import recorded_count
from pathfinder.tests._support.site_organisms import recorded_organisms

_RUNNABLE = StepValidation(level="RUNNABLE", is_valid=True)


def _step(wdk_step_id: int, count: int | None = 840, **site: object) -> SiteStep:
    return SiteStep.model_validate(
        {"title": "Signal", "wdkStepId": wdk_step_id, "count": count, **site}
    )


def test_a_step_the_site_marks_invalid_fails_with_its_messages() -> None:
    refused = StepValidation.model_validate(
        client_recording("refresh_with_a_value_outside_the_vocabulary").body
    )

    check = validity_check(
        [_step(11, validation=_RUNNABLE), _step(12, validation=refused)]
    )

    assert (check.status, check.evidence) == (
        "fail",
        (
            "the site marks 1 step invalid: step 12 ('Signal'): The passed changed "
            "param value 'Nope' is invalid."
        ),
    )


def test_steps_the_site_marks_valid_pass_and_unvalidated_ones_are_unchecked() -> None:
    unvalidated = StepValidation(level="NONE", is_valid=False)

    assert [
        (c.status, c.evidence)
        for c in (
            validity_check([_step(11, validation=_RUNNABLE), _step(12)]),
            validity_check([_step(12, validation=unvalidated)]),
        )
    ] == [
        ("pass", "the site marks 1 of 2 steps valid"),
        ("unchecked", "the site states the validity of no step"),
    ]


def test_a_value_the_site_holds_otherwise_fails_with_both_values() -> None:
    moved = HeldValue(
        step="step 11 ('Signal')",
        param="all_count",
        bound='{"min": 1.0, "max": 1.0}',
        site='{"min": 1.0, "max": 2.0}',
    )

    assert [
        (c.status, c.evidence)
        for c in (
            bound_values_check(1, [moved]),
            bound_values_check(2, []),
            bound_values_check(0, []),
        )
    ] == [
        (
            "fail",
            (
                "step 11 ('Signal') holds '{\"min\": 1.0, \"max\": 2.0}' for "
                'all_count, the spec binds \'{"min": 1.0, "max": 1.0}\''
            ),
        ),
        ("pass", "the site holds every value the spec binds on 2 search steps"),
        ("unchecked", "no step of the strategy binds a value to compare"),
    ]


def _joined(operator: CombineOp, joined: int | None) -> JoinedCounts:
    return JoinedCounts(
        title="Both",
        operator=operator,
        left=recorded_count("report_ortholog_tgon_all"),
        right=recorded_count("report_ortholog_tgon_no_exclusion"),
        joined=joined,
    )


@pytest.mark.parametrize(
    ("operator", "joined", "status"),
    [
        (CombineOp.INTERSECT, 484, "pass"),
        (CombineOp.INTERSECT, 485, "fail"),
        (CombineOp.UNION, 2408, "pass"),
        (CombineOp.UNION, 2407, "fail"),
        (CombineOp.UNION, 2893, "fail"),
        (CombineOp.MINUS, 0, "pass"),
        (CombineOp.MINUS, 485, "fail"),
        (CombineOp.RMINUS, 1924, "pass"),
        (CombineOp.RMINUS, 2409, "fail"),
        (CombineOp.INTERSECT, None, "unchecked"),
    ],
)
def test_a_combine_holds_a_count_its_operator_allows(
    operator: CombineOp, joined: int | None, status: str
) -> None:
    check = combine_counts_check([_joined(operator, joined)])

    assert check is not None
    assert check.status == status


def test_an_intersection_larger_than_its_smaller_input_names_the_counts() -> None:
    check = combine_counts_check([_joined(CombineOp.INTERSECT, 600)])

    assert check is not None
    assert check.evidence == (
        "a count its operator cannot hold: INTERSECT 'Both' holds 600 from inputs "
        "of 484 and 2,408"
    )


def test_a_strategy_with_no_set_operation_has_no_combine_check() -> None:
    assert [
        combine_counts_check([]),
        combine_counts_check([_joined(CombineOp.COLOCATE, 12)]),
    ] == [None, None]


def test_the_result_count_passes_fails_on_none_and_waits_on_no_count() -> None:
    assert [
        (c.status, c.evidence)
        for c in (
            result_count_check(_step(11, count=4787)),
            result_count_check(_step(11, count=0)),
            result_count_check(_step(11, count=None)),
        )
    ] == [
        ("pass", "the result step 11 ('Signal') holds 4,787 records"),
        ("fail", "the result step 11 ('Signal') holds no record on the site"),
        ("unchecked", "the site did not count the result step"),
    ]


def _tally(wdk_step_id: int) -> TallyFact:
    return TallyFact(
        id="tally_a4cb04a0",
        title="Proteins by Taxon Code",
        record_noun="protein",
        total=523795,
        distinct=840,
        wdk_step_id=wdk_step_id,
    )


def test_a_tally_of_a_live_step_is_held_as_a_pass() -> None:
    [check] = tally_checks([_tally(227289050), _tally(1)], [227289040, 227289050])

    assert (check.subject, check.status, check.evidence) == (
        "Proteins by Taxon Code",
        "pass",
        "the site counted 523,795 proteins of step 227289050 over 840 values",
    )


def _counted(*rows: tuple[str, int], total: int | None = None) -> CountedOrganisms:
    counted = [OrganismCount(organism=o, count=n) for o, n in rows]
    return CountedOrganisms(
        step="step 11 ('Signal')",
        total=sum(n for _, n in rows) if total is None else total,
        rows=counted,
    )


def _pf(strain: str) -> str:
    [found] = [o for o in recorded_organisms("plasmodb") if o.endswith(strain)]
    return found


def test_a_record_of_an_organism_the_strategy_does_not_select_fails() -> None:
    selected = frozenset({_pf("falciparum 3D7")})
    found = _counted((_pf("falciparum 3D7"), 819), (_pf("falciparum IT"), 21))

    check = organism_check("P. falciparum 3D7", "organism:x", selected, found)

    assert (check.status, check.requirement, check.evidence) == (
        "fail",
        "organism:x",
        (
            "21 of the 840 records of step 11 ('Signal') hold organisms the strategy "
            "does not select: Plasmodium falciparum IT (21)"
        ),
    )


def test_a_species_selected_whole_holds_its_strains() -> None:
    found = _counted((_pf("falciparum 3D7"), 819), (_pf("falciparum IT"), 21))

    check = organism_check(
        "the organisms of the result",
        "",
        frozenset({"Plasmodium falciparum"}),
        found,
    )

    assert check.status == "pass"


def test_an_organism_count_the_site_cut_short_or_did_not_read_is_unchecked() -> None:
    selected = frozenset({_pf("falciparum 3D7")})

    refused = UnreadOrganisms(why="no_check", evidence="the site refused the column")
    unanswered = UnreadOrganisms(
        why="site_unanswered", evidence="the site did not answer the organism count"
    )
    cut = _counted((_pf("falciparum 3D7"), 800), total=840)

    assert [
        (check.status, check.why_unchecked, check.evidence)
        for check in (
            organism_check("x", "", selected, refused),
            organism_check("x", "", selected, unanswered),
            organism_check("x", "", None, None),
        )
    ] == [
        ("unchecked", "no_check", "the site refused the column"),
        ("unchecked", "site_unanswered", "the site did not answer the organism count"),
        (
            "unchecked",
            "no_check",
            "no step of the strategy selects the organism of its result",
        ),
    ]
    assert organism_check("x", "", selected, cut).why_unchecked == "no_check"


def test_a_check_is_unchecked_exactly_when_it_names_why() -> None:
    with pytest.raises(ValueError, match="names why"):
        SiteCheck(kind="tally", subject="x", status="unchecked", evidence="e")
    with pytest.raises(ValueError, match="names why"):
        SiteCheck(
            kind="tally",
            subject="x",
            status="pass",
            evidence="e",
            why_unchecked="no_check",
        )


def test_a_read_the_site_did_not_answer_is_unchecked_for_that_reason() -> None:
    checks = [
        *unanswered_checks("the site did not answer the strategy read"),
        unanswered_columns("step 11"),
        result_count_check(None),
    ]

    assert [(c.kind, c.site_unanswered) for c in checks] == [
        ("step_valid", True),
        ("bound_values", True),
        ("result_count", True),
        ("step_columns", True),
        ("result_count", True),
    ]
    assert checks[3].evidence == "the site did not answer the column read of step 11"


@pytest.mark.parametrize(
    ("words", "names"),
    [
        ("P. falciparum", True),
        ("Plasmodium", True),
        ("Plasmodium falciparum 3D7", True),
        ("falciparum", False),
        ("P. vivax", False),
    ],
)
def test_words_name_an_organism_by_its_leading_words(words: str, names: bool) -> None:
    assert names_the_organism(words, _pf("falciparum 3D7")) is names


def _grounded(
    status: ConstraintStatus,
    *,
    hard: bool = True,
    realized_value: str | None = None,
    note: str = "",
) -> SiteCheck:
    return grounded_check(
        GroundedConstraint(
            constraint=Constraint(
                kind=ConstraintKind.DATA_TYPE,
                requested_value="RNA-Seq",
                label="data type",
                source=ConstraintSource.USER_EXPLICIT,
                hard=hard,
            ),
            status=status,
            realized_value=realized_value,
            note=note,
        )
    )


def test_a_grounded_requirement_is_checked_by_how_the_spec_grounds_it() -> None:
    assert [
        (c.status, c.evidence)
        for c in (
            _grounded(ConstraintStatus.GROUNDED, realized_value="rna-seq"),
            _grounded(
                ConstraintStatus.SUBSTITUTED,
                realized_value="microarray",
                note="requested RNA-Seq but only microarray searches were selected",
            ),
            _grounded(ConstraintStatus.SUBSTITUTED, hard=False, note="soft"),
            _grounded(ConstraintStatus.PROVISIONAL),
        )
    ] == [
        ("pass", "the strategy states rna-seq"),
        ("fail", "requested RNA-Seq but only microarray searches were selected"),
        ("unchecked", "soft"),
        ("unchecked", "no check reads this requirement on the site"),
    ]


def test_only_a_failed_check_is_a_gap() -> None:
    held = _grounded(ConstraintStatus.GROUNDED, realized_value="rna-seq")
    missed = _grounded(ConstraintStatus.UNGROUNDABLE, note="no step runs on RNA-Seq")

    assert failed([held, missed]) == [SiteCheckGap(check=missed)]
