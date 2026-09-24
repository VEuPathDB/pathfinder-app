"""A reply names the search each step this turn added runs, and gives the
reason it was chosen beside the name."""

from __future__ import annotations

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.step_rationale import (
    AnalysisRationale,
    ComparedSearch,
    SearchRationale,
)
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    kinds,
    reply,
)
from pathfinder.tests.unit.domain.strategy._analysis import binding

_EXPORTED = AddedSearch(
    step_id="step_1",
    search_display_name="Exported Protein",
    criterion_text="genes with a predicted GPI anchor",
    rationale=SearchRationale(
        search_name="GenesByExportPrediction",
        basis="nearest",
        term="GPI anchor",
        reason="no search states a GPI anchor; Exported Protein scored nearest",
        similarity=0.44,
        compared=[
            ComparedSearch(
                name="GenesByText", display_name="Gene Text Search", similarity=0.41
            )
        ],
        tool_call_id="call_gpi",
    ),
)
_ANALYSIS = AddedSearch(
    step_id="step_3",
    search_display_name="Genes higher in 24h than in 18h",
    criterion_text="genes up at 24 h",
    rationale=AnalysisRationale.of(binding()),
)
_ORTHOLOGS = AddedSearch(
    step_id="step_2",
    search_display_name="Orthologs",
    criterion_text="their P. vivax orthologs",
)


def _added(*searches: AddedSearch) -> LeadDeps:
    deps = building_deps()
    deps.state.turn_markers.added_searches = list(searches)
    return deps


def test_a_reply_that_names_every_added_search_passes() -> None:
    deps = _added(_EXPORTED, _ORTHOLOGS)
    report = reply(
        "No search on PlasmoDB states a GPI anchor, so I used exported protein "
        "(ExportPred) and mapped the result with Orthologs.",
        changed=True,
    )

    assert "unnamed_search" not in kinds(deps, report)


def test_a_reply_in_the_researchers_words_only_is_refused_with_the_list() -> None:
    deps = _added(_EXPORTED, _ORTHOLOGS)
    report = reply(
        "I built a filter for genes with a predicted GPI anchor and mapped them "
        "to Orthologs.",
        changed=True,
    )

    mismatches = reconcile(report, turn_record(run_context_for(deps)))

    unnamed = [m.sentence for m in mismatches if m.kind == "unnamed_search"]
    assert len(unnamed) == 1
    assert "Exported Protein (for: genes with a predicted GPI anchor)" in unnamed[0]
    assert "their P. vivax orthologs" not in unnamed[0]


def test_a_name_inside_a_longer_word_is_not_a_name() -> None:
    deps = _added(_ORTHOLOGS)
    report = reply("I added OrthologsPlus over your genes.", changed=True)

    assert "unnamed_search" in kinds(deps, report)


def test_a_turn_that_added_nothing_is_not_asked_to_name_a_search() -> None:
    report = reply("I built a filter for a predicted GPI anchor.", changed=True)

    assert "unnamed_search" not in kinds(_added(), report)


def _unnamed(deps: LeadDeps, prose: str) -> list[str]:
    mismatches = reconcile(
        reply(prose, changed=True), turn_record(run_context_for(deps))
    )
    return [m.sentence for m in mismatches if m.kind == "unnamed_search"]


def test_a_reply_that_names_the_search_without_its_reason_is_refused() -> None:
    unnamed = _unnamed(
        _added(_EXPORTED, _ORTHOLOGS),
        "I used Exported Protein and mapped the result with Orthologs.",
    )

    assert len(unnamed) == 1
    assert (
        "Exported Protein (for: genes with a predicted GPI anchor) - no search "
        "states a GPI anchor; Exported Protein scored nearest "
        "(over Gene Text Search 0.41)"
    ) in unnamed[0]


def test_a_reason_in_another_paragraph_is_not_beside_the_name() -> None:
    unnamed = _unnamed(
        _added(_EXPORTED),
        "I used Exported Protein.\n\nNo search on PlasmoDB states a GPI anchor.",
    )

    assert len(unnamed) == 1


def test_a_list_item_with_the_name_and_the_term_passes() -> None:
    unnamed = _unnamed(
        _added(_EXPORTED, _ORTHOLOGS),
        "The strategy runs:\n"
        "- Exported Protein, the nearest search to a GPI anchor on PlasmoDB\n"
        "- Orthologs, mapping those genes to P. vivax",
    )

    assert unnamed == []


def test_a_search_with_no_rationale_is_held_to_its_name_only() -> None:
    assert _unnamed(_added(_ORTHOLOGS), "I mapped the genes with Orthologs.") == []


def test_an_analysis_step_is_held_to_its_method() -> None:
    deps = _added(_ANALYSIS)
    named = "I added Genes higher in 24h than in 18h."

    assert (
        len(_unnamed(deps, named)),
        _unnamed(deps, f"{named[:-1]}, computed by DESeq."),
    ) == (1, [])


def test_a_reason_in_a_sub_bullet_of_the_named_item_passes() -> None:
    assert (
        _unnamed(_added(_EXPORTED), "- Exported Protein\n  - nearest to a GPI anchor")
        == []
    )
