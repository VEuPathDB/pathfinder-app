from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from assistant_core.graph.turn_state import UserQuestionAnswer
from veupathdb.domain.strategy import CombineOp
from veupathdb_mcp.catalog import (
    DecisionRequest,
    DecisionResponse,
    DecisionsTransport,
    use_decisions_transport,
)

from strategist.ai.graph.runtime import AgentDeps
from strategist.ai.graph.state import StrategyDomainState
from strategist.ai.lead import frame_dispatch
from strategist.ai.lead.deltas import FrameResult
from strategist.ai.lead.frame_dispatch import frame_work_order, run_frame
from strategist.ai.lead.frame_requirements import questions_for_the_card
from strategist.ai.lead.lead_consult import apply_option_bindings
from strategist.ai.lead.operator_reader import read_the_operators
from strategist.ai.lead.sub_agent_tools import LeadDeps
from strategist.domain.strategy.constraints import (
    Constraint,
    ConstraintKind,
    ConstraintSource,
)
from strategist.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    RequirementLink,
    SpecStructure,
    StructureNode,
)
from strategist.domain.strategy.operator_reading import operator_source, settled
from strategist.platform.config import get_settings
from strategist.tests.unit.ai.lead.conftest import lead_deps, pipeline_state

_FIXTURE = Path(__file__).parents[3] / "fixtures/decisions/operator_reading.json"
_RECORDED: dict[str, Any] = json.loads(_FIXTURE.read_text())
_MESSAGE = "Find kinases that are expressed in gametocytes in P. falciparum 3D7."
_BOTH = frozenset({"a", "b"})


@pytest.fixture(autouse=True)
def _a_deployment_that_asks_the_service(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "strategist_chat_provider", "default")


def _stated(rid: str, quote: str) -> Constraint:
    return Constraint(
        id=rid,
        kind=ConstraintKind.UNTYPED,
        requested_value=quote,
        label=quote,
        source=ConstraintSource.USER_EXPLICIT,
        quote=quote,
    )


_KINASES = _stated("r1", "kinases")
_GAMETOCYTES = _stated("r2", "expressed in gametocytes")
_ASSUMED = Constraint(
    id="r3", kind=ConstraintKind.UNTYPED, requested_value="drug target", label="x"
)


def _spec(second: Constraint = _GAMETOCYTES) -> OperationalSpec:
    return OperationalSpec(
        criteria=[
            Criterion(
                id=cid,
                text=cid,
                search_name="GenesByText",
                record_class="transcript",
                answers=[RequirementLink(requirement=linked.id)],
            )
            for cid, linked in (("a", _KINASES), ("b", second))
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.UNION,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="a"),
                    StructureNode(kind="leaf", criterion_id="b"),
                ],
            )
        ),
    )


def _deps(spec: OperationalSpec) -> LeadDeps:
    domain = StrategyDomainState(
        requirements=[_KINASES, _GAMETOCYTES, _ASSUMED], operational_spec=spec
    )
    return lead_deps(pipeline_state(user_prompt=_MESSAGE, domain=domain))


class _Service:
    def __init__(self, response: dict[str, Any] | None) -> None:
        self.response = response
        self.sent: list[dict[str, Any]] = []

    async def __call__(self, request: DecisionRequest) -> DecisionResponse | None:
        self.sent.append(request.model_dump(mode="json"))
        if self.response is None:
            return None
        return DecisionResponse.model_validate(self.response)


def _answering(choice: str, confidence: float) -> dict[str, Any]:
    response: dict[str, Any] = json.loads(json.dumps(_RECORDED["response"]))
    response["answers"][0].update({"choice": choice, "confidence": confidence})
    return response


async def _read(deps: LeadDeps, service: DecisionsTransport) -> OperationalSpec:
    use_decisions_transport(service)
    spec = deps.state.domain.operational_spec
    assert spec is not None
    read = await read_the_operators(spec, deps)
    deps.state.domain.operational_spec = read
    return read


async def test_the_reader_reads_the_researcher_s_words_and_the_branches() -> None:
    service = _Service(_RECORDED["response"])

    await _read(_deps(_spec()), service)

    assert service.sent == [_RECORDED["request"]]


async def test_a_confident_disagreement_asks_the_card_and_holds_the_build() -> None:
    deps = _deps(_spec())
    read = await _read(deps, _Service(_RECORDED["response"]))

    asked = questions_for_the_card(deps, FrameResult(), [])
    kept = settled(read, asked=asked)

    assert (
        [q.question for q in asked],
        [o.label for q in asked for o in q.options],
        kept.ready_to_build,
    ) == (
        [
            (
                'Your words read as genes in both "kinases" and "expressed in '
                'gametocytes", but the plan finds genes in "kinases" or "expressed '
                'in gametocytes". Which should it find?'
            )
        ],
        [
            'Keep genes in "kinases" or "expressed in gametocytes"',
            'Change to genes in both "kinases" and "expressed in gametocytes"',
        ],
        False,
    )


