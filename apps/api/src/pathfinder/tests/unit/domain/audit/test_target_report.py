"""The counts a run's gene targets give each genome they judged, kept apart from the sampled rates."""

from __future__ import annotations

from pathfinder.domain.audit.findings import ErrorType, FindingStatus
from pathfinder.domain.audit.rates import (
    TargetFinding,
    TargetReport,
    TargetTally,
    Unresolved,
    target_report,
)

P3D7 = "Plasmodium falciparum 3D7"
DD2 = "Plasmodium falciparum Dd2"


def _pair(
    error_type: ErrorType | None,
    model: str,
    *,
    status: FindingStatus = "confirmed",
    judged: bool = True,
) -> TargetFinding:
    return TargetFinding(
        check="strain_model",
        status=status,
        error_type=error_type,
        judged=judged,
        model_genome=model,
        judged_genomes=(DD2, P3D7),
    )


def test_a_strain_pair_counts_in_both_genomes_and_its_error_in_the_model_genome() -> (
    None
):
    report = target_report(
        [
            _pair("truncated_model", DD2),
            _pair(None, DD2),
            _pair("over_extended_model", P3D7),
            _pair("over_extended_model", P3D7),
        ]
    )
    assert report == TargetReport(
        genomes=[
            TargetTally(
                genome=P3D7,
                check="strain_model",
                checked=4,
                errors=2,
                unjudged=0,
                unresolved_by_status=Unresolved(),
            ),
            TargetTally(
                genome=DD2,
                check="strain_model",
                checked=4,
                errors=1,
                unjudged=0,
                unresolved_by_status=Unresolved(),
            ),
        ],
        unplaced=0,
    )


def test_unjudged_unresolved_and_unplaced_targets_are_counted_apart() -> None:
    unplaced = TargetFinding(
        check="gene_length",
        status="failed",
        error_type=None,
        judged=True,
        model_genome="",
        judged_genomes=("",),
    )
    report = target_report(
        [_pair(None, DD2, judged=False), _pair(None, "", status="unreached"), unplaced]
    )
    assert [
        (t.genome, t.checked, t.unjudged, t.unresolved) for t in report.genomes
    ] == [
        (P3D7, 0, 1, 1),
        (DD2, 0, 1, 1),
    ]
    assert report.unplaced == 1


def test_a_remodeled_target_counts_its_error_in_the_genome_that_holds_it() -> None:
    vivax = "Plasmodium vivax P01"
    remodeled = TargetFinding(
        check="gene_length",
        status="confirmed",
        error_type="over_extended_model",
        judged=True,
        model_genome=vivax,
        judged_genomes=(DD2, vivax),
    )
    assert [
        (t.genome, t.checked, t.errors) for t in target_report([remodeled]).genomes
    ] == [(DD2, 1, 0), (vivax, 1, 1)]


def test_a_target_left_unread_is_unresolved_under_its_status() -> None:
    (tally,) = target_report(
        [
            TargetFinding(
                check="gene_length",
                status="unread",
                error_type=None,
                judged=True,
                model_genome=DD2,
                judged_genomes=(DD2,),
            )
        ]
    ).genomes
    assert (tally.genome, tally.unresolved_by_status, tally.unresolved) == (
        DD2,
        Unresolved(unread=1),
        1,
    )
