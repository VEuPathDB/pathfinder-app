"""Every reference of the grammar renders from the facts a recorded turn showed,
a difference admits exactly the differences of two held counts, and a reference
the grammar cannot read is refused, never rendered."""

from __future__ import annotations

from itertools import permutations

import pytest

from pathfinder.domain.comparison_facts import (
    ComparedVariant,
    ComparisonFact,
    SharedGenes,
)
from pathfinder.domain.record_page import ListedRecord
from pathfinder.domain.reply_references import (
    ProseFault,
    UnheldReferenceError,
    prose_faults,
    render_reply,
)
from pathfinder.domain.turn_facts import (
    ListedFact,
    SourceFact,
    StepFact,
    TurnFacts,
)

_TOXO_RECORD = "https://toxodb.org/toxo/app/record/gene/"
_TOXO_STRATEGY = "https://toxodb.org/toxo/app/workspace/strategies/330870683/441173213"
_MICRO_STRATEGY = (
    "https://microsporidiadb.org/micro/app/workspace/strategies/330870613/441173013"
)


def _param(
    name: str, display: str, value: str, label: str, source: str
) -> dict[str, str]:
    return {
        "name": name,
        "displayName": display,
        "value": value,
        "label": label,
        "source": source,
    }


# The facts part a toxodb turn wrote: GT1 signal peptides 680, no ortholog in
# N. caninum Liverpool 1,240, both 53. The record and the listing are the ones
# the turn before it read from the same intersect.
_TOXO = TurnFacts.model_validate(
    {
        "steps": [
            {
                "stepId": "step_abeb2e8d",
                "displayName": "Predicted Signal Peptide",
                "count": 680,
                "parameters": [
                    _param(
                        "organism",
                        "Organism",
                        "Toxoplasma gondii GT1",
                        "Toxoplasma gondii GT1",
                        "stated",
                    ),
                    _param(
                        "signalp_version",
                        "Version",
                        "SignalP-6.0",
                        "SignalP-6.0",
                        "default",
                    ),
                ],
            },
            {
                "stepId": "step_1d7b3c03",
                "displayName": "Orthology Phylogenetic Profile",
                "count": 1240,
                "parameters": [
                    _param(
                        "profile_pattern",
                        "Profile Pattern",
                        "%ncan:N%",
                        "Neospora caninum Liverpool",
                        "stated",
                    ),
                    _param(
                        "included_species",
                        "Included Species",
                        "not set",
                        "site placeholder",
                        "default",
                    ),
                ],
            },
            {
                "stepId": "step_ecdce1b7",
                "displayName": "Intersect",
                "operator": "INTERSECT",
                "count": 53,
            },
        ],
        "rootCount": 53,
        "strategyUrl": _TOXO_STRATEGY,
    }
).model_copy(
    update={
        "sources": [
            SourceFact(
                url=f"{_TOXO_RECORD}TGGT1_235590",
                record_id="TGGT1_235590",
                product="hypothetical protein",
                step_id="step_ecdce1b7",
            )
        ],
        "listed": [
            ListedFact(
                step_id="step_ecdce1b7",
                records=[
                    ListedRecord(
                        record_id="TGGT1_230705", url=f"{_TOXO_RECORD}TGGT1_230705"
                    )
                ],
            )
        ],
    }
)

# The facts part a microsporidiadb turn wrote: E. intestinalis signal peptides
# 66, no ortholog in E. cuniculi GB-M1 129, both 9.
_MICRO = TurnFacts(
    steps=[
        StepFact(step_id="step_12d27eba", display_name="Signal Peptide", count=66),
        StepFact(step_id="step_fb8dd87e", display_name="Phyletic Profile", count=129),
        StepFact(
            step_id="step_353195e7",
            display_name="Intersect",
            operator="INTERSECT",
            count=9,
        ),
    ],
    root_count=9,
    strategy_url=_MICRO_STRATEGY,
)

# cryptodb, build 71: mucin* over C. parvum IOWA-ATCC, product field 2, every
# text field 84, both 2.
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
    ]
)


