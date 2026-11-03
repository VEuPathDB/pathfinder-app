"""A data-type requirement is grounded by the data a criterion that links it
runs on, as the site marks it: the type of the upload it reads, else the assay
the site's dataset record names for its study or its search."""

from __future__ import annotations

import pytest

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
    DataKind,
    DataTypeValue,
)
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
)
from pathfinder.tests._support.user_dataset_doubles import UPLOAD_DATASET

_STEP = "step_cb47c568"
_ASEXUAL_PERCENTILE = (
    "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"
)
_ANTIBODY_ARRAY = "GenesByAntibodyArrayEdaSubset_PlasmoDB_Loffler_Natural_Infection_AntibodyArray_RSRC"
_NAMED_MICROARRAY = (
    "GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection"
)
_PROFILE = "GenesByProfileSimilarity"
_GAMBIAN_STUDY = "DS_eeca6a5476"


def _asked(data: DataKind | None = "rna_seq") -> Constraint:
    return Constraint(
        id="r_data",
        kind=ConstraintKind.DATA_TYPE,
        label="RNA-Seq dataset",
        requested_value="RNA-Seq",
        source=ConstraintSource.USER_EXPLICIT,
        value=None if data is None else DataTypeValue(data=data),
    )


def _links(linked: bool) -> list[RequirementLink]:
    return [RequirementLink(requirement="r_data")] if linked else []


def _deseq_on(search_name: str, dataset_id: str = UPLOAD_DATASET) -> OperationalSpec:
    return OperationalSpec(
        goal="DESeq2 on a study",
        criteria=[
            Criterion(
                id=_STEP,
                text="Genes differentially expressed in the study.",
                search_name=search_name,
                answers=_links(True),
                analysis=AnalysisBinding(
                    dataset_id=dataset_id,
                    method="DESeq",
                    effect_size_threshold=1.0,
                    effect_size_label="log2(Fold Change)",
                    significance_threshold=0.05,
                    words="Genes that differ between Control and Treated",
                ),
            )
        ],
    )


def _curated(search_name: str, *, linked: bool = True) -> OperationalSpec:
    return OperationalSpec(
        goal="curated",
        criteria=[
            Criterion(
                id="c_cur",
                text="curated",
                search_name=search_name,
                answers=_links(linked),
            )
        ],
    )


def _ground(
    spec: OperationalSpec, marks: DataMarks, asked: Constraint | None = None
) -> tuple[object, ...]:
    [grounded] = ground_against_spec([asked or _asked()], spec, marks=marks)
    return grounded.status, grounded.realized_value, grounded.note


_UNMARKED = (
    ConstraintStatus.UNGROUNDABLE,
    None,
    "no step that links it runs on expression data",
)


def test_a_step_on_an_rna_seq_upload_grounds_the_rna_seq_requirement() -> None:
    for search_name in ("GenesByDESeqUserDataset", "GenesByEdaVizWithCompute"):
        assert _ground(
            _deseq_on(search_name), DataMarks(uploads={_STEP: "rnaseqrc"})
        ) == (ConstraintStatus.GROUNDED, "rna_seq", "")


def test_a_step_on_a_gene_list_upload_runs_on_no_expression_data() -> None:
    assert (
        _ground(
            _deseq_on("GenesByUserDatasetGeneList"),
            DataMarks(uploads={_STEP: "genelist"}),
        )
        == _UNMARKED
    )


def test_a_step_whose_upload_is_not_read_grounds_nothing_by_its_name() -> None:
    assert _ground(_deseq_on("GenesByDESeqUserDataset"), DataMarks()) == _UNMARKED


def test_a_curated_search_grounds_the_requirement_by_its_datasets_assay() -> None:
    marks = DataMarks(searches={_ASEXUAL_PERCENTILE: "RNASeq"})

    assert _ground(_curated(_ASEXUAL_PERCENTILE), marks) == (
        ConstraintStatus.GROUNDED,
        "rna_seq",
        "",
    )


def test_a_search_with_no_mark_grounds_nothing_by_its_name() -> None:
    assert _ground(_curated(_NAMED_MICROARRAY), DataMarks()) == _UNMARKED


def test_a_search_on_an_antibody_array_runs_on_no_expression_data() -> None:
    marks = DataMarks(searches={_ANTIBODY_ARRAY: "Immunology"})

    assert _ground(_curated(_ANTIBODY_ARRAY), marks) == _UNMARKED


@pytest.mark.parametrize(
    ("asked", "mark", "built"),
    [
        ("rna_seq", "DNA Microarray Assay", "microarray"),
        ("microarray", "RNASeq", "rna_seq"),
    ],
)
def test_a_step_on_the_other_assay_substitutes_the_requirement(
    asked: DataKind, mark: str, built: DataKind
) -> None:
    marks = DataMarks(searches={_PROFILE: mark})

    assert _ground(_curated(_PROFILE), marks, _asked(asked)) == (
        ConstraintStatus.SUBSTITUTED,
        built,
        f"asked {asked}, the steps that link it run on {built}",
    )


def test_a_microarray_requirement_is_grounded_by_a_microarray_step() -> None:
    marks = DataMarks(searches={_PROFILE: "DNA Microarray Assay"})

    assert _ground(_curated(_PROFILE), marks, _asked("microarray")) == (
        ConstraintStatus.GROUNDED,
        "microarray",
        "",
    )


def test_an_analysis_on_a_curated_study_grounds_by_the_studys_assay() -> None:
    marks = DataMarks(studies={_GAMBIAN_STUDY: "RNASeq"})

    assert _ground(_deseq_on("GenesByEdaVizWithCompute", _GAMBIAN_STUDY), marks) == (
        ConstraintStatus.GROUNDED,
        "rna_seq",
        "",
    )


def test_the_upload_a_step_reads_outranks_the_mark_of_its_search() -> None:
    marks = DataMarks(
        uploads={_STEP: "genelist"},
        searches={"GenesByEdaVizWithCompute": "RNASeq"},
    )

    assert _ground(_deseq_on("GenesByEdaVizWithCompute"), marks) == _UNMARKED


def test_a_requirement_no_criterion_links_is_not_verified() -> None:
    marks = DataMarks(searches={_PROFILE: "DNA Microarray Assay"})

    assert _ground(_curated(_PROFILE, linked=False), marks) == (
        ConstraintStatus.GROUNDED,
        None,
        "no criterion links it",
    )


def test_a_requirement_with_no_typed_value_is_not_verified() -> None:
    marks = DataMarks(searches={_PROFILE: "DNA Microarray Assay"})

    assert _ground(_curated(_PROFILE), marks, _asked(None)) == (
        ConstraintStatus.GROUNDED,
        None,
        "no typed value to compare",
    )


def test_only_the_criteria_that_link_it_ground_it() -> None:
    spec = OperationalSpec(
        goal="two steps",
        criteria=[
            Criterion(id="c_rna", text="rna", search_name=_ASEXUAL_PERCENTILE),
            Criterion(
                id="c_array",
                text="array",
                search_name=_PROFILE,
                answers=_links(True),
            ),
        ],
    )
    marks = DataMarks(
        searches={_ASEXUAL_PERCENTILE: "RNASeq", _PROFILE: "DNA Microarray Assay"}
    )

    assert _ground(spec, marks)[:2] == (ConstraintStatus.SUBSTITUTED, "microarray")
