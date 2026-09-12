"""Authoring runs the pure predicates, then verifies with a real count."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import (
    EdaClient,
    EdaComparator,
    EdaComputation,
    EdaComputationDescriptor,
    EdaDifferentialExpressionConfig,
    EdaLabeledRange,
    EdaStringSetFilter,
    EdaVariableSpec,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.services.eda import authoring, catalog
from pathfinder.tests._support.eda_wire import wire_eda_client

FIXTURES = FIXTURE_DIR

pytestmark = pytest.mark.asyncio

_DATASET = "DS_53f554ec6a"
_STUDY = "STUDY_53f554ec6a"
_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"

_DE_ENTITY = "ENT_fd574cd6"
_DE_VALUE = "SEQUENCE_READ_COUNT_SENSE"


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _route(
    counts: dict[bool, int] | None = None,
    seen: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    """Route the phenotype study. A count answers by whether filters travelled."""
    sizes = counts or {}

    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if path == f"/eda/studies/{_STUDY}":
            return httpx.Response(200, json=_fixture("study_detail_phenotype.json"))
        if path == f"/eda/studies/{_STUDY}/entities/{_ENTITY}/count":
            filtered = bool(json.loads(request.content)["filters"])
            return httpx.Response(200, json={"count": sizes[filtered]})
        if path.endswith("/distribution"):
            return httpx.Response(200, json=_fixture("distribution_categorical.json"))
        return httpx.Response(404, json={"status": "not-found"})

    return httpx.MockTransport(handler)


type Wire = Callable[[httpx.AsyncBaseTransport], EdaClient]


@pytest.fixture
def wire(monkeypatch: pytest.MonkeyPatch) -> Iterator[Wire]:
    """Build the site's EDA client over one transport, and route the site to it."""

    def _wire(transport: httpx.AsyncBaseTransport) -> EdaClient:
        client = EdaClient(base_url="https://plasmodb.org/eda", transport=transport)
        monkeypatch.setattr(catalog, "get_eda_client", lambda _s: client)
        monkeypatch.setattr(authoring, "get_eda_client", lambda _s: client)
        return client

    token = veupathdb_auth_token_ctx.set("t")
    yield _wire
    veupathdb_auth_token_ctx.reset(token)


def _species(value: str) -> EdaStringSetFilter:
    return EdaStringSetFilter(
        entity_id=_ENTITY, variable_id=_SPECIES, string_set=[value]
    )


async def test_an_out_of_vocabulary_value_is_refused_before_the_count(
    wire: Wire,
) -> None:
    """The service would answer 200 with count 0, so validation is the only guard."""
    wired = wire(_route())
    with pytest.raises(authoring.SubsetRejectedError) as excinfo:
        await authoring.verified_count(
            "plasmodb",
            dataset_id=_DATASET,
            entity_id=_ENTITY,
            filters=[_species("P. vivax")],
        )
    await wired.close()
    assert len(excinfo.value.messages) == 1
    assert "P. vivax" in excinfo.value.messages[0]


async def test_the_verified_count_is_the_service_answer(wire: Wire) -> None:
    wired = wire(_route({True: 4011, False: 4279}))
    counted = await authoring.verified_count(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_ENTITY,
        filters=[_species("P. berghei")],
    )
    await wired.close()
    assert counted.entity_id == _ENTITY
    assert counted.count == 4011
    assert counted.unfiltered_count == 4279


async def test_a_verified_count_of_zero_is_reported_not_swallowed(
    wire: Wire,
) -> None:
    wired = wire(_route({True: 0, False: 4279}))
    counted = await authoring.verified_count(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_ENTITY,
        filters=[_species("P. berghei")],
    )
    await wired.close()
    assert counted.count == 0
    assert counted.unfiltered_count == 4279


