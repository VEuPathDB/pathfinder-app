"""A user-dataset search is known by its declared upload type, and offers the
uploads of that type its vocabulary lists under the researcher's token."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.wdk import WDKSearch

from pathfinder.services.strategies.user_dataset_searches import (
    OwnedUpload,
    UserDatasetOffer,
    dataset_parameter,
    export_search_for,
    offers_for,
    user_dataset_types,
)
from pathfinder.tests._support.qa_recording import qa_recording

_FIXTURES = Path(__file__).parents[3] / "fixtures" / "wdk"


def _searches(site: str) -> dict[str, WDKSearch]:
    raw = json.loads(
        qa_recording(_FIXTURES / f"user_dataset_searches_{site}.json").read_text()
    )
    return {entry["urlSegment"]: WDKSearch.model_validate(entry) for entry in raw}


_PLASMO_UPLOADS = [
    OwnedUpload(
        vdi_id="p0Z51wRgo404A", name="pathfinder-uat-genelist", type_name="genelist"
    ),
    OwnedUpload(vdi_id="dMY5sYJRNl11F", name="csv uploaded msps", type_name="genelist"),
    OwnedUpload(
        vdi_id="lhZ5ptRgo014J", name="pathfinder-uat-deseq", type_name="rnaseqrc"
    ),
    OwnedUpload(
        vdi_id="c1Z5oVRJpY04s", name="pathfinder-uat-phenotype", type_name="phenotype"
    ),
]


@pytest.mark.parametrize("site", ["plasmodb", "vectorbase"])
def test_each_search_declares_the_upload_type_it_reads(site: str) -> None:
    searches = _searches(site)
    assert user_dataset_types(searches["GenesByDESeqUserDataset"]) == {"rnaseqrc"}
    assert user_dataset_types(searches["GenesByUserDatasetGeneList"]) == {"genelist"}
    assert user_dataset_types(searches["GenesByPhenotypeUserDataset"]) == {"phenotype"}
    assert user_dataset_types(searches["GenesByEdaVizWithCompute"]) == frozenset()


@pytest.mark.parametrize("site", ["plasmodb", "vectorbase"])
def test_the_dataset_parameter_is_the_searchs_one_single_pick(site: str) -> None:
    searches = _searches(site)
    named = {name: dataset_parameter(search) for name, search in searches.items()}
    assert {name: p.name if p else None for name, p in named.items()} == {
        "GenesByDESeqUserDataset": "eda_dataset_id",
        "GenesByUserDatasetGeneList": "geneListUserDataset",
        "GenesByPhenotypeUserDataset": "eda_dataset_id",
        "GenesByEdaVizWithCompute": None,
    }


def test_each_upload_is_offered_on_the_search_of_its_type() -> None:
    searches = _searches("plasmodb")
    offered = {
        name: offers_for(search, _PLASMO_UPLOADS) for name, search in searches.items()
    }
    assert offered["GenesByUserDatasetGeneList"] == [
        UserDatasetOffer(
            search_name="GenesByUserDatasetGeneList",
            search_display_name="Gene List (User Datasets)",
            parameter="geneListUserDataset",
            value="p0Z51wRgo404A",
            upload_name="pathfinder-uat-genelist",
        ),
        UserDatasetOffer(
            search_name="GenesByUserDatasetGeneList",
            search_display_name="Gene List (User Datasets)",
            parameter="geneListUserDataset",
            value="dMY5sYJRNl11F",
            upload_name="csv uploaded msps",
        ),
    ]
    assert [o.value for o in offered["GenesByDESeqUserDataset"]] == [
        "EDAUD_lhZ5ptRgo014J"
    ]
    assert [o.value for o in offered["GenesByPhenotypeUserDataset"]] == [
        "EDAUD_c1Z5oVRJpY04s"
    ]
    assert offered["GenesByEdaVizWithCompute"] == []


def test_an_upload_the_vocabulary_does_not_list_is_not_offered() -> None:
    """The vocabulary under the researcher's token is the proof the site can run it."""
    deseq = _searches("vectorbase")["GenesByDESeqUserDataset"]
    elsewhere = OwnedUpload(vdi_id="YpZ55YRsoQ144", name="failed", type_name="rnaseqrc")
    assert offers_for(deseq, [elsewhere]) == []


def test_an_account_without_an_upload_of_the_type_has_no_offer() -> None:
    """The vocabulary's placeholder and public entries are no upload of the account."""
    gene_list = _searches("plasmodb")["GenesByUserDatasetGeneList"]
    rnaseq_only = [u for u in _PLASMO_UPLOADS if u.type_name == "rnaseqrc"]
    assert offers_for(gene_list, rnaseq_only) == []


def test_a_volcano_export_of_an_upload_runs_the_differential_expression_search() -> (
    None
):
    searches = list(_searches("plasmodb").values())
    assert (
        export_search_for(
            searches, _PLASMO_UPLOADS, "EDAUD_lhZ5ptRgo014J", reads_a_volcano=True
        )
        == "GenesByDESeqUserDataset"
    )


def test_a_subset_export_of_a_phenotype_upload_runs_the_phenotype_search() -> None:
    searches = list(_searches("plasmodb").values())
    assert (
        export_search_for(
            searches, _PLASMO_UPLOADS, "EDAUD_c1Z5oVRJpY04s", reads_a_volcano=False
        )
        == "GenesByPhenotypeUserDataset"
    )


def test_an_export_no_user_dataset_search_reads_stays_generic() -> None:
    """A subset of counts, and a curated study, have no user-dataset search."""
    searches = list(_searches("plasmodb").values())
    routed = [
        export_search_for(
            searches, _PLASMO_UPLOADS, "EDAUD_lhZ5ptRgo014J", reads_a_volcano=False
        ),
        export_search_for(
            searches, _PLASMO_UPLOADS, "DS_e973eadd57", reads_a_volcano=True
        ),
    ]
    assert routed == [None, None]
