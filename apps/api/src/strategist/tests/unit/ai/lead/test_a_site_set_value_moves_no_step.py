from __future__ import annotations

from veupathdb.domain.parameters import StringValue

from strategist.ai.agents.state import AgentToolState
from strategist.ai.lead.derive import derive_ledger
from strategist.ai.lead.dispatch_context import the_edit_the_strategy_owes
from strategist.ai.lead.sub_agent_tools import apply_agent_state
from strategist.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    OperationalSpec,
)
from strategist.domain.strategy.site_set_reads import SiteSetReads
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state
from strategist.tests.unit.ai.tools.conftest import agent_run_context


def _text(*, with_document_type: bool) -> OperationalSpec:
    held = {
        "text_expression": BoundValue(
            value=StringValue(value="kinase"), source="stated"
        )
    }
    if with_document_type:
        held["document_type"] = BoundValue(
            value=StringValue(value="gene"), source="default"
        )
    return OperationalSpec(
        goal="kinases",
        criteria=[
            Criterion(
                id="c_text",
                text="kinases",
                search_name="GenesByText",
                resolved_params=held,
            )
        ],
    )


def test_a_pass_hands_its_site_set_names_to_the_turn() -> None:
    deps = lead_deps(pipeline_state())
    deps.state.domain.site_set = SiteSetReads(
        by_search={"GenesByLocation": frozenset({"chromosome"})}
    )
    state = AgentToolState()
    state.site_set_read_this_pass = {"GenesByText": frozenset({"document_type"})}

    apply_agent_state(deps, agent_run_context(agent_state=state).deps)

    assert deps.state.domain.site_set.by_search == {
        "GenesByLocation": frozenset({"chromosome"}),
        "GenesByText": frozenset({"document_type"}),
    }


def test_the_ledger_keeps_a_criterion_that_gained_a_site_set_value() -> None:
    state = pipeline_state()
    state.domain.spec_before_turn = _text(with_document_type=False)
    state.domain.operational_spec = _text(with_document_type=True)
    state.domain.site_set = SiteSetReads(
        by_search={"GenesByText": frozenset({"document_type"})}
    )

    diff = derive_ledger(state, None).frame.spec_diff()

    assert diff is not None
    assert [c.disposition for c in diff.changes] == ["kept"]


def test_the_ledger_names_a_value_the_researcher_sets_as_moved() -> None:
    state = pipeline_state()
    state.domain.spec_before_turn = _text(with_document_type=False)
    state.domain.operational_spec = _text(with_document_type=True)

    diff = derive_ledger(state, None).frame.spec_diff()

    assert diff is not None
    assert [c.changed_params for c in diff.changes] == [{"document_type": "gene"}]


def test_the_edit_owes_no_site_set_value() -> None:
    state = pipeline_state()
    state.domain.answered_spec = _text(with_document_type=False)
    state.domain.site_set = SiteSetReads(
        by_search={"GenesByText": frozenset({"document_type"})}
    )

    _, pending = the_edit_the_strategy_owes(state, _text(with_document_type=True))

    assert [c.disposition for c in pending.changes] == ["kept"]