def test_every_reference_kind_renders_from_the_recorded_facts() -> None:
    prose = (
        "The signal peptide step returns [count:step_abeb2e8d], the ortholog "
        "step [count:step_1d7b3c03] and the result [root]; the organism is "
        "[value:step_abeb2e8d.organism], [source:step_abeb2e8d.organism], the "
        "version [source:step_abeb2e8d.signalp_version]. Read "
        "[record:TGGT1_235590] and [record:TGGT1_230705] at [url]."
    )

    assert render_reply(prose, _TOXO) == (
        "The signal peptide step returns 680 genes, the ortholog step 1,240 "
        "genes and the result 53 genes; the organism is Toxoplasma gondii GT1, "
        "you stated, the version the site's default. Read "
        f"[TGGT1_235590]({_TOXO_RECORD}TGGT1_235590) (hypothetical protein) and "
        f"[TGGT1_230705]({_TOXO_RECORD}TGGT1_230705) at {_TOXO_STRATEGY}."
    )


def test_a_value_whose_label_differs_renders_both() -> None:
    assert render_reply("[value:step_1d7b3c03.profile_pattern]", _TOXO) == (
        "%ncan:N% (Neospora caninum Liverpool)"
    )


@pytest.mark.parametrize("facts", [_TOXO, _MICRO], ids=["toxodb", "microsporidiadb"])
def test_a_difference_admits_exactly_the_differences_of_two_held_counts(
    facts: TurnFacts,
) -> None:
    held = {step.step_id: step.count for step in facts.steps} | {
        "root": facts.root_count
    }
    rendered = {
        (a, b): render_reply(f"[diff:{a},{b}]", facts) for a, b in permutations(held, 2)
    }

    assert rendered == {
        (a, b): f"{abs(n - m):,} gene{'' if abs(n - m) == 1 else 's'}"
        for (a, n), (b, m) in permutations(held.items(), 2)
        if n is not None and m is not None
    }


@pytest.mark.parametrize(
    "reference",
    [
        "[diff:step_353195e7,step_353195e7]",
        "[diff:step_353195e7]",
        "[diff:step_353195e7,step_12d27eba,root]",
        "[diff:root,root_before]",
        "[diff:root,before:step_353195e7]",
        "[diff:root,step_gone]",
    ],
)
def test_a_difference_of_anything_but_two_held_counts_is_refused(
    reference: str,
) -> None:
    assert prose_faults(f"It removes {reference}.", _MICRO) == [
        ProseFault(token=reference, kind="unheld_reference")
    ]


@pytest.mark.parametrize(
    ("facts", "reference"),
    [
        (_TOXO, "[count:step_gone]"),
        (_TOXO, "[before:step_abeb2e8d]"),
        (_TOXO, "[value:step_abeb2e8d.threshold]"),
        (_TOXO, "[source:step_gone.organism]"),
        (_TOXO, "[record:TGGT1_999999]"),
        (_MUCIN, "[compare:Name field]"),
        (_MUCIN, "[compare:Product field:result]"),
        (_MUCIN, "[compare:Product field,Name field:shared]"),
        (_MUCIN, "[root]"),
        (_MUCIN, "[url]"),
    ],
)
def test_a_reference_to_what_the_facts_do_not_hold_is_refused_by_name(
    facts: TurnFacts, reference: str
) -> None:
    assert prose_faults(f"It is {reference}.", facts) == [
        ProseFault(token=reference, kind="unheld_reference")
    ]
    with pytest.raises(UnheldReferenceError, match=reference.replace("[", r"\[")):
        render_reply(f"It is {reference}.", facts)


