"""The planner keeps the gene targets the site can judge, places their genomes, and never uploads a dataset."""

from __future__ import annotations

import httpx
import pytest
import veupathdb_mcp.audit
from veupathdb.errors import WDKError
from veupathdb.wdk import StrategyAPI
from veupathdb_mcp.catalog import NoGeneRecordsError

from pathfinder.domain.audit.planning import RefusedTarget
from pathfinder.domain.audit.scope import AuditScope, MissingGeneTarget, OrganelleTarget
from pathfinder.services.audit import planning
from pathfinder.services.audit.planning import propose_scope, unresolved_names
from pathfinder.tests._support.audit_planning import (
    BETA_R,
    RNA_KEPT,
    RNA_REFUSED,
    SEC_KEPT,
    SEC_REFUSED,
    SEC_UNSERVED,
    SITE,
    SITE_NAME,
    STRAINS,
    FakeSite,
    faked_site,
    plan_request,
)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> FakeSite:
    return faked_site(monkeypatch)


def _refusing(*args: object, **kwargs: object) -> None:
    del args, kwargs
    msg = "planning uploads no dataset"
    raise AssertionError(msg)


async def _failing_proteins(site_id: str, gene_ids: list[str]) -> dict[str, str]:
    del site_id, gene_ids
    detail = "the record service answered 500"
    raise WDKError(detail)


async def _failing_organism(site_id: str, gene: str) -> str:
    del gene
    raise NoGeneRecordsError(site_id)


def _raising(error: Exception) -> object:
    async def gene_organism(site_id: str, gene: str) -> str:
        del site_id, gene
        raise error

    return gene_organism


@pytest.mark.usefixtures("site")
async def test_a_target_without_a_junction_track_is_refused() -> None:
    proposal = await propose_scope(plan_request(targets=(RNA_KEPT, RNA_REFUSED)))

    assert proposal.scope is not None
    assert proposal.scope.targets == (RNA_KEPT,)
    assert proposal.refused_targets == (
        RefusedTarget(
            key=RNA_REFUSED.key,
            reason=f"{SITE_NAME} serves no RNA-seq junction track for the genome of EXB_0001",
        ),
    )


@pytest.mark.usefixtures("site")
async def test_a_sec_target_whose_reference_holds_no_selenocysteine_is_refused() -> (
    None
):
    proposal = await propose_scope(
        plan_request(targets=(SEC_KEPT, SEC_REFUSED, SEC_UNSERVED))
    )

    assert proposal.scope is not None
    assert proposal.scope.targets == (SEC_KEPT, SEC_UNSERVED)
    assert proposal.refused_targets == (
        RefusedTarget(
            key=SEC_REFUSED.key,
            reason=(
                "the reference protein of EXA_0012 holds no selenocysteine, "
                "so its lineage reads no Sec codon"
            ),
        ),
    )


