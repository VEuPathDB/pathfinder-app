"""Gene rows, library check results, a simulated clock and a fake site the audit tests build on."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal, TypedDict, Unpack
from uuid import uuid4

from assistant_core.persistence.models import Conversation
from assistant_core.platform.db import async_session_factory
from pydantic import BaseModel, ConfigDict
from veupathdb import get_observer, set_observer
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb_mcp.audit import (
    GeneId,
    GeneLengthAudit,
    GeneListDataset,
    GeneRow,
    GeneticCode,
    PseudogeneCallAudit,
    SelenoproteinEndAudit,
)

from pathfinder.persistence.models import AuditRunRecord, User
from pathfinder.persistence.repositories.audit import AuditRepository
from pathfinder.platform.identity import PATHFINDER_ASSISTANT_ID
from pathfinder.platform.metrics import PathfinderObserver
from pathfinder.services.audit.progress import StageLane
from pathfinder.services.audit.runs import RunOwner
from pathfinder.services.audit.units import (
    FIRST_WAIT_SECONDS,
    LONGEST_WAIT_SECONDS,
    SLICE_SECONDS,
    ContinueLaterError,
    Waits,
)

NF54 = "Plasmodium falciparum NF54"
P3D7 = "Plasmodium falciparum 3D7"
PIGA = "PF3D7_1032400"
NF54_PIGA = "PfNF54_100037200"
GT1_SELK = "TGGT1_316600"
ME49_SELK = "TGME49_316600"
GROUP = "OG7_0000001"
_REQUEST = {
    "method": "POST",
    "endpoint_group": "searches",
    "site_host": "qa.plasmodb.org",
    "has_auth": "true",
    "status_family": "2xx",
    "outcome": "ok",
}
_NOT_CHECKED_GROUPS = {
    "TYPICAL": (0.95, 10),
    "LONG": (2.0, 10),
    "UNQUALIFIED": (0.6, 6),
}


class Placement(TypedDict, total=False):
    group: str
    sequence: str
    start: int
    strand: Literal["+", "-"]
    pseudo: bool


class _Placed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group: str = GROUP
    sequence: str = "chr1"
    start: int = 1000
    strand: Literal["+", "-"] = "+"
    pseudo: bool = False


def gene_row(
    gene: str, organism: str, length: int | None, **place: Unpack[Placement]
) -> GeneRow:
    at = _Placed.model_validate(place)
    return GeneRow.model_validate(
        {
            "gene": gene,
            "organism": organism,
            "ortholog_group": at.group,
            "protein_length": length,
            "name": "",
            "product": "conserved protein, unknown function",
            "sequence_id": at.sequence,
            "start": at.start,
            "end": at.start + 3 * (length or 100) - 1,
            "strand": at.strand,
            "pseudo": at.pseudo,
            "gene_type": "protein coding gene",
        }
    )


def resolved_ids(*genes: str) -> list[GeneId]:
    return [GeneId(given=gene, resolved=gene) for gene in genes]


def relative_organisms(count: int) -> tuple[str, ...]:
    return tuple(f"Plasmodium relative{k} X" for k in range(count))


def relatives(count: int, length: int, *, group: str = GROUP) -> list[GeneRow]:
    return [
        gene_row(f"{group}_REL{k}", organism, length, group=group)
        for k, organism in enumerate(relative_organisms(count))
    ]


PIGA_INTACT = PseudogeneCallAudit(
    verdict="INTACT",
    reference_cds_length=1386,
    strain_cds_length=1386,
    covered=1386,
    premature_stops=[],
    residue_differences=0,
    gene_ids=resolved_ids(NF54_PIGA, PIGA),
    strain_gene=NF54_PIGA,
    reference_gene=PIGA,
)

SELK_STOPS = SelenoproteinEndAudit(
    verdict="STOPS_AT_SEC",
    after_model_end="*G*",
    reference_tail="UG",
    tail_identity=1.0,
    sec_aligned=True,
    gene_ids=resolved_ids(GT1_SELK, ME49_SELK),
    gene=GT1_SELK,
    reference_gene=ME49_SELK,
)


def _group(
    length_class: str, ratio: float, organisms: int, reference_gene: str
) -> dict[str, object]:
    return {
        "length_class": length_class,
        "ratio": ratio,
        "group_median": 200.0,
        "group_copies": 1.0,
        "group_spread": 0.0,
        "organisms": organisms,
        "reference_gene": reference_gene,
    }


def short_audit(
    gene: str,
    *,
    reference_gene: str,
    verdict: str = "GENOME_ENCODES",
    at_contig_edge: bool = False,
) -> GeneLengthAudit:
    return GeneLengthAudit.model_validate(
        {
            "verdict": verdict,
            "windows": 19,
            "counts": {"model": 12, "genome_same_strand": 7},
            "track": "MMMMMMGGGGGGGMMMMMM",
            "ns_in_window": 0,
            "at_contig_edge": at_contig_edge,
            "genes": [gene],
            "gene_ids": resolved_ids(gene),
            **_group("SHORT", 0.6, 10, reference_gene),
            "code": GeneticCode.STANDARD,
            "code_inferred": True,
        }
    )


def split_audit(
    first: str, second: str, *, reference_gene: str, verdict: str = "SPLIT_CONFIRMED"
) -> GeneLengthAudit:
    return GeneLengthAudit.model_validate(
        {
            "verdict": verdict,
            "windows": 19,
            "counts": {"part1": 9, "genome_same_strand": 1, "part2": 9},
            "track": "1" * 9 + "G" + "2" * 9,
            "ns_in_window": 0,
            "at_contig_edge": False,
            "genes": [first, second],
            "gene_ids": resolved_ids(first, second),
            **_group("SPLIT", 1.0, 10, reference_gene),
            "code": GeneticCode.STANDARD,
            "code_inferred": True,
        }
    )


def not_checked_audit(
    genes: list[str], length_class: str, *, reference_gene: str
) -> GeneLengthAudit:
    ratio, organisms = _NOT_CHECKED_GROUPS[length_class]
    return GeneLengthAudit.model_validate(
        {
            "verdict": "NOT_CHECKED",
            "windows": 0,
            "counts": {},
            "track": "",
            "ns_in_window": None,
            "at_contig_edge": None,
            "genes": genes,
            "gene_ids": resolved_ids(*genes),
            **_group(length_class, ratio, organisms, reference_gene),
            "code": None,
            "code_inferred": False,
        }
    )


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.at = start
        self.slept: list[float] = []

    def now(self) -> datetime:
        return self.at

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.at += timedelta(seconds=seconds)


def simulated_waits(deadline: datetime, clock: FakeClock | None = None) -> Waits:
    ticking = clock or FakeClock(datetime.now(UTC))
    return Waits(
        deadline=deadline,
        slice_ends=ticking.now() + timedelta(seconds=SLICE_SECONDS),
        first_seconds=FIRST_WAIT_SECONDS,
        longest_seconds=LONGEST_WAIT_SECONDS,
        clock=ticking,
    )


type StageBody = Callable[[AuditRunRecord, StageLane, Waits], Awaitable[None]]


async def carried(
    body: StageBody, run: AuditRunRecord, lane: StageLane, *, seconds: float
) -> list[float]:
    clock = FakeClock(datetime.now(UTC))
    waits = simulated_waits(clock.now() + timedelta(seconds=seconds), clock)
    pauses: list[float] = []
    while True:
        try:
            await body(run, lane, waits)
        except ContinueLaterError as later:
            pauses.append(later.seconds)
            await clock.sleep(later.seconds)
            waits = replace(
                waits,
                first_seconds=later.next_seconds,
                slice_ends=clock.now() + timedelta(seconds=SLICE_SECONDS),
            )
            async with async_session_factory() as session:
                stored = await AuditRepository(session).stored_run(run.id)
            assert stored is not None
            run = stored
        else:
            return pauses


async def seed_thread(site_id: str = "plasmodb") -> RunOwner:
    owner = RunOwner(user_id=uuid4(), conversation_id=uuid4())
    async with async_session_factory() as session:
        session.add(User(id=owner.user_id))
        await session.flush()
        session.add(
            Conversation(
                assistant_id=PATHFINDER_ASSISTANT_ID,
                id=owner.conversation_id,
                user_id=owner.user_id,
                site_id=site_id,
                name="",
            )
        )
        await session.commit()
    return owner


class RecordedLane:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def update(self, *, done: int, total: int, message: str) -> None:
        del done, total
        self.messages.append(message)


@contextmanager
def observed_requests() -> Iterator[None]:
    previous = get_observer()
    set_observer(PathfinderObserver())
    try:
        yield
    finally:
        set_observer(previous)


class FakeSite:
    def __init__(self, rows: list[GeneRow]) -> None:
        self.rows = rows
        self.failures: defaultdict[str, list[BaseException]] = defaultdict(list)
        self.release_failures: list[BaseException] = []
        self.target_failures: list[BaseException] = []
        self.uploads: list[list[str]] = []
        self.genome_reads: list[str] = []
        self.release_reads = 0
        self.tokens: set[str | None] = set()

    def _requested(self) -> None:
        self.tokens.add(veupathdb_auth_token_ctx.get())
        get_observer().on_wdk_request(0.01, _REQUEST)

    async def genes_of_genome(self, site_id: str, organism: str) -> list[GeneRow]:
        del site_id
        self._requested()
        self.genome_reads.append(organism)
        if self.failures[organism]:
            raise self.failures[organism].pop(0)
        return [row for row in self.rows if row.organism == organism]

    async def named_rows(self, site_id: str, gene_ids: list[str]) -> list[GeneRow]:
        del site_id
        self._requested()
        if self.target_failures:
            raise self.target_failures.pop(0)
        return [row for row in self.rows if row.gene in gene_ids]

    async def upload_list(self, site_id: str, gene_ids: list[str]) -> GeneListDataset:
        self._requested()
        self.uploads.append(sorted(gene_ids))
        return GeneListDataset(
            site_id=site_id, dataset_id=len(self.uploads), size=len(gene_ids)
        )

    async def read_list(self, dataset: GeneListDataset) -> list[GeneRow]:
        return await self.named_rows(
            dataset.site_id, self.uploads[dataset.dataset_id - 1]
        )

    async def site_build(self, site_id: str) -> str:
        del site_id
        self._requested()
        self.release_reads += 1
        if self.release_failures:
            raise self.release_failures.pop(0)
        return "71"
