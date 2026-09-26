"""The one rule every agent that writes text a researcher reads must follow.

Leaf module, so any instruction module can import it.
"""

from __future__ import annotations

USER_FACING_VOCABULARY = """\

## Vocabulary the researcher reads

Never write EDA, WDK, FRAME, BUILD, VERIFY, sub-agent, Ledger, Operational Spec, or a \
``DS_``/``ENT_``/``VAR_`` id in any text the researcher can read: your prose, a question you \
ask the user, a result summary, a spec summary, and a digest's prose, key findings and \
reason. Write study, search, strategy, step, sample, gene and plan instead, and name the \
site VEuPathDB or the site the researcher is on. A step id is the researcher's own step, so \
"step 3" reads well and "WDK step 440186113" does not. These words are yours for reading tool \
results and calling tools; they are never words the researcher reads.
"""


def with_vocabulary(instructions: str) -> str:
    """The instructions, followed by the rule for text a researcher reads."""
    return instructions + USER_FACING_VOCABULARY
