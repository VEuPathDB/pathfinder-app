from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import RunContext
from veupathdb_mcp.catalog import ParameterInfo

from pathfinder.ai.agents.frame_pick_checks import hold_an_unsettled_pick_to_a_question
from pathfinder.ai.graph.runtime import AgentDeps
from pathfinder.ai.lead.card_question import CardQuestion
from pathfinder.ai.lead.deltas import FrameResult
from pathfinder.ai.lead.recorded_cards import the_card_asked
from pathfinder.ai.tools.standalone import catalog_discovery
from pathfinder.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.tests.unit.ai.tools.conftest import agent_run_context

_FIXTURES = Path(__file__).parents[3] / "fixtures/decisions"
_V7 = _FIXTURES / "v7_plasmodb_interpro_kinase_card.json"
_V6 = _FIXTURES / "v6_tritrypdb_rna_binding_pass.json"
_PARAM = "domain_typeahead"


def _stated(kind: ConstraintKind, value: str) -> Constraint:
    return Constraint(
        kind=kind,
        requested_value=value,
        label=value,
        source=ConstraintSource.USER_EXPLICIT,
    )


_V7_REQUIREMENTS = [
    _stated(ConstraintKind.ORGANISM, "Plasmodium falciparum 3D7"),
    _stated(ConstraintKind.OTHER, "InterPro protein kinase domain"),
]


def _recorded(path: Path) -> dict[str, Any]:
    body: dict[str, Any] = json.loads(path.read_text())
    return body


async def _replayed(
    monkeypatch: pytest.MonkeyPatch,
    recorded: dict[str, Any],
    *,
    site_id: str,
    requirements: list[Constraint],
    criterion: Criterion,
) -> RunContext[AgentDeps]:
    info = ParameterInfo.model_validate(recorded["read"])

    async def _site_read(*_args: object, **_kwargs: object) -> ParameterInfo:
        return info

    monkeypatch.setattr(catalog_discovery, "read_parameter_options", _site_read)
    ctx = agent_run_context(site_id=site_id)
    ctx.deps.agent_state.stated_requirements = requirements
    await catalog_discovery.get_parameter_options(ctx, **recorded["readArgs"])
    ctx.deps.agent_state.operational_spec_draft = OperationalSpec(
        criteria=[criterion],
        structure=SpecStructure(
            root=StructureNode(kind="leaf", criterion_id=criterion.id)
        ),
    )
    return ctx


def _held(ctx: RunContext[AgentDeps], recorded: dict[str, Any]) -> FrameResult:
    held = hold_an_unsettled_pick_to_a_question(
        ctx, FrameResult.model_validate(recorded["frameOutput"])
    )
    assert isinstance(held, FrameResult)
    return held


def _v6_criterion(recorded: dict[str, Any], source: str = "chosen") -> Criterion:
    criterion = Criterion.model_validate(recorded["criterion"])
    bound = criterion.resolved_params[_PARAM]
    return criterion.model_copy(
        update={
            "resolved_params": {
                **criterion.resolved_params,
                _PARAM: bound.model_copy(update={"source": source}),
            }
        }
    )


async def test_the_recorded_v7_card_asks_the_unsettled_pick_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _recorded(_V7)
    ctx = await _replayed(
        monkeypatch,
        recorded,
        site_id="plasmodb",
        requirements=_V7_REQUIREMENTS,
        criterion=Criterion.model_validate(recorded["criterion"]),
    )

    held = _held(ctx, recorded)
    written = [CardQuestion.model_validate(q) for q in recorded["consultQuestions"]]
    shown = the_card_asked(
        written, held.questions(ctx.deps.agent_state.operational_spec_draft)
    )

    assert [(q.criterion_id, q.param_name) for q in held.open_questions] == [
        ("c_interpro_protein_kinase_domain", _PARAM)
    ]
    assert [q.id for q in shown] == ["q1"]
    assert shown[0].options[0].label == "Specific Domain(s) IPR011009"


async def test_the_recorded_v6_pass_asks_the_pick_and_binds_no_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _recorded(_V6)
    criterion = _v6_criterion(recorded)
    ctx = await _replayed(
        monkeypatch, recorded, site_id="tritrypdb", requirements=[], criterion=criterion
    )
    assert ctx.deps.agent_state.operational_spec_draft.ready_to_build

    held = _held(ctx, recorded)
    draft = ctx.deps.agent_state.operational_spec_draft
    (asked,) = held.open_questions
    (open_criterion,) = draft.criteria

    assert (held.disposition, asked.criterion_id, asked.param_name) == (
        "needs_user",
        "c_rna_binding_domain",
        _PARAM,
    )
    assert asked.recommended_value == "PF00575"
    assert asked.options[:3] == ["PF00575", "PF00298", "PF01798"]
    assert (draft.ready_to_build, _PARAM in open_criterion.resolved_params) == (
        False,
        False,
    )
    assert [s.param_name for s in open_criterion.open_params] == [_PARAM]
    (typed,) = held.questions(draft)
    assert typed.options[0].label == "Specific Domain(s) S1 RNA binding domain"


async def test_a_settled_pick_over_the_recorded_v6_entries_is_not_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _recorded(_V6)
    settled = recorded["read"]["vocabPick"] | {
        "choiceConfidence": 0.91,
        "confidence": 0.78,
        "settled": True,
    }
    recorded["read"] = recorded["read"] | {"vocabPick": settled}
    criterion = _v6_criterion(recorded)
    ctx = await _replayed(
        monkeypatch, recorded, site_id="tritrypdb", requirements=[], criterion=criterion
    )

    held = _held(ctx, recorded)

    assert held == FrameResult.model_validate(recorded["frameOutput"])
    assert ctx.deps.agent_state.operational_spec_draft.criteria == [criterion]


@pytest.mark.parametrize("source", ["stated", "card"])
async def test_a_value_the_researcher_gave_over_the_recorded_v6_pick_is_not_asked(
    monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    recorded = _recorded(_V6)
    criterion = _v6_criterion(recorded, source)
    ctx = await _replayed(
        monkeypatch, recorded, site_id="tritrypdb", requirements=[], criterion=criterion
    )

    held = _held(ctx, recorded)

    assert held == FrameResult.model_validate(recorded["frameOutput"])
    assert ctx.deps.agent_state.operational_spec_draft.ready_to_build


async def test_a_question_of_the_leads_own_on_another_criterion_stays_on_the_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded = _recorded(_V7)
    ctx = await _replayed(
        monkeypatch,
        recorded,
        site_id="plasmodb",
        requirements=_V7_REQUIREMENTS,
        criterion=Criterion.model_validate(recorded["criterion"]),
    )
    held = _held(ctx, recorded)
    q1, own = (CardQuestion.model_validate(q) for q in recorded["consultQuestions"])
    elsewhere = own.model_copy(update={"requirement": "c_signal_peptide"})

    shown = the_card_asked(
        [q1, elsewhere], held.questions(ctx.deps.agent_state.operational_spec_draft)
    )

    assert [(q.id, q.requirement) for q in shown] == [
        ("q1", ""),
        ("own-1", "c_signal_peptide"),
    ]
