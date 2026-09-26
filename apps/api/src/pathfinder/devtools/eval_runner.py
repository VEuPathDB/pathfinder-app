"""Running the corpus against the pipeline, and writing the run summary.

Each case is one fresh thread, driven turn by turn end to end, exactly as a
chat turn runs. What the run produced is read back from the two durable
records: the strategy projection, and the checkpoint the turn left.

The harness is ``pydantic-evals``: it owns the dataset, the case loop and the
evaluator protocol. The summary shape is ours, so a change of harness does not
change the feed.

A run always uses the configured provider and needs a VEuPathDB login exactly
as the chat debugger does. A case that records a root count is judged against
the build each site reports at the start of the run.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import ReasoningEffort
from langchain_core.runnables import RunnableConfig
from pydantic import TypeAdapter
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.proposal import OFFER_TOOLS
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.devtools.capture import RunCapture
from pathfinder.devtools.chat import (
    RespondArgs,
    RunArgs,
    drive_respond,
    drive_run,
    resolve_run_assistant,
)
from pathfinder.devtools.gates import Gate
from pathfinder.evals.case import EvalCase, GateAnswer, GateEnd
from pathfinder.evals.distance import tree_from_ast
from pathfinder.evals.drift import DriftVerdict, classify, count_difference
from pathfinder.evals.scoring import (
    ObservedOutcome,
    RequirementCounts,
    final_count_below_every_input,
    requirement_counts,
    root_count,
    root_operator,
    score_case,
    step_reasons,
    step_titles,
    structure_signature,
)
from pathfinder.evals.store import attachment_paths, load_corpus
from pathfinder.evals.summary import CaseResult, EvalRunSummary
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.config import get_settings
from pathfinder.services.wdk_build import site_build

HARNESS = "pydantic-evals"
_VERDICT: TypeAdapter[DriftVerdict] = TypeAdapter(DriftVerdict)


def checkpointed_verdict(values: Mapping[str, object]) -> bool | None:
    """The verdict on the checkpointed strategy, or None when no check judged it."""
    verdict = PipelineState.model_validate(values).turn_verdict
    return None if verdict is None else verdict.passed


def checkpointed_requirements(
    values: Mapping[str, object],
) -> RequirementCounts | None:
    """The requirement rows of the verdict on the checkpointed strategy, counted."""
    verdict = PipelineState.model_validate(values).turn_verdict
    return None if verdict is None else requirement_counts(verdict.review.requirements)


async def _checkpoint_values(conversation_id: UUID) -> Mapping[str, object]:
    """The state the thread's last turn left in the checkpoint."""
    registry = get_assistant_registry()
    spec = await resolve_run_assistant(conversation_id)
    async with lifespan_checkpointer(
        get_settings().database_url,
        checkpoint_types=registry.checkpoint_types(),
    ) as saver:
        graph = spec.build_graph(saver)
        config: RunnableConfig = {"configurable": {"thread_id": str(conversation_id)}}
        snapshot = await graph.aget_state(config)
    return snapshot.values


async def persisted_wdk_step_ids(conversation_id: UUID) -> set[int]:
    """The WDK step ids the thread's persisted strategy carries right now."""
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    if not strategy.strategy_ast:
        return set()
    ast = StrategyAst.model_validate(strategy.strategy_ast)
    return set((ast.wdk_step_ids or {}).values())


def gate_end(gate: Gate) -> GateEnd | None:
    """The card the gate shows the researcher, or None for a task still running."""
    match gate.kind:
        case "none":
            return "none"
        case "consult":
            return "consult"
        case "approval":
            return "proposal" if gate.tool in OFFER_TOOLS else "approval"
        case _:
            return None


