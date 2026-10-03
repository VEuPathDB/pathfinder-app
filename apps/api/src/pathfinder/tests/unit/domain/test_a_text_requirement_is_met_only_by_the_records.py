"""A requirement a text value states, and no other criterion answers, stays met
since its step answers it; a reader is shown it unshown when a sampled record
judged not to fit, or a column some record falls outside, shows it missing."""

from __future__ import annotations

from pathfinder.domain.caveats import check_gaps
from pathfinder.domain.evidence import (
    ColumnFit,
    GeneFit,
    RequirementCheck,
    SampledGene,
    VerificationReview,
)
from pathfinder.domain.shown_requirements import TextQuery, held_to_the_records
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
    provisional_constraints,
)
from pathfinder.tests._support.column_fits import tm_fit

_TEXT = "step_b0f1"
_SUBUNITS = "include every subunit of the lectin, including Hgl, Lgl, Igl1, and Igl2"
_HELD = provisional_constraints(
    [
        Constraint(
            kind=ConstraintKind.OTHER,
            requested_value=_SUBUNITS,
            label="lectin subunits",
            source=ConstraintSource.USER_EXPLICIT,
        )
    ]
)


_TEXTS = [
    TextQuery(criterion_id=_TEXT, param="text_expression", value="Hgl OR Lgl OR Igl1")
]


def _row(
    answered_by: str, shown_by: list[str], text: str = _SUBUNITS
) -> RequirementCheck:
    return RequirementCheck(
        text=text,
        turn=1,
        answered_by=[answered_by],
        how="search",
        status="met",
        note="text_expression includes Hgl, Lgl, Igl1, and Igl2 as alternatives",
        shown_by=shown_by,
    )


def _gene(gene_id: str, fits: GeneFit) -> SampledGene:
    return SampledGene(
        gene_id=gene_id,
        product="galactose-inhibitable lectin 35 kDa subunit",
        fits=fits,
        why=(
            "the product names none of Hgl, Lgl or Igl1"
            if fits == "no"
            else "the product names a galactose-inhibitable lectin"
        ),
    )


def _unjudged(review: VerificationReview) -> VerificationReview:
    """The review with its one row left unjudged by the records."""
    [row] = review.requirements
    unjudged = row.model_copy(
        update={
            "note": (
                "no sampled record judged it; the query text alone does not show it"
            ),
            "no_record_judged_it": True,
        }
    )
    return review.model_copy(update={"requirements": [unjudged]})


def test_an_unclear_record_is_no_evidence_the_requirement_is_missing() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, [])],
        sampled_genes=[_gene("EHI_035690", "unclear"), _gene("EHI_133900", "unclear")],
    )

    assert held_to_the_records(review, _TEXTS) == _unjudged(review)


def test_a_text_requirement_a_record_is_judged_short_of_is_unshown() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, [])],
        sampled_genes=[_gene("EHI_035690", "unclear"), _gene("EHI_133900", "no")],
    )

    [row] = held_to_the_records(review, _TEXTS).requirements

    assert (row.shown_status, row.note) == (
        "unshown",
        (
            "0 of 2 sampled records fit and no column fit shows it; the query "
            "text alone does not show it"
        ),
    )


def test_a_sampled_record_that_shows_it_keeps_it_met() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, ["EHI_035690"])],
        sampled_genes=[_gene("EHI_035690", "yes")],
    )

    assert held_to_the_records(review, _TEXTS) == review


def test_a_record_judged_short_of_it_shows_nothing() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, ["EHI_035690"])],
        sampled_genes=[_gene("EHI_035690", "no")],
    )

    [row] = held_to_the_records(review, _TEXTS).requirements
    assert row.shown_status == "unshown"


def test_a_criterion_that_binds_no_text_query_needs_no_record() -> None:
    review = VerificationReview(
        requirements=[_row("c_tm", [], text="two or more transmembrane domains")],
        column_fits=[tm_fit(40, 40)],
    )

    assert held_to_the_records(review, _TEXTS) == review


def _product_fit(fitting: int, total: int) -> ColumnFit:
    return ColumnFit(
        criterion_id=_TEXT,
        criterion_text="Gal/GalNAc lectin subunits",
        wdk_step_id=441096900,
        column="gene_product",
        display_name="Product Description",
        bound_value="names a Gal/GalNAc lectin subunit",
        total=total,
        fitting=fitting,
        fitting_at_most=fitting,
    )


def test_a_column_every_record_fits_keeps_a_text_requirement_met() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, ["gene_product"])],
        column_fits=[_product_fit(4, 4)],
    )

    assert held_to_the_records(review, _TEXTS) == review


def test_a_column_some_records_fit_does_not_show_it() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, ["gene_product"])],
        column_fits=[_product_fit(1, 4)],
    )

    [row] = held_to_the_records(review, _TEXTS).requirements
    assert row.shown_status == "unshown"


