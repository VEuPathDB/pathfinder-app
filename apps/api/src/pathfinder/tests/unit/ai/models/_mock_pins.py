"""The instructions and work orders a mock role reads, as the real renderers
write them: the Lead's pinned spec and memories, and FRAME's EDIT order."""

from __future__ import annotations

from datetime import UTC, datetime

from assistant_core.memory.schemas import MemoryValue
from veupathdb.domain.parameters import MultiPickValue, ParamValue, StringValue
from veupathdb.domain.strategy import CombineOp

from pathfinder.ai.agents._instructions import pinned_user_memories
from pathfinder.ai.lead.edit_messages import edit_work_order
from pathfinder.ai.lead.lead_pins import pinned_operational_spec
from pathfinder.ai.models.mock.site_values import SiteValues
from pathfinder.domain.strategy.operational_spec import (
    Criterion,
    OperationalSpec,
    SpecStructure,
    StructureNode,
)
from pathfinder.domain.strategy.spec_diff import SpecDiff
from pathfinder.tests._support.run_context import lead_run_context


def unframed_pins() -> str:
    """The Lead's pinned spec on a thread that has framed nothing yet."""
    return pinned_operational_spec(lead_run_context()) or ""


def framed_pins() -> str:
    """The Lead's pinned spec on a thread that already framed a request."""
    ctx = lead_run_context()
    ctx.deps.state.domain.operational_spec = OperationalSpec(goal="kinases")
    return pinned_operational_spec(ctx) or ""


def memory_pins(summary: str) -> str:
    """The recalled memories pinned for the Lead, holding one preference."""
    ctx = lead_run_context()
    ctx.deps.retrieved_memories = [
        MemoryValue(
            kind="preference",
            name="default organism",
            summary=summary,
            content={},
            created_at=datetime.now(UTC),
        )
    ]
    return pinned_user_memories(ctx) or ""


def _criterion(cid: str, search: str, params: dict[str, ParamValue]) -> Criterion:
    return Criterion(
        id=cid,
        text=f"{search} genes",
        search_name=search,
        role="filter",
        resolved_params=params,
    )


def edit_order(site_id: str) -> str:
    """The EDIT work order of a thread holding signal peptide INTERSECT domains."""
    organism = MultiPickValue(values=[SiteValues.for_site(site_id).organism])
    before = OperationalSpec(
        goal="secreted membrane genes",
        criteria=[
            _criterion(
                "signal_peptide", "GenesWithSignalPeptide", {"organism": organism}
            ),
            _criterion(
                "tm_domains",
                "GenesByTransmembraneDomains",
                {"organism": organism, "min_tm": StringValue(value="2")},
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=CombineOp.INTERSECT,
                inputs=[
                    StructureNode(kind="leaf", criterion_id="signal_peptide"),
                    StructureNode(kind="leaf", criterion_id="tm_domains"),
                ],
            )
        ),
    )
    return edit_work_order(
        "mock edit",
        "Change it",
        before,
        pending=SpecDiff(),
        answered=before,
        answer=None,
    )
