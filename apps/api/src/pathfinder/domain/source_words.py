from __future__ import annotations

from pathfinder.domain.strategy.operational_spec import ValueSource
from pathfinder.domain.turn_facts import ParameterFact, TurnFacts

SOURCE_WORDS: dict[ValueSource, str] = {
    "stated": "you stated",
    "card": "your answer on a card",
    "default": "the site's default",
    "chosen": "chosen",
    "held": "held by the strategy",
}


def parameter_of(facts: TurnFacts, body: str) -> ParameterFact | None:
    step_id, _, name = body.partition(".")
    step = facts.step(step_id)
    if step is None:
        return None
    return next((p for p in step.parameters if p.name == name), None)


__all__ = ["SOURCE_WORDS", "parameter_of"]
