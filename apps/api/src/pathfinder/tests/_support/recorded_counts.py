"""The counts and the site-search answers the measurement fixtures recorded."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import pytest
from veupathdb.domain.parameters import ParamValue, to_wire
from veupathdb.errors import WDKError
from veupathdb.wdk import DocumentTypeFilter, SiteSearchResponse, WDKAnswer

from pathfinder.services.strategies import measurements
from pathfinder.tests._support.recorded_columns import recorded_body

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


def serve_counts(
    monkeypatch: pytest.MonkeyPatch,
    at: CountAt,
    budgets: list[float | None] | None = None,
) -> list[str]:
    """Answer each measured count from ``at``, and record the searches asked
    and, into ``budgets``, the time each read was given."""
    asked: list[str] = []

    async def _count(
        _site_id: str,
        _record_type: str,
        search_name: str,
        params: Mapping[str, ParamValue],
        *,
        timeout_seconds: float | None = None,
    ) -> int | None:
        asked.append(search_name)
        if budgets is not None:
            budgets.append(timeout_seconds)
        return at(search_name, params)

    monkeypatch.setattr(measurements, "count_search_answer", _count)
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