async def test_a_picked_operator_rewires_the_combine_as_the_researcher_s() -> None:
    deps = _deps(_spec())
    await _read(deps, _Service(_RECORDED["response"]))
    domain = deps.state.domain
    [question] = questions_for_the_card(deps, FrameResult(), [])
    domain.record_questions([question])

    apply_option_bindings(
        deps.state,
        [
            UserQuestionAnswer(
                question_id="q1",
                prompt=question.question,
                chosen_labels=[question.options[1].label],
            )
        ],
        sheets={},
    )

    spec = domain.operational_spec
    assert spec is not None
    assert spec.structure is not None
    assert (
        spec.structure.root.operator,
        spec.ready_to_build,
        operator_source(spec, _BOTH),
        domain.requirements,
    ) == (CombineOp.INTERSECT, True, "card", [_KINASES, _GAMETOCYTES, _ASSUMED])


async def test_an_agreement_is_the_researcher_s_and_asks_nothing() -> None:
    deps = _deps(_spec())
    read = await _read(deps, _Service(_answering("union", 0.88)))

    assert (
        questions_for_the_card(deps, FrameResult(), []),
        operator_source(read, _BOTH),
        read.ready_to_build,
    ) == ([], "stated", True)


async def test_an_unsure_or_unstated_read_is_the_assistant_s() -> None:
    sources = []
    for choice, confidence in (("intersect", 0.31), ("not_stated", 0.97)):
        deps = _deps(_spec())
        read = await _read(deps, _Service(_answering(choice, confidence)))
        sources.append(
            (
                operator_source(read, _BOTH),
                questions_for_the_card(deps, FrameResult(), []),
            )
        )

    assert sources == [("chosen", []), ("chosen", [])]


async def test_no_answer_records_no_read_and_asks_nothing() -> None:
    deps = _deps(_spec())
    read = await _read(deps, _Service(None))

    assert (read.operator_reads, read.ready_to_build) == ([], True)


async def test_a_branch_that_answers_no_stated_words_costs_no_call() -> None:
    service = _Service(_RECORDED["response"])

    read = await _read(_deps(_spec(_ASSUMED)), service)

    assert (service.sent, operator_source(read, _BOTH)) == ([], "chosen")


async def test_a_frame_pass_that_disagrees_ends_on_the_operator_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _frame(**kwargs: Any) -> FrameResult:
        agent_deps: AgentDeps = kwargs["agent_deps"]
        agent_deps.agent_state.operational_spec_draft = _spec()
        return FrameResult(disposition="spec_ready", summary="two searches")

    monkeypatch.setattr(frame_dispatch, "stream_sub_agent", _frame)
    use_decisions_transport(_Service(_RECORDED["response"]))
    deps = _deps(OperationalSpec())

    result = await run_frame(
        deps=deps,
        parent_tool_call_id="t1",
        work_order=frame_work_order("frame it", deps),
    )

    assert isinstance(result, FrameResult)
    spec = deps.state.domain.operational_spec
    assert spec is not None
    assert (
        result.disposition,
        [o.label for q in result.card_questions for o in q.options],
        [q.question for q in deps.state.domain.open_questions],
        spec.ready_to_build,
    ) == (
        "needs_user",
        [
            'Keep genes in "kinases" or "expressed in gametocytes"',
            'Change to genes in both "kinases" and "expressed in gametocytes"',
        ],
        [q.prompt for q in result.card_questions],
        False,
    )


_LATER = "Make that a union: kinases or gametocyte expression, either one."


class _ByMessages:
    def __init__(self, newest: str, history: str) -> None:
        self.answers = {True: newest, False: history}
        self.sent: list[str] = []

    async def __call__(self, request: DecisionRequest) -> DecisionResponse | None:
        self.sent.append(request.input)
        newest_alone = _MESSAGE not in request.input
        return DecisionResponse.model_validate(
            _answering(self.answers[newest_alone], 0.9)
        )


def _edited() -> LeadDeps:
    domain = StrategyDomainState(
        requirements=[_KINASES, _GAMETOCYTES, _ASSUMED],
        operational_spec=_spec(),
        original_request=_MESSAGE,
    )
    return lead_deps(pipeline_state(user_prompt=_LATER, domain=domain))


async def test_the_newest_message_that_states_an_operator_wins() -> None:
    deps = _edited()
    service = _ByMessages(newest="union", history="intersect")

    read = await _read(deps, service)

    assert (
        len(service.sent),
        _MESSAGE in service.sent[0],
        questions_for_the_card(deps, FrameResult(), []),
        operator_source(read, _BOTH),
        read.ready_to_build,
    ) == (1, False, [], "stated", True)


async def test_a_newest_message_that_states_no_operator_reads_the_history() -> None:
    deps = _edited()
    service = _ByMessages(newest="not_stated", history="intersect")

    read = await _read(deps, service)

    assert (
        len(service.sent),
        _MESSAGE in service.sent[1],
        len(questions_for_the_card(deps, FrameResult(), [])),
        read.ready_to_build,
    ) == (2, True, 1, False)