async def observe(
    conversation_id: UUID,
    reply_text: str,
    *,
    step_ids_unchanged: bool | None = None,
    ends_on: GateEnd | None = None,
) -> ObservedOutcome:
    """What the finished turn left behind, as the scorer reads it."""
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    built = bool(strategy.strategy_ast)
    ast = StrategyAst.model_validate(strategy.strategy_ast) if built else None
    checkpointed = await _checkpoint_values(conversation_id)
    return ObservedOutcome(
        built_strategy=built,
        structure=structure_signature(ast) if ast is not None else None,
        record_type=strategy.record_type or None,
        step_count=strategy.step_count if built else None,
        verified=checkpointed_verdict(checkpointed),
        requirements=checkpointed_requirements(checkpointed),
        step_ids_unchanged=step_ids_unchanged,
        tree=tree_from_ast(ast) if ast is not None else None,
        step_titles=step_titles(ast) if ast is not None else [],
        step_reasons=step_reasons(ast) if ast is not None else [],
        reply_text=reply_text,
        root_operator=root_operator(ast) if ast is not None else None,
        final_count_below_every_input=(
            final_count_below_every_input(ast) if ast is not None else None
        ),
        root_count=root_count(ast) if ast is not None else None,
        ends_on=ends_on,
    )


def _approve(case: EvalCase, index: int) -> Literal["auto", "prompt"]:
    """How a turn meets its gates: answered by the policy, or left for the case."""
    match case.gates:
        case "auto":
            return "auto"
        case "stop":
            return "prompt" if index == len(case.turns) - 1 else "auto"
        case _:
            return "prompt"


def _question_answers(gate: Gate, picks: list[str]) -> list[str]:
    """Each question's answer as ``respond --answer`` takes it: ``QID=VALUE``."""
    wanted = [pick.casefold() for pick in picks]
    answers: list[str] = []
    for question in gate.consult_questions:
        if question.kind == "free_text":
            answers.append(f"{question.id}={'; '.join(picks)}")
            continue
        labels = [o.label for o in question.options]
        picked = [
            label for label in labels if any(w in label.casefold() for w in wanted)
        ]
        recommended = [o.label for o in question.options if o.recommended]
        chosen = picked or recommended or labels[:1]
        answers.append(f"{question.id}={','.join(chosen)}")
    return answers


def _answers_the_gate(answer: GateAnswer, gate: Gate) -> bool:
    """A yes or a no answers an approval or offer card; picks answer questions."""
    match gate.kind:
        case "approval":
            return answer.picks is None
        case "consult":
            return answer.picks is not None
        case _:
            return False


async def _answer(
    args: RunArgs,
    answer: GateAnswer,
    gate: Gate,
) -> tuple[RunCapture, Gate] | None:
    """Answer the turn's pending card as ``respond`` does, from the case's answer."""
    picks = answer.picks
    return await drive_respond(
        RespondArgs(
            site=args.site,
            conversation_id=args.conversation_id,
            run_dir=args.run_dir,
            approve="prompt",
            via_worker=args.via_worker,
            quiet=True,
            assistant=args.assistant,
            effort=args.effort,
            accept=picks is None and answer.accept,
            deny=picks is None and not answer.accept,
            reason=answer.comment,
            answers=[] if picks is None else _question_answers(gate, picks),
        ),
    )


async def run_one_case(
    case: EvalCase,
    *,
    run_root: Path,
    effort: ReasoningEffort | None = None,
    via_worker: bool = False,
) -> ObservedOutcome:
    """Drive every turn of one case on a fresh thread, in order.

    The step ids are read on both sides of the last turn. A thread that held
    none before it observes nothing, because there was nothing to keep. The
    effort the run names wins over the case's. The case's own answers go to
    its cards in order.
    """
    conversation_id = uuid4()
    last = len(case.turns) - 1
    before: set[int] = set()
    reply = ""
    ended = Gate(kind="none")
    answers = case.gate_answers()
    for index, prompt in enumerate(case.turns):
        if index in case.new_conversation_before:
            conversation_id = uuid4()
        if index == last and last > 0:
            before = await persisted_wdk_step_ids(conversation_id)
        args = RunArgs(
            prompt=prompt,
            site=case.site_id,
            conversation_id=conversation_id,
            run_dir=run_root / case.name / f"turn-{index + 1}",
            approve=_approve(case, index),
            via_worker=via_worker,
            quiet=True,
            assistant=case.assistant_id,
            effort=case.effort if effort is None else effort,
            attachments=attachment_paths(case, index),
        )
        capture, ended = await drive_run(args)
        while answers and _answers_the_gate(answers[0], ended):
            answered = await _answer(args, answers.pop(0), ended)
            if answered is None:
                ended = Gate(kind="none")
                break
            capture, ended = answered
        reply = capture.assistant_text()
    after = await persisted_wdk_step_ids(conversation_id)
    return await observe(
        conversation_id,
        reply,
        step_ids_unchanged=(before == after) if before else None,
        ends_on=gate_end(ended),
    )


