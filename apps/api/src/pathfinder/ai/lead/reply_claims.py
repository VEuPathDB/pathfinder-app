"""What a reply's prose claims, the references it cites, and the internal
names it must not print.

Pure text reading. The turn contract joins these readings to the record of the
turn; nothing here knows what the turn did.
"""

from __future__ import annotations

import re

from pathfinder.ai.lead.proposal import PROPOSAL_TOOL
from pathfinder.ai.lead.sub_agent_tools import TOOL_TO_PHASE_ROLE
from pathfinder.domain.strategy.step_rationale import names_the_phrase

# An artifact the reply reports as saved. An offer to save one is an
# infinitive, and a listing says "saved control sets" with no words between.
_SAVED = r"\b(?:created|saved|built|made|added|stored)\s+.{1,40}?\b"
# A gene set that qualifies another noun names an analysis or a note.
_THE_SET_ITSELF = r"(?!\s+(?:enrichment|note))"
SAVED_A_CONTROL_SET = re.compile(_SAVED + r"control sets?\b")
SAVED_A_GENE_SET = re.compile(_SAVED + r"gene sets?\b" + _THE_SET_ITSELF)
_CLAUSE_END = re.compile(r"[.!?;\n]")

# A clause that takes its own claim back. The second form is the report of a
# failure: the act was attempted and something turned it down.
_DENIAL_WORD = r"\b(?:not|never|no|none|nothing|cannot)\b|n't"
_DENIED_BY_A_FAILURE = (
    r"\bbut\b.{0,80}?"
    r"\b(?:refused|rejected|declined|failed|stopped|would not|could not)\b"
)
_DENIED = re.compile(f"{_DENIAL_WORD}|{_DENIED_BY_A_FAILURE}")

# A criterion the reply reports as framed. The claim is the act; naming what
# the plan holds is a description, and "the added filter" qualifies a noun.
_FRAMED = r"(?<!the )\b(?:framed|planned|added)\s+"
_A_CRITERION = r".{0,40}?\b(?:criterion|criteria|filter)\b"
_TO_THE_PLAN = r".{0,60}?\bto the (?:plan|spec)\b"
CLAIMED_A_FRAME = re.compile(_FRAMED + f"(?:{_A_CRITERION}|{_TO_THE_PLAN})")

# The tools a reply can name by their identifier. Every one carries an
# underscore, so the plain words for the same act read as ordinary prose.
TOOL_IDENTIFIERS: frozenset[str] = frozenset(TOOL_TO_PHASE_ROLE) | {
    "build_strategy",
    "clear_strategy",
    "consult_user",
    "delete_step",
    PROPOSAL_TOOL,
    "save_gene_set",
}

# A step id the graph mints, and the error strings a reply can copy out of a
# refusal. None of them names anything the researcher can act on. A status code
# is read only after the word that makes it one, or before the word that does,
# because a number in this range is a gene count in ordinary prose.
_A_STEP_ID = re.compile(r"\bstep_[0-9a-f]{8}\b")
_STATUS = r"[45]\d\d"
_AN_ERROR_STRING = re.compile(
    r"\bmodelretry\b"
    rf"|\b(?:http|status|code|error)\s+{_STATUS}\b"
    rf"|\b{_STATUS}\s+(?:error|response|status)\b"
)


def claims(prose: str, made: re.Pattern[str]) -> bool:
    """Whether an undenied clause of this reply makes that claim."""
    return any(
        made.search(clause)
        for clause in _CLAUSE_END.split(prose.casefold())
        if not _DENIED.search(clause)
    )


def names_an_organism(prose: str, organism: str) -> bool:
    """Whether the prose names the organism in full or with its genus abbreviated."""
    genus, _, rest = organism.partition(" ")
    abbreviated = f"{genus[:1]}. {rest}" if rest else organism
    return names_the_phrase(prose, organism) or names_the_phrase(prose, abbreviated)


def machine_words(prose: str) -> list[str]:
    """Every internal name this reply prints, in the order they are looked for.

    A tool name, a minted step id and an error string are the three the user
    holds no use for.
    """
    text = prose.casefold()
    found = sorted(name for name in TOOL_IDENTIFIERS if name in text)
    found.extend(sorted(set(_A_STEP_ID.findall(text))))
    found.extend(sorted(set(_AN_ERROR_STRING.findall(text))))
    return found


# What may close a question after its mark: whitespace, emphasis, code, a
# bracket or a quote.
_CLOSING_MARKS = " \t\r\n*_`)]\"'"


def ends_with_a_question(prose: str) -> bool:
    """Whether the last non-empty paragraph of the prose ends with ``?``.

    Marks that close the sentence after its question mark are read through, so
    a bold or quoted question still ends the reply.
    """
    return prose.rstrip(_CLOSING_MARKS).endswith("?")


def counts_named_as(prose: str, noun: str, *, instead_of: str) -> list[int]:
    """Every count the prose names with ``noun``, in order.

    A few words may stand between the count and the noun, as in "479
    Plasmodium falciparum 3D7 transcripts", but no other number and no
    ``instead_of``. A word holds a letter; a number holds none.
    """
    word = r"(?=[\w.-]*[A-Za-z])[\w][\w.-]*"
    between = rf"(?:(?!{re.escape(instead_of)}s?\b){word}\**\s+){{0,4}}?"
    named = re.compile(
        rf"\b(\d[\d,]*)\**\s+{between}\**{re.escape(noun)}s?\b", re.IGNORECASE
    )
    return [int(match.group(1).replace(",", "")) for match in named.finditer(prose)]
