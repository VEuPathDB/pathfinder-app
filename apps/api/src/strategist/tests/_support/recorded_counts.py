"""The counts and the site-search answers the measurement fixtures recorded."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

import httpx
import pytest
from veupathdb.domain.parameters import ParamValue, StringValue, to_wire
from veupathdb.errors import WDKError
from veupathdb.json_types import JSONObject
from veupathdb.model import CamelModel
from veupathdb.wdk import (
    DocumentTypeFilter,
    SiteSearchResponse,
    VEuPathDBClient,
    WDKAnswer,
    WDKFilterValue,
    WDKSearchConfig,
)

from strategist.services.strategies import measurements
from strategist.tests._support.recorded_columns import recorded_body

PERCENTILE_SEARCH = (
    "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"
)
GIARDIA_WB = "Giardia Assemblage A isolate WB"
CRYPTO_IOWA = "Cryptosporidium parvum Iowa II"
# The fifteen Toxoplasma gondii strains the cryptodb clade tree holds.
TGON_STRAINS = (
    "tgar",
    "tgca",
    "tgco",
    "tgee",
    "tgfo",
    "tggd",
    "tggt",
    "tgma",
    "tgon",
    "tgop",
    "tgru",
    "tgta",
    "tgtg",
    "tgva",
    "tgve",
)


PERCENTILE_ANTISENSE = (
    "Asexual blood stages and salivary gland sporozoite and midgut oocyst "
    "transcriptomes - Antisense"
)
# Each other reading of the percentile bind, and the report that counted it.
_PERCENTILE_READINGS = (
    ("min_expression_percentile", "0", "report_percentile_min_0"),
    ("profileset_generic", PERCENTILE_ANTISENSE, "report_percentile_antisense"),
    ("protein_coding_only", "no", "report_percentile_all_genes"),
    ("any_or_all", "all", "report_percentile_all_samples"),
)
# The body plasmodb answers a percentile report on a channel its dataset lacks.
_INTERNAL_ERROR = "Internal Error"


def percentile_count(_search: str, params: Mapping[str, ParamValue]) -> int:
    """The recorded plasmodb percentile counts. The site fails on a second
    channel, and a maximum of 0 keeps no gene."""
    if wire(params, "channel") == "Channel 2":
        raise WDKError(_INTERNAL_ERROR, status=500)
    if wire(params, "max_expression_percentile") == "0":
        return 0
    return next(
        (recorded_count(f) for n, v, f in _PERCENTILE_READINGS if wire(params, n) == v),
        recorded_count("report_percentile_min_80"),
    )


def recorded_count(fixture: str) -> int:
    """The total one recorded standard report answered."""
    return WDKAnswer.model_validate(recorded_body(fixture)).meta.records_returned()


def recorded_site_search(fixture: str) -> SiteSearchResponse:
    return SiteSearchResponse.model_validate(recorded_body(fixture))


CountAt = Callable[[str, Mapping[str, ParamValue]], int | None]


class _CountingSite(VEuPathDBClient):
    def __init__(
        self,
        site_id: str,
        at: CountAt,
        asked: list[str],
        budgets: list[float | None] | None,
    ) -> None:
        super().__init__(
            f"https://qa.{site_id}.org/service",
            site_id=site_id,
            transport=httpx.MockTransport(self._answer),
        )
        self._at = at
        self._asked = asked
        self._budgets = budgets

    async def run_search_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        report_config: JSONObject | None = None,
        *,
        view_filters: Sequence[WDKFilterValue] | None = None,
        budget_seconds: float | None = None,
    ) -> WDKAnswer:
        if self._budgets is not None:
            self._budgets.append(budget_seconds)
        return await super().run_search_report(
            record_type,
            search_name,
            search_config,
            report_config,
            view_filters=view_filters,
            budget_seconds=budget_seconds,
        )

    def _answer(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/app"):
            return httpx.Response(200, text="")
        search_name = request.url.path.split("/")[-3]
        sent = _ReportRequest.model_validate_json(request.content)
        self._asked.append(search_name)
        try:
            count = self._at(
                search_name,
                {
                    name: StringValue(value=value)
                    for name, value in sent.search_config.parameters.items()
                },
            )
        except WDKError as refused:
            return httpx.Response(refused.status, text=str(refused))
        meta = {} if count is None else {"totalCount": count}
        return httpx.Response(200, json={"meta": meta, "records": []})


class _ReportRequest(CamelModel):
    search_config: WDKSearchConfig


def serve_counts(
    monkeypatch: pytest.MonkeyPatch,
    at: CountAt,
    budgets: list[float | None] | None = None,
) -> list[str]:
    """Answer each measured count from ``at`` through a site client, and record
    the searches sent and, into ``budgets``, the time each read was given."""
    asked: list[str] = []
    sites: dict[str, _CountingSite] = {}

    def _site(site_id: str) -> _CountingSite:
        if site_id not in sites:
            sites[site_id] = _CountingSite(site_id, at, asked, budgets)
        return sites[site_id]

    monkeypatch.setattr("veupathdb_mcp.wdk.plan_counts.get_wdk_client", _site)
    return asked


def wire(params: Mapping[str, ParamValue], name: str) -> str:
    return to_wire(params[name])


@dataclass
class SiteSearchDouble:
    """One site's search client, answering every phrase from one recording."""

    answer: SiteSearchResponse
    asked: list[tuple[str, list[str] | None]] = field(default_factory=list)

    async def search(
        self,
        search_text: str,
        *,
        document_type_filter: DocumentTypeFilter | None = None,
        organisms: list[str] | None = None,
        limit: int = 20,
    ) -> SiteSearchResponse:
        del document_type_filter, limit
        self.asked.append((search_text, organisms))
        return self.answer


@dataclass
class _Router:
    client: SiteSearchDouble

    def get_site_search_client(self, _site_id: str) -> SiteSearchDouble:
        return self.client


def serve_site_search(
    monkeypatch: pytest.MonkeyPatch, answer: SiteSearchResponse
) -> SiteSearchDouble:
    double = SiteSearchDouble(answer)
    monkeypatch.setattr(measurements, "get_site_router", lambda: _Router(double))
    return double


def no_measurements(monkeypatch: pytest.MonkeyPatch) -> None:
    """The site counts no other reading and its site search finds nothing."""
    serve_counts(monkeypatch, lambda _search, _params: None)
    serve_site_search(monkeypatch, SiteSearchResponse())
