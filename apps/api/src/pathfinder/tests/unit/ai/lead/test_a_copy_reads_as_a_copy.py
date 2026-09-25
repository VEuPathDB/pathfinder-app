"""A structure that still holds a copy reads as a copy wherever it is shown, and
leaves with what it copies."""

from __future__ import annotations

from pathfinder.ai.lead.edit_messages import edit_work_order
from pathfinder.ai.lead.ledger_sections import render_structure
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.domain.strategy.spec_reconciliation import spec_without_steps
from pathfinder.tests.unit.domain.strategy._orthology import round_trip_spec


def test_the_ledger_writes_the_copy_over_what_it_copies() -> None:
    spec = round_trip_spec()
    assert spec.structure is not None

    rendered = render_structure(spec.structure.root, spec)

    assert rendered == (
        "((GenesWithSignalPeptide INTERSECT GenesByTransmembraneDomains) INTERSECT "
        "GenesByOrthologs(GenesByOrthologs(COPY (GenesWithSignalPeptide INTERSECT "
        "GenesByTransmembraneDomains))))"
    )


def test_the_edit_work_order_draws_the_copy_as_a_node() -> None:
    spec = round_trip_spec()

    order = edit_work_order(
        "keep the syntenic orthologs",
        "keep only those with syntenic orthologs in Plasmodium vivax P01",
        spec,
        pending=SpecDiff(),
        answered=spec,
        answer=None,
    )

    assert "        COPY\n" in order
    assert "[c_to] syntenic orthologs in Plasmodium vivax P01" in order


def test_a_copy_leaves_with_the_criteria_it_copies() -> None:
    left = spec_without_steps(round_trip_spec(), {"c_signal", "c_tm"})

    assert (left.structure, [c.id for c in left.criteria]) == (None, [])


def test_a_copy_keeps_what_is_left_of_what_it_copies() -> None:
    kept = spec_without_steps(round_trip_spec(), {"c_tm"})
    assert kept.structure is not None

    assert render_structure(kept.structure.root, kept) == (
        "(GenesWithSignalPeptide INTERSECT "
        "GenesByOrthologs(GenesByOrthologs(COPY GenesWithSignalPeptide)))"
    )
