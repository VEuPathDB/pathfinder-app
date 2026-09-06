"""The seam between the memory store and what PathFinder remembers.

Storing, ranking and tombstoning a memory is generic. Which kinds exist, and
which of a finished turn's artifacts are worth keeping, are the product's, so
they reach the store as arguments rather than as imports.
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from types import ModuleType
from uuid import uuid4

import pytest
from assistant_core import memory
from assistant_core.memory.autowrite import auto_write_memories
from assistant_core.memory.retrieval import retrieve_relevant_memories
from assistant_core.memory.schemas import MemoryEntryDraft
from assistant_core.memory.store import memory_namespace
from veupathdb.domain.strategy.operational_spec import OperationalSpec

from pathfinder.ai.graph.state import (
    PhaseDisposition,
    PipelineState,
    StrategyDomainState,
    VerificationDigest,
)
from pathfinder.ai.lead.memory_candidates import (
    PRODUCT_MEMORY_KINDS,
    collect_memory_candidates,
)

FOREIGN_PACKAGES = (
    "veupathdb.domain.strategy",
    "pathfinder.ai.lead",
    "pathfinder.ai.graph",
    "pathfinder.services",
)


def _memory_modules() -> list[ModuleType]:
    return [
        importlib.import_module(info.name)
        for info in pkgutil.walk_packages(
            memory.__path__,
            prefix=f"{memory.__name__}.",
        )
    ]


def _foreign_bindings(module: ModuleType) -> set[str]:
    found: set[str] = set()
    for value in vars(module).values():
        origin = getattr(value, "__module__", None)
        if not isinstance(origin, str):
            continue
        found.update(pkg for pkg in FOREIGN_PACKAGES if origin.startswith(pkg))
    return found


@pytest.mark.parametrize("module", _memory_modules(), ids=lambda m: m.__name__)
def test_no_memory_module_binds_product_science(module: ModuleType) -> None:
    assert _foreign_bindings(module) == set()


def test_autowrite_is_handed_its_candidates() -> None:
    params = inspect.signature(auto_write_memories).parameters
    assert "candidates" in params
    assert "state" not in params


def test_retrieval_is_told_which_kinds_to_search() -> None:
    assert "kinds" in inspect.signature(retrieve_relevant_memories).parameters


def test_the_namespace_accepts_a_kind_the_core_never_declared() -> None:
    user_id = uuid4()
    namespace = memory_namespace(user_id=user_id, kind="contact", application_id="app1")
    assert namespace == ("app", "app1", "user", str(user_id), "contact")


def test_the_product_declares_the_five_pathfinder_kinds() -> None:
    assert PRODUCT_MEMORY_KINDS == (
        "gene_set",
        "strategy",
        "preference",
        "knowledge",
        "case",
    )


def test_the_product_turns_a_verified_turn_into_its_candidates() -> None:
    conversation_id = uuid4()
    state = PipelineState(
        conversation_id=conversation_id,
        user_id=uuid4(),
        site_id="plasmodb",
        mode="strategy",
        user_prompt="find Plasmodium kinases",
        domain=StrategyDomainState(
            operational_spec=OperationalSpec(
                goal="kinases",
                criteria=[],
                interpreted_goal="find kinases",
            ),
            created_gene_set_ids=["gs-1"],
            verification_digest=VerificationDigest(
                disposition=PhaseDisposition.DONE,
                prose="done",
                reason="ok",
                success=True,
                remember=[
                    MemoryEntryDraft(name="kinome", summary="~142 kinases"),
                ],
            ),
        ),
    )

    candidates = collect_memory_candidates(state)

    assert [(value.kind, key) for value, key in candidates] == [
        ("gene_set", "gene_set:gs-1"),
        ("knowledge", f"knowledge:{conversation_id.hex}:0"),
    ]
