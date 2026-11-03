"""An INTERSECT input that states only the organism a sibling already runs on,
or that matches every gene of that organism, narrows nothing, so the structure
fold drops it and holds open the requirements it links."""

from __future__ import annotations

from veupathdb.domain.parameters import MultiPickValue, SinglePickValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    OrganismValue,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.organism_scope import universe_key
from pathfinder.domain.strategy.spec_fold import (
    FoldedStructure,
    fold_organism_universe,
)
from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.tests._support.bound_values import bound

PEST = "Anopheles gambiae PEST"
PF = "Plasmodium falciparum 3D7"
STEPHENSI = "Anopheles stephensi Indian"
ORGANISMS = (PEST, STEPHENSI, PF, "Plasmodium vivax P01")
PEST_ORGANISM = Constraint(
    kind=ConstraintKind.ORGANISM,
    requested_value=PEST,
    label="organism",
    source=ConstraintSource.USER_EXPLICIT,
    value=OrganismValue(organism=PEST),
)
# The genes of each organism, as the site's organism search counts them.
PEST_GENES = 13_845
PF_GENES = 5_720
UNIVERSE: dict[tuple[str, ...], int] = {(PEST,): PEST_GENES, (PF,): PF_GENES}


def _pest_universe(text: str = f"{PEST} genes") -> Criterion:
    return Criterion(
        id="c_pest",
        text=text,
        answers=[RequirementLink(requirement=PEST_ORGANISM.id)],
        search_name="GenesByGeneModelChars",
        organism_param="organism_select_none",
        resolved_params=bound(
            {
                "organism_select_none": MultiPickValue(values=[PEST]),
                "gene_or_transcript": SinglePickValue(value="Genes"),
                "gene_model_char": StringValue(value='{"filters":[]}'),
            },
            defaulted=["gene_model_char", "gene_or_transcript"],
        ),
    )


def _signal(
    organism: str = PEST, criterion_id: str = "c_signal", count: int | None = 627
) -> Criterion:
    """A signal peptide search with every value at its default but the organism."""
    return Criterion(
        id=criterion_id,
        text="proteins with a predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        organism_param="organism",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=[organism]),
                "signalp_version": SinglePickValue(value="SignalP-6.0"),
            },
            defaulted=["signalp_version"],
        ),
        result_count=count,
    )


def _tm(organism: str = PEST) -> Criterion:
    """A transmembrane search that states a range beside the organism."""
    return Criterion(
        id="c_tm",
        text="proteins with 2 to 99 transmembrane domains",
        search_name="GenesByTransmembraneDomains",
        organism_param="organism",
        resolved_params=bound(
            {
                "organism": MultiPickValue(values=[organism]),
                "min_tm": StringValue(value="2"),
                "max_tm": StringValue(value="99"),
            }
        ),
        result_count=1_214,
    )


def _isolates(
    count: int | None = PF_GENES, answers: tuple[Constraint, ...] = ()
) -> Criterion:
    """A SNP search with every value at its default but the organism."""
    return Criterion(
        id="c_isolates",
        text="do not vary much between isolates",
        answers=[RequirementLink(requirement=c.id) for c in answers],
        search_name="GenesByNgsSnps",
        organism_param="organismSinglePick",
        resolved_params=bound(
            {
                "organismSinglePick": MultiPickValue(values=[PF]),
                "snp_stat": StringValue(value="density"),
            },
            defaulted=["snp_stat"],
        ),
        result_count=count,
    )


def _organism_reason(search_name: str, organism: str) -> SearchRationale:
    return SearchRationale(
        search_name=search_name,
        basis="organism",
        term="Organism",
        reason=f"Organism is {organism}.",
        tool_call_id="call_bind",
    )


