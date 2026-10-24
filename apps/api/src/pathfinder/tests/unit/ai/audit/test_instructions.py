from __future__ import annotations

from pathfinder.ai.audit.instructions import (
    AUDITOR_INSTRUCTIONS,
    INVESTIGATOR_INSTRUCTIONS,
    JUDGING_RULES,
    REVIEWER_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
)
from pathfinder.ai.lead.card_reply import REPLY_REFERENCES

_TRAPS = (
    "a correct reference with a signal peptide",
    "a deliberately curated fusion",
    "a genuine pseudogene",
    "a truncated product name",
    "the CTG serine codon of the Candida clade",
)
_SERVED_EVIDENCE = (
    "PdbSimilarities",
    "AlphaFoldLinkouts",
    "MassSpec",
    "GeneLinkouts",
    "Seqedits",
    "transcriptomics",
    "phenotype screens",
)
_ROLES = (
    INVESTIGATOR_INSTRUCTIONS,
    AUDITOR_INSTRUCTIONS,
    REVIEWER_INSTRUCTIONS,
    SYNTHESIS_INSTRUCTIONS,
)


def test_the_judging_rules_name_every_trap_of_the_design() -> None:
    assert [trap for trap in _TRAPS if trap not in JUDGING_RULES] == []
    assert [name for name in _SERVED_EVIDENCE if name not in JUDGING_RULES] == []


def test_the_judging_rules_hold_the_reply_references() -> None:
    assert REPLY_REFERENCES in JUDGING_RULES
    assert "undecided" in JUDGING_RULES
    assert "curators" in JUDGING_RULES


def test_every_role_reads_the_judging_rules_first() -> None:
    assert [text.startswith(JUDGING_RULES) for text in _ROLES] == [True] * 4
    assert len({text.removeprefix(JUDGING_RULES) for text in _ROLES}) == 4


def test_every_instruction_is_ascii() -> None:
    assert [text.isascii() for text in (JUDGING_RULES, *_ROLES)] == [True] * 5