@dataclass
class CaseVerdict(Evaluator[EvalCase, ObservedOutcome, None]):
    """The corpus expectation, as the label the harness records: a drift verdict.

    ``builds`` holds the build each site reported at the start of the run.
    """

    builds: dict[str, str]

    def evaluate(
        self,
        ctx: EvaluatorContext[EvalCase, ObservedOutcome, None],
    ) -> DriftVerdict:
        return classify(ctx.inputs, ctx.output, self.builds[ctx.inputs.site_id])


def build_dataset(
    cases: list[EvalCase],
    builds: dict[str, str],
) -> Dataset[EvalCase, ObservedOutcome, None]:
    """The corpus as a harness dataset, one row per case."""
    return Dataset[EvalCase, ObservedOutcome, None](
        name="pathfinder-logic",
        cases=[Case(name=case.name, inputs=case) for case in cases],
        evaluators=[CaseVerdict(builds=builds)],
    )


async def run_corpus(
    *,
    run_root: Path,
    only: list[str] | None = None,
    effort: ReasoningEffort | None = None,
    via_worker: bool = False,
) -> EvalRunSummary:
    """Run the corpus and return the summary. Cases run one at a time.

    Every case writes the same checkpoint store, so concurrency is one. Each
    site's build is read once, before the first case.
    """
    cases = [case for case in load_corpus() if not only or case.name in only]
    builds = {site: await site_build(site) for site in {c.site_id for c in cases}}
    dataset = build_dataset(cases, builds)

    async def task(case: EvalCase) -> ObservedOutcome:
        return await run_one_case(
            case, run_root=run_root, effort=effort, via_worker=via_worker
        )

    report = await dataset.evaluate(task, max_concurrency=1, progress=False)

    by_name = {case.name: case for case in cases}
    results: list[CaseResult] = []
    for reported in report.cases:
        # The harness's own label decides the verdict; the score gives the
        # distance and the differences, and a moved count is carried apart.
        verdict = _VERDICT.validate_python(reported.labels[CaseVerdict.__name__].value)
        case = by_name[reported.name]
        score = score_case(case, reported.output)
        results.append(
            CaseResult(
                name=reported.name,
                verdict=verdict,
                differences=score.differences,
                distance=score.distance,
                observed_count=reported.output.root_count,
                count_drift=count_difference(
                    case, reported.output, builds[case.site_id]
                ),
                duration_seconds=round(reported.task_duration, 3),
            ),
        )
    results.extend(
        CaseResult(name=failure.name, verdict="fail", error=failure.error_message)
        for failure in report.failures
    )
    return EvalRunSummary(
        harness=HARNESS,
        provider=get_settings().pathfinder_chat_provider,
        assistant_id=cases[0].assistant_id if cases else "",
        ran_at=datetime.datetime.now(tz=datetime.UTC).isoformat(timespec="seconds"),
        cases=sorted(results, key=lambda result: result.name),
    )


__all__ = [
    "HARNESS",
    "build_dataset",
    "gate_end",
    "observe",
    "persisted_wdk_step_ids",
    "run_corpus",
    "run_one_case",
]