@pytest.mark.parametrize(
    ("prose", "token"),
    [
        ("It is [count:[count:step_353195e7]].", "[count:[count:step_353195e7]]"),
        ("It is [[root]].", "[[root]]"),
        ("It is [count:].", "[count:]"),
        ("It is [root ].", "[root ]"),
        ("Open [URL].", "[URL]"),
        ("It is [Count:step_353195e7].", "[Count:step_353195e7]"),
        ("It is [root and more.", "[root"),
        ("It is [root]] now.", "]"),
    ],
)
def test_a_nested_or_malformed_reference_is_refused_not_rendered(
    prose: str, token: str
) -> None:
    faults = prose_faults(prose, _MICRO)

    assert [f for f in faults if f.kind == "malformed_reference"] == [
        ProseFault(token=token, kind="malformed_reference")
    ]


def test_a_bracketed_word_that_names_no_reference_is_prose() -> None:
    prose = "[mock] The intersect keeps [count:step_353195e7] [in both]."

    assert (prose_faults(prose, _MICRO), render_reply(prose, _MICRO)) == (
        [],
        "[mock] The intersect keeps 9 genes [in both].",
    )


@pytest.mark.parametrize(
    ("prose", "fault"),
    [
        ("Grown at 37C.", ProseFault(token="37C", kind="number")),
        ("Kept at p < 1e-6.", ProseFault(token="1e-6", kind="number")),
        (
            "Annotated GO:0016298.",
            ProseFault(token="GO:0016298", kind="identifier"),
        ),
        ("Grown 5x longer.", ProseFault(token="5x", kind="number")),
        ("On the log2 scale.", ProseFault(token="log2", kind="number")),
        ("A 2-fold change.", ProseFault(token="2-fold", kind="number")),
        ("Kept 12.5% of them.", ProseFault(token="12.5%", kind="number")),
        ("The PF01395 domain.", ProseFault(token="PF01395", kind="identifier")),
        ("The IPR000719 family.", ProseFault(token="IPR000719", kind="identifier")),
        (
            "The gene PF3D7_0908300.",
            ProseFault(token="PF3D7_0908300", kind="identifier"),
        ),
        ("The gene PKNH_1234500.", ProseFault(token="PKNH_1234500", kind="identifier")),
        (
            "The gene TGME49_233460.",
            ProseFault(token="TGME49_233460", kind="identifier"),
        ),
        ("The gene LmjF.36.0010.", ProseFault(token="LmjF.36.0010", kind="identifier")),
        (
            "The gene ENSMUSG00000012345.",
            ProseFault(token="ENSMUSG00000012345", kind="identifier"),
        ),
        (
            "The step step_353195e7.",
            ProseFault(token="step_353195e7", kind="identifier"),
        ),
        (
            "See https://toxodb.org now.",
            ProseFault(token="https://toxodb.org", kind="link"),
        ),
    ],
)
def test_a_fact_written_outside_a_reference_is_refused(
    prose: str, fault: ProseFault
) -> None:
    assert [(f.token, f.kind) for f in prose_faults(prose, _MICRO)] == [
        (fault.token, fault.kind)
    ]


def test_prose_of_ordinary_words_holds_no_fault() -> None:
    prose = (
        "The intersect keeps the secreted genes with no ortholog in the "
        "excluded species, e.g. candidate effectors. Would a domain search, "
        "and/or a text search, find more?"
    )

    assert prose_faults(prose, _MICRO) == []


@pytest.mark.parametrize(
    "name", ["PfEMP1", "IL-6", "CD4+", "H3K27me3", "ME49", "3D7", "SignalP-6.0"]
)
def test_a_name_that_mixes_letters_and_digits_is_prose(name: str) -> None:
    assert prose_faults(f"The {name} genes are kept.", _MICRO) == []


def test_a_number_word_is_prose_the_validator_does_not_read() -> None:
    assert prose_faults("The strategy has three steps.", _MICRO) == []


def test_a_numbered_list_is_exempt_only_in_its_own_order() -> None:
    listed = "1. The signal peptide step.\n2. The ortholog step.\n3. The intersect."

    assert (
        prose_faults(listed, _MICRO),
        prose_faults("The intersect keeps\n9. That is the result.", _MICRO),
    ) == (
        [],
        [
            ProseFault(
                token="9", kind="number", references=("[count:step_353195e7]", "[root]")
            )
        ],
    )