async def test_a_verified_count_refuses_an_out_of_vocabulary_value(
    wire: Wire,
) -> None:
    """The service answers 200 with count 0, so the predicates run first."""
    seen: list[httpx.Request] = []
    wired = wire(_route({True: 4011, False: 4279}, seen))
    with pytest.raises(authoring.SubsetRejectedError) as excinfo:
        await authoring.verified_count(
            "plasmodb",
            dataset_id=_DATASET,
            entity_id=_ENTITY,
            filters=[_species("P. vivax")],
        )
    await wired.close()
    assert "P. vivax" in str(excinfo.value)
    assert not any("/count" in r.url.path for r in seen)


async def test_a_preview_refuses_an_out_of_vocabulary_value(
    wire: Wire,
) -> None:
    seen: list[httpx.Request] = []
    wired = wire(_route({True: 4011, False: 4279}, seen))
    with pytest.raises(authoring.SubsetRejectedError) as excinfo:
        await authoring.preview_subset(
            "plasmodb",
            dataset_id=_DATASET,
            entity_id=_ENTITY,
            filters=[_species("P. vivax")],
        )
    await wired.close()
    assert "P. vivax" in str(excinfo.value)
    assert not any("/count" in r.url.path for r in seen)


async def test_the_preview_carries_both_counts_and_a_distribution(
    wire: Wire,
) -> None:
    wired = wire(_route({True: 4011, False: 4279}))
    preview = await authoring.preview_subset(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_ENTITY,
        filters=[_species("P. berghei")],
        distribution_variable_id=_SPECIES,
    )
    await wired.close()
    assert preview.count == 4011
    assert preview.unfiltered_count == 4279
    assert preview.distribution is not None
    assert preview.distribution.statistics.subset_size == 4279
    assert preview.entity_display_name
    assert preview.distribution_note is None


async def test_the_preview_omits_the_distribution_when_no_variable_is_named(
    wire: Wire,
) -> None:
    wired = wire(_route({True: 4011, False: 4279}))
    preview = await authoring.preview_subset(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_ENTITY,
        filters=[_species("P. berghei")],
    )
    await wired.close()
    assert preview.distribution is None
    assert preview.distribution_note is None


async def test_a_filter_on_an_unknown_entity_is_reported_with_its_id(
    wire: Wire,
) -> None:
    wired = wire(_route())
    with pytest.raises(authoring.SubsetRejectedError) as excinfo:
        await authoring.verified_count(
            "plasmodb",
            dataset_id=_DATASET,
            entity_id=_ENTITY,
            filters=[
                EdaStringSetFilter(
                    entity_id="ENT_nope", variable_id="V", string_set=["x"]
                )
            ],
        )
    await wired.close()
    assert len(excinfo.value.messages) == 1
    assert "ENT_nope" in excinfo.value.messages[0]


async def test_every_subset_call_addresses_the_study_id_never_the_dataset_id(
    wire: Wire,
) -> None:
    """Subsetting takes the STUDY id; a dataset id there is a 403 upstream."""
    seen: list[httpx.Request] = []
    wired = wire(_route({True: 4011, False: 4279}, seen))
    await authoring.preview_subset(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_ENTITY,
        filters=[_species("P. berghei")],
        distribution_variable_id=_SPECIES,
    )
    await wired.close()
    addressed = [r.url.path for r in seen if "/entities/" in r.url.path]
    assert len(addressed) == 3
    assert all(path.startswith(f"/eda/studies/{_STUDY}/") for path in addressed)
    assert not any(_DATASET in path for path in addressed)


async def test_a_preview_on_an_entity_the_study_does_not_carry_is_refused(
    wire: Wire,
) -> None:
    wired = wire(_route())
    with pytest.raises(ValueError, match="ENT_nope"):
        await authoring.preview_subset(
            "plasmodb",
            dataset_id=_DATASET,
            entity_id="ENT_nope",
            filters=[],
        )
    await wired.close()


# --------------------------------------------------------------------------
# binSpec: required for a continuous variable, refused for any other.
# --------------------------------------------------------------------------


