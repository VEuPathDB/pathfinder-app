"""Stand-ins for the catalog and WDK reads a strategy write makes."""

from __future__ import annotations

from typing import Any

import pytest
from veupathdb_mcp.catalog import ValidatedParams

from pathfinder.services.strategies import commit, stated_sides, step_wdk_push


async def accepts_every_value(*_args: Any, **kwargs: Any) -> ValidatedParams:
    """Answer a validation with the values as sent, in the catalog's shape."""
    return ValidatedParams(params=dict(kwargs["parameters"]), record_class="transcript")


async def no_plan_params(*_args: Any, **_kwargs: Any) -> set[str]:
    return set()


async def no_reconcile(*_args: Any, **_kwargs: Any) -> None:
    return None


def stub_every_catalog_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """A write reaches no catalog and no WDK: every read answers its input."""
    monkeypatch.setattr(step_wdk_push, "_validate_plan_params", no_plan_params)
    monkeypatch.setattr(stated_sides, "validate_parameters", accepts_every_value)
    monkeypatch.setattr(commit, "reconcile_sync_state_with_wdk", no_reconcile)
