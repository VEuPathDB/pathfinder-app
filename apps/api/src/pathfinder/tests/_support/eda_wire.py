"""The recorded EDA deployment, served over an httpx transport.

Everything but the network is real: the client, the services and the analysis
document a PATCH rewrites. The bodies are the pinned fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest
from veupathdb.eda import (
    EdaAnalysesClient,
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaClient,
    analysis_descriptor_patch,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb.wdk import get_site

from pathfinder.services.eda import authoring, binding, catalog, compute, gene_subset

BASE_URL = "https://plasmodb.org/eda"
EDA_USER_ID = "9001"
JOB_ID = "b" * 32

PHENOTYPE_DATASET = "DS_53f554ec6a"
PHENOTYPE_STUDY = "STUDY_53f554ec6a"
PHENOTYPE_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
DE_STUDY = "STUDY_e973eadd57"

# The size of each entity of the differential-expression study: its samples,
# and one row per gene in each sample.
DE_ENTITY_SIZES = {"ENT_8151325d": 12, "ENT_fd574cd6": 68640}

# The recorded gene-id distributions of each study, under its example subset
# and under none, by the name of the study's detail fixture.
_GENE_ID_DISTRIBUTIONS = {
    "study_detail_phenotype": "gene_id_distribution_phenotype",
    "study_detail_de": "gene_id_distribution_de",
}


def fixture(name: str) -> Any:
    """One pinned EDA response, by file name without the suffix."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


def phenotype_overview() -> dict[str, Any]:
    """The catalog row for the phenotype study, from its permission entry.

    The recorded ``/studies`` slice stops before this study, and the permission
    entry carries every field the overview needs.
    """
    entry = fixture("permissions")["perDataset"][PHENOTYPE_DATASET]
    return {
        "id": PHENOTYPE_STUDY,
        "datasetId": PHENOTYPE_DATASET,
        "sha1hash": entry["sha1Hash"],
        "sourceType": "curated",
        "displayName": entry["displayName"],
        "shortDisplayName": entry["shortDisplayName"],
        "description": entry["description"],
        "lastModified": "2026-05-27T20:00:00-04:00",
    }


@dataclass
class AnalysisStore:
    """The upstream analysis document, as a read-patch-read really sees it."""

    detail: EdaAnalysisDetail
    patches: int = 0
    created: list[dict[str, Any]] = field(default_factory=list)
    patched: list[dict[str, Any]] = field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.created.append(json.loads(request.content))
            return httpx.Response(200, json={"analysisId": self.detail.analysis_id})
        if request.method != "PATCH":
            return httpx.Response(200, json=self._stored())
        self.patches += 1
        body = json.loads(request.content)
        self.patched.append(body)
        written = EdaAnalysisDescriptor.model_validate(body["descriptor"])
        self.detail = self.detail.model_copy(
            update={
                "descriptor": written,
                "num_computations": len(written.computations),
            }
        )
        return httpx.Response(204)

    def _stored(self) -> dict[str, Any]:
        """The document as the site stores it: each node as it was written."""
        summary = self.detail.model_dump(
            by_alias=True, mode="json", exclude={"descriptor"}
        )
        return {
            **summary,
            "descriptor": analysis_descriptor_patch(self.detail.descriptor),
        }


def entity_size(path: str, sizes: Mapping[str, int]) -> httpx.Response:
    """The size of the entity a ``/count`` path names."""
    return httpx.Response(200, json={"count": sizes[path.split("/")[-2]]})


def _counted(
    request: httpx.Request, sizes: Mapping[str, int] | None, *, filtered_empty: bool
) -> httpx.Response:
    filtered = bool(json.loads(request.content)["filters"])
    if filtered and filtered_empty:
        return httpx.Response(200, json={"count": 0})
    if sizes is not None:
        return entity_size(request.url.path, sizes)
    return httpx.Response(
        200, json=fixture("count_filtered" if filtered else "count_unfiltered")
    )


def gene_id_distribution(study_fixture: str, *, filtered: bool) -> str:
    """The fixture that holds the gene ids of ``study_fixture`` under one subset."""
    subset = "filtered" if filtered else "unfiltered"
    return f"{_GENE_ID_DISTRIBUTIONS[study_fixture]}_{subset}"


def distribution_response(
    path: str, body: Any, study_fixture: str
) -> httpx.Response | None:
    """The gene ids of ``study_fixture`` or the recorded species distribution.

    None answers a path that is not a distribution.
    """
    if path.endswith("/variables/VEUPATHDB_GENE_ID/distribution"):
        name = gene_id_distribution(study_fixture, filtered=bool(body["filters"]))
        return httpx.Response(200, json=fixture(name))
    if path.endswith("/distribution"):
        return httpx.Response(200, json=fixture("distribution_categorical"))
    return None


def _recorded(path: str, study_id: str, study_fixture: str) -> str | None:
    """The fixture a read path answers with, or None when it is not a read."""
    if path.endswith("/permissions"):
        return "permissions"
    if path == "/eda/studies":
        return "studies_list"
    if path == f"/eda/studies/{study_id}":
        return study_fixture
    if path.endswith("/statistics"):
        return "volcano_statistics"
    return None


def eda_transport(
    *,
    study_id: str,
    study_fixture: str,
    store: AnalysisStore | None = None,
    entity_sizes: Mapping[str, int] | None = None,
    filtered_empty: bool = False,
) -> httpx.MockTransport:
    """The deployment one study lives in, plus that study's analysis document.

    ``entity_sizes`` answers every count of a study whose subset selects every
    row. ``filtered_empty`` answers 0 to a count under any filter.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/analyses/" in path and store is not None:
            return store.respond(request)
        if path.endswith("/count"):
            return _counted(request, entity_sizes, filtered_empty=filtered_empty)
        body = json.loads(request.content) if request.content else None
        distribution = distribution_response(path, body, study_fixture)
        if distribution is not None:
            return distribution
        recorded = _recorded(path, study_id, study_fixture)
        if recorded is not None:
            return httpx.Response(200, json=fixture(recorded))
        if path.startswith("/eda/computes/"):
            return httpx.Response(200, json={"jobID": JOB_ID, "status": "complete"})
        return httpx.Response(404, json={"status": "not-found"})

    return httpx.MockTransport(handler)


def wire_eda_client(monkeypatch: pytest.MonkeyPatch, client: EdaClient) -> None:
    """Point every service that opens an EDA client or analysis store at ``client``."""

    def analyses(site_id: str) -> EdaAnalysesClient:
        return EdaAnalysesClient(client=client, project_id=get_site(site_id).project_id)

    for module in (catalog, authoring, compute, gene_subset):
        monkeypatch.setattr(module, "get_eda_client", lambda _site: client)
    for module in (authoring, binding):
        monkeypatch.setattr(module, "get_eda_analyses_client", analyses)


def wire_eda(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport
) -> EdaClient:
    """Point every EDA seam at one client over ``transport``.

    The analysis routes are keyed by a WDK user id, which only WDK answers, so
    that one lookup is answered here too.
    """
    client = EdaClient(base_url=BASE_URL, transport=transport)
    wire_eda_client(monkeypatch, client)

    async def user_id(_site: str) -> str:
        return EDA_USER_ID

    monkeypatch.setattr(authoring, "resolve_eda_user_id", user_id)
    monkeypatch.setattr(binding, "resolve_eda_user_id", user_id)
    return client
