"""The arc token a test message carries, and the arc it names.

A token that is nearly right fails: a misspelt spec must never play the echo.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

ECHO = "echo"

# Anything shaped like a token is read, so a malformed one can be refused.
_LOOSE = re.compile(r"\[\[\s*(arc|fault)\s*:([^\]]*)\]\]", re.IGNORECASE)
_NAME = re.compile(r"[a-z0-9-]+")
# A message the product writes for the researcher carries no token, so its
# whole text names its arc.
_PRODUCT_MESSAGES = {
    "Clear the current strategy by calling clear_strategy with confirm=true.": "clear",
}


class MalformedTokenError(ValueError):
    """A message carries a token the mock cannot read as one arc and one fault."""


class ArcDirective(BaseModel):
    """The arc a message asks the mock to play, and the fault it injects."""

    model_config = ConfigDict(frozen=True)

    arc: str = ECHO
    fault: str | None = None


def _names(text: str, kind: str) -> list[str]:
    """Every name one kind of token carries, each checked for its exact form."""
    names: list[str] = []
    for found in _LOOSE.finditer(text):
        if found.group(1).lower() != kind:
            continue
        name = found.group(2)
        if found.group(0) != f"[[{kind}:{name}]]" or _NAME.fullmatch(name) is None:
            msg = f"{found.group(0)!r} is no {kind} token; write [[{kind}:<name>]]"
            raise MalformedTokenError(msg)
        names.append(name)
    if len(names) > 1:
        msg = f"A message names one {kind}, and this one names {names}"
        raise MalformedTokenError(msg)
    return names


def directive_of(text: str) -> ArcDirective:
    """The arc and fault the tokens name, else the arc a product message
    names, else the echo."""
    arcs = _names(text, "arc")
    faults = _names(text, "fault")
    if faults and not arcs:
        msg = f"The fault {faults[0]!r} names no arc to play it in"
        raise MalformedTokenError(msg)
    if not arcs:
        return ArcDirective(arc=_PRODUCT_MESSAGES.get(text.strip(), ECHO))
    return ArcDirective(arc=arcs[0], fault=faults[0] if faults else None)


def without_tokens(text: str) -> str:
    """The text a researcher wrote, with the tokens taken out."""
    return _LOOSE.sub("", text).strip()
