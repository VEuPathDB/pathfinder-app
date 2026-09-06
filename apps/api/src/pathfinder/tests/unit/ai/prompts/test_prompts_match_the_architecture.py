"""The prompts are the model's only description of its own architecture.

A prompt naming a sub-agent or an output schema that no longer exists is not
a documentation problem: the model is instructed to return a schema it cannot
return, and to expect dispatches that cannot happen. These tests fail when
prose and code drift apart, which is how FRAME/BUILD/VERIFY left `scoping`,
`discovery` and `planning` behind in the base prompt.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from pathfinder.ai.lead import deltas
from pathfinder.ai.lead.ledger_sections import SubAgentName

_PROMPTS = Path(deltas.__file__).parents[1] / "prompts"

# Named in prose as illustrations of the contract, not as dispatchable roles.
_NON_ROLE_WORDS = frozenset({"lead"})


def _prompt_files() -> list[Path]:
    return sorted(_PROMPTS.rglob("*.md"))


def _mentioned_schemas(text: str) -> set[str]:
    return set(re.findall(r"\b(\w+(?:Delta|Result))\b", text))


def test_there_are_prompts_to_check() -> None:
    assert _prompt_files(), f"no prompt markdown found under {_PROMPTS}"


def test_every_schema_named_in_a_prompt_exists() -> None:
    known = {name for name in dir(deltas) if not name.startswith("_")}
    # Schemas owned elsewhere but legitimately named in prompts.
    known |= {"LeadResponse", "ToolReturn", "FrameResult"}

    missing: dict[str, set[str]] = {}
    for path in _prompt_files():
        unknown = _mentioned_schemas(path.read_text()) - known
        if unknown:
            missing[path.name] = unknown

    assert missing == {}, (
        f"prompts name output schemas that do not exist: {missing}. "
        "The model is being told to return a type it cannot return."
    )


def test_no_prompt_names_a_deleted_sub_agent() -> None:
    """Only role references count, not the English words.

    "Search Discovery" as a capability label is fine and stays; "the
    discovery agent" or "the planning phase" describes a dispatch that
    cannot happen. Matching whole words alone flagged the former, and a
    test that forces correct prose to change is a bad test.
    """
    roles = set(get_args(SubAgentName)) | _NON_ROLE_WORDS
    retired = {"scoping", "discovery", "planning"} - roles
    role_reference = re.compile(
        r"\b(?:the\s+)?(" + "|".join(retired) + r")[- ](?:sub-)?(?:agent|phase|node)\b"
        r"|\b(?:sub-)?agents?\s*\([^)]*\b(" + "|".join(retired) + r")\b",
    )

    offenders: dict[str, set[str]] = {}
    for path in _prompt_files():
        named = {
            m
            for hit in role_reference.findall(path.read_text().casefold())
            for m in hit
            if m
        }
        if named:
            offenders[path.name] = named

    assert offenders == {}, (
        f"prompts still name retired sub-agents as roles: {offenders}. "
        "FRAME does scoping, discovery and planning in one pass."
    )