def _leaf(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _combine(operator: CombineOp, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _counts(criteria: tuple[Criterion, ...]) -> dict[str, int]:
    """Each organism-only leaf's universe count, as the tool reads it."""
    return {
        c.id: UNIVERSE[key]
        for c in criteria
        if (key := universe_key(c, ORGANISMS)) is not None and key in UNIVERSE
    }


def _fold(
    root: StructureNode,
    *criteria: Criterion,
    live: tuple[str, ...] = (),
    counts: dict[str, int] | None = None,
    requirements: tuple[Constraint, ...] = (),
) -> FoldedStructure:
    tree = SpecStructure(root=root)
    spec = OperationalSpec(criteria=list(criteria), structure=tree)
    return fold_organism_universe(
        spec,
        tree,
        ORGANISMS,
        (PEST_ORGANISM, *requirements),
        _counts(criteria) if counts is None else counts,
        live_step_ids=live,
    ).holding_open(requirements)


def test_a_leaf_that_links_only_the_organism_is_dropped_and_met() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_pest"), _leaf("c_signal")),
        _pest_universe(),
        _signal(),
    )

    assert folded.structure.root == _leaf("c_signal")
    assert [(d.criterion_id, d.met, d.carrier_id) for d in folded.dropped] == [
        ("c_pest", True, "c_signal")
    ]
    assert folded.dropped[0].fate == (
        f"c_pest ('{PEST} genes') is dropped: it links only the organism {PEST}, "
        f"which c_signal already runs on, so that organism value meets it."
    )


def _stated(value: str, kind: ConstraintKind = ConstraintKind.UNTYPED) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_VARIES = _stated("do not vary much between isolates")


def test_a_binding_that_matches_its_organism_universe_holds_its_link_open() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_isolates")),
        _signal(PF),
        _isolates(answers=(_VARIES,)),
        requirements=(_VARIES,),
    )

    assert folded.structure.root == _leaf("c_signal")
    assert [(d.criterion_id, d.met, d.requirements) for d in folded.dropped] == [
        ("c_isolates", False, (_VARIES,))
    ]
    assert folded.dropped[0].fate == (
        f"c_isolates ('do not vary much between isolates') is dropped: it matches "
        f"all 5,720 genes of {PF}, which c_signal already runs on, so it narrows "
        f"nothing. 'do not vary much between isolates' stays open: bind a search whose "
        f"values state it, or end with it as a gap."
    )


def test_the_organism_the_dropped_criterion_links_stays_with_the_carrier() -> None:
    organism = _stated(PF, ConstraintKind.ORGANISM)

    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_isolates")),
        _signal(PF),
        _isolates(answers=(organism, _VARIES)),
        requirements=(organism, _VARIES),
    )

    assert [d.requirements for d in folded.dropped] == [(_VARIES,)]


def test_a_dropped_criterion_that_links_nothing_holds_nothing_open() -> None:
    """The text is the researcher's words, and no link names a requirement."""
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_isolates")),
        _signal(PF),
        _isolates(),
        requirements=(_VARIES,),
    )

    assert [d.requirements for d in folded.dropped] == [()]
    assert folded.dropped[0].fate.endswith("so it narrows nothing.")


def test_a_binding_that_sets_only_the_organism_and_narrows_it_is_kept() -> None:
    """A signal peptide search at its defaults still filters its organism's genes."""
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_tm")),
        _signal(PEST),
        _tm(PEST),
    )

    assert (folded.dropped, folded.structure.root) == (
        (),
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_tm")),
    )


def test_a_binding_whose_count_is_unknown_is_kept() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_isolates")),
        _signal(PF),
        _isolates(count=None),
    )

    assert folded.dropped == ()


def test_a_binding_whose_organism_was_not_counted_is_kept() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_tm")),
        _signal(STEPHENSI, count=PEST_GENES),
        _tm(STEPHENSI),
    )

    assert folded.dropped == ()


def test_the_organism_as_the_reason_keeps_a_binding_that_narrows() -> None:
    named = _signal(PEST).model_copy(
        update={"rationale": _organism_reason("GenesWithSignalPeptide", PEST)}
    )

    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_tm")),
        named,
        _tm(PEST),
    )

    assert folded.dropped == ()


def test_a_universe_the_search_decides_is_still_dropped() -> None:
    """The recorded reason decides nothing; the count does."""
    decided = _isolates().model_copy(
        update={
            "rationale": SearchRationale(
                search_name="GenesByNgsSnps",
                basis="only_match",
                term="isolates",
                reason="The only search naming isolates.",
                tool_call_id="call_bind",
            )
        }
    )

    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_isolates")),
        _signal(PF),
        decided,
    )

    assert [(d.criterion_id, d.met) for d in folded.dropped] == [("c_isolates", False)]


def test_an_input_of_another_organism_is_kept() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_isolates")),
        _signal(PEST),
        _isolates(),
    )

    assert folded.dropped == ()
    assert folded.structure.root.kind == "combine"


def test_a_leaf_that_states_more_than_the_organism_is_kept() -> None:
    chromosome = _stated("on chromosome 2L")
    universe = _pest_universe(f"{PEST} genes on chromosome 2L")
    narrowed = universe.model_copy(
        update={
            "answers": [
                *universe.answers,
                RequirementLink(requirement=chromosome.id),
            ],
            "resolved_params": bound(
                universe.param_values, defaulted=["gene_or_transcript"]
            ),
            "result_count": PEST_GENES,
        }
    )

    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_pest"), _leaf("c_signal")),
        narrowed,
        _signal(),
        requirements=(chromosome,),
    )

    assert folded.dropped == ()


