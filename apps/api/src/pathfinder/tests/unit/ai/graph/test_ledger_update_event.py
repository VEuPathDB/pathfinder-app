"""The ledger chunk carries every key its serialization schema requires."""

from uuid import UUID

from pathfinder.ai.graph.stream_events import (
    enrichment_results_event,
    ledger_update_event,
)
from pathfinder.ai.lead.ledger import InvestigationLedger
from pathfinder.ai.lead.ledger_sections import (
    BuildSection,
    FrameSection,
    VerificationSection,
)
from pathfinder.ai.stream_part_payloads import EnrichmentResultsChunk
from pathfinder.services.enrichment.types import EnrichmentResult, EnrichmentTerm


def _required_keys(model: type[InvestigationLedger]) -> frozenset[str]:
    schema = model.model_json_schema(mode="serialization")
    return frozenset(schema["required"])


def _empty_ledger() -> InvestigationLedger:
    return InvestigationLedger(
        user_intent=None,
        frame=FrameSection(),
        build=BuildSection(),
        verification=VerificationSection(),
    )


def test_ledger_chunk_carries_every_required_top_level_key() -> None:
    chunk = ledger_update_event(ledger=_empty_ledger())
    assert isinstance(chunk.data, dict)
    assert _required_keys(InvestigationLedger) <= frozenset(chunk.data)


def test_ledger_chunk_carries_the_nullable_section_fields() -> None:
    chunk = ledger_update_event(ledger=_empty_ledger())
    assert chunk.data == {
        "userIntent": None,
        "frame": {
            "spec": None,
            "present": False,
            "diff": None,
            "criteriaCount": 0,
            "boundCount": 0,
            "openSlotCount": 0,
            "droppedCount": 0,
            "readyToBuild": False,
            "needsUser": False,
            "contrasts": [],
            "structureRender": None,
        },
        "build": {
            "outcome": None,
            "staleBuild": None,
            "pushedCount": 0,
            "failedCount": 0,
            "skippedCount": 0,
            "zeroResultSteps": [],
            "needsRecovery": False,
            "recoveryKind": "none",
            "succeeded": False,
            "nodeResults": [],
            "wdkStrategyId": None,
            "wdkUrl": None,
        },
        "verification": {"digest": None, "complete": False, "successful": False},
        "constraints": {"grounded": [], "unmetCount": 0, "blocking": False},
    }


def test_ledger_chunk_sections_carry_every_required_key() -> None:
    chunk = ledger_update_event(ledger=_empty_ledger())
    assert isinstance(chunk.data, dict)
    for field, section in (
        ("frame", FrameSection),
        ("build", BuildSection),
        ("verification", VerificationSection),
    ):
        payload = chunk.data[field]
        assert isinstance(payload, dict)
        required = frozenset(
            section.model_json_schema(mode="serialization")["required"]
        )
        assert required <= frozenset(payload), field


_GO_RESULT = EnrichmentResult(
    analysis_type="go_function",
    terms=[
        EnrichmentTerm(
            term_id="GO:0004672",
            term_name="protein kinase activity",
            gene_count=87,
            background_count=5412,
            fold_enrichment=3.48,
            odds_ratio=3.61,
            p_value=3.4e-13,
            fdr=1.1e-10,
            bonferroni=2.2e-10,
        )
    ],
    total_genes_analyzed=87,
    background_size=5412,
)


def test_enrichment_chunk_matches_its_payload_model() -> None:
    task_id = UUID("d7e0c4a0-0000-4000-8000-000000000000")
    chunk = enrichment_results_event(
        task_id=task_id,
        gene_set_id="gs_1",
        gene_set_name="kinases",
        gene_count=87,
        results=[_GO_RESULT],
    )
    assert isinstance(chunk.data, dict)
    required = frozenset(
        EnrichmentResultsChunk.model_json_schema(mode="serialization")["required"]
    )
    assert required <= frozenset(chunk.data)
    assert chunk.data["taskId"] == "d7e0c4a0-0000-4000-8000-000000000000"