async def test_without_the_sec_prefilter_every_sec_target_is_kept_unread(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(planning, "SEC_PREFILTER", False)

    proposal = await propose_scope(plan_request(targets=(SEC_KEPT, SEC_REFUSED)))

    assert proposal.scope is not None
    assert proposal.scope.targets == (SEC_KEPT, SEC_REFUSED)
    assert "record_proteins" not in site.calls


async def test_planning_never_uploads_a_dataset(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(veupathdb_mcp.audit, "proteins_of", _refusing)
    monkeypatch.setattr(veupathdb_mcp.audit, "locus_tag_answers", _refusing)
    monkeypatch.setattr(StrategyAPI, "create_dataset", _refusing)

    proposal = await propose_scope(
        plan_request(STRAINS[0], targets=(SEC_KEPT, RNA_KEPT, SEC_UNSERVED))
    )

    assert proposal.scope is not None
    assert proposal.scope.targets == (SEC_KEPT, RNA_KEPT, SEC_UNSERVED)
    assert site.calls.count("record_proteins") == 2


async def test_a_proposal_reads_the_site_three_times_and_each_target_it_judges(
    site: FakeSite,
) -> None:
    await propose_scope(plan_request(STRAINS[0], targets=(SEC_KEPT, RNA_KEPT)))

    assert site.calls == [
        "list_organisms",
        "organism_report",
        "genome_priorities",
        "record_proteins",
        "gene_organism",
        "junction_tracks",
    ]


async def test_a_failed_sec_read_refuses_only_its_target(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    del site
    monkeypatch.setattr(planning, "record_proteins", _failing_proteins)

    proposal = await propose_scope(plan_request(targets=(SEC_KEPT, RNA_KEPT)))

    assert proposal.scope is not None
    assert proposal.scope.targets == (RNA_KEPT,)
    assert proposal.refused_targets == (
        RefusedTarget(
            key=SEC_KEPT.key, reason=f"{SITE_NAME} did not answer the read of EXR_0002"
        ),
    )


async def test_a_gene_the_site_cannot_read_refuses_only_its_target(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    del site
    monkeypatch.setattr(planning, "gene_organism", _failing_organism)

    proposal = await propose_scope(plan_request(targets=(SEC_KEPT, RNA_KEPT)))

    assert proposal.scope is not None
    assert proposal.scope.targets == (SEC_KEPT,)
    assert proposal.refused_targets == (
        RefusedTarget(key=RNA_KEPT.key, reason=f"{SITE_NAME} could not read EXA_0007"),
    )


@pytest.mark.usefixtures("site")
@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (NoGeneRecordsError(SITE), f"{SITE_NAME} could not read EXA_0007"),
        (WDKError("no such gene", status=404), f"{SITE_NAME} could not read EXA_0007"),
        (WDKError("bad gateway"), f"{SITE_NAME} did not answer the read of EXA_0007"),
        (
            httpx.ConnectError("refused"),
            f"{SITE_NAME} did not answer the read of EXA_0007",
        ),
    ],
    ids=["no_gene_records", "not_found", "server_error", "transport"],
)
async def test_a_failed_read_says_whether_the_site_answered(
    monkeypatch: pytest.MonkeyPatch, error: Exception, reason: str
) -> None:
    monkeypatch.setattr(planning, "gene_organism", _raising(error))

    proposal = await propose_scope(plan_request(targets=(RNA_KEPT,)))

    assert proposal.refused_targets == (RefusedTarget(key=RNA_KEPT.key, reason=reason),)


@pytest.mark.usefixtures("site")
async def test_two_targets_that_place_to_one_key_are_checked_once() -> None:
    first = MissingGeneTarget(
        check="missing_gene", genes=("EXA_0009",), absent_organism=BETA_R
    )
    again = first.model_copy(update={"absent_organism": "examplea beta r"})

    proposal = await propose_scope(plan_request(targets=(first, SEC_KEPT, again)))

    assert proposal.refusal is None
    assert proposal.scope is not None
    assert proposal.scope.targets == (first, SEC_KEPT)


@pytest.mark.usefixtures("site")
async def test_a_target_genome_is_placed_on_its_resolved_name() -> None:
    missing = MissingGeneTarget(
        check="missing_gene", genes=("EXA_0009",), absent_organism="examplea beta r"
    )
    organelle = OrganelleTarget(
        check="organelle_join",
        genes=("EXA_0006",),
        organism="EXAMPLEA ALPHA A",
        sequence_id="EXA_MT",
    )

    proposal = await propose_scope(plan_request(targets=(missing, organelle)))

    assert proposal.scope is not None
    assert proposal.scope.targets == (
        missing.model_copy(update={"absent_organism": BETA_R}),
        organelle.model_copy(update={"organism": STRAINS[0]}),
    )


@pytest.mark.usefixtures("site")
async def test_an_unresolved_target_genome_draws_no_scope() -> None:
    missing = MissingGeneTarget(
        check="missing_gene", genes=("EXA_0009",), absent_organism="beta"
    )

    proposal = await propose_scope(plan_request(targets=(missing,)))

    assert (proposal.scope, proposal.unresolved) == (None, ("beta",))
    assert proposal.suggestions == {"beta": ("Examplea beta R", "Examplea beta S")}


@pytest.mark.usefixtures("site")
async def test_unresolved_names_are_the_scope_names_the_site_does_not_hold() -> None:
    scope = AuditScope(
        site_id=SITE,
        genomes=(STRAINS[0], "Examplea alpha Z"),
        comparison=("Examplea alpha Y",),
        checks=("gene_length",),
        targets=(
            MissingGeneTarget(
                check="missing_gene", genes=("EXA_0009",), absent_organism="Nonea x"
            ),
        ),
    )

    assert await unresolved_names(scope) == (
        "Examplea alpha Z",
        "Examplea alpha Y",
        "Nonea x",
    )


async def _proteins_timing_out(site_id: str, gene_ids: list[str]) -> dict[str, str]:
    del site_id, gene_ids
    detail = "read timed out"
    raise httpx.ConnectTimeout(detail)


async def test_a_sec_read_that_times_out_is_not_answered(
    site: FakeSite, monkeypatch: pytest.MonkeyPatch
) -> None:
    del site
    monkeypatch.setattr(planning, "record_proteins", _proteins_timing_out)

    proposal = await propose_scope(plan_request(targets=(SEC_KEPT, RNA_KEPT)))

    assert proposal.refused_targets == (
        RefusedTarget(
            key=SEC_KEPT.key, reason=f"{SITE_NAME} did not answer the read of EXR_0002"
        ),
    )


@pytest.mark.usefixtures("site")
async def test_a_request_whose_every_target_is_refused_says_so() -> None:
    proposal = await propose_scope(plan_request(targets=(RNA_REFUSED, SEC_REFUSED)))

    assert (proposal.scope, proposal.refusal) == (
        None,
        "every gene target was refused",
    )
    assert len(proposal.refused_targets) == 2
