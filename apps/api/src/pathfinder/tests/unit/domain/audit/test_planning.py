"""The planner's pure rules: the genome budget, the audited and comparison genomes, the estimate and the start card."""

from __future__ import annotations

from typing import get_args

import pytest

from pathfinder.domain.audit.findings import EvidenceKind
from pathfinder.domain.audit.planning import (
    AuditStartCard,
    PlanRequest,
    RefusedTarget,
    RunEstimate,
    ScopeProposal,
    SiteGenome,
    UnitCosts,
    audited_by_gap,
    comparison_for,
    estimate,
    genome_budget,
    reference_for,
    same_scope,
    screened_checks,
    start_card,
)
from pathfinder.domain.audit.scope import (
    MAX_COMPARISON_GENOMES,
    AuditScope,
    CheckName,
    GenePairTarget,
    MissingGeneTarget,
    OrganelleTarget,
    SingleGeneTarget,
)

STRAINS = tuple(f"Examplea alpha {letter}" for letter in "ABCDEFGHI")
ALPHA_R = "Examplea alpha R"
BETA_R = "Examplea beta R"
BETA_S = "Examplea beta S"
OUTGROUP = "Otherus gamma G"


def _genome(
    organism: str, *, reference: bool | None = False, gap: float | None = None
) -> SiteGenome:
    genus, epithet, _ = organism.split()
    return SiteGenome(
        organism=organism,
        genus=genus,
        species=f"{genus} {epithet}",
        reference_strain=reference,
        gap=gap,
    )


GENOMES = (
    _genome(BETA_S),
    *(_genome(name, gap=float(k + 1)) for k, name in enumerate(STRAINS)),
    _genome(ALPHA_R, reference=True),
    _genome(BETA_R, reference=True),
    _genome(OUTGROUP, reference=True),
)
LIST_TARGETS = (
    GenePairTarget(check="selenoprotein_end", genes=("EXA_0002", "EXR_0002")),
    SingleGeneTarget(check="gene_fusion", genes=("EXA_0003",)),
    GenePairTarget(check="strain_model", genes=("EXA_0004", "EXR_0004")),
    SingleGeneTarget(check="intron_support", genes=("EXA_0007",)),
)
MISSING = MissingGeneTarget(
    check="missing_gene", genes=("EXR_0005",), absent_organism=STRAINS[1]
)
TARGETS = (
    *LIST_TARGETS,
    MISSING,
    OrganelleTarget(
        check="organelle_join",
        genes=("EXA_0006",),
        organism=STRAINS[0],
        sequence_id="EXA_MT",
    ),
)
SCOPE = AuditScope(
    site_id="exampledb",
    genomes=STRAINS[:1],
    comparison=STRAINS[1:],
    checks=("gene_length", "gene_split"),
    targets=TARGETS,
    confirm_limit=5,
)


def _costs() -> UnitCosts:
    checks: tuple[CheckName, ...] = get_args(CheckName)
    kinds: tuple[EvidenceKind, ...] = get_args(EvidenceKind)
    return UnitCosts(
        collect_requests={"audited": 2, "comparison": 2},
        run_requests=3,
        confirm_requests=dict.fromkeys(checks, 4),
        evidence_requests={"confirmation": 0, "relatives": 1, "gene_evidence": 2},
        collect_seconds={"audited": 2.0, "comparison": 2.0},
        confirm_seconds=dict.fromkeys(checks, 2.0),
        confirm_store_reads={c: 5 if c == "intron_support" else 0 for c in checks},
        evidence_seconds=dict.fromkeys(kinds, 2.0),
    )


def test_the_budget_counts_the_reference_and_every_whole_genome_target() -> None:
    assert genome_budget(8, reference=ALPHA_R, targets=(), named=STRAINS) == 7
    absent = MISSING.model_copy(update={"absent_organism": BETA_S})
    assert genome_budget(8, reference=ALPHA_R, targets=(absent,), named=STRAINS) == 6
    assert genome_budget(8, reference=None, targets=(MISSING,), named=STRAINS) == 8
    assert genome_budget(1, reference=ALPHA_R, targets=(absent,), named=()) == 0


def test_nine_strains_with_a_pseudogene_screen_keep_seven() -> None:
    kept, left_out = audited_by_gap(STRAINS, GENOMES, budget=7)

    assert kept == tuple(reversed(STRAINS[2:]))
    assert left_out == STRAINS[:2]


