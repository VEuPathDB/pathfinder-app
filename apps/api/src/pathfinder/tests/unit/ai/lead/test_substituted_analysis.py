"""The Lead refuses a reply that reports one gene set's analysis as another's."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest
from pydantic_ai.exceptions import ModelRetry
from pydantic_ai.messages import ToolCallPart

from pathfinder.ai.graph.state import EnrichmentRun
from pathfinder.ai.lead.lead_agent import (
    LeadResponse,
    build_lead_agent,
    refuse_a_substituted_analysis,
)
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.tests._support.run_context import run_context_for
from pathfinder.tests.unit.ai.lead.conftest import (
    RetryRecordingScript,
    lead_deps,
    pipeline_state,
)

_REQUESTED_SET = "gametocyte secreted candidates v3"
_SUBSTITUTED_REPLY = (
    f"Completed the GO enrichment for '{_REQUESTED_SET}' (155 genes "
    "analyzed). The top terms are protein export and host cell remodeling."
)
_NAMED_REPLY = (
    f"The enrichment on '{_REQUESTED_SET}' could not run. I ran it on 'WDK "
    "Strategy 214617320' instead, which holds the same 155 genes: the top "
    "terms are protein export and host cell remodeling."
)


_FAILED_RUN = EnrichmentRun(
    task_id=UUID("0c6100d2-0000-4000-8000-0000000000a1"),
    gene_set_id="gs-requested",
    succeeded=False,
)
_ANALYSED_RUN = EnrichmentRun(
    task_id=UUID("0c6100d2-0000-4000-8000-0000000000a2"),
    gene_set_id="gs-other",
    gene_set_name="WDK Strategy 214617320",
    succeeded=True,
)


def _deps_with_runs(*runs: EnrichmentRun) -> LeadDeps:
    deps = lead_deps(
        pipeline_state(
            user_prompt=f"Run GO enrichment on {_REQUESTED_SET}.",
            user_message_id=uuid4(),
        ),
    )
    deps.state.turn_markers.enrichment_runs = list(runs)
    return deps


def _substitution_deps() -> LeadDeps:
    return _deps_with_runs(_FAILED_RUN, _ANALYSED_RUN)


def test_a_reply_that_hides_the_gene_set_it_analysed_is_refused() -> None:
    deps = _substitution_deps()

    with pytest.raises(ModelRetry) as raised:
        refuse_a_substituted_analysis(
            run_context_for(deps),
            LeadResponse(prose=_SUBSTITUTED_REPLY, strategy_changed=False),
        )

    message = str(raised.value)
    assert "gs-other" in message
    assert "WDK Strategy 214617320" in message


def test_a_reply_that_names_the_gene_set_it_analysed_stands() -> None:
    output = LeadResponse(prose=_NAMED_REPLY, strategy_changed=False)

    assert (
        refuse_a_substituted_analysis(run_context_for(_substitution_deps()), output)
        is output
    )


def test_a_reply_whose_enrichment_ran_on_the_set_asked_for_stands() -> None:
    deps = _deps_with_runs(
        _FAILED_RUN.model_copy(
            update={"gene_set_id": "gs-requested", "succeeded": True}
        )
    )
    output = LeadResponse(prose=_SUBSTITUTED_REPLY, strategy_changed=False)

    assert refuse_a_substituted_analysis(run_context_for(deps), output) is output


def test_a_later_message_is_not_judged_by_an_earlier_messages_enrichments() -> None:
    """The record belongs to the message it was made under."""
    deps = _deps_with_runs(_FAILED_RUN, _ANALYSED_RUN)
    deps.state.user_message_id = uuid4()
    output = LeadResponse(
        prose="The strategy searched Plasmodium falciparum 3D7.", strategy_changed=False
    )

    assert refuse_a_substituted_analysis(run_context_for(deps), output) is output


def test_a_failure_after_a_success_is_not_a_substitution() -> None:
    """Nothing was routed around: the failed set was asked for second."""
    deps = _deps_with_runs(_ANALYSED_RUN, _FAILED_RUN)
    output = LeadResponse(
        prose="The enrichment on set A failed: it has no WDK step.",
        strategy_changed=False,
    )

    assert refuse_a_substituted_analysis(run_context_for(deps), output) is output


def test_the_substitution_refusal_is_asked_once_per_turn() -> None:
    deps = _substitution_deps()
    output = LeadResponse(prose=_SUBSTITUTED_REPLY, strategy_changed=False)

    with pytest.raises(ModelRetry):
        refuse_a_substituted_analysis(run_context_for(deps), output)

    assert refuse_a_substituted_analysis(run_context_for(deps), output) is output


def test_a_substituted_reply_is_re_asked_and_the_next_answer_goes_through() -> None:
    """The refusal reaches the model once, and the turn still answers."""
    deps = _substitution_deps()
    script = RetryRecordingScript(
        ToolCallPart(
            tool_name="final_result",
            args={
                "prose": _SUBSTITUTED_REPLY,
                "nextState": "await_user",
                "strategyChanged": False,
            },
            tool_call_id="call_final",
        ),
    )

    result = asyncio.run(
        build_lead_agent().run(
            "Run GO enrichment on my gametocyte set.",
            deps=deps,
            model=script.model(),
        ),
    )

    assert isinstance(result.output, LeadResponse)
    assert len(script.retries) == 1
    assert "gs-other" in script.retries[0]
