"""A genome's error rate with its interval, and the impact a named finding is ordered by."""

from __future__ import annotations

from typing import get_args

import pytest
from veupathdb_mcp.audit import GeneEvidence, rate_with_bounds

from pathfinder.domain.audit.findings import Certainty, FindingStatus, FindingTally
from pathfinder.domain.audit.rates import (
    CERTAINTY_WEIGHT,
    GenomeRate,
    GenomeUse,
    Importance,
    Unresolved,
    Weighing,
    genome_rates,
    impact,
    importance_of,
    use_by_role,
    use_of,
)
from pathfinder.tests._support.audit import NF54
from pathfinder.tests._support.audit_evidence import (
    K13_EVIDENCE,
    PIGA_EVIDENCE,
    UNCITED_EVIDENCE,
)

DD2 = "Plasmodium falciparum Dd2"


def _row(
    genome: str,
    status: FindingStatus,
    count: int,
    *,
    error: bool = False,
    judged: bool = True,
    check: str = "pseudogene_call",
) -> FindingTally:
    return FindingTally.model_validate(
        {
            "genome": genome,
            "check": check,
            "status": status,
            "error_type": "intact_gene_called_pseudogene" if error else None,
            "judged": judged,
            "model_genome": genome,
            "count": count,
        }
    )


def test_a_rate_counts_the_unchecked_candidates_into_its_floor_and_ceiling() -> None:
    tally = [
        _row(NF54, "confirmed", 15, error=True),
        _row(NF54, "confirmed", 21),
        _row(NF54, "unsampled", 61),
    ]
    (rate,) = genome_rates(tally)
    assert (rate.genome, rate.check) == (NF54, "pseudogene_call")
    assert rate.bounds is not None
    assert rate.bounds == rate_with_bounds(15, 36, 61)
    assert (rate.bounds.floor, rate.bounds.ceiling) == (15 / 97, 76 / 97)


def test_every_status_but_confirmed_is_unresolved() -> None:
    tally = [
        _row(NF54, "confirmed", 2, error=True),
        _row(NF54, "confirmed", 3),
        _row(NF54, "screened", 1),
        _row(NF54, "unsampled", 4),
        _row(NF54, "trying", 1),
        _row(NF54, "failed", 2),
        _row(NF54, "unreached", 3),
        _row(NF54, "unread", 5),
    ]
    (rate,) = genome_rates(tally)
    assert rate.bounds is not None
    assert (rate.bounds.confirmed, rate.bounds.checked, rate.bounds.unresolved) == (
        2,
        5,
        16,
    )


def test_a_finding_not_judged_is_out_of_the_rate_and_counted_beside_it() -> None:
    tally = [
        _row(NF54, "confirmed", 3, error=True),
        _row(NF54, "confirmed", 7),
        _row(NF54, "confirmed", 5, judged=False),
        _row(NF54, "unsampled", 2),
    ]
    (rate,) = genome_rates(tally)
    assert rate.bounds is not None
    assert rate.bounds == rate_with_bounds(3, 10, 2)
    assert rate.unjudged == 5
    assert (rate.bounds.rate, rate.bounds.floor) == (0.3, 3 / 12)
    assert round(rate.bounds.low, 4) == round(rate_with_bounds(3, 10, 0).low, 4)


def test_an_error_whose_model_is_another_genome_is_clean_in_the_screened_one() -> None:
    moved = FindingTally(
        genome=NF54,
        model_genome="Plasmodium vivax P01",
        check="gene_length",
        status="confirmed",
        error_type="over_extended_model",
        count=1,
        judged=True,
    )
    tally = [
        _row(NF54, "confirmed", 3, error=True, check="gene_length"),
        moved,
        _row(NF54, "confirmed", 6, check="gene_length"),
    ]
    (rate,) = genome_rates(tally)
    assert rate.bounds is not None
    assert rate.bounds == rate_with_bounds(3, 10, 0)
    assert (round(rate.bounds.low, 3), round(rate.bounds.high, 3)) == (0.108, 0.603)
    assert (moved.holds_error, tally[0].holds_error) == (False, True)


def test_a_check_with_no_judged_finding_has_no_rate() -> None:
    (rate,) = genome_rates(
        [_row(NF54, "confirmed", 4, judged=False), _row(NF54, "unsampled", 3)]
    )
    assert (rate.bounds, rate.unjudged, rate.unresolved) == (None, 4, 3)


def test_each_genome_and_check_has_its_own_rate_in_order() -> None:
    tally = [
        _row(NF54, "confirmed", 1, error=True, check="pseudogene_call"),
        _row(NF54, "confirmed", 4, check="gene_length"),
        _row(DD2, "unsampled", 7, check="gene_length"),
    ]
    assert genome_rates(tally) == [
        GenomeRate(
            genome=DD2,
            check="gene_length",
            bounds=None,
            unjudged=0,
            unresolved_by_status=Unresolved(unsampled=7),
        ),
        GenomeRate(
            genome=NF54,
            check="gene_length",
            bounds=rate_with_bounds(0, 4, 0),
            unjudged=0,
            unresolved_by_status=Unresolved(),
        ),
        GenomeRate(
            genome=NF54,
            check="pseudogene_call",
            bounds=rate_with_bounds(1, 1, 0),
            unjudged=0,
            unresolved_by_status=Unresolved(),
        ),
    ]


