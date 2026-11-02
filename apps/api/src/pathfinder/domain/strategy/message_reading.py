"""Whether a researcher's message adds an alternative to what it already finds."""

from __future__ import annotations

import re

# An "include" verb adds an alternative to what the request already finds.
_ADDS_AN_ALTERNATIVE_RE = re.compile(
    r"\balso\s+include|\bto\s+include\b|(?:^|[,;.]\s*)include\b"
    r"|\bas\s+an?\s+alternative\b",
    re.IGNORECASE,
)


def adds_an_alternative(text: str) -> bool:
    """Whether the text adds an alternative with an "include" verb."""
    return bool(_ADDS_AN_ALTERNATIVE_RE.search(text))