def test_named_genomes_that_fit_keep_their_order() -> None:
    named = (STRAINS[3], STRAINS[0], STRAINS[5])

    assert audited_by_gap(named, GENOMES, budget=3) == (named, ())


def test_a_genome_without_a_gap_is_left_out_first() -> None:
    named = (BETA_S, BETA_R, STRAINS[0])

    assert audited_by_gap(named, GENOMES, budget=1) == ((STRAINS[0],), (BETA_R, BETA_S))


def test_an_audited_reference_is_not_its_own_reference() -> None:
    assert reference_for(STRAINS[:2], GENOMES) == (ALPHA_R, None)
    assert reference_for((STRAINS[0], ALPHA_R), GENOMES) == (
        None,
        "the named genomes include the species reference Examplea alpha R",
    )
    two = (*GENOMES, _genome("Examplea alpha Q", reference=True))
    assert reference_for(STRAINS[:1], two) == (
        None,
        "2 genomes of Examplea alpha are marked reference strains",
    )
    assert reference_for((STRAINS[0], BETA_S), GENOMES) == (
        None,
        "the named genomes span 2 species",
    )
    unmarked = tuple(g for g in GENOMES if g.organism != ALPHA_R)
    assert reference_for(STRAINS[:1], unmarked) == (
        None,
        "no genome of Examplea alpha is marked a reference strain",
    )


def test_the_comparison_puts_reference_strains_first() -> None:
    assert comparison_for(STRAINS[:1], ALPHA_R, GENOMES) == (
        ALPHA_R,
        BETA_R,
        *STRAINS[1:],
        BETA_S,
    )


def test_a_comparison_of_41_relatives_cuts_to_40_and_keeps_the_reference() -> None:
    relatives = tuple(
        _genome(f"Examplea delta {k:02d}", reference=True) for k in range(40)
    )
    genomes = (*relatives, _genome(STRAINS[0]), _genome(ALPHA_R, reference=True))

    comparison = comparison_for(STRAINS[:1], ALPHA_R, genomes)

    assert len(comparison) == MAX_COMPARISON_GENOMES
    assert comparison[:2] == (ALPHA_R, "Examplea delta 00")
    assert comparison[-1] == "Examplea delta 38"


def test_a_pseudogene_screen_needs_a_reference() -> None:
    assert screened_checks(ALPHA_R) == ("gene_length", "gene_split", "pseudogene_call")
    assert screened_checks(None) == ("gene_length", "gene_split")


def test_the_estimate_is_the_cost_of_its_units() -> None:
    assert estimate(SCOPE, run_hours=6.0, costs=_costs()) == RunEstimate(
        wdk_requests=133,
        store_reads=5,
        hours=102 / 3600,
        hours_at_most=6.0,
        model_reviews=60,
    )


def test_each_listed_gene_is_priced_as_one_record_read() -> None:
    listed = AuditScope(site_id="exampledb", targets=LIST_TARGETS)
    one = AuditScope(site_id="exampledb", targets=LIST_TARGETS[1:2])

    many = estimate(listed, run_hours=6.0, costs=_costs()).wdk_requests
    single = estimate(one, run_hours=6.0, costs=_costs()).wdk_requests

    assert (many, single) == (3 + 6 + 4 * (4 + 2), 3 + 1 + 4 + 2)
    assert "datasets" not in RunEstimate.model_fields
    assert "model_reads" not in UnitCosts.model_fields


def test_a_scope_of_missing_gene_targets_reads_no_listed_gene() -> None:
    missing = AuditScope(site_id="exampledb", targets=(MISSING,))

    cost = estimate(missing, run_hours=6.0, costs=_costs())

    assert cost.wdk_requests == 3 + 4 + 2


def test_unit_costs_name_every_check() -> None:
    costs = _costs().model_dump()
    del costs["confirm_requests"]["intron_support"]

    with pytest.raises(ValueError, match="confirm_requests names no intron_support"):
        UnitCosts.model_validate(costs)


def _proposal() -> ScopeProposal:
    return ScopeProposal(
        request=PlanRequest(site_id="exampledb", genomes=STRAINS),
        scope=SCOPE,
        estimate=estimate(SCOPE, run_hours=6.0, costs=_costs()),
        left_out=STRAINS[7:],
        refused_targets=(
            RefusedTarget(key="intron_support:EXB_0001", reason="no junction track"),
        ),
    )


