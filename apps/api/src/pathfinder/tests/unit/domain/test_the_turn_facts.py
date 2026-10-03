"""The facts a turn shows beside its reply, as lines and as carried values."""

from pathfinder.domain.comparison_facts import ComparedVariant, ComparisonFact
from pathfinder.domain.turn_facts import (
    ControlResultFact,
    ParameterFact,
    RetiredFact,
    SavedSetFact,
    StepFact,
    TurnFacts,
    uncarried_assumptions,
)
from pathfinder.domain.value_caveats import AssumedValueCaveat, UnmeasuredValueCaveat

_CLAUSE = (
    "Minimum expression percentile at the site's default of 80: 1,665 genes; "
    "at 0: 8,201"
)


def _percentile(notes: list[str]) -> ParameterFact:
    return ParameterFact(
        name="min_expression_percentile",
        display_name="Minimum expression percentile",
        value="80",
        source="default",
        notes=notes,
    )


def _facts(notes: list[str]) -> TurnFacts:
    return TurnFacts(
        steps=[
            StepFact(
                step_id="c1",
                display_name="Trophozoite RNA-Seq percentile",
                count=1665,
                parameters=[_percentile(notes)],
            )
        ],
        root_count=1665,
    )


def _caveat() -> AssumedValueCaveat:
    return AssumedValueCaveat(
        criterion_id="c1",
        param_display_name="Minimum expression percentile",
        value="80",
        source="default",
        bound_count=1665,
        reading_kind="loosest_bound",
        reading="0",
        reading_count=8201,
    )


def test_a_step_row_shows_its_count_its_values_and_their_measurements() -> None:
    assert _facts([_CLAUSE]).lines() == [
        "Trophozoite RNA-Seq percentile: 1,665 genes",
        "Minimum expression percentile: 80",
        _CLAUSE,
        "Result: 1,665 genes",
    ]


def test_a_default_shown_with_its_measurement_is_carried() -> None:
    assert uncarried_assumptions([_caveat()], _facts([_CLAUSE])) == 0


def test_a_default_shown_without_its_measurement_is_not_carried() -> None:
    assert uncarried_assumptions([_caveat()], _facts([])) == 1


def test_no_facts_part_carries_nothing() -> None:
    assert uncarried_assumptions([_caveat(), _caveat()], None) == 2


def test_a_vocabulary_value_is_shown_with_its_label() -> None:
    term = ParameterFact(
        name="GoTerm",
        display_name="GO term",
        value="GO:0031225",
        label="obsolete anchored component of membrane",
        source="chosen",
    )
    assert term.lines() == [
        "GO term: GO:0031225 (obsolete anchored component of membrane)"
    ]


def test_a_withdrawn_requirement_reads_as_withdrawn() -> None:
    withdrawn = RetiredFact(requirement="above the 50th percentile", state="withdrawn")
    replaced = RetiredFact(
        requirement="organism", state="replaced", replaced_by="Toxoplasma gondii ME49"
    )
    assert (withdrawn.sentence, replaced.sentence) == (
        "'above the 50th percentile' is withdrawn",
        "'organism' is replaced by Toxoplasma gondii ME49",
    )


def test_a_saved_set_and_a_control_result_read_with_their_counts() -> None:
    saved = SavedSetFact(kind="gene_set", name="vaccine candidates draft", count=39)
    result = ControlResultFact(
        tested_label="Signal peptide",
        positives_returned=8,
        positives_total=10,
        negatives_returned=1,
        negatives_total=5,
    )
    assert (saved.line(), result.sentence) == (
        "Saved gene set vaccine candidates draft, 39 genes",
        (
            "Signal peptide: 8 of 10 positive controls returned; "
            "1 of 5 negative controls returned"
        ),
    )


def test_facts_with_nothing_in_them_are_empty() -> None:
    assert (TurnFacts().empty(), _facts([]).empty()) == (True, False)


def test_a_value_whose_other_reading_did_not_arrive_is_not_counted() -> None:
    unmeasured = UnmeasuredValueCaveat(
        criterion_id="c1",
        param_display_name="Minimum expression percentile",
        value="80",
        source="default",
        reading_kind="loosest_bound",
        reading="0",
    )

    assert uncarried_assumptions([unmeasured], None) == 0


def test_a_measurement_a_row_shows_is_no_caveat_as_well() -> None:
    facts = _facts([_CLAUSE]).model_copy(update={"caveats": [_caveat()]})
    carried = TurnFacts.model_validate(facts.model_dump())

    assert (carried.caveats, carried.lines().count(_CLAUSE)) == ([], 1)


def test_a_measurement_no_row_shows_stays_a_caveat() -> None:
    facts = _facts([]).model_copy(update={"caveats": [_caveat()]})
    kept = TurnFacts.model_validate(facts.model_dump())

    assert [c.sentence for c in kept.caveats] == [
        (
            "Minimum expression percentile is 80, the site's default: 1,665 genes "
            "at that value, 8,201 at 0"
        )
    ]


_SIX_FIELDS = (
    '["product", "name", "so_id", "UserCommentContent", "so_term_name", '
    '"organism_full"]'
)


def _compared(*variants: ComparedVariant) -> TurnFacts:
    return TurnFacts(comparisons=[ComparisonFact(variants=list(variants))])


def test_a_compared_variant_row_shows_the_values_it_differs_by() -> None:
    facts = _compared(
        ComparedVariant(
            label="Product field",
            gene_count=2,
            unique_count=0,
            differs_by={"text_fields": '["product"]'},
        ),
        ComparedVariant(
            label="Every text field",
            gene_count=2,
            unique_count=0,
            differs_by={"text_fields": _SIX_FIELDS, "text_expression": "tube*"},
        ),
    )

    assert facts.lines() == [
        "Product field (text_fields: product): 2 genes",
        (
            "Every text field (text_fields: product, name, so_id, "
            "UserCommentContent, so_term_name, organism_full; "
            "text_expression: tube*): 2 genes"
        ),
    ]


def test_a_compared_variant_that_differs_by_nothing_shows_its_count() -> None:
    facts = _compared(
        ComparedVariant(label="As built", gene_count=1, unique_count=0),
        ComparedVariant(label="Again", gene_count=1665, unique_count=0),
    )

    assert facts.lines() == ["As built: 1 gene", "Again: 1,665 genes"]
