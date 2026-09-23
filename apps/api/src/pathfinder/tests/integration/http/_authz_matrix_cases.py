"""The requests the authorization matrix issues, and the resources they need."""

from __future__ import annotations

from typing import Any

from pathfinder.tests.integration.http._authz_matrix_support import (
    CONVERSATION,
    EXPERIMENT,
    GENE_IDS,
    GENE_SET,
    MEMORY,
    MEMORY_KIND,
    ROOT_STEP_ID,
    SITE_ID,
    Case,
    Owned,
)
from pathfinder.tests.integration.http.conftest import chat_body

_CONV = frozenset({CONVERSATION.name})
_EXP = frozenset({EXPERIMENT.name})
_GS = frozenset({GENE_SET.name})
_MEM = frozenset({MEMORY.name})
_PRIMARY_KEY = {"primaryKey": [{"name": "source_id", "value": GENE_IDS[0]}]}
_ORGANISM = "Plasmodium falciparum 3D7"


def _experiment_body(gene_set_id: str) -> dict[str, Any]:
    """A create-experiment body whose only foreign id is the gene set."""
    return {
        "siteId": SITE_ID,
        "recordType": "transcript",
        "searchName": "GenesByText",
        "parameters": {},
        "positiveControls": [GENE_IDS[0]],
        "negativeControls": [GENE_IDS[1]],
        "controlsSearchName": "GeneByLocusTag",
        "controlsParamName": "ds_gene_ids",
        "name": "stolen evaluation",
        "geneSetId": gene_set_id,
    }


def _conversation_cases(owned: Owned) -> tuple[Case, ...]:
    conv = str(owned.conversation_id)
    base = f"/api/v1/conversations/{conv}"
    notes = f"{base}/scratchpad/notes/{owned.note_id}"
    site = f"?siteId={SITE_ID}"
    return (
        Case(
            "POST",
            "/api/v1/chat",
            "/api/v1/chat",
            _CONV,
            chat_body(owned.conversation_id),
        ),
        Case(
            "PATCH",
            "/api/v1/conversations/{strategyId:uuid}",
            base,
            _CONV,
            {"name": "renamed by an intruder"},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{strategyId:uuid}/fork",
            f"{base}/fork",
            _CONV,
            {"fromMessageId": str(owned.message_id)},
        ),
        Case("DELETE", "/api/v1/conversations/{strategyId:uuid}", base, _CONV),
        Case(
            "POST",
            "/api/v1/conversations/{strategyId:uuid}/restore",
            f"{base}/restore",
            _CONV,
        ),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id}/begin",
            f"{base}/begin",
            _CONV,
            {"siteId": SITE_ID},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{strategyId:uuid}/operations",
            f"{base}/operations{site}",
            _CONV,
            {"op": {"kind": "updateStrategyMeta", "name": "renamed by an intruder"}},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{strategyId:uuid}/refresh-counts",
            f"{base}/refresh-counts{site}",
            _CONV,
        ),
        Case(
            "POST",
            "/api/v1/conversations/open",
            "/api/v1/conversations/open",
            _CONV,
            {"conversationId": conv, "siteId": SITE_ID},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id}/dismiss",
            f"{base}/dismiss",
            _CONV,
        ),
        Case(
            "PATCH",
            "/api/v1/conversations/{conversation_id}/eda",
            f"{base}/eda",
            _CONV,
            {"action": "unbind"},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id}/duplicate",
            f"{base}/duplicate",
            _CONV,
        ),
        Case(
            "PATCH",
            "/api/v1/conversations/{conversation_id}/scratchpad/notes/{note_id}",
            notes,
            _CONV,
            {"pinned": True},
        ),
        Case(
            "DELETE",
            "/api/v1/conversations/{conversation_id}/scratchpad/notes/{note_id}",
            notes,
            _CONV,
        ),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id}/revert-to-message",
            f"{base}/revert-to-message",
            _CONV,
            {"messageId": str(owned.message_id)},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id:uuid}/save-substrategy",
            f"{base}/save-substrategy{site}",
            _CONV,
            {"stepId": ROOT_STEP_ID, "name": "stolen subtree"},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id:uuid}/insert-saved",
            f"{base}/insert-saved{site}",
            _CONV,
            {"targetStepId": ROOT_STEP_ID, "savedWdkStrategyId": 1},
        ),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id}/cancel",
            f"{base}/cancel",
            _CONV,
        ),
        Case(
            "POST",
            "/api/v1/eval/strategy-gene-ids",
            "/api/v1/eval/strategy-gene-ids",
            _CONV,
            {"strategyId": conv, "siteId": SITE_ID},
        ),
    )


