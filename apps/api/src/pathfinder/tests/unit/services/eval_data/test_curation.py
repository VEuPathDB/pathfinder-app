"""Turning one staged row into a case, without touching a database."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pathfinder.evals.case import ExpectedOutcome
from pathfinder.evals.extract import (
    EvalExtract,
    ExtractedStrategy,
    ExtractedTurn,
    ExtractedVerification,
)
from pathfinder.persistence.models import EvalStagedCase
from pathfinder.services.eval_data.curation import (
    PromotionEdits,
    build_case,
    default_expectation,
    staged_extract,
)

STAGING_ID = uuid4()


def _extract(*, built: bool = True) -> EvalExtract:
    return EvalExtract(
        site_id="plasmodb",
        assistant_id="pathfinder",
        turns=[
            ExtractedTurn(request="find kinases", reply="Built it."),
            ExtractedTurn(request="now swap the organism", reply="Swapped it."),
        ],
        strategy=(
            ExtractedStrategy(
                record_type="transcript",
                step_count=3,
                structure="(A INTERSECT B)",
                strategy_ast={"recordType": "transcript"},
            )
            if built
            else None
        ),
        verification=ExtractedVerification(success=True, reason="root size holds"),
    )


def _row(
    *, built: bool = True, promoted: bool = False, rated: bool = False
) -> EvalStagedCase:
    return EvalStagedCase(
        id=STAGING_ID,
        rated_message_id=uuid4() if rated else None,
        site_id="plasmodb",
        assistant_id="pathfinder",
        content_hash="a" * 64,
        extract=(
            None
            if promoted
            else _extract(built=built).model_dump(by_alias=True, mode="json")
        ),
        status="promoted" if promoted else "staged",
    )


def test_a_promoted_row_has_no_extract_to_read() -> None:
    with pytest.raises(ValueError, match="already promoted"):
        staged_extract(_row(promoted=True))


def test_the_default_expectation_repeats_what_the_run_did() -> None:
    expectation = default_expectation(_row())

    assert expectation.builds_strategy
    assert expectation.structure == "(A INTERSECT B)"
    assert expectation.step_count == 3
    assert expectation.verified is True


def test_a_run_with_a_pending_check_defaults_to_not_verified() -> None:
    """Nobody checked the pending step, so the case may not expect a pass."""
    extract = _extract().model_copy(
        update={
            "verification": ExtractedVerification(
                success=True, reason="root size holds", pending_checks=["step_de"]
            )
        }
    )
    row = _row()
    row.extract = extract.model_dump(by_alias=True, mode="json")

    assert default_expectation(row).verified is False


def test_a_run_that_built_nothing_defaults_to_forbidding_a_build() -> None:
    expectation = default_expectation(_row(built=False))

    assert not expectation.builds_strategy
    assert expectation.structure is None
    assert expectation.step_count is None


def test_the_case_takes_the_requests_of_the_staged_thread_in_order() -> None:
    case = build_case(
        _row(),
        PromotionEdits(name="a-case", rationale="pins the build"),
        today="2026-08-23",
    )

    assert case.turns == ["find kinases", "now swap the organism"]
    assert case.site_id == "plasmodb"
    assert case.provenance.origin == "promoted"
    assert case.provenance.staging_id == str(STAGING_ID)
    assert case.provenance.added_at == "2026-08-23"


def test_the_curator_can_replace_the_turns_and_the_expectation() -> None:
    case = build_case(
        _row(),
        PromotionEdits(
            name="a-case",
            rationale="the run built a decoy; the case forbids it",
            turns=["remember my preferred dataset"],
            expected=ExpectedOutcome(builds_strategy=False),
        ),
        today="2026-08-23",
    )

    assert case.turns == ["remember my preferred dataset"]
    assert not case.expected.builds_strategy


def test_a_case_built_from_a_staged_row_names_no_user() -> None:
    case = build_case(
        _row(),
        PromotionEdits(name="a-case", rationale="pins the build"),
        today="2026-08-23",
    )

    payload = case.model_dump_json(by_alias=True)

    assert "user" not in payload.casefold()
    assert case.assert_de_identified()


def test_a_disliked_row_s_default_expectation_compares_nothing() -> None:
    """The recorded run is the one the researcher said was wrong."""
    assert default_expectation(_row(rated=True)) == ExpectedOutcome(
        builds_strategy=None
    )


def test_a_disliked_row_is_not_promoted_without_an_expectation() -> None:
    with pytest.raises(ValueError, match="state what the case expects"):
        build_case(
            _row(rated=True),
            PromotionEdits(name="a-case", rationale="the reply was wrong"),
            today="2026-09-24",
        )


def test_a_disliked_row_promotes_with_the_curator_s_expectation() -> None:
    case = build_case(
        _row(rated=True),
        PromotionEdits(
            name="a-case",
            rationale="the build intersected where the request said OR",
            expected=ExpectedOutcome(builds_strategy=True, structure="(A UNION B)"),
        ),
        today="2026-09-24",
    )

    assert case.expected.structure == "(A UNION B)"
    assert case.turns == ["find kinases", "now swap the organism"]
