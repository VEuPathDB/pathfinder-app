"""A fact-guard hint names a value reference only when that reference renders
the one value it replaces. A token one value of a multi-pick holds has no such
reference, so the hint says to cite it another way or drop it."""

from __future__ import annotations

from pathfinder.ai.lead.contract_messages import unrendered_prose_message
from pathfinder.domain.reply_references import ProseFault, prose_faults
from pathfinder.domain.tally_facts import TallyFact, TallyRowFact
from pathfinder.domain.turn_facts import ParameterFact, StepFact, TurnFacts

_TAXA = ParameterFact(
    name="taxon_type_ahead",
    display_name="Taxon",
    value="pfac, pyxn, pyyx",
    label=(
        "pfac (Plasmodium falciparum CD01), pyxn (Plasmodium yoelii yoelii 17XNL), "
        "pyyx (Plasmodium yoelii yoelii 17XNL 2023)"
    ),
    source="chosen",
    picks=3,
)
_STRAIN = ParameterFact(
    name="strain", display_name="Strain", value="17XNL", source="stated"
)


def _facts(parameter: ParameterFact) -> TurnFacts:
    return TurnFacts(
        steps=[
            StepFact(
                step_id="step_5ebea5e6",
                display_name="Taxonomy",
                count=333932,
                parameters=[parameter],
                record_noun="protein",
            )
        ],
        record_noun="protein",
    )


_PROSE = "Plasmodium yoelii yoelii 17XNL has the most singleton proteins."


def test_a_token_of_a_multi_pick_names_no_reference_that_renders_it() -> None:
    faults = prose_faults(_PROSE, _facts(_TAXA))

    assert faults == [
        ProseFault(
            token="17XNL",
            kind="listed_value",
            references=("[value:step_5ebea5e6.taxon_type_ahead]",),
        )
    ]
    message = unrendered_prose_message(faults)
    assert "write ``[value:step_5ebea5e6.taxon_type_ahead]``" not in message
    assert (
        "- ``17XNL`` is one of the values ``[value:step_5ebea5e6.taxon_type_ahead]`` "
        "holds, and that reference renders every one of them, so no reference "
        "renders it alone: cite it through a fact that holds it alone, or take "
        "it out."
    ) in message


def test_a_token_of_a_single_value_names_its_value_reference() -> None:
    faults = prose_faults(_PROSE, _facts(_STRAIN))

    assert faults == [
        ProseFault(
            token="17XNL",
            kind="number",
            references=("[value:step_5ebea5e6.strain]",),
        )
    ]
    assert (
        "- ``17XNL``: write ``[value:step_5ebea5e6.strain]``, which renders it."
        in unrendered_prose_message(faults)
    )


_ROOT_TALLY = TallyFact(
    id="tally_root",
    title="Proteins by Taxon Code",
    record_noun="protein",
    total=2744,
    distinct=61,
    rows=[TallyRowFact(value="pyxn", count=90, label="Plasmodium yoelii yoelii 17XNL")],
    wdk_step_id=227288280,
)


def test_the_name_of_a_tally_row_the_reply_cites_is_held() -> None:
    facts = _facts(_TAXA).model_copy(
        update={"tallies": [_ROOT_TALLY], "result_step_id": 227288280}
    )

    assert (
        prose_faults(
            "Plasmodium yoelii yoelii 17XNL has the most singleton proteins: "
            "[tally:tally_root.pyxn].",
            facts,
        )
        == []
    )


_TWO_ROWS = TurnFacts(
    tallies=[
        _ROOT_TALLY.model_copy(
            update={
                "rows": [
                    TallyRowFact(
                        value="pyxn", count=90, label="Plasmodium yoelii yoelii 17XNL"
                    ),
                    TallyRowFact(
                        value="pyoe", count=80, label="Plasmodium yoelii yoelii 17X"
                    ),
                ]
            }
        )
    ],
    result_step_id=227288280,
    record_noun="protein",
)


def test_a_name_only_another_row_holds_is_not_held_by_the_cited_row() -> None:
    faults = prose_faults("Strain 17XNL leads: [tally:tally_root.pyoe].", _TWO_ROWS)

    assert [(f.token, f.kind) for f in faults] == [("17XNL", "number")]


def test_two_cited_rows_cannot_swap_their_names_across_clauses() -> None:
    swapped = prose_faults(
        "P. yoelii 17XNL has [tally:tally_root.pyoe] and P. yoelii 17X has "
        "[tally:tally_root.pyxn].",
        _TWO_ROWS,
    )
    paired = prose_faults(
        "P. yoelii 17XNL has [tally:tally_root.pyxn] and P. yoelii 17X has "
        "[tally:tally_root.pyoe].",
        _TWO_ROWS,
    )

    assert ([(f.token, f.kind) for f in swapped], paired) == (
        [("17XNL", "number"), ("17X", "number")],
        [],
    )
