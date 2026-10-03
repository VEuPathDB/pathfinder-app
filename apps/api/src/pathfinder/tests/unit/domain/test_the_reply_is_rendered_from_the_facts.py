"""A reply names each fact by a reference, the product renders every reference
from the turn's facts, and a fact written outside a reference is a fault that
names the reference which renders it."""

from __future__ import annotations

import pytest

from pathfinder.domain.comparison_facts import (
    ComparedVariant,
    ComparisonFact,
    SharedGenes,
)
from pathfinder.domain.reply_references import (
    ProseFault,
    UnheldReferenceError,
    prose_faults,
    render_reply,
    shape_faults,
)
from pathfinder.domain.turn_facts import (
    ListedFact,
    ListedRecord,
    ParameterFact,
    SourceFact,
    StepFact,
    TurnFacts,
)

_RECORD_PAGE = "https://cryptodb.org/cryptodb/app/record/gene/"
_STRATEGY = "https://microsporidiadb.org/micro/app/workspace/strategies/1/3"

# microsporidiadb, build 71: E. intestinalis signal peptide 66, the E. cuniculi
# ortholog exclusion 129, 9 in both.
_MICRO = TurnFacts(
    steps=[
        StepFact(
            step_id="step_sp",
            display_name="Predicted Signal Peptide",
            count=66,
            parameters=[
                ParameterFact(
                    name="organism",
                    display_name="Organism",
                    value="Encephalitozoon intestinalis ATCC 50506",
                    source="stated",
                ),
            ],
        ),
        StepFact(
            step_id="step_orth",
            display_name="Orthology Phylogenetic Profile",
            count=129,
            parameters=[
                ParameterFact(
                    name="phyletic_indicator",
                    display_name="Profile Pattern",
                    value="N",
                    label="absent",
                    source="default",
                ),
            ],
        ),
        StepFact(
            step_id="step_join",
            display_name="Intersect",
            operator="INTERSECT",
            count=9,
            count_before=1183,
        ),
    ],
    root_count=9,
    root_count_before=1183,
    strategy_url=_STRATEGY,
)

# cryptodb, build 71: mucin* over C. parvum IOWA-ATCC, product field 2, every
# text field 84, both 2, only every text field 82.
_MUCIN = TurnFacts(
    comparisons=[
        ComparisonFact(
            variants=[
                ComparedVariant(label="Product field", gene_count=2, unique_count=0),
                ComparedVariant(
                    label="All text fields",
                    gene_count=84,
                    unique_count=82,
                    result_count=84,
                ),
            ],
            overlaps=[SharedGenes(a="Product field", b="All text fields", shared=2)],
        )
    ],
    sources=[
        SourceFact(
            url=f"{_RECORD_PAGE}CPATCC_0009860",
            record_id="CPATCC_0009860",
            product="Cryptopsoridial mucin",
        )
    ],
    listed=[
        ListedFact(
            step_id="step_text",
            records=[
                ListedRecord(
                    record_id="CPATCC_0031660", url=f"{_RECORD_PAGE}CPATCC_0031660"
                )
            ],
        )
    ],
)


def test_each_count_reference_renders_the_count_with_the_record_noun() -> None:
    prose = (
        "The signal peptide step returns [count:step_sp] and the result [root], "
        "so the ortholog filter removes [diff:step_sp,root]."
    )

    assert render_reply(prose, _MICRO) == (
        "The signal peptide step returns 66 genes and the result 9 genes, "
        "so the ortholog filter removes 57 genes."
    )


def test_a_count_before_the_edit_is_rendered_thousands_separated() -> None:
    prose = "It held [root_before], and the join [before:step_join] before it."

    assert render_reply(prose, _MICRO) == (
        "It held 1,183 genes, and the join 1,183 genes before it."
    )


def test_a_difference_reads_two_references_to_counts() -> None:
    prose = (
        "The edit removed [diff:root_before,root]; [diff:before:step_join,step_join]."
    )

    assert render_reply(prose, _MICRO) == "The edit removed 1,174 genes; 1,174 genes."


def test_a_value_renders_with_its_label_and_its_source_word() -> None:
    prose = (
        "The pattern is [value:step_orth.phyletic_indicator], "
        "[source:step_orth.phyletic_indicator]; the organism is the one "
        "[source:step_sp.organism]."
    )

    assert render_reply(prose, _MICRO) == (
        "The pattern is N (absent), the site's default; the organism is the one "
        "you stated."
    )


def test_the_url_renders_the_strategy_link() -> None:
    assert render_reply("Open it at [url].", _MICRO) == f"Open it at {_STRATEGY}."


def test_a_comparison_renders_its_genes_unique_result_and_shared_counts() -> None:
    prose = (
        "Every text field finds [compare:All text fields] against "
        "[compare:Product field]: [compare:All text fields:unique] only there, "
        "[compare:Product field,All text fields:shared] in both, and "
        "[compare:All text fields:result] in the result."
    )

    assert render_reply(prose, _MUCIN) == (
        "Every text field finds 84 genes against 2 genes: 82 genes only there, "
        "2 genes in both, and 84 genes in the result."
    )


def test_a_record_renders_its_id_linked_with_its_product() -> None:
    prose = "The hits are [record:CPATCC_0009860] and [record:CPATCC_0031660]."

    assert render_reply(prose, _MUCIN) == (
        f"The hits are [CPATCC_0009860]({_RECORD_PAGE}CPATCC_0009860) "
        f"(Cryptopsoridial mucin) and "
        f"[CPATCC_0031660]({_RECORD_PAGE}CPATCC_0031660)."
    )


