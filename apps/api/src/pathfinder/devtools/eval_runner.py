"""Running the corpus against the pipeline, and writing the run summary.

Each case is one fresh thread, driven turn by turn end to end, exactly as a
chat turn runs. What the run produced is read back from the two durable
records: the strategy projection, and the checkpoint the turn left.

The harness is ``pydantic-evals``: it owns the dataset, the case loop and the
evaluator protocol. The summary shape is ours, so a change of harness does not
change the feed.

**What a deterministic-provider run can settle.** With
``PATHFINDER_CHAT_PROVIDER=mock`` the model is a script, so a run tests the
pipeline, not the model: routing, materialisation, persistence, the shape of
the strategy the phases assemble, and the verdict the turn reports. It cannot
settle whether a real model would have chosen that route. The corpus is the
same either way: ``--real`` runs the same cases against the configured provider,
and needs a VEuPathDB login exactly as the chat debugger does.
"""

from __future__ import annotations

import datetime
from pathlib import Path
from uuid import UUID, uuid4

from assistant_core.conversation.checkpointer import lifespan_checkpointer
from assistant_core.platform.db import async_session_factory
from langchain_core.runnables import RunnableConfig
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from veupathdb.domain.strategy.strategy_ast import StrategyAst

from pathfinder.ai.graph.state import StrategyDomainState
from pathfinder.assistants.registry import get_assistant_registry
from pathfinder.devtools.chat import RunArgs, drive_run, resolve_run_assistant
from pathfinder.evals.case import EvalCase
from pathfinder.evals.distance import tree_from_ast
from pathfinder.evals.scoring import (
    ObservedOutcome,
    score_case,
    structure_signature,
)
from pathfinder.evals.store import load_corpus
from pathfinder.evals.summary import CaseResult, EvalRunSummary
from pathfinder.persistence.repositories import ConversationRepository
from pathfinder.platform.config import get_settings

HARNESS = "pydantic-evals"
MOCK_PROVIDER = "mock"


async def _verification_verdict(conversation_id: UUID) -> bool | None:
    """The verdict the turn checkpointed, or None when it verified nothing."""
    registry = get_assistant_registry()
    spec = await resolve_run_assistant(conversation_id)
    async with lifespan_checkpointer(
        get_settings().database_url,
        checkpoint_types=registry.checkpoint_types(),
    ) as saver:
        graph = spec.build_graph(saver)
        config: RunnableConfig = {"configurable": {"thread_id": str(conversation_id)}}
        snapshot = await graph.aget_state(config)
    domain = StrategyDomainState.model_validate(snapshot.values.get("domain") or {})
    digest = domain.verification_digest
    return None if digest is None else digest.success


async def persisted_wdk_step_ids(conversation_id: UUID) -> set[int]:
    """The WDK step ids the thread's persisted strategy carries right now."""
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    if not strategy.strategy_ast:
        return set()
    ast = StrategyAst.model_validate(strategy.strategy_ast)
    return set((ast.wdk_step_ids or {}).values())


async def observe(
    conversation_id: UUID,
    reply_text: str,
    *,
    step_ids_unchanged: bool | None = None,
) -> ObservedOutcome:
    """What the finished turn left behind, as the scorer reads it."""
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    built = bool(strategy.strategy_ast)
    ast = StrategyAst.model_validate(strategy.strategy_ast) if built else None
    return ObservedOutcome(
        built_strategy=built,
        structure=structure_signature(ast) if ast is not None else None,
        record_type=strategy.record_type or None,
        step_count=strategy.step_count if built else None,
        verified=await _verification_verdict(conversation_id),
        step_ids_unchanged=step_ids_unchanged,
        tree=tree_from_ast(ast) if ast is not None else None,
        reply_text=reply_text,
    )


async def run_one_case(
    case: EvalCase,
    *,
    run_root: Path,
    mock: bool = True,
) -> ObservedOutcome:
    """Drive every turn of one case on a fresh thread, in order.

    The step ids are read on both sides of the last turn. A thread that held
    none before it observes nothing, because there was nothing to keep.
    """
    conversation_id = uuid4()
    last = len(case.turns) - 1
    before: set[int] = set()
    reply = ""
    for index, prompt in enumerate(case.turns):
        capture, _gate = await drive_run(
            RunArgs(
                prompt=prompt,
                site=case.site_id,
                conversation_id=conversation_id,
                run_dir=run_root / case.name / f"turn-{index + 1}",
                mock=mock,
                approve="auto",
                quiet=True,
                assistant=case.assistant_id,
            ),
        )
        reply = capture.assistant_text()
        if index == last - 1:
            before = await persisted_wdk_step_ids(conversation_id)
    after = await persisted_wdk_step_ids(conversation_id)
    return await observe(
        conversation_id,
        reply,
        step_ids_unchanged=(before == after) if before else None,
    )


class CaseExpectation(Evaluator[EvalCase, ObservedOutcome, None]):
    """The corpus expectation, as an assertion the harness records."""

    def evaluate(
        self,
        ctx: EvaluatorContext[EvalCase, ObservedOutcome, None],
    ) -> bool:
        return score_case(ctx.inputs, ctx.output).passed


def build_dataset(cases: list[EvalCase]) -> Dataset[EvalCase, ObservedOutcome, None]:
    """The corpus as a harness dataset, one row per case."""
    return Dataset[EvalCase, ObservedOutcome, None](
        name="pathfinder-logic",
        cases=[Case(name=case.name, inputs=case) for case in cases],
        evaluators=[CaseExpectation()],
    )


async def run_corpus(
    *,
    run_root: Path,
    only: list[str] | None = None,
    mock: bool = True,
) -> EvalRunSummary:
    """Run the corpus and return the summary. Cases run one at a time.

    Every case writes the same checkpoint store, so concurrency is one.
    """
    cases = [case for case in load_corpus() if not only or case.name in only]
    dataset = build_dataset(cases)

    async def task(case: EvalCase) -> ObservedOutcome:
        return await run_one_case(case, run_root=run_root, mock=mock)

    report = await dataset.evaluate(task, max_concurrency=1, progress=False)

    by_name = {case.name: case for case in cases}
    results: list[CaseResult] = []
    for reported in report.cases:
        # The harness's own assertion decides the verdict; the score is read
        # for the distance either way, and for the differences of a failure.
        passed = all(result.value for result in reported.assertions.values())
        score = score_case(by_name[reported.name], reported.output)
        results.append(
            CaseResult(
                name=reported.name,
                passed=passed,
                differences=[] if passed else score.differences,
                distance=score.distance,
                duration_seconds=round(reported.task_duration, 3),
            ),
        )
    results.extend(
        CaseResult(name=failure.name, passed=False, error=failure.error_message)
        for failure in report.failures
    )
    return EvalRunSummary(
        harness=HARNESS,
        provider=MOCK_PROVIDER if mock else get_settings().pathfinder_chat_provider,
        assistant_id=cases[0].assistant_id if cases else "",
        ran_at=datetime.datetime.now(tz=datetime.UTC).isoformat(timespec="seconds"),
        cases=sorted(results, key=lambda result: result.name),
    )


__all__ = [
    "HARNESS",
    "build_dataset",
    "observe",
    "persisted_wdk_step_ids",
    "run_corpus",
    "run_one_case",
]
