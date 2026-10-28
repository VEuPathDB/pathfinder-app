from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import pytest
from veupathdb.errors import WDKError
from veupathdb.wdk import WDKAnswer, WDKStrategyDetails

from pathfinder.ai.graph._lead_events import _verified
from pathfinder.ai.lead.ledger_render import render_verification_full
from pathfinder.ai.lead.ledger_sections import VerificationSection
from pathfinder.domain.site_checks import SiteCheck
from pathfinder.domain.strategy.constraints import ConstraintKind
from pathfinder.services.experiment import paged_tally
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
_BY_VALUE = (
    "https://qa.plasmodb.org/plasmo.qa/service/users/1/steps/"
    f"{_EXPORTED}/columns/organism/reports/byValue"
)


def _failed_after(cause: Exception, status: int) -> WDKError:
    failed = WDKError(f"Request failed after retries: {cause}", status=status)
    failed.__cause__ = cause
    return failed


def _internal_error() -> WDKError:
    request = httpx.Request("POST", _BY_VALUE)
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
                "totalCount": len(organisms),
                "responseCount": len(organisms),
                "displayTotalCount": len(organisms),
                "viewTotalCount": len(organisms),
                "displayViewTotalCount": len(organisms),
                "recordClassName": "transcript",
                "attributes": ["organism_full"],
            },
            "records": [
                {
                    "displayName": f"PF3D7_{n:07d}",
                    "recordClassName": "TranscriptRecordClasses.TranscriptRecordClass",
                    "attributes": {"organism_full": organism},
                    "id": [{"name": "source_id", "value": f"PF3D7_{n:07d}.1"}],
                }
                for n, organism in enumerate(organisms)
            ],
        }
    )


@dataclass
class _Pages:
    answer: WDKAnswer
    asked: list[tuple[int, list[str] | None, dict[str, int] | None]] = field(
        default_factory=list
    )

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
    ) -> WDKAnswer:
        self.asked.append((step_id, attributes, pagination))
        return self.answer


def _refusing_site(
    monkeypatch: pytest.MonkeyPatch, size: int, refusal: WDKError, pages: _Pages
) -> None:
    serve_the_site(monkeypatch, _sized(size), [column_catalog()])
    serve_columns(monkeypatch, ColumnSite({}, {}))
    serve(
        monkeypatch,
        TallySite(column_catalog(), step_count=size),
        ToolServer(refusal=refusal),
    )
    monkeypatch.setattr(paged_tally, "get_strategy_api", lambda _site: pages)


def _organism(checks: list[SiteCheck]) -> SiteCheck:
    [organism] = [c for c in checks if c.kind is ConstraintKind.ORGANISM]
    return organism


async def test_a_refused_count_of_a_small_result_is_counted_from_its_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _Pages(_answer(*[_PF] * 477, _PF_IT, _PF_IT))
    _refusing_site(monkeypatch, 479, _internal_error(), pages)

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    assert pages.asked == [
        (_EXPORTED, ["organism_full"], {"offset": 0, "numRecords": 2000})
    ]
    assert _organism(digest.review.checks) == SiteCheck(
        kind=ConstraintKind.ORGANISM,
        subject=_PF,
        status="fail",
        evidence=(
            f"2 of the 479 records of step {_EXPORTED} ('Text') hold organisms the "
            f"strategy does not select: {_PF_IT} (2)"
        ),
        requirement=f"organism:{_PF}",
    )
    assert (digest.success, digest.not_checked) == (False, False)


async def test_a_refused_count_of_records_of_the_selected_organism_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _Pages(_answer(*[f"<i>{_PF}</i>"] * 479))
    _refusing_site(monkeypatch, 479, _internal_error(), pages)

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    organism = _organism(digest.review.checks)
    assert (digest.success, digest.passed, organism.status, organism.evidence) == (
        True,
        True,
        "pass",
        (
            f"all 479 records of step {_EXPORTED} ('Text') hold an organism the "
            f"strategy selects: {_PF} (479)"
        ),
    )


async def test_a_refused_count_of_a_large_result_is_refused_and_still_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _Pages(_answer())
    _refusing_site(monkeypatch, 2001, _internal_error(), pages)

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


async def test_an_organism_count_the_site_does_not_answer_gives_no_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = _Pages(_answer())
    _refusing_site(monkeypatch, 479, _connect_error(), pages)

    digest = (await verify(monkeypatch, _exported_deps(), UNANSWERED_DIGEST)).digest

    organism = _organism(digest.review.checks)
    assert pages.asked == []
    assert (organism.status, organism.why_unchecked) == ("unchecked", "site_unanswered")
    assert (digest.success, digest.not_checked) == (False, True)


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
