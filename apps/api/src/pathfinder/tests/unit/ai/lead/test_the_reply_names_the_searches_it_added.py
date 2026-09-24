"""A reply names the search each step this turn added runs."""

from __future__ import annotations

from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import reconcile
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.strategy.step_words import AddedSearch
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import (
    building_deps,
    kinds,
    reply,
)

_EXPORTED = AddedSearch(
    step_id="step_1",
    search_display_name="Exported Protein",
    criterion_text="genes with a predicted GPI anchor",
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
