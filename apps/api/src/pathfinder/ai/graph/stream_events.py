r"""Builders for the ``DataChunk``\ s that carry strategy telemetry to the
frontend as data parts on the assistant message."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from assistant_core.memory.store import StoredMemory
from assistant_core.platform.pydantic_base import CamelModel
from pydantic import TypeAdapter
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.stream_part_payloads import ControlTestResults
from pathfinder.domain.evidence import EvidenceCard
from pathfinder.domain.memory import MemoryKind
from pathfinder.domain.separation import SeparationReport


def control_test_results_event(results: ControlTestResults) -> DataChunk:
    """Report the numbers one control test measured, as its own exhibit."""
    return DataChunk(
        type="data-control-test-results",
        data=results.model_dump(by_alias=True, mode="json"),
    )


def evidence_card_event(card: EvidenceCard) -> DataChunk:
    """Report the evidence behind one check, as its own part."""
    return DataChunk(
        type="data-evidence-card",
        data=card.model_dump(by_alias=True, mode="json"),
    )


def separation_result_event(report: SeparationReport) -> DataChunk:
    """Report what one separation run measured and what it offers."""
    return DataChunk(
        type="data-separation-result",
        data=report.model_dump(by_alias=True, mode="json"),
    )


class StrategyRevisionPayload(CamelModel):
    """Payload for the strategy-revision chunk. The revision is a fingerprint
    of the strategy that the turn describes.
    """

    revision: str


def strategy_revision_event(*, revision: str) -> DataChunk:
    return DataChunk(
        type="data-strategy-revision",
        data=StrategyRevisionPayload(revision=revision).model_dump(
            by_alias=True,
            mode="json",
        ),
    )


def ledger_update_event(*, ledger: InvestigationLedger) -> DataChunk:
    """Report a snapshot of the investigation ledger."""
    return DataChunk(
        type="data-ledger-update",
        data=ledger.model_dump(by_alias=True, mode="json"),
    )


class RecalledMemory(CamelModel):
    """One memory a turn recalled, with the thread that wrote it and when."""

    key: str
    kind: MemoryKind
    name: str
    summary: str
    created_at: datetime
    source_conversation_id: UUID | None = None


class RecalledMemoriesPayload(CamelModel):
    memories: list[RecalledMemory]


_MEMORY_KIND: TypeAdapter[MemoryKind] = TypeAdapter(MemoryKind)


def recalled_memories_event(*, memories: list[StoredMemory]) -> DataChunk:
    """Report the memories recalled at turn start, each key of a kind once."""
    recalled: dict[tuple[str, str], RecalledMemory] = {}
    for m in memories:
        recalled.setdefault(
            (m.value.kind, m.key),
            RecalledMemory(
                key=m.key,
                kind=_MEMORY_KIND.validate_python(m.value.kind),
                name=m.value.name,
                summary=m.value.summary,
                created_at=m.value.created_at,
                source_conversation_id=m.value.source_conversation_id,
            ),
        )
    payload = RecalledMemoriesPayload(memories=list(recalled.values()))
    return DataChunk(
        type="data-memory-retrieved",
        data=payload.model_dump(by_alias=True, mode="json"),
    )
