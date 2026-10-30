"""A statistic the EDA service computed belongs to the thread: a later turn's
facts hold it, and the Lead's instructions list its values."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead.lead_pins import pinned_statistics
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.statistic_facts import StatisticFact, StatisticRowFact
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_PCA = StatisticFact(
    id="stat_1c2d3e4f",
    kind="pca",
    title="PCA of 12 samples",
    rows=[
        StatisticRowFact(name="PC1", value="54.35%"),
        StatisticRowFact(name="PC2", value="12.79%"),
        StatisticRowFact(name="samples", value="12 samples"),
        StatisticRowFact(name="groups", value="3 groups"),
    ],
    statements=[
        "PC1 separates no pair of groups; every pair's ranges on PC1 overlap.",
    ],
)


def _a_later_turn() -> LeadDeps:
    """A thread whose earlier message computed the PCA, answering a new message."""
    state = pipeline_state(user_prompt="Run a PCA colored by sex.")
    state.user_message_id = uuid4()
    state.domain.record_statistics([_PCA])
    state.user_message_id = uuid4()
    state.user_prompt = "Which component separates the sexes?"
    assert state.turn_markers.edited is False
    return lead_deps(state)


def test_a_later_turn_holds_a_statistic_an_earlier_turn_computed() -> None:
    assert turn_facts(_a_later_turn()).statistics == [_PCA]


def test_the_lead_reads_each_statistic_by_its_row() -> None:
    assert pinned_statistics(run_context_for(_a_later_turn())) == (
        "## Statistics this conversation computed\n"
        "Their cards show every value; say what they mean, with no number.\n"
        "- PCA of 12 samples\n"
        "  - PC1 = 54.35%\n"
        "  - PC2 = 12.79%\n"
        "  - samples = 12 samples\n"
        "  - groups = 3 groups\n"
        "  - PC1 separates no pair of groups; every pair's ranges on PC1 overlap."
    )


def test_a_conversation_with_no_statistic_pins_nothing() -> None:
    state = pipeline_state(user_prompt="Find kinases.")
    assert [pinned_statistics(run_context_for(lead_deps(state)))] == [None]


def test_a_later_read_of_one_statistic_replaces_the_earlier() -> None:
    state = pipeline_state(user_prompt="Run it again.")
    rerun = _PCA.model_copy(
        update={"rows": [StatisticRowFact(name="PC1", value="60%")]}
    )

    state.domain.record_statistics([_PCA])
    state.domain.record_statistics([rerun])

    assert state.domain.statistics == [rerun]


def test_an_audit_findings_fact_is_not_pinned_into_the_next_turn() -> None:
    listed = StatisticFact(
        id="stat_5a6b7c8d",
        kind="audit_findings",
        title="Findings of an audit run",
        rows=[StatisticRowFact(name="findings.0.genome", value="Examplea alpha A")],
    )
    state = pipeline_state(user_prompt="List the findings.")
    state.user_message_id = uuid4()
    state.domain.record_statistics([_PCA, listed])
    state.user_message_id = uuid4()

    pinned = pinned_statistics(run_context_for(lead_deps(state)))

    assert pinned is not None
    assert ("PCA of 12 samples" in pinned, "Examplea alpha A" in pinned) == (
        True,
        False,
    )
