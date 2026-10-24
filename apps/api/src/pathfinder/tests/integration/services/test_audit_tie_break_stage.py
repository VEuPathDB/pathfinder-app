"""The tie-break stage on a real database: each confirmed length error weighed against its relatives."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from veupathdb.errors import DataParsingError
from veupathdb_mcp import audit

from pathfinder.domain.audit.findings import (
    RelativesEvidence,
)
from pathfinder.domain.audit.scope import GenePairTarget
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
)
from pathfinder.services.audit import confirm, tie_break
from pathfinder.tests._support.audit import (
    NF54_PIGA,
    RecordedLane,
    carried,
    observed_requests,
    relative_organisms,
)
from pathfinder.tests._support.audit_answers import PCYB_PKAC, PCYM_PKAC
from pathfinder.tests.integration.services._audit_confirm import (
    OTHER_REFERENCE,
    OTHER_SHORT,
    PAIR,
    REFERENCE,
    SHORT,
    SPLIT,
    TYPICAL,
    CheckTools,
    CountedLane,
    confirmed_with_no_evidence,
    faked_checks,
    findings_of,
    run_with,
    screened,
    stage_requests,
    weighed_of,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

RELATIVE1 = "Plasmodium relative1 X"
WEIGHED_LENGTHS = dict.fromkeys(relative_organisms(9)[2:], 400) | {RELATIVE1: 420}
OTHER_LENGTHS = {o: 400 for o in relative_organisms(9) if o != RELATIVE1}
WEIGHED = RelativesEvidence(
    reference_gene=REFERENCE,
    reference_length=400,
    model_length=200,
    relatives_median=400.0,
    relative_lengths=WEIGHED_LENGTHS,
    relatives_tier="SAME_GENUS",
    side=audit.tie_break(400, 200, 400.0),
    reference_organism="Plasmodium relative0 X",
)
STRAIN = GenePairTarget(check="strain_model", genes=(PCYM_PKAC, PCYB_PKAC))


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> Iterator[CheckTools]:
    with observed_requests():
        yield faked_checks(monkeypatch)


async def test_tie_break_weighs_each_confirmed_length_error_against_its_relatives(
    tools: CheckTools,
) -> None:
    run = await run_with(screened(SHORT, TYPICAL, PAIR))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    lane = CountedLane()
    await carried(tie_break.run_tie_break_stage, run, lane, seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, lane, seconds=3600)
    weighed = await weighed_of(run.id)
    assert {
        gene: (e.status, e.payload, e.attempts, e.requests)
        for gene, e in weighed.items()
    } == {"NF54_SHORT": ("stored", WEIGHED, 1, 2)}
    assert WEIGHED.side == "STRAIN_SHORT"
    assert tools.ortholog_reads == ["NF54_SHORT"]
    assert tools.evidence_reads == ["NF54_SHORT", NF54_PIGA]
    assert lane.updates == [
        (1, 3, "gene_length:NF54_SHORT: stored"),
        (2, 3, "gene_length:NF54_SHORT: gene evidence stored"),
        (3, 3, f"{PAIR.key}: gene evidence stored"),
    ]
    assert await stage_requests(run) == {
        "collect": 0,
        "screen": 0,
        "confirm": 3,
        "tie_break": 4,
    }


async def test_a_tie_break_read_the_site_cannot_parse_is_stored_failed(
    tools: CheckTools,
) -> None:
    tools.ortholog_failures["NF54_SHORT"].append(
        DataParsingError(
            "plasmodb serves no gene row for PF3D7_0000100, "
            "named in the orthologs of NF54_SHORT"
        )
    )
    tools.references["NF54_SHORT2"] = OTHER_REFERENCE
    run = await run_with(screened(SHORT, OTHER_SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    weighed = await weighed_of(run.id)
    failed, stored = weighed["NF54_SHORT"], weighed["NF54_SHORT2"]
    assert (failed.status, failed.payload, failed.attempts, failed.requests) == (
        "failed",
        None,
        1,
        1,
    )
    assert failed.message == (
        "Data parsing failed: plasmodb serves no gene row for PF3D7_0000100, "
        "named in the orthologs of NF54_SHORT"
    )
    assert (stored.status, stored.payload) == (
        "stored",
        RelativesEvidence(
            reference_gene=OTHER_REFERENCE,
            reference_length=420,
            model_length=190,
            relatives_median=400.0,
            relative_lengths=OTHER_LENGTHS,
            relatives_tier="SAME_GENUS",
            side="STRAIN_SHORT",
            reference_organism=RELATIVE1,
        ),
    )
    assert tools.ortholog_reads == ["NF54_SHORT", "NF54_SHORT2"]


async def test_a_tie_break_read_the_site_answers_late_is_waited_for(
    tools: CheckTools,
) -> None:
    tools.ortholog_failures["NF54_SHORT"].append(
        httpx.ConnectError("connection refused")
    )
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    lane = CountedLane()
    await carried(tie_break.run_tie_break_stage, run, lane, seconds=3600)
    weighed = (await weighed_of(run.id))["NF54_SHORT"]
    assert (weighed.status, weighed.payload, weighed.attempts, weighed.requests) == (
        "stored",
        WEIGHED,
        2,
        3,
    )
    assert lane.updates == [
        (0, 2, "gene_length:NF54_SHORT: unreached (connection refused)"),
        (0, 2, "waiting 30 s for plasmodb, 2 findings unanswered"),
        (1, 2, "gene_length:NF54_SHORT: stored"),
        (2, 2, "gene_length:NF54_SHORT: gene evidence stored"),
    ]
    assert (await stage_requests(run))["tie_break"] == 4


async def test_a_tie_break_read_unanswered_at_the_deadline_is_read_on_the_next_run(
    tools: CheckTools,
) -> None:
    tools.ortholog_failures["NF54_SHORT"].append(
        httpx.ConnectError("connection refused")
    )
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=10)
    weighed = (await weighed_of(run.id))["NF54_SHORT"]
    assert (weighed.status, weighed.payload, weighed.attempts, weighed.message) == (
        "unreached",
        None,
        1,
        "connection refused",
    )
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    weighed = (await weighed_of(run.id))["NF54_SHORT"]
    assert (weighed.status, weighed.payload, weighed.attempts, weighed.message) == (
        "stored",
        WEIGHED,
        2,
        None,
    )


async def test_relatives_the_worker_stopped_during_are_read_again(
    tools: CheckTools,
) -> None:
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    async with async_session_factory() as session:
        await AuditFindingRepository(session).try_evidence(
            (await findings_of(run.id))["NF54_SHORT"].id, "relatives"
        )
        await session.commit()
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    weighed = (await weighed_of(run.id))["NF54_SHORT"]
    assert (weighed.status, weighed.attempts, weighed.stopped) == ("stored", 2, 1)


async def test_a_split_model_is_weighed_by_its_two_parts(tools: CheckTools) -> None:
    run = await run_with(screened(SPLIT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    finding = (await findings_of(run.id))["NF54_A"]
    weighed = (await weighed_of(run.id))["NF54_A"]
    assert (finding.status, finding.error_type, finding.certainty) == (
        "confirmed",
        "split_model",
        "medium",
    )
    assert (weighed.status, weighed.payload) == (
        "stored",
        WEIGHED.model_copy(update={"model_length": 370, "side": "UNCLEAR"}),
    )
    assert tools.ortholog_reads == ["NF54_A"]


async def test_a_confirmation_naming_no_reference_is_failed_without_a_read(
    tools: CheckTools,
) -> None:
    tools.unreferenced.add("NF54_SHORT")
    run = await run_with(screened(SHORT, OTHER_SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    lane = CountedLane()
    await carried(tie_break.run_tie_break_stage, run, lane, seconds=3600)
    weighed = (await weighed_of(run.id))["NF54_SHORT"]
    reason = "the confirmation names no reference gene"
    assert (
        weighed.status,
        weighed.payload,
        weighed.attempts,
        weighed.requests,
        weighed.message,
    ) == ("failed", None, 1, 0, reason)
    assert tools.ortholog_reads == ["NF54_SHORT2"]
    assert lane.updates == [
        (1, 4, f"gene_length:NF54_SHORT: failed ({reason})"),
        (2, 4, "gene_length:NF54_SHORT2: stored"),
        (3, 4, "gene_length:NF54_SHORT: gene evidence stored"),
        (4, 4, "gene_length:NF54_SHORT2: gene evidence stored"),
    ]
    assert (await stage_requests(run))["tie_break"] == 4


async def test_a_named_finding_with_no_confirmation_is_failed_without_a_read(
    tools: CheckTools,
) -> None:
    run = await run_with(screened(SHORT))
    await confirmed_with_no_evidence(run.id, "NF54_SHORT")
    lane = CountedLane()
    await carried(tie_break.run_tie_break_stage, run, lane, seconds=3600)
    weighed = (await weighed_of(run.id))["NF54_SHORT"]
    reason = "no confirmation is stored for this finding"
    assert (
        weighed.status,
        weighed.payload,
        weighed.attempts,
        weighed.requests,
        weighed.message,
    ) == ("failed", None, 1, 0, reason)
    assert tools.ortholog_reads == []
    assert lane.updates == [
        (1, 2, f"gene_length:NF54_SHORT: failed ({reason})"),
        (2, 2, "gene_length:NF54_SHORT: gene evidence stored"),
    ]


async def test_an_unexpected_tie_break_failure_still_counts_its_requests(
    tools: CheckTools,
) -> None:
    tools.ortholog_failures["NF54_SHORT"].append(RuntimeError("a library bug"))
    run = await run_with(screened(SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    with pytest.raises(RuntimeError, match="a library bug"):
        await carried(tie_break.run_tie_break_stage, run, RecordedLane(), seconds=3600)
    weighed = (await weighed_of(run.id))["NF54_SHORT"]
    assert (weighed.status, weighed.attempts) == ("trying", 1)
    assert (await stage_requests(run))["tie_break"] == 1