def _de_route(study: Any, seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if path == f"/eda/studies/{_STUDY}":
            return httpx.Response(200, json=study)
        if path.endswith("/count"):
            return httpx.Response(200, json={"count": 5511})
        if path.endswith("/distribution"):
            return httpx.Response(200, json=_fixture("distribution_categorical.json"))
        return httpx.Response(404, json={"status": "not-found"})

    return httpx.MockTransport(handler)


def _de_study() -> Any:
    return _fixture("study_detail_de.json")


def _de_computation(group_a: str, group_b: str) -> EdaComputation:
    return EdaComputation(
        computation_id="de1",
        descriptor=EdaComputationDescriptor(
            configuration=EdaDifferentialExpressionConfig(
                identifier_variable=EdaVariableSpec(
                    entity_id=_DE_ENTITY, variable_id="VEUPATHDB_GENE_ID"
                ),
                value_variable=EdaVariableSpec(
                    entity_id=_DE_ENTITY, variable_id=_DE_VALUE
                ),
                comparator=EdaComparator(
                    variable=EdaVariableSpec(
                        entity_id="ENT_8151325d", variable_id="VAR_081ab087"
                    ),
                    group_a=[EdaLabeledRange(label=group_a)],
                    group_b=[EdaLabeledRange(label=group_b)],
                ),
            )
        ),
    )


def _de_value_variable(study: Any) -> Any:
    counts_entity = study["study"]["rootEntity"]["children"][0]
    return next(v for v in counts_entity["variables"] if v["id"] == _DE_VALUE)


async def test_a_continuous_variable_sends_the_declared_bin_spec(
    wire: Wire,
) -> None:
    """A continuous variable with no binSpec is a bare 500 upstream."""
    seen: list[httpx.Request] = []
    wired = wire(_de_route(_de_study(), seen))
    preview = await authoring.preview_subset(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_DE_ENTITY,
        filters=[],
        distribution_variable_id=_DE_VALUE,
    )
    await wired.close()
    assert preview.distribution is not None
    assert preview.distribution_note is None
    body = json.loads(
        next(r for r in seen if r.url.path.endswith("/distribution")).content
    )
    assert body["binSpec"] == {
        "displayRangeMin": 0.0,
        "displayRangeMax": 61892.0,
        "binWidth": 2135.0,
    }


async def test_a_continuous_variable_with_no_declared_bin_width_is_skipped(
    wire: Wire,
) -> None:
    study = _de_study()
    del _de_value_variable(study)["distributionDefaults"]
    seen: list[httpx.Request] = []
    wired = wire(_de_route(study, seen))
    preview = await authoring.preview_subset(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_DE_ENTITY,
        filters=[],
        distribution_variable_id=_DE_VALUE,
    )
    await wired.close()
    assert preview.distribution is None
    assert preview.distribution_note is not None
    assert _DE_VALUE in preview.distribution_note
    assert not [r for r in seen if r.url.path.endswith("/distribution")]


async def test_a_continuous_date_variable_is_skipped_rather_than_binned(
    wire: Wire,
) -> None:
    """Its declared bin width is a day count, which a numeric binSpec cannot carry."""
    study = _de_study()
    study["study"]["rootEntity"]["variables"].append(
        {
            "id": "EUPATH_0043256",
            "type": "date",
            "displayName": "Collection date",
            "dataShape": "continuous",
            "distributionDefaults": {
                "rangeMin": "2017-05-05",
                "rangeMax": "2017-05-11",
                "binWidth": 1,
                "binUnits": "day",
            },
        }
    )
    seen: list[httpx.Request] = []
    wired = wire(_de_route(study, seen))
    preview = await authoring.preview_subset(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id="ENT_8151325d",
        filters=[],
        distribution_variable_id="EUPATH_0043256",
    )
    await wired.close()
    assert preview.distribution is None
    assert preview.distribution_note is not None
    assert "EUPATH_0043256" in preview.distribution_note
    assert not [r for r in seen if r.url.path.endswith("/distribution")]


async def test_a_variable_the_entity_does_not_declare_is_named_in_the_note(
    wire: Wire,
) -> None:
    seen: list[httpx.Request] = []
    wired = wire(_de_route(_de_study(), seen))
    preview = await authoring.preview_subset(
        "plasmodb",
        dataset_id=_DATASET,
        entity_id=_DE_ENTITY,
        filters=[],
        distribution_variable_id="VAR_nope",
    )
    await wired.close()
    assert preview.distribution is None
    assert preview.distribution_note is not None
    assert "VAR_nope" in preview.distribution_note


async def test_the_declared_ranges_key_every_numeric_variable_by_entity(
    wire: Wire,
) -> None:
    wired = wire(_de_route(_de_study(), []))
    _entry, study = await catalog.get_study_detail_for_dataset("plasmodb", _DATASET)
    await wired.close()
    ranges = authoring.declared_ranges(study)
    assert ranges[(_DE_ENTITY, _DE_VALUE)] == (0.0, 61892.0)
    assert ranges[("ENT_8151325d", "VAR_7033e90f")] == (37.0, 41.0)
    assert (_DE_ENTITY, "VEUPATHDB_GENE_ID") not in ranges


# --------------------------------------------------------------------------
# The upstream analysis document, which stays the SSOT.
# --------------------------------------------------------------------------


async def _fake_user_id(_site_id: str) -> str:
    return "1216062453"


_ANALYSIS_DETAIL = {
    "analysisId": "t4fszEJ",
    "displayName": "berghei subset",
    "studyId": _DATASET,
    "numFilters": 1,
    "numComputations": 0,
    "descriptor": {
        "subset": {
            "descriptor": [
                {
                    "entityId": _ENTITY,
                    "variableId": _SPECIES,
                    "type": "stringSet",
                    "stringSet": ["P. berghei"],
                }
            ],
            "uiSettings": {},
        },
        "computations": [],
        "starredVariables": [],
        "dataTableConfig": {},
        "derivedVariables": [],
    },
}


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
) -> EdaClient:
    """One client for the catalog, the authoring module and the analysis store."""
    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(authoring, "get_eda_client", lambda _s: client)
    wire_eda_client(monkeypatch, client)
    monkeypatch.setattr(authoring, "resolve_eda_user_id", _fake_user_id)
    return client


