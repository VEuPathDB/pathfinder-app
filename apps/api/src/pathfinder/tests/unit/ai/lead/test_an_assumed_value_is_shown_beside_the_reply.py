"""A default or chosen value that narrows its step is a caveat: the ledger lists
it, and the facts part shows its two counts once, on the step's row."""

from __future__ import annotations

from uuid import uuid4

from veupathdb.domain.parameters import NumberValue

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.derive import derive_ledger
from pathfinder.ai.lead.ledger_render import render_verification_full
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.lead.turn_facts import turn_facts
from pathfinder.domain.strategy.operational_spec import (
    BoundValue,
    Criterion,
    Measurement,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.domain.turn_facts import uncarried_assumptions
from pathfinder.domain.value_caveats import assumed_value_caveats
from pathfinder.tests.unit.ai.lead._turn_contract_cases import kinds, reply
from pathfinder.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_PERCENTILE = "min_expression_percentile"
_SENTENCE = (
    "Minimum expression percentile is 80, the site's default: 1,024 genes at "
    "that value, 5,120 at 0"
)
_CLAUSE = "Minimum expression percentile at the site's default of 80: 1,024 genes; at 0: 5,120"


def _spec() -> OperationalSpec:
    return OperationalSpec(
        goal="genes expressed in blood stages",
        criteria=[
            Criterion(
                id="c_expr",
                text="expressed in blood stages",
                search_name="GenesByRNASeqPercentile",
                role="seed",
                resolved_params={
                    _PERCENTILE: BoundValue(
                        value=NumberValue(value=80), source="default"
                    )
                },
                param_display_names={_PERCENTILE: "Minimum expression percentile"},
                measurements=[
                    Measurement(
                        kind="loosest_bound", param=_PERCENTILE, count=5120, reading="0"
                    )
                ],
                result_count=1024,
            )
        ],
        structure=SpecStructure(root=StructureNode(kind="leaf", criterion_id="c_expr")),
    )


def _checked() -> LeadDeps:
    state = pipeline_state(
        user_prompt="Genes expressed in blood stages.",
        user_message_id=uuid4(),
        domain=StrategyDomainState(operational_spec=_spec()),
    )
    state.domain.record_verdict(
        VerificationDigest(
            disposition=PhaseDisposition.DONE,
            prose="Checked.",
            reason="read the records",
            success=True,
        ),
        revision=strategy_revision(None),
    )
    state.turn_markers.verification_dispatched = True
    return lead_deps(state)


def test_the_ledger_lists_the_assumed_value_after_the_measured_caveats() -> None:
    section = derive_ledger(_checked().state, None).verification

    assert [caveat.sentence for caveat in section.caveats] == [_SENTENCE]
    assert f"- {_SENTENCE}" in render_verification_full(section).splitlines()


def test_the_facts_part_shows_the_assumed_value_once_and_carries_it() -> None:
    deps = _checked()
    facts = turn_facts(deps)

    assert (facts.caveats, facts.lines().count(_CLAUSE)) == ([], 1)
    assert (
        uncarried_assumptions(
            assumed_value_caveats(deps.state.domain.operational_spec), facts
        )
        == 0
    )


def test_a_turn_that_did_not_check_still_shows_the_assumed_value() -> None:
    deps = _checked()
    deps.state.turn_markers.verification_dispatched = False

    facts = turn_facts(deps)
    assert (facts.caveats, facts.lines().count(_CLAUSE)) == ([], 1)


def _trophozoite_checked() -> LeadDeps:
    """The amoebadb trophozoite step as the dry run bound it: the site's 80th
    percentile left in place, 1,665 genes there and 8,201 at a floor of 0."""
    deps = _checked()
    spec = deps.state.domain.operational_spec
    assert spec is not None
    spec.criteria[0] = spec.criteria[0].model_copy(
        update={
            "search_name": (
                "GenesByRNASeqehisHM1IMSS_Trophozoite_transcriptome_ebi_rnaSeq_"
                "RSRCPercentile"
            ),
            "measurements": [
                Measurement(
                    kind="loosest_bound", param=_PERCENTILE, count=8201, reading="0"
                )
            ],
            "result_count": 1665,
        }
    )
    return deps


def test_the_trophozoite_default_is_shown_with_both_counts() -> None:
    assert (
        "Minimum expression percentile at the site's default of 80: 1,665 genes; "
        "at 0: 8,201"
    ) in turn_facts(_trophozoite_checked()).lines()


def test_a_reply_that_names_the_shown_trophozoite_counts_stands() -> None:
    report = reply(
        "The trophozoite step returns 1,665 genes at the site's default; at a "
        "floor of 0 it returns 8,201."
    )

    assert kinds(_trophozoite_checked(), report) == []


def test_a_reply_with_a_trophozoite_count_the_facts_lack_is_refused() -> None:
    report = reply("At a floor of 50 the trophozoite step returns 4,000 genes.")

    assert kinds(_trophozoite_checked(), report) == ["fact_outside_the_block"]
