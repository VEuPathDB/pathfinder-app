"""The partial update payload for a conversation and its strategy row."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from veupathdb.domain.strategy import StrategyAst

from strategist.domain.strategy.generated_name import NameSeed

__all__ = ["ConversationUpdate"]


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
    wdk_strategy_created_here: bool | None = None
    is_saved: bool | None = None
    strategy_ast: StrategyAst | None = None
    step_count: int | None = None
    estimated_size: int | None = None
    estimated_size_set: bool = False
    gene_set_id: str | None = None
    gene_set_id_set: bool = False
    gene_set_auto_imported: bool | None = None
    imported_saved_strategy_ids: list[int] | None = None
    generated_name_seed: NameSeed | None = None
    generated_name_seed_set: bool = False
    touch_updated_at: bool = True

    def strategy_values(self) -> dict[str, Any]:
        simple: dict[str, Any] = {
            "record_type": self.record_type,
            "wdk_strategy_created_here": self.wdk_strategy_created_here,
            "is_saved": self.is_saved,
            "step_count": self.step_count,
            "gene_set_auto_imported": self.gene_set_auto_imported,
            "strategy_ast": None
            if self.strategy_ast is None
            else self.strategy_ast.model_dump(
                by_alias=True, exclude_none=True, mode="json"
            ),
            "imported_saved_strategy_ids": None
            if self.imported_saved_strategy_ids is None
            else list(self.imported_saved_strategy_ids),
        }
        flagged: dict[str, tuple[bool, Any]] = {
            "wdk_strategy_id": (self.wdk_strategy_id_set, self.wdk_strategy_id),
            "estimated_size": (self.estimated_size_set, self.estimated_size),
            "gene_set_id": (self.gene_set_id_set, self.gene_set_id),
            "generated_name_seed": (
                self.generated_name_seed_set,
                self.generated_name_seed,
            ),
        }
        return {name: v for name, v in simple.items() if v is not None} | {
            name: v for name, (written, v) in flagged.items() if written
        }
