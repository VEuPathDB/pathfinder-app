"""A saved set records each gene's home: a genomics site's own, the portal's
project column, and OrthoMCL's gene source columns. Groups have no home."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import pytest
from assistant_core.platform.types import JSONObject
from veupathdb.wdk import WDKAnswer, WDKDatasetConfigIdList, WDKSearchConfig

from pathfinder.domain.gene_homes import GeneHome
from pathfinder.services.gene_sets import homes
from pathfinder.services.gene_sets.homes import gene_homes, sites_that_list


def _answer(record_class: str, rows: Sequence[tuple[str, dict[str, str]]]) -> WDKAnswer:
    return WDKAnswer.model_validate(
        {
            "meta": {
                "totalCount": len(rows),
                "responseCount": len(rows),
                "recordClassName": record_class,
            },
            "records": [
                {"id": [{"name": "source_id", "value": key}], "attributes": attrs}
                for key, attrs in rows
            ],
        }
    )


_ORTHO_PROTEINS = _answer(
    "sequence",
    [
        (
            "PF3D7_0103400.1-p1",
            {
                "gene_source_id": "PF3D7_0103400",
                "gene_source_url": "https://qa.plasmodb.org/plasmo.qa/app/record/gene/PF3D7_0103400",
            },
        ),
        (
            "UNIPROT_Q9XYZ1",
            {
                "gene_source_id": "Q9XYZ1",
                "gene_source_url": "https://www.uniprot.org/uniprot/Q9XYZ1",
            },
        ),
    ],
)
_PORTAL_GENES = _answer(
    "transcript",
    [
        ("PF3D7_0103400", {"project_id": "PlasmoDB"}),
        ("TGME49_200250", {"project_id": "ToxoDB"}),
    ],
)


@dataclass
class _Site:
    answer: WDKAnswer
    datasets: list[list[str]] = field(default_factory=list)
    reports: list[tuple[str, str, dict[str, str]]] = field(default_factory=list)

    async def get_step_answer(
        self,
        step_id: int,
        attributes: list[str] | None = None,
        pagination: dict[str, int] | None = None,
        *,
        view_filters: object = None,
    ) -> WDKAnswer:
        del step_id, attributes, pagination, view_filters
        return self.answer

    async def create_dataset(self, config: WDKDatasetConfigIdList) -> int:
        self.datasets.append(config.source_content.ids)
        return 9001

    async def run_search_report(
        self,
        record_type: str,
        search_name: str,
        search_config: WDKSearchConfig,
        report_config: JSONObject | None = None,
    ) -> WDKAnswer:
        del report_config
        self.reports.append((record_type, search_name, search_config.parameters))
        return self.answer


def _serve(monkeypatch: pytest.MonkeyPatch, answer: WDKAnswer) -> _Site:
    site = _Site(answer)

    async def _no_filters(*_args: object) -> list[object]:
        return []

    monkeypatch.setattr(homes, "get_strategy_api", lambda _site_id: site)
    monkeypatch.setattr(homes, "get_wdk_client", lambda _site_id: site)
    monkeypatch.setattr(homes, "step_view_filters", _no_filters)
    return site


async def test_a_genomics_set_of_genes_lives_on_its_own_site() -> None:
    found = [
        await gene_homes(
            "plasmodb", ["PF3D7_0103400"], record_type=record_type, wdk_step_id=7
        )
        for record_type in ("transcript", None, "compound")
    ]

    assert found == [
        {"PF3D7_0103400": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb")},
        {"PF3D7_0103400": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb")},
        {},
    ]


async def test_a_portal_step_reads_each_genes_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _PORTAL_GENES)

    found = await gene_homes(
        "veupathdb",
        ["PF3D7_0103400", "TGME49_200250"],
        record_type="transcript",
        wdk_step_id=227256540,
    )

    assert found == {
        "PF3D7_0103400": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb"),
        "TGME49_200250": GeneHome(gene_id="TGME49_200250", site_id="toxodb"),
    }


async def test_an_orthomcl_protein_reads_its_gene_and_a_gene_off_veupathdb_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _serve(monkeypatch, _ORTHO_PROTEINS)

    found = await gene_homes(
        "orthomcl",
        ["PF3D7_0103400.1-p1", "UNIPROT_Q9XYZ1"],
        record_type="transcript",
        wdk_step_id=227256540,
    )

    assert found == {
        "PF3D7_0103400.1-p1": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb")
    }


async def test_a_list_without_a_step_is_read_through_the_sites_id_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    site = _serve(monkeypatch, _ORTHO_PROTEINS)

    await gene_homes(
        "orthomcl", ["PF3D7_0103400.1-p1"], record_type=None, wdk_step_id=None
    )

    assert (site.datasets, site.reports) == (
        [["PF3D7_0103400.1-p1"]],
        [("sequence", "ByIdList", {"source_ids": "9001"})],
    )


async def test_a_step_of_groups_has_no_homes(monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch, _answer("group", [("OG7_0001234", {})]))

    assert (
        await gene_homes(
            "orthomcl", ["OG7_0001234"], record_type="group", wdk_step_id=1
        )
        == {}
    )


def test_a_set_names_the_sites_it_lists_on() -> None:
    plasmo = {"PF3D7_0103400": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb")}
    proteins = {
        "PF3D7_0103400.1-p1": GeneHome(gene_id="PF3D7_0103400", site_id="plasmodb")
    }

    assert [
        sites_that_list("plasmodb", plasmo),
        sites_that_list("orthomcl", proteins),
        sites_that_list("orthomcl", {}),
    ] == [
        ["PlasmoDB", "VEuPathDB", "OrthoMCL"],
        ["OrthoMCL", "VEuPathDB", "PlasmoDB"],
        ["OrthoMCL"],
    ]