def test_a_column_of_another_criterion_is_no_evidence_either_way() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, ["tm_count"])],
        column_fits=[tm_fit(40, 40)],
    )

    assert held_to_the_records(review, _TEXTS) == _unjudged(review)


def test_every_sampled_gene_fitting_shows_a_text_requirement() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, [])],
        sampled_genes=[_gene(f"EHI_0{n}", "yes") for n in range(35690, 35698)],
    )

    assert held_to_the_records(review, _TEXTS) == review


def test_a_partial_sample_fit_shows_its_share() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, [])],
        sampled_genes=[
            *(_gene(f"EHI_0{n}", "yes") for n in range(35690, 35693)),
            *(_gene(f"EHI_1{n}", "no") for n in range(33900, 33905)),
        ],
    )

    [row] = held_to_the_records(review, _TEXTS).requirements

    assert (row.shown_status, row.note) == (
        "unshown",
        (
            "3 of 8 sampled records fit and no column fit shows it; the query "
            "text alone does not show it"
        ),
    )


def test_no_sample_and_no_column_leaves_a_text_requirement_unjudged() -> None:
    review = VerificationReview(requirements=[_row(_TEXT, [])])

    assert held_to_the_records(review, _TEXTS) == _unjudged(review)


def test_a_column_some_records_fall_outside_with_no_sample_says_so() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, ["gene_product"])],
        column_fits=[_product_fit(1, 4)],
    )

    [row] = held_to_the_records(review, _TEXTS).requirements

    assert row.note == (
        "no column fit or sampled record of this check shows it; the query text "
        "alone does not show it"
    )


_DM28C_SAMPLE = {
    "C4B63_121g77": "trans-sialidase, Group V",
    "C4B63_16g142": "trans-sialidase, Group II",
    "C4B63_22g135": "trans-sialidase, Group V",
    "C4B63_29g57": "trans-sialidase, Group V",
    "C4B63_35g363": "trans-sialidase, Group VIII",
    "C4B63_54g93": "trans-sialidase, Group V",
    "C4B63_60g90": "trans-sialidase, Group V",
    "C4B63_75g84": "trans-sialidase, Group VII",
}


def test_a_product_text_query_whose_sample_all_fits_stays_met() -> None:
    row = RequirementCheck(
        text="trans-sialidase",
        turn=3,
        answered_by=["step_text"],
        how="parameter",
        status="met",
        note="text_expression is trans-sialidase over the product fields",
    )
    review = VerificationReview(
        requirements=[row],
        sampled_genes=[
            SampledGene(
                gene_id=gene_id,
                product=product,
                fits="yes",
                why=f"the product is {product}",
            )
            for gene_id, product in _DM28C_SAMPLE.items()
        ],
    )

    assert (
        held_to_the_records(
            review,
            [
                TextQuery(
                    criterion_id="step_text",
                    param="text_expression",
                    value="trans-sialidase",
                )
            ],
        )
        == review
    )


def test_a_demoted_row_is_a_gap_that_says_no_sampled_record_shows_it() -> None:
    review = VerificationReview(
        requirements=[_row(_TEXT, [])],
        sampled_genes=[_gene("EHI_035690", "no")],
    )
    held = held_to_the_records(review, _TEXTS)

    [gap] = check_gaps(structure=None, words=[], review=held, requirements=_HELD)

    assert (held.requirements[0].no_record_shows_it, gap.sentence) == (
        True,
        f"'{_SUBUNITS}': no sampled record shows it",
    )


def test_a_row_the_check_filed_unmet_is_a_gap_of_the_strategy() -> None:
    row = RequirementCheck(text=_SUBUNITS, turn=1, how="search", status="unmet")

    [gap] = check_gaps(
        structure=None,
        words=[],
        review=VerificationReview(requirements=[row]),
        requirements=_HELD,
    )

    assert gap.sentence == f"'{_SUBUNITS}': nothing in the strategy answers it"


# The piroplasmadb check: a text step and a signal peptide step, both on the
# stated organism, and every sampled record of that organism judged unclear.
_WINNIE = "Cytauxzoon felis strain Winnie"
_GPI_STEP = "step_0c6996fa"
_SIGNAL_STEP = "step_6a264618"
_GPI_QUERY = TextQuery(
    criterion_id=_GPI_STEP, param="text_expression", value="GPI anchor"
)
_WINNIE_PRODUCTS = {
    "CF000144": "Serine aminopeptidase, S33 | domain-containing protein",
    "CF000749": "unspecified product",
    "CF001117": "hypothetical protein",
    "CF002025": "Domain of unknown function, DUF529 | domain-containing protein",
    "CF002191": "Thioredoxin | domain-containing protein",
    "CF002937": "unspecified product",
    "CF003831": "hypothetical protein",
    "CF004023": (
        "Serine aminopeptidase, S33 | Domain of unknown function, DUF529 | "
        "domain-containing protein"
    ),
}
_WINNIE_SAMPLE = [
    SampledGene(
        gene_id=gene_id,
        product=product,
        organism=_WINNIE,
        fits="unclear",
        why="the record does not state its signal peptide classification",
    )
    for gene_id, product in _WINNIE_PRODUCTS.items()
]


