"""Conversation-title generation using the provider's smallest model.

The title names the thread in the sidebar. It runs beside the turn, and the
turn runner writes it as `data-conversation-title`, the last chunk before
`finish`.
"""

from __future__ import annotations

import contextlib
import re

import httpx
from assistant_core.models.settings import build_model_settings
from assistant_core.platform.types import ModelProvider
from assistant_core.spec import MockModelFactory
from pydantic_ai import Agent
from pydantic_ai.exceptions import AgentRunError, UserError
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from pathfinder.ai.models.catalog import get_smallest_model
from pathfinder.platform.config import get_settings

MAX_TITLE_WORDS = 7
MAX_TITLE_CHARS = 60
_MIN_QUOTED_LEN = 2

_TITLE_INSTRUCTIONS = (
    "You produce conversation titles. Respond with ONLY the title, no "
    "quotes, no punctuation, no leading dash, no trailing period, no "
    "wrapping characters. Use Title Case. Use at most 7 words. Summarize "
    "the subject of the user's request, not the request itself. Examples:\n"
    "  User: Find genes in P. falciparum upregulated in liver stage\n"
    "  Title: Plasmodium Liver Stage Upregulated Genes\n"
    "  User: show me how toxo genes respond to IFN-gamma\n"
    "  Title: Toxoplasma Genes Under IFN-Gamma"
)

_TITLE_USAGE_LIMITS = UsageLimits(
    request_limit=1,
    total_tokens_limit=500,
)


def _fallback_title(user_message: str) -> str:
    """Produce a deterministic fallback when model generation fails.

    Takes the first `MAX_TITLE_CHARS` characters of the user message, stripped
    of whitespace. Better than showing "Untitled" in the sidebar.
    """
    cleaned = re.sub(r"\s+", " ", user_message.strip())
    if not cleaned:
        return "New conversation"
    if len(cleaned) <= MAX_TITLE_CHARS:
        return cleaned
    return cleaned[: MAX_TITLE_CHARS - 1].rstrip() + "\u2026"


def _trim_title(raw: str) -> str:
    """Normalize a model-produced title to our formatting rules.

    - Strip surrounding whitespace and matched outer quote characters.
    - Drop any trailing punctuation.
    - Collapse internal whitespace runs to single spaces.
    - Truncate to `MAX_TITLE_WORDS` words.
    - Truncate to `MAX_TITLE_CHARS` characters with an ellipsis suffix.
    """
    title = raw.strip()
    # Strip outer matching quotes/backticks/angle brackets (a few iterations
    # in case the model nested them).
    for _ in range(3):
        if (
            len(title) >= _MIN_QUOTED_LEN
            and title[0] == title[-1]
            and title[0] in "\"'`"
        ):
            title = title[1:-1].strip()
        else:
            break
    title = re.sub(r"\s+", " ", title)
    title = title.rstrip(".!?,;:")
    words = title.split(" ")
    if len(words) > MAX_TITLE_WORDS:
        title = " ".join(words[:MAX_TITLE_WORDS])
    if len(title) > MAX_TITLE_CHARS:
        title = title[: MAX_TITLE_CHARS - 1].rstrip() + "\u2026"
    return title


async def generate_conversation_title(
    first_user_message: str,
    mock_model: MockModelFactory,
    provider: ModelProvider | None = None,
) -> str:
    """Generate a short conversation title from the user's first message.

    :param first_user_message: The text of the first user message.
    :param provider: Provider whose smallest model should be used. Defaults
        to the configured ``settings.default_provider``.
    :param mock_model: The assistant's test double, used when the chat
        provider is the mock one.
    :returns: A trimmed, formatted title of at most 7 words / 60 chars. If
        generation fails, returns a truncated-first-message fallback.
    """
    cleaned = first_user_message.strip()
    if not cleaned:
        return "New conversation"

    settings = get_settings()
    is_mock = settings.pathfinder_chat_provider.strip().lower() == "mock"
    resolved_provider: ModelProvider = provider or settings.default_provider
    try:
        entry = get_smallest_model(resolved_provider)
    except LookupError:
        if not is_mock:
            return _fallback_title(first_user_message)
        entry = None

    # ``entry`` is only None on the mock path above, so the fallback must be the
    # mock model, not a real provider id.
    title_model_id = entry.id if entry is not None else "mock:deterministic"
    agent: Agent[None, str] = Agent(
        title_model_id,
        output_type=str,
        instructions=_TITLE_INSTRUCTIONS,
        model_settings=build_model_settings(title_model_id),
        retries=1,
        name="conversation-title",
        defer_model_check=True,
    )

    override_ctx = (
        agent.override(model=mock_model())
        if is_mock and not isinstance(agent.model, FunctionModel)
        else contextlib.nullcontext()
    )
    try:
        with override_ctx:
            result = await agent.run(
                f"User's first message:\n{cleaned}",
                usage_limits=_TITLE_USAGE_LIMITS,
            )
    except AgentRunError, UserError, httpx.HTTPError, TimeoutError, OSError:
        return _fallback_title(first_user_message)

    return _trim_title(result.output) or _fallback_title(first_user_message)