def _experiment_cases(owned: Owned) -> tuple[Case, ...]:
    first, _second = owned.experiment_ids
    base = f"/api/v1/experiments/{first}"
    # A conversation id nobody holds yet, so the experiment is the only
    # foreign resource in the request.
    fresh = str(owned.unclaimed_conversation_id)
    chat = chat_body(owned.unclaimed_conversation_id) | {"experimentId": first}
    return (
        Case("POST", "/api/v1/chat", "/api/v1/chat", _EXP, chat),
        Case(
            "POST",
            "/api/v1/conversations/{conversation_id}/begin",
            f"/api/v1/conversations/{fresh}/begin",
            _EXP,
            {"siteId": SITE_ID, "experimentId": first},
        ),
        Case(
            "POST",
            "/api/v1/experiments/{experiment_id}/custom-enrich",
            f"{base}/custom-enrich",
            _EXP,
            {"geneIds": list(GENE_IDS), "geneSetName": "intruder set"},
        ),
        Case(
            "POST",
            "/api/v1/experiments/{experiment_id}/results/record",
            f"{base}/results/record",
            _EXP,
            _PRIMARY_KEY,
        ),
        Case(
            "POST",
            "/api/v1/experiments/{experiment_id}/threshold-sweep",
            f"{base}/threshold-sweep",
            _EXP,
            {"parameterName": "organism", "sweepType": "numeric", "values": ["1"]},
        ),
    )


def _gene_set_cases(owned: Owned) -> tuple[Case, ...]:
    first, second = owned.gene_set_ids
    base = f"/api/v1/gene-sets/{first}"
    return (
        Case("DELETE", "/api/v1/gene-sets/{gene_set_id}", base, _GS),
        Case(
            "POST",
            "/api/v1/gene-sets/{gene_set_id}/enrich",
            f"{base}/enrich",
            _GS,
            {"enrichmentTypes": ["go_function"]},
        ),
        Case(
            "POST",
            "/api/v1/gene-sets/{gene_set_id}/export",
            f"{base}/export",
            _GS,
        ),
        Case(
            "POST",
            "/api/v1/gene-sets/{gene_set_id}/results/record",
            f"{base}/results/record",
            _GS,
            _PRIMARY_KEY,
        ),
        Case(
            "POST",
            "/api/v1/gene-sets/{gene_set_id}/retake",
            f"{base}/retake",
            _GS,
        ),
        Case(
            "POST",
            "/api/v1/gene-sets/{gene_set_id}/vdi-publication",
            f"{base}/vdi-publication",
            _GS,
            {"name": "stolen set"},
        ),
        Case(
            "POST",
            "/api/v1/gene-sets/ensemble",
            "/api/v1/gene-sets/ensemble",
            _GS,
            {"geneSetIds": [first, second], "positiveControls": [GENE_IDS[0]]},
        ),
        Case(
            "POST",
            "/api/v1/gene-sets/operations",
            "/api/v1/gene-sets/operations",
            _GS,
            {
                "setAId": first,
                "setBId": second,
                "operation": "union",
                "name": "stolen union",
            },
        ),
        Case(
            "POST",
            "/api/v1/experiments",
            "/api/v1/experiments",
            _GS,
            _experiment_body(first),
        ),
        Case(
            "POST",
            "/api/v1/experiments/batch",
            "/api/v1/experiments/batch",
            _GS,
            {
                "base": _experiment_body(first),
                "organismParamName": "organism",
                "targetOrganisms": [{"organism": _ORGANISM}],
            },
        ),
        Case(
            "POST",
            "/api/v1/experiments/benchmark",
            "/api/v1/experiments/benchmark",
            _GS,
            {
                "base": _experiment_body(first),
                "controlSets": [
                    {
                        "label": "primary",
                        "positiveControls": [GENE_IDS[0]],
                        "negativeControls": [GENE_IDS[1]],
                        "isPrimary": True,
                    },
                ],
            },
        ),
    )


def cases(owned: Owned) -> tuple[Case, ...]:
    memory = f"/api/v1/memories/{owned.memory_key}?kind={MEMORY_KIND}"
    return (
        *_conversation_cases(owned),
        *_experiment_cases(owned),
        *_gene_set_cases(owned),
        Case(
            "PATCH",
            "/api/v1/memories/{key}",
            memory,
            _MEM,
            {"name": "renamed by an intruder"},
        ),
        Case("DELETE", "/api/v1/memories/{key}", memory, _MEM),
    )
