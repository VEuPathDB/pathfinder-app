"""A data-type requirement is grounded by the data a step runs on, as the site
marks it: the type of the upload it reads, else the assay the site's dataset
record names for its study or its search."""

from __future__ import annotations

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
)
from pathfinder.domain.strategy.data_marks import DataMarks
from pathfinder.domain.strategy.operational_spec import Criterion, OperationalSpec
from pathfinder.tests._support.user_dataset_doubles import UPLOAD_DATASET

# The recorded DESeq flow on plasmodb: one step on the researcher's upload.
_STEP = "step_cb47c568"
_RNA_SEQ = Constraint(
    kind=ConstraintKind.DATA_TYPE,
    label="RNA-Seq dataset",
    requested_value="RNA-Seq",
    source=ConstraintSource.USER_EXPLICIT,
)
# Curated plasmodb searches, each named by one dataset record.
_ASEXUAL_PERCENTILE = (
    "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_RSRCPercentile"
)
_ANTIBODY_ARRAY = "GenesByAntibodyArrayEdaSubset_PlasmoDB_Loffler_Natural_Infection_AntibodyArray_RSRC"
# A plasmodb search whose name says microarray and that no dataset record names.
_NAMED_MICROARRAY = (
    "GenesByAntibodyArraypfal3D7_microarrayAntibody_Loffler_Natural_Infection"
)
# A curated plasmodb study and the export search a compute on it runs.
_GAMBIAN_STUDY = "DS_eeca6a5476"


def _deseq_on(search_name: str, dataset_id: str = UPLOAD_DATASET) -> OperationalSpec:
    return OperationalSpec(
        goal="DESeq2 on a study",
        criteria=[
            Criterion(
                id=_STEP,
                text="Genes differentially expressed in the study.",
                search_name=search_name,
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


def _curated(search_name: str) -> OperationalSpec:
    return OperationalSpec(
        goal="curated",
        criteria=[Criterion(id="c_cur", text="curated", search_name=search_name)],
    )


def _ground(spec: OperationalSpec, marks: DataMarks) -> tuple[object, ...]:
    [grounded] = ground_against_spec([_RNA_SEQ], spec, marks=marks)
    return grounded.status, grounded.realized_value, grounded.note


def test_a_step_on_an_rna_seq_upload_grounds_the_rna_seq_requirement() -> None:
    for search_name in ("GenesByDESeqUserDataset", "GenesByEdaVizWithCompute"):
        assert _ground(
            _deseq_on(search_name), DataMarks(uploads={_STEP: "rnaseqrc"})
        ) == (ConstraintStatus.GROUNDED, "rna-seq", "")


def test_a_step_on_a_gene_list_upload_runs_on_no_expression_data() -> None:
    assert _ground(
        _deseq_on("GenesByUserDatasetGeneList"), DataMarks(uploads={_STEP: "genelist"})
    ) == (ConstraintStatus.UNGROUNDABLE, None, "no step runs on expression data")


def test_a_step_whose_upload_is_not_read_grounds_nothing_by_its_name() -> None:
    assert _ground(_deseq_on("GenesByDESeqUserDataset"), DataMarks()) == (
        ConstraintStatus.UNGROUNDABLE,
        None,
        "no step runs on expression data",
    )


def test_a_curated_search_grounds_the_requirement_by_its_datasets_assay() -> None:
    marks = DataMarks(searches={_ASEXUAL_PERCENTILE: "RNASeq"})

    assert _ground(_curated(_ASEXUAL_PERCENTILE), marks) == (
        ConstraintStatus.GROUNDED,
        "rna-seq",
        "",
    )


def test_a_search_with_no_mark_grounds_nothing_by_its_name() -> None:
    assert _ground(_curated(_NAMED_MICROARRAY), DataMarks()) == (
        ConstraintStatus.UNGROUNDABLE,
        None,
        "no step runs on expression data",
    )


def test_a_search_on_an_antibody_array_runs_on_no_expression_data() -> None:
    marks = DataMarks(searches={_ANTIBODY_ARRAY: "Immunology"})

    assert _ground(_curated(_ANTIBODY_ARRAY), marks) == (
        ConstraintStatus.UNGROUNDABLE,
        None,
        "no step runs on expression data",
    )


def test_a_search_whose_name_names_no_assay_is_read_by_its_mark() -> None:
    marks = DataMarks(searches={"GenesByProfileSimilarity": "DNA Microarray Assay"})

    assert _ground(_curated("GenesByProfileSimilarity"), marks) == (
        ConstraintStatus.SUBSTITUTED,
        "microarray",
        "requested RNA-Seq but only microarray searches were selected",
    )


def test_an_analysis_on_a_curated_study_grounds_by_the_studys_assay() -> None:
    marks = DataMarks(studies={_GAMBIAN_STUDY: "RNASeq"})

    assert _ground(_deseq_on("GenesByEdaVizWithCompute", _GAMBIAN_STUDY), marks) == (
        ConstraintStatus.GROUNDED,
        "rna-seq",
        "",
    )


def test_the_upload_a_step_reads_outranks_the_mark_of_its_search() -> None:
    marks = DataMarks(
        uploads={_STEP: "genelist"},
        searches={"GenesByEdaVizWithCompute": "RNASeq"},
    )

    assert _ground(_deseq_on("GenesByEdaVizWithCompute"), marks)[0] is (
        ConstraintStatus.UNGROUNDABLE
    )
