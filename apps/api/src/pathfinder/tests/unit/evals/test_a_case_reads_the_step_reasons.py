"""A case can hold the reply to the reason each step runs its search: the
recorded term beside the search's name."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyAst, StrategyStepNode

from pathfinder.domain.strategy.step_rationale import SearchRationale
from pathfinder.domain.strategy.step_words import StepWords
from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome
from pathfinder.evals.scoring import ObservedOutcome, score_case, step_reasons
from pathfinder.evals.store import load_case

_EXPORTED = "GenesByExportPrediction"
_CHOSEN = SearchRationale(
    search_name=_EXPORTED,
    basis="nearest",
    term="GPI anchor",
    reason="no search states a GPI anchor; Exported Protein scored nearest",
    tool_call_id="call_gpi",
)
_REASONS = ExpectedOutcome(builds_strategy=None, reply_gives_its_reasons=True)


def _case(expected: ExpectedOutcome) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["find genes with a predicted GPI anchor"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the reason beside the search",
        expected=expected,
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="decisions/a-criterion-says-why-its-search-was-chosen.md",
            added_at="2026-09-24",
        ),
    )


def _stored(search_name: str) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_1", search_name=search_name, display_name="Exported Protein"
        ),
        metadata=StepWords(rationales={"step_1": _CHOSEN}).model_dump(
            by_alias=True, mode="json"
        ),
    )


def _built(reply: str) -> ObservedOutcome:
    return ObservedOutcome(
        built_strategy=True,
        step_reasons=[("Exported Protein", "GPI anchor")],
        reply_text=reply,
    )


def test_a_step_with_a_recorded_reason_is_read_by_its_title_and_term() -> None:
    assert step_reasons(_stored(_EXPORTED)) == [("Exported Protein", "GPI anchor")]


def test_a_step_that_runs_another_search_now_gives_no_reason() -> None:
    assert step_reasons(_stored("GenesByTaxon")) == []


def test_a_reply_with_the_term_beside_the_name_passes() -> None:
    observed = _built("Exported Protein is the nearest search to a GPI anchor.")

    assert score_case(_case(_REASONS), observed).differences == []


def test_a_reply_that_names_the_search_without_its_reason_fails() -> None:
    observed = _built("I used Exported Protein.\n\nNothing states a GPI anchor.")

    fields = [d.field for d in score_case(_case(_REASONS), observed).differences]

    assert fields == ["replyGivesItsReasons"]


def test_the_shipped_gpi_case_holds_the_reply_to_its_reasons() -> None:
    case = load_case("a-search-the-site-lacks-is-named-or-asked")
    worded = _built("I used Exported Protein, the closest search.")

    assert (case.expected.reply_gives_its_reasons, score_case(case, worded).passed) == (
        True,
        False,
    )
