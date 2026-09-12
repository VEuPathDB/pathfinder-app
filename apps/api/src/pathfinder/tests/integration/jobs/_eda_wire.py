"""The EDA doubles the durable-compute tests share.

One recorded wire for the study, the job, the statistics and the analysis
document, plus the thread binding the worker impl reads the analysis through.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import count
from typing import Any
from uuid import UUID

import httpx
import pytest
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaClient,
    EdaComputation,
    EdaFilter,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.jobs.impls import eda_compute_impl
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.services.eda import authoring, binding
from pathfinder.tests._support.eda_wire import AnalysisStore, wire_eda_client

FIXTURES = FIXTURE_DIR

STUDY = "STUDY_e973eadd57"
DATASET = "DS_e973eadd57"
ANALYSIS = "t4fszEJ"
JOB = "a" * 32

# Every sample of the study, because the subset names both of its conditions.
ENTITY_SIZES = {"ENT_8151325d": 12, "ENT_fd574cd6": 66132}

# The recorded slice of the live volcano. The live lane pins 5511 and 1543.
FIXTURE_ROWS = 201
FIXTURE_RETAINED = 67

ARGS: dict[str, Any] = {
    "identifier_variable": {
        "entity_id": "ENT_fd574cd6",
        "variable_id": "VEUPATHDB_GENE_ID",
    },
    "value_variable": {
        "entity_id": "ENT_fd574cd6",
        "variable_id": "SEQUENCE_READ_COUNT_SENSE",
    },
    "comparator_variable": {
        "entity_id": "ENT_8151325d",
        "variable_id": "VAR_081ab087",
    },
    "group_a_labels": ["normal"],
    "group_b_labels": ["febrile"],
    "method": "DESeq",
}

SUBSET: list[EdaFilter] = [
    EdaStringSetFilter(
        entity_id="ENT_8151325d",
        variable_id="VAR_081ab087",
        string_set=["febrile", "normal"],
    ),
]


async def bound(*, conversation_id: UUID) -> ConversationAnalysisView | None:
    del conversation_id
    return ConversationAnalysisView(
        site_id="plasmodb",
        dataset_id=DATASET,
        analysis_id=ANALYSIS,
        revision=2,
    )


async def unbound(*, conversation_id: UUID) -> ConversationAnalysisView | None:
    del conversation_id
    return None


def detail(
    filters: Sequence[EdaFilter] = (),
    computations: Sequence[EdaComputation] = (),
) -> EdaAnalysisDetail:
    return EdaAnalysisDetail(
        analysis_id=ANALYSIS,
        study_id=DATASET,
        num_filters=len(list(filters)),
        num_computations=len(list(computations)),
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=list(filters)),
            computations=list(computations),
        ),
    )


def permissions() -> dict[str, Any]:
    """The fixture body, plus the entry that resolves this test's dataset."""
    body: dict[str, Any] = json.loads((FIXTURES / "permissions.json").read_text())
    entry = next(iter(body["perDataset"].values()))
    body["perDataset"][DATASET] = {**entry, "studyId": STUDY}
    return body


@dataclass(frozen=True)
class Call:
    path: str
    body: Any


def _recorded(path: str) -> httpx.Response | None:
    """The response a read path answers with, or None when it is a job poll."""
    if path.endswith("/permissions"):
        return httpx.Response(200, json=permissions())
    if path == "/eda/studies":
        return httpx.Response(200, json={"studies": []})
    if path.endswith("/count"):
        return httpx.Response(200, json={"count": ENTITY_SIZES[path.split("/")[5]]})
    if path.startswith("/eda/studies/"):
        return httpx.Response(
            200, json=json.loads((FIXTURES / "study_detail_de.json").read_text())
        )
    if path.endswith("/statistics"):
        return httpx.Response(
            200, json=json.loads((FIXTURES / "volcano_statistics.json").read_text())
        )
    return None


def handler(
    statuses: Sequence[str], calls: list[Call], store: AnalysisStore
) -> httpx.MockTransport:
    remaining = list(statuses)

    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        content = request.content
        calls.append(Call(path=path, body=json.loads(content) if content else None))
        if "/analyses/" in path:
            return store.respond(request)
        recorded = _recorded(path)
        if recorded is not None:
            return recorded
        status = remaining.pop(0) if remaining else "complete"
        return httpx.Response(200, json={"jobID": JOB, "status": status})

    return httpx.MockTransport(handle)


@dataclass
class Wire:
    """One installed EDA double: its client, its calls and its writes."""

    client: EdaClient
    calls: list[Call]
    store: AnalysisStore
    chunks: list[dict[str, Any]]

    @property
    def applied(self) -> list[EdaComputation]:
        """The computations the analysis document now carries."""
        return list(self.store.detail.descriptor.computations)


def install(
    monkeypatch: pytest.MonkeyPatch,
    *statuses: str,
    real_binding: bool = False,
) -> Wire:
    """Serve the EDA wire from a recorded transport, for both service modules.

    ``real_binding`` leaves the thread's binding to the real repository, so a
    test with a database reads and counts the row the tool bound.
    """
    calls: list[Call] = []
    store = AnalysisStore(detail=detail(SUBSET))
    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=handler(statuses, calls, store)
    )

    async def user_id(_site: str) -> str:
        return "9001"

    wire_eda_client(monkeypatch, client)
    monkeypatch.setattr(authoring, "resolve_eda_user_id", user_id)
    monkeypatch.setattr(binding, "resolve_eda_user_id", user_id)
    chunks: list[dict[str, Any]] = []
    revisions = count(1)

    async def bump(*, conversation_id: UUID) -> int:
        del conversation_id
        return next(revisions)

    async def record(*, conversation_id: UUID, chunk: dict[str, Any]) -> int:
        del conversation_id
        chunks.append(chunk)
        return len(chunks)

    if not real_binding:
        monkeypatch.setattr(eda_compute_impl, "bound_conversation_analysis", bound)
        monkeypatch.setattr(eda_compute_impl, "bump_analysis_revision", bump)
        monkeypatch.setattr(eda_compute_impl, "append_chunk", record)
    monkeypatch.setattr(eda_compute_impl, "_POLL_SECONDS", 0.0)
    return Wire(client=client, calls=calls, store=store, chunks=chunks)
