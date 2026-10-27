from __future__ import annotations

from pathfinder.domain.reply_references import FaultKind, ProseFault
from pathfinder.domain.turn_facts import TurnFacts

WITHHELD_ALONE = (
    "I could not write this answer in facts the product renders from the result, "
    "so it is not shown."
)
WITHHELD_REPLY = (
    f"{WITHHELD_ALONE} The facts beside this reply show what this turn found."
)
WITHHELD_FAULTS: frozenset[FaultKind] = frozenset(
    {
        "number",
        "identifier",
        "product_text",
        "unheld_reference",
        "keyed_reference",
        "misnamed_reference",
    }
)


def withholds(faults: list[ProseFault]) -> bool:
    return any(f.kind in WITHHELD_FAULTS for f in faults)


def withheld_prose(facts: TurnFacts) -> str:
    return WITHHELD_ALONE if facts.empty() else WITHHELD_REPLY
