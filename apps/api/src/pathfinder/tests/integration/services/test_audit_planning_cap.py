"""Every scope the planner proposes is one its admission accepts, and a named genome is cut only when the genome cap is full."""

from __future__ import annotations

from itertools import combinations, product

import pytest

from pathfinder.domain.audit.planning import PlanRequest
from pathfinder.domain.audit.scope import (
    AuditScope,
    MissingGeneTarget,
    ScreenedCheck,
    SingleGeneTarget,
    whole_genome_reads,
)
from pathfinder.services.audit.planning import propose_scope
from pathfinder.tests._support.audit_planning import (
    BETA_R,
    BETA_S,
    OUTGROUP,
    SITE,
    STRAINS,
    FakeSite,
    faked_site,
    plan_request,
    setting,
)

UNNAMED = (BETA_R, BETA_S, OUTGROUP)
NO_SCREEN = ("gene_length", "gene_split")
SCREENED: tuple[ScreenedCheck, ...] = ("gene_length", "gene_split", "pseudogene_call")
CHECK_SETS: list[tuple[ScreenedCheck, ...] | None] = [
    None,
    *(subset for size in (1, 2, 3) for subset in combinations(SCREENED, size)),
]
FUSION = SingleGeneTarget(check="gene_fusion", genes=("EXA_0003",))


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    return faked_site(monkeypatch)


def _missing(organism: str) -> MissingGeneTarget:
    return MissingGeneTarget(
        check="missing_gene", genes=("EXA_0009",), absent_organism=organism
    )


@pytest.mark.usefixtures("site")
async def test_one_named_genome_under_a_cap_of_one_is_audited_without_a_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with setting(monkeypatch, "AUDIT_MAX_GENOMES", "1"):
        proposal = await propose_scope(plan_request(STRAINS[0]))

    assert proposal.scope is not None
    assert (proposal.scope.genomes, proposal.scope.checks, proposal.left_out) == (
        STRAINS[:1],
        NO_SCREEN,
        (),
    )
    assert proposal.no_reference == (
        "the species reference Examplea alpha R does not fit the cap of 1 whole genome"
    )


@pytest.mark.usefixtures("site")
async def test_a_named_genome_keeps_the_last_slot_beside_seven_target_genomes() -> None:
    absent = (*UNNAMED, *STRAINS[1:5])
    targets = tuple(_missing(organism) for organism in absent)

    proposal = await propose_scope(plan_request(STRAINS[0], targets=targets))

    assert proposal.scope is not None
    assert (proposal.scope.genomes, proposal.scope.checks, proposal.left_out) == (
        STRAINS[:1],
        NO_SCREEN,
        (),
    )
    assert len(proposal.scope.targets) == 7
    assert proposal.no_reference == (
        "the species reference Examplea alpha R does not fit the cap of 8 whole genomes"
    )


@pytest.mark.usefixtures("site")
async def test_a_reference_beside_genomes_the_targets_read_is_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with setting(monkeypatch, "AUDIT_MAX_GENOMES", "2"):
        proposal = await propose_scope(
            plan_request(STRAINS[0], targets=(_missing(STRAINS[0]),))
        )

    assert proposal.scope is not None
    assert (proposal.scope.reference_genome, proposal.scope.checks) == (
        "Examplea alpha R",
        SCREENED,
    )
    assert proposal.no_reference is None


@pytest.mark.usefixtures("site")
async def test_genomes_with_no_check_left_are_left_out_and_the_targets_kept() -> None:
    request = PlanRequest(
        site_id=SITE,
        genomes=(STRAINS[0], BETA_S),
        checks=("pseudogene_call",),
        targets=(FUSION,),
    )

    proposal = await propose_scope(request)

    assert proposal.scope == AuditScope(site_id=SITE, targets=(FUSION,))
    assert proposal.left_out == (STRAINS[0], BETA_S)
    assert proposal.no_reference == "the named genomes span 2 species"


@pytest.mark.usefixtures("site")
async def test_genomes_with_no_check_left_and_no_target_are_refused_with_the_reason() -> (
    None
):
    request = PlanRequest(
        site_id=SITE, genomes=(STRAINS[0], BETA_S), checks=("pseudogene_call",)
    )

    proposal = await propose_scope(request)

    assert (proposal.scope, proposal.left_out) == (None, (STRAINS[0], BETA_S))
    assert proposal.refusal == (
        "no pseudogene screen can run: the named genomes span 2 species"
    )


@pytest.mark.usefixtures("site")
@pytest.mark.parametrize(
    ("cap", "named", "read", "on_named", "checks"),
    list(product(range(1, 5), range(4), range(4), (False, True), CHECK_SETS)),
)
async def test_every_proposed_scope_is_admitted_or_refused_with_its_reason(
    monkeypatch: pytest.MonkeyPatch,
    cap: int,
    named: int,
    read: int,
    on_named: bool,
    checks: tuple[ScreenedCheck, ...] | None,
) -> None:
    genomes = STRAINS[:named]
    places = ((*genomes, *UNNAMED) if on_named else UNNAMED)[:read]
    targets = tuple(_missing(organism) for organism in places)
    request = PlanRequest(site_id=SITE, genomes=genomes, targets=targets, checks=checks)
    with setting(monkeypatch, "AUDIT_MAX_GENOMES", str(cap)):
        proposal = await propose_scope(request)

    unscreened = checks == ("pseudogene_call",) and proposal.no_reference is not None
    if proposal.scope is None:
        if read > cap:
            assert proposal.refusal == (
                f"the gene targets read {read} whole genomes, and an audit reads "
                f"at most {cap}"
            )
        elif named:
            assert (unscreened, read, proposal.refusal) == (
                True,
                0,
                f"no pseudogene screen can run: {proposal.no_reference}",
            )
        else:
            assert (read, proposal.refusal) == (
                0,
                "an audit names the genomes it screens or the gene targets it checks",
            )
        return
    dumped = proposal.scope.model_dump(mode="json", by_alias=True)
    assert AuditScope.admitted(dumped, max_genomes=cap) == proposal.scope
    assert sorted((*proposal.scope.genomes, *proposal.left_out)) == list(genomes)
    if proposal.left_out:
        full = len(whole_genome_reads(proposal.scope)) == cap
        assert full or (unscreened and not proposal.scope.genomes)
