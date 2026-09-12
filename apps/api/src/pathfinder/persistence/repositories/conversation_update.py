"""The partial update payload for a conversation and its strategy row."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from veupathdb.domain.strategy import StrategyAst

__all__ = ["ConversationUpdate", "collect_strategy_values"]


@dataclass
class ConversationUpdate:
    """Partial update payload for a conversation and its strategy projection.

    Only non-None fields are written. A ``*_set=True`` flag writes its field
    even when the value is ``None``.
    """

    name: str | None = None
    record_type: str | None = None
    wdk_strategy_id: int | None = None
    wdk_strategy_id_set: bool = False
    is_saved: bool | None = None
    is_saved_set: bool = False
    strategy_ast: StrategyAst | None = None
    step_count: int | None = None
    estimated_size: int | None = None
    estimated_size_set: bool = False
    gene_set_id: str | None = None
    gene_set_id_set: bool = False
    gene_set_auto_imported: bool | None = None
    imported_saved_strategy_ids: list[int] | None = None
    touch_updated_at: bool = True


_SIMPLE_FIELDS: tuple[str, ...] = (
    "record_type",
    "step_count",
    "gene_set_auto_imported",
)

_FLAGGED_FIELDS: tuple[tuple[str, str], ...] = (
    ("wdk_strategy_id_set", "wdk_strategy_id"),
    ("estimated_size_set", "estimated_size"),
    ("gene_set_id_set", "gene_set_id"),
    ("is_saved_set", "is_saved"),
)


def collect_strategy_values(upd: ConversationUpdate) -> dict[str, Any]:
    """Build the ``conversation_strategies`` column-value dict."""
    values: dict[str, Any] = {}

    for attr in _SIMPLE_FIELDS:
        val = getattr(upd, attr)
        if val is not None:
            values[attr] = val

    if upd.strategy_ast is not None:
        values["strategy_ast"] = upd.strategy_ast.model_dump(
            by_alias=True, exclude_none=True, mode="json"
        )

    if upd.imported_saved_strategy_ids is not None:
        values["imported_saved_strategy_ids"] = list(upd.imported_saved_strategy_ids)

    for flag, attr in _FLAGGED_FIELDS:
        if getattr(upd, flag):
            values[attr] = getattr(upd, attr)

    return values