def _winnie_row(text: str, answered_by: list[str], fits: GeneFit) -> VerificationReview:
    row = RequirementCheck(
        text=text,
        turn=1,
        answered_by=answered_by,
        how="parameter",
        status="met",
        note="the organism parameter",
    )
    sample = [g.model_copy(update={"fits": fits}) for g in _WINNIE_SAMPLE]
    return VerificationReview(requirements=[row], sampled_genes=sample)


def test_the_organism_row_every_record_is_unclear_on_stands_met() -> None:
    review = _winnie_row(
        "Cytauxzoon felis Winnie genes", [_GPI_STEP, _SIGNAL_STEP], "unclear"
    )

    assert held_to_the_records(review, [_GPI_QUERY]) == review


def test_an_organism_row_a_text_step_shares_is_not_held_to_the_records() -> None:
    review = _winnie_row(
        "Cytauxzoon felis Winnie genes", [_GPI_STEP, _SIGNAL_STEP], "no"
    )

    assert held_to_the_records(review, [_GPI_QUERY]) == review


def test_a_row_the_text_value_does_not_state_is_not_held() -> None:
    review = _winnie_row("Cytauxzoon felis Winnie genes", [_GPI_STEP], "no")

    assert held_to_the_records(review, [_GPI_QUERY]) == review


def test_a_row_another_criterion_answers_as_well_is_not_held() -> None:
    review = _winnie_row("a predicted GPI anchor", [_GPI_STEP, _SIGNAL_STEP], "no")

    assert held_to_the_records(review, [_GPI_QUERY]) == review


_GPI_ROW = "a predicted GPI anchor"
# The record the piroplasmadb check judged against the GPI anchor text.
_GPI_MISS = SampledGene(
    gene_id="CF001077",
    product="Gaa1-like, GPI transamidase component | domain-containing protein",
    organism=_WINNIE,
    fits="no",
    why=(
        "The displayed product mentions GPI transamidase but does not contain "
        "the requested 'GPI anchor' phrase."
    ),
)
_ORGANISM_MISS = SampledGene(
    gene_id="CF000144",
    product="Serine aminopeptidase, S33 | domain-containing protein",
    organism="Theileria orientalis strain Shintoku",
    fits="no",
    why="The record's organism is not the requested Cytauxzoon felis strain Winnie.",
)


def _gpi_review(*genes: SampledGene) -> VerificationReview:
    row = RequirementCheck(
        text=_GPI_ROW,
        turn=1,
        answered_by=[_GPI_STEP],
        how="parameter",
        status="met",
        note="text_expression is GPI anchor over the product fields",
    )
    return VerificationReview(requirements=[row], sampled_genes=list(genes))


def test_a_record_judged_short_of_the_text_keeps_the_row_met_and_unshown() -> None:
    [row] = held_to_the_records(_gpi_review(_GPI_MISS), [_GPI_QUERY]).requirements

    assert (row.status, row.shown_status) == ("met", "unshown")


def test_a_record_judged_short_of_another_requirement_is_no_absence_of_the_text() -> (
    None
):
    [row] = held_to_the_records(_gpi_review(_ORGANISM_MISS), [_GPI_QUERY]).requirements

    assert (row.status, row.no_record_shows_it, row.no_record_judged_it) == (
        "met",
        False,
        True,
    )


def test_a_text_row_every_record_is_unclear_on_is_unjudged_not_confirmed() -> None:
    review = _winnie_row(_GPI_ROW, [_GPI_STEP], "unclear")

    [row] = held_to_the_records(review, [_GPI_QUERY]).requirements

    assert (row.status, row.no_record_judged_it, row.shown_status, row.note) == (
        "met",
        True,
        "unjudged",
        "no sampled record judged it; the query text alone does not show it",
    )


def test_a_text_row_a_record_shows_is_confirmed() -> None:
    shown = _GPI_MISS.model_copy(update={"fits": "yes"})
    review = _gpi_review(shown).model_copy(
        update={
            "requirements": [
                _gpi_review()
                .requirements[0]
                .model_copy(update={"shown_by": ["CF001077"]})
            ]
        }
    )

    [row] = held_to_the_records(review, [_GPI_QUERY]).requirements

    assert (row.status, row.shown_status) == ("met", "met")
