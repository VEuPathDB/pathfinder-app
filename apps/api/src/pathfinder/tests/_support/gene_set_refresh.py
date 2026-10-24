"""A stored strategy root, and the refresh job run the way the worker runs it."""

from dataclasses import dataclass, field
from uuid import UUID

import pytest
from assistant_core.platform.db import async_session_factory
from assistant_core.tasks.job_context import durable_job_context
from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.domain.strategy import CombineOp, StrategyAst, StrategyStepNode
from veupathdb.errors import ValidationError

from pathfinder.jobs.impls.gene_set_refresh_impl import refresh_strategy_gene_set
from pathfinder.persistence.repositories import (
    ConversationRepository,
    ConversationUpdate,
)
from pathfinder.services.gene_sets import operations
from pathfinder.services.gene_sets.homes import StepGenes
from pathfinder.services.gene_sets.strategy_genes import StrategyGenes
from pathfinder.services.gene_sets.types import StrategyRootContext
from pathfinder.services.strategies.gene_set_refresh import GeneSetRefreshJob

RESEARCHER_TOKEN = "wdk-session-of-the-researcher"


def root(operator: CombineOp) -> StrategyAst:
    """Two text searches joined at ``operator``, as a thread stores them."""
    return StrategyAst(
        record_type="transcript",
        root=StrategyStepNode(
            id="step_root",
            search_name="__combine__",
            primary_input=StrategyStepNode(id="step_a", search_name="GenesByText"),
            secondary_input=StrategyStepNode(id="step_b", search_name="GenesByText"),
            operator=operator,
        ),
    )


async def store_root(conversation_id: UUID, operator: CombineOp) -> StrategyAst:
    """Write the root a commit leaves on the thread."""
    stored = root(operator)
    async with async_session_factory() as session:
        await ConversationRepository(session).update_conversation(
            conversation_id, ConversationUpdate(strategy_ast=stored)
        )
        await session.commit()
    return stored


async def run_refresh_job(conversation_id: UUID) -> None:
    """Run the job body with the payload a write under the researcher defers."""
    reset = veupathdb_auth_token_ctx.set(RESEARCHER_TOKEN)
    try:
        carried = durable_job_context().capture().model_dump(mode="json")
    finally:
        veupathdb_auth_token_ctx.reset(reset)
    job = GeneSetRefreshJob(
        conversation_id=conversation_id, site_id="plasmodb", job_context=carried
    )
    await refresh_strategy_gene_set(job.model_dump(mode="json"))


@dataclass(frozen=True)
class RootAnswer:
    gene_ids: list[str] = field(default_factory=list)
    refusal: ValidationError | None = None


class ServedRoots:
    def __init__(self, answers: list[RootAnswer]) -> None:
        self.answers = answers
        self.tokens: list[str | None] = []

    async def read(self, site_id: str, wdk_strategy_id: int) -> StrategyGenes:
        del site_id
        self.tokens.append(veupathdb_auth_token_ctx.get())
        answer = self.answers.pop(0)
        if answer.refusal is not None:
            raise answer.refusal
        return StrategyGenes(
            genes=StepGenes(
                gene_ids=list(answer.gene_ids), homes={}, record_class="transcript"
            ),
            context=StrategyRootContext(
                wdk_strategy_id=wdk_strategy_id,
                wdk_step_id=439858931,
                search_name=None,
                record_type="transcript",
                parameters=None,
            ),
            step_count=3,
        )


def serve_roots(
    monkeypatch: pytest.MonkeyPatch, answers: list[RootAnswer]
) -> ServedRoots:
    served = ServedRoots(answers)
    monkeypatch.setattr(operations, "read_strategy_genes", served.read)
    return served
