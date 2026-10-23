"""The planner reads the site's genomes, resolves the named ones and composes an admitted scope with its estimate."""

from __future__ import annotations

from collections.abc import Mapping

import pytest

from pathfinder.domain.audit.planning import PlanRequest, SiteGenome, estimate
from pathfinder.domain.audit.scope import AuditScope, MissingGeneTarget
from pathfinder.platform.config import get_settings
from pathfinder.services.audit.planning import (
    MEASURED_COSTS,
    propose_scope,
    site_genomes,
)
from pathfinder.tests._support.audit_planning import (
    ALPHA_R,
    BETA_R,
    BETA_S,
    ORGANISMS,
    OUTGROUP,
    SITE,
    STRAINS,
    FakeSite,
    faked_site,
    plan_request,
    setting,
)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    return faked_site(monkeypatch)


def _missing(organism: str) -> MissingGeneTarget:
    return MissingGeneTarget(
        check="missing_gene", genes=(f"EXA_{organism[-1]}",), absent_organism=organism
    )


async def test_the_site_genomes_join_the_three_reads(site: FakeSite) -> None:
    genomes = await site_genomes(SITE)

    assert site.calls == ["list_organisms", "organism_report", "genome_priorities"]
    assert [g.organism for g in genomes] == ORGANISMS
    assert genomes[0] == SiteGenome(
        organism=STRAINS[0],
        genus="Examplea",
        species="Examplea alpha",
        reference_strain=False,
        gap=1.0,
    )
    assert {
        g.organism: g.reference_strain
        for g in genomes
        if g.reference_strain is not False
    } == {ALPHA_R: True, BETA_R: True, BETA_S: None, OUTGROUP: None}


@pytest.mark.usefixtures("site")
async def test_a_named_genome_resolves_and_takes_its_species_reference() -> None:
    proposal = await propose_scope(plan_request("examplea alpha a"))

    expected = AuditScope(
        site_id=SITE,
        genomes=(STRAINS[0],),
        comparison=(ALPHA_R, BETA_R, *STRAINS[1:], BETA_S),
        checks=("gene_length", "gene_split", "pseudogene_call"),
        reference_genome=ALPHA_R,
    )
    assert (proposal.scope, proposal.refusal, proposal.unresolved) == (
        expected,
        None,
        (),
    )
    assert proposal.estimate == estimate(expected, run_hours=6, costs=MEASURED_COSTS)


@pytest.mark.usefixtures("site")
async def test_the_words_of_one_organism_resolve_it() -> None:
    proposal = await propose_scope(plan_request("beta s"))

    assert proposal.scope is not None
    assert proposal.scope.genomes == (BETA_S,)


async def test_a_name_in_another_case_resolves_before_the_word_match(
    site: FakeSite,
) -> None:
    site.organisms.append("Examplea beta")

    proposal = await propose_scope(plan_request("examplea beta"))

    assert proposal.scope is not None
    assert proposal.scope.genomes == ("Examplea beta",)


@pytest.mark.usefixtures("site")
async def test_a_genome_named_twice_is_audited_once() -> None:
    proposal = await propose_scope(plan_request("examplea alpha a", STRAINS[0]))

    assert proposal.scope is not None
    assert proposal.scope.genomes == (STRAINS[0],)


@pytest.mark.usefixtures("site")
async def test_nine_named_strains_with_a_pseudogene_screen_make_an_admitted_scope() -> (
    None
):
    proposal = await propose_scope(plan_request(*STRAINS))

    assert proposal.scope is not None
    assert proposal.scope.genomes == tuple(reversed(STRAINS[2:]))
    assert proposal.left_out == STRAINS[:2]
    assert proposal.scope.reference_genome == ALPHA_R
    assert (
        AuditScope.admitted(
            proposal.scope.model_dump(mode="json", by_alias=True),
            max_genomes=get_settings().audit_max_genomes,
        )
        == proposal.scope
    )


@pytest.mark.usefixtures("site")
async def test_a_named_genome_a_target_reads_whole_stays_audited() -> None:
    proposal = await propose_scope(
        plan_request(*STRAINS, targets=(_missing(STRAINS[0]),))
    )

    assert proposal.refusal is None
    assert proposal.scope is not None
    assert proposal.scope.genomes == (STRAINS[0], *reversed(STRAINS[3:]))
    assert proposal.left_out == STRAINS[1:3]
    assert proposal.scope.reference_genome == ALPHA_R


