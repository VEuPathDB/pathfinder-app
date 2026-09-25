"""A VDI service and an EDA permissions read that answer with recorded bodies."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from veupathdb.eda import EdaClient
from veupathdb.testing import FIXTURE_ROOT
from veupathdb.testing.eda_fixtures import FIXTURE_DIR
from veupathdb.wdk import VdiClient

from pathfinder.services.eda.catalog import StudyCard

_VDI_BASE_URL = "https://plasmodb.org/vdi"
_EDA_BASE_URL = "https://plasmodb.org/eda"
_USER_STUDY = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "eda"
    / "user_study_permission.json"
)
_NOT_FOUND = {"status": "not-found"}


def vdi_body(name: str) -> Any:
    """One body VDI answered, as the client repository recorded it."""
    return json.loads((FIXTURE_ROOT / "vdi" / f"{name}.json").read_text())


def installed_user_study() -> tuple[str, Any]:
    """The owner's permission entry for an installed upload, and its dataset id."""
    recorded = json.loads(_USER_STUDY.read_text())
    return recorded["datasetId"], recorded["entry"]


def permissions_body(*, with_user_study: bool) -> Any:
    """The recorded ``/permissions`` answer, with the recorded upload's entry or not."""
    body = json.loads((FIXTURE_DIR / "permissions.json").read_text())
    if with_user_study:
        dataset_id, entry = installed_user_study()
        body["perDataset"][dataset_id] = entry
    return body


@dataclass
class RecordedVdi:
    """Serves the owned listing and each dataset's statuses.

    ``statuses`` holds, per dataset id, the bodies ``GET /datasets/{id}`` answers
    in order; the last one repeats. An id with none answers 404, as a deleted
    dataset does.
    """

    listing: list[Any] = field(default_factory=lambda: vdi_body("datasets_owned"))
    statuses: dict[str, list[Any]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path.removeprefix("/vdi")
        if path == "/datasets":
            return httpx.Response(200, json=self.listing)
        vdi_id = path.removeprefix("/datasets/")
        served = self.statuses.get(vdi_id, [])
        if not served:
            return httpx.Response(404, json=_NOT_FOUND)
        body = served.pop(0) if len(served) > 1 else served[0]
        return httpx.Response(200, json=body)

    def client(self) -> VdiClient:
        return VdiClient(
            base_url=_VDI_BASE_URL, transport=httpx.MockTransport(self.handler)
        )

    def calls(self) -> list[str]:
        """Every request as ``METHOD /path``, in the order it was sent."""
        return [f"{r.method} {r.url.path.removeprefix('/vdi')}" for r in self.requests]


@dataclass
class RecordedPermissions:
    """Serves ``/permissions`` and counts the reads."""

    bodies: list[Any]
    reads: int = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        del request
        self.reads += 1
        body = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        return httpx.Response(200, json=body)

    def client(self) -> EdaClient:
        return EdaClient(
            base_url=_EDA_BASE_URL, transport=httpx.MockTransport(self.handler)
        )


async def no_own_datasets(site_id: str, query: str, limit: int = 5) -> list[StudyCard]:
    """An account with no installed uploads, in place of the study search's VDI read."""
    del site_id, query, limit
    return []
