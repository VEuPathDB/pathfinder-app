"""The EDA client against the recorded wire, with no network."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from pathfinder.integrations.eda.analyses import EdaAnalysesClient
from pathfinder.integrations.eda.client import EdaClient
from pathfinder.integrations.eda.errors import (
    EdaBadRequestError,
    EdaForbiddenError,
    EdaInvalidInputError,
)
from pathfinder.integrations.eda.models import (
    EdaAnalysisDescriptor,
    EdaBinSpec,
    EdaComparator,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaNewAnalysis,
    EdaStringSetFilter,
    EdaSubsetDescriptor,
    EdaVariableSpec,
)
from pathfinder.integrations.veupathdb.client import VEuPathDBClient
from pathfinder.platform.context import veupathdb_auth_token_ctx
from pathfinder.platform.errors import WDKLoginRequiredError

FIXTURES = (
    Path(__file__).resolve().parents[2] / "unit" / "integrations" / "eda" / "fixtures"
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _registered_token() -> Iterator[None]:
    """Every hermetic call travels as a registered user."""
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def _fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text())


def _client(handler: httpx.MockTransport) -> EdaClient:
    return EdaClient(base_url="https://plasmodb.org/eda", transport=handler)


def _species_filter() -> EdaStringSetFilter:
    return EdaStringSetFilter(
        entity_id="GENE_PHENOTYPE_DATA_ENTITY",
        variable_id="VAR_035294d0",
        string_set=["P. berghei"],
    )


def _de_config() -> EdaDifferentialExpressionConfig:
    return EdaDifferentialExpressionConfig(
        identifier_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="VEUPATHDB_GENE_ID"
        ),
        value_variable=EdaVariableSpec(
            entity_id="ENT_fd574cd6", variable_id="SEQUENCE_READ_COUNT_SENSE"
        ),
        comparator=EdaComparator(
            variable=EdaVariableSpec(
                entity_id="ENT_8151325d", variable_id="VAR_081ab087"
            ),
            group_a=[EdaLabeledRange(label="normal")],
            group_b=[EdaLabeledRange(label="febrile")],
        ),
    )


async def test_the_request_carries_the_authorization_cookie() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_fixture("studies_list.json"))

    token = veupathdb_auth_token_ctx.set("token-abc")
    try:
        client = _client(httpx.MockTransport(handler))
        await client.list_studies()
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert "Authorization=token-abc" in seen[0].headers["cookie"]
    assert seen[0].url.path == "/eda/studies"


async def test_a_request_with_no_token_never_reaches_the_wire() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"count": 0})

    token = veupathdb_auth_token_ctx.set(None)
    client = _client(httpx.MockTransport(handler))
    try:
        with pytest.raises(WDKLoginRequiredError):
            await client.count(study_id="S", entity_id="E", filters=[])
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert calls == []


async def test_list_studies_parses_the_recorded_catalog() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _r: httpx.Response(200, json=_fixture("studies_list.json"))
        )
    )
    studies = await client.list_studies()
    await client.close()
    assert studies
    assert any(s.source_type == "user_submitted" for s in studies)


async def test_get_study_unwraps_the_study_envelope() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_fixture("study_detail_phenotype.json"))

    client = _client(httpx.MockTransport(handler))
    study = await client.get_study("STUDY_53f554ec6a")
    await client.close()
    assert seen[0].url.path == "/eda/studies/STUDY_53f554ec6a"
    assert study.id == "STUDY_53f554ec6a"
    assert study.root_entity.id == "GENE_PHENOTYPE_DATA_ENTITY"


async def test_get_permissions_returns_the_resolution_map() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _r: httpx.Response(200, json=_fixture("permissions.json"))
        )
    )
    per_dataset = await client.get_permissions()
    await client.close()
    assert per_dataset["DS_53f554ec6a"].study_id == "STUDY_53f554ec6a"


async def test_count_posts_the_filter_array_and_returns_an_int() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"count": 4011})

    client = _client(httpx.MockTransport(handler))
    count = await client.count(
        study_id="STUDY_53f554ec6a",
        entity_id="GENE_PHENOTYPE_DATA_ENTITY",
        filters=[_species_filter()],
    )
    await client.close()
    assert count == 4011
    assert seen[0] == {
        "filters": [
            {
                "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
                "variableId": "VAR_035294d0",
                "type": "stringSet",
                "stringSet": ["P. berghei"],
            }
        ]
    }


async def test_a_distribution_omits_the_bin_spec_for_a_categorical_variable() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_fixture("distribution_categorical.json"))

    client = _client(httpx.MockTransport(handler))
    response = await client.distribution(
        study_id="STUDY_53f554ec6a",
        entity_id="GENE_PHENOTYPE_DATA_ENTITY",
        variable_id="VAR_035294d0",
        filters=[],
    )
    await client.close()
    assert seen[0].url.path == (
        "/eda/studies/STUDY_53f554ec6a/entities/GENE_PHENOTYPE_DATA_ENTITY"
        "/variables/VAR_035294d0/distribution"
    )
    assert json.loads(seen[0].content) == {"filters": [], "valueSpec": "count"}
    assert response.statistics.subset_size == 4279
    assert response.histogram[0].bin_label == "P. berghei"
    assert response.histogram[0].value == 4011


async def test_a_distribution_sends_a_bin_spec_when_one_is_given() -> None:
    seen: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=_fixture("distribution_categorical.json"))

    client = _client(httpx.MockTransport(handler))
    await client.distribution(
        study_id="S",
        entity_id="E",
        variable_id="V",
        filters=[],
        bin_spec=EdaBinSpec(bin_width=7, bin_units="day"),
    )
    await client.close()
    assert seen[0]["binSpec"] == {"binWidth": 7.0, "binUnits": "day"}


async def test_submit_compute_sends_autostart_and_the_study_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_fixture("compute_job_lookup.json"))

    client = _client(httpx.MockTransport(handler))
    job = await client.submit_compute(
        compute_name="differentialexpression",
        study_id="STUDY_e973eadd57",
        config=_de_config(),
        filters=[],
        autostart=False,
    )
    await client.close()
    assert seen[0].url.params["autostart"] == "false"
    body = json.loads(seen[0].content)
    assert body["studyId"] == "STUDY_e973eadd57"
    assert body["filters"] == []
    assert body["derivedVariables"] == []
    assert len(job.job_id) == 32


async def test_a_statistics_read_repeats_the_submit_body_that_addresses_the_job() -> (
    None
):
    """The job id is a hash of this body, so a reader sends the same one."""
    seen: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.content)
        if request.url.path.endswith("/statistics"):
            return httpx.Response(200, json=_fixture("volcano_statistics.json"))
        return httpx.Response(200, json=_fixture("compute_job_lookup.json"))

    client = _client(httpx.MockTransport(handler))
    await client.submit_compute(
        compute_name="differentialexpression",
        study_id="STUDY_e973eadd57",
        config=_de_config(),
        filters=[_species_filter()],
    )
    stats = await client.compute_statistics(
        compute_name="differentialexpression",
        study_id="STUDY_e973eadd57",
        config=_de_config(),
        filters=[_species_filter()],
    )
    await client.close()
    assert seen[0] == seen[1]
    submitted = json.loads(seen[0])
    assert submitted["filters"] == [
        {
            "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
            "variableId": "VAR_035294d0",
            "type": "stringSet",
            "stringSet": ["P. berghei"],
        }
    ]
    assert stats.effect_size_label == "log2(Fold Change)"
    assert len(stats.statistics) == 201


async def test_get_job_addresses_the_job_by_its_derivable_id() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=_fixture("compute_job_lookup.json"))

    client = _client(httpx.MockTransport(handler))
    job = await client.get_job("db04204e5386396e1ca2cb78469ab6fb")
    await client.close()
    assert seen[0].url.path == "/eda/jobs/db04204e5386396e1ca2cb78469ab6fb"
    assert job.status == "complete"


async def test_a_400_becomes_a_bad_request_error() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _r: httpx.Response(
                400,
                json={
                    "status": "bad-request",
                    "message": "Variable 'VAR_deadbeef' is not found",
                },
            )
        )
    )
    with pytest.raises(EdaBadRequestError):
        await client.count(study_id="S", entity_id="E", filters=[])
    await client.close()


async def test_a_403_on_a_compute_becomes_forbidden() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _r: httpx.Response(403, json={"status": "forbidden"})
        )
    )
    with pytest.raises(EdaForbiddenError):
        await client.submit_compute(
            compute_name="differentialexpression",
            study_id="DS_e973eadd57",
            config=_de_config(),
            filters=[],
        )
    await client.close()


async def test_a_422_becomes_invalid_input() -> None:
    client = _client(
        httpx.MockTransport(
            lambda _r: httpx.Response(
                422,
                json={
                    "status": "invalid-input",
                    "errors": {"general": [], "byKey": {"config": ["bad enum"]}},
                },
            )
        )
    )
    with pytest.raises(EdaInvalidInputError):
        await client.submit_compute(
            compute_name="differentialexpression",
            study_id="STUDY_x",
            config=_de_config(),
            filters=[],
        )
    await client.close()


async def test_create_analysis_posts_the_new_analysis_under_the_project() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"analysisId": "t4fszEJ"})

    client = _client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    created = await analyses.create(
        user_id="1216062453",
        analysis=EdaNewAnalysis(study_id="DS_53f554ec6a", display_name="probe"),
    )
    await client.close()
    assert created.analysis_id == "t4fszEJ"
    assert seen[0].url.path == "/eda/users/1216062453/analyses/PlasmoDB"
    body = json.loads(seen[0].content)
    assert body["studyId"] == "DS_53f554ec6a"
    assert body["descriptor"]["subset"]["descriptor"] == []


async def test_patch_descriptor_sends_only_the_descriptor() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(204)

    client = _client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    await analyses.patch_descriptor(
        user_id="1",
        analysis_id="t4fszEJ",
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=[_species_filter()]),
        ),
    )
    await client.close()
    assert seen[0].method == "PATCH"
    assert seen[0].url.path == "/eda/users/1/analyses/PlasmoDB/t4fszEJ"
    assert set(json.loads(seen[0].content)) == {"descriptor"}


async def test_get_analysis_parses_the_stored_descriptor() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "analysisId": "t4fszEJ",
                "displayName": "probe",
                "studyId": "DS_53f554ec6a",
                "numFilters": 1,
                "descriptor": {
                    "subset": {
                        "descriptor": [
                            {
                                "entityId": "GENE_PHENOTYPE_DATA_ENTITY",
                                "variableId": "VAR_035294d0",
                                "type": "stringSet",
                                "stringSet": ["P. berghei"],
                            }
                        ],
                        "uiSettings": {},
                    }
                },
            },
        )

    client = _client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    detail = await analyses.get(user_id="1", analysis_id="t4fszEJ")
    await client.close()
    assert seen[0].url.path == "/eda/users/1/analyses/PlasmoDB/t4fszEJ"
    assert detail.num_filters == 1
    assert detail.descriptor.subset.descriptor == [_species_filter()]


async def test_list_all_returns_every_analysis_summary() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json=[
                {"analysisId": "t4fszEJ", "displayName": "probe"},
                {"analysisId": "kW2n1Qb", "displayName": "second"},
            ],
        )

    client = _client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    summaries = await analyses.list_all(user_id="1")
    await client.close()
    assert seen[0].url.path == "/eda/users/1/analyses/PlasmoDB"
    assert [s.analysis_id for s in summaries] == ["t4fszEJ", "kW2n1Qb"]


async def test_delete_analysis_addresses_the_single_analysis() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202)

    client = _client(httpx.MockTransport(handler))
    analyses = EdaAnalysesClient(client=client, project_id="PlasmoDB")
    await analyses.delete(user_id="1", analysis_id="t4fszEJ")
    await client.close()
    assert seen[0].method == "DELETE"


async def test_resolve_user_id_returns_the_numeric_wdk_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wdk = VEuPathDBClient(base_url="https://plasmodb.org/plasmo/service")
    http = httpx.AsyncClient(
        base_url=wdk.base_url,
        transport=httpx.MockTransport(
            lambda _r: httpx.Response(200, json={"id": 1216062453, "isGuest": False})
        ),
    )

    async def _http() -> httpx.AsyncClient:
        return http

    monkeypatch.setattr(wdk, "_get_client", _http)
    analyses = EdaAnalysesClient(
        client=_client(httpx.MockTransport(lambda _r: httpx.Response(204))),
        project_id="PlasmoDB",
    )
    user_id = await analyses.resolve_user_id(wdk)
    await http.aclose()
    assert user_id == "1216062453"


async def test_resolve_user_id_refuses_a_response_that_names_no_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wdk = VEuPathDBClient(base_url="https://plasmodb.org/plasmo/service")
    http = httpx.AsyncClient(
        base_url=wdk.base_url,
        transport=httpx.MockTransport(lambda _r: httpx.Response(200, json={})),
    )

    async def _http() -> httpx.AsyncClient:
        return http

    monkeypatch.setattr(wdk, "_get_client", _http)
    analyses = EdaAnalysesClient(
        client=_client(httpx.MockTransport(lambda _r: httpx.Response(204))),
        project_id="PlasmoDB",
    )
    with pytest.raises(WDKLoginRequiredError):
        await analyses.resolve_user_id(wdk)
    await http.aclose()
