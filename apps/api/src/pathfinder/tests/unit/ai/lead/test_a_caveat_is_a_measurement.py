"""A caveat is a typed measurement: one sentence carries its numbers, and a
reply states it only when it gives those numbers."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from pathfinder.ai.lead.verdict_claims import caveat_stated
from pathfinder.domain.caveats import (
    BuildCaveat,
    Caveat,
    ControlsCaveat,
    SampleCaveat,
    controls_caveat,
    sample_caveat,
)
from pathfinder.domain.evidence import (
    ControlSetEvidence,
    ControlTestEvidence,
    GeneFit,
    NamedControlSet,
    SampledGene,
)


def _ids(prefix: str, count: int) -> list[str]:
    return [f"{prefix}{index:04d}" for index in range(count)]


def _test(
    positives: tuple[int, int],
    negatives: tuple[int, int],
    control_set: NamedControlSet | None = None,
) -> ControlTestEvidence:
    """A control test that returned ``found`` of ``total`` of each kind."""
    pos_found, pos_total = positives
    neg_found, neg_total = negatives
    pos, neg = _ids("PF3D7_01", pos_total), _ids("PF3D7_14", neg_total)
    return ControlTestEvidence(
        tested_label="Predicted Signal Peptide",
        control_set=control_set,
        positive=ControlSetEvidence(
            returned=pos[:pos_found], not_returned=pos[pos_found:]
        ),
        negative=ControlSetEvidence(
            returned=neg[:neg_found], not_returned=neg[neg_found:]
        ),
    )


def _genes(*fits: GeneFit) -> list[SampledGene]:
    return [
        SampledGene(
            gene_id=f"PF3D7_02{index:05d}",
            fits=fit,
            why="the product names a secreted protein",
        )
        for index, fit in enumerate(fits)
    ]


V2_CONTROLS = ControlsCaveat(
    positives_returned=52,
    positives_total=80,
    negatives_returned=2,
    negatives_total=40,
)


def test_the_v2_control_test_is_a_caveat_with_both_counts() -> None:
    assert controls_caveat(_test((52, 80), (2, 40))) == V2_CONTROLS
    assert V2_CONTROLS.sentence == (
        "52 of 80 positive controls returned; 2 of 40 negative controls returned"
    )


def test_the_caveat_names_the_saved_set_and_keeps_its_sentence() -> None:
    kinases = NamedControlSet(id="0b6c1f4e-set", name="Kinases from Treeck")

    caveat = controls_caveat(_test((52, 80), (2, 40), kinases))

    assert caveat == V2_CONTROLS.model_copy(update={"control_set": kinases})
    assert caveat is not None
    assert caveat.sentence == V2_CONTROLS.sentence
    assert caveat.texts() == ["Kinases from Treeck"]


def test_every_positive_returned_and_no_negative_is_no_caveat() -> None:
    assert [controls_caveat(_test((80, 80), (0, 40)))] == [None]


def test_a_missed_positive_alone_names_only_the_positives() -> None:
    caveat = controls_caveat(_test((79, 80), (0, 40)))

    assert caveat is not None
    assert caveat.sentence == "79 of 80 positive controls returned"


def test_a_reply_states_the_control_caveat_only_with_both_counts() -> None:
    assert caveat_stated(
        "52 of the 80 positives were returned, and 2 of 40 negative controls "
        "came back too.",
        V2_CONTROLS,
    )
    assert not caveat_stated(
        "Most positive controls were returned, and 2 of 40 negative controls too.",
        V2_CONTROLS,
    )


def test_two_unclear_genes_of_eight_are_a_sample_caveat() -> None:
    caveat = SampleCaveat(unclear=2, misfit=0, total=8)

    assert (
        sample_caveat(
            _genes("yes", "yes", "unclear", "yes", "yes", "unclear", "yes", "yes")
        )
        == caveat
    )
    assert caveat.sentence == "2 of 8 sampled genes unclear"
    assert caveat_stated(
        "Of the genes I sampled, 2 of 8 sampled genes are unclear.", caveat
    )
    assert not caveat_stated("The sampled genes look right.", caveat)


def test_a_misfit_and_an_unclear_gene_are_both_counted() -> None:
    caveat = sample_caveat(_genes("yes", "no", "unclear", "yes"))

    assert caveat is not None
    assert caveat.sentence == (
        "1 of 4 sampled genes unclear; 1 of 4 sampled genes do not fit"
    )
    assert not caveat_stated("1 of 4 sampled genes do not fit.", caveat)


def test_a_sample_where_every_gene_fits_is_no_caveat() -> None:
    assert [sample_caveat(_genes("yes", "yes", "yes"))] == [None]


def test_a_caveat_is_never_a_text_the_checker_wrote() -> None:
    with pytest.raises(
        ValidationError, match="does not match any of the expected tags"
    ):
        TypeAdapter(Caveat).validate_python(
            {
                "kind": "threshold",
                "label": "Count type",
                "requested": "sense counts",
                "realized": "The step specification does not state a count type",
            }
        )


def test_a_build_that_failed_a_step_names_its_counts() -> None:
    caveat = BuildCaveat(pushed=3, failed=1, skipped=0, empty=1)

    assert caveat.sentence == (
        "The build pushed 3 steps, failed 1, skipped 0 and left 1 empty"
    )
    assert caveat_stated("1 step failed and 1 step returned no genes.", caveat)
    assert not caveat_stated("One step failed and another came back empty.", caveat)