def test_the_unresolved_count_is_split_by_status() -> None:
    tally = [
        _row(NF54, "confirmed", 1, error=True),
        _row(NF54, "confirmed", 2),
        _row(NF54, "unreached", 1),
        _row(NF54, "unread", 1),
        _row(NF54, "unsampled", 1),
        _row(NF54, "failed", 2),
        _row(NF54, "declined", 1),
    ]
    (rate,) = genome_rates(tally)
    assert rate.unresolved_by_status == Unresolved(
        unsampled=1, failed=2, declined=1, unreached=1, unread=1
    )
    assert rate.unresolved == 6
    assert rate.bounds == rate_with_bounds(1, 3, 6)


def test_the_unresolved_split_names_every_status_but_confirmed() -> None:
    statuses = [status for status in get_args(FindingStatus) if status != "confirmed"]
    assert list(Unresolved.model_fields) == statuses


def test_an_unresolved_split_reads_on_the_wire_with_its_total() -> None:
    (rate,) = genome_rates([_row(NF54, "unread", 2), _row(NF54, "trying", 1)])
    wire = rate.model_dump(by_alias=True, mode="json")
    assert (wire["unresolved"], wire["unresolvedByStatus"]) == (
        3,
        {
            "screened": 0,
            "unsampled": 0,
            "trying": 1,
            "failed": 0,
            "declined": 0,
            "unreached": 0,
            "unread": 2,
            "total": 3,
        },
    )


@pytest.mark.parametrize(
    ("certainty", "weight"), [("high", 1.0), ("medium", 0.6), ("low", 0.3)]
)
def test_a_weighing_states_its_certainty_weight(certainty: str, weight: float) -> None:
    weighing = Weighing.model_validate(
        {
            "certainty": certainty,
            "importance": {"genes": ["PF3D7_1032400"], "source": "cited"},
            "use": {"genome": NF54, "source": "other_strain", "reference": False},
        }
    )
    assert (weighing.certainty_weight, weighing.impact) == (
        weight,
        round(weight * 0.5, 3),
    )


def test_a_rate_reads_on_the_wire_with_its_interval() -> None:
    (rate,) = genome_rates([_row(NF54, "confirmed", 1, error=True)])
    wire = rate.model_dump(by_alias=True, mode="json")
    bounds = wire["bounds"]
    assert wire["unjudged"] == 0
    assert (bounds["confirmed"], bounds["checked"], bounds["unresolved"]) == (1, 1, 0)
    assert (bounds["rate"], bounds["floor"], bounds["ceiling"]) == (1.0, 1.0, 1.0)
    assert round(bounds["low"], 4) == 0.2065
    assert bounds["high"] == 1.0


def test_impact_is_certainty_times_importance_times_use() -> None:
    assert impact("high", 1.0, 1.0) == 1.0
    assert impact("medium", 0.5, 1.0) == 0.3
    assert impact("low", 0.5, 0.5) == 0.075


@pytest.mark.parametrize(
    ("certainty", "weight"), [("high", 1.0), ("medium", 0.6), ("low", 0.3)]
)
def test_each_certainty_has_its_fixed_weight(
    certainty: Certainty, weight: float
) -> None:
    assert CERTAINTY_WEIGHT[certainty] == weight
    assert impact(certainty, 1.0, 1.0) == weight


@pytest.mark.parametrize(
    ("evidence", "source", "value"),
    [
        ((K13_EVIDENCE,), "cited", 1.0),
        ((PIGA_EVIDENCE,), "cited", 1.0),
        ((UNCITED_EVIDENCE.model_copy(update={"comments": 1}),), "cited", 1.0),
        ((UNCITED_EVIDENCE, K13_EVIDENCE), "cited", 1.0),
        ((UNCITED_EVIDENCE,), "uncited", 0.5),
        (None, "not_read", 0.5),
    ],
)
def test_a_gene_cited_or_commented_on_is_more_important(
    evidence: tuple[GeneEvidence, ...] | None, source: str, value: float
) -> None:
    importance = importance_of(["G1"], evidence)
    assert (importance.genes, importance.source, importance.value) == (
        ("G1",),
        source,
        value,
    )


@pytest.mark.parametrize(
    ("reference_strain", "source", "value"),
    [
        (True, "reference_strain", 1.0),
        (False, "other_strain", 0.5),
        (None, "unknown", 0.5),
    ],
)
def test_a_species_reference_strain_is_used_more_than_another_genome(
    reference_strain: bool | None, source: str, value: float
) -> None:
    use = use_of(NF54, reference_strain=reference_strain)
    assert (use.genome, use.source, use.value) == (NF54, source, value)


def test_a_strain_check_uses_its_model_role() -> None:
    assert (use_by_role(NF54, "reference").value, use_by_role(DD2, "strain").value) == (
        1.0,
        0.5,
    )


def test_a_weighing_names_its_inputs_and_their_sources() -> None:
    weighing = Weighing(
        certainty="medium",
        importance=Importance(genes=("G1",), source="not_read"),
        use=GenomeUse(genome=NF54, source="reference_strain", reference=True),
    )
    assert weighing.impact == 0.3
    assert weighing.model_dump(by_alias=True, mode="json") == {
        "certainty": "medium",
        "importance": {"genes": ["G1"], "source": "not_read", "value": 0.5},
        "use": {
            "genome": NF54,
            "source": "reference_strain",
            "reference": True,
            "value": 1.0,
        },
        "certaintyWeight": 0.6,
        "impact": 0.3,
    }
    assert Weighing.model_validate(weighing.model_dump(by_alias=True, mode="json")) == (
        weighing
    )
