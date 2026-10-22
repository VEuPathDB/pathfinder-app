"""Whether each audited genome is its species' reference strain, read once in collect and used to weigh findings."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from uuid import UUID

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb import get_observer
from veupathdb.wdk import WDKAnswer

from pathfinder.domain.audit.scope import AuditScope
from pathfinder.persistence.models import AuditRunRecord
from pathfinder.persistence.repositories.audit import AuditRepository, CollectedGenome
from pathfinder.services.audit import collect, confirm, tie_break
from pathfinder.services.audit.runs import create_run
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import (
    NF54,
    P3D7,
    FakeSite,
    RecordedLane,
    carried,
    gene_row,
    observed_requests,
    relative_organisms,
    seed_thread,
)
from pathfinder.tests._support.audit_provenance import organism_answer
from pathfinder.tests.integration.services._audit_confirm import (
    SHORT,
    CheckTools,
    faked_checks,
    findings_of,
    run_with,
    screened,
)
from pathfinder.tests.integration.services._audit_stages import faked_site

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

RELATIVE = "Plasmodium relative0 X"
NF55 = "Plasmodium falciparum NF55"
SCOPE = AuditScope(
    site_id="plasmodb",
    genomes=(P3D7, NF54),
    comparison=relative_organisms(9),
    checks=("gene_length",),
)
_REQUEST = {
    "method": "POST",
    "endpoint_group": "searches",
    "site_host": "qa.plasmodb.org",
    "has_auth": "true",
    "status_family": "2xx",
    "outcome": "ok",
}


class Organisms:
    def __init__(self) -> None:
        self.reads = 0
        self.failures: list[BaseException] = []

    async def report(self, site_id: str, attributes: Sequence[str]) -> WDKAnswer:
        del site_id, attributes
        self.reads += 1
        get_observer().on_wdk_request(0.01, _REQUEST)
        if self.failures:
            raise self.failures.pop(0)
        return organism_answer()


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeSite]:
    with observed_requests():
        fake = faked_site(monkeypatch)
        fake.rows = [
            *fake.rows,
            gene_row("P3D7_A", P3D7, 300),
            gene_row("NF55_A", NF55, 300),
        ]
        yield fake


@pytest.fixture
def organisms(monkeypatch: pytest.MonkeyPatch) -> Organisms:
    served = Organisms()
    monkeypatch.setattr(collect, "organism_report", served.report)
    return served


async def _collect(run_id: UUID, seconds: float = 3600) -> None:
    async with async_session_factory() as session:
        run = await AuditRepository(session).stored_run(run_id)
    assert run is not None
    await carried(collect.run_collect_stage, run, RecordedLane(), seconds=seconds)


async def _states(run_id: UUID) -> dict[str, tuple[str, bool | None, int, str | None]]:
    async with async_session_factory() as session:
        states = await AuditRepository(session).genome_states(run_id)
    return {
        s.organism: (s.status, s.reference_strain, s.requests, s.message)
        for s in states
    }


async def _one_genome_run(organism: str) -> UUID:
    owner = await seed_thread()
    scope = AuditScope(site_id="plasmodb", genomes=(organism,), checks=("gene_length",))
    return await create_run(owner=owner, scope=scope)


async def test_collect_reads_the_organism_report_once_for_every_audited_genome(
    site: FakeSite, organisms: Organisms
) -> None:
    owner = await seed_thread()
    run_id = await create_run(owner=owner, scope=SCOPE)
    await _collect(run_id)
    states = await _states(run_id)
    assert (states[P3D7], states[NF54], states[RELATIVE][:2]) == (
        ("collected", True, 2, None),
        ("collected", False, 1, None),
        ("collected", None),
    )
    assert organisms.reads == 1
    view = await run_view(run_id, owner.user_id)
    assert [(g.organism, g.reference_strain) for g in view.genomes][:2] == [
        (P3D7, True),
        (NF54, False),
    ]
    assert len(site.genome_reads) == 11


async def test_an_unanswered_organism_report_leaves_the_genome_unreached_until_read(
    site: FakeSite, organisms: Organisms
) -> None:
    organisms.failures.append(httpx.ConnectError("connection refused"))
    run_id = await _one_genome_run(NF54)
    await _collect(run_id, seconds=10)
    assert (await _states(run_id))[NF54] == (
        "unreached",
        None,
        1,
        "genome provenance unreached: connection refused",
    )
    assert site.genome_reads == []
    async with async_session_factory() as session:
        assert await AuditRepository(session).reopen_unreached(run_id) == "collect"
        await session.commit()
    await _collect(run_id)
    assert (await _states(run_id))[NF54] == ("collected", False, 3, None)
    assert organisms.reads == 2


async def test_a_genome_the_report_does_not_hold_has_an_unknown_use(
    site: FakeSite, organisms: Organisms
) -> None:
    run_id = await _one_genome_run(NF55)
    await _collect(run_id)
    assert (await _states(run_id))[NF55] == (
        "collected",
        None,
        2,
        (
            f"genome provenance failed: {NF55} names no genome of plasmodb; "
            "its genome use is unknown"
        ),
    )
    assert (organisms.reads, site.genome_reads) == (1, [NF55])


async def test_a_stored_mark_is_never_read_again(
    site: FakeSite, organisms: Organisms
) -> None:
    site.failures[NF54].append(httpx.ConnectError("connection refused"))
    run_id = await _one_genome_run(NF54)
    await _collect(run_id)
    assert (await _states(run_id))[NF54][:2] == ("collected", False)
    assert (organisms.reads, site.genome_reads) == (1, [NF54, NF54])


async def _with_genome(reference_strain: bool | None) -> AuditRunRecord:
    run = await run_with(screened(SHORT))
    async with async_session_factory() as session:
        repo = AuditRepository(session)
        await repo.add_genomes(run.id, [(NF54, "audited")])
        await repo.try_genome(run.id, NF54)
        await repo.save_genome(
            run.id,
            CollectedGenome(
                organism=NF54, status="collected", reference_strain=reference_strain
            ),
        )
        await session.commit()
    return run


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> Iterator[CheckTools]:
    with observed_requests():
        yield faked_checks(monkeypatch)


@pytest.mark.parametrize(
    ("reference_strain", "weighed"), [(True, 1.0), (False, 0.5), (None, 0.5)]
)
async def test_a_finding_in_its_species_reference_strain_weighs_more(
    tools: CheckTools, reference_strain: bool | None, weighed: float
) -> None:
    run = await _with_genome(reference_strain)
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    finding = (await findings_of(run.id))["NF54_SHORT"]
    assert (finding.error_type, finding.certainty, finding.impact) == (
        "truncated_model",
        "high",
        weighed,
    )
    assert tools.evidence_reads == ["NF54_SHORT"]