def test_the_card_carries_the_proposal_fields() -> None:
    card = start_card(_proposal(), tool_call_id="call_1")

    assert card == AuditStartCard(
        tool_call_id="call_1",
        site_id="exampledb",
        genomes=STRAINS[:1],
        comparison=STRAINS[1:],
        reference_genome=None,
        checks=(
            "gene_fusion",
            "gene_length",
            "gene_split",
            "intron_support",
            "missing_gene",
            "organelle_join",
            "selenoprotein_end",
            "strain_model",
        ),
        targets=6,
        left_out=STRAINS[7:],
        refused_targets=(
            RefusedTarget(key="intron_support:EXB_0001", reason="no junction track"),
        ),
        wdk_requests=133,
        store_reads=5,
        hours=102 / 3600,
        hours_at_most=6.0,
        model_reviews=60,
    )


def test_a_proposal_without_a_scope_draws_no_card() -> None:
    refused = ScopeProposal(
        request=PlanRequest(site_id="exampledb", genomes=("alpha",)),
        unresolved=("alpha",),
    )

    with pytest.raises(ValueError, match="no scope"):
        start_card(refused, tool_call_id="call_1")


def test_a_proposal_carries_a_scope_and_its_estimate_together() -> None:
    with pytest.raises(ValueError, match="together"):
        ScopeProposal(request=PlanRequest(site_id="exampledb"), scope=SCOPE)


def test_the_same_scope_in_another_order_is_the_same_scope() -> None:
    reordered = SCOPE.model_copy(
        update={
            "genomes": tuple(reversed(SCOPE.genomes)),
            "comparison": tuple(reversed(SCOPE.comparison)),
            "targets": tuple(reversed(SCOPE.targets)),
            "checks": tuple(reversed(SCOPE.checks)),
        }
    )

    assert same_scope(SCOPE, reordered)


@pytest.mark.parametrize(
    "change",
    [
        {"comparison": SCOPE.comparison[1:]},
        {"confirm_limit": 6},
        {"site_id": "otherdb"},
        {"reference_genome": ALPHA_R},
        {"checks": ("gene_length",)},
        {
            "targets": (
                *TARGETS[1:],
                SingleGeneTarget(check="gene_fusion", genes=("EXA_0099",)),
            )
        },
    ],
    ids=["comparison", "confirm_limit", "site", "reference", "checks", "target"],
)
def test_a_changed_field_is_another_scope(change: dict[str, object]) -> None:
    assert not same_scope(SCOPE, SCOPE.model_copy(update=change))


def test_the_reference_leads_the_comparison_even_after_an_earlier_marked_strain() -> (
    None
):
    genomes = (
        _genome("Examplea alpha Q", reference=True),
        _genome(STRAINS[0]),
        _genome(ALPHA_R, reference=True),
    )

    assert comparison_for(STRAINS[:1], ALPHA_R, genomes) == (
        ALPHA_R,
        "Examplea alpha Q",
    )


def test_a_genome_a_target_reads_whole_stays_audited_and_the_cut_falls_on_the_others() -> (
    None
):
    kept, left_out = audited_by_gap(
        STRAINS, GENOMES, budget=7, always=frozenset({STRAINS[0]})
    )

    assert kept == (STRAINS[0], *reversed(STRAINS[3:]))
    assert left_out == STRAINS[1:3]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            {"confirm_limit": 0},
            "an audit confirms between 1 and 500 findings for each check, not 0",
        ),
        (
            {"confirm_limit": 900},
            "an audit confirms between 1 and 500 findings for each check, not 900",
        ),
        (
            {
                "targets": tuple(
                    SingleGeneTarget(check="gene_fusion", genes=(f"EXA_{k:04d}",))
                    for k in range(201)
                )
            },
            "an audit checks at most 200 gene targets, not 201",
        ),
        (
            {"checks": ()},
            "an audit request names at least one check, or leaves the checks to the planner",
        ),
    ],
    ids=["confirm_limit_low", "confirm_limit_high", "targets", "no_checks"],
)
def test_a_request_out_of_bounds_is_refused_in_words(
    change: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        PlanRequest.model_validate({"siteId": "exampledb", **change})


def test_a_request_at_the_bounds_is_taken() -> None:
    targets = tuple(
        SingleGeneTarget(check="gene_fusion", genes=(f"EXA_{k:04d}",))
        for k in range(200)
    )

    assert PlanRequest(site_id="exampledb", confirm_limit=500, targets=targets) == (
        PlanRequest(site_id="exampledb", confirm_limit=500, targets=targets)
    )
    assert PlanRequest(site_id="exampledb", confirm_limit=1).confirm_limit == 1
