"""Whether a reply counts a strategy's steps in the noun the site counts them in."""

from __future__ import annotations

from veupathdb.domain.strategy import StrategyAst

from pathfinder.ai.lead.reply_claims import counts_in_the_wrong_unit


def counts_in_genes(reply_text: str, ast: StrategyAst) -> bool:
    """Whether the reply names no count of the strategy's steps in the record
    type, where the site counts that record type in another noun."""
    held = (ast.step_counts or {}).values()
    return not counts_in_the_wrong_unit(reply_text, ast.record_type, held)


__all__ = ["counts_in_genes"]
