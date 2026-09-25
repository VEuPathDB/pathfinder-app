"""The review VERIFY returns is held to the record: a breached combination and a
word no search states are rows the check cannot omit, and a gene or a source
stands only when this turn read it."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.lead.verify_review import ReviewRecord, review_held_to_the_turn
from pathfinder.domain.evidence import (
    Citation,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.strategy.combination_check import first_combination_violation
from pathfinder.domain.strategy.constraints import Constraint, ConstraintKind
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.lead.conftest import requirement

_COMBINATION = "mass spectrometry evidence OR DeRisi expression"
_ASKED = "Kinases with mass spectrometry evidence or DeRisi expression."
_ADDED = "Keep only the orthologs of P. berghei genes."
_READ = "https://plasmodb.org/plasmo/app/record/gene/PF3D7_0102200"
_PAPER = "10.1038/nature12970"


def _combination() -> Constraint:
    return requirement(
        ConstraintKind.COMBINATION, "how the evidence combines", _COMBINATION
    )


def _spec(
    operator: CombineOp, *, unexpressed: list[str] | None = None
) -> OperationalSpec:
    return OperationalSpec(
        goal="kinase drug targets",
        criteria=[
            Criterion(
                id="c_ms",
                text="trophozoite mass spectrometry evidence",
                search_name="GenesByMassSpec",
            ),
            Criterion(
                id="c_derisi",
                text="DeRisi timecourse expression",
                search_name="GenesByRNASeqEvidence",
                unexpressed_qualifiers=list(unexpressed or []),
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=operator,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="c_ms"),
                    StructureNode(kind="leaf", criterion_id="c_derisi"),
                ],
            )
        ),
    )


def _record(spec: OperationalSpec, *, read: tuple[str, ...] = ()) -> ReviewRecord:
    return ReviewRecord(
        messages=(_ASKED, _ADDED),
        requirements=(_combination(),),
        spec=spec,
        read_as=lambda reference: reference if reference in read else None,
        record_url=lambda gene_id: (
            f"https://plasmodb.org/plasmo/app/record/gene/{gene_id}"
        ),
    )


_MET_STRUCTURE = RequirementCheck(
    text="mass spec evidence or DeRisi expression",
    turn=1,
    answered_by=["c_ms", "c_derisi"],
    how="structure",
    status="met",
    note="the two leaves meet at a combine",
)


def test_a_breached_combination_replaces_the_row_that_called_it_met() -> None:
    spec = _spec(CombineOp.INTERSECT)
    structure = spec.structure
    assert structure is not None
    breach = first_combination_violation([_combination()], spec.criteria, structure)
    assert breach is not None

    held = review_held_to_the_turn(
        VerificationReview(requirements=[_MET_STRUCTURE]), _record(spec)
    )

    assert held.requirements == [
        RequirementCheck(
            text=_COMBINATION,
            turn=1,
            answered_by=["c_derisi", "c_ms"],
            how="structure",
            status="unmet",
            note=breach.message,
        )
    ]


def test_a_combination_the_tree_honours_keeps_the_checkers_row() -> None:
    held = review_held_to_the_turn(
        VerificationReview(requirements=[_MET_STRUCTURE]),
        _record(_spec(CombineOp.UNION)),
    )

    assert held.requirements == [_MET_STRUCTURE]


def test_a_word_no_search_states_is_an_unexpressed_row() -> None:
    held = review_held_to_the_turn(
        VerificationReview(), _record(_spec(CombineOp.UNION, unexpressed=["orthologs"]))
    )

    assert held.requirements == [
        RequirementCheck(
            text="orthologs",
            turn=2,
            answered_by=["c_derisi"],
            how="search",
            status="unexpressed",
            note="no search the framing pass read can state 'orthologs'",
        )
    ]


def test_a_row_that_calls_an_unexpressed_word_met_is_corrected() -> None:
    claimed = RequirementCheck(
        text="the orthologs of P. berghei genes",
        turn=2,
        answered_by=["c_derisi"],
        how="transform",
        status="met",
        note="an ortholog transform",
    )

    held = review_held_to_the_turn(
        VerificationReview(requirements=[claimed]),
        _record(_spec(CombineOp.UNION, unexpressed=["orthologs"])),
    )

    assert held.requirements == [
        claimed.model_copy(
            update={
                "status": "unexpressed",
                "note": "no search the framing pass read can state 'orthologs'",
            }
        )
    ]


def _gene(gene_id: str) -> SampledGene:
    return SampledGene(
        gene_id=gene_id,
        product="ring-infected erythrocyte surface antigen",
        organism="Plasmodium falciparum 3D7",
        fits="yes",
        why="the product is an exported surface antigen",
    )


def test_a_gene_stands_only_when_this_turn_read_its_record() -> None:
    held = review_held_to_the_turn(
        VerificationReview(
            sampled_genes=[_gene("PF3D7_0102200"), _gene("PF3D7_0935800")]
        ),
        _record(_spec(CombineOp.UNION), read=(_READ,)),
    )

    assert [gene.gene_id for gene in held.sampled_genes] == ["PF3D7_0102200"]


def test_a_source_stands_only_when_a_read_of_this_turn_returned_it() -> None:
    retrieved = Citation(
        kind="literature", label="Exportome", doi=_PAPER, why="lists exported proteins"
    )
    invented = Citation(
        kind="web",
        label="A page",
        url="https://example.org/never-read",
        why="not read",
    )

    held = review_held_to_the_turn(
        VerificationReview(sources=[retrieved, invented]),
        _record(_spec(CombineOp.UNION), read=(_PAPER,)),
    )

    assert held.sources == [retrieved]
