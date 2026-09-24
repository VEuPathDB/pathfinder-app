r"""Builders for the ``DataChunk``\ s that carry strategy telemetry to the
frontend as data parts on the assistant message."""

from __future__ import annotations

from assistant_core.platform.pydantic_base import CamelModel
from pydantic_ai.ui.vercel_ai.response_types import DataChunk

from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.stream_part_payloads import ControlTestResults
from pathfinder.domain.evidence import EvidenceCard


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
