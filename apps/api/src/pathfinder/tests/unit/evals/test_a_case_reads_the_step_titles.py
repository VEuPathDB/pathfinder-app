"""A case holds the reply to the searches the strategy runs, by their titles."""

from __future__ import annotations

from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode

from pathfinder.evals.case import CaseProvenance, EvalCase, ExpectedOutcome
from pathfinder.evals.scoring import ObservedOutcome, score_case, step_titles
from pathfinder.evals.store import load_case

_GPI_CASE = "a-search-the-site-lacks-is-named-or-asked"
_WORDS = "genes with a predicted GPI anchor"


def _case(expected: ExpectedOutcome) -> EvalCase:
    return EvalCase(
        name="a-case",
        turns=["find genes with a predicted GPI anchor"],
        site_id="plasmodb",
        assistant_id="pathfinder",
        rationale="pins the named search",
        expected=expected,
        provenance=CaseProvenance(
            site="plasmodb",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="decisions/a-step-says-what-runs.md",
            added_at="2026-09-23",
        ),
    )


_EITHER = ExpectedOutcome(
    builds_strategy=None,
    reply_names_its_searches=True,
    step_titles_omit=["GPI"],
)


def _built(title: str, reply: str) -> ObservedOutcome:
    return ObservedOutcome(
        built_strategy=True,
        structure="GenesByExportPrediction",
        step_titles=[title],
        reply_text=reply,
    )


def _fields(observed: ObservedOutcome) -> list[str]:
    return [d.field for d in score_case(_case(_EITHER), observed).differences]


def test_a_build_whose_reply_names_its_search_passes() -> None:
    observed = _built(
        "Exported Protein",
        "No search here states a GPI anchor; I used Exported Protein (ExportPred).",
    )

    score = score_case(_case(_EITHER), observed)

    assert (score.passed, score.differences) == (True, [])


def test_a_build_whose_reply_skips_its_search_fails() -> None:
    observed = _built("Exported Protein", "I built a GPI anchor filter.")

    assert _fields(observed) == ["replyNamesItsSearches"]


def test_a_step_titled_with_the_researchers_words_fails() -> None:
    observed = _built(_WORDS, f"I built {_WORDS}.")

    assert _fields(observed) == ["stepTitlesOmit"]


def test_a_turn_that_asks_instead_of_building_passes() -> None:
    observed = ObservedOutcome(
        built_strategy=False,
        reply_text="PlasmoDB has no GPI anchor search. Use Exported Protein instead?",
    )

    score = score_case(_case(_EITHER), observed)

    assert (score.passed, score.differences) == (True, [])


def test_a_turn_that_neither_builds_nor_asks_fails() -> None:
    observed = ObservedOutcome(built_strategy=False, reply_text="Done.")

    assert _fields(observed) == ["replyNamesItsSearches"]


def test_the_titles_are_the_search_steps_only() -> None:
    root = StrategyStepNode(
        search_name="__combine__",
        operator=CombineOp.INTERSECT,
        display_name="Intersect",
        primary_input=StrategyStepNode(
            search_name="GenesByTaxon", display_name="Organism"
        ),
        secondary_input=StrategyStepNode(
            search_name="GenesByExportPrediction", display_name="Exported Protein"
        ),
    )

    titles = step_titles(StrategyAst(record_type="transcript", root=root))

    assert titles == ["Organism", "Exported Protein"]


def test_the_shipped_gpi_case_holds_the_reply_to_what_runs() -> None:
    case = load_case(_GPI_CASE)
    faithful = _built("Exported Protein", "I used Exported Protein: no GPI search.")
    worded = _built(_WORDS, "I built a GPI anchor filter.")

    assert (case.site_id, case.expected.builds_strategy) == ("plasmodb", None)
    assert score_case(case, faithful).passed
    assert not score_case(case, worded).passed
