"""Every entity's subset size, and the cache that spares the unfiltered read."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Callable, Generator, Sequence
from typing import Any

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda.client import EdaClient
from veupathdb.eda.models import (
    EdaAnalysisDescriptor,
    EdaAnalysisDetail,
    EdaFilter,
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaSubsetDescriptor,
)
from veupathdb.testing.eda_fixtures import FIXTURE_DIR

from pathfinder.domain.eda_parts import EdaEntityCount
from pathfinder.persistence.models import ConversationAnalysisView
from pathfinder.services.eda import authoring, catalog
from pathfinder.services.eda.binding import read_analysis_state

pytestmark = pytest.mark.asyncio

FIXTURES = FIXTURE_DIR

_PHENOTYPE_DATASET = "DS_53f554ec6a"
_PHENOTYPE_STUDY = "STUDY_53f554ec6a"
_PHENOTYPE_ENTITY = "GENE_PHENOTYPE_DATA_ENTITY"
_SPECIES = "VAR_035294d0"

_DE_DATASET = "DS_e973eadd57"
_DE_STUDY = "STUDY_e973eadd57"
_SAMPLE = "ENT_8151325d"
_HTSEQ = "ENT_fd574cd6"
_TEMPERATURE_CONDITION = "VAR_081ab087"

# The filtered and unfiltered size of each entity, keyed by (study, entity).
# The gene pair is the recorded one; the sample pair is six of twelve samples
# and the htseq pair is those samples against the study's 5511 genes.
_SIZES = {
    (_PHENOTYPE_STUDY, _PHENOTYPE_ENTITY): (4011, 4279),
    (_DE_STUDY, _SAMPLE): (6, 12),
    (_DE_STUDY, _HTSEQ): (33066, 66132),
}

_PERMISSIONS = {
    "perDataset": {
        _PHENOTYPE_DATASET: {
            "studyId": _PHENOTYPE_STUDY,
            "sha1Hash": "53f554ec6aee372f6489f0bccc0b58fbdb7ad643",
            "isUserStudy": False,
            "displayName": "RMgmDB - Rodent Malaria genetically modified Parasites",
            "actionAuthorization": {
                "subsetting": True,
                "visualizations": True,
                "resultsFirstPage": True,
                "resultsAll": True,
            },
        },
        _DE_DATASET: {
            "studyId": _DE_STUDY,
            "sha1Hash": "e973eadd5719cbe0a30cbb0b5f6f9ee0e1c1d0a2",
            "isUserStudy": False,
            "displayName": "Heat shock response in sensitive mutants (LRR5, DHC)",
            "actionAuthorization": {
                "subsetting": True,
                "visualizations": True,
                "resultsFirstPage": True,
                "resultsAll": True,
            },
        },
    }
}

_STUDIES = {
    "studies": [
        {
            "id": _PHENOTYPE_STUDY,
            "datasetId": _PHENOTYPE_DATASET,
            "sha1hash": "53f554ec6aee372f6489f0bccc0b58fbdb7ad643",
            "sourceType": "curated",
            "displayName": "RMgmDB - Rodent Malaria genetically modified Parasites",
            "lastModified": "2026-05-27T20:00:00-04:00",
        },
        {
            "id": _DE_STUDY,
            "datasetId": _DE_DATASET,
            "sha1hash": "e973eadd5719cbe0a30cbb0b5f6f9ee0e1c1d0a2",
            "sourceType": "curated",
            "displayName": "Heat shock response in sensitive mutants (LRR5, DHC)",
            "lastModified": "2026-05-27T20:00:00-04:00",
        },
    ]
}


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


def _study_detail(name: str) -> EdaStudyDetail:
    return EdaStudyDetail.model_validate(_fixture(name)["study"])


@pytest.fixture(autouse=True)
def _token() -> Generator[None]:
    token = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(token)


@pytest.fixture
async def count_paths(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[list[str]]:
    """The recorded wire, plus the count path of every count request."""
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/permissions"):
            return httpx.Response(200, json=_PERMISSIONS)
        if path == "/eda/studies":
            return httpx.Response(200, json=_STUDIES)
        if path == f"/eda/studies/{_PHENOTYPE_STUDY}":
            return httpx.Response(200, json=_fixture("study_detail_phenotype.json"))
        if path == f"/eda/studies/{_DE_STUDY}":
            return httpx.Response(200, json=_fixture("study_detail_de.json"))
        if path.endswith("/count"):
            paths.append(path)
            parts = path.split("/")
            filtered, unfiltered = _SIZES[(parts[3], parts[5])]
            body = json.loads(request.content)
            return httpx.Response(
                200, json={"count": filtered if body["filters"] else unfiltered}
            )
        return httpx.Response(404, json={"status": "not-found"})

    client = EdaClient(
        base_url="https://plasmodb.org/eda", transport=httpx.MockTransport(handler)
    )
    monkeypatch.setattr(catalog, "get_eda_client", lambda _s: client)
    monkeypatch.setattr(authoring, "get_eda_client", lambda _s: client)
    yield paths
    await client.close()


def _de_filters() -> Sequence[EdaFilter]:
    return [
        EdaStringSetFilter(
            entity_id=_SAMPLE,
            variable_id=_TEMPERATURE_CONDITION,
            string_set=["febrile"],
        )
    ]


def _phenotype_filters() -> Sequence[EdaFilter]:
    return [
        EdaStringSetFilter(
            entity_id=_PHENOTYPE_ENTITY,
            variable_id=_SPECIES,
            string_set=["P. berghei"],
        )
    ]


async def test_every_entity_of_the_study_is_counted_in_tree_order(
    count_paths: list[str],
) -> None:
    del count_paths
    counts = await authoring.subset_entity_counts(
        "plasmodb",
        study=_study_detail("study_detail_de.json"),
        filters=_de_filters(),
    )
    assert counts == [
        EdaEntityCount(
            entity_id=_SAMPLE,
            entity_display_name="Sample",
            count=6,
            unfiltered_count=12,
        ),
        EdaEntityCount(
            entity_id=_HTSEQ,
            entity_display_name="pfal3D7 htseq counts",
            count=33066,
            unfiltered_count=66132,
        ),
    ]


async def test_a_cold_cache_reads_both_sizes_of_every_entity(
    count_paths: list[str],
) -> None:
    await authoring.subset_entity_counts(
        "plasmodb",
        study=_study_detail("study_detail_de.json"),
        filters=_de_filters(),
    )
    assert count_paths == [
        f"/eda/studies/{_DE_STUDY}/entities/{_SAMPLE}/count",
        f"/eda/studies/{_DE_STUDY}/entities/{_SAMPLE}/count",
        f"/eda/studies/{_DE_STUDY}/entities/{_HTSEQ}/count",
        f"/eda/studies/{_DE_STUDY}/entities/{_HTSEQ}/count",
    ]


async def test_a_warm_cache_reads_only_the_filtered_size(
    count_paths: list[str],
) -> None:
    """The whole size of an entity does not move while the study detail holds."""
    study = _study_detail("study_detail_de.json")
    await authoring.subset_entity_counts("plasmodb", study=study, filters=_de_filters())
    count_paths.clear()
    await authoring.subset_entity_counts("plasmodb", study=study, filters=_de_filters())
    assert count_paths == [
        f"/eda/studies/{_DE_STUDY}/entities/{_SAMPLE}/count",
        f"/eda/studies/{_DE_STUDY}/entities/{_HTSEQ}/count",
    ]


async def test_clearing_the_study_caches_reads_both_sizes_again(
    count_paths: list[str],
    drop_eda_study_caches: Callable[[], None],
) -> None:
    study = _study_detail("study_detail_de.json")
    await authoring.subset_entity_counts("plasmodb", study=study, filters=_de_filters())
    count_paths.clear()
    drop_eda_study_caches()
    await authoring.subset_entity_counts("plasmodb", study=study, filters=_de_filters())
    assert len(count_paths) == 4


async def test_a_filter_the_study_refuses_never_reaches_the_count(
    count_paths: list[str],
) -> None:
    with pytest.raises(authoring.SubsetRejectedError):
        await authoring.subset_entity_counts(
            "plasmodb",
            study=_study_detail("study_detail_de.json"),
            filters=[
                EdaStringSetFilter(
                    entity_id=_SAMPLE,
                    variable_id=_TEMPERATURE_CONDITION,
                    string_set=["boiling"],
                )
            ],
        )
    assert count_paths == []


async def test_the_read_state_carries_the_counts_of_its_own_subset(
    count_paths: list[str],
) -> None:
    del count_paths
    analysis = EdaAnalysisDetail(
        analysis_id="t4fszEJ",
        display_name="berghei subset",
        study_id=_PHENOTYPE_DATASET,
        num_filters=1,
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(descriptor=list(_phenotype_filters()))
        ),
    )
    state = await read_analysis_state(
        bound=ConversationAnalysisView(
            site_id="plasmodb",
            dataset_id=_PHENOTYPE_DATASET,
            analysis_id="t4fszEJ",
            revision=3,
        ),
        analysis=analysis,
    )
    assert state.entity_counts == [
        EdaEntityCount(
            entity_id=_PHENOTYPE_ENTITY,
            entity_display_name="Gene Phenotype Data",
            count=4011,
            unfiltered_count=4279,
        )
    ]
    assert state.revision == 3


async def test_a_read_of_a_subset_the_study_refuses_reports_it_instead_of_a_count(
    count_paths: list[str],
) -> None:
    """An analysis edited elsewhere can hold a value the vocabulary dropped.

    Upstream answers such a filter 200 with count 0, so the read is refused
    rather than reported as an empty subset.
    """
    analysis = EdaAnalysisDetail(
        analysis_id="t4fszEJ",
        display_name="berghei subset",
        study_id=_PHENOTYPE_DATASET,
        num_filters=1,
        num_computations=0,
        descriptor=EdaAnalysisDescriptor(
            subset=EdaSubsetDescriptor(
                descriptor=[
                    EdaStringSetFilter(
                        entity_id=_PHENOTYPE_ENTITY,
                        variable_id=_SPECIES,
                        string_set=["P. vivax"],
                    )
                ]
            )
        ),
    )
    with pytest.raises(authoring.SubsetRejectedError) as raised:
        await read_analysis_state(
            bound=ConversationAnalysisView(
                site_id="plasmodb",
                dataset_id=_PHENOTYPE_DATASET,
                analysis_id="t4fszEJ",
                revision=3,
            ),
            analysis=analysis,
        )
    assert count_paths == []
    assert raised.value.messages == [
        "Filter stringSet on variable VAR_035294d0 of entity "
        "GENE_PHENOTYPE_DATA_ENTITY names P. vivax, which the vocabulary does "
        "not carry. The vocabulary is P. berghei, P. falciparum, P. yoelii. "
        "An unknown value returns count 0 rather than an error."
    ]
