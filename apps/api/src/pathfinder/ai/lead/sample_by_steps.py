from __future__ import annotations

from dataclasses import dataclass, field

from pydantic_ai import ToolFailed
from veupathdb.domain.strategy import StrategyStepNode
from veupathdb.errors import DataParsingError, ValidationError

from pathfinder.ai.capabilities.site_reads import read_in_time
from pathfinder.ai.lead.derive import grounded_requirements
from pathfinder.ai.lead.sub_agent_tools import LeadDeps
from pathfinder.ai.tools.standalone.step_ids import (
    LISTING_DEADLINE_SECONDS,
    STEP_IDS_CAP,
)
from pathfinder.domain.evidence import VerificationReview
from pathfinder.domain.step_membership import (
    Implied,
    StepFact,
    StepHolds,
    UnlistedStep,
    decided_by_steps,
    implied_holdings,
    requirement_by_steps,
)
from pathfinder.domain.strategy.constraints import ConstraintSource
from pathfinder.domain.strategy.operational_spec import Criterion
from pathfinder.domain.strategy.session import StrategyGraph
from pathfinder.domain.strategy.types import SyncStateProtocol
from pathfinder.services.evidence.step_answers import ids_the_step_holds


@dataclass(frozen=True)
class BuiltStep:
    title: str
    wdk_step_id: int
    count: int | None
    implied: Implied

    @property
    def unlisted(self) -> bool:
        return (
            self.implied is None
            and self.count is not None
            and self.count > STEP_IDS_CAP
        )


@dataclass(frozen=True)
class StepsDecide:
    root: StrategyStepNode | None = None
    requirements: list[tuple[str, frozenset[str]]] = field(default_factory=list)
    steps: dict[str, BuiltStep] = field(default_factory=dict)
    unlisted: list[UnlistedStep] = field(default_factory=list)
    judged: bool = True

    def lines(self) -> list[str]:
        if not self.requirements:
            return []
        return [
            (
                "The steps decide these requirements for each sampled gene, by "
                "whether the step holds it:"
            ),
            *(
                f"- {asked}: "
                + " or ".join(f"'{self.steps[step].title}'" for step in sorted(linked))
                for asked, linked in self.requirements
            ),
        ]

    @property
    def listed(self) -> list[str]:
        return sorted(
            {
                step
                for _, linked in self.requirements
                for step in linked
                if self.steps[step].implied is None
            }
        )


def _links(criterion: Criterion, requirement_id: str) -> bool:
    return any(
        link.requirement == requirement_id and not link.result_size
        for link in criterion.answers
    )


def _built(
    graph: StrategyGraph, sync: SyncStateProtocol, ast_root: StrategyStepNode
) -> dict[str, BuiltStep]:
    return {
        step_id: BuiltStep(
            title=graph.steps[step_id].display_label,
            wdk_step_id=wdk_step_id,
            count=sync.step_counts.get(step_id),
            implied=implied,
        )
        for step_id, implied in implied_holdings(ast_root).items()
        if (wdk_step_id := sync.wdk_step_ids.get(step_id)) is not None
    }


def _unlisted(
    requirement: str, linked: frozenset[str], built: dict[str, BuiltStep]
) -> list[UnlistedStep]:
    return [
        UnlistedStep(
            requirement=requirement,
            title=built[step].title,
            count=count,
            listed_at_most=STEP_IDS_CAP,
        )
        for step in sorted(linked)
        if built[step].unlisted and (count := built[step].count) is not None
    ]


def steps_decide(deps: LeadDeps) -> StepsDecide:
    session = deps.runtime.strategy_session
    graph, sync = session.get_graph(None), session.sync_state
    ast = None if graph is None else graph.to_strategy_ast()
    spec = deps.state.domain.operational_spec
    if graph is None or sync is None or ast is None or spec is None:
        return StepsDecide()
    built = _built(graph, sync, ast.root)
    stated = [
        held.constraint
        for held in grounded_requirements(deps.state, deps.intent)
        if held.constraint.source is ConstraintSource.USER_EXPLICIT
    ]
    linked = [
        (
            asked.requested_value,
            frozenset(
                c.id for c in spec.criteria if c.id in built and _links(c, asked.id)
            ),
        )
        for asked in stated
    ]
    unlisted = [u for asked, held in linked for u in _unlisted(asked, held, built)]
    too_large = {u.requirement for u in unlisted}
    decided = [(a, held) for a, held in linked if held and a not in too_large]
    return StepsDecide(
        root=ast.root,
        requirements=decided,
        steps=built,
        unlisted=unlisted,
        judged=not stated or len(decided) < len(stated),
    )


async def _held(site_id: str, step: BuiltStep, gene_ids: list[str]) -> StepHolds:
    try:
        return await read_in_time(
            "the steps that hold the sampled genes",
            f"step {step.wdk_step_id}",
            ids_the_step_holds(
                site_id,
                step.wdk_step_id,
                gene_ids=gene_ids,
                listed_at_most=STEP_IDS_CAP,
            ),
            deadline=LISTING_DEADLINE_SECONDS,
        )
    except ToolFailed, ValidationError, DataParsingError:
        return StepHolds()


async def sampled_by_their_steps(
    deps: LeadDeps, decide: StepsDecide, review: VerificationReview
) -> VerificationReview:
    root = decide.root
    gene_ids = [gene.gene_id for gene in review.sampled_genes]
    if root is None or not gene_ids:
        return review
    held = {
        step: await _held(deps.runtime.site_id, decide.steps[step], gene_ids)
        for step in decide.listed
    }
    genes = []
    for gene in review.sampled_genes:
        facts = {
            step: StepFact(
                title=built.title,
                holding=built.implied or held[step].holding(gene.gene_id),
            )
            for step, built in decide.steps.items()
            if built.implied is not None or step in held
        }
        decided = [
            requirement_by_steps(root, requirement, linked, facts)
            for requirement, linked in decide.requirements
        ]
        genes.append(
            decided_by_steps(gene, decided, decide.unlisted, judged=decide.judged)
        )
    return review.model_copy(update={"sampled_genes": genes})
