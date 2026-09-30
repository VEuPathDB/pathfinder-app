"""Each provider's tiers follow from the ranks its catalog entries carry."""

from __future__ import annotations

import pytest
from assistant_core.platform.types import ModelProvider, ReasoningEffort, TierName

from pathfinder.platform.model_catalog import ModelEntry, get_model_catalog
from pathfinder.platform.tiers import derive_tiers

type Table = dict[
    TierName, tuple[tuple[str, ReasoningEffort], tuple[str, ReasoningEffort]]
]


def _table(provider: ModelProvider, entries: tuple[ModelEntry, ...]) -> Table:
    return {
        name: (
            (tier.thinker.model_id, tier.thinker.reasoning_effort),
            (tier.worker.model_id, tier.worker.reasoning_effort),
        )
        for name, tier in derive_tiers(entries, provider).items()
    }


# The decided lineup; a refresh of the catalog edits this table.
_DECIDED: dict[ModelProvider, Table] = {
    "openai": {
        "quality": (("openai:gpt-6-sol", "high"), ("openai:gpt-5.6-luna", "medium")),
        "balanced": (
            ("openai:gpt-5.6-luna", "medium"),
            ("openai:gpt-6-luna", "medium"),
        ),
        "default": (
            ("openai:gpt-5.6-luna", "medium"),
            ("openai:gpt-6-luna", "medium"),
        ),
        "fast": (("openai:gpt-6-luna", "low"), ("openai:gpt-6-luna", "low")),
    },
    "google": {
        "quality": (
            ("google:gemini-3.1-pro-preview", "high"),
            ("google:gemini-3.8-flash", "medium"),
        ),
        "balanced": (
            ("google:gemini-3.8-flash", "medium"),
            ("google:gemini-3.5-flash-lite", "medium"),
        ),
        "default": (
            ("google:gemini-3.8-flash", "medium"),
            ("google:gemini-3.5-flash-lite", "medium"),
        ),
        "fast": (
            ("google:gemini-3.5-flash-lite", "low"),
            ("google:gemini-3.5-flash-lite", "low"),
        ),
    },
    "anthropic": {
        "quality": (
            ("anthropic:claude-haiku-4-5", "high"),
            ("anthropic:claude-haiku-4-5", "high"),
        ),
        "balanced": (
            ("anthropic:claude-haiku-4-5", "medium"),
            ("anthropic:claude-haiku-4-5", "medium"),
        ),
        "default": (
            ("anthropic:claude-haiku-4-5", "medium"),
            ("anthropic:claude-haiku-4-5", "medium"),
        ),
        "fast": (
            ("anthropic:claude-haiku-4-5", "low"),
            ("anthropic:claude-haiku-4-5", "low"),
        ),
    },
}


@pytest.mark.parametrize("provider", sorted(_DECIDED))
def test_the_catalog_derives_the_decided_tiers(provider: ModelProvider) -> None:
    assert _table(provider, get_model_catalog()) == _DECIDED[provider]


def test_a_missing_rank_takes_the_next_one_down() -> None:
    """A lineup without a standard entry runs the balanced thinker on the small."""
    entries = (
        ModelEntry.entry(
            id="openai:big", name="Big", rank="flagship", is_provider_default=True
        ),
        ModelEntry.entry(id="openai:tiny", name="Tiny", rank="small"),
    )

    assert _table("openai", entries) == {
        "quality": (("openai:big", "high"), ("openai:tiny", "medium")),
        "balanced": (("openai:tiny", "medium"), ("openai:tiny", "medium")),
        "default": (("openai:big", "medium"), ("openai:tiny", "medium")),
        "fast": (("openai:tiny", "low"), ("openai:tiny", "low")),
    }


def test_a_provider_without_a_default_entry_is_refused() -> None:
    entries = (ModelEntry.entry(id="openai:tiny", name="Tiny", rank="small"),)

    with pytest.raises(ValueError, match="0 default"):
        derive_tiers(entries, "openai")


def test_two_entries_at_one_rank_are_refused() -> None:
    entries = (
        ModelEntry.entry(
            id="openai:a", name="A", rank="small", is_provider_default=True
        ),
        ModelEntry.entry(id="openai:b", name="B", rank="small"),
    )

    with pytest.raises(ValueError, match="twice"):
        derive_tiers(entries, "openai")
