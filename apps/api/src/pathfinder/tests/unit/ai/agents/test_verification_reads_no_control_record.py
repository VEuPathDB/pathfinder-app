"""VERIFY spends its record reads on the sampled genes, never on a control."""

from __future__ import annotations

from pathfinder.ai.agents.verification import _VERIFICATION_INSTRUCTIONS


def test_a_control_genes_record_is_not_read() -> None:
    assert (
        "Never read a control gene's record: a control test reads the saved set "
        "by its id."
    ) in " ".join(_VERIFICATION_INSTRUCTIONS.split())
