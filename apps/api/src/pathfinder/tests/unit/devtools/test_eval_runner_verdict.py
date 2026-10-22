"""The verdict an eval reads is the one on the strategy the checkpoint holds, and an
expression is judged against the taxonomy of the case's site."""

from __future__ import annotations

import datetime
from uuid import uuid4

import pytest
from pydantic import JsonValue
from pydantic_evals.evaluators import EvaluatorContext
from pydantic_evals.otel import SpanTree
from veupathdb.domain.parameters import PhyleticTree
from veupathdb.domain.strategy import StrategyAst, StrategyStepNode
from veupathdb.wdk import WDKAnswer, ortho_taxonomy_of

from pathfinder.ai.graph.state import VerificationDigest
from pathfinder.devtools import eval_runner
from pathfinder.devtools.eval_runner import (
    CaseVerdict,
    checkpointed_requirements,
    checkpointed_verdict,
)
from pathfinder.domain.evidence import RequirementCheck, VerificationReview
from pathfinder.domain.strategy.revision import strategy_revision
from pathfinder.evals.case import (
    CaseProvenance,
    EvalCase,
    ExpectedOutcome,
    GatePlan,
    RecordedCount,
)
from pathfinder.evals.distance import ComparisonNode
from pathfinder.evals.requirements import RequirementCounts
from pathfinder.evals.scoring import ObservedOutcome
from pathfinder.tests.unit.ai.lead._budget_stop_turn import objection
from pathfinder.tests.unit.ai.lead.conftest import pipeline_state
from pathfinder.tests.unit.evals._phyletic import clade_tree


def _tree(search_name: str) -> StrategyAst:
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(id="step_a", search_name=search_name),
    )


def _checked(
    *, then_edited: bool, digest: VerificationDigest | None = None
) -> dict[str, JsonValue]:
    """A checkpoint whose strategy a check judged, then a later message."""
    state = pipeline_state(user_prompt="find the 24 h responders")
    state.user_message_id = uuid4()
    judged = _tree("GenesByText")
    state.domain.answered_graph = judged
    state.domain.record_verdict(
        objection() if digest is None else digest,
        revision=strategy_revision(judged),
    )
    state.user_message_id = uuid4()
    if then_edited:
        state.domain.answered_graph = _tree("GenesByGoTerm")
    return state.model_dump(mode="json")


def test_the_verdict_read_is_the_one_on_the_strategy_as_it_stands() -> None:
    verdicts = {
        "a later message": checkpointed_verdict(_checked(then_edited=False)),
        "a later edit": checkpointed_verdict(_checked(then_edited=True)),
    }

    assert verdicts == {"a later message": False, "a later edit": None}


def test_a_pass_with_a_pending_check_is_not_verified() -> None:
    pending = objection().model_copy(
        update={"success": True, "pending_checks": ["step_de"]}
    )

    assert checkpointed_verdict(_checked(then_edited=False, digest=pending)) is False


def test_the_rows_an_eval_counts_are_the_verdicts_on_the_strategy() -> None:
    reviewed = objection().model_copy(
        update={
            "review": VerificationReview(
                requirements=[
                    RequirementCheck(
                        text="with a signal peptide",
                        turn=1,
                        answered_by=["s1"],
                        how="search",
                        status="met",
                    ),
                    RequirementCheck(
                        text="at least 2 transmembrane domains",
                        turn=1,
                        how="search",
                        status="unmet",
                    ),
                ]
            )
        }
    )

    counted = {
        "a later message": checkpointed_requirements(
            _checked(then_edited=False, digest=reviewed)
        ),
        "a later edit": checkpointed_requirements(
            _checked(then_edited=True, digest=reviewed)
        ),
    }

    assert counted == {
        "a later message": RequirementCounts(met=1, unmet=1, unexpressed=0),
        "a later edit": None,
    }


def _phyletic_case() -> EvalCase:
    return EvalCase(
        name="orthomcl-single-copy",
        turns=["List the groups with one protein in every apicomplexan genome."],
        site_id="orthomcl",
        assistant_id="pathfinder",
        rationale="pins single copy over a clade",
        expected=ExpectedOutcome(
            builds_strategy=True,
            expressions={"GroupsByPhyleticPattern": ["APIC=139T AND APIC=139"]},
            root_count=RecordedCount(
                count=2, build="8.2", measured_on=datetime.date(2026, 10, 21)
            ),
        ),
        gates=GatePlan(policy="auto"),
        provenance=CaseProvenance(
            site="orthomcl",
            assistant="pathfinder",
            origin="cataloged-failure",
            reference="an-item.md",
            added_at="2026-10-21",
        ),
    )


def _context(case: EvalCase) -> EvaluatorContext[EvalCase, ObservedOutcome, None]:
    return EvaluatorContext[EvalCase, ObservedOutcome, None](
        name=case.name,
        inputs=case,
        metadata=None,
        expected_output=None,
        output=ObservedOutcome(
            built_strategy=True,
            root_count=2,
            tree=ComparisonNode(
                search_name="GroupsByPhyleticPattern",
                parameters={"phyletic_expression": "APIC=139 AND APIC=139T"},
            ),
        ),
        duration=0.0,
        _span_tree=SpanTree(),
        attributes={},
        metrics={},
    )


def test_the_verdict_reads_the_taxonomy_of_the_case_site() -> None:
    context = _context(_phyletic_case())
    taxonomy = clade_tree({"APIC": 139})

    verdicts = [
        CaseVerdict(builds={"orthomcl": "8.2"}, taxonomies=held).evaluate(context)
        for held in ({"orthomcl": taxonomy}, {})
    ]

    assert verdicts == ["pass", "fail"]


def _answer(*, tables: bool) -> WDKAnswer:
    rows = {
        "RootTaxons": [
            {"orthomcl_clade_id": "1", "taxon_abbrev": "APIC", "name": "Apicomplexa"}
        ],
        "Taxons": [
            {
                "orthomcl_clade_id": "2",
                "parent_id": "1",
                "three_letter_abbrev": "pfal",
                "name": "Plasmodium falciparum 3D7",
            }
        ],
    }
    return WDKAnswer.model_validate(
        {
            "meta": {
                "totalCount": 1,
                "responseCount": 1,
                "displayTotalCount": 1,
                "viewTotalCount": 1,
                "displayViewTotalCount": 1,
                "recordClassName": "helper",
            },
            "records": [{"id": [], "tables": rows if tables else {}}],
        }
    )


async def test_the_taxonomy_is_read_only_for_a_site_whose_cases_state_expressions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read: list[str] = []

    async def taxonomy(site_id: str) -> PhyleticTree | None:
        read.append(site_id)
        return ortho_taxonomy_of(_answer(tables=site_id == "orthomcl"))

    monkeypatch.setattr(eval_runner, "ortho_taxonomy", taxonomy)
    phyletic = _phyletic_case()
    cases = [
        phyletic,
        phyletic.model_copy(update={"site_id": "toxodb"}),
        phyletic.model_copy(update={"site_id": "plasmodb", "expected": _plain()}),
    ]

    taxonomies = await eval_runner.read_taxonomies(cases)

    assert read == ["orthomcl", "toxodb"]
    assert {
        site: tree.genomes_under(["APIC"]) for site, tree in taxonomies.items()
    } == {"orthomcl": {"pfal"}}


def _plain() -> ExpectedOutcome:
    return ExpectedOutcome(builds_strategy=True)
