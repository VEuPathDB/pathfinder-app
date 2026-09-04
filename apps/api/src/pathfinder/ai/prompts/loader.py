"""Prompt loading helpers for the AI agent."""

from functools import lru_cache

from pathfinder.platform.langfuse.prompts import load_prompt_result


@lru_cache(maxsize=2)
def load_system_prompt(*, include_site_hints: bool = True) -> str:
    """Load and combine the unified system prompt.

    :param include_site_hints: When False, skip site_hints.md to save ~400
        tokens on continuation turns where the model already has site context.
    """
    parts = [
        load_prompt_result("system"),
        load_prompt_result("safety"),
    ]
    if include_site_hints:
        parts.append(load_prompt_result("site-hints"))
    return "\n\n---\n\n".join(prompt.text for prompt in parts)
