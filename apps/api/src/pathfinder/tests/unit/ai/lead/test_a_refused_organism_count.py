from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import httpx
import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKAnswer, WDKFilterValue, WDKStrategyDetails
from veupathdb_mcp.wdk import ColumnCounts, CountedValue

from pathfinder.ai.graph._lead_events import _verified
from pathfinder.ai.lead.ledger_render import render_verification_full
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.services.experiment import paged_tally
from pathfinder.services.experiment.reporter_refusals import (
    REFUSAL_LIFETIME_SECONDS,
    REPORTER_REFUSALS,
)
from pathfinder.services.strategies import site_counts
from pathfinder.tests._support.column_reads import ColumnSite, serve_columns
from pathfinder.tests._support.recorded_columns import column_catalog
from pathfinder.tests._support.step_tally_site import TallySite, ToolServer, serve
from pathfinder.tests.unit.ai.lead._site_verdict import (
    UNANSWERED_DIGEST,
    serve_the_site,
    verify,
)
from pathfinder.tests.unit.ai.lead.test_a_second_organism_fails_the_verdict import (
    _EXPORTED,
    _exported_deps,
    _exported_details,
)

pytestmark = pytest.mark.usefixtures("collector")

_PF = "Plasmodium falciparum 3D7"
_PF_IT = "Plasmodium falciparum IT"
_GENES, _TRANSCRIPTS = 479, 483
_LARGE = 4200
_SERVICE = "https://qa.plasmodb.org/plasmo.qa/service/users/1/steps"
_BY_VALUE = f"{_SERVICE}/{_EXPORTED}/columns/organism/reports/byValue"
_STANDARD = f"{_SERVICE}/{_EXPORTED}/reports/standard"
_GENE_VIEW = [WDKFilterValue(name="representativeTranscriptOnly", value={})]


def _failed_after(cause: Exception, status: int) -> WDKError:
    failed = WDKError(f"Request failed after retries: {cause}", status=status)
    failed.__cause__ = cause
    return failed


def _internal_error(url: str) -> WDKError:
    request = httpx.Request("POST", url)
    response = httpx.Response(500, text="Internal Error", request=request)
    status = httpx.HTTPStatusError("Internal Error", request=request, response=response)
    return _failed_after(status, 500)


def _connect_error() -> WDKError:
    return _failed_after(httpx.ConnectError("connection refused"), 502)


def _sized(size: int) -> WDKStrategyDetails:
    details = _exported_details()
    root = details.steps[str(_EXPORTED)].model_copy(update={"estimated_size": size})
    return details.model_copy(update={"steps": {str(_EXPORTED): root}})


def _answer(*organisms: str) -> WDKAnswer:
    return WDKAnswer.model_validate(
        {
            "meta": {
                "totalCount": _TRANSCRIPTS,
                "displayTotalCount": _TRANSCRIPTS,
                "viewTotalCount": len(organisms),
                "displayViewTotalCount": len(organisms),
                "responseCount": len(organisms),
                "recordClassName": "transcript",
                "attributes": ["organism_full"],
                "tables": [],
                "pagination": {"offset": 0, "numRecords": 2000},
                "sorting": [],
                "cachePreviouslyExisted": True,
            },
            "records": [
                {
                    "displayName": f"PF3D7_{n:07d}",
                    "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
                    "attributes": {"organism_full": organism},
                    "id": [
                        {"name": "gene_source_id", "value": f"PF3D7_{n:07d}"},
                        {"name": "source_id", "value": f"PF3D7_{n:07d}.1"},
                        {"name": "project_id", "value": "PlasmoDB"},
                    ],
                    "tables": {},
                    "tableErrors": [],
                }
                for n, organism in enumerate(organisms)
            ],
        }
    )


def _organisms(*counted: tuple[str, int]) -> ColumnCounts:
    return ColumnCounts(
        step_id=_EXPORTED,
        column="organism",
        display_name="Organism",
        kind="string",
        total_records=sum(count for _, count in counted),
        distinct_values=len(counted),
        values=tuple(CountedValue(value=v, count=n) for v, n in counted),
    )


@dataclass
class _Pages:
    answer: WDKAnswer | None = None
    failure: WDKError | None = None
    asked: list[tuple[int, list[str] | None, dict[str, int] | None]] = field(
        default_factory=list
    )
    viewed: list[Sequence[WDKFilterValue] | None] = field(default_factory=list)

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
    ) -> WDKAnswer:
        self.asked.append((step_id, attributes, pagination))
        self.viewed.append(view_filters)
        if self.failure is not None:
            raise self.failure
        assert self.answer is not None
        return self.answer


@dataclass
class _Clock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