async def test_open_analysis_creates_the_upstream_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if path == f"/eda/studies/{_STUDY}":
            return httpx.Response(200, json=_fixture("study_detail_phenotype.json"))
        if "/analyses/" in path and request.method == "POST":
            return httpx.Response(200, json={"analysisId": "t4fszEJ"})
        return httpx.Response(404, json={"status": "not-found"})

    client = _wire(monkeypatch, handler)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        analysis_id = await authoring.open_analysis(
            "plasmodb", dataset_id=_DATASET, display_name="berghei subset"
        )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert analysis_id == "t4fszEJ"
    posts = [r for r in seen if r.method == "POST" and "/analyses/" in r.url.path]
    assert posts
    assert posts[0].url.path == "/eda/users/1216062453/analyses/PlasmoDB"
    body = json.loads(posts[0].content)
    assert body["studyId"] == _DATASET


async def test_open_analysis_cuts_a_long_display_name_to_the_upstream_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The user service refuses a displayName over 50 UTF-8 bytes."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if "/analyses/" in path and request.method == "POST":
            return httpx.Response(200, json={"analysisId": "t4fszEJ"})
        return httpx.Response(404, json={"status": "not-found"})

    client = _wire(monkeypatch, handler)
    purpose = (
        "Febrile versus normal differential expression in the LRR5 and DHC "
        "heat-shock RNA-seq study"
    )
    token = veupathdb_auth_token_ctx.set("t")
    try:
        await authoring.open_analysis(
            "plasmodb", dataset_id=_DATASET, display_name=purpose
        )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    posts = [r for r in seen if r.method == "POST" and "/analyses/" in r.url.path]
    sent = json.loads(posts[0].content)["displayName"]
    assert sent == "Febrile versus normal differential expression in t"
    assert len(sent.encode()) == 50


