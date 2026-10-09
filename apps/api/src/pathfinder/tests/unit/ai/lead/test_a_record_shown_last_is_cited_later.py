"""A reply on a turn that reads nothing cites the records the conversation showed
last and the contract holds it; a record never shown is refused, and the grammar
says which records a reference cites."""

from __future__ import annotations

from uuid import uuid4

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.ai.lead._lead_instructions import LEAD_INSTRUCTIONS
from pathfinder.ai.lead.card_reply import CITABLE_RECORDS, REPLY_REFERENCES
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_contract import hold_the_turn_contract, to_correct
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.ai.lead.turn_record import turn_record
from pathfinder.domain.reply_references import render_reply
from pathfinder.domain.turn_facts import SourceFact
from pathfinder.services.gene_records.read import gene_record_url
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead._turn_contract_cases import reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

# hostdb, build 71: the sample of five a turn listed from the MHC class I
# intersect of chromosome 17 genes.
_SAMPLE = [
    "ENSMUSG00000035929",
    "ENSMUSG00000060550",
    "ENSMUSG00000061232",
    "ENSMUSG00000067212",
    "ENSMUSG00000067235",
]
_SHOWN = [SourceFact(url=gene_record_url("hostdb", g), record_id=g) for g in _SAMPLE]
_SAME_SAMPLE = (
    "Here is the same sample again: "
    + ", ".join(f"[record:{g}]" for g in _SAMPLE)
    + "."
)


def _deps() -> LeadDeps:
    state = pipeline_state(
        "hostdb", user_message_id=uuid4(), domain=StrategyDomainState()
    )
    state.turn_markers.intent_classified = True
    state.domain.record_shown(_SHOWN)
    return lead_deps(state)


def test_the_facts_of_a_later_turn_carry_the_records_shown_last() -> None:
    facts = turn_facts(_deps())

    assert (facts.shown_before, facts.record_ids(), facts.lines()) == (
        _SHOWN,
        [],
        [],
    )


def test_a_reply_citing_the_sample_shown_last_stands_and_renders_each_link() -> None:
    deps = _deps()
    answer = reply(_SAME_SAMPLE)

    assert hold_the_turn_contract(run_context_for(deps), answer) is answer
    assert render_reply(answer.prose, turn_facts(deps)) == (
        "Here is the same sample again: "
        + ", ".join(
            f"[{g}](https://qa.hostdb.org/hostdb.qa/app/record/gene/{g})"
            for g in _SAMPLE
        )
        + "."
    )


def test_a_record_the_conversation_never_showed_is_refused() -> None:
    deps = _deps()
    record = turn_record(run_context_for(deps))
    answer = reply("The sample now holds [record:ENSMUSG00000073409].")

    [mismatch] = to_correct(run_context_for(deps), answer, record, [answer.prose])

    assert (mismatch.kind, mismatch.sentence.splitlines()[1]) == (
        "unrendered_prose",
        "- ``[record:ENSMUSG00000073409]`` names nothing the facts hold.",
    )


def test_the_schema_and_the_instruction_say_which_records_a_reference_cites() -> None:
    assert (
        REPLY_REFERENCES.count(f"[record:<record_id>] {CITABLE_RECORDS}"),
        " ".join(LEAD_INSTRUCTIONS.split()).count(
            f"``[record:<record_id>]`` {CITABLE_RECORDS}"
        ),
        CITABLE_RECORDS.endswith("or one of the records the conversation showed last"),
    ) == (1, 1, True)
