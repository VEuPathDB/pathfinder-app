"""A criterion the controls chose states the counts its own step returned."""

from __future__ import annotations

import pytest
from pydantic import TypeAdapter, ValidationError

from pathfinder.domain.strategy.step_rationale import (
    ChosenRationale,
    ControlsInforms,
    ControlsRationale,
    SearchRationale,
    StepRationale,
)
from pathfinder.domain.strategy.step_words import StepWords


def _chosen(informs: ControlsInforms = "recovering") -> ControlsRationale:
    return ControlsRationale(
        task_id="0c6100d2-0000-4000-8000-000000000001",
        search_name="GenesByGoTerm",
        source="enrichment",
        basis="GO:0044217 other organism part",
        informs=informs,
        recovered=42,
        positives=80,
        admitted=0,
        negatives=40,
        result_size=637,
    )


def test_a_recovering_criterion_is_decided_by_its_positives() -> None:
    chosen = _chosen()

    assert (chosen.term, chosen.short) == (
        "42 of 80 positives",
        "recovers 42 of 80 positives, admits 0 of 40 negatives",
    )


def test_an_excluding_criterion_is_decided_by_its_negatives() -> None:
    assert _chosen("excluding").term == "0 of 40 negatives"


def test_the_line_names_the_counts_the_size_and_the_basis() -> None:
    assert _chosen().line() == (
        "chosen by the controls: recovers 42 of 80 positives, admits 0 of 40 "
        "negatives, 637 genes (GO:0044217 other organism part)"
    )


def test_both_unions_read_the_controls_kind_back() -> None:
    dumped = _chosen().model_dump(by_alias=True, mode="json")

    assert TypeAdapter(ChosenRationale).validate_python(dumped) == _chosen()
    assert TypeAdapter(StepRationale).validate_python(dumped) == _chosen()


def test_a_stored_strategy_keeps_the_controls_reason_of_its_step() -> None:
    words = StepWords(rationales={"step_a": _chosen()})

    stored = StepWords.model_validate(words.model_dump(by_alias=True, mode="json"))

    assert stored.rationale_of("step_a", "GenesByGoTerm") == _chosen()
    assert stored.rationale_of("step_a", "GenesByText") is None


def test_a_search_reason_still_reads_as_a_search_reason() -> None:
    searched = SearchRationale(
        search_name="GenesByText",
        basis="parameter",
        term="Text fields",
        reason="its Text fields parameter reads the product",
        tool_call_id="call_1",
    )

    stored: ChosenRationale = TypeAdapter(ChosenRationale).validate_python(
        searched.model_dump(by_alias=True, mode="json")
    )

    assert stored == searched


def test_a_redacted_reason_keeps_its_counts_and_hides_its_words() -> None:
    cited = _chosen().model_copy(update={"sources": ["https://doi.org/10.1/x"]})

    redacted = cited.redacted(lambda text: f"<{len(text)}>")

    assert (redacted.basis, redacted.sources, redacted.short, redacted.texts()) == (
        "<30>",
        ["<22>"],
        "recovers 42 of 80 positives, admits 0 of 40 negatives",
        ["<30>", "<22>"],
    )


def test_a_negative_count_is_a_validation_error_naming_the_field() -> None:
    dumped = _chosen().model_dump(by_alias=True, mode="json") | {"recovered": -1}

    with pytest.raises(ValidationError) as refused:
        TypeAdapter(StepRationale).validate_python(dumped)

    assert [e["loc"] for e in refused.value.errors()] == [("controls", "recovered")]
