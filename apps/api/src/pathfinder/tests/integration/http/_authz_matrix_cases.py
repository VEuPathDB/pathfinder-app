"""The requests the authorization matrix issues, and the resources they need."""

from __future__ import annotations

from pathfinder.tests.integration.http._authz_matrix_support import (
    CONVERSATION,
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
_GS = frozenset({GENE_SET.name})
_MEM = frozenset({MEMORY.name})


def _conversation_cases(owned: Owned) -> tuple[Case, ...]:
    conv = str(owned.conversation_id)
    base = f"/api/v1/conversations/{conv}"
    notes = f"{base}/scratchpad/notes/{owned.note_id}"
    rating = f"{base}/messages/{owned.reply_id}/rating"
    rating_route = (
        "/api/v1/conversations/{conversation_id}/messages/{message_id}/rating"
    )
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
        Case("PUT", rating_route, rating, _CONV, {"rating": "dislike"}),
        Case("DELETE", rating_route, rating, _CONV),
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


def _gene_set_cases(owned: Owned) -> tuple[Case, ...]:
    first = owned.gene_set_ids[0]
    base = f"/api/v1/gene-sets/{first}"
    return (
        Case("DELETE", "/api/v1/gene-sets/{gene_set_id}", base, _GS),
        Case(
            "POST",
            "/api/v1/gene-sets/{gene_set_id}/export",
            f"{base}/export",
            _GS,
        ),
        Case(
            "POST",
            "/api/v1/gene-sets/{gene_set_id}/vdi-publication",
            f"{base}/vdi-publication",
            _GS,
            {"name": "stolen set"},
        ),
    )


def cases(owned: Owned) -> tuple[Case, ...]:
    memory = f"/api/v1/memories/{owned.memory_key}?kind={MEMORY_KIND}"
    return (
        *_conversation_cases(owned),
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
