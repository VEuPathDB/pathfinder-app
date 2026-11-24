from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from strategist.ai.graph.state import PipelineState, StrategyDomainState
from strategist.domain.strategy.operational_spec import SpecStructure
from strategist.domain.strategy.question_options import PickTail
from strategist.domain.strategy.questions import OpenQuestion
from strategist.platform.errors import ConversationFromEarlierBuildError


def _tail_question() -> dict[str, object]:
    return {
        "question": "Which cut of Mean Phenotype Score selects the genes you mean?",
        "options": [
            {
                "id": "low",
                "label": "Lowest 5%",
                "binding": {"kind": "pick_tail", "rule": {"end": "low", "percent": 5}},
            },
            {
                "id": "high",
                "label": "Highest 5%",
                "binding": {"kind": "pick_tail", "rule": {"end": "high", "percent": 5}},
            },
        ],
    }


def _loaded(domain: StrategyDomainState) -> PipelineState:
    return PipelineState(
        conversation_id=uuid4(),
        user_id=uuid4(),
        site_id="veupathdb",
        mode="build",
        domain=domain,
    )


def test_a_tail_pick_saved_without_a_variable_binds_no_variable() -> None:
    domain = StrategyDomainState.model_validate(
        {
            "answered_questions": [_tail_question()],
            "tail_picks": {"Lowest 5%": {"rule": {"end": "low", "percent": 5}}},
        }
    )
    binding = domain.answered_questions[0].options[0].binding
    assert binding == PickTail.model_validate({"rule": {"end": "low", "percent": 5}})
    assert domain.tail_rules_on("Mean Phenotype Score") == {}


def test_a_domain_left_as_mappings_is_rebuilt_on_load() -> None:
    stored: dict[str, Any] = {"answered_questions": [_tail_question()]}
    state = _loaded(StrategyDomainState.model_construct(**stored))
    question = state.domain.answered_questions[0]
    assert isinstance(question, OpenQuestion)
    assert [o.label for o in question.options] == ["Lowest 5%", "Highest 5%"]


def test_a_domain_this_build_cannot_read_is_refused_on_load() -> None:
    stored: dict[str, Any] = {"answered_questions": [{"question": "q", "options": 5}]}
    with pytest.raises(ConversationFromEarlierBuildError) as caught:
        _loaded(StrategyDomainState.model_construct(**stored))
    assert "saved by an earlier version of Strategist" in str(caught.value.detail)
    assert "answered_questions" in str(caught.value.detail)


def test_a_saved_colocation_without_parameters_loads_unstated() -> None:
    colocated = {
        "kind": "combine",
        "operator": "COLOCATE",
        "inputs": [
            {"kind": "leaf", "criterionId": "c_kin"},
            {"kind": "leaf", "criterionId": "c_snp"},
        ],
    }
    stored: dict[str, Any] = {
        "operational_spec": {
            "goal": "kinases near snps",
            "criteria": [
                {"id": "c_kin", "text": "kinases", "searchName": "GenesByText"},
                {"id": "c_snp", "text": "snps", "searchName": "GenesByGoTerm"},
            ],
            "structure": {"root": colocated},
        }
    }

    state = _loaded(StrategyDomainState.model_construct(**stored))

    spec = state.domain.operational_spec
    assert spec is not None
    assert spec.structure == SpecStructure.model_validate({"root": colocated})
