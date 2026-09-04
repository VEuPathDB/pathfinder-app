"""The unified system prompt is the three components joined in order."""

from unittest.mock import patch

from pathfinder.ai.prompts.loader import load_system_prompt
from pathfinder.platform.langfuse.prompts import LoadedPrompt

_PROMPTS = {
    "system": LoadedPrompt(
        name="system",
        text="system prompt",
        label="production",
        source="langfuse",
        version=2,
    ),
    "safety": LoadedPrompt(
        name="safety",
        text="safety prompt",
        label="production",
        source="local",
    ),
    "site-hints": LoadedPrompt(
        name="site-hints",
        text="site hints",
        label="production",
        source="langfuse",
        version=4,
    ),
}


def _load(*, include_site_hints: bool) -> str:
    load_system_prompt.cache_clear()
    with patch(
        "pathfinder.ai.prompts.loader.load_prompt_result",
        side_effect=lambda name: _PROMPTS[name],
    ):
        return load_system_prompt(include_site_hints=include_site_hints)


def test_the_bundle_joins_system_safety_and_site_hints() -> None:
    assert _load(include_site_hints=True) == (
        "system prompt\n\n---\n\nsafety prompt\n\n---\n\nsite hints"
    )


def test_a_continuation_turn_drops_the_site_hints() -> None:
    assert _load(include_site_hints=False) == "system prompt\n\n---\n\nsafety prompt"
