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
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

from assistant_core.platform.db import async_session_factory
from assistant_core.platform.types import ReasoningEffort
from pydantic import TypeAdapter
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import Evaluator, EvaluatorContext
from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.conversation.gene_list_marker import gene_list_marker
from pathfinder.ai.graph.state import PipelineState
from pathfinder.ai.lead.proposal import OFFER_TOOLS
from pathfinder.ai.lead.reply_claims import counts_in_the_wrong_unit
from pathfinder.devtools.capture import RunCapture, unshown_assumed_values
from pathfinder.devtools.chat import (
    RespondArgs,
    RunArgs,
    checkpoint_values,
    drive_respond,
    drive_run,
)
from pathfinder.devtools.gates import Gate
from pathfinder.domain.turn_facts import TurnFacts
from pathfinder.evals.case import EvalCase, GateAnswer, GateEnd, GatePlan
from pathfinder.evals.difference import CaseDifference
from pathfinder.evals.distance import tree_from_ast
from pathfinder.evals.drift import DriftVerdict, classify, count_difference
from pathfinder.evals.phrases import shown
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
# A gene-id list goes to the model as the text the composer writes for it.
_GENE_LIST_SUFFIXES = frozenset({".csv", ".tsv", ".txt"})
_GENE_ID_HEADER = re.compile(r"^gene.?id$", re.IGNORECASE)
_VERDICT: TypeAdapter[DriftVerdict] = TypeAdapter(DriftVerdict)
# The cards one turn answers before it is left as it stands.
_MAX_ANSWERS = 8


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


def facts_text(facts: TurnFacts | None) -> str:
    """The facts part a turn showed, one line each; empty when it showed none."""
    return "" if facts is None else "\n".join(facts.lines())


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


def counts_in_genes(reply_text: str, ast: StrategyAst) -> bool:
    """Whether the reply names no count of the strategy's steps in the record
    type, where the site counts that record type in another noun."""
    held = (ast.step_counts or {}).values()
    return not counts_in_the_wrong_unit(reply_text, ast.record_type, held)


@dataclass(frozen=True)
class TurnsShown:
    """What the case's turns showed: each reply, the facts part beside each,
    and the last facts part any turn showed."""

    replies: list[str]
    facts: list[str]
    last_facts: TurnFacts | None = None


async def observe(
    conversation_id: UUID,
    turns: TurnsShown,
    *,
    step_ids_unchanged: bool | None = None,
    ends_on: GateEnd | None = None,
    refused_tools: list[str],
) -> ObservedOutcome:
    """What the finished turns left behind, as the scorer reads it.

    The last turn is the one scored.
    """
    reply_text = turns.replies[-1] if turns.replies else ""
    last_facts = turns.facts[-1] if turns.facts else ""
    async with async_session_factory() as session:
        strategy = await ConversationRepository(session).get_strategy(conversation_id)
    built = bool(strategy.strategy_ast)
    ast = StrategyAst.model_validate(strategy.strategy_ast) if built else None
    checkpointed = await checkpoint_values(conversation_id)
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
        facts_text=last_facts,
        turn_replies=turns.replies,
        turn_facts=turns.facts,
        counts_in_genes=(
            counts_in_genes(shown(last_facts, reply_text), ast)
            if ast is not None
            else None
        ),
        root_operator=root_operator(ast) if ast is not None else None,
        final_count_below_every_input=(
            final_count_below_every_input(ast) if ast is not None else None
        ),
        root_count=root_count(ast) if ast is not None else None,
        ends_on=ends_on,
        refused_tools=refused_tools,
        assumed=unshown_assumed_values(checkpointed, turns.last_facts),
    )


def _gene_list_text(path: Path) -> str:
    """The composer's text for a gene-id list: each line's first column, once."""
    firsts = (
        re.split(r"[,\t]", line)[0].strip() for line in path.read_text().splitlines()
    )
    ids = list(dict.fromkeys(f for f in firsts if f and not _GENE_ID_HEADER.match(f)))
    return gene_list_marker(path.name, ids)


def _turn_message(case: EvalCase, index: int) -> tuple[str, list[Path]]:
    """The turn's text with its gene-id lists appended, and the files sent inline."""
    paths = attachment_paths(case, index)
    lists = [p for p in paths if p.suffix.lower() in _GENE_LIST_SUFFIXES]
    inline = [p for p in paths if p not in lists]
    text = "\n\n".join([case.turns[index], *map(_gene_list_text, lists)])
    return text, inline


def _question_answers(gate: Gate, picks: list[str]) -> list[str]:
    """Each question's answer as ``respond --answer`` takes it: ``QID=VALUE``."""
    wanted = [pick.casefold() for pick in picks]
    answers: list[str] = []
    for question in gate.consult_questions:
        if question.kind == "free_text":
            # A free-text question with no pick takes the note the debugger's
            # own automatic answer sends.
            answers.append(
                f"{question.id}={'; '.join(picks) or 'proceed with defaults'}"
            )
            continue
        labels = [o.label for o in question.options]
        picked = [
            label for label in labels if any(w in label.casefold() for w in wanted)
        ]
        recommended = [o.label for o in question.options if o.recommended]
        chosen = picked or recommended or labels[:1]
        answers.append(f"{question.id}={','.join(chosen)}")
    return answers


