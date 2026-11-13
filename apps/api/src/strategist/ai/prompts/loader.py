"""The base system prompt every strategy agent reads, from the files beside this module."""

from functools import lru_cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).resolve().parent


def _read(filename: str) -> str:
    return (_PROMPTS_DIR / filename).read_text()


@lru_cache(maxsize=2)
def load_system_prompt(*, include_site_hints: bool = True) -> str:
    """The system, safety and site-hint prompts joined in that order.

    :param include_site_hints: When False, the site hints are left out.
    """
    parts = [_read("system.md"), _read("safety.md")]
    if include_site_hints:
        parts.append(_read("site_hints.md"))
    return "\n\n---\n\n".join(parts)


@lru_cache(maxsize=1)
def load_reading_guide() -> str:
    return _read("message_reading.md")


@lru_cache(maxsize=1)
def load_request_guide() -> str:
    return _read("stated_request.md")