def _site(
    monkeypatch: pytest.MonkeyPatch, size: int, server: ToolServer, pages: _Pages
) -> None:
    serve_the_site(monkeypatch, _sized(size), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    serve(monkeypatch, TallySite(column_catalog(), step_count=size), server)
    monkeypatch.setattr(paged_tally, "get_strategy_api", lambda _site: pages)


def _organism(checks: list[SiteCheck]) -> SiteCheck:
    [organism] = [c for c in checks if c.kind is ConstraintKind.ORGANISM]
    return organism


async def test_a_small_result_is_counted_by_gene_from_its_records_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(refusal=_internal_error(_BY_VALUE))
    pages = _Pages(_answer(*[_PF] * (_GENES - 2), _PF_IT, _PF_IT))
    _site(monkeypatch, _GENES, server, pages)

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    assert (server.counted, pages.asked, pages.viewed) == (
        [],
        [(_EXPORTED, ["organism_full"], {"offset": 0, "numRecords": 2000})],
        [_GENE_VIEW],
    )
    assert _organism(digest.review.checks) == SiteCheck(
        kind=ConstraintKind.ORGANISM,
        subject=_PF,
        status="fail",
        evidence=(
            f"2 of the {_GENES} records of step {_EXPORTED} ('Text') hold organisms "
            f"the strategy does not select: {_PF_IT} (2)"
        ),
        requirement=f"organism:{_PF}",
    )
    assert (digest.success, digest.not_checked) == (False, False)


async def test_a_small_result_of_the_selected_organism_passes_on_its_gene_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(refusal=_internal_error(_BY_VALUE))
    _site(monkeypatch, _GENES, server, _Pages(_answer(*[f"<i>{_PF}</i>"] * _GENES)))

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    organism = _organism(digest.review.checks)
    assert (digest.success, digest.passed, organism.status, organism.evidence) == (
        True,
        True,
        "pass",
        (
            f"all {_GENES} records of step {_EXPORTED} ('Text') hold an organism the "
            f"strategy selects: {_PF} ({_GENES})"
        ),
    )


async def test_a_standard_report_the_site_refuses_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(counts=_organisms((_PF, _GENES)))
    pages = _Pages(failure=_internal_error(_STANDARD))
    _site(monkeypatch, _GENES, server, pages)

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    organism = _organism(digest.review.checks)
    assert (server.counted, organism.why_unchecked, digest.success) == (
        [],
        "site_refused",
        True,
    )


async def test_a_standard_report_the_site_does_not_answer_gives_no_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _Pages(failure=_connect_error())
    _site(monkeypatch, _GENES, ToolServer(), pages)

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    organism = _organism(digest.review.checks)
    assert (organism.why_unchecked, digest.success, digest.not_checked) == (
        "site_unanswered",
        False,
        True,
    )


async def test_a_refused_count_of_a_large_result_is_refused_and_still_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _Pages()
    _site(monkeypatch, _LARGE, ToolServer(refusal=_internal_error(_BY_VALUE)), pages)

    delta = await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)

    digest = delta.digest
    organism = _organism(digest.review.checks)
    ledger = render_verification_full(VerificationSection(digest=digest))
    assert pages.asked == []
    assert _verified(delta) == "Verified successfully"
    assert (
        f"- [unchecked] {_PF}: the site refused the organism count of step "
        f"{_EXPORTED} ('Text')"
    ) in ledger.split("\n")
    assert (organism.status, organism.why_unchecked, organism.evidence) == (
        "unchecked",
        "site_refused",
        f"the site refused the organism count of step {_EXPORTED} ('Text')",
    )
    assert (digest.success, digest.passed, digest.not_checked, digest.gaps) == (
        True,
        True,
        False,
        [],
    )


async def test_a_refused_reporter_is_not_sent_again_until_its_refusal_lapses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    monkeypatch.setattr(REPORTER_REFUSALS, "clock", clock)
    server = ToolServer(refusal=_internal_error(_BY_VALUE))
    _site(monkeypatch, _LARGE, server, _Pages())

    first = await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)
    clock.now += REFUSAL_LIFETIME_SECONDS - 1
    second = await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)
    sent_while_held = len(server.counted)
    clock.now += 1
    await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)

    assert [
        _organism(turn.digest.review.checks).why_unchecked for turn in (first, second)
    ] == ["site_refused", "site_refused"]
    assert (sent_while_held, len(server.counted)) == (1, 2)


async def test_an_organism_count_the_site_does_not_answer_is_sent_next_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = ToolServer(refusal=_connect_error())
    _site(monkeypatch, _LARGE, server, _Pages())

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest
    await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)

    organism = _organism(digest.review.checks)
    assert (organism.status, organism.why_unchecked) == ("unchecked", "site_unanswered")
    assert (digest.success, digest.not_checked, len(server.counted)) == (False, True, 2)


class _Unreached:
    async def get_strategy(self, strategy_id: int) -> WDKStrategyDetails:
        raise _connect_error()


async def test_a_strategy_read_the_site_does_not_answer_gives_no_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_columns(monkeypatch, ColumnSite({}, {}))
    monkeypatch.setattr(site_counts, "get_strategy_api", lambda _site: _Unreached())

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    assert [(c.kind, c.why_unchecked) for c in digest.review.checks] == [
        ("step_valid", "site_unanswered"),
        ("bound_values", "site_unanswered"),
        ("result_count", "site_unanswered"),
    ]
    assert (digest.success, digest.passed, digest.not_checked) == (False, False, True)
