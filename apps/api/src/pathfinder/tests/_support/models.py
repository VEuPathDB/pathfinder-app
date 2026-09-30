"""The catalog ids tests use, read from the lineup so a refresh edits no test."""

from __future__ import annotations

from assistant_core.platform.types import ModelProvider

from pathfinder.platform.model_catalog import (
    DEFAULT_MODEL_ID,
    ModelRank,
    get_model_catalog,
    get_model_entry,
)


def lineup_id(provider: ModelProvider, rank: ModelRank) -> str:
    """The id of the provider's one entry at ``rank``."""
    (entry,) = (
        e for e in get_model_catalog() if e.provider == provider and e.rank == rank
    )
    return entry.id


DEFAULT_MODEL = DEFAULT_MODEL_ID
OPENAI_FLAGSHIP = lineup_id("openai", "flagship")
OPENAI_STANDARD = lineup_id("openai", "standard")
OPENAI_SMALL = lineup_id("openai", "small")
GOOGLE_FLAGSHIP = lineup_id("google", "flagship")
GOOGLE_STANDARD = lineup_id("google", "standard")
GOOGLE_SMALL = lineup_id("google", "small")
ANTHROPIC_SMALL = lineup_id("anthropic", "small")


def display_name(model_id: str) -> str:
    """The name the catalog shows for ``model_id``."""
    entry = get_model_entry(model_id)
    assert entry is not None, model_id
    return entry.name