def test_a_reference_to_a_step_the_facts_do_not_hold_is_not_rendered() -> None:
    with pytest.raises(UnheldReferenceError, match=r"\[count:step_gone\]"):
        render_reply("It returns [count:step_gone].", _MICRO)


def test_a_reference_to_a_step_the_facts_do_not_hold_is_a_fault() -> None:
    assert prose_faults("It returns [count:step_gone].", _MICRO) == [
        ProseFault(token="[count:step_gone]", kind="unheld_reference")
    ]


def test_a_digit_outside_a_reference_names_the_reference_that_renders_it() -> None:
    faults = prose_faults("The ortholog filter removes 57 genes, from **66**.", _MICRO)

    assert faults == [
        ProseFault(
            token="57",
            kind="number",
            references=("[diff:step_sp,step_join]", "[diff:step_sp,root]"),
        ),
        ProseFault(token="66", kind="number", references=("[count:step_sp]",)),
    ]


def test_a_thousands_separated_count_names_its_reference() -> None:
    faults = prose_faults("It held 1,183 genes.", _MICRO)

    assert faults == [
        ProseFault(
            token="1,183",
            kind="number",
            references=("[before:step_join]", "[root_before]"),
        )
    ]


def test_a_number_glued_to_its_unit_is_a_fault() -> None:
    assert shape_faults("Grown at 37C for a day.") == [
        ProseFault(token="37C", kind="number")
    ]


def test_a_p_value_in_scientific_notation_is_a_fault() -> None:
    assert shape_faults("Genes at p < 1e-6 are kept.") == [
        ProseFault(token="1e-6", kind="number")
    ]


def test_a_number_no_fact_gives_names_no_reference() -> None:
    assert prose_faults("About 628 remain.", _MICRO) == [
        ProseFault(token="628", kind="number")
    ]


def test_an_identifier_shape_outside_a_reference_is_a_fault() -> None:
    faults = prose_faults(
        "CPATCC_0031660 and the GenesByText search step_text hold them.", _MUCIN
    )

    assert faults == [
        ProseFault(
            token="CPATCC_0031660",
            kind="identifier",
            references=("[record:CPATCC_0031660]",),
        ),
        ProseFault(token="GenesByText", kind="identifier"),
        ProseFault(token="step_text", kind="identifier"),
    ]


def test_a_word_of_a_value_names_the_value_reference() -> None:
    assert prose_faults("They are Encephalitozoon genes of ATCC 50506.", _MICRO) == [
        ProseFault(
            token="50506", kind="number", references=("[value:step_sp.organism]",)
        )
    ]


def test_a_link_outside_a_reference_names_its_reference() -> None:
    assert prose_faults(f"See {_STRATEGY} for it.", _MICRO) == [
        ProseFault(token=_STRATEGY, kind="link", references=("[url]",))
    ]


def test_a_source_word_outside_a_reference_names_the_rows_it_could_mean() -> None:
    faults = prose_faults(
        "The pattern is the default, and the organism is what you asked for.",
        _MICRO,
    )

    assert faults == [
        ProseFault(
            token="default",
            kind="source_word",
            references=("[source:step_orth.phyletic_indicator]",),
        ),
        ProseFault(
            token="you asked",
            kind="source_word",
            references=("[source:step_sp.organism]",),
        ),
    ]


def test_prose_that_writes_every_fact_by_reference_holds_no_fault() -> None:
    prose = (
        "1. The signal peptide step returns [count:step_sp].\n"
        "2. The ortholog filter removes [diff:step_sp,root], "
        "[source:step_orth.phyletic_indicator]. Open it at [url]."
    )

    assert prose_faults(prose, _MICRO) == []


# piroplasmadb: one text step of VESA1 genes.
_VESA = TurnFacts(
    steps=[StepFact(step_id="step_cfe9f20f", display_name="Text", count=146)],
    request_messages=[
        (
            "Can you compare the two counts in one sentence I could put in a paper, "
            "i.e. what fraction of the VESA1 genes are on chromosome 1?"
        )
    ],
)
_ON_CHROMOSOME_1 = (
    "VESA1 genes on chromosome 1 are a share of the "
    "total VESA1 gene set [count:step_cfe9f20f]."
)


def test_a_number_the_request_writes_is_prose() -> None:
    assert prose_faults(_ON_CHROMOSOME_1, _VESA) == []


def test_a_p_value_the_request_writes_is_prose() -> None:
    facts = TurnFacts(request_messages=["Keep the genes at P 0.001 or lower."])

    assert prose_faults("Genes at p 0.001 are kept.", facts) == []


def test_a_number_no_request_writes_is_still_a_fault() -> None:
    facts = _VESA.model_copy(update={"request_messages": ["Which genes are VESA1?"]})

    assert prose_faults(_ON_CHROMOSOME_1, facts) == [
        ProseFault(token="1", kind="number")
    ]


def test_a_number_inside_a_request_word_is_still_a_fault() -> None:
    assert prose_faults("It held 4,497 genes.", _VESA) == [
        ProseFault(token="4,497", kind="number")
    ]


def test_a_gene_id_the_request_writes_is_still_an_identifier_fault() -> None:
    facts = TurnFacts(request_messages=["Is CPATCC_0031660 a mucin?"])

    assert prose_faults("CPATCC_0031660 is a mucin.", facts) == [
        ProseFault(token="CPATCC_0031660", kind="identifier")
    ]


def test_the_request_messages_stay_off_the_wire() -> None:
    assert "requestMessages" not in _VESA.model_dump(by_alias=True)
