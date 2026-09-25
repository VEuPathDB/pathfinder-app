"""The gene entity a subset filters, the genes it selects, and its two refusals."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator, Sequence

import httpx
import pytest
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.eda import (
    EdaAnalysisDescriptor,
    EdaClient,
    EdaFilter,
    EdaPermissionEntry,
    EdaServerError,
    EdaStringSetFilter,
    EdaStudyDetail,
    EdaStudyDetailResponse,
    EdaSubsetDescriptor,
)
from veupathdb.testing.eda_fixtures import recorded_distribution

from pathfinder.services.eda import gene_subset
from pathfinder.services.eda.authoring import SubsetRejectedError
from pathfinder.services.eda.gene_subset import (
    GeneCount,
    NoGeneSubsetError,
    refuse_a_subset_that_selects_no_genes,
)
from pathfinder.tests._support.eda_doubles import SPECIES_VARIABLE, no_gene_study
from pathfinder.tests._support.eda_step_doubles import (
    COUNTS_ENTITY,
    DE_DATASET,
    DE_GENES,
    SAMPLE_ONLY_REFUSAL,
    SAMPLE_ONLY_RETRY,
    de_analysis,
    de_study,
    gene_filter,
    phenotype_subset,
    sample_filter,
    wire_gene_count,
)
from pathfinder.tests._support.eda_wire import (
    BASE_URL,
    DE_STUDY,
    PHENOTYPE_DATASET,
    PHENOTYPE_ENTITY,
    eda_transport,
    fixture,
)

_STUDY = EdaStudyDetailResponse.model_validate(fixture("study_detail_de")).study


@pytest.fixture
def token() -> Iterator[None]:
    reset = veupathdb_auth_token_ctx.set("t")
    yield
    veupathdb_auth_token_ctx.reset(reset)


def test_filters_on_samples_name_the_sample_entity_once_and_no_gene() -> None:
    subset = gene_subset.gene_subset(_STUDY, [sample_filter(), sample_filter()])

    assert subset.filters_genes is False
    assert subset.filters_clause() == "2 filters on Sample"
    assert subset.gene_entity_clause() == "pfal3D7 htseq counts (ENT_fd574cd6)"


def test_a_filter_on_the_gene_entity_filters_genes() -> None:
    subset = gene_subset.gene_subset(_STUDY, [sample_filter(), gene_filter()])

    assert subset.filters_genes is True
    assert subset.filters_clause() == "2 filters on Sample, pfal3D7 htseq counts"


def test_no_filter_is_stated_as_no_filter() -> None:
    subset = gene_subset.gene_subset(_STUDY, [])

    assert subset.filters_genes is False
    assert subset.filters_clause() == "no filter"


async def test_a_gene_count_is_the_distinct_gene_ids_and_not_the_rows(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    """Each counts row is one gene in one sample, so rows overstate genes."""
    del token
    asked: list[tuple[str, list[object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        filters = json.loads(request.content)["filters"]
        asked.append((request.url.path, filters))
        subset = "filtered" if filters else "unfiltered"
        return httpx.Response(200, json=fixture(f"gene_id_distribution_de_{subset}"))

    client = EdaClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(gene_subset, "get_eda_client", lambda _site: client)

    counted = await gene_subset.gene_count(
        "plasmodb",
        study=_STUDY,
        entity_id=COUNTS_ENTITY,
        filters=[gene_filter()],
    )

    filtered_rows = recorded_distribution("gene_id_distribution_de_filtered")
    assert counted == DE_GENES
    assert counted.count < filtered_rows.statistics.subset_size
    path = (
        f"/eda/studies/{DE_STUDY}/entities/{COUNTS_ENTITY}"
        "/variables/VEUPATHDB_GENE_ID/distribution"
    )
    assert [entry[0] for entry in asked] == [path, path]
    assert [len(entry[1]) for entry in asked] == [1, 0]


async def test_the_recorded_deployment_answers_the_recorded_gene_ids(
    token: None,
) -> None:
    """Both gene-id distributions are the bodies recorded from the site."""
    del token
    transport = eda_transport(study_id=DE_STUDY, study_fixture="study_detail_de")
    client = EdaClient(base_url=BASE_URL, transport=transport)

    answered = [
        await client.distribution(
            study_id=DE_STUDY,
            entity_id=COUNTS_ENTITY,
            variable_id="VEUPATHDB_GENE_ID",
            filters=filters,
        )
        for filters in ([gene_filter()], [])
    ]

    assert answered == [
        recorded_distribution("gene_id_distribution_de_filtered"),
        recorded_distribution("gene_id_distribution_de_unfiltered"),
    ]


async def test_an_export_reads_the_study_once_and_asks_both_counts_at_once(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    """Each distribution call waits until the other one is asked too."""
    del token
    events: list[str] = []
    both_asked = asyncio.Event()

    async def read_study(
        site: str, dataset_id: str
    ) -> tuple[EdaPermissionEntry, EdaStudyDetail]:
        events.append("study")
        return await de_study(site, dataset_id)

    async def handler(request: httpx.Request) -> httpx.Response:
        filters = json.loads(request.content)["filters"]
        events.append(f"ask {len(filters)}")
        if sum(event.startswith("ask") for event in events) == 2:
            both_asked.set()
        await asyncio.wait_for(both_asked.wait(), timeout=1)
        events.append(f"answer {len(filters)}")
        subset = "filtered" if filters else "unfiltered"
        return httpx.Response(200, json=fixture(f"gene_id_distribution_de_{subset}"))

    client = EdaClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(gene_subset, "get_study_detail_for_dataset", read_study)
    monkeypatch.setattr(gene_subset, "get_eda_client", lambda _site: client)

    await refuse_a_subset_that_selects_no_genes(
        "plasmodb",
        dataset_id=DE_DATASET,
        analysis=de_analysis(filters=[gene_filter()]),
    )

    assert events[0] == "study"
    assert sorted(events[1:3]) == ["ask 0", "ask 1"]
    assert sorted(events[3:]) == ["answer 0", "answer 1"]


async def test_a_refused_count_cancels_its_sibling_and_raises_the_services_error(
    monkeypatch: pytest.MonkeyPatch, token: None
) -> None:
    """The caller reads the service's own refusal, and no call outlives it."""
    del token
    sibling: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        if json.loads(request.content)["filters"]:
            await asyncio.sleep(0)
            return httpx.Response(500, json={"message": "subset query failed"})
        sibling.append("asked")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            sibling.append("cancelled")
            raise
        return httpx.Response(200, json=fixture("gene_id_distribution_de_unfiltered"))

    client = EdaClient(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    monkeypatch.setattr(gene_subset, "get_eda_client", lambda _site: client)

    with pytest.raises(EdaServerError) as refused:
        await gene_subset.gene_count(
            "plasmodb", study=_STUDY, entity_id=COUNTS_ENTITY, filters=[gene_filter()]
        )

    assert refused.value.status == 500
    assert refused.value.detail == (
        f"POST /studies/{DE_STUDY}/entities/{COUNTS_ENTITY}"
        "/variables/VEUPATHDB_GENE_ID/distribution: subset query failed"
    )
    assert sibling == ["asked", "cancelled"]


async def _refusal(
    filters: Sequence[EdaFilter], *, with_computation: bool = False
) -> NoGeneSubsetError:
    with pytest.raises(NoGeneSubsetError) as refusal:
        await refuse_a_subset_that_selects_no_genes(
            "plasmodb",
            dataset_id=DE_DATASET,
            analysis=de_analysis(filters=filters, with_computation=with_computation),
        )
    return refusal.value


async def test_a_sample_subset_tells_each_reader_the_same_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The researcher reads no tool name and no id; the model reads both."""
    counted = wire_gene_count(monkeypatch, study=de_study, genes=DE_GENES)

    refusal = await _refusal([sample_filter()])

    assert refusal.status == 422
    assert refusal.detail == SAMPLE_ONLY_REFUSAL
    assert refusal.retry == SAMPLE_ONLY_RETRY
    assert counted == []


async def test_a_sample_subset_beside_a_computation_names_the_volcano_cut(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire_gene_count(monkeypatch, study=de_study, genes=DE_GENES)

    refusal = await _refusal([sample_filter()], with_computation=True)

    held = (
        "The analysis holds 1 filter on Sample and 1 comparison, and no filter "
        "on pfal3D7 htseq counts. A step holds genes, and a subset of another "
        "entity selects no genes, so nothing was written."
    )
    assert refusal.detail == (
        f"{held} Export the genes that pass a volcano cut, or add a filter on "
        "pfal3D7 htseq counts."
    )
    assert refusal.retry == (
        f"{held} The gene entity is pfal3D7 htseq counts (ENT_fd574cd6). Send "
        "effect_size_threshold and significance_threshold to export the genes "
        "that pass them, or call set_eda_filters with a filter on pfal3D7 "
        "htseq counts."
    )


async def test_a_gene_subset_that_selects_no_gene_is_counted_in_genes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The denominator is the study's distinct genes, never its rows."""
    whole = DE_GENES.unfiltered_count
    counted = wire_gene_count(
        monkeypatch, study=de_study, genes=GeneCount(count=0, unfiltered_count=whole)
    )

    refusal = await _refusal([sample_filter(), gene_filter()])

    held = (
        f"The subset selects 0 of the {whole:,} genes on pfal3D7 htseq counts, "
        "so there is no step to export and nothing was written."
    )
    assert refusal.detail == (
        f"{held} Widen the filters on pfal3D7 htseq counts, or run a "
        "differential expression comparison and export the genes that pass "
        "its cut."
    )
    assert refusal.retry == (
        f"{held} To subset genes, widen the filters on pfal3D7 htseq counts "
        "with set_eda_filters. For 'up in A versus B', call run_eda_compute "
        "and export the genes that pass its thresholds."
    )
    assert [(c.study_id, c.entity_id) for c in counted] == [(DE_STUDY, COUNTS_ENTITY)]


async def test_a_gene_subset_that_selects_genes_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    counted = wire_gene_count(monkeypatch, study=de_study, genes=DE_GENES)

    await refuse_a_subset_that_selects_no_genes(
        "plasmodb",
        dataset_id=DE_DATASET,
        analysis=de_analysis(filters=[gene_filter()]),
    )

    assert [list(c.filters) for c in counted] == [[gene_filter()]]


async def test_a_study_with_no_gene_entity_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A study that carries no gene id exports no step, whatever it filters."""
    counted = wire_gene_count(monkeypatch, study=no_gene_study)

    refusal = await _refusal([sample_filter()])

    assert refusal.detail == (
        "This study has no single gene variable, so it cannot export genes as "
        "a step. Nothing was written."
    )
    assert refusal.retry == (
        "Study STUDY_53f554ec6a carries no VEUPATHDB_GENE_ID variable, so it "
        "cannot export a gene list to a strategy step. Nothing was written. "
        "Report the counts and the distributions instead."
    )
    assert counted == []


async def test_a_gene_subset_the_study_refuses_is_never_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A value outside the vocabulary answers 0 upstream, so no count is taken."""
    counted = wire_gene_count(monkeypatch)
    vivax = EdaStringSetFilter(
        entity_id=PHENOTYPE_ENTITY,
        variable_id=SPECIES_VARIABLE,
        string_set=["P. vivax"],
    )
    analysis = phenotype_subset().model_copy(
        update={
            "descriptor": EdaAnalysisDescriptor(
                subset=EdaSubsetDescriptor(descriptor=[vivax])
            )
        }
    )

    with pytest.raises(SubsetRejectedError) as refusal:
        await refuse_a_subset_that_selects_no_genes(
            "plasmodb", dataset_id=PHENOTYPE_DATASET, analysis=analysis
        )

    assert refusal.value.messages == [
        (
            "Filter stringSet on variable VAR_035294d0 of entity "
            "GENE_PHENOTYPE_DATA_ENTITY names P. vivax, which the vocabulary "
            "does not carry. The vocabulary is P. berghei, P. falciparum, "
            "P. yoelii. An unknown value returns count 0 rather than an error."
        )
    ]
    assert counted == []
