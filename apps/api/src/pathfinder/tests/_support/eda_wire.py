"""The recorded EDA deployment, served over an httpx transport.

Everything but the network is real: the client, the services and the analysis
document a PATCH rewrites. The bodies are the pinned fixtures.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pytest

from pathfinder.integrations.eda import factory
from pathfinder.integrations.eda.client import EdaClient
from pathfinder.integrations.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
)
from pathfinder.services.eda import authoring, binding, catalog, compute

FIXTURE_DIR = (
    Path(__file__).resolve().parents[1] / "unit" / "integrations" / "eda" / "fixtures"
)

BASE_URL = "https://plasmodb.org/eda"
EDA_USER_ID = "9001"
JOB_ID = "b" * 32

PHENOTYPE_DATASET = "DS_53f554ec6a"
PHENOTYPE_STUDY = "STUDY_53f554ec6a"
PHENOTYPE_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
DE_STUDY = "STUDY_e973eadd57"


def fixture(name: str) -> Any:
    """One pinned EDA response, by file name without the suffix."""
    return json.loads((FIXTURE_DIR / f"{name}.json").read_text())


@dataclass
class AnalysisStore:
    """The upstream analysis document, as a read-patch-read really sees it."""

    detail: EdaAnalysisDetail
    patches: int = 0
    created: list[dict[str, Any]] = field(default_factory=list)

    def respond(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            self.created.append(json.loads(request.content))
            return httpx.Response(200, json={"analysisId": self.detail.analysis_id})
        if request.method != "PATCH":
            return httpx.Response(
                200, json=self.detail.model_dump(by_alias=True, mode="json")
            )
        self.patches += 1
        written = EdaAnalysisDescriptor.model_validate(
            json.loads(request.content)["descriptor"]
        )
        self.detail = self.detail.model_copy(
            update={
                "descriptor": written,
                "num_computations": len(written.computations),
            }
        )
        return httpx.Response(204)


def _counted(request: httpx.Request, count: int | None) -> httpx.Response:
    if count is not None:
        return httpx.Response(200, json={"count": count})
    filtered = json.loads(request.content)["filters"]
    name = "count_filtered" if filtered else "count_unfiltered"
    return httpx.Response(200, json=fixture(name))


def _recorded(path: str, study_id: str, study_fixture: str) -> str | None:
    """The fixture a read path answers with, or None when it is not a read."""
    if path.endswith("/permissions"):
        return "permissions"
    if path == "/eda/studies":
        return "studies_list"
    if path == f"/eda/studies/{study_id}":
        return study_fixture
    if path.endswith("/distribution"):
        return "distribution_categorical"
    if path.endswith("/statistics"):
        return "volcano_statistics"
    return None


def eda_transport(
    *,
    study_id: str,
    study_fixture: str,
    store: AnalysisStore | None = None,
    count: int | None = None,
) -> httpx.MockTransport:
    """The deployment one study lives in, plus that study's analysis document."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/analyses/" in path and store is not None:
            return store.respond(request)
        if path.endswith("/count"):
            return _counted(request, count)
        recorded = _recorded(path, study_id, study_fixture)
        if recorded is not None:
            return httpx.Response(200, json=fixture(recorded))
        if path.startswith("/eda/computes/"):
            return httpx.Response(200, json={"jobID": JOB_ID, "status": "complete"})
        return httpx.Response(404, json={"status": "not-found"})

    return httpx.MockTransport(handler)


def wire_eda(
    monkeypatch: pytest.MonkeyPatch, transport: httpx.MockTransport
) -> EdaClient:
    """Point every EDA seam at one client over ``transport``.

    The analysis routes are keyed by a WDK user id, which only WDK answers, so
    that one lookup is answered here too.
    """
    client = EdaClient(base_url=BASE_URL, transport=transport)
    for module in (catalog, authoring, compute, factory):
        monkeypatch.setattr(module, "get_eda_client", lambda _site: client)

    async def user_id(_site: str) -> str:
        return EDA_USER_ID

    monkeypatch.setattr(authoring, "resolve_eda_user_id", user_id)
    monkeypatch.setattr(binding, "resolve_eda_user_id", user_id)
    return client
