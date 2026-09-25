"""The offer's card question is written from the site's counts, and a reference
the turn did not read leaves the offer while its counts stay."""

from __future__ import annotations

import math

import pytest
from veupathdb.domain.parameters import StringValue
from veupathdb_mcp.separation import hypergeometric_log_sf

from pathfinder.domain.evidence import (
    ControlEnrichment,
    ControlSetEvidence,
    ControlTestEvidence,
)
from pathfinder.domain.separation import OfferedLeaf, SeparationOffer
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.step_rationale import ControlsRationale

_DOI = "https://doi.org/10.1016/j.cell.2008.01.001"
_CHOSEN = ControlsRationale(
    task_id="task-1",
    search_name="GenesByText",
    source="literature",
    basis="exported proteins",
    sources=[_DOI],
    informs="recovering",
    recovered=3,
    positives=3,
    admitted=0,
    negatives=2,
    result_size=5012,
)


def _sets(
    recovered: list[str], missed: list[str], admitted: list[str], excluded: list[str]
) -> ControlTestEvidence:
    return ControlTestEvidence(
        tested_label="the offered strategy",
        positive=ControlSetEvidence(returned=recovered, not_returned=missed),
        negative=ControlSetEvidence(returned=admitted, not_returned=excluded),
    )


def _enrichment(read: ControlTestEvidence) -> ControlEnrichment:
    positive, negative = read.positive, read.negative
    assert positive is not None
    assert negative is not None
    population = positive.controls_count + negative.controls_count
    returned = positive.returned_count + negative.returned_count
    log_sf = hypergeometric_log_sf(
        positive.returned_count, population, positive.controls_count, returned
    )
    return ControlEnrichment(
        population=population,
        positives=positive.controls_count,
        returned=returned,
        positives_returned=positive.returned_count,
        p_value=math.exp(log_sf),
    )


def _offer(
    read: ControlTestEvidence, *, separates: bool, result_size: int | None = 5012
) -> SeparationOffer:
    assert read.positive is not None
    assert read.negative is not None
    criterion = Criterion(
        id="c1",
        text="Text (product name, notes, etc.): exported proteins",
        search_name="GenesByText",
        search_display_name="Text (product name, notes, etc.)",
        role="seed",
        resolved_params={"text_expression": StringValue(value="exported")},
        rationale=_CHOSEN,
    )
    return SeparationOffer(
        task_id="task-1",
        site_id="plasmodb",
        mode="exact",
        spec=OperationalSpec(
            goal="Separate 3 positive genes from 2 negative genes",
            criteria=[criterion],
            structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c1")),
        ),
        positive=read.positive,
        negative=read.negative,
        enrichment=_enrichment(read),
        result_size=result_size,
        separates=separates,
        predicted_matches_read=True,
        leaves=[
            OfferedLeaf(
                criterion_id="c1",
                display_name="Text (product name, notes, etc.)",
                controls=_sets(["P1", "P2", "P3"], [], [], ["N1", "N2"]),
            )
        ],
    )


def test_a_separating_offer_asks_for_the_strategy_by_its_counts() -> None:
    offer = _offer(_sets(["P1", "P2", "P3"], [], [], ["N1", "N2"]), separates=True)

    assert offer.question == (
        "Build the separating strategy: 1 search returning 3 of 3 positives "
        "and 0 of 2 negatives in 5,012 genes?"
    )


def test_a_closest_offer_says_it_is_the_closest() -> None:
    offer = _offer(_sets(["P1", "P2"], ["P3"], ["N1"], ["N2"]), separates=False)

    assert offer.question == (
        "Build the closest strategy found: 1 search returning 2 of 3 positives "
        "and 1 of 2 negatives in 5,012 genes?"
    )


def test_a_result_the_site_did_not_count_is_said_so() -> None:
    offer = _offer(
        _sets(["P1", "P2", "P3"], [], [], ["N1", "N2"]),
        separates=True,
        result_size=None,
    )

    assert offer.question.endswith("in a result the site did not count?")


def test_an_enrichment_row_the_sets_do_not_back_is_refused() -> None:
    offer = _offer(_sets(["P1", "P2", "P3"], [], [], ["N1", "N2"]), separates=True)
    stated = offer.model_dump(by_alias=True, mode="json")
    stated["enrichment"]["returned"] = 4

    with pytest.raises(ValueError, match="are not the sets"):
        SeparationOffer.model_validate(stated)


def test_the_offer_backs_its_read_and_each_leaf() -> None:
    read = _sets(["P1", "P2", "P3"], [], [], ["N1", "N2"])
    offer = _offer(read, separates=True)

    assert offer.evidence() == [
        read.model_copy(update={"enrichment": _enrichment(read)}),
        offer.leaves[0].controls,
    ]


def test_a_reference_the_turn_read_stays_in_the_form_it_was_read() -> None:
    offer = _offer(_sets(["P1", "P2", "P3"], [], [], ["N1", "N2"]), separates=True)

    kept = offer.with_references_read(
        lambda ref: "doi:10.1016/j.cell.2008.01.001" if ref == _DOI else None
    )

    assert kept.spec.criteria[0].rationale == _CHOSEN.model_copy(
        update={"sources": ["doi:10.1016/j.cell.2008.01.001"]}
    )


def test_a_reference_the_turn_did_not_read_leaves_and_the_counts_stay() -> None:
    offer = _offer(_sets(["P1", "P2", "P3"], [], [], ["N1", "N2"]), separates=True)

    kept = offer.with_references_read(lambda _ref: None)

    assert kept.spec.criteria[0].rationale == _CHOSEN.model_copy(update={"sources": []})
