from __future__ import annotations

import pytest
from pydantic_ai.usage import UsageLimits

from strategist.assistants.audit import spec


def auditor_stops_after(monkeypatch: pytest.MonkeyPatch, calls: int) -> None:
    monkeypatch.setattr(
        spec,
        "AUDITOR_LIMITS",
        UsageLimits(request_limit=calls, tool_calls_limit=calls),
    )