@pytest.mark.usefixtures("site")
async def test_target_genomes_over_the_cap_are_a_refusal() -> None:
    with (
        pytest.MonkeyPatch.context() as patch,
        setting(patch, "AUDIT_MAX_GENOMES", "1"),
    ):
        proposal = await propose_scope(
            plan_request(targets=(_missing(ALPHA_R), _missing(BETA_R)))
        )

    assert (proposal.scope, proposal.estimate) == (None, None)
    assert proposal.refusal == (
        "the gene targets read 2 whole genomes, and an audit reads at most 1"
    )


@pytest.mark.usefixtures("site")
async def test_a_reference_that_does_not_fit_beside_the_target_genomes_is_dropped() -> (
    None
):
    targets = (_missing(STRAINS[0]), _missing(STRAINS[1]))
    with (
        pytest.MonkeyPatch.context() as patch,
        setting(patch, "AUDIT_MAX_GENOMES", "2"),
    ):
        proposal = await propose_scope(plan_request(*STRAINS[:2], targets=targets))

    assert proposal.scope is not None
    assert (proposal.scope.genomes, proposal.scope.checks) == (
        STRAINS[:2],
        ("gene_length", "gene_split"),
    )
    assert proposal.no_reference == (
        "the species reference Examplea alpha R does not fit the cap of 2 whole genomes"
    )


@pytest.mark.usefixtures("site")
async def test_the_proposal_states_why_it_screens_no_pseudogene_calls() -> None:
    spanning = await propose_scope(plan_request(STRAINS[0], BETA_S))
    unmarked = await propose_scope(plan_request(OUTGROUP))

    assert spanning.no_reference == "the named genomes span 2 species"
    assert spanning.scope is not None
    assert spanning.scope.checks == ("gene_length", "gene_split")
    assert unmarked.no_reference == (
        "no genome of Otherus gamma is marked a reference strain"
    )


@pytest.mark.usefixtures("site")
async def test_a_name_held_by_several_organisms_is_unresolved_with_suggestions() -> (
    None
):
    several = await propose_scope(plan_request("alpha"))
    none = await propose_scope(plan_request("alpha zeta"))

    assert (several.scope, several.unresolved) == (None, ("alpha",))
    assert several.suggestions == {"alpha": STRAINS[:5]}
    assert none.suggestions == {"alpha zeta": ()}


@pytest.mark.usefixtures("site")
async def test_the_requested_checks_and_confirm_limit_narrow_the_screen() -> None:
    request = PlanRequest(
        site_id=SITE, genomes=(STRAINS[0],), checks=("gene_length",), confirm_limit=5
    )

    proposal = await propose_scope(request)

    assert proposal.scope is not None
    assert (
        proposal.scope.checks,
        proposal.scope.reference_genome,
        proposal.scope.confirm_limit,
    ) == (("gene_length",), None, 5)


@pytest.mark.usefixtures("site")
async def test_a_cap_spent_on_target_genomes_leaves_the_named_genomes_out() -> None:
    missing = _missing(BETA_R)
    with (
        pytest.MonkeyPatch.context() as patch,
        setting(patch, "AUDIT_MAX_GENOMES", "1"),
    ):
        proposal = await propose_scope(plan_request(STRAINS[0], targets=(missing,)))

    assert proposal.scope == AuditScope(site_id=SITE, targets=(missing,))
    assert proposal.left_out == (STRAINS[0],)


@pytest.mark.usefixtures("site")
async def test_the_scope_is_admitted_at_the_settings_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admitted = AuditScope.admitted
    caps: list[int] = []

    def spy(raw: Mapping[str, object], *, max_genomes: int) -> AuditScope:
        caps.append(max_genomes)
        return admitted(raw, max_genomes=max_genomes)

    monkeypatch.setattr(AuditScope, "admitted", staticmethod(spy))
    with setting(monkeypatch, "AUDIT_MAX_GENOMES", "5"):
        await propose_scope(plan_request(STRAINS[0]))

    assert caps == [5]


@pytest.mark.usefixtures("site")
async def test_the_estimate_waits_the_settings_run_hours(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with setting(monkeypatch, "AUDIT_RUN_HOURS", "3.5"):
        proposal = await propose_scope(plan_request(STRAINS[0]))

    assert proposal.estimate is not None
    assert proposal.estimate.hours_at_most == 3.5