async def test_open_analysis_refuses_a_dataset_the_account_cannot_see(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        return httpx.Response(404, json={"status": "not-found"})

    client = _wire(monkeypatch, handler)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        with pytest.raises(catalog.UnknownEdaDatasetError):
            await authoring.open_analysis(
                "plasmodb", dataset_id="DS_nope", display_name="x"
            )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()


async def test_patch_subset_patches_the_descriptor_and_returns_the_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if path == f"/eda/studies/{_STUDY}":
            return httpx.Response(200, json=_fixture("study_detail_phenotype.json"))
        if request.method == "PATCH":
            return httpx.Response(204)
        if request.method == "GET" and "/analyses/" in path:
            return httpx.Response(200, json=_ANALYSIS_DETAIL)
        return httpx.Response(404, json={"status": "not-found"})

    client = _wire(monkeypatch, handler)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        detail = await authoring.patch_subset(
            "plasmodb",
            analysis_id="t4fszEJ",
            dataset_id=_DATASET,
            filters=[_species("P. berghei")],
        )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert detail.num_filters == 1
    patches = [r for r in seen if r.method == "PATCH"]
    assert len(patches) == 1
    patched = json.loads(patches[0].content)
    assert set(patched) == {"descriptor"}
    assert patched["descriptor"]["subset"]["descriptor"] == [
        {
            "entityId": _ENTITY,
            "variableId": _SPECIES,
            "type": "stringSet",
            "stringSet": ["P. berghei"],
        }
    ]
    reads = [r for r in seen if r.method == "GET" and "/analyses/" in r.url.path]
    assert len(reads) == 2


async def test_patch_subset_refuses_an_invalid_array_before_patching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if path == f"/eda/studies/{_STUDY}":
            return httpx.Response(200, json=_fixture("study_detail_phenotype.json"))
        return httpx.Response(404, json={"status": "not-found"})

    client = _wire(monkeypatch, handler)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        with pytest.raises(authoring.SubsetRejectedError) as excinfo:
            await authoring.patch_subset(
                "plasmodb",
                analysis_id="t4fszEJ",
                dataset_id=_DATASET,
                filters=[_species("P. vivax")],
            )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert "P. vivax" in str(excinfo.value)
    assert "PATCH" not in seen


async def test_apply_computation_replaces_the_single_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if path == f"/eda/studies/{_STUDY}":
            return httpx.Response(200, json=_de_study())
        if request.method == "PATCH":
            return httpx.Response(204)
        if request.method == "GET" and "/analyses/" in path:
            return httpx.Response(200, json=_ANALYSIS_DETAIL)
        return httpx.Response(404, json={"status": "not-found"})

    client = _wire(monkeypatch, handler)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        await authoring.apply_computation(
            "plasmodb",
            analysis_id="t4fszEJ",
            dataset_id=_DATASET,
            computation=_de_computation("normal", "febrile"),
        )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    patched = json.loads(next(r for r in seen if r.method == "PATCH").content)
    computations = patched["descriptor"]["computations"]
    assert len(computations) == 1
    assert computations[0]["descriptor"]["type"] == "differentialexpression"
    assert patched["descriptor"]["subset"]["descriptor"][0]["stringSet"] == [
        "P. berghei"
    ]


async def test_apply_computation_refuses_a_label_outside_the_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bad label reaches a failed job, so the predicate is the only guard."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.method)
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_fixture("permissions.json"))
        if path == "/eda/studies":
            return httpx.Response(200, json=_fixture("studies_list.json"))
        if path == f"/eda/studies/{_STUDY}":
            return httpx.Response(200, json=_de_study())
        return httpx.Response(404, json={"status": "not-found"})

    client = _wire(monkeypatch, handler)
    token = veupathdb_auth_token_ctx.set("t")
    try:
        with pytest.raises(authoring.SubsetRejectedError) as excinfo:
            await authoring.apply_computation(
                "plasmodb",
                analysis_id="t4fszEJ",
                dataset_id=_DATASET,
                computation=_de_computation("normal", "hypothermic"),
            )
    finally:
        veupathdb_auth_token_ctx.reset(token)
        await client.close()

    assert "hypothermic" in str(excinfo.value)
    assert "PATCH" not in seen
