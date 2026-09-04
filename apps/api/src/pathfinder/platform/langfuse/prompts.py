"""Loads agent prompts from Langfuse, and falls back to local files.

Local files also seed Langfuse with any prompt it does not hold yet.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import langfuse.api
from assistant_core.platform.logging import get_logger
from langfuse.api.commons import errors as langfuse_errors

from pathfinder.platform.langfuse.client import get_langfuse

logger = get_logger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parents[2] / "ai" / "prompts"

PromptSource = Literal["langfuse", "local"]


@dataclass(frozen=True)
class LoadedPrompt:
    """Resolved prompt text plus the metadata Langfuse exposes for it."""

    name: str
    text: str
    label: str
    source: PromptSource
    version: int | None = None


_LOCAL_FILES: dict[str, str] = {
    "system": "system.md",
    "safety": "safety.md",
    "site-hints": "site_hints.md",
}

# The Langfuse SDK raises error classes from more than one namespace.
# All of them are recoverable: prompt loading falls back to local files.
_LANGFUSE_ERRORS = (
    langfuse.api.Error,
    langfuse_errors.Error,
    langfuse_errors.NotFoundError,
    langfuse_errors.UnauthorizedError,
    langfuse_errors.AccessDeniedError,
    langfuse_errors.MethodNotAllowedError,
    ValueError,
    OSError,
)


def _load_local(name: str, *, label: str) -> LoadedPrompt:
    """Load a prompt from the local filesystem."""
    try:
        filename = _LOCAL_FILES[name]
    except KeyError:
        msg = f"Unknown prompt name: {name!r}. Known: {sorted(_LOCAL_FILES)}"
        raise ValueError(msg) from None
    path = _PROMPTS_DIR / filename
    return LoadedPrompt(
        name=name,
        text=path.read_text(),
        label=label,
        source="local",
    )


def load_prompt_result(name: str, *, label: str = "production") -> LoadedPrompt:
    """Load a prompt with its source and version metadata."""
    client = get_langfuse()
    if client is not None:
        try:
            prompt = client.get_prompt(name, label=label)
        except langfuse_errors.NotFoundError:
            logger.info(
                "Langfuse prompt not found, falling back to local",
                name=name,
                label=label,
            )
        except _LANGFUSE_ERRORS:
            logger.warning(
                "Langfuse prompt fetch failed, falling back to local",
                name=name,
                exc_info=True,
            )
        else:
            text: str = prompt.compile()
            logger.debug("Prompt loaded from Langfuse", name=name, label=label)
            return LoadedPrompt(
                name=name,
                text=text,
                label=label,
                source="langfuse",
                version=getattr(prompt, "version", None),
            )

    loaded = _load_local(name, label=label)
    logger.debug("Prompt loaded from local file", name=name)
    return loaded


def seed_prompts() -> None:
    """Upload each local prompt file that Langfuse does not hold yet."""
    client = get_langfuse()
    if client is None:
        return

    for name, filename in _LOCAL_FILES.items():
        try:
            client.get_prompt(name)
        except langfuse_errors.NotFoundError:
            text = (_PROMPTS_DIR / filename).read_text()
            try:
                client.create_prompt(
                    name=name,
                    prompt=text,
                    type="text",
                    labels=["production"],
                )
                logger.info("Seeded prompt to Langfuse", name=name)
            except _LANGFUSE_ERRORS:
                logger.warning("Failed to seed prompt", name=name, exc_info=True)
        except _LANGFUSE_ERRORS:
            logger.warning(
                "Langfuse prompt existence check failed; skipping seed",
                name=name,
                exc_info=True,
            )
        else:
            logger.debug("Prompt already exists in Langfuse", name=name)
