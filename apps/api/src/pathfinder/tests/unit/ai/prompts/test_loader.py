"""The unified system prompt is the three prompt files joined in order."""

from pathlib import Path

from pathfinder.ai.prompts.loader import load_system_prompt

_PROMPTS = Path(__file__).resolve().parents[4] / "ai" / "prompts"
_SEPARATOR = "\n\n---\n\n"


def _read(name: str) -> str:
    return (_PROMPTS / name).read_text()


def test_the_bundle_joins_system_safety_and_site_hints() -> None:
    load_system_prompt.cache_clear()

    assert load_system_prompt(include_site_hints=True) == _SEPARATOR.join(
        [_read("system.md"), _read("safety.md"), _read("site_hints.md")]
    )


def test_a_continuation_turn_drops_the_site_hints() -> None:
    load_system_prompt.cache_clear()

    assert load_system_prompt(include_site_hints=False) == _SEPARATOR.join(
        [_read("system.md"), _read("safety.md")]
    )
