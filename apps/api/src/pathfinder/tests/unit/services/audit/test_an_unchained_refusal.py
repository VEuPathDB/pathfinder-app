from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from pathfinder.domain.audit.scope import SingleGeneTarget
from pathfinder.services.audit import checks
from pathfinder.services.audit.checks import DeclinedCheck, confirm_target
from pathfinder.services.audit.units import UnitFailure


def _raising(kind: str) -> ToolError:
    error = ToolError("the check's words")
    underneath = ValueError("underneath")
    error.__context__ = underneath
    if kind == "cut":
        error.__suppress_context__ = True
    if kind == "chained":
        error.__cause__ = underneath
    return error


@pytest.mark.parametrize(
    ("kind", "unchained"), [("cut", True), ("chained", False), ("bare", False)]
)
def test_a_tool_error_is_unchained_only_with_nothing_shown_under_it(
    kind: str, unchained: bool
) -> None:
    assert checks.is_unchained(_raising(kind)) is unchained
    assert checks.is_unchained(ToolError("alone")) is True


@pytest.mark.parametrize(
    ("kind", "found"),
    [
        ("cut", DeclinedCheck(message="the check's words")),
        ("chained", UnitFailure(status="failed", message="the check failed")),
        ("bare", UnitFailure(status="failed", message="the check failed")),
    ],
)
async def test_a_confirmation_declines_only_an_unchained_refusal(
    monkeypatch: pytest.MonkeyPatch, kind: str, found: object
) -> None:
    async def tool(site_id: str, gene: str) -> object:
        raise _raising(kind)

    monkeypatch.setattr(checks, "audit_gene_length", tool)

    assert (
        await confirm_target(
            "plasmodb", SingleGeneTarget(check="gene_length", genes=("X",))
        )
        == found
    )
