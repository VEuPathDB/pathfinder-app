"""open_eda_analysis creates the analysis, binds the thread and cards the state."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic_ai import RunContext
from pydantic_ai.exceptions import ModelRetry

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone import eda_analysis
from pathfinder.integrations.eda import factory as eda_factory
from pathfinder.integrations.eda.client import EdaClient
from pathfinder.integrations.eda.models import EdaPermissionEntry, EdaStudyDetail
from pathfinder.platform.context import veupathdb_auth_token_ctx
from pathfinder.services.eda import authoring, binding, catalog
from pathfinder.services.eda.catalog import UnknownEdaDatasetError
from pathfinder.tests._support.eda_doubles import (
    ANALYSIS_ID,
    RevisionCounter,
    no_gene_study,
    phenotype_study,
    read_analysis_detail,
    recorded_entity_counts,
)
from pathfinder.tests._support.eda_wire import (
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    PHENOTYPE_STUDY,
    fixture,
)


@pytest.fixture(autouse=True)
def revisions(monkeypatch: pytest.MonkeyPatch) -> RevisionCounter:
    counter = RevisionCounter()
    monkeypatch.setattr(binding, "bump_analysis_revision", counter.bump)
    return counter


@pytest.fixture(autouse=True)
def entity_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    """These tools are read through their chunks, not through the count wire."""
    monkeypatch.setattr(binding, "subset_entity_counts", recorded_entity_counts)


async def _noop_bind(**_kwargs: object) -> None:
    return None


async def _resolved(value: str) -> str:
    return value


async def _fake_user_id(_site_id: str) -> str:
    return "1216062453"


def _serve_study(monkeypatch: pytest.MonkeyPatch, resolver: object) -> None:
    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", resolver)
    monkeypatch.setattr(binding, "get_study_detail_for_dataset", resolver)


async def test_open_eda_analysis_creates_the_analysis_and_binds_the_conversation(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    bound: list[tuple[str, str, str]] = []

    async def open_it(_site: str, *, dataset_id: str, display_name: str) -> str:
        assert display_name
        assert dataset_id == PHENOTYPE_DATASET
        return ANALYSIS_ID

    async def bind(**kwargs: object) -> None:
        bound.append(
            (
                str(kwargs["dataset_id"]),
                str(kwargs["analysis_id"]),
                str(kwargs["site_id"]),
            )
        )

    monkeypatch.setattr(binding, "open_analysis", open_it)
    monkeypatch.setattr(binding, "bind_conversation_analysis", bind)
    monkeypatch.setattr(binding, "read_analysis", read_analysis_detail)
    _serve_study(monkeypatch, phenotype_study)

    returned = await eda_analysis.open_eda_analysis(
        lead_ctx, dataset_id=PHENOTYPE_DATASET, purpose="keep the P. berghei rows"
    )
    assert returned.return_value.analysis_id == ANALYSIS_ID
    assert returned.return_value.study_id == PHENOTYPE_STUDY
    assert returned.return_value.gene_entity_id == PHENOTYPE_ENTITY
    assert bound == [(PHENOTYPE_DATASET, ANALYSIS_ID, "plasmodb")]
    kinds = [chunk.type for chunk in returned.metadata]
    assert kinds == ["data-eda.analysis-state"]
    assert returned.metadata[0].data["revision"] == 1


async def test_open_eda_analysis_cuts_a_long_purpose_before_the_wire(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The user service refuses a displayName over 50 UTF-8 bytes."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/permissions"):
            return httpx.Response(200, json=fixture("permissions"))
        if "/analyses/" in request.url.path and request.method == "POST":
            return httpx.Response(200, json={"analysisId": ANALYSIS_ID})
        return httpx.Response(404, json={"status": "not-found"})

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(authoring, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(eda_factory, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(authoring, "resolve_eda_user_id", _fake_user_id)
    monkeypatch.setattr(binding, "bind_conversation_analysis", _noop_bind)
    monkeypatch.setattr(binding, "read_analysis", read_analysis_detail)
    _serve_study(monkeypatch, phenotype_study)

    purpose = (
        "Febrile versus normal differential expression in the LRR5 and DHC "
        "heat-shock RNA-seq study"
    )
    assert len(purpose) == 90
    token = veupathdb_auth_token_ctx.set("t")
    try:
        returned = await eda_analysis.open_eda_analysis(
            lead_ctx, dataset_id="DS_16bc228c8e", purpose=purpose
        )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert returned.return_value.analysis_id == ANALYSIS_ID
    posts = [r for r in seen if r.method == "POST" and "/analyses/" in r.url.path]
    sent = json.loads(posts[0].content)["displayName"]
    assert sent == "Febrile versus normal differential expression in t"
    assert len(sent.encode()) == 50


async def test_opening_a_second_analysis_replaces_the_binding(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """One conversation binds at most one open analysis at a time."""
    calls: list[str] = []

    async def bind(**kwargs: object) -> None:
        calls.append(str(kwargs["analysis_id"]))

    monkeypatch.setattr(binding, "bind_conversation_analysis", bind)
    monkeypatch.setattr(binding, "open_analysis", lambda *_a, **_k: _resolved("A"))
    monkeypatch.setattr(binding, "read_analysis", read_analysis_detail)
    _serve_study(monkeypatch, phenotype_study)
    await eda_analysis.open_eda_analysis(
        lead_ctx, dataset_id=PHENOTYPE_DATASET, purpose="first"
    )
    monkeypatch.setattr(binding, "open_analysis", lambda *_a, **_k: _resolved("B"))
    await eda_analysis.open_eda_analysis(
        lead_ctx, dataset_id=PHENOTYPE_DATASET, purpose="second"
    )
    assert calls == ["A", "B"]


async def test_opening_an_analysis_on_a_study_with_no_gene_id_warns_the_model(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """A study with no gene column can be explored and cannot be exported."""
    monkeypatch.setattr(binding, "open_analysis", lambda *_a, **_k: _resolved("A"))
    monkeypatch.setattr(binding, "read_analysis", read_analysis_detail)
    monkeypatch.setattr(binding, "bind_conversation_analysis", _noop_bind)
    _serve_study(monkeypatch, no_gene_study)

    returned = await eda_analysis.open_eda_analysis(
        lead_ctx, dataset_id=PHENOTYPE_DATASET, purpose="explore"
    )
    assert "cannot export" in returned.return_value.guidance
    assert returned.return_value.can_export_rows is False


async def test_opening_an_analysis_on_an_unknown_dataset_creates_nothing(
    monkeypatch: pytest.MonkeyPatch, lead_ctx: RunContext[LeadDeps]
) -> None:
    """The study resolves first, so a bad id never leaves an orphan analysis."""
    opened: list[str] = []

    async def raises(
        _site: str, _dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        unknown = "DS_nope"
        raise UnknownEdaDatasetError(unknown, ["DS_a"])

    async def open_it(_site: str, **_kwargs: object) -> str:
        opened.append("opened")
        return "A"

    monkeypatch.setattr(eda_analysis, "get_study_detail_for_dataset", raises)
    monkeypatch.setattr(binding, "open_analysis", open_it)
    monkeypatch.setattr(binding, "bind_conversation_analysis", _noop_bind)
    with pytest.raises(ModelRetry) as excinfo:
        await eda_analysis.open_eda_analysis(
            lead_ctx, dataset_id="DS_nope", purpose="explore"
        )
    assert "search_eda_studies" in str(excinfo.value)
    assert opened == []
