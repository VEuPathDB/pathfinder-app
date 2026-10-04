"""A spec reads from the site what each criterion runs on: the type of the
upload it reads, and the assay of the dataset record its study or search names."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.services.strategies import bound_uploads
from pathfinder.services.strategies.data_marks import read_data_marks
from pathfinder.services.strategies.user_dataset_searches import OwnedUpload
from pathfinder.tests._support.user_dataset_doubles import UPLOAD_DATASET

_PERCENTILE = "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"


def _on(study: str, step_id: str) -> Criterion:
    return Criterion(
        id=step_id,
        text="genes the compute keeps",
        search_name="GenesByEdaVizWithCompute",
        analysis=AnalysisBinding(dataset_id=study, method="DESeq", words="DESeq"),
    )


async def test_each_criterion_is_marked_by_its_upload_its_study_or_its_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _uploads(site_id: str) -> list[OwnedUpload]:
        assert site_id == "plasmodb"
        return [
            OwnedUpload(
                vdi_id="lhZ5ptRgo014J",
                name="pathfinder-uat-deseq",
                type_name="rnaseqrc",
            )
        ]

    monkeypatch.setattr(bound_uploads, "owned_uploads", _uploads)
    spec = OperationalSpec(
        goal="three kinds of data",
        criteria=[
            _on(UPLOAD_DATASET, "step_upload"),
            _on("DS_eeca6a5476", "step_study"),
            Criterion(id="step_pct", text="expressed", search_name=_PERCENTILE),
            Criterion(id="step_text", text="kinase", search_name="GenesByText"),
        ],
    )

    marks = await read_data_marks("plasmodb", [spec])

    assert marks == DataMarks(
        uploads={"step_upload": "rnaseqrc"},
        studies={"DS_eeca6a5476": "RNASeq"},
        searches={_PERCENTILE: "RNASeq"},
    )


async def test_every_spec_named_is_read_and_no_spec_reads_nothing() -> None:
    first = OperationalSpec(
        goal="g", criteria=[Criterion(id="a", text="t", search_name=_PERCENTILE)]
    )
    second = OperationalSpec(
        goal="g",
        criteria=[Criterion(id="b", text="t", search_name="GenesByProfileSimilarity")],
    )

    assert (
        await read_data_marks("plasmodb", [first, None, second]),
        await read_data_marks("plasmodb", [None]),
    ) == (
        DataMarks(
            searches={
                _PERCENTILE: "RNASeq",
                "GenesByProfileSimilarity": "DNA Microarray Assay",
            }
        ),
        DataMarks(),
    )