class _CardAnswers:
    """The answer each card of one case gets: the answer the case names for the
    card's tool and turn, else its policy's. A named answer is given once."""

    def __init__(self, plan: GatePlan) -> None:
        self._plan = plan
        self._named = list(plan.answers)

    def reply(self, gate: Gate, *, turn: int, final: bool) -> GateAnswer | None:
        if gate.kind not in {"approval", "consult"} or gate.tool is None:
            return None
        for answer in self._named:
            if answer.card == gate.tool and answer.turn == turn:
                self._named.remove(answer)
                return answer
        return self._plan.default_answer(
            gate.tool, turn=turn, offer=gate.tool in OFFER_TOOLS, final=final
        )


async def _answer(
    args: RunArgs,
    answer: GateAnswer,
    gate: Gate,
    run_dir: Path,
) -> tuple[RunCapture, Gate] | None:
    """Answer the turn's pending card as ``respond`` does, from the case's answer."""
    picks = answer.picks
    return await drive_respond(
        RespondArgs(
            site=args.site,
            conversation_id=args.conversation_id,
            run_dir=run_dir,
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
    effort the run names wins over the case's. Each card gets the answer the
    case names for its tool and turn, else the case's policy's, and each
    answer writes its own run directory under the turn's.
    """
    conversation_id = uuid4()
    last = len(case.turns) - 1
    before: set[int] = set()
    replies: list[str] = []
    shown_facts: list[str] = []
    last_facts: TurnFacts | None = None
    ended = Gate(kind="none")
    refused: list[str] = []
    cards = _CardAnswers(case.gates)
    for index in range(len(case.turns)):
        prompt, inline = _turn_message(case, index)
        if index in case.new_conversation_before:
            conversation_id = uuid4()
        if index == last and last > 0:
            before = await persisted_wdk_step_ids(conversation_id)
        args = RunArgs(
            prompt=prompt,
            site=case.site_id,
            conversation_id=conversation_id,
            run_dir=run_root / case.name / f"turn-{index + 1}",
            approve="prompt",
            via_worker=via_worker,
            quiet=True,
            assistant=case.assistant_id,
            effort=case.effort if effort is None else effort,
            attachments=inline,
        )
        capture, ended = await drive_run(args)
        refused.extend(capture.refused_tools())
        facts = capture.turn_facts()
        for given in range(1, _MAX_ANSWERS + 1):
            answer = cards.reply(ended, turn=index, final=index == last)
            if answer is None:
                break
            answered = await _answer(
                args, answer, ended, args.run_dir / f"answer-{given}"
            )
            if answered is None:
                ended = Gate(kind="none")
                break
            capture, ended = answered
            refused.extend(capture.refused_tools())
            facts = capture.turn_facts() or facts
        last_facts = facts or last_facts
        replies.append(capture.assistant_text())
        shown_facts.append(facts_text(facts))
    after = await persisted_wdk_step_ids(conversation_id)
    return await observe(
        conversation_id,
        TurnsShown(replies=replies, facts=shown_facts, last_facts=last_facts),
        step_ids_unchanged=(before == after) if before else None,
        ends_on=gate_end(ended),
        refused_tools=refused,
    )


@dataclass
class CaseVerdict(Evaluator[EvalCase, ObservedOutcome, None]):
    """The corpus expectation, as the label the harness records: a drift verdict.

    ``builds`` holds the build each site reported at the start of the run. Each
    verdict is printed the moment it is known, so a long run shows its progress.
    """

    builds: dict[str, str]

    def evaluate(
        self,
        ctx: EvaluatorContext[EvalCase, ObservedOutcome, None],
    ) -> DriftVerdict:
        build = self.builds[ctx.inputs.site_id]
        verdict = classify(ctx.inputs, ctx.output, build)
        print(_progress_line(ctx, verdict, build), flush=True)
        return verdict


def assumed_label(assumed: int | None) -> str:
    """The count of applied values the request did not state, or a dash when uncounted."""
    return f"assumed={'-' if assumed is None else assumed}"


def refusals_label(refused_tools: list[str]) -> str:
    """The refusal count, and the refused tools in order when there are any."""
    named = f" ({', '.join(refused_tools)})" if refused_tools else ""
    return f"refusals={len(refused_tools)}{named}"


def _difference_line(difference: CaseDifference) -> str:
    """One difference as the progress line prints it, with the text it read."""
    line = (
        f"{difference.field}: expected {difference.expected!r}, "
        f"got {difference.actual!r}"
    )
    return f"{line} (read {difference.read})" if difference.read else line


def _progress_line(
    ctx: EvaluatorContext[EvalCase, ObservedOutcome, None],
    verdict: DriftVerdict,
    build: str,
) -> str:
    """One case's verdict, time, root count, assumed values, refusals and first difference."""
    drift = count_difference(ctx.inputs, ctx.output, build)
    named = [
        *score_case(ctx.inputs, ctx.output).differences,
        *([] if drift is None else [drift]),
    ]
    count = "-" if ctx.output.root_count is None else str(ctx.output.root_count)
    first = "-" if not named else _difference_line(named[0])
    refusals = refusals_label(ctx.output.refused_tools)
    return (
        f"{verdict} {ctx.inputs.name} {round(ctx.duration, 3)}s "
        f"count={count} {assumed_label(ctx.output.assumed)} {refusals}  {first}"
    )


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
                refused_tools=reported.output.refused_tools,
                assumed=reported.output.assumed,
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
    "TurnsShown",
    "assumed_label",
    "build_dataset",
    "counts_in_genes",
    "facts_text",
    "gate_end",
    "observe",
    "persisted_wdk_step_ids",
    "refusals_label",
    "run_corpus",
    "run_one_case",
]
