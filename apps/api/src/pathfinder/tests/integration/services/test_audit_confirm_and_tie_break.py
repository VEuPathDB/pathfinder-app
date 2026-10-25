"""The confirm stage on a real database: settled findings, stored confirmations, waited-for checks."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from assistant_core.platform.db import async_session_factory
from fastmcp.exceptions import ToolError
from veupathdb.errors import DataParsingError
from veupathdb_mcp.audit import rate_with_bounds

from pathfinder.domain.audit.confirmations import LengthConfirmation
from pathfinder.domain.audit.findings import ConfirmationEvidence
from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.domain.audit.words import target_words
from pathfinder.persistence.repositories.audit_findings import (
    AuditFindingRepository,
    NewFinding,
)
from pathfinder.services.audit import confirm
from pathfinder.services.audit.views import run_view
from pathfinder.tests._support.audit import (
    NF54,
    NF54_PIGA,
    RecordedLane,
    carried,
    not_checked_audit,
    observed_requests,
    short_audit,
)
from pathfinder.tests._support.audit_wire import (
    DD2,
    DD2_YIP1,
    UNFLAGGED_STRAIN,
    yip1_records,
)
from pathfinder.tests.integration.services._audit_confirm import (
    PAIR,
    REFERENCE,
    SHORT,
    TYPICAL,
    UNANSWERED,
    CheckTools,
    CountedLane,
    faked_checks,
    findings_of,
    run_with,
    screened,
    stage_requests,
    unanswered,
)

pytestmark = pytest.mark.usefixtures("patch_app_db_engine", "db_cleaner")

PAIR_WORDS = target_words(PAIR)
TOO_LARGE = (
    "PF3D7_0310200 spans 14855 bases and the PfNF54_030015100:pseudogene window "
    "19628 bases; the check aligns pairs whose product is at most 200000000"
)


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> Iterator[CheckTools]:
    with observed_requests():
        yield faked_checks(monkeypatch)


def _truncated() -> ToolError:
    detail = "WDK GeneByLocusTag report served 10 records of a total of 12"
    error = ToolError(detail)
    error.__cause__ = DataParsingError(detail)
    return error


async def test_confirm_settles_each_sampled_finding_and_stores_its_answer(
    tools: CheckTools,
) -> None:
    left = NewFinding(
        genome=NF54,
        target=SingleGeneTarget(check="gene_length", genes=("NF54_LEFT",)),
        sampled=False,
        status="unsampled",
    )
    run = await run_with([*screened(SHORT, TYPICAL), left])
    lane = CountedLane()
    await carried(confirm.run_confirm_stage, run, lane, seconds=3600)
    found = await findings_of(run.id)
    async with async_session_factory() as session:
        evidence = await AuditFindingRepository(session).evidence(
            run.id, [found["NF54_SHORT"].id, found["NF54_TYPICAL"].id]
        )
    short = found["NF54_SHORT"]
    assert (short.status, short.error_type, short.certainty) == (
        "confirmed",
        "truncated_model",
        "high",
    )
    typical = found["NF54_TYPICAL"]
    assert (typical.status, typical.error_type, typical.judged, typical.message) == (
        "confirmed",
        None,
        False,
        (
            "NOT_CHECKED: the ortholog group does not class the gene as short, so "
            "the check reads no DNA"
        ),
    )
    (rate,) = (await run_view(run.id, run.user_id)).rates
    assert (rate.bounds, rate.unjudged, rate.unresolved) == (
        rate_with_bounds(1, 1, 1),
        1,
        1,
    )
    assert found["NF54_LEFT"].status == "unsampled"
    assert [(e.kind, e.status, e.payload) for e in evidence] == [
        (
            "confirmation",
            "stored",
            ConfirmationEvidence(
                confirmation=LengthConfirmation(
                    check="gene_length",
                    result=short_audit("NF54_SHORT", reference_gene=REFERENCE),
                )
            ),
        ),
        (
            "confirmation",
            "stored",
            ConfirmationEvidence(
                confirmation=LengthConfirmation(
                    check="gene_length",
                    result=not_checked_audit(
                        ["NF54_TYPICAL"], "TYPICAL", reference_gene=REFERENCE
                    ),
                )
            ),
        ),
    ]
    assert [(e.requests, e.attempts) for e in evidence] == [(0, 0), (0, 0)]
    assert [f.requests for f in found.values()] == [1, 1, 0]
    assert await stage_requests(run) == {
        "collect": 0,
        "screen": 0,
        "confirm": 2,
        "tie_break": 0,
    }
    assert lane.updates == [
        (
            1,
            2,
            "Gene length against orthologs, NF54_SHORT: The genome's DNA encodes the part the model lacks",
        ),
        (
            2,
            2,
            (
                "Gene length against orthologs, NF54_TYPICAL: The site's whole ortholog group does not "
                "class the model as short, so its DNA was not read"
            ),
        ),
    ]


async def test_a_check_the_site_answers_late_is_waited_for(tools: CheckTools) -> None:
    tools.pseudogene_failures.append(unanswered())
    run = await run_with(screened(PAIR))
    lane = CountedLane()
    await carried(confirm.run_confirm_stage, run, lane, seconds=3600)
    (finding,) = (await findings_of(run.id)).values()
    assert (
        finding.status,
        finding.error_type,
        finding.attempts,
        finding.requests,
        finding.message,
    ) == ("confirmed", "intact_gene_called_pseudogene", 2, 2, None)
    assert (await stage_requests(run))["confirm"] == 2
    assert lane.updates == [
        (0, 1, f"{PAIR_WORDS}: unreached ({UNANSWERED})"),
        (0, 1, "waiting 30 s for plasmodb, 1 finding unanswered"),
        (
            1,
            1,
            (
                f"{PAIR_WORDS}: The strain's DNA encodes the whole protein, so the "
                "pseudogene call is wrong"
            ),
        ),
    ]


async def test_a_check_unanswered_at_the_deadline_is_tried_on_the_next_run(
    tools: CheckTools,
) -> None:
    tools.pseudogene_failures.append(unanswered())
    run = await run_with(screened(PAIR))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=10)
    (finding,) = (await findings_of(run.id)).values()
    assert (finding.status, finding.attempts, finding.requests, finding.message) == (
        "unreached",
        1,
        1,
        UNANSWERED,
    )
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    (finding,) = (await findings_of(run.id)).values()
    assert (finding.status, finding.attempts, finding.requests, finding.message) == (
        "confirmed",
        2,
        2,
        None,
    )


async def test_a_target_the_screen_stored_unreached_is_confirmed(
    tools: CheckTools,
) -> None:
    run = await run_with(
        [
            NewFinding(
                genome="",
                target=PAIR,
                sampled=True,
                status="unreached",
                message=UNANSWERED,
            )
        ]
    )
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    (finding,) = (await findings_of(run.id)).values()
    assert (
        finding.genome,
        finding.status,
        finding.error_type,
        finding.attempts,
        finding.requests,
        finding.message,
    ) == (NF54, "confirmed", "intact_gene_called_pseudogene", 1, 2, None)


async def test_a_target_the_site_serves_no_gene_row_for_is_failed(
    tools: CheckTools,
) -> None:
    gone = SingleGeneTarget(check="gene_length", genes=("NF54_GONE",))
    run = await run_with(
        [NewFinding(genome="", target=gone, sampled=True, status="screened")]
    )
    lane = CountedLane()
    await carried(confirm.run_confirm_stage, run, lane, seconds=3600)
    (finding,) = (await findings_of(run.id)).values()
    reason = "plasmodb serves no gene row for NF54_GONE"
    assert (
        finding.genome,
        finding.status,
        finding.error_type,
        finding.attempts,
        finding.requests,
        finding.message,
    ) == ("", "failed", None, 1, 1, reason)
    assert lane.updates == [
        (1, 1, f"Gene length against orthologs, NF54_GONE: failed ({reason})")
    ]


async def test_an_unplaced_target_the_site_does_not_answer_for_stays_unreached(
    tools: CheckTools,
) -> None:
    tools.site.target_failures.append(httpx.ConnectError("connection refused"))
    run = await run_with(
        [NewFinding(genome="", target=SHORT, sampled=True, status="screened")]
    )
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=10)
    (finding,) = (await findings_of(run.id)).values()
    assert (finding.genome, finding.status, finding.requests, finding.message) == (
        "",
        "unreached",
        1,
        "connection refused",
    )


@pytest.mark.parametrize(
    ("refusal", "status"),
    [
        (ToolError(f"{NF54_PIGA} names no gene of plasmodb"), "declined"),
        (ToolError(TOO_LARGE), "declined"),
        (_truncated(), "failed"),
    ],
)
async def test_a_refused_check_is_stored_and_the_stage_moves_on(
    tools: CheckTools, refusal: ToolError, status: str
) -> None:
    tools.pseudogene_failures.append(refusal)
    run = await run_with(screened(PAIR, SHORT))
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    found = await findings_of(run.id)
    async with async_session_factory() as session:
        evidence = await AuditFindingRepository(session).evidence(
            run.id, [found[NF54_PIGA].id]
        )
    failed = found[NF54_PIGA]
    assert (failed.status, failed.attempts, failed.requests, failed.message) == (
        status,
        1,
        1,
        str(refusal),
    )
    assert evidence == []
    assert found["NF54_SHORT"].status == "confirmed"
    assert (await stage_requests(run))["confirm"] == 2


@pytest.mark.parametrize(
    ("readable", "reason", "reads", "status"),
    [
        (
            True,
            (
                f"{DD2_YIP1} is not flagged a pseudogene on plasmodb (is_pseudo: No); "
                "the check reads a strain gene the site calls a pseudogene"
            ),
            2,
            "declined",
        ),
        (
            False,
            (
                f"the gene record of {DD2_YIP1} on plasmodb gives no readable "
                "GeneTranscripts"
            ),
            1,
            "failed",
        ),
    ],
)
async def test_a_check_the_library_refuses_on_the_wire_is_stored_once(
    readable: bool, reason: str, reads: int, status: str
) -> None:
    finding = NewFinding(
        genome=DD2, target=UNFLAGGED_STRAIN, sampled=True, status="screened"
    )
    run = await run_with([finding])
    with observed_requests(), yip1_records(readable=readable) as report:
        await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    (failed,) = (await findings_of(run.id)).values()
    assert (failed.status, failed.error_type, failed.attempts, failed.message) == (
        status,
        None,
        1,
        reason,
    )
    assert report.call_count == reads
    assert failed.requests == reads + 1
    assert (await stage_requests(run))["confirm"] == reads + 1


async def test_a_finding_the_worker_stopped_during_is_tried_again(
    tools: CheckTools,
) -> None:
    run = await run_with(screened(SHORT))
    async with async_session_factory() as session:
        await AuditFindingRepository(session).try_finding(
            (await findings_of(run.id))["NF54_SHORT"].id
        )
        await session.commit()
    await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    (finding,) = (await findings_of(run.id)).values()
    assert (finding.status, finding.attempts, finding.stopped) == ("confirmed", 2, 1)


async def test_an_unexpected_failure_still_counts_its_requests(
    tools: CheckTools,
) -> None:
    tools.length_failures["NF54_SHORT"].append(RuntimeError("a library bug"))
    run = await run_with(screened(SHORT))
    with pytest.raises(RuntimeError, match="a library bug"):
        await carried(confirm.run_confirm_stage, run, RecordedLane(), seconds=3600)
    (finding,) = (await findings_of(run.id)).values()
    assert (finding.status, finding.attempts) == ("trying", 1)
    assert (await stage_requests(run))["confirm"] == 1
