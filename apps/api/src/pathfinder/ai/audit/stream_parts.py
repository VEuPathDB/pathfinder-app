"""The stream parts the audit tools emit."""

from __future__ import annotations

from assistant_core.conversation.stream_parts.registry import StreamPartRegistry

from pathfinder.domain.audit.planning import AuditStartCard


def register_audit_stream_parts(registry: StreamPartRegistry) -> None:
    registry.register("data-audit-start", AuditStartCard)
