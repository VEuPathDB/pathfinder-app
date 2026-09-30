"""A data-type requirement is grounded by the data a step runs on: the type of
the upload it reads, else the curated expression search it runs."""

from __future__ import annotations

from pathfinder.domain.strategy.analysis_binding import AnalysisBinding
from pathfinder.domain.strategy.constraint_grounding import ground_against_spec
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    ConstraintStatus,
)
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


def _deseq_on_the_upload(search_name: str) -> OperationalSpec:
    return OperationalSpec(
        goal="DESeq2 on my upload",
        criteria=[
            Criterion(
                id=_STEP,
                text="Genes differentially expressed in pathfinder-uat-deseq.",
                search_name=search_name,
                analysis=AnalysisBinding(
                    dataset_id=UPLOAD_DATASET,
                    method="DESeq",
                    effect_size_threshold=1.0,
                    effect_size_label="log2(Fold Change)",
                    significance_threshold=0.05,
                    words="Genes that differ between Control and Treated",
                ),
            )
        ],
    )


def test_a_step_on_an_rna_seq_upload_grounds_the_rna_seq_requirement() -> None:
    for search_name in ("GenesByDESeqUserDataset", "GenesByEdaVizWithCompute"):
        [grounded] = ground_against_spec(
            [_RNA_SEQ],
            _deseq_on_the_upload(search_name),
            upload_types={_STEP: "rnaseqrc"},
        )

        assert (grounded.status, grounded.realized_value, grounded.note) == (
            ConstraintStatus.GROUNDED,
            "rna-seq",
            "",
        )


def test_a_step_on_a_gene_list_upload_runs_on_no_expression_data() -> None:
    [grounded] = ground_against_spec(
        [_RNA_SEQ],
        _deseq_on_the_upload("GenesByUserDatasetGeneList"),
        upload_types={_STEP: "genelist"},
    )

    assert (grounded.status, grounded.note) == (
        ConstraintStatus.UNGROUNDABLE,
        "no step runs on expression data",
    )


def test_a_step_whose_upload_is_not_read_grounds_nothing_by_its_name() -> None:
    [grounded] = ground_against_spec(
        [_RNA_SEQ], _deseq_on_the_upload("GenesByDESeqUserDataset")
    )

    assert grounded.status is ConstraintStatus.UNGROUNDABLE


def test_a_curated_expression_search_still_grounds_the_requirement() -> None:
    curated = OperationalSpec(
        goal="percentile",
        criteria=[
            Criterion(
                id="c_pct",
                text="expressed in asexual stages",
                search_name=(
                    "GenesByRNASeqpfal3D7_Gomez-Diaz_asexual_stages_ebi_rnaSeq_"
                    "RSRCPercentile"
                ),
            )
        ],
    )

    [grounded] = ground_against_spec([_RNA_SEQ], curated)

    assert (grounded.status, grounded.realized_value) == (
        ConstraintStatus.GROUNDED,
        "rna-seq",
    )