def test_a_leaf_whose_organism_holds_no_entry_is_kept() -> None:
    untyped = PEST_ORGANISM.model_copy(update={"id": "r_words", "value": None})
    leaf = _pest_universe().model_copy(
        update={"answers": [RequirementLink(requirement=untyped.id)]}
    )

    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_pest"), _leaf("c_signal")),
        leaf,
        _signal(),
        counts={},
        requirements=(untyped,),
    )

    assert folded.dropped == ()


def test_a_leaf_that_links_nothing_is_kept_whatever_its_text_names() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_pest"), _leaf("c_signal")),
        _pest_universe().model_copy(update={"answers": []}),
        _signal(),
        counts={},
    )

    assert folded.dropped == ()


def test_the_only_leaf_of_the_tree_is_kept() -> None:
    folded = _fold(_leaf("c_pest"), _pest_universe())

    assert (folded.structure.root, folded.dropped) == (_leaf("c_pest"), ())


def test_a_minus_primary_input_is_kept() -> None:
    folded = _fold(
        _combine(CombineOp.MINUS, _leaf("c_pest"), _leaf("c_signal")),
        _pest_universe(),
        _signal(),
    )

    assert folded.dropped == ()


def test_a_transform_input_is_kept() -> None:
    ortho = Criterion(
        id="c_ortho",
        text=f"orthologs in {PEST}",
        search_name="GenesByOrthologs",
        role="transform",
        organism_param="organism",
        resolved_params=bound({"organism": MultiPickValue(values=[PEST])}),
    )
    root = _combine(
        CombineOp.INTERSECT,
        StructureNode(
            kind="transform", criterion_id="c_ortho", inputs=[_leaf("c_pest")]
        ),
        _leaf("c_signal"),
    )

    folded = _fold(root, _pest_universe(), _signal(), ortho)

    assert folded.dropped == ()


def test_a_live_step_is_kept() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_pest"), _leaf("c_signal")),
        _pest_universe(),
        _signal(),
        live=("c_pest",),
    )

    assert folded.dropped == ()


def test_each_leaf_is_read_against_its_own_universe_count() -> None:
    """Two leaves of one organism on two record types hold two counts."""
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_pest"), _leaf("c_again")),
        _pest_universe(),
        _pest_universe().model_copy(update={"id": "c_again"}),
        counts={"c_pest": PEST_GENES, "c_again": PEST_GENES - 1},
    )

    assert folded.structure.root == _leaf("c_again")
    assert [d.criterion_id for d in folded.dropped] == ["c_pest"]


def test_of_two_organism_leaves_one_stays() -> None:
    folded = _fold(
        _combine(CombineOp.INTERSECT, _leaf("c_pest"), _leaf("c_again")),
        _pest_universe(),
        _pest_universe().model_copy(update={"id": "c_again"}),
    )

    assert folded.structure.root == _leaf("c_again")
    assert [d.criterion_id for d in folded.dropped] == ["c_pest"]


def test_a_wider_intersect_keeps_its_other_inputs() -> None:
    folded = _fold(
        _combine(
            CombineOp.INTERSECT,
            _leaf("c_pest"),
            _leaf("c_signal"),
            _leaf("c_second"),
        ),
        _pest_universe(),
        _signal(),
        _signal(criterion_id="c_second"),
    )

    assert folded.structure.root == _combine(
        CombineOp.INTERSECT, _leaf("c_signal"), _leaf("c_second")
    )


def test_an_ortholog_transform_carries_the_organism_it_maps_to() -> None:
    """The carrier is the step whose output holds the organism, not its seed."""
    ortho = Criterion(
        id="c_ortho",
        text=f"orthologs in {PEST}",
        search_name="GenesByOrthologs",
        role="transform",
        organism_param="organism",
        resolved_params=bound({"organism": MultiPickValue(values=[PEST])}),
    )
    root = _combine(
        CombineOp.INTERSECT,
        StructureNode(
            kind="transform", criterion_id="c_ortho", inputs=[_leaf("c_signal")]
        ),
        _leaf("c_pest"),
    )

    folded = _fold(root, _pest_universe(), _signal(PF), ortho)

    assert [(d.criterion_id, d.carrier_id) for d in folded.dropped] == [
        ("c_pest", "c_ortho")
    ]
