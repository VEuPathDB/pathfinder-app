from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from pydantic import TypeAdapter
from pydantic_ai import ApprovalRequired, ModelRetry

from pathfinder.ai.explore import account_reads
from pathfinder.ai.explore.account_reads import (
    GeneSetReading,
    ask_to_read_the_account,
    list_my_threads,
    read_gene_set,
)
from pathfinder.services.conversations.thread_reading import ThreadListing
from pathfinder.services.gene_sets.types import GeneSet
from pathfinder.tests._support.run_context import lead_run_context

_THREADS: TypeAdapter[list[ThreadListing]] = TypeAdapter(list[ThreadListing])
_THREAD = ThreadListing(
    conversation_id=uuid4(), name="kinases in falciparum", site_id="plasmodb"
)


@pytest.fixture
def standing(monkeypatch: pytest.MonkeyPatch) -> list[bool]:
    allowed = [False]

    async def _allowed(conversation_id: UUID, user_id: UUID) -> bool:
        del conversation_id, user_id
        return allowed[0]

    async def _threads(user_id: UUID, *, but: UUID) -> list[ThreadListing]:
        del user_id, but
        return [_THREAD]

    monkeypatch.setattr(account_reads, "standing_leave", _allowed)
    monkeypatch.setattr(account_reads, "other_threads", _threads)
    return allowed


async def test_a_read_without_leave_asks_first(standing: list[bool]) -> None:
    del standing

    with pytest.raises(ModelRetry, match="ask_to_read_the_account"):
        await list_my_threads(lead_run_context())


async def test_an_approved_ask_lets_the_turns_reads_run(standing: list[bool]) -> None:
    del standing
    ctx = lead_run_context()

    await ask_to_read_the_account(
        replace(ctx, tool_call_approved=True), what="your other threads"
    )
    listed = await list_my_threads(ctx)

    assert _THREADS.validate_python(listed.return_value) == [_THREAD]


async def test_a_standing_leave_needs_no_ask(standing: list[bool]) -> None:
    standing[0] = True

    listed = await list_my_threads(lead_run_context())

    assert _THREADS.validate_python(listed.return_value) == [_THREAD]


async def test_a_gene_set_read_names_its_genes(
    standing: list[bool], monkeypatch: pytest.MonkeyPatch
) -> None:
    standing[0] = True
    ctx = lead_run_context()
    held = GeneSet(
        id="gs1",
        name="kinases",
        site_id="plasmodb",
        gene_ids=["PF3D7_0102200", "PF3D7_0107600"],
        source="strategy",
        user_id=ctx.deps.state.user_id,
    )

    async def _get(gene_set_id: str, *, user_id: UUID | None) -> GeneSet | None:
        return held if (gene_set_id, user_id) == ("gs1", held.user_id) else None

    monkeypatch.setattr(account_reads, "get_gene_set", _get)

    read = await read_gene_set(ctx, gene_set_id="gs1")

    gene_set = GeneSetReading.model_validate(read.return_value)
    assert (gene_set.name, gene_set.gene_ids) == (
        "kinases",
        ["PF3D7_0102200", "PF3D7_0107600"],
    )


async def test_an_ask_that_was_not_approved_grants_nothing(
    standing: list[bool],
) -> None:
    del standing
    ctx = lead_run_context()

    with pytest.raises(ApprovalRequired):
        await ask_to_read_the_account(ctx, what="your other threads")

    assert ctx.deps.state.turn_markers.account_reads_allowed is False
    with pytest.raises(ModelRetry, match="ask_to_read_the_account"):
        await list_my_threads(ctx)
