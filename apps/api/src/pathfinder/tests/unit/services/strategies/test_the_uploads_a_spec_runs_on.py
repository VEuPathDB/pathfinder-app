"""The upload each criterion runs on: the one its user-dataset parameter binds,
or the one whose study its analysis reads, with its name and its type."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from veupathdb.domain.parameters import SinglePickValue, StringValue
from veupathdb.wdk import WDKSearch
from veupathdb.wdk.vdi.client import VdiServiceError

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.services.strategies import bound_uploads
from pathfinder.services.strategies.bound_uploads import (
    uploads_run_on,
    uploads_the_specs_run_on,
)
from pathfinder.services.strategies.user_dataset_searches import OwnedUpload
from pathfinder.tests._support.bound_values import bound

_FIXTURES = Path(__file__).parents[3] / "fixtures" / "wdk"
_UPLOADS = [
    OwnedUpload(
        vdi_id="p0Z51wRgo404A", name="pathfinder-uat-genelist", type_name="genelist"
    ),
    OwnedUpload(
        vdi_id="lhZ5ptRgo014J", name="pathfinder-uat-deseq", type_name="rnaseqrc"
    ),
]


def _searches() -> dict[str, WDKSearch]:
    raw = json.loads((_FIXTURES / "user_dataset_searches_plasmodb.json").read_text())
    return {entry["urlSegment"]: WDKSearch.model_validate(entry) for entry in raw}


# The DESeq flow's step as it was built: the compute export on the upload's study.
_DESEQ = Criterion(
    id="step_cb47c568",
    text="Genes differentially expressed in pathfinder-uat-deseq using DESeq2.",
    search_name="GenesByEdaVizWithCompute",
    analysis=AnalysisBinding(
        dataset_id="EDAUD_lhZ5ptRgo014J",
        method="DESeq",
        words="Genes that differ between Control and Treated",
    ),
)
_GENE_LIST = Criterion(
    id="c_list",
    text="genes in my gene list",
    search_name="GenesByUserDatasetGeneList",
    resolved_params=bound(
        {"geneListUserDataset": SinglePickValue(value="p0Z51wRgo404A")}
    ),
)


def test_each_step_runs_on_the_upload_it_binds_or_reads() -> None:
    spec = OperationalSpec(goal="uploads", criteria=[_DESEQ, _GENE_LIST])

    assert uploads_run_on(spec, _searches(), _UPLOADS) == {
        "step_cb47c568": _UPLOADS[1],
        "c_list": _UPLOADS[0],
    }


def test_an_upload_id_in_a_parameter_of_another_kind_is_no_upload() -> None:
    typed = Criterion(
        id="c_text",
        text="a text search",
        search_name="GenesByEdaVizWithCompute",
        resolved_params=bound({"eda_dataset_id": StringValue(value="p0Z51wRgo404A")}),
    )
    spec = OperationalSpec(goal="text", criteria=[typed])

    assert uploads_run_on(spec, _searches(), _UPLOADS) == {}


async def test_an_unreadable_upload_listing_answers_no_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _refused(site_id: str) -> list[OwnedUpload]:
        del site_id
        detail = "the listing did not load"
        raise VdiServiceError(detail)

    monkeypatch.setattr(bound_uploads, "owned_uploads", _refused)
    spec = OperationalSpec(goal="deseq", criteria=[_DESEQ])

    assert await uploads_the_specs_run_on("plasmodb", [spec], _searches()) == {}


async def test_a_spec_on_no_upload_reads_no_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listed: list[str] = []

    async def _listing(site_id: str) -> list[OwnedUpload]:
        listed.append(site_id)
        return list(_UPLOADS)

    monkeypatch.setattr(bound_uploads, "owned_uploads", _listing)
    public = _DESEQ.model_copy(
        update={
            "analysis": AnalysisBinding(
                dataset_id="DS_4902d9b7ec", words="a public study"
            )
        }
    )

    found = await uploads_the_specs_run_on(
        "plasmodb", [OperationalSpec(goal="public", criteria=[public])], _searches()
    )

    assert (found, listed) == ({}, [])


async def test_several_specs_read_the_listing_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    listed: list[str] = []

    async def _listing(site_id: str) -> list[OwnedUpload]:
        listed.append(site_id)
        return list(_UPLOADS)

    monkeypatch.setattr(bound_uploads, "owned_uploads", _listing)
    spec = OperationalSpec(goal="deseq", criteria=[_DESEQ])

    found = await uploads_the_specs_run_on("plasmodb", [spec, None, spec], _searches())

    assert (sorted(found), listed) == ([_DESEQ.id], ["plasmodb"])
