"""A statistic the EDA service computed belongs to the thread: a later turn's
facts render it, and the Lead's instructions list it by its reference."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.lead.lead_pins import pinned_statistics
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.reply_references import render_reply
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


def test_a_later_turn_renders_a_statistic_an_earlier_turn_computed() -> None:
    facts = turn_facts(_a_later_turn())

    assert (
        render_reply(
            "PC1 explains [stat:stat_1c2d3e4f.PC1] of the variance across "
            "[stat:stat_1c2d3e4f.samples].",
            facts,
        )
        == "PC1 explains 54.35% of the variance across 12 samples."
    )


def test_the_lead_reads_each_statistic_by_its_reference() -> None:
    assert pinned_statistics(run_context_for(_a_later_turn())) == (
        "## Statistics this conversation computed\n"
        "Write each number below as its reference, never as the bare number.\n"
        "- PCA of 12 samples\n"
        "  - [stat:stat_1c2d3e4f.PC1] = 54.35%\n"
        "  - [stat:stat_1c2d3e4f.PC2] = 12.79%\n"
        "  - [stat:stat_1c2d3e4f.samples] = 12 samples\n"
        "  - [stat:stat_1c2d3e4f.groups] = 3 groups\n"
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
