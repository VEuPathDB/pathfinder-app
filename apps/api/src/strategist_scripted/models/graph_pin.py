"""The strategy graph a sub-agent's instructions pin, read back: the organism
the root's records belong to."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import TypeAdapter, ValidationError

_HEAD = "Current strategy graph ("
_STEP = re.compile(r"^(?P<id>[^\s:]+): (?P<body>.+)$")
_PRIMARY = re.compile(r"^[A-Z_]+\((?P<combined>[^,]+), |\binput=(?P<input>\S+)")
_ROOT = re.compile(r"-> (?:.*, )?root(?:,|$)")
_ORGANISM = re.compile(r"(?:^|, )organism=(?P<value>.*?)(?=, \w+=|$)")
# The pin cuts a long value and ends it with this mark.
_CUT = "..."
_TERMS = TypeAdapter(list[str])


@dataclass(frozen=True)
class _PinnedStep:
    primary: str | None
    organism: str | None
    root: bool


def _organism(params: str) -> str | None:
    """The first organism a parameter line sets, or the start of a cut one."""
    found = _ORGANISM.search(params)
    if found is None:
        return None
    value = found["value"]
    if value.endswith(_CUT):
        return value.removesuffix(_CUT).removeprefix('["')
    try:
        terms = _TERMS.validate_json(value)
    except ValidationError:
        return value
    return terms[0] if terms else None


def _steps(instructions: str) -> dict[str, _PinnedStep]:
    lines = instructions.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith(_HEAD)), None)
    if start is None:
        return {}
    steps: dict[str, _PinnedStep] = {}
    for at, line in enumerate(lines[start + 1 :], start + 1):
        if line.startswith("#"):
            break
        header = _STEP.match(line)
        if header is None:
            continue
        body = header["body"]
        primary = _PRIMARY.search(body)
        params = lines[at + 1] if at + 1 < len(lines) else ""
        steps[header["id"]] = _PinnedStep(
            primary=None
            if primary is None
            else primary["combined"] or primary["input"],
            organism=_organism(params.strip()) if params.startswith("  ") else None,
            root=_ROOT.search(body) is not None,
        )
    return steps


def pinned_root_organism(instructions: str) -> str | None:
    """The organism the pinned root's records belong to: the nearest organism
    down its primary inputs, where a transform states its target. A value the
    pin cuts is its first characters."""
    steps = _steps(instructions)
    step = next((s for s in steps.values() if s.root), None)
    while step is not None:
        if step.organism is not None:
            return step.organism
        step = steps.get(step.primary or "")
    return None
